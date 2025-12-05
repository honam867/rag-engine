# rag-engine-phase-6 – Redis Event Bus & Worker Wake-up

## 1. Mục tiêu Phase 6

- Giải quyết triệt để vấn đề realtime cross-process khi **không thể dùng Postgres LISTEN/NOTIFY** do hạn chế hạ tầng (Supabase Transaction/Session Pooler, IPv4, v.v.).
- Thay thế lớp Event Bus dựa trên Postgres hiện tại bằng **Redis-based Event Bus**:
  - Worker (parse / ingest) publish event lên Redis.
  - API process subscribe Redis và forward event sang WebSocket `/ws`.
- Đảm bảo **parse_worker được wake-up gần như tức thì** khi có `parse_job` mới, mà không phụ thuộc vào polling 5s như hiện tại.
- Giữ nguyên:
  - 1 API process (uvicorn).
  - 2 worker process: `parse_worker`, `ingest_worker`.
  - WebSocket contract & business logic đã xây dựng ở các phase trước.

> Phase 6 **tập trung vào hạ tầng realtime** (event bus + wake-up), không mở rộng thêm business domain mới.

---

## 2. Phạm vi & nguyên tắc

### 2.1. Phạm vi Phase 6

- Backend `rag-engine`:
  - Thêm Redis như một tầng Event Bus trung gian giữa:
    - API ↔ parse_worker ↔ ingest_worker.
  - Thay thế mọi logic dựa trên Postgres LISTEN/NOTIFY được thêm ở Phase 5.1.
- Không thay đổi:
  - REST API contract (Phase 1–4, 5).
  - WebSocket `/ws` contract (event `type` + `payload` đã define ở Phase 5).
  - DB schema (`parse_jobs`, `documents`, `rag_documents`, `messages`, …).

### 2.2. Nguyên tắc thiết kế

- **Redis làm Event Bus**, không thay thế Postgres:
  - Postgres vẫn là **single source of truth** cho state (documents, jobs, messages).
  - Redis chỉ dùng để:
    - Push realtime event cross-process (worker → API → WebSocket).
    - Wake-up worker khi có job mới.
- **Best-effort realtime**:
  - Nếu Redis tạm thời down hoặc unreachable:
    - Business flow (upload, parse, ingest, chat) vẫn chạy qua Postgres.
    - Worker vẫn có polling fallback (idle sleep nhỏ hơn, ví dụ 1–2s).
    - Client vẫn có thể sync state qua REST nếu cần.
- **Không thêm requirement monitoring phức tạp**:
  - Chỉ log lỗi/exception (như hiện tại) khi publish/subscribe gặp lỗi.
  - Không yêu cầu metrics/phân tích sâu.

---

## 3. Dọn dẹp Phase 5.1 – Những gì cần remove / thay thế

Phase 6 phải **loại bỏ hoặc vô hiệu hóa** các phần dưới đây (được thêm ở Phase 5.1) để tránh trùng logic:

1. Event Bus dựa trên Postgres:
   - `server/app/core/event_bus.py`:
     - `EventBus.publish(...)` dùng `pg_notify('rag_realtime', ...)`.
     - `listen_realtime_events()` dùng asyncpg + `LISTEN rag_realtime`.
     - `notify_parse_job_created(...)` dùng `pg_notify('parse_jobs', ...)`.
2. Parse worker wake-up bằng Postgres NOTIFY:
   - `server/app/workers/parse_worker.py`:
     - Hàm `listen_parse_jobs_notifications(...)` dùng asyncpg + `LISTEN parse_jobs`.
     - Phần logic `wakeup_event` gắn với channel `parse_jobs`.
3. Mọi chỗ gọi `notify_parse_job_created(...)`:
   - Ví dụ trong API upload documents.

> Sau Phase 6, mọi bridge realtime cross-process **phải đi qua Redis**, không còn phụ thuộc vào Postgres NOTIFY.

---

## 4. Use cases chính (không đổi về mặt business)

1. **Parse (Document AI) hoàn tất ở parse_worker**:
   - Khi parse thành công:
     - `documents.status` đổi sang `parsed`.
     - `parse_jobs.status` đổi sang `success`.
   - Client:
     - Nhận được `job.status_updated` + `document.status_updated` **qua WebSocket**.
2. **Ingest RAG hoàn tất ở ingest_worker**:
   - Khi ingest thành công:
     - `documents.status` đổi sang `ingested`.
   - Client:
     - Nhận được `document.status_updated (ingested)` qua WebSocket.
