# Phase 3 – Tech Design (RAG Engine Integration với RAG‑Anything)

Mục tiêu: chuyển đặc tả Phase 3 trong `../requirements/requirements-phase-3.md` thành thiết kế kỹ thuật cụ thể, sử dụng RAG‑Anything như thư viện trong backend FastAPI, bám sát kiến trúc `architecture-overview.md` và dữ liệu đã có từ Phase 2.

---

## 1. Phạm vi Phase 3 (tech)

- Thiết kế **integration layer** giữa app và RAG‑Anything (LightRAG):
  - Khởi tạo RAG‑Anything với cấu hình linh hoạt (embedding/LLM/storage).
  - Cung cấp interface backend: `ingest_content(...)`, `query(...)`, `delete_document(...)`.
- Thiết kế **chunker** dựa trên dữ liệu Phase 2:
  - Đọc `documents.docai_full_text` và JSON raw (từ R2).
  - Tạo `content_list` đúng schema RAG‑Anything (ít nhất text + page_idx) để dùng với `insert_content_list`.
- Thiết kế **ingestion worker** cho document đã `parsed`:
  - Tìm documents `status='parsed'`, chưa có `rag_documents`.
  - Chunk → ingest vào RAG‑Anything → lưu `rag_doc_id` và set `status='ingested'`.
- Mở rộng **API chat** để gọi RAG Engine:
  - `POST /conversations/{conversation_id}/messages` lưu message `user`, gọi RAG, lưu message `ai` + citations.

Không làm ở Phase 3:

- Chưa tối ưu hóa: reranking, VLM multimodal query, tools, long‑term memory, workflow phức tạp.
- Vector DB được chốt là **Supabase Postgres với PGVector** (sử dụng các storage class PGKVStorage/PGVectorStorage/PGDocStatusStorage trên cùng cụm Postgres với app), không dùng Neo4j ở v1.

---

## 2. RAG Engine layer (`services/rag_engine.py`)

### 2.1. Vai trò & interface

Module `services/rag_engine.py` đóng vai trò “adapter” giữa app và RAG‑Anything:

```python
class RagEngineService:
    def __init__(self, settings, llm_client, embedding_client):
        """
        settings: config chung (RAG storage dir, model name, query mode,...)
        llm_client: wrapper gọi LLM (OpenAI, local, v.v.)
        embedding_client: wrapper gọi embedding model
        """

    async def ingest_content(
        self,
        workspace_id: str,
        document_id: str,
        content_list: list[dict],
        file_path: str,
        doc_id: str | None = None,
    ) -> str: ...

    async def query(
        self,
        workspace_id: str,
        question: str,
        system_prompt: str | None = None,
        mode: str = "mix",
    ) -> dict: ...

    async def delete_document(self, workspace_id: str, rag_doc_id: str) -> None: ...
```

Yêu cầu chính:

- **ingest_content**:
  - Nhận `content_list` (đã chunked) và meta:
    - `workspace_id`, `document_id` (PG id).
    - `file_path` (string hiển thị nguồn, ví dụ `"{workspace_id}/{document_id}/{original_filename}"`).
    - `doc_id`: nếu `None`, dùng `str(document_id)` để doc_id trong RAG map 1–1 với document trong DB.
  - Gọi `rag.insert_content_list(...)` từ RAG‑Anything.
  - Trả về `rag_doc_id` (chính là doc_id đã dùng hoặc do RAG sinh, tùy strategy).
- **query**:
  - Nhận câu hỏi, workspace.
  - Chuẩn bị `system_prompt` persona (Tiếng Việt, “mình/bạn”, ưu tiên kiến thức workspace nhưng được phép dùng hiểu biết chung).
  - Gọi `rag.aquery(...)` hoặc hàm wrapper tương tự và trả về:
    - `answer` (string).
    - `citations` (list đơn giản, ví dụ: `{file_path, page_idx}`).
