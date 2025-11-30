# rag-engine-v1 – Multi‑Domain Knowledge Engine Spec v1

## 1. Mục tiêu & triết lý thiết kế

- Xây dựng một **knowledge engine đa domain**, có thể dùng cho:
  - Luật, lịch sử, y tế, phân tích tài chính, tài liệu kỹ thuật, v.v.
  - Đặc biệt phù hợp cho **kiến thức cần độ chính xác cao** và **ít thay đổi** (hoặc thay đổi theo “version” rõ ràng).
- Người dùng có thể:
  - Tạo nhiều **workspace** tương ứng với từng “snapshot kiến thức” (domain + version do user tự đặt tên).
  - Feed tài liệu (batch hoặc upload tay) vào từng workspace, sau đó dùng RAG để truy vấn.
- Thiết kế để **tái sử dụng**:
  - Backend Python + Supabase + Cloudflare R2 là khung cố định.
  - **RAG Engine** là một lớp trừu tượng: hiện tại dùng RAG‑Anything, nhưng có thể thay bằng engine khác (LlamaIndex, LangChain RAG, custom, …) mà không phải đổi kiến trúc tổng thể.

---

## 2. Các khái niệm chính

### 2.1. User

- Tài khoản người dùng, được quản lý bởi **Supabase Auth** (`auth.users`).
- Hiện tại hệ thống dự kiến chỉ có 1 user chính (mình), nhưng kiến trúc vẫn hỗ trợ nhiều user để dễ tái sử dụng.

### 2.2. Workspace

- Đơn vị kiến thức chính trong hệ thống.
- Mỗi workspace tương ứng với **một domain + một version** do user tự đặt tên, ví dụ:
  - `Luật VN - 2020`
  - `Luật VN - 2021`
  - `Luật VN - 2020-v2`
  - `Chính sách Công ty A - V1`
  - `Chính sách Công ty A - V2`
- Không có bảng `domain_versions`: version được encode trực tiếp trong tên workspace.

### 2.3. Document

- Một tài liệu logic thuộc về một workspace:
  - Ví dụ: một file PDF luật, một tài liệu nội bộ, một hướng dẫn, một file training, …
- Một document có thể:
  - Gắn với một file vật lý trên Cloudflare R2.
  - Tương ứng với một hoặc nhiều chunk trong RAG Engine (thông qua `content_list`).
  - Lưu thêm:
    - `docai_full_text`: full text sau khi được OCR bởi Document AI.
    - `docai_raw_r2_key`: key trên R2 trỏ tới JSON raw response từ Document AI (optional).

### 2.4. File

- File vật lý (PDF, DOCX, PPTX, hình ảnh, …) được lưu trên **Cloudflare R2**.
- Database chỉ lưu metadata:
  - `r2_key`, `original_filename`, `mime_type`, `size_bytes`, `checksum`, …

### 2.5. Parse Job

- Nhiệm vụ xử lý một document để biến nó thành kiến thức trong RAG:
  - Tải file từ R2.
  - Gọi Google Cloud Document AI để parse (OCR + layout).
  - Map kết quả sang `content_list` (schema ingestion của RAG Engine).
  - Gọi RAG Engine để ingest (`insert_content_list` hoặc API tương đương).
- Mỗi job có trạng thái:
  - `queued`, `running`, `success`, `failed`.

### 2.6. RAG Document

- Mapping giữa `documents` trong DB và document tương ứng trong RAG Engine.
- Lưu `rag_doc_id` (id nội bộ của engine, ví dụ LightRAG/RAG‑Anything).
- Dùng để:
  - Xoá document khỏi RAG Engine khi cần.
  - Refresh / re‑ingest khi document thay đổi.

### 2.7. Conversation & Message

- **Conversation**:
  - Một phiên chat (session) giữa user và AI trong context **một workspace cụ thể**.
- **Message**:
  - Một tin nhắn trong conversation, gồm:
    - `role`:
      - `'user'`: tin nhắn từ người dùng.
      - `'ai'`: tin nhắn trả lời từ AI (dựa trên RAG + LLM).
    - `content`: nội dung text.
    - `metadata`: JSON (citations, token usage, …).

---

## 3. Luồng sử dụng chính (view từ user)

### 3.1. Auth cơ bản

- Dùng **Supabase Auth** cho đăng ký / đăng nhập / đổi mật khẩu (email + password).
- Backend FastAPI xác thực request bằng JWT của Supabase:
  - Đọc token từ header `Authorization: Bearer <token>`.
  - Verify, trích `user_id` (uid) để gán vào dữ liệu (`workspaces`, `conversations`, …).

### 3.2. Tạo workspace (domain + version)

- Từ dashboard:
  - Tạo workspace mới với:
    - `name`: ví dụ `Luật VN - 2020`, `Chính sách Công ty A - V1`.
    - `description`: mô tả ngắn về workspace.
