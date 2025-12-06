# rag-engine – Tech Design (Phase 7: Explainable RAG & Raw Document Viewer)

**Mục tiêu**: Chuyển `docs/requirements/requirements-phase-7.md` thành thiết kế kỹ thuật cụ thể, bám sát kiến trúc `architecture-overview.md` và các phase trước. Phase 7 tập trung vào:
- Expose text thô (đã OCR) của document cho UI.
- Chuẩn hóa “segments” cho viewer và mapping.
- Mở rộng RAG query để trả câu trả lời có cấu trúc `sections + citations` tham chiếu tới segments.

---

## 1. Tech Stack & Quyết định chính

- **Backend**: Python + FastAPI (async), giống các phase trước.
- **Database**: Supabase Postgres, SQLAlchemy Core async.
- **Authentication**: Supabase Auth JWT, verify trong `core/security.py`, reuse dependency `get_current_user`.
- **External Services**:
  - Google Cloud Document AI (Phase 2) – không thay đổi.
  - Cloudflare R2 (Phase 1/2) – không thay đổi.
  - RAG-Anything + LightRAG (Phase 3) – chỉ thay đổi cách prompt/parse kết quả trong `RagEngineService.query`, không đổi storage.
- **Other**:
  - Redis event bus (Phase 5/6) giữ nguyên; Phase 7 chỉ thêm dữ liệu trong payload message.

Quyết định chính Phase 7:
- Không sửa schema DB; tận dụng:
  - `documents.docai_full_text` làm nguồn text thô.
  - `messages.metadata` để lưu `sections` + `citations`.
- “Segment” chỉ tồn tại ở tầng service/API (không tạo bảng mới).
- Mapping answer → nguồn **không giao cho LLM**, mà dùng chiến lược server-side text matching:
  - LLM chỉ sinh `sections[*].text`.
  - Backend đọc text của mỗi section và so khớp với segments (chunk từ `docai_full_text`) để gán `document_id` + `segment_index` cho citations.

---

## 2. Cấu trúc Folder & Module (Source Code)

Giữ nguyên layout server hiện tại, Phase 7 chạm vào các file:

```text
server/
  app/
    api/
      routes/
        documents.py      # + endpoint raw-text viewer
        messages.py       # vẫn route cũ, nhưng xử lý metadata.sections
    services/
      chunker.py          # reuse / refactor nhỏ để dùng cho viewer
      rag_engine.py       # mở rộng query() → sections + citations
    schemas/
      documents.py        # + schema RawText response
      conversations.py    # nếu cần mở rộng schema Message metadata (ở mức Pydantic)
```

Không tạo module mới ở phase này; chỉ thêm hàm/schema trong các module tương ứng để giữ kiến trúc ổn định.

---

## 3. Configuration & Environment

Phase 7 không yêu cầu env mới. Reuse:
- Config hiện tại của DB, R2, Document AI, RAG.

Lưu ý:
- Prompt cho LLM sẽ dài hơn; cần đảm bảo `RAGSettings` (nếu có `max_tokens`) đủ dư. Nếu cần, thêm hằng số nhỏ trong `RagSettings` (nhưng không bắt buộc trong v1).

---

## 4. Database Layer Design

### 4.1. Models (Schema Mapping)

Reuse `server/app/db/models.py`:
- `documents`:
  - Dùng `docai_full_text` để build segments cho viewer.
- `messages`:
  - Trường `metadata` (JSON) dùng để lưu:
    - `sections`: list sections (Phase 7).
    - Có thể vẫn lưu `citations` flat nếu cần cho backward‑compat (Phase 3).

Không thêm hoặc sửa cột trong DB.

### 4.2. Repositories / Data Access

Chỉ cần reuse:
- `get_document(session, document_id, workspace_id)` – để xác thực document thuộc workspace.
- Seeding/logic parse/ingest giữ nguyên.

Có thể cân nhắc thêm helper mới (không bắt buộc):
- `get_document_full_text(session, document_id, workspace_id)`:
  - SELECT `docai_full_text`, `status`.
  - Hoặc dùng trực tiếp `get_document` rồi đọc field tại tầng API – tránh thêm function nếu không cần.

---

## 5. Service Layer & External Integrations

