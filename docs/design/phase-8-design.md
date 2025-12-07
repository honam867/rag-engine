# rag-engine – Tech Design (Phase 8: Retrieval-Only RAG & Answer Orchestrator)

**Mục tiêu**: Chuyển đặc tả Phase 8 thành thiết kế kỹ thuật cụ thể, xây dựng:
- Lớp **Retrieval Engine** chỉ dùng RAG-Anything/LightRAG cho ingest + retrieval.
- Lớp **Answer Orchestrator** làm “hộp đen trả lời” duy nhất cho chat, dễ scale, dễ mở rộng.

---

## 1. Tech Stack & Quyết định chính

- **Backend**: Python + FastAPI (async), giữ nguyên kiến trúc hiện tại.
- **Database**: Supabase Postgres với SQLAlchemy Core async.
- **Authentication**: Supabase Auth JWT, reuse `get_current_user`.
- **External Services**:
  - Google Cloud Document AI (Phase 2) – OCR + JSON, không đổi.
  - Cloudflare R2 – lưu file gốc + JSON raw, không đổi.
  - RAG-Anything / LightRAG:
    - Phase 8: chỉ dùng cho **ingest + retrieval**, không dùng `aquery` cho chat.
- **LLM Provider**:
  - Một lớp client riêng (không đi qua LightRAG) gọi OpenAI-compatible APIs.
  - Sau này có thể route sang nhiều model/provider khác (Anthropic, Gemini, local, …).
- **Other**:
  - Redis event bus, realtime, workers giữ nguyên từ Phase 5/6.

**Quyết định chính Phase 8**:
- RAG-Anything trở thành **Retrieval Engine**, không còn là “Answer Box” cho chat.
- Tất cả logic:
  - build prompt,
  - định dạng JSON answer,
  - map citations,
  - tracking LLM usage  
  đều nằm trong Answer Orchestrator, dưới sự kiểm soát của rag-engine.

---

## 2. Cấu trúc Folder & Module (Source Code)

Giữ layout hiện tại, bổ sung/điều chỉnh các module sau:

```text
server/
  app/
    services/
      rag_engine.py          # Giữ ingest vào RAG-Anything + (mới) expose retrieval-only helpers
      chunker.py             # Segmentation từ DocAI JSON (Phase 7.1) – canonical segments
      answer_engine.py       # NEW: Answer Orchestrator (hộp đen trả lời)
      llm_client.py          # NEW: LLM abstraction (OpenAI-compatible, tracking usage)
    api/
      routes/
        messages.py          # Cập nhật dùng AnswerEngineService thay vì RagEngineService.query
```

Ghi chú:
- Không đổi high-level layout `server/app/*`.
- `rag_engine.py`:
  - Giữ `ingest_content`, `delete_*`.
  - Thêm API retrieval-only (hoặc helper) dùng LightRAG.
- `answer_engine.py` + `llm_client.py` được thiết kế độc lập với RAG-Anything:
  - Không import từ `raganything/`.

---

## 3. Configuration & Environment

### 3.1. Biến môi trường (Env Vars)

Bổ sung nhóm config mới cho LLM Answer Engine (nếu chưa có):

- `ANSWER_LLM_MODEL` – model chính cho Answer Orchestrator (ví dụ: `gpt-4.1-mini`).
- `ANSWER_LLM_BASE_URL` – base URL (nếu dùng provider không phải OpenAI).
- `ANSWER_LLM_API_KEY` – API key riêng (có thể reuse `OPENAI_API_KEY` hiện tại, nhưng tách config để linh hoạt).
- `ANSWER_LLM_MAX_TOKENS` – giới hạn tokens cho completion.
- `ANSWER_LLM_TEMPERATURE` – default temperature cho answer.

Có thể reuse `RagSettings` hoặc tạo `LLMSettings` / `AnswerSettings` mới trong `core/config.py`:

```python
class AnswerSettings(BaseSettings):
    model: str = "gpt-4.1-mini"
    base_url: str | None = None
    api_key: str | None = None
    max_tokens: int = 2048
    temperature: float = 0.2
```

### 3.2. Config Loader

- Mở rộng `get_settings()` để include `answer: AnswerSettings` và/hoặc `llm: LLMSettings`.
- `AnswerEngineService` và `LLMClient` nhận config qua dependency injection (tránh hard-code env).

---

## 4. Database Layer Design

### 4.1. Models (Schema Mapping)

- Không thay đổi bảng hiện có (`documents`, `rag_documents`, `conversations`, `messages`).
- `messages.metadata` vẫn là JSON:
  - Phase 8 dùng các key:
    - `"sections"` – danh sách AnswerSection.
    - `"citations"` – flatten citations.
    - `"llm_usage"` – usage của lần gọi LLM.
    - `"retrieved_segments"` – optional (nếu muốn expose cho client).

