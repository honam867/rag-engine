# rag-engine – Phase 9 Requirements (LightRAG Refactor, Disable Citations)

## 1. Mục tiêu & Phạm vi (Goals & Scope)

- **Mục tiêu chính**
  - Refactor backend để:
    - Sử dụng **LightRAG trực tiếp** làm hạ tầng ingest + retrieval (vector + graph).
    - **Loại bỏ phụ thuộc runtime vào RAG-Anything** trong pipeline chat (query / answer).
  - Đưa hệ thống về trạng thái **ổn định, dễ debug**, tập trung vào chất lượng câu trả lời:
    - Tạm **tắt hoàn toàn tính năng trích xuất nguồn/citation** trong API chat.
    - Đảm bảo kết quả trả lời không bị suy giảm do các lớp mapping nguồn phức tạp hiện tại.
  - Chuẩn bị nền tảng sạch cho Phase 9.1:
    - LightRAG trở thành **single source of truth** cho retrieval.
    - Việc thiết kế lại citation sẽ dựa trên output chuẩn của LightRAG (không parse “prompt thô” nữa).

- **Phạm vi công việc**
  - Backend / server:
    - Thay đổi `RagEngineService` để:
      - Khởi tạo và cấu hình `LightRAG` trực tiếp (PGVector trên Supabase).
      - Ingest nội dung từ DocAI → LightRAG mà không đi qua `RAGAnything`.
      - Cung cấp API nội bộ đơn giản để:
        - Ingest tài liệu.
        - Thực hiện query LLM (nếu còn dùng LLM của LightRAG) hoặc retrieval-only (cho AnswerEngine).
    - Điều chỉnh `AnswerEngineService` & API chat:
      - Bỏ toàn bộ logic mapping citations hiện có (segment_id, segment_index, source_ids…).
      - Trả về **chỉ text câu trả lời** (và usage nếu cần), không còn `sections`/`citations` cho client.
  - Config & deployment:
    - Cập nhật config để bật/tắt LightRAG trực tiếp, không phụ thuộc `.env` của RAG-Anything.

- **Ngoài phạm vi (Out of scope) cho Phase 9**
  - Không thiết kế lại format citation mới (để dành cho Phase 9.1).
  - Không thay đổi kiến trúc tổng thể trong `docs/design/architecture-overview.md`.
  - Không thay đổi schema DB Supabase hiện có (workspaces, documents, conversations, messages…).
  - Không buộc migrate dữ liệu RAG cũ; behavior với workspace/doc đã ingest trước đó được chấp nhận “best effort”.

- **Kết quả kỳ vọng (Deliverables)**
  - Tài liệu:
    - `docs/design/phase-9-design.md` mô tả chi tiết refactor LightRAG.
  - Code (sau khi implement Phase 9):
    - `RagEngineService` dùng LightRAG thuần; không còn import `raganything`.
    - `AnswerEngineService`/API chat trả về message AI **không có citations**.
  - Hệ thống chạy ổn định được trên dữ liệu thực tế, dù chưa có explainable RAG.

---

## 2. Các khái niệm & thực thể chính (Key Concepts & Entities)

### 2.1. LightRAG Core

- **Mô tả**
  - Thư viện core RAG (`LightRAG/lightrag`) chịu trách nhiệm:
    - Lưu trữ vector + graph (PGVector, graph storage, KV storage).
    - Ingest tài liệu (`ainsert`, `ainsert_custom_chunks`).
    - Truy vấn (`aquery_llm`, `aquery_data`) và trả về dữ liệu cấu trúc.
- **Vai trò trong hệ thống**
  - Trở thành engine duy nhất phía server cho:
    - Ingest text (từ DocAI).
    - Retrieval context cho RAG.
  - RAG-Anything chỉ còn là “vendor code” trong repo, **không dùng trong runtime**.

### 2.2. Answer Engine (Phase 9)

- **Mô tả**
  - Service chịu trách nhiệm xử lý câu hỏi chat từ client:
    - Gọi LightRAG để retrieve / generate answer.
    - Trả về câu trả lời text cho API.