### 5.1. ChunkerService – Reuse/Refactor cho Segments

File: `server/app/services/chunker.py`

Hiện tại:
- `build_content_list_from_document(document_id: str) -> List[dict]`:
  - Load document + file.
  - Đọc `docai_full_text`.
  - Chunk theo paragraph/fixed size (1500 chars) → tạo `content_list` dạng:
    ```python
    {"type": "text", "text": chunk, "page_idx": 0}
    ```

Yêu cầu Phase 7:
- Tạo 1 helper nội bộ dùng chung cho:
  - `build_content_list_from_document` (ingest).
  - Endpoint raw-text viewer.

Đề xuất:
- Thêm hàm riêng (module-level):
  ```python
  def chunk_full_text_to_segments(full_text: str, max_chunk_chars: int = 1500) -> list[dict]:
      # Trả về list segments: {"segment_index": int, "page_idx": int, "text": str}
  ```
  - Logic chunk:
    - Giữ nguyên cách split theo paragraphs (`\n\n`) và giới hạn `max_chunk_chars` như hiện tại.
    - `page_idx`:
      - V1: vẫn là 0 cho tất cả (trong tương lai có thể map từ JSON Document AI).
  - Gán `segment_index` tăng dần từ 0.

- Sửa `build_content_list_from_document` để reuse helper:
  ```python
  segments = chunk_full_text_to_segments(full_text)
  content_list = [
      {"type": "text", "text": seg["text"], "page_idx": seg["page_idx"]}
      for seg in segments
  ]
  ```

- Endpoint raw-text viewer sẽ dùng `chunk_full_text_to_segments(full_text)` để trả dữ liệu cho UI (xem phần 6.2).

Không đụng vào integration với R2/JSON Document AI ở Phase 7.

### 5.2. RagEngineService – Query với Sections (không còn citations từ LLM)

File: `server/app/services/rag_engine.py`

Hiện tại:
- `query(workspace_id, question, system_prompt=None, mode="mix") -> Dict[str, Any]`:
  - Build `combined_query = system_prompt + question` (đưa JSON schema vào trong prompt).
  - Call `raw_result = await rag.aquery(combined_query, mode=query_mode)`.
  - V2 (Phase 7) sẽ chỉ cố gắng parse JSON sections, không còn kỳ vọng citations từ LLM.

Mục tiêu Phase 7:
- Chuẩn hóa output:
  - `answer_text`: string (toàn bộ câu trả lời để dùng cho `messages.content`).
  - `sections`: list sections (mỗi section có ít nhất `text`).
  - Citations sẽ được gắn ở tầng trên (messages API) sau khi chạy text matching.

Thiết kế chi tiết:

1. **Định nghĩa output nội bộ**
   - Trong `RagEngineService.query`, sau khi gọi LLM, chuẩn hóa output thành:
     ```python
     result = {
         "answer": answer_text: str,
         "sections": list[dict],      # optional nếu JSON không đúng
     }
     ```

2. **Prompt format**
   - Không thay đổi cách gọi `rag.aquery` (vẫn dùng `combined_query`).
   - Điều chỉnh phần hướng dẫn JSON trong `effective_system_prompt`:
     - Yêu cầu LLM trả EXACT JSON với cấu trúc:
       ```json
       {
         "sections": [
           {
             "text": "Đoạn trả lời 1..."
           },
           {
             "text": "Đoạn trả lời 2..."
           }
         ]
       }
       ```
     - Không yêu cầu LLM tự điền `document_id`, `segment_index` hay `snippet_preview`.

3. **Parsing JSON**
   - Sau `raw_result`:
     - `try: parsed = json.loads(raw_result)`.
     - Nếu `parsed` là `dict` và có key `sections`:
       - Validate từng section:
         - `text`: string.
       - `answer_text` = join `section["text"]` với 2 line-break giữa sections.
     - Nếu JSON không đúng:
       - `answer_text = raw_result`.
       - `sections = []`.

4. **Return value cho API layer**
   - `RagEngineService.query` trả:
     ```python
     return {
         "answer": answer_text,
         "sections": sections,
     }
     ```

5. **Backward-compat**
   - `citations` flatten vẫn giữ để những chỗ cũ (Phase 3) không cần section vẫn đọc được list citations tổng quát.