Ví dụ metadata Phase 8:

```json
{
  "sections": [
    {
      "text": "Người được ủy quyền công bố thông tin là Trần Phương, Phó Tổng Giám đốc.",
      "source_ids": ["957e...c7a:1"],
      "citations": [
        {
          "document_id": "957e3456-5d7e-4178-b204-51529d9f9c7a",
          "segment_index": 1,
          "page_idx": 0,
          "snippet_preview": "Báo cáo tài chính hợp nhất giữa niên độ..."
        }
      ]
    }
  ],
  "citations": [
    {
      "document_id": "957e3456-5d7e-4178-b204-51529d9f9c7a",
      "segment_index": 1,
      "page_idx": 0,
      "snippet_preview": "Báo cáo tài chính hợp nhất giữa niên độ..."
    }
  ],
  "llm_usage": {
    "model": "gpt-4.1-mini",
    "prompt_tokens": 1234,
    "completion_tokens": 210,
    "total_tokens": 1444
  }
}
```

### 4.2. Repositories / Data Access

- Reuse repository hiện có:
  - Lấy `documents`, `docai_full_text`, `docai_raw_r2_key`.
  - Lấy `conversations`, `messages`.
- Phase 8 không thêm repository mới bắt buộc; phần retrieval từ RAG-Anything sẽ do service `rag_engine.py` làm việc trực tiếp với LightRAG/PGVector, không qua `repositories.py`.

---

## 5. Service Layer & External Integrations

### 5.1. Retrieval Engine (trên RAG-Anything/LightRAG)

**Mục tiêu**: lấy được danh sách `RetrievedSegment` cho một câu hỏi, không gọi LLM của RAG-Anything.

Thiết kế cao cấp:

- Trong `rag_engine.py`, thêm (hoặc tách) interface:

```python
class RagEngineService:
    ...

    async def retrieve_segments(
        self,
        workspace_id: str,
        question: str,
        top_k: int = 8,
    ) -> list[RetrievedSegment]:
        ...
```

- Bên trong:
  - Lấy `rag = self._get_rag_instance(workspace_id)` như hiện tại.
  - Thay vì `rag.aquery(...)`, dùng LightRAG API để:
    - Chạy search vector/graph với query `question`.
    - Lấy danh sách chunk/chunk_id + text context + score.
  - Nếu LightRAG không expose retrieval-only “đẹp”:
    - Bước 1: tạm thời gọi `rag.lightrag.aquery(..., only_need_context=True)` nếu API cho phép, hoặc tương đương.
    - Bước 2: Parse text context trả về, sử dụng prefix `[SEG=doc_id:segment_index]` để cắt ra từng segment:
      - Regex tìm tất cả `[SEG=...:...]`.
      - Mỗi match → một `segment_id`, substring phía sau tới trước match tiếp theo → `text`.
    - Bước 3: Với mỗi `segment_id`:
      - Split `document_id`, `segment_index` (int).
      - Gán `page_idx` từ segmentation DocAI nếu cần (hoặc 0 nếu không truy ngược).
      - Lưu `score` từ retrieval nếu có (nếu không, có thể đặt thứ tự theo vị trí).

> Lưu ý: Phase 8 ưu tiên phương án sử dụng API retrieval-only của LightRAG nếu có; việc parse từ context `[SEG=...]` là chiến lược fallback, nhưng vẫn an toàn vì chính mình đã đưa `[SEG=...]` vào khi ingest.

**Shape trả về (internal)**:

```python
class RetrievedSegment(BaseModel):
    segment_id: str
    document_id: str
    segment_index: int
    page_idx: int | None
    text: str
    score: float | None
```

### 5.2. LLMClient – Abstraction cho Answer LLM

File mới: `server/app/services/llm_client.py`

Mục tiêu:
- Đóng gói việc gọi OpenAI-compatible APIs.
- Cho phép tracking usage/tokens.
- Dễ mở rộng sang LangChain / tools.

Interface đề xuất:

```python
class LLMUsage(BaseModel):
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class LLMClient:
    def __init__(self, settings: AnswerSettings): ...

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema_hint: str | None = None,
    ) -> tuple[str, dict | None, LLMUsage | None]:
        """
        Trả về (raw_text, parsed_json, usage).
        """
```

Implementation:
- V1: sử dụng OpenAI official client (hoặc HTTP) với `response_format="json"` nếu khả thi (để giảm rủi ro parse).
- Nếu provider không hỗ trợ `response_format="json"`:
  - Dùng prompt như hiện tại (yêu cầu JSON).
  - Tự parse bằng `json.loads` với heuristic cắt `{...}`.

Tracking:
- Lấy `usage` từ response của LLM (nếu provider trả).
- Nếu không có usage, có thể để `None` hoặc ước lượng sau (Phase sau).

### 5.3. AnswerEngineService – Hộp đen trả lời