- **Vai trò**
  - Trong Phase 9:
    - Giữ luồng chat hoạt động, nhưng **không build citations**.
    - Là điểm nối duy nhất giữa API và LightRAG.
  - Chuẩn bị để Phase 9.1 có thể plug-in cơ chế citation mới dựa trên output của LightRAG.

### 2.3. Legacy Citation Metadata (Phase 7/8)

- **Mô tả**
  - Các field trong `messages.metadata` hiện dùng cho explainable RAG:
    - `sections`, `citations`, `retrieved_segments`, `segment_id`, `segment_index`, `source_ids`, v.v.
- **Vai trò trong Phase 9**
  - **Không còn được ghi/gửi** cho message mới.
  - Các message cũ vẫn giữ metadata cũ trong DB, nhưng client nên:
    - Hoặc ignore,
    - Hoặc chỉ đọc khi biết message thuộc Phase 7/8.

---

## 3. Luồng nghiệp vụ (User/System Flows)

### 3.1. Ingest tài liệu (DocAI → LightRAG)

1. User upload file như hiện tại (Phase 2/3).
2. Worker parse bằng Document AI, lưu:
   - `documents.docai_full_text`
   - `documents.docai_raw_r2_key` (JSON gốc)
   - `documents.status = 'parsed'`.
3. Service ingest (Phase 3 đã có) được refactor:
   - Lấy **full text** và/hoặc `content_list` được build từ DocAI (giữ logic hiện có).
   - Gọi trực tiếp `LightRAG.ainsert(...)` hoặc `ainsert_custom_chunks(...)`:
     - Workspace = `workspace_id`.
     - doc_id = `document_id` (đảm bảo mapping 1-1).
4. LightRAG tạo vector + graph trong các bảng `LIGHTRAG_*` (PGVector) tự động.
5. Không có metadata citation nào được xây dựng trong bước ingest (để dành Phase 9.1).

### 3.2. Chat & Query RAG (không citation)

1. Client gửi câu hỏi mới:
   - `POST /api/conversations/{conversation_id}/messages`.
2. API layer:
   - Tạo bản ghi message user như cũ.
   - Gọi `AnswerEngineService.answer_question(...)`.
3. `AnswerEngineService`:
   - Lấy workspace + history tương ứng.
   - Gọi LightRAG:
     - Option A (dễ nhất Phase 9):
       - Dùng `lightrag.aquery_llm(...)` với `QueryParam` phù hợp, để LightRAG tự gọi LLM và trả về answer string (`llm_response.content`).
     - Option B (nếu đã có Answer LLM riêng):
       - Dùng `lightrag.aquery_data(...)` để lấy context JSON.
       - Gọi LLM riêng với context đó, nhưng **vẫn chưa build citations** (chỉ lấy answer).
   - Nhận `answer_text` + optional `llm_usage`.
4. API tạo message AI:
   - `content = answer_text`.
   - `metadata`:
     - Có thể chứa `{"llm_usage": {...}}` nhưng **không chứa `sections` hay `citations`**.
5. Client hiển thị:
   - Chỉ text câu trả lời (không bong bóng nguồn).

### 3.3. Behavior với message/citation cũ

1. Các message đã tạo ở Phase 7/8 trong DB vẫn giữ metadata cũ.
2. Trong Phase 9:
   - API không xoá hay migrate metadata cũ.
   - Client:
     - Có thể tạm thời **không render** citation cho message cũ để tránh UX không nhất quán.
     - Hoặc render nhưng đánh dấu “legacy”.
3. (Chi tiết behavior UI sẽ được chốt trong client-design Phase 9, nếu cần).

---

## 4. Kiến trúc & Thiết kế kỹ thuật (Architecture & Technical Design – Overview)

> Chi tiết implementation sẽ ở `docs/design/phase-9-design.md`.  
> Đây là overview để chốt phạm vi Phase 9.

### 4.1. Backend / Service Layer

