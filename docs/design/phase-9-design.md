# rag-engine – Tech Design (Phase 9: LightRAG Refactor, Disable Citations)

**Mục tiêu**: Refactor backend để dùng LightRAG trực tiếp (không qua RAG-Anything) cho ingest + query, đồng thời tạm tắt cơ chế trích xuất nguồn/citation trong pipeline chat. Phase 9 chỉ nhằm đưa hệ thống về trạng thái ổn định, chuẩn bị nền cho Phase 9.1.

---

## 1. Tech Stack & Quyết định chính

- **Backend**: Python 3.12 + FastAPI (async) (giữ nguyên).
- **Database**:
  - Supabase Postgres (ứng dụng chính).
  - PGVector / LightRAG tables (`LIGHTRAG_*`) dùng làm vector + graph storage.
- **RAG Engine**:
  - **LightRAG** (`LightRAG/lightrag`) dùng trực tiếp.
  - RAG-Anything **không còn dùng trong runtime** (chỉ còn như vendor code trong repo).
- **LLM**:
  - Tạm thời có 2 lựa chọn (configurable):
    - Dùng luôn `lightrag.aquery_llm` (LightRAG tự gọi LLM).
    - Hoặc dùng Answer LLM riêng (pipeline Phase 8) nhưng **không build citations**.
  - Phase 9 ưu tiên phương án đơn giản, có thể chọn `aquery_llm` trước, sau đó nếu cần vẫn giữ Option B để dễ migrate sang Phase 9.1.
- **Other**:
  - Logging: dùng `server.app.core.logging.get_logger`.
  - Config: `pydantic-settings` (module `server.app.core.config`).

Quyết định chính:
- **LightRAG là nguồn duy nhất cho retrieval** (vector + graph).
- **Không parse prompt của LightRAG để build citation** trong Phase 9.
- **Không thay đổi schema DB chính**, chỉ đổi cách server gọi RAG.

---

## 2. Cấu trúc Folder & Module (Source Code)

Các thư mục chính liên quan Phase 9:

```text
server/
  app/
    core/
      config.py          # RagSettings, AnswerSettings (Phase 8), bổ sung LightRAG config nếu cần
      logging.py

    services/
      rag_engine.py      # Refactor: LightRAG-only wrapper
      answer_engine.py   # Refactor: bỏ citation, gọi RagEngineService mới

    api/
      routes/
        messages.py      # Chat API, gọi AnswerEngineService

LightRAG/
  lightrag/              # Core LightRAG (vendor)

RAG-Anything/
  raganything/           # Không dùng trực tiếp trong runtime (Phase 9)
```

Thay đổi chính Phase 9:
- `rag_engine.py`: bỏ import RAG-Anything, khởi tạo `LightRAG` trực tiếp.
- `answer_engine.py`: giữ vai trò orchestrator cho chat, nhưng không build citations.
- `messages.py`: wiring đơn giản hơn, chỉ nhận answer text + usage.

---

## 3. Configuration & Environment

### 3.1. Biến môi trường (Env Vars)

Giữ lại các biến hiện có, bổ sung ghi chú cho LightRAG:

- **Supabase / ứng dụng** (đã có):
  - `SUPABASE_DB_URL` – DSN cho Postgres (được parse để derive `POSTGRES_*`).
- **LightRAG / PGVector**:
  - `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DATABASE`
    - Được `RagEngineService._ensure_postgres_env_from_supabase()` set từ `SUPABASE_DB_URL` nếu chưa có.
  - `EMBEDDING_DIM` – số chiều vector; phải khớp với embedding model (vd `3072`).
  - Các env khác của LightRAG (tùy chọn):
    - `TOP_K`, `CHUNK_TOP_K`, `MAX_TOTAL_TOKENS`, `COSINE_THRESHOLD`, v.v. – dùng default nếu không set.
- **OpenAI / LLM**:
  - `OPENAI_API_KEY`
  - `OPENAI_BASE_URL` (optional)

Phase 9 không thêm env mới bắt buộc; chỉ cần đảm bảo cấu hình hiện tại đủ cho LightRAG chạy trực tiếp.