---

## 6. API Design & Routes

### 6.1. Documents – Raw Text Viewer Endpoint

File: `server/app/api/routes/documents.py`

Endpoint mới:

```python
@router.get("/{document_id}/raw-text", response_model=DocumentRawTextResponse)
async def get_document_raw_text(
    workspace_id: str,
    document_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    ...
```

#### Flow backend:

1. Gọi `_ensure_workspace(session, workspace_id, current_user.id)` – reuse logic hiện có.
2. Lấy document:
   - `doc_row = await repo.get_document(session, document_id=document_id, workspace_id=workspace_id)`.
   - Nếu không tồn tại → 404.
3. Kiểm tra trạng thái:
   - Cho phép khi `status in {'parsed', 'ingested'}`.
   - Nếu `status` là `pending` hoặc `error` → 409 (hoặc 400) với message phù hợp (“Document chưa parse xong”).
4. Đọc text:
   - `full_text = (doc_row["docai_full_text"] or "").strip()`.
   - Nếu rỗng → 409/500 tuỳ cách xử lý (có thể coi là lỗi parse và hướng user re-parse).
5. Chunk thành segments:
   - Gọi `_chunk_full_text_to_segments(full_text)` từ `ChunkerService` (có thể dùng trực tiếp helper module-level hoặc khởi tạo service).
6. Trả response:
   - Pydantic schema (xem 6.2):
     ```json
     {
       "document_id": "...",
       "workspace_id": "...",
       "status": "parsed",
       "segments": [
         { "segment_index": 0, "page_idx": 0, "text": "..." }
       ]
     }
     ```

### 6.2. Schemas – Documents Raw Text

File: `server/app/schemas/documents.py`

Thêm các model:

```python
class DocumentSegment(BaseModel):
    segment_index: int
    page_idx: int
    text: str


class DocumentRawTextResponse(BaseModel):
    document_id: UUID
    workspace_id: UUID
    status: str
    segments: list[DocumentSegment]
```

Endpoint `/raw-text` sẽ dùng `DocumentRawTextResponse` làm `response_model`.

### 6.3. Messages – Lưu & Trả Sections + Citations

File: `server/app/api/routes/messages.py`

Luồng hiện tại trong `_process_ai_message_background`:
- Gọi `rag_engine.query(...)` → `rag_result`.
- Lấy `answer = rag_result.get("answer")`.
- Lưu message AI:
  ```python
  updated_ai_msg = await repo.update_message(
      ...,
      content=answer or "...fallback...",
      status=MESSAGE_STATUS_DONE,
      metadata={"citations": citations} if citations else {},
  )
  ```

Phase 7 thay đổi:

1. Sau khi gọi `rag_engine.query`:
   ```python
   answer = rag_result.get("answer") or ""
   sections = rag_result.get("sections") or []
   ```

2. Mapping citations ở server (text matching):
   - Tại `_process_ai_message_background`, sau khi có `sections`:
     - Load các documents trong workspace với `status in ('parsed', 'ingested')` và `docai_full_text` không rỗng.
     - Dùng `chunk_full_text_to_segments` để tạo segments cho từng document.
     - Với mỗi section:
       - So khớp `section["text"]` với text của từng segment (thuật toán similarity chuỗi đơn giản).
       - Chọn 1–N segment tốt nhất (trên một ngưỡng) làm nguồn.
       - Tạo `citations` cho section:
         ```python
         {
           "document_id": <uuid thực>,
           "segment_index": <int>,
           "page_idx": <int>,
           "snippet_preview": <đoạn text nguồn rút gọn>
         }
         ```
     - Build `sections_with_citations` và `citations_flat`.

3. Lưu metadata:
   ```python
   metadata: dict[str, Any] = {}
   if sections_with_citations:
       metadata["sections"] = sections_with_citations
   if citations_flat:
       metadata["citations"] = citations_flat
   ```

4. Update message:
   ```python
   updated_ai_msg = await repo.update_message(
       ...,
       content=answer or "...fallback...",
       status=MESSAGE_STATUS_DONE,
       metadata=metadata or None,
   )
   ```