3. **Wake-up parse_worker khi có parse_job mới**:
   - Khi API tạo parse_job (upload document):
     - parse_worker được đánh thức **gần như ngay** (thay vì chờ idle sleep 5s).
4. **Multi-tab / multi-screen cho cùng user**:
   - Mọi tab/màn hình của cùng `user_id` vẫn nhận được event như Phase 5.

---

## 5. Kiến trúc Redis Event Bus (mức yêu cầu)

> Chi tiết kỹ thuật sẽ được mô tả ở `docs/design/phase-6-design.md`. Phần này chỉ đặt requirement tổng.

### 5.1. Channels & message format

- Redis channels (tối thiểu):
  1. `rag_realtime`:
     - Dùng để worker publish các event mà cuối cùng sẽ đi ra WebSocket.
     - Payload JSON **giữ nguyên** format Phase 5.1:
       ```jsonc
       {
         "user_id": "uuid",
         "type": "document.status_updated", // hoặc job.status_updated, message.created, ...
         "payload": { "...": "..." }
       }
       ```
  2. `parse_jobs` (wake-up):
     - Dùng để API thông báo cho parse_worker biết có job mới (hoặc dùng queue, tuỳ design).
     - Payload không phải source-of-truth, chỉ là hint:
       ```jsonc
       {
         "document_id": "uuid",
         "job_id": "uuid"
       }
       ```

### 5.2. Vai trò các process

- API process:
  - **Publisher**:
    - Có thể publish một số event trực tiếp lên Redis (nếu cần unify API/worker).
  - **Subscriber**:
    - Subscribe channel `rag_realtime`.
    - Với mỗi message: gọi `send_event_to_user(user_id, type, payload)` để đẩy sang WebSocket.
- parse_worker:
  - **Subscriber / Consumer**:
    - Lắng nghe channel/queue `parse_jobs` để wake-up khi có parse_job mới.
  - **Publisher**:
    - Sau khi update DB (`parse_jobs`, `documents`), publish event lên `rag_realtime`.
- ingest_worker:
  - **Publisher**:
    - Sau khi ingest thành công, update DB xong, publish `document.status_updated` lên `rag_realtime`.

---

## 6. Env & config yêu cầu

- Bổ sung env cho Redis (tên gợi ý):
  - `REDIS_URL=redis://localhost:6379/0` (hoặc URL do hạ tầng cung cấp).
- Yêu cầu:
  - API + 2 worker đều dùng được cùng một `REDIS_URL`.
  - Timeout/phục hồi:
    - Nếu connect Redis thất bại, code:
      - Log warning/error (như hiện tại).
      - Retry sau một khoảng ngắn (VD 5s).
      - Không crash toàn bộ process chỉ vì Redis.

---

## 7. Acceptance criteria

1. **Bridge worker → WebSocket qua Redis hoạt động ổn định**:
   - Khi parse_worker/ingest_worker publish event:
     - API nhận được message từ Redis.
     - WebSocket client (đã connect `/ws`) nhận được event với `type` + `payload` đúng contract Phase 5.
2. **Wake-up parse_worker cải thiện latency**:
   - Trong điều kiện Redis hoạt động:
     - Khoảng thời gian giữa lúc API tạo parse_job và lúc parse_worker bắt đầu xử lý job:
       - Ngắn hơn rõ rệt so với polling 5s (target: ~0–1s khi worker idle).
3. **Fallback khi Redis gặp sự cố**:
   - Nếu Redis down:
     - parse_worker vẫn xử lý job nhờ polling (idle sleep có thể là 1–2s).
     - API/worker vẫn update DB bình thường.
     - WebSocket realtime có thể mất event, nhưng client vẫn đồng bộ lại được thông qua REST.
4. **Dọn dẹp Phase 5.1**:
   - Không còn đoạn code nào trong server sử dụng Postgres `LISTEN/NOTIFY` cho realtime.
   - Mọi publish/subscribe cross-process đều đi qua Redis.

---

## 8. Không làm ở Phase 6

- Không thêm tính năng streaming token (ChatGPT-style) – để phase riêng.
- Không thêm logic assistant nâng cao (gợi ý câu hỏi tiếp theo, v.v.).
- Không thêm dashboard monitoring cho Redis (metrics, UI). Chỉ log text như hiện tại là đủ.

Phase 6 chỉ tập trung:
- Thay hạ tầng Event Bus từ Postgres sang Redis.
- Đảm bảo parse_worker được wake-up nhanh và event từ worker tới WebSocket client hoạt động tốt trong bối cảnh hạ tầng Supabase hiện tại.