### 3.2. Config Loader

- `server/app/core/config.py`:
  - `RagSettings` hiện đã chứa:
    - `working_dir`
    - `llm_model`
    - `embedding_model`
    - `query_mode`
  - Phase 9:
    - Tiếp tục dùng `RagSettings` cho LightRAG (model name, working_dir, query_mode).
    - Nếu cần, thêm vài field LightRAG-specific (vd `top_k`, `chunk_top_k`) nhưng không bắt buộc.

---

## 4. Database Layer Design

### 4.1. Models (Schema Mapping)

- Không thêm bảng mới trong DB chính (Supabase).
- Các bảng `LIGHTRAG_*` vẫn do LightRAG tạo/maintain qua PGVector:
  - `LIGHTRAG_VDB_CHUNKS`, `LIGHTRAG_VDB_ENTITY`, `LIGHTRAG_VDB_RELATION`, …
  - Ứng dụng **không định nghĩa lại** các bảng này qua SQLAlchemy; chỉ tương tác qua LightRAG API.

### 4.2. Repositories / Data Access

- `db/repositories.py` vẫn chỉ phục vụ:
  - Workspaces, documents, conversations, messages, jobs.
- Phase 9:
  - Không thêm repository mới cho RAG; mọi tương tác với RAG đều qua `RagEngineService` (LightRAG wrapper).

---

## 5. Service Layer & External Integrations

### 5.1. RagEngineService (LightRAG-only)

File: `server/app/services/rag_engine.py`

**Mục tiêu**:
- Bao bọc LightRAG, giấu đi chi tiết cấu hình PGVector / workspace / working_dir.
- Cung cấp interface đơn giản cho phần còn lại của app.

#### 5.1.1. Khởi tạo & lifecycle

- Thuộc tính:
  - `self.settings: RagSettings`
  - `self._instances: dict[str, LightRAG]` – map `workspace_id` → LightRAG instance.

- Hàm private:
  - `_ensure_postgres_env_from_supabase()` – giữ lại logic hiện tại:
    - Parse `SUPABASE_DB_URL` → set `POSTGRES_*`, `EMBEDDING_DIM` nếu chưa có.
  - `_get_lightrag_instance(workspace_id: str) -> LightRAG`:
    - Nếu đã tồn tại trong `self._instances` → trả về.
    - Nếu chưa:
      - Gọi `_ensure_postgres_env_from_supabase()`.
      - Khởi tạo `LightRAG`:
        - `working_dir = os.path.join(self.settings.working_dir, workspace_id)`
        - `workspace = workspace_id`
        - `kv_storage = "PGKVStorage"`
        - `vector_storage = "PGVectorStorage"`
        - `doc_status_storage = "PGDocStatusStorage"`
        - `graph_storage` – để default hoặc cấu hình nếu cần.
        - `llm_model_func` và `embedding_func` giống như đã build cho RAG-Anything, nhưng truyền trực tiếp vào `LightRAG`.
      - Gọi `await lightrag.initialize_storages()` trước khi dùng.
    - Cache instance trong `self._instances`.

> Lưu ý: RAG-Anything sẽ không còn được import trong file này.

#### 5.1.2. Ingest API

Ký hiệu giữ gần giống API cũ để hạn chế thay đổi caller:

```python
async def ingest_content(
    self,
    workspace_id: str,
    document_id: str,
    content_list: list[dict],
    file_path: str,
    doc_id: str | None = None,
) -> str:
    """
    Ingest content_list vào LightRAG; trả về rag_doc_id (doc_id trong LightRAG).
    """
```

Implementation tổng quan:

1. Lấy `lightrag = self._get_lightrag_instance(workspace_id)`.
2. `rag_doc_id = doc_id or str(document_id)`.
3. Chuẩn bị `full_text` và `text_chunks` cho LightRAG:
   - Phase 9 **không thay đổi cách build content_list** (tận dụng `chunker.py` hiện có).
   - Có 2 lựa chọn:
     - Option A: nối `content_list[*]["text"]` thành `full_text`, để LightRAG tự chunk (đơn giản hơn).
     - Option B: map `content_list` → danh sách `{"content": text, "chunk_order_index": i}` rồi gọi `ainsert_custom_chunks`.
   - Phase 9, ưu tiên Option A (đơn giản) để giảm rủi ro; việc tinh chỉnh chunk sẽ thuộc Phase 9.x nếu cần.
