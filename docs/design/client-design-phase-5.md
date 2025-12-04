# client-design-phase-5 – Realtime WebSocket (Summary for Frontend)

Mục tiêu: mô tả **những thứ cần biết** cho team client để lắp Phase 5 vào UI (Next.js) – không đi vào chi tiết cách code.

File này bổ sung trên nền `client-design.md` và `phase-1-client-design.md`.

---

## 1. Phạm vi cho client

- Kết nối WebSocket tới backend để nhận **realtime event**:
  - Trạng thái documents (upload → parsed → ingested/ready).
  - Trạng thái jobs (parse / ingest).
  - Trạng thái chat messages (message user / message AI pending/done).
- Dùng event để:
  - Cập nhật UI mà **không cần polling** (hoặc giảm polling).
  - Đồng bộ nhiều tab của cùng một user.

Không thay đổi:

- API REST hiện tại (React Query vẫn fetch/list như cũ).
- Luồng auth Supabase (vẫn dùng JWT để gọi backend).

---

## 2. Backend contract – những gì client cần biết

### 2.1. WebSocket endpoint

- Đường dẫn: `GET /ws`.
- Auth:
  - Truyền Supabase JWT (access token) khi connect:
    - Cách đơn giản: query param `?token=<JWT>` (tùy backend implement final).
  - Backend sẽ validate token giống HTTP API.

=> Client chỉ cần: **lấy JWT hiện đang dùng cho REST** và dùng lại khi mở WebSocket.

### 2.2. Cấu trúc event chung

- Mọi message server gửi đều có dạng:

```jsonc
{
  "type": "<domain>.<action>",
  "payload": { ... }
}
```

- `type` là string, ví dụ:
  - `document.created`
  - `document.status_updated`
  - `job.status_updated`
  - `message.created`
  - `message.status_updated`

### 2.3. Các loại event & field quan trọng

1) **Document**

- `document.created`
  - Cho biết có document mới trong một workspace.
  - Payload tối thiểu:
    - `workspace_id`
    - `document` (object giống item trong `GET /workspaces/{id}/documents`)
- `document.status_updated`
  - Cho biết document đổi trạng thái.
  - Payload tối thiểu:
    - `workspace_id`
    - `document_id`
    - `status` (`pending | parsed | ingested | error`)

2) **Jobs (parse / ingest)**

- `job.status_updated`
  - Cho biết job parse/ingest đang queued/running/success/failed.
  - Payload tối thiểu:
    - `job_id`
    - `job_type` (`parse | ingest`)
    - `workspace_id`
    - `document_id`
    - `status` (`queued | running | success | failed`)
    - `retry_count`
    - `error_message` (có thể null)

3) **Messages (chat)**

- `message.created`
  - Gửi cho cả message user và message AI khi được tạo.
  - Payload tối thiểu:
    - `workspace_id`
    - `conversation_id`
    - `message`:
      - `id`
      - `role` (`user | ai`)
      - `content`
      - `status` (`pending | running | done | error`)
      - `created_at`
- `message.status_updated`
  - Cho biết message AI đổi trạng thái (ví dụ từ `pending` → `done`).
  - Payload tối thiểu:
    - `workspace_id`
    - `conversation_id`
    - `message_id`
    - `status`

---

## 3. Gợi ý tích hợp vào client hiện tại

Phần này chỉ nói **nên gắn ở đâu**, không hướng dẫn chi tiết cách code.

### 3.1. Vị trí WebSocket trong app

- Nên có **một** WebSocket connection global cho mỗi user (không mở mỗi màn hình một cái), ví dụ:
  - Trong `AppProviders` hoặc một provider tương đương.
- Sau khi:
  - Lấy được JWT từ Supabase (hoặc dev token),
  - App có thể mở connection `/ws?token=<JWT>`.

### 3.2. Cách dùng event với React Query / state

- Documents:
  - Khi nhận `document.created`:
    - Thêm document mới vào danh sách documents của workspace tương ứng, hoặc invalidate query list.
  - Khi nhận `document.status_updated`:
    - Cập nhật field `status` của document trong list.
- Messages:
  - Khi nhận `message.created`:
    - Append message vào list messages của `conversation_id` tương ứng.
  - Khi nhận `message.status_updated`:
    - Cập nhật `status` của message AI (để UI show spinner/pending hoặc done).
- Jobs:
  - Nếu có UI hiển thị job detail/progress:
    - Dùng `job.status_updated` để update trạng thái (Queued/Running/Success/Failed).
  - Nếu chưa có UI riêng cho jobs:
    - Có thể bỏ qua event này ở phía client.

### 3.3. Ứng xử khi không có WebSocket

- App vẫn phải hoạt động được với REST như hiện tại:
  - WebSocket chỉ là **nâng UX**, không phải hard dependency.
  - Nếu WebSocket fail/error:
    - Có thể fallback nhẹ bằng polling (tùy quyết định team client).

---

## 4. Checklist ngắn cho team client

Khi implement Phase 5 trên client, chỉ cần đảm bảo:

- Biết cách **lấy JWT** (Supabase access token) và dùng để:
  - Gọi REST (đã có).
  - Mở WebSocket `/ws?token=<JWT>`.
- Lắng nghe message dạng:
  - `{ "type": "document.created", "payload": { ... } }`
  - `{ "type": "document.status_updated", "payload": { ... } }`
  - `{ "type": "job.status_updated", "payload": { ... } }`
  - `{ "type": "message.created", "payload": { ... } }`
  - `{ "type": "message.status_updated", "payload": { ... } }`
- Map các event này vào:
  - List documents theo workspace (status hiển thị realtime).
  - List messages theo conversation (message user/AI + trạng thái pending/done).
  - (Optional) UI job/progress nếu có.

Chỉ cần backend giữ đúng contract trên, phía client có thể chủ động chọn pattern (React Query, Zustand, Redux, v.v.) để cập nhật state mà không phụ thuộc chi tiết implement của server.

