# [Tên Project/Module] – Tech Design ([Tên Phase])

**Mục tiêu**: Chuyển đặc tả (Requirements) thành thiết kế kỹ thuật cụ thể, chi tiết các quyết định về công nghệ, kiến trúc và luồng dữ liệu.

---

## 1. Tech Stack & Quyết định chính

Liệt kê các công nghệ và thư viện sẽ sử dụng, cùng lý do (nếu cần).

- **Backend**: (Ví dụ: Python + FastAPI (async))
- **Database**: (Ví dụ: Supabase Postgres, SQLAlchemy Core async)
- **Authentication**: (Ví dụ: Supabase Auth, JWT Verification)
- **External Services**: (Ví dụ: Cloudflare R2, Google Cloud Document AI)
- **Other**: (Ví dụ: Redis, Celery, etc.)

---

## 2. Cấu trúc Folder & Module (Source Code)

Mô tả cây thư mục dự kiến và vai trò của từng module/file.

```text
server/
  app/
    main.py           # Entry point
    core/             # Config, Security, Logging
    api/              # Routes definition
    services/         # Business logic & External integrations
    db/               # Models, Repositories
    schemas/          # Pydantic models
    workers/          # Background tasks
```

---

## 3. Configuration & Environment

### 3.1. Biến môi trường (Env Vars)
Danh sách các biến môi trường cần thiết.

- `VAR_NAME`: Mô tả.

### 3.2. Config Loader
Cách load và quản lý cấu hình trong code (ví dụ: `pydantic-settings`).

---

## 4. Database Layer Design

### 4.1. Models (Schema Mapping)
Cách map database schema vào code (ORM models hoặc Core Tables).

### 4.2. Repositories / Data Access
Cách truy xuất dữ liệu. Defines các interface/class để tương tác với DB.

- `EntityRepository`:
  - `method_name(args) -> return_type`

---

## 5. Service Layer & External Integrations

Thiết kế chi tiết cho các service logic hoặc integrations.

### 5.1. [Service Name - Ví dụ: StorageService]
- **Interface**:
  - `method(args)`
- **Implementation**:
  - Logic xử lý, thư viện sử dụng.

### 5.2. [Service Name - Ví dụ: RagEngineService]
- ...

---

## 6. API Design & Routes

Mapping chi tiết giữa Endpoint và Service/Logic.

### 6.1. [Group Name - Ví dụ: Auth]
- `POST /path`: Logic xử lý (gọi service nào, trả về gì).

### 6.2. [Group Name - Ví dụ: Documents]
- `POST /upload`: Flow xử lý upload file, tạo job, lưu DB.

---

## 7. Background Workers / Jobs (Nếu có)

Thiết kế cho các tác vụ xử lý nền.

- **Job Type**: [Tên Job]
- **Trigger**: Khi nào job được tạo/chạy.
- **Processing Logic**: Các bước thực hiện trong job.

---

## 8. Security & Authentication

- Cách verify user.
- Authorization (Quyền truy cập).

---

## 9. Logging & Monitoring

- Chiến lược log (format, level).
- Các metric quan trọng cần theo dõi.

---

## 10. Kế hoạch Implement & Testing

- Các bước code theo thứ tự ưu tiên.
- Chiến lược test (Unit test, Integration test).

---

## 11. Ghi chú & Kết luận

- Tóm tắt lại phạm vi của thiết kế này.
- Các vấn đề mở (Open issues) cần giải quyết sau.
