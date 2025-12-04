# Implement: Phase 5 – Realtime WebSocket & Worker Reliability

## 1. Summary
- Scope: server (API + workers), Phase 5.
- Mục tiêu: 
  - Thêm WebSocket `/ws` theo user để client có thể nhận realtime event cho chat + document/job status **không cần polling**.
  - Bổ sung cơ chế retry có giới hạn và self-heal cơ bản cho `parse_jobs` để tránh job chạy vô hạn hoặc bị kẹt ở trạng thái `running`.

## 2. Related spec / design
- Requirements:
  - `docs/requirements/requirements-phase-5.md`
- Design:
  - `docs/design/phase-5-design.md`
  - `docs/design/architecture-overview.md` (mục Jobs / Worker Layer)
- Client design (contract, không implement code FE):
  - `docs/design/client-design-phase-5.md`

## 3. Files touched
- `server/app/core/security.py`
  - Thêm `get_current_user_ws(websocket: WebSocket)` để decode Supabase JWT từ query param `token` hoặc header `Authorization` cho WebSocket.
- `server/app/core/realtime.py`
  - Thêm `ConnectionManager` giữ danh sách WebSocket theo `user_id`.
  - Cung cấp helper `send_event_to_user(user_id, event_type, payload)` dùng chung cho routes/services/workers (best-effort, không làm hỏng business flow nếu lỗi).
- `server/app/api/routes/realtime.py`
  - Thêm endpoint `GET /ws` (WebSocket):
    - Auth qua `get_current_user_ws`.
    - Mỗi connection được gắn với `CurrentUser.id` trong `ConnectionManager`.
    - V1 chỉ giữ kết nối mở, không xử lý message từ client (thuần push).
- `server/app/main.py`
  - Register router mới `realtime.router` để expose `/ws`.

- `server/app/core/constants.py`
  - Thêm constants cho message status:
    - `MESSAGE_STATUS_PENDING`, `MESSAGE_STATUS_RUNNING`, `MESSAGE_STATUS_DONE`, `MESSAGE_STATUS_ERROR`.

- `server/app/db/models.py`
  - `parse_jobs`:
    - Thêm cột `retry_count INTEGER NOT NULL DEFAULT 0` để track số lần retry.
  - `messages`:
    - Thêm cột `status TEXT NOT NULL DEFAULT 'done'` để phản ánh trạng thái xử lý của message (hiện tại chủ yếu hữu ích cho message AI).

- `server/app/db/repositories.py`
  - Thêm helper:
    - `get_workspace_owner_id(session, workspace_id)` → trả `user_id` của workspace (không filter theo current user, chỉ dùng cho realtime).
  - Parse jobs:
    - `requeue_parse_job(session, job_id, retry_count, error_message=None)`:
      - Set `status='queued'`, tăng `retry_count`, reset `started_at`/`finished_at`.
    - `fetch_stale_running_parse_jobs(session, older_than_seconds)`:
      - Tìm các job `status='running'` có `started_at` quá lâu (`started_at < now() - interval 'older_than_seconds seconds'`).
  - Messages:
    - Giữ nguyên API `create_message` nhưng giờ DB sẽ luôn có cột `status` (default `'done'`).

- `server/app/schemas/conversations.py`
  - Mở rộng schema `Message`:
    - Thêm field `status: Optional[str]` để API trả thêm trạng thái (khớp với cột `messages.status` mới).

- `server/app/api/routes/messages.py`
  - Sau khi tạo message user + AI (vẫn synchronous như Phase 3):
    - Gửi 2 realtime event `message.created` tới user (qua `send_event_to_user`):
      - Payload gồm `workspace_id`, `conversation_id`, và object `message` chứa:
        - `id`, `conversation_id`, `workspace_id`, `role`, `content`, `status='done'`, `created_at`, `metadata`.
  - Behaviour HTTP không đổi: vẫn trả về `Message` của AI.
  - V1 **chưa** tạo message AI `pending` trước rồi update sau – tất cả message gửi qua WS đều ở trạng thái `done` ngay khi RAG trả lời (matching flow hiện tại).

