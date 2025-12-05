# phase-5-design – Realtime WebSocket & Worker Reliability

Mục tiêu: thiết kế chi tiết cách thêm WebSocket realtime cho rag-engine (chat + document/job status) và nâng độ tin cậy worker (retry, self-heal) theo đúng requirements Phase 5.

---

## 1. Tổng quan kiến trúc

- Bổ sung một **Realtime layer** trong server:
  - Dựa trên WebSocket của FastAPI/Starlette (không dùng Supabase Realtime).
  - Mỗi connection gắn với `user_id` (Supabase).
  - Các service/API/worker có thể gửi event tới user thông qua một `RealtimeGateway` chung.
- Không thay đổi high-level kiến trúc:
  - API layer: `server/app/api/routes/` – thêm endpoint WebSocket.
  - Services: `server/app/services/` – chỉ gọi `RealtimeGateway` khi state DB thay đổi.
  - Workers: `server/app/workers/` – dùng lại service để gửi event (hoặc gọi gateway trực tiếp nếu cần, nhưng vẫn qua abstraction).

---

## 2. WebSocket endpoint & Connection Manager

### 2.1. Vị trí & interface

- Thêm file mới (gợi ý):
  - `server/app/api/routes/realtime.py`
- Endpoint:

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    current_user: CurrentUser = Depends(get_current_user_ws),
):
    ...
```

- `get_current_user_ws`:
  - Tương tự `get_current_user` trong `core/security.py` nhưng dùng được với WebSocket:
    - Đọc token từ query param `token` hoặc header.
    - Validate Supabase JWT.
    - Trả về object `CurrentUser` có `id`, `email`, ...

### 2.2. ConnectionManager / RealtimeGateway

- Thêm module:
  - `server/app/core/realtime.py`

```python
class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(user_id, []).append(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        conns = self._connections.get(user_id)
        if not conns:
            return
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, message: dict) -> None:
        conns = self._connections.get(user_id, [])
        for ws in list(conns):
            try:
                await ws.send_json(message)
            except Exception:
                # nếu gửi lỗi, đóng và remove connection
                try:
                    await ws.close()
                except Exception:
                    pass
                self.disconnect(user_id, ws)
```

- Để dễ sử dụng ở mọi nơi, bọc `ConnectionManager` trong một gateway dạng singleton:

```python
class RealtimeGateway:
    def __init__(self, manager: ConnectionManager) -> None:
        self._manager = manager

    async def send_event_to_user(self, user_id: str, event_type: str, payload: dict) -> None:
        await self._manager.send_to_user(
            user_id,
            {"type": event_type, "payload": payload},
        )
```

- Khởi tạo singleton trong `server/app/main.py` (hoặc module `core/realtime.py`) và inject vào services/worker thông qua dependency injection (hoặc import singleton nếu muốn đơn giản V1, chấp nhận chạy 1 process).

### 2.3. Vòng đời WebSocket

- Trong `websocket_endpoint`:

```python
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, current_user: CurrentUser = Depends(get_current_user_ws)):
    user_id = current_user.id
    await realtime_manager.connect(user_id, websocket)
    try:
        while True:
            # Hiện tại server không yêu cầu client gửi message nào cụ thể
            # Có thể đọc ping/keep-alive hoặc bỏ qua (receive_text() / receive_json()).
            await websocket.receive_text()
    except WebSocketDisconnect:
        realtime_manager.disconnect(user_id, websocket)
```

- V1: server không xử lý message từ client qua WebSocket (thuần push), mọi interaction chính vẫn là HTTP.
  - Sau này nếu cần, có thể mở rộng để client gửi command (vd subscribe theo workspace, filter, ping).

---

## 3. Event model & contract

### 3.1. Định dạng chuẩn

- Mọi event gửi qua WebSocket có dạng:

```jsonc
{
  "type": "document.status_updated",
  "payload": {
    // tuỳ theo event
  }
}
```

- Các `type` chính Phase 5:
  - `document.created`
  - `document.status_updated`
  - `job.status_updated`
  - `message.created`
  - `message.status_updated`

### 3.2. Mapping với domain hiện tại

- `document.*`:
  - Trigger từ:
    - API upload document / API thay đổi status.
    - Worker parse / ingest sau khi update `documents.status`.
  - Payload tối thiểu:

```jsonc
// document.created
{
  "workspace_id": "uuid",
  "document": {
    "id": "uuid",
    "title": "string",
    "status": "pending|parsed|ingested|error",
    "source_type": "upload|web|...",
    ...
  }
}

