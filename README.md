# 🚀 RAG Engine Backend

Đây là Backend Service cho hệ thống RAG (Retrieval-Augmented Generation), được xây dựng bằng **Python (FastAPI)**. Hệ thống quản lý Workspace, Tài liệu (Documents), Hội thoại (Conversations) và tích hợp với các dịch vụ đám mây mạnh mẽ.

## 🛠 Tech Stack

*   **Framework:** FastAPI
*   **Database:** Supabase (PostgreSQL) - Sử dụng `asyncpg` & `SQLAlchemy`.
*   **Authentication:** Supabase Auth (JWT Validation).
*   **Storage:** Cloudflare R2 (S3 Compatible).
*   **Migration:** Alembic.
*   **Package Manager:** Poetry.

---

## ⚙️ Hướng dẫn Cài đặt (Step-by-Step)

Dưới đây là các bước để thiết lập môi trường phát triển từ con số 0.

### 1. Yêu cầu tiên quyết (Prerequisites)

*   Python 3.10 trở lên.
*   [Poetry](https://python-poetry.org/docs/) đã được cài đặt.
*   Tài khoản **Supabase** (đã tạo Project).
*   Tài khoản **Cloudflare R2** (đã tạo Bucket).

### 2. Cài đặt Dependencies

Di chuyển vào thư mục dự án và cài đặt các thư viện:

```bash
cd rag-engine
poetry install
```

### 3. Cấu hình Biến môi trường (.env)

Sao chép file mẫu và tạo file cấu hình chính thức:

```bash
cp .env.example .env
```

Mở file `.env` và điền các thông tin sau (Quan trọng):

```env
# --- DATABASE (Supabase) ---
# LƯU Ý QUAN TRỌNG: Sử dụng Connection String của Supabase Connection Pooler (Port 6543) ở chế độ **Transaction Mode**.
# Mặc dù chế độ này không hỗ trợ Prepared Statements một cách truyền thống, code backend đã được cấu hình để thích nghi.
# Lấy tại: Supabase Dashboard -> Settings -> Database -> Connection String -> Pooler -> Mode: Transaction
SUPABASE_DB_URL=postgresql://postgres.your-project:[PASSWORD]@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres

> **⚠️ LƯU Ý QUAN TRỌNG VỀ LỖI KẾT NỐI (DuplicatePreparedStatementError):**
> Nếu bạn gặp lỗi `DuplicatePreparedStatementError: prepared statement "__asyncpg_stmt_..." already exists` khi khởi chạy server hoặc chạy migration/script, điều này là do **Supabase Transaction Pooler (cổng 6543) không hỗ trợ Prepared Statements**.
>
> **Giải pháp:** Code của dự án đã được cấu hình để **buộc `asyncpg` KHÔNG sử dụng Prepared Statements** bằng cách thêm các tùy chọn `connect_args` vào `create_async_engine`. Cụ thể, các file `server/app/db/session.py` (cho ứng dụng chính) và `rag-engine/alembic/env.py` (cho Alembic) phải chứa đoạn cấu hình sau:
> ```python
> connect_args={
>     "statement_cache_size": 0,
>     "prepared_statement_cache_size": 0,
>     "prepared_statement_name_func": lambda *args: "",
> },
> ```
> Nếu bạn vẫn gặp lỗi, hãy kiểm tra lại hai file này để đảm bảo các tùy chọn trên đã được áp dụng chính xác.

# Lấy tại: Supabase Dashboard -> Project Settings -> API -> JWT Secret
SUPABASE_JWT_SECRET=your-supabase-jwt-secret

# --- STORAGE (Cloudflare R2) ---
# Endpoint phải là URL API (không bao gồm tên bucket), kết thúc bằng account id
R2_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=your-access-key-id
R2_SECRET_ACCESS_KEY=your-secret-access-key
R2_BUCKET=your-bucket-name
```

### 4. Khởi tạo Database (Migration)

Chúng ta sử dụng **Alembic** để tạo các bảng trong Database. Chạy lệnh sau để áp dụng cấu trúc bảng mới nhất:

```bash
poetry run alembic upgrade head
```

### 5. Tạo dữ liệu mẫu (Seed Data) - Tùy chọn

Vì chúng ta không có API đăng ký user (việc này do Supabase Auth lo), bạn cần tạo một user "giả lập" trong database để test. Chạy script sau:

```bash
poetry run python scripts/seed_users.py
```
*Lưu lại `User ID` được in ra màn hình để dùng cho bước kiểm thử.*

---

## 🚀 Khởi chạy Server

Chạy server development với tính năng hot-reload:

```bash
poetry run uvicorn server.app.main:app --reload --host 127.0.0.1 --port 8000
```

Server sẽ hoạt động tại: `http://127.0.0.1:8000`
API Documentation (Swagger UI): `http://127.0.0.1:8000/docs`

---

## 🧪 Kiểm thử (Testing)

Dự án có sẵn script kiểm thử End-to-End (E2E) để verify toàn bộ luồng hoạt động (Auth -> Workspace -> Upload -> Chat).

Sau khi start server, mở một terminal khác và chạy:

```bash
# Thay <USER_ID> bằng ID bạn lấy được ở bước Seed Data
poetry run python scripts/e2e_phase1.py --base-url http://127.0.0.1:8000 --user-id <USER_ID>
```

Nếu tất cả các bước đều hiện output (OK/Found) mà không có lỗi đỏ, hệ thống đã hoạt động hoàn hảo!

---

## 🧵 Worker Phase 2 – Document AI Parser

Phase 2 sử dụng một **worker riêng** để xử lý `parse_jobs` (OCR bằng Google Cloud Document AI) ở background.

- Chạy worker parse (từ cùng project, cùng `.env`):

```bash
poetry run python -m server.app.workers.parse_worker
```

Worker sẽ:
- Poll bảng `parse_jobs` với `status='queued'`.
- Tải file gốc từ Cloudflare R2.
- Gọi Document AI (OCR) và lưu:
  - `documents.docai_full_text`
  - JSON raw Document AI lên R2 (`docai-raw/{document_id}.json`) và key vào `documents.docai_raw_r2_key`.
- Cập nhật trạng thái `parse_jobs` (`running/success/failed`) và `documents.status` (`parsed`/`error`).

Bạn nên chạy worker này song song với server (ví dụ 2 terminal, 2 service, hoặc 2 container khi deploy).

---

## 📂 Cấu trúc thư mục chính

*   `server/app/`: Mã nguồn chính của ứng dụng.
    *   `api/routes/`: Các endpoints API (Controllers).
    *   `core/`: Cấu hình hệ thống, Security, Logging.
    *   `db/`: Models (Schema DB) và Repositories (Truy vấn DB).
    *   `schemas/`: Pydantic Models (Validation request/response).
    *   `services/`: Các module tích hợp bên ngoài (R2, RAG...).
*   `alembic/`: Quản lý migration database.
*   `scripts/`: Các script tiện ích (Seed data, E2E test, Init DB).
