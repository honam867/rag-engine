# Phase 1 – Tech Design (DB & API Khung)

Mục tiêu: chuyển đặc tả Phase 1 thành thiết kế kỹ thuật cụ thể, đủ để bắt đầu code backend FastAPI + Supabase + Cloudflare R2 theo kiến trúc trong `architecture-overview.md`.

---

## 1. Tech stack & quyết định chính

- **Backend**: Python + FastAPI (async).
- **DB access**: Supabase Postgres, kết nối bằng **SQLAlchemy Core async + asyncpg**:
  - Supabase chịu trách nhiệm migrations/schema.
  - App **không** dùng Alembic để migrate, chỉ query/insert/update dựa trên schema sẵn có.
  - Không dùng Supabase client SDK trong backend Python.
- **Auth**: Supabase Auth (email/password):
  - Frontend hoặc Supabase UI đảm nhiệm sign up / sign in.
  - FastAPI chỉ **verify JWT** Supabase gửi kèm trong `Authorization: Bearer <token>`.
  - Dùng `SUPABASE_JWT_SECRET` hoặc JWKS từ Supabase để verify.
- **Storage**: Cloudflare R2, S3-compatible, wrap bởi module `storage_r2`.
- **RAG Engine, Document AI**: chưa dùng ở Phase 1 (chỉ chuẩn bị field/schema, chưa gọi).

---

## 2. Folder tree (server/client)

Áp dụng skeleton từ `architecture-overview.md`:

```text
server/
  app/
    main.py

    core/
      config.py
      logging.py
      security.py

    db/
      session.py
      models.py
      repositories.py

    api/
      routes/
        me.py
        workspaces.py
        documents.py
        conversations.py
        messages.py
        status.py    # optional

    schemas/
      workspaces.py
      documents.py
      conversations.py
      common.py

    services/
      storage_r2.py
      # (Các service parser/rag sẽ tới Phase 2/3)

    workers/
      # Phase 1 chưa cần worker thật, chỉ placeholder

    utils/
      time.py
      ids.py

client/
  # UI sẽ gọi API ở server/, Phase 1 chưa thiết kế
```

Phase 1 chỉ implement những phần cần thiết; các file khác có thể là stub/placeholder để Phase sau dùng.

---

## 3. Config & môi trường (core/config.py)

### 3.1. Env cần thiết

- Supabase:
  - `SUPABASE_DB_URL` – Postgres connection string (service role hoặc connection riêng cho backend).
  - `SUPABASE_JWT_SECRET` – secret để verify JWT (lấy từ project settings).
- Cloudflare R2:
  - `R2_ENDPOINT`
  - `R2_ACCESS_KEY_ID`
  - `R2_SECRET_ACCESS_KEY`
  - `R2_BUCKET`

### 3.2. Cấu trúc config

- Dùng Pydantic `BaseSettings` hoặc tương tự để đọc env:
  - `DatabaseSettings` (db_url).
  - `R2Settings` (endpoint, key, secret, bucket).
  - `AuthSettings` (jwt_secret, supabase_project_id nếu cần).
- `get_settings()` dùng FastAPI dependency injection hoặc import trực tiếp (singleton).

---

## 4. DB layer (db/session.py, db/models.py, db/repositories.py)

### 4.1. Kết nối DB (session.py)

- Dùng SQLAlchemy async engine + asyncpg:
  - `create_async_engine(settings.db_url, echo=False, future=True)`
  - `async_sessionmaker(bind=engine, expire_on_commit=False)`
- Dependency cho FastAPI:

```python
async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session
```

> Lưu ý: Không dùng Alembic ở project này; toàn bộ schema được quản lý bởi Supabase.

### 4.2. Models (models.py)

- Option 1 (đề xuất Phase 1): **SQLAlchemy Core** với `Table`:
  - Khai báo `workspaces`, `documents`, `files`, `parse_jobs`, `rag_documents`, `conversations`, `messages` bằng `Table(...)` trùng schema Supabase.
  - Ưu điểm: nhẹ, rõ ràng; không cần ORM nặng.
- Option 2 (sau này nếu cần): thêm ORM models mỏng chỉ để type hint, nhưng không dùng Alembic.

### 4.3. Repositories (repositories.py)

- Tách hàm truy vấn DB theo entity:
  - `WorkspaceRepository` (hoặc hàm module-level):
    - `create_workspace(session, user_id, name, description)`
    - `list_workspaces(session, user_id)`
    - `get_workspace(session, workspace_id, user_id)`
  - `DocumentRepository`:
    - `create_document(session, workspace_id, title, source_type)`
    - `list_documents(session, workspace_id)`
    - `get_document(session, document_id, workspace_id)`
  - `FileRepository`:
    - `create_file(session, document_id, r2_key, original_filename, mime_type, size_bytes, checksum)`
  - `ParseJobRepository`:
    - `create_parse_job(session, document_id)`
  - `ConversationRepository`:
    - `create_conversation(session, workspace_id, user_id, title)`
    - `list_conversations(session, workspace_id, user_id)`
  - `MessageRepository`:
    - `list_messages(session, conversation_id, user_id)`
    - `create_message(session, conversation_id, role, content, metadata)`

- Query style:
  - Dùng SQLAlchemy Core:

```python
stmt = sa.select(workspaces).where(workspaces.c.user_id == user_id)
result = await session.execute(stmt)
rows = result.fetchall()
```