- **delete_document**:
  - Xoá document khỏi RAG storage (dùng API LightRAG/RAG‑Anything tương ứng).  
  - NẾU RAG‑Anything chưa có hàm xóa tiện, có thể đánh dấu/logical delete hoặc để Phase sau.

### 2.2. Khởi tạo RAG‑Anything

RAG‑Anything class chính: `raganything.raganything.RAGAnything`.

Trong `RagEngineService.__init__`:

- Đọc config RAG từ `settings` (ví dụ từ env / `core/config.py`):
  - `RAG_WORKING_DIR` – thư mục chứa LightRAG storage (file/SQLite/kv).
  - `RAG_QUERY_MODE` – mặc định `"mix"`.
  - `RAG_CHUNK_TOKEN_SIZE`, `RAG_MAX_TOKENS`, … (tuỳ chọn).
- Tạo instance:

```python
from raganything.raganything import RAGAnything

self._rag = RAGAnything(
    llm_model_func=llm_client.call_llm,           # wrapper hàm async cho LLM
    embedding_func=embedding_client.embed_text,   # wrapper hàm async/sync cho embedding
    lightrag_kwargs={
        "working_dir": settings.rag_working_dir,
        # thêm các tham số khác nếu cần (top_k, chunk sizes,...)
    },
)
```

- Dựa trên code `RAGAnything._ensure_lightrag_initialized`, khi lần đầu gọi `insert_content_list`/`aquery`, nó sẽ:
  - Tự khởi tạo LightRAG với `llm_model_func`, `embedding_func` và `lightrag_kwargs`.
  - Chuẩn bị parse cache, modal processors, v.v.

Lưu ý:

- Phase 3 tech design không ép buộc loại LLM/embedding cụ thể (có thể là OpenAI, local, v.v.).  
- Quan trọng là `llm_client` và `embedding_client` có interface chuẩn và được inject vào `RagEngineService`.

### 2.3. Isolation theo workspace

Yêu cầu logic: query theo `workspace_id` chỉ dùng tài liệu trong workspace đó.

LightRAG/RAG‑Anything mặc định không có khái niệm workspace, nhưng có thể điều khiển ở 2 layer:

1. **Layer app (được ưu tiên)**:
   - Bảng `rag_documents` giữ mapping `workspace_id` ↔ `document_id` ↔ `rag_doc_id`.
   - Khi hỏi: mình chỉ hỏi chung toàn bộ knowledge base, nhưng citations trả về sẽ kèm `doc_id`, `file_path` → app có thể filter/validate rằng `rag_doc_id` thuộc workspace hiện tại.
   - Tuy nhiên, cách này không chặn retrieval cross‑workspace bên trong RAG.
2. **Layer RAG storage (nâng cao, Phase sau)**:
   - Dùng “namespace” hoặc tách storage path theo `workspace_id`, ví dụ:
     - `working_dir = f"{BASE_RAG_DIR}/workspace_{workspace_id}"`.
   - Khi init RAG cho một workspace, dùng directory khác nhau → mỗi workspace có LightRAG instance/storage riêng.

Trong Phase 3 v1, để đơn giản và an toàn:

- Strategy đề xuất: **tách working_dir theo workspace** (mỗi workspace 1 namespace riêng).
  - `workspace_rag_dir = os.path.join(settings.rag_base_dir, workspace_id)`.
  - `RagEngineService` có thể:
    - Hoặc tạo 1 RAGAnything instance/ cache per workspace (map workspace_id → instance).
    - Hoặc tạo on‑demand khi ingest/query lần đầu cho workspace, giữ trong memory map.

Pseudocode idea:

```python
class RagEngineService:
    def __init__(...):
        self._instances: dict[str, RAGAnything] = {}

    def _get_instance(self, workspace_id: str) -> RAGAnything:
        if workspace_id not in self._instances:
            working_dir = os.path.join(self.settings.rag_base_dir, workspace_id)
            self._instances[workspace_id] = RAGAnything(
                llm_model_func=self.llm_client.call_llm,
                embedding_func=self.embedding_client.embed_text,
                lightrag_kwargs={"working_dir": working_dir},
            )
        return self._instances[workspace_id]
```