File mới: `server/app/services/answer_engine.py`

Mục tiêu:
- Đóng vai trò “single source of truth” cho pipeline:
  - retrieval → prompt build → LLM → mapping citations.
- Không phụ thuộc trực tiếp vào FastAPI/Request.

Interface:

```python
class AnswerEngineService:
    def __init__(
        self,
        rag_engine: RagEngineService,
        llm_client: LLMClient,
        settings: AnswerSettings,
    ): ...

    async def answer_question(
        self,
        workspace_id: str,
        conversation_id: str,
        question: str,
        max_context_segments: int = 8,
    ) -> dict[str, Any]:
        """
        Trả về:
        {
          "answer": str,
          "sections": list[dict],    # {text, source_ids, citations}
          "citations": list[dict],   # flatten
          "retrieved_segments": list[RetrievedSegment],  # optional
          "llm_usage": LLMUsage | None,
        }
        """
```

Logic chi tiết:

1. **Retrieval**:
   - `retrieved_segments = await rag_engine.retrieve_segments(workspace_id, question, top_k=max_context_segments)`.
   - Nếu rỗng:
     - Option A: vẫn gọi LLM nhưng nói rõ “không có tài liệu trong workspace”; citations rỗng.

2. **Build context string**:

```text
Context segments:

[SEG={document_id}:{segment_index}] {segment_text}
...

User question:
{question}
```

3. **System prompt (tiếng Anh để LLM hiểu tốt hơn)**:
   - Mô tả persona (giống Phase 3/7, nhưng tiếng Anh).
   - Mô tả rõ:
     - Trả lời dựa trên context khi có thể; nếu không đủ, hãy nói rõ.
     - Trả về JSON:

```json
{
  "sections": [
    {
      "text": "<answer section>",
      "source_ids": ["{document_id}:{segment_index}", "..."]
    }
  ]
}
```

   - Quy tắc:
     - `source_ids` chỉ được chứa ID xuất hiện trong `[SEG=...]`.
     - Có thể để mảng rỗng nếu không chắc.

4. **Gọi LLMClient.generate_json**:
   - Nhận `(raw_text, parsed_json, usage)`.
   - Nếu `parsed_json` có `sections` hợp lệ:
     - Dùng luôn.
   - Nếu không:
     - Fallback: coi toàn bộ `raw_text` là một section `{"text": raw_text, "source_ids": []}`.

5. **Map `source_ids` → citations**:

   - Tạo map nhanh từ `segment_id` → RetrievedSegment (in-memory):

```python
segment_map = {seg.segment_id: seg for seg in retrieved_segments}
```

   - Với mỗi section:
     - Duyệt `source_ids`:
       - Nếu `segment_id` có trong `segment_map`:
         - Lấy `document_id`, `segment_index`, `page_idx`, `text`.
         - Build `Citation`.
     - Không dùng text-matching hoặc search ngoài `retrieved_segments`.
   - Flatten tất cả citations cho `metadata.citations`.

6. **Build answer string**:
   - `answer = "\n\n".join(section["text"] for section in sections)`

7. **Return object**:
   - Đủ thông tin để `messages.py` lưu vào DB:

```python
return {
    "answer": answer,
    "sections": sections_with_citations,
    "citations": citations_flat,
    "retrieved_segments": retrieved_segments,  # optional
    "llm_usage": usage,
}
```

### 5.4. Khả năng mở rộng (LangChain, tools, history, multi-model)

Thiết kế AnswerEngineService theo hướng “mở rộng được”:

- **LangChain / tools**:
  - `LLMClient` có thể được implement bằng:
    - LangChain `Runnable` pipeline (chaining multiple tools).
    - Function-calling để gọi thêm API (calculator, search, internal services).
  - AnswerEngineService chỉ cần LLMClient trả `(raw_text, parsed_json, usage)` nên không phụ thuộc vào concrete implementation.

- **Multi-model routing**:
  - AnswerSettings có thể chứa nhiều profile:
    - `answer_model`, `rerank_model`, `summary_model`, …
  - LLMClient có thể chọn model theo:
    - Loại câu hỏi,
    - Độ dài context,
    - Policy.

- **History & Memory**:
  - `answer_question` nhận thêm tùy chọn `history_messages` (Phase sau):
    - Load một số message gần nhất từ DB.
    - Build phần “conversation history” trong prompt trước context.
  - Long-term memory:
    - Có thể dùng chính RAG-Anything để retrieval từ “conversation store” khác; kiến trúc này vẫn áp dụng được.

- **Token / cost monitoring**:
  - `LLMClient` luôn cố gắng trả `LLMUsage`.
  - AnswerEngineService truyền `usage` vào `messages.metadata.llm_usage`.
  - Phase sau có thể thêm job tổng hợp chi phí từ metadata.

---

## 6. API Design & Routes