// document.status_updated
{
  "workspace_id": "uuid",
  "document_id": "uuid",
  "status": "pending|parsed|ingested|error"
}
```

- `job.status_updated`:
  - Trigger từ worker parse / ingest mỗi khi job đổi trạng thái.
  - Payload:

```jsonc
{
  "job_id": "uuid",
  "job_type": "parse" | "ingest",
  "workspace_id": "uuid",
  "document_id": "uuid",
  "status": "queued" | "running" | "success" | "failed",
  "retry_count": 0,
  "error_message": null
}
```

- `message.*`:
  - Trigger từ API `POST /conversations/{id}/messages` khi:
    - Tạo message user.
    - Tạo/cập nhật message AI.

```jsonc
// message.created
{
  "conversation_id": "uuid",
  "workspace_id": "uuid",
  "message": {
    "id": "uuid",
    "role": "user|ai",
    "content": "string",
    "status": "done|pending|running|error",
    "created_at": "ISO8601",
    ...
  }
}

// message.status_updated
{
  "conversation_id": "uuid",
  "workspace_id": "uuid",
  "message_id": "uuid",
  "status": "pending|running|done|error"
}
```

### 3.3. Phân phối event theo user

- Mỗi workspace/document/conversation thuộc về một `user_id`.
- RealtimeGateway sẽ có helper:

```python
class RealtimeService:
    def __init__(self, gateway: RealtimeGateway, repositories: ...) -> None:
        ...

    async def notify_document_status(self, workspace_id: str, document_id: str, status: str) -> None:
        user_id = await self._repos.get_workspace_owner_id(workspace_id)
        if not user_id:
            return
        await self._gateway.send_event_to_user(
            user_id,
            "document.status_updated",
            {"workspace_id": workspace_id, "document_id": document_id, "status": status},
        )
```

- Các API / worker không cần biết chi tiết WebSocket, chỉ gọi service ở mức `notify_*`.

---

## 4. Thay đổi ở layer API (chat / documents)

### 4.1. Chat – POST /conversations/{conversation_id}/messages

- File: `server/app/api/routes/messages.py`
- Luồng thiết kế:
  - Sau khi lưu message user:
    - Gửi event `message.created` cho user message.
  - Tạo message AI với `status='pending'` (content rỗng) để làm placeholder:
    - Gửi event `message.created` cho AI pending.
  - Việc gọi RAG có thể:
    - **(Hiện tại)** chạy trong background task (non-blocking HTTP).
    - Hoặc synchronous trong route (về mặt thiết kế, Phase 5 chấp nhận cả hai).
  - Khi RAG trả answer:
    - Cập nhật `content`, `metadata.citations`, `status='done'`.
    - Gửi event `message.status_updated` cho message AI.

Pseudo-code cho implementation **hiện tại** (non-blocking):

```python
async def create_message(...):
    # 1) create user message (done)
    user_msg = await messages_repo.create_user_message(...)
    await realtime_service.notify_message_created(user_msg)

    # 2) create AI message placeholder (pending)
    ai_msg = await messages_repo.create_ai_message(conversation_id, status="pending", content="")
    await realtime_service.notify_message_created(ai_msg)

    # 3) schedule background RAG processing (không block HTTP)
    background_tasks.add_task(
        process_ai_message_background,
        ai_message_id=ai_msg.id,
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        user_id=current_user.id,
        question=body.content,
    )

    # 4) HTTP response trả về ngay cả user_msg và ai_msg (pending)
    return MessageListResponse(items=[user_msg, ai_msg])


async def process_ai_message_background(...):
    rag_result = await rag_engine.query(...)
    # update AI message → done / error
    await messages_repo.update_ai_message(...)
    await realtime_service.notify_message_status_updated(...)
```

> Lưu ý: WebSocket contract (`message.created`, `message.status_updated`) giữ nguyên; Phase 5 chỉ thay đổi “thời điểm” xử lý RAG sang background để API response nhanh hơn.

### 4.2. Documents – upload / status update

- File: `server/app/api/routes/documents.py`
- Sau khi tạo document trong DB (upload xong):
  - Gọi `RealtimeService.notify_document_created(workspace_id, document)` → push `document.created`.
- Các chỗ update `documents.status`:
  - Thường nằm trong worker, nhưng nếu có chỗ update từ API thì cũng nên gọi `notify_document_status(...)`.

---

## 5. Worker design – retry & self-heal

### 5.1. Thay đổi schema jobs

- Bổ sung field:
  - `retry_count` INT NOT NULL DEFAULT 0.
  - Optional: `next_run_at` TIMESTAMPTZ NULL.
- Cập nhật repositories tương ứng để đọc/ghi các field này khi xử lý jobs.

### 5.2. Vòng lặp parse_worker / ingest_worker

- File: `server/app/workers/parse_worker.py`, `server/app/workers/ingest_worker.py`
- Pseudo-code vòng lặp:

```python
while True:
    jobs = await jobs_repo.fetch_queued_jobs(batch_size=..., now=utcnow())
    if not jobs:
        await asyncio.sleep(settings.worker_sleep_seconds)  # vd 2–5s
        continue

    for job in jobs:
        await process_single_job(job)