4. Gọi:

```python
await lightrag.ainsert(
    full_text,
    doc_id=rag_doc_id,
    file_path=file_path,
)
```

5. Log ingest thành công, trả về `rag_doc_id`.

#### 5.1.3. Query API

Phase 9 chỉ cần một API để trả answer text (không citations):

```python
async def query_answer(
    self,
    workspace_id: str,
    question: str,
    mode: str | None = None,
    system_prompt: str | None = None,
) -> tuple[str, dict[str, int] | None]:
    """
    Gọi LightRAG để trả về (answer_text, usage).
    usage là dict đơn giản (prompt_tokens, completion_tokens, total_tokens) nếu lấy được.
    """
```

Gợi ý implementation:

1. Lấy `lightrag = self._get_lightrag_instance(workspace_id)`.
2. Build `QueryParam`:

```python
from lightrag import QueryParam

query_mode = mode or self.settings.query_mode  # ví dụ: "mix"
param = QueryParam(mode=query_mode)
```

3. Gọi `await lightrag.aquery_llm(question, param, system_prompt=system_prompt)`:
   - Hàm này trả về dict `raw_data` với:
     - `data`: kết quả retrieval.
     - `metadata`: metadata.
     - `llm_response`: `{ content, response_iterator, is_streaming }`.
4. Phase 9:
   - Chỉ cần:
     - `answer_text = raw_data["llm_response"]["content"] or ""`.
     - Nếu LightRAG có metadata về tokens thì có thể map sang `usage`; nếu không, usage = `None`.

> Không sử dụng `only_need_prompt` hay `aquery_data` trong Phase 9 (để tránh phức tạp).  
> Các API retrieval-only sẽ được khai thác trong Phase 9.1.

### 5.2. AnswerEngineService (no citation)

File: `server/app/services/answer_engine.py`

**Mục tiêu**:
- Đơn giản hóa để:
  - Nhận câu hỏi từ API.
  - Gọi `RagEngineService.query_answer`.
  - Trả về text câu trả lời (và usage nếu có).
- Tạm thời tắt toàn bộ logic Explainable RAG (sections, citations).

#### 5.2.1. Interface

```python
class AnswerEngineService:
    def __init__(self, rag_engine: RagEngineService, ...):
        ...

    async def answer_question(
        self,
        workspace_id: str,
        conversation_id: UUID,
        question: str,
        history: list[dict] | None = None,
    ) -> dict[str, Any]:
        """
        Trả về:
        {
          "answer": str,
          "llm_usage": {...} | None
        }
        """
```

#### 5.2.2. Logic chính

1. (Optional) Build `system_prompt` / `conversation history` nếu cần cho LightRAG:
   - Phase 9 đơn giản có thể để LightRAG tự dùng history/param mặc định (hoặc không dùng history).
2. Gọi:

```python
answer_text, usage = await self.rag_engine.query_answer(
    workspace_id=workspace_id,
    question=question,
    mode=None,
    system_prompt=None,
)
```

3. Trả về dict:

```python
return {
    "answer": answer_text,
    "llm_usage": usage,
}
```

Không còn trường:
- `sections`
- `citations`
- `retrieved_segments`

### 5.3. Integration với API routes

File: `server/app/api/routes/messages.py`

- Trong handler tạo message AI:
  - Thay vì:
    - Gọi `AnswerEngineService` rồi đọc `sections`, `citations`, attach vào `metadata`.
  - Phase 9:
    - Gọi `result = await answer_engine.answer_question(...)`.
    - Tạo message AI:

```python
metadata = {}
if result.get("llm_usage"):
    metadata["llm_usage"] = result["llm_usage"]

ai_message = MessageCreate(
    role="ai",
    content=result["answer"],
    metadata=metadata,
)
```

