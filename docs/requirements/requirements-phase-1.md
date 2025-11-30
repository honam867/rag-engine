# rag-engine-phase-1 – Database & API Khung

## 1. Mục tiêu Phase 1

- Dựng khung backend FastAPI + Supabase + Cloudflare R2:
  - Dùng **Supabase Auth** cho đăng ký / đăng nhập / đổi mật khẩu.
  - Thiết kế & tạo xong schema DB cơ bản (workspaces, documents, files, parse_jobs, rag_documents, conversations, messages).
  - Kết nối thật với Cloudflare R2 để upload file.
- Expose các API khung:
  - Kiểm tra auth (`/me`).
  - Quản lý workspaces.
  - Upload file vào workspace (chưa parse, chỉ tạo job).
  - Quản lý conversation & message (chưa gọi RAG Engine, chỉ lưu).

---

## 2. Database & Supabase

### 2.1. Sử dụng Supabase

- Supabase đảm nhiệm:
  - **Auth**: Supabase Auth (`auth.users`) với email + password.
  - **Postgres**: các bảng app nằm trong schema `public`.
- Không tạo bảng `users` riêng:
  - Mọi liên kết user sẽ dùng FK tới `auth.users.id`.

### 2.2. Bảng cần tạo trong `public`

- `workspaces`
  - `id` (uuid, PK)
  - `user_id` (uuid, FK `auth.users.id`)
  - `name` (text)
  - `description` (text, nullable)
  - `created_at` (timestamptz, default now())
  - `updated_at` (timestamptz, default now())

- `documents`
  - `id` (uuid, PK)
  - `workspace_id` (uuid, FK `workspaces.id`)
  - `title` (text)
  - `source_type` (text: `upload`, `api`, …)
  - `status` (text: `pending`, `parsed`, `ingested`, `error`)
  - `created_at`, `updated_at`

- `files`
  - `id` (uuid, PK)
  - `document_id` (uuid, FK `documents.id`)
  - `r2_key` (text)
  - `original_filename` (text)
  - `mime_type` (text)
  - `size_bytes` (bigint)
  - `checksum` (text)
  - `created_at`

- `parse_jobs`
  - `id` (uuid, PK)
  - `document_id` (uuid, FK `documents.id`)
  - `status` (text: `queued`, `running`, `success`, `failed`)
  - `parser_type` (text, default `gcp_docai`)
  - `error_message` (text, nullable)
  - `started_at` (timestamptz, nullable)
  - `finished_at` (timestamptz, nullable)

- `rag_documents`
  - `id` (uuid, PK)
  - `document_id` (uuid, FK `documents.id`)
  - `rag_doc_id` (text)
  - `created_at`

- `conversations`
  - `id` (uuid, PK)
  - `workspace_id` (uuid, FK `workspaces.id`)
  - `user_id` (uuid, FK `auth.users.id`)
  - `title` (text)
  - `created_at`, `updated_at`

- `messages`
  - `id` (uuid, PK)
  - `conversation_id` (uuid, FK `conversations.id`)
  - `role` (text: `user`, `ai`)
  - `content` (text)
  - `metadata` (jsonb, nullable)
  - `created_at`

## 3. Auth & tích hợp Supabase

- Đăng ký / đăng nhập sử dụng Supabase Auth (qua Supabase UI/SDK).
- Backend FastAPI:
  - Nhận JWT từ header `Authorization: Bearer <token>`.
  - Verify JWT bằng Supabase Python client hoặc libs tương đương.
  - Trích `user_id` (`sub`/`uid`) gán vào `workspaces.user_id`, `conversations.user_id`.
- Endpoint tiện ích:
  - `GET /me`: trả lại `user_id` (và email nếu cần) để kiểm tra auth.

---

## 4. Cloudflare R2 Integration

- Cấu hình:
  - Env vars: `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`.
  - Dùng thư viện S3‑compatible (vd `boto3` hoặc `aioboto3`) trong FastAPI.