```

Trong đó:

```python
async def process_single_job(job):
    try:
        await jobs_repo.mark_running(job.id)
        await realtime_service.notify_job_status(job, status="running")

        # thực thi parse/ingest thực tế
        await pipeline.run(job)

        await jobs_repo.mark_success(job.id)
        await realtime_service.notify_job_status(job, status="success")
    except Exception as exc:
        await handle_job_failure(job, exc)
```

`handle_job_failure`:

```python
async def handle_job_failure(job, exc):
    if job.retry_count < settings.max_retries:
        await jobs_repo.requeue(job.id, retry_count=job.retry_count + 1)
        await realtime_service.notify_job_status(job, status="queued")
    else:
        await jobs_repo.mark_failed(job.id, error=str(exc))
        await realtime_service.notify_job_status(job, status="failed", error_message=str(exc))
```

### 5.3. Self-heal khi worker start

- Khi worker start (lúc `main()`):

```python
async def heal_stuck_jobs():
    stale_jobs = await jobs_repo.fetch_stale_running_jobs(
        older_than=settings.job_stale_threshold,  # vd 10 phút
    )
    for job in stale_jobs:
        if job.retry_count < settings.max_retries:
            await jobs_repo.requeue(job.id, retry_count=job.retry_count + 1)
            await realtime_service.notify_job_status(job, status="queued")
        else:
            await jobs_repo.mark_failed(job.id, error="stale-running")
            await realtime_service.notify_job_status(job, status="failed", error_message="stale-running")
```

- Gọi `heal_stuck_jobs()` một lần trước khi vào vòng lặp chính.

---

## 6. Security & deployment considerations

- Auth WebSocket:
  - `get_current_user_ws` phải kiểm tra JWT giống HTTP route:
    - Verify signature với `SUPABASE_JWT_SECRET` hoặc JWKS.
    - Kiểm tra expiry.
  - Nếu fail → đóng kết nối, không chấp nhận WebSocket.
- Phân quyền event:
  - `RealtimeService` luôn tra `user_id` owner từ DB (workspace/conversation/document) trước khi gửi event.
  - Không bao giờ broadcast event theo workspace_id mà không check owner.
- Deployment:
  - Thiết kế hiện tại giả định **single process** của API giữ state `ConnectionManager`:
    - Dev / môi trường đơn giản: ok.
    - Nếu production scale nhiều instance:
      - Cần thêm layer pub/sub (Redis, Postgres NOTIFY, Supabase Realtime, ...) để fan-out event giữa các instance.
      - Điều này nằm ngoài phạm vi Phase 5 (có thể bổ sung trong Phase sau).

---

## 7. Kế hoạch triển khai (backend-only)

1. **Infra WebSocket & realtime core**
   - Tạo `core/realtime.py` (ConnectionManager + RealtimeGateway).
   - Thêm WebSocket endpoint `/ws` trong `api/routes/realtime.py`.
   - Implement `get_current_user_ws` trong `core/security.py`.
2. **RealtimeService & hooks**
   - Tạo `services/realtime_service.py` hoặc gộp vào service hiện có:
     - Hàm `notify_document_created`, `notify_document_status`, `notify_job_status`, `notify_message_created`, `notify_message_status_updated`.
   - Thêm gọi `RealtimeService` vào:
     - `messages.create_message` (API chat).
     - Upload document + chỗ update `documents.status` (nếu trong API).
3. **Worker updates**
   - Cập nhật schema jobs (retry_count, next_run_at).
   - Cập nhật `parse_worker.py` và `ingest_worker.py`:
     - Vòng lặp dùng retry & heal logic.
     - Gửi event job status.
4. **Test flows**
   - Manual test với 2 tab cùng user:
     - Upload document, quan sát state.
     - Gửi message chat, quan sát message user/AI realtime.
   - Simulate error trong worker để kiểm tra retry/self-heal & event.

Phase 5 không yêu cầu thay đổi UI ngay trong repo này, nhưng thiết kế trên đảm bảo client có thể xây dựng phần realtime một cách đơn giản, dựa trên WebSocket `/ws` và event model thống nhất.
