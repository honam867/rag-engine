# rag-engine – Phase 9.1 Requirements (Source Attribution v2 on LightRAG)

## 1. Mục tiêu & Phạm vi (Goals & Scope)

- **Mục tiêu chính**
  - Thiết kế lại hoàn toàn cơ chế **trích xuất nguồn (citations)** trên nền pipeline Phase 9 (LightRAG-only), nhằm:
    - Mỗi câu trả lời RAG đều **có citations rõ ràng** khi thông tin xuất phát từ tài liệu đã ingest.
    - Citations **bám sát chunk/context mà LightRAG thực sự dùng** (không rebuild từ DB theo cách riêng).
    - Mapping citations → UI raw viewer **ổn định, chính xác, xử lý tốt trường hợp bảng/cột**.
  - Đảm bảo pipeline mới:
    - Không cần parse “prompt text” của LightRAG.
    - Tận dụng tối đa output structured của LightRAG (`aquery_data`, `QueryResult.raw_data`).

- **Phạm vi công việc**
  - Backend / server:
    - Thiết kế lại representation của **nguồn trích dẫn** dựa trên:
      - `data.chunks[*]` và `data.references[*]` của LightRAG (chunk_id, reference_id, file_path, content).
      - (Nếu cần) metadata bổ sung lưu kèm khi ingest (doc_id, page, offset).
    - Mở rộng `AnswerEngineService`:
      - Lấy context chunks trực tiếp từ LightRAG (retrieval-only API).
      - Gọi Answer LLM riêng để sinh `sections + source_ids` trên nền chunk_id/reference_id (không phải UUID segment_index).
      - Attach citations (document, vị trí trong raw viewer) vào `messages.metadata`.
  - Client / UI:
    - Contract dữ liệu sẽ thay đổi so với Phase 7/8 (format `source_ids` & citation).
    - Thiết kế client chi tiết có thể nằm ở tài liệu `client-design-phase-9.1` riêng, nhưng Phase 9.1 backend phải định nghĩa rõ schema response mới.

- **Ngoài phạm vi (Out of scope) cho Phase 9.1**
  - Không đụng tới pipeline parse Document AI (Phase 2) ở mức dịch vụ bên ngoài.
  - Không thay đổi kiến trúc tổng thể server/client trong `architecture-overview.md`.
  - Không cố sửa lại toàn bộ messages đã tạo ở Phase 7/8; citations mới áp dụng cho message tạo từ Phase 9.1 trở đi.

- **Kết quả kỳ vọng (Deliverables)**
  - Tài liệu:
    - `docs/design/phase-9.1-design.md` – chi tiết kiến trúc source attribution v2.
    - (Option) `docs/design/client-design-phase-9.1.md` – cho team client.
  - Khi implement:
    - API chat trả về message AI có:
      - `sections[*].text` + `sections[*].source_ids` (dựa trên chunk_id/reference_id).
      - `citations` đã map tới document & vị trí để raw viewer có thể scroll/highlight.

---

## 2. Các khái niệm & thực thể chính (Key Concepts & Entities)

### 2.1. RetrievalChunk (LightRAG Chunk)

- **Mô tả**
  - Đơn vị context mà LightRAG trả về trong `data.chunks[*]` khi gọi `aquery_data`.
  - Bao gồm:
    - `content: str` – nội dung chunk (text).
    - `chunk_id: str` – id duy nhất trong LightRAG.
    - `reference_id: str` – id dùng để map sang `data.references[*]`.
    - `file_path: str` – (từ LightRAG) đường dẫn file gốc, có thể dùng để suy ra document.
- **Vai trò**
  - Là **anchor chính** cho citation v2:
    - LLM sẽ tham chiếu chunk này qua `chunk_id`/`reference_id`.
    - Backend dùng chunk_id/reference_id → document_id + vị trí.

### 2.2. SourceId v2

- **Mô tả**
  - Định danh trích dẫn mà LLM trả về trong mỗi section.
  - Khác với Phase 7/8 (dùng `"${document_uuid}:${segment_index}"`), Phase 9.1 dùng:
    - `"chunk:{chunk_id}"` hoặc `"ref:{reference_id}"` (tuỳ quyết định cuối).
- **Vai trò**
  - Giúp backend:
    - Match trực tiếp với `RetrievalChunk` từ LightRAG (không cần search trong DB).
    - Sau đó tính ra mapping tới document raw viewer.

### 2.3. Citation v2

- **Mô tả**
  - Cấu trúc backend lưu trong `messages.metadata` để client render bong bóng số & scroll.