Sau đó, `ingest_content`/`query`/`delete_document` đều gọi `_get_instance(workspace_id)` trước khi thao tác.

---

## 3. Chunker (`services/chunker.py`)

### 3.1. Vai trò

Chunker là cầu nối giữa Phase 2 (Document AI OCR) và RAG‑Anything:

- Đầu vào: `document_id` (PG), liên quan tới:
  - `documents.docai_full_text` (text từ OCR).
  - JSON raw của Document AI (từ `docai_raw_r2_key` trên R2) – optional cho v1.
  - `documents.title`, `files.original_filename` (để hiển thị nguồn).
- Đầu ra: `content_list` đúng schema RAG‑Anything để feed vào `insert_content_list`.

### 3.2. Interface

```python
class ChunkerService:
    def __init__(self, db_session_factory, storage_r2: StorageR2): ...

    async def build_content_list_from_document(self, document_id: str) -> list[dict]:
        """
        - Load document + workspace + file metadata từ DB.
        - Đọc docai_full_text (bắt buộc).
        - Optional: đọc JSON raw Document AI từ R2.
        - Chunk text thành các đoạn nhỏ + gán page_idx (ít nhất là 0 hoặc page thực).
        - Trả content_list phù hợp insert_content_list của RAG-Anything.
        """
```

### 3.3. Chiến lược chunk v1

V1 giữ đơn giản, dễ debug:

- Dùng `docai_full_text` như 1 chuỗi text lớn.
- Chunk theo độ dài ký tự hoặc token gần đúng:
  - Ví dụ: ~1000–2000 ký tự mỗi chunk, cắt theo newline/dấu câu khi có thể.
- Mỗi chunk tạo 1 item:

```python
{
    "type": "text",
    "text": "<chuỗi sau chunk>",
    "page_idx": 0  # hoặc page gần đúng nếu có thông tin
}
```

Về page_idx:

- V1 có thể:
  - a) Đặt `page_idx = 0` cho tất cả (citations chỉ hiển thị tên file, chưa chính xác trang).  
  - b) Hoặc nếu dễ: dùng JSON Document AI để map từng đoạn text về page, thành `page_idx` gần đúng.  
- Tech design đề xuất:
  - Ghi rõ rằng v1 **có thể dùng 0**, nhưng khung `ChunkerService` được thiết kế để sau này nâng cấp: đọc JSON raw, tách text theo pages/paragraphs để set page_idx chính xác.

### 3.4. Định danh file_path

Chunker (hoặc ingestion worker) cần build một `file_path` hiển thị nguồn cho RAG‑Anything:

- Mẫu đề xuất:

```text
file_path = f"{workspace_id}/{document_id}/{original_filename}"
```

- `file_path` này sẽ được truyền vào `rag.insert_content_list` để citations có thể hiển thị nguồn dạng “workspace/document/file gốc”.

---

## 4. Ingestion worker (`workers/ingest_worker.py`) & `services/jobs_ingest.py`

### 4.1. Trạng thái document & rag_documents

- Sau Phase 2:
  - `documents.status = 'parsed'` khi đã OCR xong.
- Phase 3 thêm:
  - Document “hoàn tất ingest vào RAG” → `documents.status = 'ingested'`.
  - Bảng `rag_documents` chứa mapping:
    - `document_id`
    - `workspace_id`
    - `rag_doc_id` (id trong RAG‑Anything/LightRAG).

### 4.2. Service ingest (`services/jobs_ingest.py`)

Tạo service chuyên xử lý ingest jobs (Phase 3):

```python
class IngestJobService:
    def __init__(
        self,
        db_session_factory,
        chunker: ChunkerService,
        rag_engine: RagEngineService,
    ): ...

    async def ingest_document(self, document_id: str) -> None: ...

    async def ingest_pending_documents(self, batch_size: int = 1) -> int: ...
```

Logic `ingest_document(document_id)`:

