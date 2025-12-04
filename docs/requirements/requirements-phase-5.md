# rag-engine-phase-5 – Realtime & Worker Reliability

## 1. Mục tiêu Phase 5

- Bổ sung **lớp realtime** cho rag-engine (WebSocket), không dùng polling:
  - User gửi chat → UI thấy trạng thái `pending/running/done` và tự nhận kết quả.
  - Upload document → UI tự nhận event khi `parse → ingest → ready`, không cần F5.
- Thiết kế realtime theo kiểu **single source of truth**:
  - Mọi event đều phản ánh **state trong DB** (documents, jobs, messages).
  - Event được push theo **user** (Supabase user), mọi tab / màn hình của user đó đều nhận được.
- Nâng độ tin cậy cho worker:
  - Thêm **retry tối đa 3 lần** cho `parse_jobs` / `ingest_jobs`.
  - Worker có khả năng **tự “self-heal”**: quét job dang dở (stuck) khi start lại và đưa về trạng thái hợp lý để chạy tiếp.

> Ghi chú: Phase 5 **chưa** triển khai token streaming từng chunk như ChatGPT, nhưng kiến trúc WebSocket sẽ được thiết kế sao cho Phase sau có thể thêm streaming mà không phải đập lại.

---

## 2. Phạm vi & ưu tiên

### 2.1. Phạm vi bắt buộc

- **Realtime WebSocket cho user**:
  - Thiết kế một endpoint WebSocket riêng của rag-engine (vd `GET /ws` hoặc `/api/ws`).
  - Auth bằng Supabase JWT (giống HTTP), lấy được `user_id` gắn với connection.
  - Mỗi user có thể mở nhiều tab → server giữ danh sách connection theo `user_id`.
- **Realtime event cho các domain hiện tại**:
  - Chat:
    - Khi user gửi message, UI nhận được event tạo message và trạng thái xử lý RAG (tối thiểu: `pending` → `done`).
    - Khi message AI được tạo / cập nhật → gửi event cho user.
  - Document + jobs:
    - Khi tạo document mới → gửi event `document.created`.
    - Khi trạng thái document đổi (vd `pending → parsed → ingested/ready`) → gửi event `document.status_updated`.
    - Khi trạng thái job `parse_jobs` / `ingest_jobs` đổi (queued/running/success/failed) → gửi event `job.status_updated`.
- **Worker reliability**:
  - Thêm cơ chế retry cho parse/ingest:
    - Mỗi job có `retry_count`, `max_retries = 3`.
    - Nếu lỗi:
      - `retry_count < 3` → đặt lại về `queued` (có thể kèm `next_run_at` backoff).
      - `retry_count >= 3` → set `failed` và ghi `error_message`.
  - Khi worker khởi động:
    - Quét các job `status='running'` nhưng đã **quá lâu không cập nhật** (stale) → reset về `queued` + tăng `retry_count` (nếu còn quota).
    - Đảm bảo không có job bị kẹt vĩnh viễn ở trạng thái `running`.

### 2.2. Phạm vi không làm ở Phase 5 (đưa sang Phase sau)

- Token streaming từng chunk giống ChatGPT:
  - Phase 5 tập trung vào cập nhật realtime theo event, trả câu trả lời **full** sau khi RAG xong.
  - Streaming sẽ được thiết kế ở Phase sau dựa trên nền WebSocket này.
- Assistant UX nâng cao:
  - Gợi ý câu hỏi tiếp theo dựa trên answer.
  - Hành vi “no-context” thân thiện hơn (vd gợi ý upload thêm tài liệu).
  - Các tính năng này sẽ được thiết kế thành một Phase riêng (vd Phase 6).

---

## 3. Realtime API – mô hình tổng quan

- Thêm một endpoint WebSocket user-scoped, ví dụ:
  - `GET /ws?token=<Supabase JWT>` hoặc dùng header `Authorization`.
- Auth:
  - Backend verify JWT như request HTTP bình thường → lấy `user_id`.
  - Nếu token invalid/expired → từ chối kết nối.
- Quản lý connection:
  - Server giữ cấu trúc kiểu:
    - `connections[user_id] = list[WebSocketConnection]`.
  - Khi có event liên quan tới user nào, server gọi:
    - `send_to_user(user_id, event)` → gửi tới mọi tab của user đó.