- **RagEngineService (v2 – LightRAG-only)**
  - Trách nhiệm:
    - Quản lý lifecycle của `LightRAG` theo từng `workspace_id`.
    - Cung cấp hàm:
      - `ingest_content(workspace_id, document_id, content_list, ...)`.
      - `query_llm(workspace_id, question, query_param, system_prompt) -> answer_text`.
      - (Option) `retrieve_data(workspace_id, question, query_param) -> dict` dùng cho Phase 9.1.
  - Không còn import/tạo `RAGAnything`.

- **AnswerEngineService (v2 – no citation)**
  - Trách nhiệm:
    - Nhận question + history + workspace.
    - Gọi RagEngineService (LightRAG hoặc combination LightRAG + LLM riêng).
    - Trả về answer_text + optional usage.
  - Không còn bất kỳ logic:
    - parse prompt LightRAG,
    - map segment_id → document_id/segment_index,
    - build `sections`/`citations`.

### 4.2. Database Schema (Supabase / Postgres)

- **Không thay đổi** bảng:
  - `documents`, `rag_documents`, `conversations`, `messages`, …
- **Bảng LightRAG** (`LIGHTRAG_*`):
  - Được tạo và quản lý bởi LightRAG (PGVector).
  - Phase 9 không sửa schema, chỉ cấu hình kết nối qua env `POSTGRES_*`.

---

## 5. API Endpoints (Dự kiến)

### 5.1. Chat API (server/app/api/routes/messages.py)

- `POST /api/conversations/{conversation_id}/messages`
  - **Không đổi** shape request body.
  - Response:
    - Field `content` của message AI: vẫn là string như hiện tại.
    - Field `metadata` của message AI:
      - Không còn `sections`/`citations` cho message mới.
      - Có thể có:
        - `llm_usage` (model, prompt_tokens, completion_tokens, total_tokens).

### 5.2. Document ingest / raw-text APIs

- `POST /api/workspaces/{workspace_id}/documents/...` (upload, ingest)
  - Luồng business giữ nguyên, chỉ thay implementation bên trong để sử dụng LightRAG.
- `GET /api/workspaces/{workspace_id}/documents/{document_id}/raw-text`
  - Giữ nguyên: vẫn phục vụ viewer Phase 7.
  - Không phụ thuộc vào citation Phase 9.1.

---

## 6. Kế hoạch triển khai (Implementation Plan)

1. **Bước 1 – Thiết kế chi tiết**
   - Viết `docs/design/phase-9-design.md`:
     - Cấu trúc mới của `RagEngineService` (LightRAG-only).
     - Cập nhật `AnswerEngineService` và cách gọi query.
2. **Bước 2 – Refactor RagEngineService**
   - Loại bỏ import/khởi tạo `RAGAnything`.
   - Khởi tạo LightRAG trực tiếp, cấu hình từ env / settings.
3. **Bước 3 – Cập nhật AnswerEngineService & messages API**
   - Dùng interface mới của RagEngineService.
   - Xoá/tắt phần build citations, chỉ lưu answer + usage.
4. **Bước 4 – Dọn dẹp & kiểm thử**
   - Chạy lại luồng upload → ingest → chat trên workspace mới.
   - Đảm bảo không còn lỗi liên quan đến citation cũ.

---

## 7. Ghi chú & Giả định (Notes & Assumptions)

- LightRAG được cấu hình chạy với:
  - Storage PGVector trên Supabase (env `POSTGRES_*` đã được derive từ `SUPABASE_DB_URL` như các phase trước).
  - Embedding & LLM model tương thích với hiện tại (OpenAI / compatible).
- Trong Phase 9:
  - Chấp nhận rằng answer **chưa explainable** (không có nguồn trích dẫn).
  - Độ chính xác của câu trả lời phụ thuộc chủ yếu vào:
    - Chất lượng parse DocAI,
    - Cách chunk/ingest hiện có,
    - Tham số retrieval của LightRAG.
- Citation v2 (luôn có nguồn, chính xác hơn) sẽ được đặc tả riêng trong:
  - `docs/requirements/requirements-phase-9.1.md`
  - `docs/design/phase-9.1-design.md`.