- Mỗi workspace là một **knowledge space độc lập**:
  - RAG Engine sẽ được query theo workspace tương ứng.

### 3.3. Feed dữ liệu cho workspace

Hiện tại tập trung vào **upload tay**:

- Từ UI hoặc một endpoint đơn giản:
  - Chọn workspace → upload 1 hoặc nhiều file.

Backend:

- Upload file lên Cloudflare R2.
- Tạo `document` + `file` trong DB.
- Tạo `parse_job` cho từng document.

### 3.4. Ingestion pipeline (tự động)

Với mỗi `parse_job`:

1. Worker/backend:
   - Lấy thông tin `file` (từ DB).
   - Download file từ Cloudflare R2.
2. Gọi **Google Cloud Document AI**:
   - Hiện tại dùng **Enterprise Document OCR** (chỉ OCR).
   - Sau này có thể bổ sung Layout Parser nếu cần hiểu layout sâu hơn.
   - Nhận về `Document` (text, pages, paragraphs, tables, …).
3. Map `Document` → `content_list`:
   - Mỗi đoạn text / paragraph / table → item:
     - `type` (`text`, `table`, …),
     - `page_idx`,
     - `content`,
     - metadata (optional).
4. Gọi **RAG Engine**:
   - `ingest_content(workspace_id, document_id, content_list) -> rag_doc_id`
5. Cập nhật DB:
   - `parse_jobs.status = success`.
   - `documents.status = ingested`.
   - Insert record vào `rag_documents` (mapping document ↔ rag_doc_id).

### 3.5. Chat / Query kiến thức

1. User chọn workspace (vd: `Luật VN - 2020-v2`).
2. Tạo conversation mới hoặc mở lại conversation cũ.
3. Gửi câu hỏi (message:
   - `role='user'`,
   - `content='...'`).
4. Backend:
   - Lấy lịch sử message gần đây (short‑term context) nếu cần.
   - Gọi **RAG Engine**:
     - `query(workspace_id, question, extra_context_from_history)`.
   - Nhận `answer` + `citations`.
   - Lưu message `role='ai'` vào DB.
5. Trả về cho client:
   - Nội dung trả lời.
   - Thông tin citation (link tới document/file, page).

---

## 4. Kiến trúc hệ thống

### 4.1. Backend API (Python)

- Sử dụng Python **FastAPI** làm backend chính:
  - **Auth**:
    - Không tự triển khai auth, tận dụng **Supabase Auth**.
    - (Optional) Có thể có endpoint `/me` để trả thông tin user từ JWT.
  - **Workspaces**:
    - Tạo / list / xem chi tiết / (xoá) workspace.
  - **Documents & Files**:
    - Upload file vào workspace (single/batch).
    - List documents trong workspace.
  - **Ingestion / Jobs**:
    - Quản lý `parse_jobs`, worker xử lý jobs.
  - **Conversations & Messages**:
    - CRUD conversation.
    - Gửi/nhận message trong conversation, gắn với workspace.
    - Endpoint chat gọi RAG Engine.

### 4.2. Database Schema (Supabase / Postgres)

Các bảng chính (v1) trong `public` schema, dùng `auth.users` làm nguồn user:

- `workspaces`
  - `id` (PK)
  - `user_id` → FK `auth.users.id`
  - `name` (vd: `Luật VN - 2020`)
  - `description`
  - `created_at`, `updated_at`

- `documents`
  - `id` (PK)
  - `workspace_id` → FK `workspaces.id`
  - `title` (tên hiển thị, thường = tên file hoặc định danh)
  - `source_type` (`upload`, `batch_cli`, `api`, …)
  - `status` (`pending`, `parsed`, `ingested`, `error`)
  - `docai_full_text` (TEXT, nullable) – full text từ Document AI OCR
  - `docai_raw_r2_key` (TEXT, nullable) – key JSON raw Document AI trên R2
  - `created_at`, `updated_at`

- `files`
  - `id` (PK)
  - `document_id` → FK `documents.id`
  - `r2_key` (key/path trên Cloudflare R2)
  - `original_filename`
  - `mime_type`
  - `size_bytes`
  - `checksum` (md5/sha256, dùng để cache parse)
  - `created_at`

- `parse_jobs`
  - `id` (PK)
  - `document_id` → FK `documents.id`
  - `status` (`queued`, `running`, `success`, `failed`)
  - `parser_type` (vd: `gcp_docai`)
  - `error_message` (nullable)
  - `started_at`, `finished_at`

- `rag_documents`
  - `id` (PK)
  - `document_id` → FK `documents.id`
  - `rag_doc_id` (string – id trong RAG Engine, ví dụ LightRAG)
  - `created_at`

- `conversations`
  - `id` (PK)
  - `workspace_id` → FK `workspaces.id`
  - `user_id` → FK `auth.users.id`
  - `title`
  - `created_at`, `updated_at`