- Format event thống nhất:

```jsonc
{
  "type": "document.status_updated",  // hoặc job.status_updated, message.created, ...
  "payload": {
    // nội dung tuỳ theo type
  }
}
```

- Không sử dụng polling giữa client và server cho các luồng:
  - Chat.
  - Documents / parse / ingest.

---

## 4. Realtime cho chat (conversations / messages)

### 4.1. Hành vi mong muốn

- Khi user gửi câu hỏi trong một conversation:
  - UI thấy ngay message của user xuất hiện (không phải chờ RAG).
  - UI biết message AI đang được xử lý (`pending` / “đang trả lời…”).
  - Khi RAG trả kết quả:
    - UI tự nhận event message AI `done` + nội dung trả lời.
    - Không cần F5 / call lại API list messages thủ công.
- Nếu user mở nhiều tab (hoặc ở màn hình conversation khác):
  - Tất cả tab của user đều nhận được event message tương ứng (đồng bộ state).

### 4.2. Trạng thái message

- Thêm trạng thái cho message AI (trong DB):
  - `status`: `pending | running | done | error`.
  - Phase 5 tối thiểu dùng:
    - `pending`: khi mới tạo message AI (đã commit DB nhưng chưa có nội dung).
    - `done`: sau khi RAG trả về answer và đã lưu nội dung.
- Message của user:
  - Có thể giữ `status` mặc định là `done` ngay khi insert (không cần trạng thái trung gian).

### 4.3. Luồng high-level (không streaming)

- HTTP endpoint chat hiện tại (`POST /conversations/{id}/messages`) vẫn là **sync**:
  - V1 Phase 5 không bắt buộc chuyển sang background job.
- Hành vi yêu cầu:
  - Khi nhận request:
    1. Lưu message `user`.
    2. Tạo record message `ai` với `status='pending'` (có thể chưa set content).
    3. Gửi event WebSocket:
       - `message.created` cho message user.
       - `message.created` hoặc `message.status_updated` cho message AI (pending).
    4. Gọi `RagEngineService.query(...)` như hiện tại.
    5. Khi có answer:
       - Cập nhật message AI: `content`, `metadata`, `status='done'`.
       - Gửi event `message.status_updated` (hoặc `message.updated`) cho user.
    6. Trả HTTP response (full answer) như hiện tại.
- Phase sau nếu cần:
  - Có thể tách bước 4–5 ra background worker và chỉ dùng WebSocket + polling nội bộ (không cần thay đổi event contract với client).

---

## 5. Realtime cho documents & jobs (parse / ingest)

### 5.1. Hành vi mong muốn

- Khi user upload document:
  - UI thấy document mới xuất hiện ngay (event `document.created`).
  - Khi document chuyển từ:
    - `pending` → `parsed` → `ingested/ready`:
      - UI tự update trạng thái theo event WebSocket.
      - Không phải tự polling `GET /documents`.
- Jobs:
  - Với mỗi `parse_jobs` / `ingest_jobs`:
    - Khi job chuyển `queued` → `running` → `success/failed`:
      - Nếu UI đang hiển thị chi tiết job (hoặc detail document), sẽ cập nhật theo event.

### 5.2. Mapping giữa DB state và event

- `documents`:
  - Khi tạo: gửi event:

```jsonc
{
  "type": "document.created",
  "payload": {
    "workspace_id": "...",
    "document": { /* schema document list item */ }
  }
}
```

  - Khi update trạng thái:

```jsonc
{
  "type": "document.status_updated",
  "payload": {
    "workspace_id": "...",
    "document_id": "...",
    "status": "parsed"
  }
}
```

- `parse_jobs` / `ingest_jobs`:

```jsonc
{
  "type": "job.status_updated",
  "payload": {
    "job_id": "...",
    "job_type": "parse" | "ingest",
    "document_id": "...",
    "workspace_id": "...",
    "status": "queued" | "running" | "success" | "failed",
    "retry_count": 0,
    "error_message": null
  }
}
```

### 5.3. Phân phối event theo user

- Mỗi document / job thuộc về một workspace.
- Mỗi workspace thuộc về một user (owner).
- Service WebSocket sẽ:
  - Khi cần gửi event cho workspace/document/job:
    - Query (hoặc đã có sẵn) `user_id` owner.
    - Gọi `send_to_user(user_id, event)`.