- `server/app/api/routes/documents.py`
  - Trong `upload_documents`:
    - Sau khi tạo `documents` + `files` + `parse_jobs`:
      - Gửi `document.created` cho user:
        - `workspace_id`, `document` với `id`, `title`, `status='pending'`, `source_type`, `created_at`.
      - Gửi `job.status_updated` cho parse job mới:
        - `job_id`, `job_type='parse'`, `workspace_id`, `document_id`, `status='queued'`, `retry_count`, `error_message`.
  - Behaviour upload (REST) giữ nguyên.

- `server/app/services/parser_pipeline.py`
  - Bổ sung import constants parse/job/document + `send_event_to_user`.
  - Khi bắt đầu xử lý job:
    - Load `parse_jobs` + `documents` để lấy `document_id`, `workspace_id`, `user_id`.
    - Mark job `running` như cũ → gửi event `job.status_updated` với `status='running'`.
  - Khi parse thành công:
    - Sau khi update `documents.docai_full_text`, `docai_raw_r2_key` và `status='parsed'` + mark job `success`:
      - Gửi `document.status_updated` (`status='parsed'`).
      - Gửi `job.status_updated` (`status='success'`, `retry_count` hiện tại).
  - Khi parse lỗi:
    - Thay vì luôn mark `failed`, giờ:
      - Đọc `retry_count` hiện tại (max 3).
      - Nếu `retry_count < 3`:
        - Gọi `requeue_parse_job` (tăng `retry_count + 1`, status `queued`).
        - Gửi `job.status_updated` với `status='queued'` và `retry_count` mới.
        - Không đổi trạng thái document (giữ `pending`/`parsed` tuỳ thời điểm).
      - Nếu `retry_count >= 3`:
        - Gọi `mark_parse_job_failed` + `update_document_parse_error` (`status='error'`).
        - Gửi `job.status_updated` (`status='failed'` + `error_message`).
        - Gửi `document.status_updated` (`status='error'`).

- `server/app/workers/parse_worker.py`
  - Trước vòng lặp chính:
    - Chạy một lần `fetch_stale_running_parse_jobs(..., older_than_seconds=600)` (~10 phút).
    - Với mỗi job stale:
      - Nếu `retry_count < 3` → `requeue_parse_job(..., retry_count+1, error="stale-running")`.
      - Nếu `retry_count >= 3` → `mark_parse_job_failed(..., error="stale-running")`.
  - Vòng lặp chính vẫn như cũ: gọi `pipeline.fetch_and_process_next_jobs(batch_size=1)` rồi sleep `idle`/`busy`.

- `server/app/services/jobs_ingest.py`
  - Sau khi ingest thành công một document:
    - Ngoài việc insert `rag_documents` + `documents.status='ingested'`, service sẽ:
      - Tra `user_id` owner của workspace.
      - Gửi realtime event `document.status_updated` (`status='ingested'`).
  - V1 **chưa** có bảng `ingest_jobs` riêng và **chưa** phát `job.status_updated` cho ingest; ingest worker vẫn retry vô hạn theo loop hiện tại nếu có lỗi, nhưng document chỉ được coi là “pending ingest” (status `'parsed'`). (Xem TODO bên dưới.)

## 4. API changes

### 4.1 HTTP API
- Không có thay đổi đường dẫn hay request body cho REST API:
  - `POST /api/conversations/{conversation_id}/messages` – vẫn trả `Message` của AI.
  - `POST /api/workspaces/{workspace_id}/documents/upload` – payload & response giữ nguyên.
- Response `Message` (schemas) giờ có thêm field `status` (optional) đọc từ `messages.status`:
  - Trong v1 Phase 5, mọi message (cả user lẫn AI) được lưu với `status='done'`.

### 4.2 WebSocket API (mới)

- Endpoint:

```http
GET /ws?token=<SUPABASE_JWT>
```

- Auth:
  - Token lấy giống như khi gọi REST (Supabase access token).
  - Backend validate qua `SUPABASE_JWT_SECRET`.

- Event format:

```json
{
  "type": "<event-type>",
  "payload": { ... }
}
```

- Các event hiện đang emit (server-side):
  - `message.created`
    - Khi user gửi message + khi AI trả lời xong.
  - `document.created`
    - Khi upload document thành công.
  - `document.status_updated`
    - Khi parse thành công → status `'parsed'`.
    - Khi parse lỗi sau `max_retries` → status `'error'`.
    - Khi ingest RAG thành công → status `'ingested'`.
  - `job.status_updated`
    - Cho `parse_jobs`:
      - `'queued'` (khi tạo job mới hoặc requeue).
      - `'running'`, `'success'`, `'failed'`.
    - Chưa emit cho ingest worker (chưa có ingest_jobs).