- `messages`
  - `id` (PK)
  - `conversation_id` → FK `conversations.id`
  - `role` (`user`, `ai`)
  - `content` (text)
  - `metadata` (JSON, lưu citation, token usage, …)
  - `created_at`

Schema này là **khung tái sử dụng**:

- Có thể dùng với bất kỳ RAG Engine nào, miễn là có thể map document ↔ rag_doc_id.
- Có thể dùng lại cho project khác không phụ thuộc RAG‑Anything (chỉ cần thay implementation engine).

### 4.3. Storage layer – Cloudflare R2

- Tất cả thao tác với Cloudflare R2 được gom vào một lớp riêng (storage layer), ví dụ:
  - `upload_file(bytes, key)`
  - `download_file(key) -> bytes`
  - `upload_json(obj, key)`
  - `download_json(key) -> dict`
- Các phần khác (upload endpoint, worker parser, RAG) chỉ gọi storage layer, không trực tiếp thao tác R2.

### 4.4. RAG Engine – Interface trừu tượng

Định nghĩa interface logic (pseudo):

```python
def ingest_content(workspace_id: str, document_id: str, content_list: list[dict]) -> str:
    \"\"\"Ingest nội dung vào RAG Engine, trả về rag_doc_id.\"\"\"

def query(workspace_id: str, question: str, extra_context: dict | None = None) -> dict:
    \"\"\"Truy vấn RAG Engine theo workspace, trả về { answer, citations }.\"\"\"

def delete_document(rag_doc_id: str) -> None:
    \"\"\"Xoá document trong RAG Engine theo rag_doc_id.\"\"\"
```

- Implementation v1:
  - Dùng RAG‑Anything + LightRAG.
- Implementation khác trong tương lai:
  - Có thể dùng engine khác, miễn implement đúng interface.

### 4.5. Parser Service – Google Cloud Document AI & RAG chunker

#### 4.5.1. Lớp Document AI client (OCR)

- Trách nhiệm:
  - Nhận file (bytes) → gọi Google Cloud Document AI Enterprise OCR → trả về `Document` (hoặc JSON).
- Interface khái niệm:

```python
def process_document_ocr(file_bytes) -> Document:
    """Gọi Document AI OCR, trả về Document."""
```

Kết quả được dùng để:

- Lưu `docai_full_text` và `docai_raw_r2_key`.
- Là input cho bước chunking sang `content_list` ở Phase sau.

#### 4.5.2. Lớp RAG chunker (build content_list)

- Trách nhiệm:
  - Dựa trên dữ liệu đã parse (ít nhất là `docai_full_text`, và nếu cần, JSON raw) để tạo `content_list` cho RAG Engine.
- Interface khái niệm:

```python
def build_content_list_from_document(document_id: str) -> list[dict]:
    """Dùng docai_full_text (+ raw nếu cần) để tạo content_list chuẩn."""
```

- Parser service (Document AI + chunker) chỉ cần đảm bảo output đúng `content_list`. Toàn bộ logic RAG nằm ở engine phía sau.

---

## 5. Phân phase triển khai (overview)

### Phase 1 – Database & API khung

- Tạo schema Supabase (các bảng ở mục 4.2).
- Backend Python:
  - Auth (register/login/change‑password).
  - CRUD `workspaces`.
  - CRUD `conversations`, `messages` (message mới tạo chỉ lưu, chưa cần gọi RAG).
- Tích hợp Cloudflare R2 ở mức:
  - Upload file, lưu metadata vào `files`.

### Phase 2 – Parser & ingestion pipeline

- Tích hợp **Google Cloud Document AI – Enterprise Document OCR**.
- Xây `parse_jobs` + worker xử lý (background).
- Lưu kết quả parse:
  - `docai_full_text` trong `documents`.
  - `docai_raw_r2_key` trỏ tới JSON raw trên R2.
- Định nghĩa interface chunker (`build_content_list_from_document`) để Phase 3 dùng.

### Phase 3 – RAG Engine integration

- Chọn & tích hợp RAG Engine (v1: RAG‑Anything).
- Dùng chunker để tạo `content_list` từ dữ liệu đã OCR.
- Nối ingestion pipeline → RAG Engine:
  - `ingest_content` từ `content_list`.
- Nối chat API → RAG Engine:
  - `query` theo `workspace_id`.

### Phase 4 – Tối ưu & mở rộng

- Thêm Redis / job queue / websocket (realtime progress, chat streaming).
- Thêm tools mở rộng (web search, DB query cho data động).
- Tối ưu caching, logging, monitoring.

---

Tài liệu này là **kim chỉ nam v1** cho thiết kế hệ thống:

- Có thể dùng nguyên xi cho các project RAG khác.
- RAG‑Anything và Google Cloud Document AI chỉ là **2 implementation cụ thể** ở tầng Engine và Parser.