5. Realtime event:
   - Payload `message` trong event `message.status_updated` nên kèm `metadata` để UI đọc được sections/citations.

### 6.4. Schemas – Conversations / Messages

File: `server/app/schemas/conversations.py`

Hiện tại:
- `Message` có field `metadata: dict | None`.

Phase 7:
- Vẫn giữ `metadata: dict | None` (không cần nested Pydantic model phức tạp để tránh breaking client).
- Có thể thêm type hint docstring:
  - `metadata["sections"]` expected shape để dev/client đọc được.

---

## 7. Background Workers / Jobs

Phase 7 không thêm worker mới.
- `parse_worker`, `ingest_worker` giữ nguyên, chỉ đảm bảo:
  - Documents có `docai_full_text` để raw-text viewer sử dụng.
  - `rag_documents` mapping vẫn hoạt động như cũ.

---

## 8. Security & Authentication

- Raw-text viewer endpoint:
  - Reuse `_ensure_workspace` + `get_current_user` như các documents API khác.
  - Người dùng chỉ xem được raw text của document thuộc workspace của mình.

- Chat messages:
  - Không thay đổi logic auth; chỉ bổ sung dữ liệu trong metadata.

Không cần phân quyền mới ở Phase 7.

---

## 9. Logging & Monitoring

- Logging trong `RagEngineService.query`:
  - Log:
    - Query mode, workspace_id.
    - Việc parse JSON thành sections/citations (success/fail).
    - Số lượng sections/citations.
- Logging trong endpoint raw-text:
  - Log document_id, workspace_id, số segments trả về.

Monitoring:
- Nếu sau này có metric:
  - Tỷ lệ JSON parse thành công từ LLM (để theo dõi độ ổn định prompt).
  - Tỷ lệ document không có `docai_full_text` nhưng `status` đã `parsed` (lỗi pipeline Phase 2).

---

## 10. Kế hoạch Implement & Testing

### 10.1. Thứ tự implement

1. **Chunker helper cho segments**
   - Refactor `ChunkerService` để có `_chunk_full_text_to_segments`.
2. **Endpoint raw-text**
   - Thêm schema `DocumentSegment`, `DocumentRawTextResponse`.
   - Implement `GET /raw-text` trong `documents.py`.
3. **RagEngineService.query**
   - Điều chỉnh prompt (system_prompt) để yêu cầu JSON sections + citations.
   - Implement logic parse JSON → `answer` + `sections` + `citations_flat`.
4. **Messages API**
   - Cập nhật `_process_ai_message_background` để lưu `metadata.sections` + `metadata.citations`.
   - Đảm bảo event realtime mang theo metadata mới.
5. **Client (out of this codebase, nhưng cần spec)**
   - Gọi endpoint raw-text để load viewer.
   - Render sections + bong bóng citations.
   - Hover/click bong bóng → scroll/highlight segment.

### 10.2. Testing

- Unit test (nếu có test infrastructure):
  - Test `_chunk_full_text_to_segments` với text dài, newline, empty text.
  - Test `RagEngineService.query` với:
    - Stub RAG returning valid JSON.
    - Stub RAG returning plain text.
  - Test documents raw-text endpoint:
    - Document không tồn tại → 404.
    - Document status không hợp lệ → 409/400.
    - Document có full_text → segments đúng số lượng.

---

## 11. Ghi chú & Kết luận

- Phase 7 bổ sung lớp explainability cho RAG mà không đổi pipeline ingest hoặc schema DB:
  - Thêm viewer text thô (dựa trên `docai_full_text`).
  - Chuẩn hóa mapping câu trả lời → nguồn ở cấp segment.
- Những điểm cố ý để Phase sau có thể nâng cấp:
  - `page_idx` trong segments/citations có thể được map chính xác từ JSON Document AI (Phase sau).
  - Có thể thay chiến lược mapping answer → source sang embedding-based alignment nếu cần nâng độ chính xác.
  - Nếu UI cần phân biệt loại nguồn (text/table/figure), có thể enrich segments/citations với `source_type` mà không đổi giao diện chính.

Thiết kế này giữ nguyên kiến trúc core (API → services → db), không phá vỡ các phase trước, và tạo foundation rõ ràng cho việc hiển thị citations như NotebookLM trong UI.
