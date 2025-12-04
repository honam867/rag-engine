# rag-engine-phase-5.1 – Cross-Process Realtime Bridge (Workers → WebSocket)

## 1. Mục tiêu Phase 5.1

- Giải quyết vấn đề **realtime từ worker** trong kiến trúc nhiều process:
  - API server (FastAPI + WebSocket) chạy 1 process riêng.
  - `parse_worker.py` + `ingest_worker.py` chạy các process Python riêng.
  - Hiện tại: WebSocket client chỉ connect vào API process, nên mọi event emit từ worker (process khác) đang **không tới được client**.
- Phase 5.1 bổ sung một lớp **bridge** để:
  - Worker phát event (`document.status_updated`, `job.status_updated`, …) → event đi qua một kênh chung (dựa trên Supabase Postgres).
  - API process lắng nghe kênh này và forward lại vào WebSocket `/ws` cho đúng `user_id`.

Mục tiêu là **không thay đổi luồng business chính** (parse, ingest, chat), chỉ thêm cơ chế chuyển tiếp event cross-process.

---

## 2. Phạm vi & nguyên tắc

### 2.1. Phạm vi Phase 5.1

- Chỉ áp dụng cho **backend**:
  - API server (FastAPI).
  - Workers (`parse_worker`, `ingest_worker`).
- Thêm một **cross-process event bridge**:
  - Worker publish event vào Supabase Postgres (LISTEN/NOTIFY hoặc tương đương).
  - API process subscribe và chuyển tiếp event sang WebSocket.

Không thay đổi:

- API REST hiện tại (Phase 1–4, 5).
- Contract WebSocket (`/ws`, event `type` + `payload`) đã define ở Phase 5:
  - `document.created`
  - `document.status_updated`
  - `job.status_updated`
  - `message.created`
  - `message.status_updated` (đã được spec, hiện mới dùng `message.created`).

### 2.2. Nguyên tắc thiết kế

- **Không thêm hạ tầng mới**:
  - Không thêm Redis, Kafka, v.v.
  - Tận dụng **Supabase Postgres** hiện có làm “event bus nhẹ”.
- **Best-effort realtime**:
  - Nếu bridge hỏng hoặc không có API process online:
    - Business vẫn chạy (parse/ingest/chat không bị block).
    - Realtime chỉ đơn giản là không tới client (client vẫn có thể sync qua REST).
- **Đồng bộ với event model Phase 5**:
  - Event từ worker phải có cùng format `type + payload` như khi emit trực tiếp từ API.
  - Client không cần biết event đến từ API hay worker.

---

## 3. Use cases chính

1. **Parse (Document AI) hoàn tất ở worker**:
   - Hiện tại:
     - `parse_worker` update `documents.status='parsed'` + `parse_jobs.status='success'`.
     - Gọi `send_event_to_user(...)` trong worker → event không tới client (khác process).
   - Sau Phase 5.1:
     - Worker publish event qua Postgres.
     - API process nhận và forward `document.status_updated` + `job.status_updated` tới WebSocket client.

2. **Ingest RAG hoàn tất ở ingest_worker**:
   - Hiện tại:
     - `ingest_worker` update `documents.status='ingested'`.
     - Gọi `send_event_to_user(...)` trong worker → không tới client.
   - Sau Phase 5.1:
     - Worker publish event → API process forward `document.status_updated (ingested)` tới client.

3. **Restart / multi-instance** (cơ bản):
   - Nếu có 2 instance API đều listen:
     - Cả 2 đều nhận NOTIFY từ Postgres.
     - Instance nào đang giữ WebSocket cho `user_id` thì gửi được event.
   - Nếu không có API instance nào online:
     - Notifications sẽ bị “mất” (LISTEN/NOTIFY là in-memory).
     - Nhưng DB vẫn là source of truth; client khi reload vẫn đọc đúng trạng thái từ REST.

---

## 4. Ràng buộc & quyết định kỹ thuật

- **Sử dụng Postgres LISTEN/NOTIFY**:
  - Worker publish event bằng `pg_notify(channel, payload_json)`.
  - API process mở connection riêng, `LISTEN channel`, và xử lý notification.
- **Không thêm table event riêng** trong Phase 5.1:
  - Event không cần persisted lâu dài, DB domain (`documents`, `parse_jobs`, …) vẫn là source of truth.
  - Nếu sau này cần audit event, có thể thêm bảng `event_log` ở phase khác.
- **Không thay đổi contract WebSocket**:
  - Event từ bridge phải giữ nguyên format như Phase 5.

---

## 5. Acceptance criteria

1. **Realtime từ parse_worker**:
   - Khi `parse_worker` xử lý xong một job thành công:
     - Client (đã kết nối `/ws`) nhận:
       - `job.status_updated` (`status='success'`, `retry_count` hiện tại).
       - `document.status_updated` (`status='parsed'`).
   - Khi job parse fail sau 3 lần retry:
     - Client nhận:
       - `job.status_updated` (`status='failed'`, kèm `error_message`).
       - `document.status_updated` (`status='error'`).

2. **Realtime từ ingest_worker**:
   - Khi ingest thành công:
     - Client nhận `document.status_updated` (`status='ingested'`) – dù ingest worker chạy ở process riêng.

3. **Không phá flow hiện tại**:
   - Nếu WebSocket / bridge tắt:
     - Upload + parse + ingest + chat vẫn chạy như Phase 5.
     - REST trả trạng thái chính xác từ DB.

4. **Multi-process**:
   - Khi API server khởi động trên port 8080 và worker chạy bằng `python -m server.app.workers.*`:
     - Event từ worker vẫn tới WebSocket client kết nối với API server.

---

## 6. Mở rộng tương lai (không thuộc Phase 5.1)

- Dùng Postgres event table để hỗ trợ:
  - Replay event cho client mới join.
  - Durability audit log.
- Tích hợp với Supabase Realtime (Postgres replication → client) thay vì tự viết LISTEN/NOTIFY.
- Dùng Redis hoặc message broker khác nếu hệ thống scale nhiều instance / nhiều service hơn.

