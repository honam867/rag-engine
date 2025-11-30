# rag-engine-phase-3 – RAG Engine Integration (RAG‑Anything)

## 1. Mục tiêu Phase 3

- Kết nối dữ liệu đã OCR ở Phase 2 với **RAG Engine** để tạo ra luồng:
  - `document (parsed) → content_list → RAG Engine → chat trả lời có citations`.
- Chọn **RAG‑Anything** làm implementation v1 của RAG Engine interface đã mô tả trong `rag-engine-v1.md`.
- Hoàn thiện API chat để:
  - Người dùng chọn workspace.
  - Hệ thống trả lời dựa trên kiến thức trong workspace đó (RAG‑based), lưu lại messages với role `user` / `ai`.

Phase 3 tập trung vào luồng RAG, không đi sâu vào tối ưu (caching, rerank, tools) – các phần đó để Phase 4.

---

## 2. RAG Engine v1: RAG‑Anything

### 2.1. Vị trí trong hệ thống

- RAG‑Anything được sử dụng như **một thư viện** bên trong backend FastAPI:
  - Tạo một module `rag_engine` cài đặt interface:
    - `ingest_content(workspace_id, document_id, content_list) -> rag_doc_id`
    - `query(workspace_id, question, extra_context) -> { answer, citations }`
    - `delete_document(rag_doc_id)`
- RAG‑Anything/LightRAG sẽ quản lý:
  - Embeddings.
  - Vector store + knowledge graph.
  - Logic retrieval + LLM để tạo câu trả lời.

### 2.2. Cấu hình (ở mức khái niệm)

- Cần cấu hình:
  - **Embedding model**: ví dụ OpenAI, local model hoặc model khác (chi tiết chọn model nằm ở tech design, Phase 3 chỉ yêu cầu “có model hoạt động được”).
  - **LLM model**: phục vụ bước answer generation trong RAG‑Anything.
  - **Storage nội bộ cho RAG‑Anything**:
    - LightRAG sẽ dùng một backend (file/SQLite/vector DB, …) – loại backend cụ thể được quyết ở tech design.
  - Cách “namespacing” theo workspace:
    - Yêu cầu logic: khi query theo `workspace_id`, chỉ lấy context từ tài liệu thuộc workspace đó.
    - Cách thực hiện (một LightRAG instance hay nhiều instance, metadata filter, …) sẽ được quyết ở tầng tech design dựa trên khả năng của LightRAG.

---

## 3. Ingestion từ documents đã OCR vào RAG

### 3.1. Trạng thái tài liệu

- Sau Phase 2, mỗi document đi qua các trạng thái:
  - `pending` (mới tạo).
  - `parsed` (đã OCR xong, có `docai_full_text`).
  - (Phase 3) `ingested` (đã đẩy vào RAG Engine).

### 3.2. Chiến lược ingestion

- Phase 3 thêm một bước ingestion riêng (tách khỏi parse):
  - Worker hoặc task định kỳ sẽ tìm các document:
    - `status = 'parsed'` và chưa có bản ghi trong `rag_documents`.
  - Với mỗi document:
    1. Gọi **chunker**:
       - `build_content_list_from_document(document_id)` – dùng `docai_full_text` (và nếu cần JSON raw) để tạo `content_list` theo schema RAG‑Anything.
    2. Gọi **RAG Engine**:
       - `ingest_content(workspace_id, document_id, content_list)`.
       - Nhận lại `rag_doc_id` (id nội bộ của RAG‑Anything).
    3. Cập nhật DB:
       - Tạo record trong `rag_documents` (document_id, rag_doc_id).
       - `documents.status = 'ingested'`.

### 3.3. Chunking (ở mức khái niệm)

- Phase 3 cần định nghĩa nguyên tắc chunk text:
  - Dựa trên `docai_full_text`:
    - Cắt theo **độ dài** (vd N ký tự/tokens) hoặc
    - Cắt theo **các dấu phân tách** (dòng trống, heading, số điều khoản) – chi tiết có thể refine dần.
  - Kết quả:
    - `content_list`: mảng các item `{ type: "text", page_idx: ?, content: "...", ... }`.
- Mục tiêu Phase 3:
  - Có một chiến lược chunking **đơn giản nhưng hợp lý**, sau có thể nâng cấp (vẫn giữ interface chunker không đổi).

---

## 4. Luồng query/chat sử dụng RAG Engine

### 4.1. Chat endpoint sau Phase 3