1. Load document + workspace + file metadata, đảm bảo:
   - `documents.status == 'parsed'`.
2. Gọi `chunker.build_content_list_from_document(document_id)` → `content_list`.
3. Xác định `file_path` như ở trên.
4. Chuẩn bị `doc_id` cho RAG:
   - Đề xuất: `doc_id = str(document_id)`.
5. Gọi `rag_engine.ingest_content(workspace_id, document_id, content_list, file_path, doc_id=doc_id)`.
6. Nhận `rag_doc_id` (v1 có thể = `doc_id`):
   - Insert vào `rag_documents`.
   - Cập nhật `documents.status = 'ingested'`.

Error handling:

- Nếu ingest lỗi:
  - Log chi tiết.
  - Có thể set `documents.status = 'parsed'` + giữ lỗi ở log, hoặc thêm trạng thái riêng `ingest_failed` (nếu schema cho phép).
  - Cho phép retry ingest sau bằng cách gọi lại `ingest_document` (document còn `status='parsed'`).

`ingest_pending_documents(batch_size)`:

- Tìm `documents` với:
  - `status='parsed'`,
  - chưa có record `rag_documents` tương ứng.
- Lấy tối đa `batch_size` document_id, lần lượt gọi `ingest_document`.

### 4.3. Worker (`workers/ingest_worker.py`)

Pattern tương tự `parse_worker`:

```python
async def run_ingest_worker_loop():
    settings = get_settings()
    service = IngestJobService(...)

    while True:
        processed = await service.ingest_pending_documents(batch_size=1)
        if processed == 0:
            await asyncio.sleep(INGEST_IDLE_SLEEP)
        else:
            await asyncio.sleep(INGEST_BUSY_SLEEP)

if __name__ == "__main__":
    asyncio.run(run_ingest_worker_loop())
```

Worker này có thể chạy song song với `parse_worker`.  
Trật tự pipeline: upload → parse_worker → ingest_worker → chat.

---

## 5. Chat API (`api/routes/messages.py`) – tích hợp RAG Engine

### 5.1. Behavior v1

`POST /conversations/{conversation_id}/messages`:

1. Auth & load conversation:
   - Verify user (Supabase JWT).
   - Load conversation bằng `conversation_id`, đảm bảo thuộc cùng user.
   - Lấy `workspace_id` từ conversation.
2. Lưu message `role='user'`:
   - Insert row vào `messages` (`role='user'`, `content`, `metadata={}`).
3. Chuẩn bị query cho RAG Engine:
   - V1: chỉ dùng **câu hỏi hiện tại**, không ghép history (giữ đơn giản, ít phức tạp prompt).  
   - Phase sau có thể:
     - Lấy vài message gần nhất, build `extra_context` để truyền vào system_prompt hoặc prefix.
4. Gọi `rag_engine.query(workspace_id, question, system_prompt=..., mode="mix")`:
   - `system_prompt` chứa persona:
     - Ngôn ngữ: ưu tiên trả lời bằng **ngôn ngữ của câu hỏi** (tiếng Việt/Anh), có thể mô tả rõ trong prompt.
     - Tone: “mình/bạn”, rõ ràng, nghiêm túc, ưu tiên chính xác; khi không chắc nên nói rõ mức độ chắc chắn.
     - Knowledge: ưu tiên căn cứ trên tài liệu trong workspace, nhưng được phép dùng kiến thức chung để giải thích/thêm context.
5. Nhận `{answer, citations}` từ `RagEngineService`:
   - `answer`: nội dung trả lời (string).
   - `citations`: list đơn giản, ví dụ:

```json
[
  {
    "file_path": "workspace123/doc456/hop_dong_2025.pdf",
    "page_idx": 4
  }
]
```

6. Lưu message `role='ai'`:
   - Insert vào `messages` với:
     - `content = answer`.
     - `metadata = {"citations": citations}`.
7. Trả response cho client:
   - Message `ai` (content + metadata).
   - Option: trả luôn message `user` + `ai` trong 1 payload tiện cho UI.