- Kết quả:
  - Dù user đang đứng ở màn hình nào (document list, workspace detail, chat…), mọi tab của user đó vẫn nhận được event realtime.

---

## 6. Worker: retry, wake-up & self-heal

### 6.1. Retry model cho parse/ingest

- Thêm field trong bảng jobs (hoặc bảng hiện có):
  - `retry_count` (INT, default 0).
  - Optional: `next_run_at` (TIMESTAMP, nullable) – để backoff.
- Logic retry:
  - Khi job lỗi:
    - Nếu `retry_count < 3`:
      - Tăng `retry_count += 1`.
      - Set `status='queued'`.
      - Optionally: set `next_run_at = now() + interval` (VD 1 phút).
      - Gửi event `job.status_updated`.
    - Nếu `retry_count >= 3`:
      - Set `status='failed'`.
      - Lưu `error_message` (truncate nếu cần).
      - Gửi event `job.status_updated`.

### 6.2. Vòng lặp worker & wake-up

- Worker parse / ingest vẫn chạy vòng lặp polling DB, nhưng:
  - **interval ngắn** (VD 2–5 giây) để giảm “thời gian chết”.
  - Với mỗi vòng lặp:
    - SELECT job `status='queued'` (và thỏa `next_run_at <= now()` nếu có).
    - Xử lý từng job (theo logic retry ở trên).
- Khi API tạo job mới:
  - Không cần cơ chế wake-up phức tạp:
    - Worker interval đủ ngắn để nhận job gần như ngay lập tức.
  - (Optional trong thiết kế): có thể bổ sung cơ chế “poke” nội bộ nếu sau này cần tối ưu.

### 6.3. Self-heal job dang dở

- Khi worker khởi động lại:
  - Quét các job `status='running'` có `updated_at` quá cũ (VD > 10 phút).
  - Với mỗi job:
    - Nếu `retry_count < 3`:
      - Tăng `retry_count += 1`.
      - Đặt lại `status='queued'` (để xử lý lại).
    - Nếu `retry_count >= 3`:
      - Đặt `status='failed'`.
  - Gửi event `job.status_updated` tương ứng cho user.
- Mục tiêu:
  - Đảm bảo không có job nằm mãi ở trạng thái `running` nếu worker/app từng crash.

---

## 7. Acceptance criteria & test flows

### 7.1. Chat realtime

- Case 1: User gửi câu hỏi trong conversation:
  - Trên UI:
    - Message user xuất hiện ngay (không F5).
    - Message AI xuất hiện với trạng thái `pending` (hoặc spinner).
    - Sau khi RAG trả lời:
      - Message AI đổi sang `done` + hiển thị full content.
  - Nếu mở thêm một tab khác của cùng user:
    - Tab thứ hai cũng thấy conversation cập nhật đồng bộ.

### 7.2. Document & job realtime

- Case 2: Upload document:
  - Sau upload:
    - Document mới xuất hiện trong list (event `document.created`).
    - `status` thay đổi tuần tự: `pending → parsed → ingested/ready` trên UI mà không cần reload.
  - Nếu parse hoặc ingest lỗi:
    - Job tương ứng hiển thị `failed` sau tối đa 3 lần retry.
    - Document có trạng thái phù hợp (`error` hoặc giữ `parsed`, tuỳ thiết kế chi tiết).

### 7.3. Worker retry & self-heal

- Case 3: Worker bị lỗi giữa chừng:
  - Dừng worker giữa lúc job `parse` đang `running`.
  - Start lại worker:
    - Job `running` được phát hiện là stale.
    - Được đưa về `queued` (nếu còn quota retry) hoặc `failed` (nếu hết quota).
    - Event `job.status_updated` được push.

---

## 8. Ghi chú triển khai

- Phase 5 **chỉ** thiết kế & triển khai trên backend `rag-engine`:
  - WebSocket server (FastAPI).
  - Event push từ API routes và worker.
  - Thay đổi nhỏ schema jobs (retry_count, next_run_at nếu cần).
- Client/UI:
  - Sẽ được cập nhật trong phase riêng (hoặc phần client-phase tương ứng) để:
    - Kết nối `/ws`.
    - Subscribe các event theo type.
    - Cập nhật state UI theo event thay vì polling.