- **Thuộc tính (dự kiến)**
  - `source_id: string` – giá trị LLM trả về (`"chunk:..."` hoặc `"ref:..."`).
  - `document_id: UUID` – id document trong DB.
  - `page_idx: int | null` – trang gốc (nếu xác định được).
  - `segment_index: int | null` – index đoạn trong raw viewer (nếu viewer vẫn segment-based).
  - `char_start` / `char_end` (optional) – offset trong `docai_full_text` hoặc trong segment, dùng để highlight chính xác hơn.
  - `snippet_preview: string` – đoạn text ngắn để preview.

### 2.4. AnswerSection v2

- **Mô tả**
  - Giống khái niệm Phase 7/8, nhưng `source_ids` dùng format v2.
- **Thuộc tính**
  - `text: string` – đoạn câu trả lời.
  - `source_ids: string[]` – danh sách `source_id` (chunk/ref) mà LLM gán cho đoạn đó.
  - `citations: CitationV2[]` – sau khi backend resolve.

---

## 3. Luồng nghiệp vụ (User/System Flows)

### 3.1. Query RAG với LightRAG (retrieval-only)

1. User gửi câu hỏi qua API chat như Phase 9.
2. `AnswerEngineService`:
   - Thay vì dùng `RagEngineService.query_answer` (LLM built-in), Phase 9.1 sẽ:
     - Gọi `RagEngineService.retrieve_context(...)` (mới) để:
       - Thực hiện `lightrag.aquery_data(query, QueryParam)` hoặc API tương đương.
       - Nhận về:
         - `chunks = data.chunks[*]`
         - `references = data.references[*]`
         - `metadata` (keywords, query_mode, …).
     - Chuẩn hóa `RetrievalChunk` list từ dữ liệu trên.
3. `AnswerEngineService` build prompt cho Answer LLM:
   - System prompt (tiếng Anh) giải thích:
     - Context là danh sách chunks, mỗi chunk có ID dạng `"chunk:{chunk_id}"` (hoặc `"ref:{reference_id}"`).
     - LLM phải:
       - Trả lời bằng sections.
       - Gán `source_ids` chính xác tương ứng với chunks đã dùng.
   - User prompt gồm:
     - Liệt kê các chunk:

       ```text
       [CHUNK=chunk:abc123]
       <content>

       [CHUNK=chunk:def456]
       <content>
       ...
       ```

     - Sau đó là "User question: ..."
4. Answer LLM trả về JSON:

```jsonc
{
  "sections": [
    {
      "text": "Câu trả lời ...",
      "source_ids": ["chunk:abc123", "chunk:def456"]
    }
  ]
}
```

5. Backend map `source_ids` → `RetrievalChunk` đã lưu:
   - Từ đó tính ra `Citation v2` và lưu vào `messages.metadata`.

### 3.2. Mapping từ RetrievalChunk → document & raw viewer

1. Trong quá trình ingest (Phase 9/9.1):
   - Hệ thống cần có cách lưu mapping:
     - `chunk_id` / `reference_id` → `document_id`, `page_idx`, offset/segment_index.
   - Có thể thực hiện bằng:
     - Lưu metadata trong LightRAG KV storage,
     - Hoặc bảng riêng trong DB ứng dụng (ví dụ `rag_chunks_mapping`), hoặc tái sử dụng `file_path` chuẩn hóa (chứa document_id).
2. Khi cần build citation:
   - Backend dùng `chunk_id`/`reference_id`:
     - Tra mapping → `document_id`, `page_idx`, `segment_index` (nếu có).
     - Từ đó build `Citation v2`.
3. Raw viewer:
   - Khi user click bong bóng số:
     - Client dùng `document_id` + `segment_index` hoặc `char_start` để scroll/highlight đúng đoạn text thô.

Chi tiết chiến lược mapping sẽ được mô tả kỹ trong `phase-9.1-design.md`.

---

## 4. Kiến trúc & Thiết kế kỹ thuật (Overview)

> Đây là overview ở mức requirements; phần triển khai cụ thể sẽ nằm trong `phase-9.1-design.md`.

### 4.1. Backend / Service Layer

- **RagEngineService (mở rộng)**
  - Thêm API retrieval-only:

    ```python
    async def retrieve_context(
        self,
        workspace_id: str,
        question: str,
        mode: str | None = None,
    ) -> RetrievalContext:
        # Gọi LightRAG.aquery_data, trả về chunks + references + metadata
    ```

  - `RetrievalContext` (concept):
    - `chunks: list[RetrievalChunk]`
    - `references: list[ReferenceInfo]`
    - `metadata: dict`