### 5.2. System prompt & persona

Tech design đề xuất pattern system prompt (pseudo):

- “Bạn là trợ lý AI trả lời theo ngôn ngữ của câu hỏi (tiếng Việt/Anh). Xưng ‘mình’/‘bạn’ khi trả lời tiếng Việt.  
  Bạn ưu tiên sử dụng thông tin từ tài liệu trong workspace hiện tại để trả lời. Khi câu hỏi vượt ngoài phạm vi tài liệu, bạn có thể dùng kiến thức chung, nhưng hãy nói rõ nếu bạn không chắc chắn hoặc tài liệu không bao phủ đầy đủ.”

Chi tiết prompt sẽ được lưu ở:

- `core/constants.py` hoặc trong `RagEngineService` dưới dạng constant, để dễ điều chỉnh sau mà không phải sửa nhiều nơi.

---

## 6. Xoá / refresh document trong RAG

### 6.1. Khi xoá document ở DB

- Khi user xoá document trong workspace (endpoint Phase 1/2/3):
  - Backend cần:
    - Xoá/đánh dấu `documents` ở DB (vd `status='deleted'` hoặc soft delete).
    - Lấy `rag_doc_id` tương ứng từ `rag_documents` (nếu có).
    - Gọi `rag_engine.delete_document(workspace_id, rag_doc_id)` để xoá khỏi RAG storage.
    - Xoá record trong `rag_documents`.

Vì RAG‑Anything/LightRAG hiện không có API delete chuẩn trong spec, Phase 3 tech design có thể:

- a) Định nghĩa `delete_document` là no‑op v1 (chỉ xoá mapping ở DB), chấp nhận vector/graph còn trong storage, và xử lý triệt để ở Phase sau.  
- b) Hoặc tận dụng API của LightRAG nếu có để xoá chunks/doc tương ứng, khi implement.

### 6.2. Refresh (ingest lại) document

- Nếu document được re‑parse (Document AI chạy lại, text thay đổi):
  - Có 2 lựa chọn:
    - a) Tạo `documents` mới (id mới) → ingest như tài liệu mới, mapping riêng trong `rag_documents`.  
    - b) Dùng cùng `document_id`, nhưng:
      - Re‑run parse (Phase 2), docai_full_text bị overwrite.
      - Re‑ingest (Phase 3) bằng cách:
        - (Nếu có delete_document thực sự) xoá doc cũ khỏi RAG.
        - Gọi lại `ingest_document(document_id)` để tạo doc mới trong RAG.

Spec tổng đã thiên về mô hình **“version bằng workspace mới / document mới”** (ít sửa in‑place) nên Phase 3 tech design ưu tiên hướng a) cho v1, để pipeline đơn giản và dễ reason.

---

## 7. Kết nối với planning & độ sẵn sàng

Thiết kế Phase 3 này:

- Bám sát `rag-engine-phase-3.md`: có ingestion pipeline tách khỏi parse, sử dụng `content_list` + `insert_content_list`, và chat với citations.
- Phù hợp với kiến trúc `architecture-overview.md`:
  - `services/rag_engine.py`, `services/chunker.py`, `services/jobs_ingest.py` rõ vai trò.
  - `workers/ingest_worker.py` song song với `parse_worker.py`.
  - API layer không phụ thuộc trực tiếp vào RAG‑Anything, chỉ gọi service.
- Không khoá cứng vào một vector DB duy nhất: dùng LightRAG backend thông qua `working_dir`, có thể file/SQLite/kv; nếu sau này cần tích hợp cụ thể hơn (như Postgres hoặc vector DB riêng) có thể mở rộng bằng cách chỉnh `lightrag_kwargs`.

Sau Phase 3 tech design, ta đã có:

- Spec đầy đủ cho pipeline upload → parse (Phase 2) → ingest (Phase 3) → chat.  
- Các module, hàm, interface rõ ràng để khi bắt đầu implement server thực tế, agent/dev có thể bám theo mà không phải “tự đoán” cách dùng RAG‑Anything.