> Chi tiết payload xem thêm ở `docs/design/phase-5-design.md` và `docs/design/client-design-phase-5.md`. Implement backend đang bám khá sát, nhưng vẫn coi đó là contract chính nếu cần chỉnh nhẹ.

## 5. Sequence / flow (high-level)

### 5.1. Chat + realtime

```text
Client -> POST /api/conversations/{id}/messages
  -> Backend:
       - create user message (status='done')
       - call RAG
       - create AI message (status='done')
       - send 2 events "message.created" qua WebSocket cho user_id owner
  -> Client:
       - REST response: message AI
       - WebSocket: 2 event message.created -> update UI ở tất cả tab
```

### 5.2. Upload document + parse worker

```text
Client -> POST /api/workspaces/{ws}/documents/upload
  -> Backend:
       - create document (status='pending')
       - upload file lên R2
       - create parse_job (status='queued', retry_count=0)
       - emit:
           - document.created
           - job.status_updated (queued)

parse_worker loop:
  - heal_stale_parse_jobs()  # một lần lúc start
  - while True:
      - fetch queued parse_jobs
      - for each job:
          - mark_running + emit job.status_updated (running)
          - try:
              - download file từ R2
              - call Document AI
              - update documents (full_text, raw key, status='parsed')
              - mark job success
              - emit:
                  - document.status_updated (parsed)
                  - job.status_updated (success)
            except:
              - if retry_count < 3:
                  - requeue_parse_job (queued, retry+1)
                  - emit job.status_updated (queued)
              - else:
                  - mark_parse_job_failed (failed)
                  - update_document_parse_error (status='error')
                  - emit:
                      - job.status_updated (failed)
                      - document.status_updated (error)
```

### 5.3. Ingest worker + realtime

```text
ingest_worker loop:
  - select documents status='parsed' without rag_documents
  - for each doc:
      - chunker.build_content_list_from_document
      - rag_engine.ingest_content -> rag_doc_id
      - insert rag_documents + set documents.status='ingested'
      - emit document.status_updated (ingested)
```

## 6. Notes / TODO
- DB schema:
  - Cần ensure các cột mới tồn tại trên Supabase:
    - `parse_jobs.retry_count INTEGER NOT NULL DEFAULT 0`
    - `messages.status TEXT NOT NULL DEFAULT 'done'`
  - Repo đã update models, nhưng migration thực tế vẫn do Supabase quản lý (chạy SQL manually trên Supabase).
- Ingest worker:
  - Hiện tại **chưa có ingest_jobs** nên:
    - Không phát `job.status_updated` cho ingest.
    - Worker vẫn retry vô hạn nếu luôn lỗi (document vẫn ở trạng thái `'parsed'`).
  - TODO Phase sau:
    - Thiết kế `ingest_jobs` hoặc cơ chế retry có giới hạn cho ingest (tương tự parse_jobs).
    - Bổ sung event `job.status_updated` cho ingest nếu UI thực sự cần theo dõi chi tiết.
- Message status:
  - Cột `messages.status` hiện luôn là `'done'` cho cả user và AI.
  - TODO Phase sau:
    - Nếu chuyển RAG sang background task + streaming, có thể:
      - Tạo AI message `status='pending'` ngay khi user gửi.
      - Stream answer qua WebSocket (chunks) và cập nhật `status='running'`/`'done'`.
- Realtime consistency:
  - Event được gửi theo `user_id` owner của workspace:
    - Mọi tab của user đó đều nhận event (wiring client đã mô tả ở `client-design-phase-5.md`).
  - Nếu WebSocket disconnect:
    - Client vẫn có thể sync lại bằng REST (React Query), realtime chỉ là incremental update.
- Deployment / scaling:
  - Thiết kế hiện tại giả định API chạy 1 process; `ConnectionManager` nằm in-memory.
  - Nếu sau này scale nhiều instance, cần bổ sung pub/sub (Redis, Supabase Realtime, v.v.) để fan-out event giữa instance – ngoài scope Phase 5.