Client nhận message:
- `content`: câu trả lời text.
- `metadata.llm_usage`: optional.
- Không còn `metadata.sections` hay `metadata.citations` cho message mới.

---

## 6. API Design & Routes

Phase 9 **không thay đổi contract API** (URL + shape body) ngoại trừ việc **metadata AI message không còn field citation**.

- `POST /api/conversations/{conversation_id}/messages`:
  - Request: giữ nguyên.
  - Response:
    - `messages[*].content`: string.
    - `messages[*].metadata`:
      - Có thể chứa:
        - `llm_usage` (dict) – optional.
      - **Không** thêm/đảm bảo `sections`, `citations` cho message được tạo trong Phase 9.

Các API khác (documents, workspaces, raw-text, ingest) **giữ nguyên**.

---

## 7. Background Workers / Jobs

Các worker ingest (Phase 2/3) vẫn giữ nguyên:

- Job parse bằng Document AI.
- Job ingest RAG:
  - Tại bước gọi `RagEngineService.ingest_content(...)`, implementation bên trong đã đổi sang LightRAG.

Không thêm job mới trong Phase 9.

---

## 8. Security & Authentication

- Không thay đổi:
  - Supabase Auth vẫn là nguồn JWT.
  - Middleware verify JWT, lấy `user_id`.
  - Check quyền workspace/document ở layer API/DB (`WHERE workspace.user_id = current_user.id`).
- LightRAG sử dụng Postgres của Supabase **chung cluster**, nhưng:
  - Tách namespace qua `workspace` + prefix bảng `LIGHTRAG_*`.
  - Không expose trực tiếp qua API, chỉ truy cập qua backend.

---

## 9. Logging & Monitoring

- `rag_engine.py`:
  - Log:
    - Khởi tạo LightRAG (per workspace).
    - Thông tin ingest: workspace, document_id, rag_doc_id, số lượng block.
    - Query: workspace, mode, preview câu hỏi, thời gian xử lý (nếu có).
- `answer_engine.py`:
  - Log:
    - Bắt đầu/hoàn thành answer cho conversation_id.
    - Nếu LightRAG trả lỗi, log error rõ ràng.

Không bổ sung hệ thống monitoring mới trong Phase 9, nhưng log nên đủ để debug pipeline mới.

---

## 10. Kế hoạch Implement & Testing

**Thứ tự triển khai đề xuất:**

1. Refactor `RagEngineService`:
   - Tạo `_get_lightrag_instance` mới.
   - Thay `ingest_content` sang `lightrag.ainsert`.
   - Thêm `query_answer`.
2. Cập nhật `AnswerEngineService`:
   - Dùng `query_answer`.
   - Bỏ mọi code liên quan đến `sections`, `citations`, `retrieved_segments`.
3. Điều chỉnh `messages.py`:
   - Ghi message AI chỉ với `content` + `llm_usage`.
4. Dọn dẹp code cũ (có thể comment/TODO):
   - Đánh dấu các hàm liên quan citation để Phase 9.1 xem lại (hoặc xóa nếu chắc chắn không dùng).
5. Testing thủ công:
   - Tạo workspace mới, upload vài tài liệu (cả bảng, text).
   - Check:
     - Ingest không lỗi.
     - Chat trả lời được (dù chưa có nguồn).
     - Không còn lỗi liên quan `segment_index`, `document_id` kiểu UUID.

---

## 11. Ghi chú & Kết luận

- Phase 9 **không giải quyết** vấn đề explainable RAG / citation chính xác; mục tiêu là:
  - Đơn giản hóa pipeline,
  - Dùng LightRAG đúng cách,
  - Tránh các lớp mapping phức tạp khiến kết quả lệch và khó debug.
- Citation v2 (luôn có nguồn, align tốt với text, xử lý tốt bảng/cột) sẽ được đặc tả trong:
  - `requirements-phase-9.1.md`
  - `phase-9.1-design.md`
  và có thể tận dụng các API `aquery_data`/`QueryResult` của LightRAG.