- Repositories **không** biết gì về Supabase Auth/JWT; chỉ nhận `user_id` đã verify từ layer trên.

---

## 5. Auth & security (core/security.py)

### 5.1. JWT từ Supabase

- Flow:
  - Client (hoặc Supabase JS) đăng nhập → nhận access token (JWT).
  - Gửi JWT trong header `Authorization: Bearer <token>` đến FastAPI.

### 5.2. Verify JWT trong FastAPI

- Trong `security.py`:
  - Hàm `decode_token(token) -> UserInfo`:
    - Dùng `SUPABASE_JWT_SECRET` + thư viện JWT (vd PyJWT) để decode & verify:
      - Signature hợp lệ.
      - Token chưa hết hạn.
    - Lấy `sub` (user id) và các claim cần thiết.
  - Dependency `get_current_user`:

```python
async def get_current_user(request: Request) -> CurrentUser:
    # Lấy token từ Authorization header
    # Decode bằng decode_token()
    # Trả object CurrentUser(user_id=..., email=...)
```

- Error handling:
  - Nếu không có/invalid token → raise HTTP 401.

> Phase 1: không cần RLS; mọi kiểm tra “user này có quyền xem workspace này không” do API + repo xử lý (`WHERE workspace.user_id = current_user.id`).  

---

## 6. Storage layer (services/storage_r2.py)

### 6.1. Interface

- `upload_file(file_bytes, key, content_type) -> None`
- `download_file(key) -> bytes`
- `upload_json(obj, key) -> None`
- `download_json(key) -> dict`

### 6.2. Implementation (mức khái niệm)

- Dùng `boto3` hoặc client S3‑compatible:
  - Khởi tạo client với `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`.
  - `upload_file` dùng `put_object(Bucket=..., Key=key, Body=file_bytes, ContentType=...)`.
- Phase 1 chỉ cần:
  - `upload_file` khi user upload document.
  - Chưa cần `download_file/json` (sẽ dùng Phase 2).

---

## 7. API routes Phase 1 (api/routes/*)

Tất cả routes dùng dependency `get_current_user` + `get_db_session`.

### 7.1. `/me` (me.py)

- `GET /me`
  - Trả về `{"user_id": ..., "email": ...}` để client test auth.

### 7.2. Workspaces (workspaces.py)

- `POST /workspaces`
  - Body: `{ "name": str, "description": str | null }`
  - Logic:
    - Gọi `WorkspaceRepository.create_workspace(session, current_user.id, ...)`.
  - Return: workspace schema.

- `GET /workspaces`
  - List tất cả workspaces của current user.

- `GET /workspaces/{workspace_id}`
  - Lấy chi tiết workspace (optional nếu Phase 1 cần).

### 7.3. Documents & upload (documents.py)

- `POST /workspaces/{workspace_id}/documents/upload`
  - Nhận multipart form:
    - 1 hoặc nhiều file (Phase 1 có thể hỗ trợ 1 file trước).
  - Logic cho mỗi file:
    - Kiểm tra workspace thuộc current user.
    - Tính checksum (md5/sha256).
    - Upload file lên R2 với key: `workspace/{workspace_id}/document/{document_id}/{file_id}.ext`.
    - Tạo `document` (status=`pending`) + `file` record.
    - Tạo `parse_job` với status=`queued`.
  - Trả: danh sách documents vừa tạo (id, title, status).

- `GET /workspaces/{workspace_id}/documents`
  - List documents (id, title, status, created_at).

### 7.4. Conversations & messages (conversations.py, messages.py)

- `POST /workspaces/{workspace_id}/conversations`
  - Body: `{ "title": str }`.
  - Tạo conversation cho user trong workspace đó.

- `GET /workspaces/{workspace_id}/conversations`
  - List conversations của user trong workspace.

- `GET /conversations/{conversation_id}/messages`
  - List messages (role, content, created_at).

- `POST /conversations/{conversation_id}/messages`
  - Body: `{ "content": str }`.
  - Phase 1:
    - Lưu message `role='user'` vào DB.
    - Option: tạo message `role='ai'` mock (`"Engine chưa kết nối"`) để test flow hai chiều.
  - Phase 3 sẽ thay logic này bằng call RAG Engine.

---

## 8. Logging & error handling (core/logging.py)

- Thiết lập logger chung:
  - Format: timestamp, level, module, message.
  - Log các sự kiện chính:
    - Upload file (workspace_id, document_id, file size).
    - Lỗi DB/R2 (kèm stacktrace ở dev).

---

## 9. Kết luận cho Phase 1 tech design

- Phase 1 tập trung vào:
  - Kết nối Supabase Postgres theo best practice (SQLAlchemy Core + asyncpg, **không** đụng tới migrations).
  - Xây khung API:
    - Auth qua Supabase JWT.
    - Workspaces, documents (upload → tạo parse_jobs), conversations, messages.
  - Wrap Cloudflare R2 trong một service duy nhất (`storage_r2`).
- Chưa có:
  - Gọi Document AI (Phase 2).
  - Gọi RAG‑Anything (Phase 3).
  - Worker thực thi `parse_jobs` (Phase 2).

Thiết kế này bám sát kiến trúc tổng và best practice Supabase cho Python, đủ chi tiết để bắt đầu implement Phase 1 mà không cần thay đổi lại nền móng sau này. 

