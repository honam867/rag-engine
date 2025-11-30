# AGENTS.md – Template for Multi‑Domain Knowledge Engine Project

> This file describes how AI coding agents should work **in the new rag‑engine project** that will be built from these design docs (server + client).  
> In this repo (`RAG-Anything`), treat this as **documentation/template only** – do **not** change `raganything/` unless explicitly requested.

---

## 1. Scope & Source of Truth

- **Scope** (khi được copy sang project mới):
  - Áp dụng cho toàn bộ repo mới có cấu trúc:
    - `server/` – FastAPI backend (Supabase + R2 + RAG‑Anything).
    - `client/` – UI gọi API của server (có thể là web app).
- **Source of truth về nghiệp vụ & kiến trúc** (trong thư mục `docs/`):
  - `docs/requirements/*` – đặc tả domain & phase (requirements-phase-*.md, overview).
  - `docs/design/architecture-overview.md` – kiến trúc tổng.
  - `docs/design/phase-*-design.md` – thiết kế kỹ thuật theo phase.
  - `docs/implement/*` – log từng lần implement feature / bugfix (theo task), dùng để tracking lịch sử triển khai.
- Khi làm việc:
  - Luôn đọc/refresh các file trên trước khi sửa code.
  - Nếu thực tế code khác spec → **ưu tiên spec**, nhưng phải nêu rõ sự khác biệt trong PR/commit message.

---

## 2. Repo layout (server / client)

Khi project mới được tạo, layout mong muốn:

```text
server/
  app/
    main.py

    core/
      config.py
      logging.py
      security.py
      constants.py      # Nơi đặt các constant chung (role, status, v.v.)

    db/
      session.py        # Kết nối Supabase Postgres (SQLAlchemy Core + asyncpg)
      models.py         # (Optional) ORM/Core metadata mapping schema
      repositories.py   # Hàm truy vấn DB (workspaces, documents, jobs,...)

    api/
      routes/
        me.py
        workspaces.py
        documents.py
        conversations.py
        messages.py
        status.py       # optional

    schemas/
      workspaces.py
      documents.py
      conversations.py
      common.py

    services/
      storage_r2.py     # Cloudflare R2 wrapper
      docai_client.py   # Google Cloud Document AI OCR wrapper
      parser_pipeline.py
      chunker.py
      rag_engine.py     # Wrap RAG‑Anything
      jobs_ingest.py

    workers/
      parse_worker.py
      ingest_worker.py

    utils/
      time.py
      ids.py

client/
  # UI (web/app) – chỉ gọi API từ server/
```

Agent **không được** tự ý thay đổi layout high‑level này trừ khi spec được cập nhật.

---

## 3. Supabase, R2, RAG‑Anything – cách dùng

**Supabase (Postgres + Auth)**

- Treat Supabase như **managed Postgres**:
  - Kết nối bằng `SUPABASE_DB_URL` (full DSN) qua SQLAlchemy Core + asyncpg.
  - Không dùng Alembic để migrate schema; migrations do Supabase quản lý.
- Auth:
  - Supabase Auth phát JWT (email/password).
  - Backend verify JWT bằng `SUPABASE_JWT_SECRET` hoặc JWKS.
  - Quyền truy cập (workspace, document, conversation) kiểm tra ở layer API/DB (`WHERE workspace.user_id = current_user.id`), **không dùng RLS**.

**Cloudflare R2**

- Tất cả thao tác R2 phải qua `services/storage_r2.py`:
  - `upload_file`, `download_file`, `upload_json`, `download_json`.
- Các module khác **không** được gọi SDK R2 trực tiếp.

**RAG‑Anything / LightRAG**

- Được wrap trong `services/rag_engine.py`:
  - `ingest_content(workspace_id, document_id, content_list)`.
  - `query(workspace_id, question, extra_context) -> { answer, citations }`.
  - `delete_document(rag_doc_id)`.
- Parser bên ngoài (Document AI) phải tạo `content_list` theo format README RAG‑Anything mô tả, sau đó mới call `rag_engine`.

---

## 4. Coding style & naming

**Ngôn ngữ & naming**

- Code (tên file, module, hàm, class, biến): **tiếng Anh**, snake_case cho function/variable, PascalCase cho class.
- Có thể dùng comment/docstring tiếng Việt nếu cần giải thích business, nhưng ưu tiên tiếng Anh nếu có thể.