### 6.1. Messages – sử dụng AnswerEngineService

File: `server/app/api/routes/messages.py`

- Hàm `_process_ai_message_background` hiện tại:
  - Gọi `RagEngineService.query` → `rag_result`.
  - Build citations qua `_build_citations_from_source_ids` hoặc text-matching.
- Phase 8 thay đổi:

```python
async def _process_ai_message_background(...):
    settings = get_settings()
    rag_engine = RagEngineService(settings=settings.rag)
    llm_client = LLMClient(settings=settings.answer)
    answer_engine = AnswerEngineService(
        rag_engine=rag_engine,
        llm_client=llm_client,
        settings=settings.answer,
    )

    result = await answer_engine.answer_question(
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        question=question,
    )

    answer = result["answer"]
    sections = result["sections"]
    citations_flat = result["citations"]
    llm_usage = result.get("llm_usage")

    metadata = {"sections": sections}
    if citations_flat:
        metadata["citations"] = citations_flat
    if llm_usage:
        metadata["llm_usage"] = llm_usage.model_dump()

    # update message + send realtime (giống hiện tại)
```

- Không còn gọi `_build_citations_from_source_ids` / `_build_citations_for_sections` trong messages API; logic này nằm trong AnswerEngineService.

### 6.2. Backward compatibility

- Shape `metadata.sections` và `metadata.citations` giữ giống Phase 7.2:
  - Client hiện tại chỉ cần đọc thêm `source_ids`/`citations` như trước.
- Behaviour khác:
  - Citations có thể ít hơn nhưng chính xác hơn (không “đoán” toàn workspace).
  - Với documents cũ, `sections[*].citations` có thể rỗng; client nên handle gracefully.

---

## 7. Background Workers / Jobs

- Không thêm worker mới.
- Thay đổi worker logic:
  - `parse_worker`, `ingest_worker` giữ nguyên.
  - Background “RAG chat worker” thực ra nằm trong chính `_process_ai_message_background` (async task), sử dụng AnswerEngineService.

---

## 8. Security & Authentication

- Không thay đổi:
  - Auth vẫn dựa vào Supabase JWT.
  - Mọi call tới AnswerEngineService đều đi qua API đã được check `current_user` + workspace ownership.
- Retrieval từ RAG-Anything:
  - `RagEngineService._get_rag_instance` đã isolate theo workspace (working_dir + workspace column).
  - AnswerEngineService chỉ gọi retrieval với `workspace_id` hiện tại → không rò rỉ data giữa các workspace.

---

## 9. Logging & Monitoring

- Logging:
  - Retrieval Engine:
    - Log số lượng `retrieved_segments`, preview câu hỏi, workspace_id.
  - AnswerEngineService:
    - Log việc parse JSON (thành công/thất bại).
    - Log số lượng sections, citations.
  - LLMClient:
    - Log model, thời gian gọi, usage (tokens).
- Monitoring:
  - Có thể thêm metric:
    - Tỷ lệ parse JSON thành công.
    - Tỷ lệ section có ít nhất 1 citation.
    - Trung bình tokens per answer.

---

## 10. Kế hoạch Implement & Testing

### Bước implement

1. Tạo `LLMClient` + `AnswerSettings` + wiring config.
2. Mở rộng `RagEngineService` với `retrieve_segments` (tạm thời có thể parse từ context `[SEG=...]` nếu chưa có retrieval-only API).
3. Implement `AnswerEngineService`:
   - Retrieval → prompt → LLM → parse JSON → map citations.
4. Cập nhật `_process_ai_message_background` để dùng AnswerEngineService.
5. Dọn dẹp/tái cấu trúc:
   - Đánh dấu `RagEngineService.query` là legacy (không dùng trong chat).
   - Giữ code citations Phase 7.2 để tham chiếu backward (nếu còn use case khác).
6. Testing end-to-end:
   - Workspace mới với tài liệu ingest sau 7.2:
     - Kiểm tra citations click → nhảy đúng đoạn.
   - Workspace cũ:
     - Đảm bảo không crash, behaviour hợp lý (có thể ít citations).

---

## 11. Ghi chú & Kết luận

- Phase 8 chuyển rag-engine từ chỗ “dựa vào aquery của RAG-Anything” sang:
  - RAG-Anything = **hạ tầng ingest + retrieval**.
  - AnswerEngineService = **nguồn sự thật duy nhất** cho pipeline trả lời & citations.
- Thiết kế này:
  - Tôn trọng các quyết định Phase 2/3/7 (DocAI, segmentation, `[SEG=...]`).
  - Loại bỏ phần “chắp vá” text-matching toàn workspace.
  - Mở đường cho các phase sau:
    - Multi-model, tools, LangChain, memory, multi-hop, v.v.  
  mà không cần thay đổi kiến trúc tổng thêm một lần nữa.