- Flow upload file (Phase 1):
  - Nhận file multipart từ client.
  - Sinh `document_id` & `file_id`.
  - Upload file lên R2 với key dạng: `workspace/{workspace_id}/document/{document_id}/{file_id}.ext`.
  - Ghi record vào:
    - `documents` (status=`pending`),
    - `files`,
    - `parse_jobs` (status=`queued`).

---

## 5. FastAPI Backend Skeleton & API

### 5.1. Cấu trúc project gợi ý

- `app/main.py` – FastAPI app, include routers.
- `app/config.py` – đọc env (Supabase URL/key, R2 config).
- `app/db.py` – kết nối Postgres (SQLAlchemy/asyncpg).
- `app/deps.py` – dependency `get_current_user` (verify Supabase JWT).
- `app/routes/`:
  - `workspaces.py`
  - `documents.py`
  - `conversations.py`
  - `me.py` (optional).
- `app/schemas/` – Pydantic models.
- `app/models/` – ORM models (nếu dùng SQLAlchemy).
- Thiết lập logging đơn giản (dùng logging chuẩn của Python hoặc `structlog`) để log:
  - Request quan trọng (upload, tạo workspace).
  - Lỗi kết nối DB/R2.

### 5.2. Endpoints Phase 1

- `GET /me`
  - Input: JWT Supabase.
  - Output: thông tin cơ bản (`user_id`, email nếu cần).

- `POST /workspaces`
  - Body: `{ name, description? }`.
  - Action: tạo workspace cho `current_user`.

- `GET /workspaces`
  - List workspaces của current user.

- `GET /workspaces/{workspace_id}`
  - Trả chi tiết workspace (optional).

- `POST /workspaces/{workspace_id}/documents/upload`
  - Nhận 1 hoặc nhiều file (multipart).
  - Với mỗi file:
    - Upload lên R2.
    - Tạo `documents`, `files`, `parse_jobs`.

- `GET /workspaces/{workspace_id}/documents`
  - List documents (title, status, created_at, …).

- `POST /workspaces/{workspace_id}/conversations`
  - Body: `{ title }`.
  - Action: tạo conversation mới.

- `GET /workspaces/{workspace_id}/conversations`
  - List conversations trong workspace của user.

- `GET /conversations/{conversation_id}/messages`
  - List messages theo thời gian.

- `POST /conversations/{conversation_id}/messages`
  - Body: `{ content }`.
  - Phase 1:
    - Lưu message với `role='user'`.
    - Option: thêm 1 message `role='ai'` dạng mock (“Engine chưa kết nối”) để test 2 chiều.

### 5.3. Tiện ích dev

- Viết một script/command nhỏ để:
  - Tạo sẵn 1–2 workspace mẫu cho user hiện tại.
  - (Option) Seed 1 conversation + vài message mock để test nhanh UI/API.

---

## 6. Kết quả kỳ vọng & đánh giá đủ/thiếu

### 6.1. Kết quả sau Phase 1

- Có backend FastAPI chạy được:
  - Xác thực bằng JWT Supabase.
  - Có các bảng trong Supabase như spec.
  - Upload file thật lên Cloudflare R2, lưu metadata + tạo parse_jobs.
  - Tạo/list workspaces, conversations, messages (khung chat).
- Chưa cần:
  - Gọi Google Cloud Document AI.
  - Gọi RAG Engine.
  - Xử lý `parse_jobs`.

### 6.2. Phase 1 đã đủ để bắt đầu chưa?

- Với mục tiêu **dựng khung hệ thống** và **không phụ thuộc vào RAG‑Anything** ở bước đầu, plan Phase 1 hiện tại là **đủ để bắt đầu code ngay**:
  - Flow dữ liệu user → workspace → document → file → parse_job đã được cover.
  - Flow cơ bản cho conversation/message đã có.

Nếu bạn đồng ý với plan Phase 1 này, Phase 2 sẽ tập trung vào:

- Tích hợp Google Cloud Document AI.
- Xây parser service (`parse_file -> content_list`).
- Bắt đầu xử lý `parse_jobs` thật sự.