**Constants**

- Đặt trong `core/constants.py`, không hard‑code rải rác:
  - Roles: `ROLE_USER = "user"`, `ROLE_AI = "ai"`.
  - Document status: `"pending"`, `"parsed"`, `"ingested"`, `"error"`.
  - Job status: `"queued"`, `"running"`, `"success"`, `"failed"`.
- Khi thay đổi giá trị, chỉ sửa ở constants, không sửa literal trong code.

**API & schemas**

- Pydantic schemas trong `schemas/*` là hợp đồng chính giữa API ↔ client.
- Các route chỉ nhận/trả schemas, không trả raw ORM/row.

**Repositories & services**

- `db/repositories.py` chỉ làm việc với DB (SQLAlchemy Core), không biết gì về R2/Document AI/RAG.
- `services/*` là nơi orchestrate nhiều nguồn (DB + R2 + RAG), nhưng không chứa logic HTTP (không dùng `Request`/`Response` trong services).

---

## 5. Agent behavior – do & don’t

**Always do**

- Đọc lại các file design tương ứng phase trước khi code:
  - Phase 1: `phase-1-design.md`
  - Phase 2: `phase-2-design.md`
  - Phase 3: `phase-3-design.md`
- Giữ cấu trúc folder ổn định, thêm file mới đúng layer (`api/`, `services/`, `db/`, `schemas/`).
- Khi thêm logic mới:
  - Thêm vào **service hoặc repo** trước, rồi API chỉ gọi lại.

**Never do (trừ khi user yêu cầu rõ)**

- Không tự ý sửa kiến trúc tổng trong `architecture-overview.md`.
- Không thay đổi cách kết nối Supabase (không chuyển sang SDK, không thêm RLS).
- Không nhảy trực tiếp vào RAG‑Anything nội bộ (`raganything/`) nếu đã có wrapper `rag_engine.py` ở server/.
- Không trộn code server vào client hoặc ngược lại.

**When unsure**

- Nếu spec / design chưa rõ hoặc có mâu thuẫn với code hiện tại:
  - Hỏi lại user (hoặc ghi rõ assumption trong comment/PR).
  - Không “tự sáng tác” kiến trúc mới.

---

## 6. Commands (gợi ý, tuỳ project mới)

Khi project mới được scaffold, nên có các command chuẩn (ví dụ):

- Chạy server dev:
  - `uvicorn server.app.main:app --reload`
- Chạy tests (nếu có):
  - `pytest`
- Format/lint (nếu được setup):
  - `ruff check .`, `black .`

Agent nên dùng đúng commands đã được định nghĩa trong README/Makefile/pyproject của project mới (khi có).  

---

---

## 7. Implementation logs – bắt buộc sau mỗi task

Để tăng độ ổn định giữa các phiên làm việc (và giữa nhiều agent), **mỗi khi hoàn thành một task coding có ý nghĩa**, agent phải:

- Tạo hoặc cập nhật một file trong `docs/implement/`:
  - Tên file mới: `implement-<short-feature-name>.md` (xem thêm ở `docs/implement/README.md`).
  - Nếu đang tiếp tục đúng một feature đã có file implement → ưu tiên **cập nhật file đó** (không tạo file trùng).
- Ghi tối thiểu các phần:
  - Summary: task này làm gì, thuộc phase nào.
  - Related spec/design: link tới requirements / design tương ứng.
  - Files touched: liệt kê file đã sửa, 1 dòng mô tả.
  - API changes (nếu có): endpoint, request/response ví dụ.
  - Sequence / flow: mermaid hoặc ASCII cho flow chính.
  - Notes / TODO: những gì chưa làm hoặc cần chú ý ở phase sau.

Mục đích:
- Khi bạn mở chat mới hoặc đổi agent, chỉ cần đọc lại:
  - `docs/requirements/*` (what),
  - `docs/design/*` (how),
  - `docs/implement/*` (đã làm tới đâu),
  là có thể tiếp tục triển khai mà không đoán mò.

---

File này được thiết kế để có thể copy nguyên sang project mới.  
Khi copy, nhớ kiểm tra lại đường dẫn nếu cấu trúc thư mục khác với `docs/requirements`, `docs/design` và `docs/implement`.