- `POST /conversations/{conversation_id}/messages`
  - Input: `{ content }` (câu hỏi của user).
  - Hành vi mới ở Phase 3:
    1. Lưu message `role='user'` như Phase 1.
    2. Backend gọi RAG Engine:
       - Chuẩn bị `question`:
         - v1: dùng **chỉ câu hỏi hiện tại** (`content`) để đơn giản hóa logic.
         - (Optional sau này): có thể nối thêm một vài message gần nhất để tạo short history trước khi gửi vào RAG.
       - Xác định `workspace_id` của conversation.
       - Gọi `rag_engine.query(workspace_id, question, extra_context_from_history)`.
    3. Nhận `{ answer, citations }` từ RAG Engine.
       - Trong đó:
         - `answer`: text đã được LLM trả lời.
         - `citations`: v1 có thể chỉ là thông tin ở dạng text/metadata tối thiểu, không bắt buộc phải là cấu trúc phức tạp.
    4. Lưu message `role='ai'`, `content=answer`, `metadata.citations=citations`.
    5. Trả response cho client.

### 4.2. Phạm vi retrieval (workspace)

- Khi query, RAG Engine phải chỉ dùng tài liệu trong **workspace tương ứng**:
  - Trong lúc ingest, mỗi document được tag với `workspace_id`.
  - Lúc retrieve, RAG‑Anything được yêu cầu chỉ lấy context có `workspace_id` tương ứng.
- Điều này đảm bảo:
  - Workspace độc lập về kiến thức.
  - User chọn workspace nào sẽ chỉ “thấy” kiến thức của workspace đó.

### 4.3. Citations

- RAG Engine nên trả kèm thông tin citation để backend lưu vào `metadata`:
  - Ít nhất ở v1:
    - Thông tin đủ để hiển thị nguồn ở mức:
      - Tên file / mô tả tài liệu (title).
      - Có thể thêm `document_id`, `page_idx` nếu khả thi (tùy vào metadata LightRAG cung cấp, chi tiết ở tech design).
  - Điều này cho phép UI hiển thị:
    - “Câu trả lời này dựa trên Luật 2020 – file X – trang 5”.

Việc RAG trả về **citations dạng đầy đủ, có cấu trúc** là mục tiêu nâng cấp sau (có thể yêu cầu thêm tech design hoặc custom prompt để LLM tự chèn nguồn vào câu trả lời).

---

## 5. Quản lý vòng đời tài liệu trong RAG

### 5.1. Xoá / refresh document

- Khi user muốn xoá hoặc cập nhật tài liệu trong workspace:
  - Backend:
    - Xoá/đánh dấu document ở DB.
    - Dùng `rag_documents.rag_doc_id` để gọi `rag_engine.delete_document(rag_doc_id)`.
  - Option:
    - Có thể đánh dấu `documents.status = 'deleted'` thay vì xoá hẳn, để giữ log.

### 5.2. Re‑ingest (khi document thay đổi)

- Nếu file được thay bằng phiên bản mới (cùng document hoặc document mới):
  - Pipeline:
    - OCR lại ở Phase 2 → `docai_full_text` mới → status `parsed`.
    - Phase 3 ingest lại → `rag_doc_id` mới (record mới trong `rag_documents`).
  - Có thể xoá `rag_doc_id` cũ nếu không còn dùng.

---

## 6. API & quan sát trạng thái (overview)

- Bổ sung/hoàn thiện các API để quan sát pipeline:
  - List documents trong workspace kèm `status` (`pending`, `parsed`, `ingested`, `error`).
  - Chi tiết document: cho biết `parse_jobs` gần nhất và có `rag_documents` hay chưa.
  - (Optional) endpoint để trigger ingest thủ công cho một document/workspace (ví dụ dùng khi dev/test).

---

## 7. Kết quả sau Phase 3

Sau Phase 3, hệ thống đạt được:

- Dòng chảy dữ liệu hoàn chỉnh:
  - Upload file → parse_jobs (Phase 1–2) → Document AI OCR + lưu kết quả (Phase 2) → ingest vào RAG‑Anything (Phase 3) → chat trả lời dùng RAG.
- Người dùng có thể:
  - Tạo workspace riêng.
  - Upload tài liệu vào workspace đó.
  - Chờ pipeline parse + ingest chạy.
  - Chat trong workspace và nhận câu trả lời dựa trên kiến thức đã feed, với:
    - Persona mặc định (trợ lý nghiêm túc, tiếng Việt, xưng “mình/bạn”, có thể dùng thêm kiến thức chung khi cần).
    - Câu trả lời ưu tiên dựa trên tài liệu nhưng vẫn cho phép giải thích linh hoạt (không hoàn toàn bị khóa cứng vào text).
    - Khi thiếu thông tin, trợ lý vẫn cố gắng suy luận và nêu rõ mức độ chắc chắn nếu phù hợp (được điều chỉnh bằng system prompt ở tech design).

Phase 3 hoàn tất phần **“core knowledge engine cho từng workspace”**.  
Phase 4 sẽ tập trung vào tối ưu (caching, reranking, tools, realtime, monitoring,…).