- **AnswerEngineService (v2 với citations)**
  - Sử dụng 2 bước:
    1. Retrieval: `retrieve_context`.
    2. Answer: gọi Answer LLM với context + question → sections + source_ids.
  - Bổ sung logic:
    - Map `source_ids` → `RetrievalChunk`.
    - Map `RetrievalChunk` → `Citation v2`.
    - Gắn `sections` + `citations` vào `messages.metadata`.

### 4.2. Database Schema

- Có thể cần thêm **1 trong 2**:
  - **Option A – Không đổi schema chính**:
    - Encode `document_id` + `page_idx` + offset vào `file_path` khi ingest vào LightRAG (ví dụ: `"doc/{document_id}/page-{page_idx}#start-{offset}"`), để sau này parse ngược từ `file_path`.
  - **Option B – Bảng mapping riêng trong DB**:
    - Bảng mới (ví dụ `rag_chunks_mapping`):

      - `id` (PK, uuid)
      - `workspace_id` (uuid)
      - `chunk_id` (text, unique trong workspace)
      - `document_id` (uuid)
      - `page_idx` (int)
      - `segment_index` (int, optional)
      - `char_start`, `char_end` (int, optional)

    - Ingest job sẽ insert bản ghi mapping tương ứng với mỗi chunk.

Quyết định giữa Option A/B sẽ được chốt trong `phase-9.1-design.md` sau khi cân nhắc trade-off performance & maintainability.

---

## 5. API Endpoints (Dự kiến)

### 5.1. Chat API – Output mới

`POST /api/conversations/{conversation_id}/messages` (AI message):

- **Không đổi** request body.
- Response (message AI) – metadata (concept):

```jsonc
{
  "content": "Câu trả lời...",
  "metadata": {
    "sections": [
      {
        "text": "Câu trả lời phần 1...",
        "source_ids": ["chunk:abc123"],
        "citations": [
          {
            "source_id": "chunk:abc123",
            "document_id": "9f2018a1-06f5-4f14-bd41-c4666f1ceaec",
            "page_idx": 0,
            "segment_index": 37,
            "snippet_preview": "NGƯỜI ĐƯỢC ỦY QUYỀN CÔNG BỐ THÔNG TIN..."
          }
        ]
      }
    ],
    "citations": [
      { "...": "..." }
    ],
    "llm_usage": { "...": "..." }
  }
}
```

Client-design Phase 9.1 sẽ định nghĩa chi tiết cách render số thứ tự bong bóng, scroll/highlight.

---

## 6. Kế hoạch triển khai (Implementation Plan)

1. **Bước 1 – Thiết kế chi tiết**
   - Viết `docs/design/phase-9.1-design.md`:
     - Chọn chiến lược mapping chunk → document (Option A hoặc B).
     - Định nghĩa chính xác schema `RetrievalChunk`, `Citation v2`, `AnswerSection v2`.
     - Thiết kế prompt cho Answer LLM.
2. **Bước 2 – Mở rộng RagEngineService**
   - Implement `retrieve_context` dựa trên LightRAG `aquery_data`.
   - Chuẩn hóa dữ liệu `RetrievalChunk`.
3. **Bước 3 – Cập nhật AnswerEngineService**
   - Thêm bước:
     - Gọi `retrieve_context`.
     - Gọi Answer LLM với context.
     - Build `sections + citations`.
4. **Bước 4 – Cập nhật API & client contract**
   - Cập nhật schema `messages.metadata` (Pydantic schemas).
   - Viết tài liệu cho client (client-design-phase-9.1).
5. **Bước 5 – Testing**
   - Test với tài liệu dạng text & bảng:
     - Hỏi câu liên quan bảng, kiểm tra:
       - Answer đúng.
       - Bong bóng số highlight đúng đoạn trong raw viewer.

---

## 7. Ghi chú & Giả định (Notes & Assumptions)

- LightRAG đã hoạt động ổn định theo Phase 9 (ingest + query).
- Kích thước context (số chunk) từ `aquery_data` đủ để Answer LLM luôn có ít nhất một chunk chứa thông tin cần thiết trong đa số case thực tế.
- Answer LLM:
  - Có khả năng tuân thủ JSON schema (`sections[*].text`, `sections[*].source_ids`).
  - Được prompt đủ rõ để không bịa `source_ids` (hoặc backend sẽ validate và loại bỏ `source_ids` không khớp).
- Việc “luôn có citation” được hiểu là:
  - Khi thông tin thật sự tồn tại trong tài liệu và được retrieval đưa vào context, backend sẽ sinh được ít nhất một citation.
  - Nếu retrieval không tìm được nội dung liên quan, hệ thống có quyền trả lời “Không tìm thấy thông tin” **và không gắn citation giả**.

