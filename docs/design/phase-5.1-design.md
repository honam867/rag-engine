# phase-5.1-design – Cross-Process Event Bridge via Postgres

Mục tiêu: thiết kế cơ chế để **worker processes** (parse_worker, ingest_worker) có thể phát realtime event tới WebSocket client đang kết nối vào API process, sử dụng chính Supabase Postgres làm bridge.

---

## 1. Kiến trúc tổng thể

- Thêm một lớp **Event Bus** dựa trên Postgres LISTEN/NOTIFY:
  - Worker: publish event → `pg_notify('rag_realtime', <json payload>)`.
  - API process: có một task background `listen_realtime_events`:
    - `LISTEN rag_realtime`.
    - Khi có notification → parse JSON → gọi `send_event_to_user(user_id, type, payload)` (từ `core/realtime.py`).

Sơ đồ:

```text
parse_worker / ingest_worker
  |  (publish)
  v
Postgres (LISTEN/NOTIFY, channel rag_realtime)
  ^  (listen)
  |
API process (FastAPI + WebSocket)
  |-- send_event_to_user --> ConnectionManager --> WebSocket clients
```

---

## 2. Event envelope & channel

### 2.1. Channel

- Dùng một channel chung:
  - Tên: `rag_realtime`.
- Tất cả worker publish vào channel này:
  - Không cần channel riêng cho parse/ingest; phân biệt bằng `type` trong payload.

### 2.2. Payload JSON

- Định dạng payload JSON thống nhất:

```jsonc
{
  "user_id": "uuid",              // Supabase user id nhận event
  "type": "document.status_updated",  // hoặc job.status_updated, message.created, ...
  "payload": {                    // đúng contract WebSocket hiện tại
    "...": "..."
  }
}
```

- `type` + `payload` sẽ được forward y nguyên sang WebSocket.

---

## 3. Event Bus abstraction

### 3.1. Module & interface

- Thêm module: `server/app/core/event_bus.py`

Interface gợi ý:

```python
from typing import Any, Dict


class EventBus:
    def __init__(self, channel: str = "rag_realtime") -> None:
        self._channel = channel

    async def publish(self, user_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        ...
```

- Triển khai `publish`:
  - Dùng SQLAlchemy async engine hoặc asyncpg để chạy:

```sql
SELECT pg_notify(:channel, :payload_json);
```

  - Payload là `json.dumps({"user_id": user_id, "type": event_type, "payload": payload})`.
- V1: Mỗi lần publish có thể mở 1 connection ngắn (qua `engine.begin()`), performance ok vì số event thấp và payload nhỏ.
  - Nếu sau này cần tối ưu, có thể thêm connection pool riêng.

### 3.2. Sử dụng trong worker

- Thay vì gọi trực tiếp `send_event_to_user` trong worker, dùng EventBus:

```python
from server.app.core.event_bus import EventBus

event_bus = EventBus()

await event_bus.publish(
    user_id=owner_id,
    event_type="document.status_updated",
    payload={
        "workspace_id": workspace_id,
        "document_id": document_id,
        "status": "parsed",
    },
)
```

- Điều này đảm bảo:
  - Worker không cần biết WebSocket hay ConnectionManager.
  - Chỉ cần DB (đã có).

---

## 4. Listener trong API process

### 4.1. Listener task

- Thêm một background task trong API server:
  - Khởi tạo ở `server/app/main.py` trong event `startup`.
  - Sử dụng `asyncpg` trực tiếp (hoặc SQLAlchemy connection raw) để:
    - Connect đến `SUPABASE_DB_URL`.
    - Thực hiện `LISTEN rag_realtime`.
    - Vòng lặp:

```python
async def listen_realtime_events():
    conn = await asyncpg.connect(dsn=SUPABASE_DB_URL, **connect_args)
    await conn.add_listener("rag_realtime", handle_notification)
    # giữ connection sống; asyncpg sẽ gọi callback khi có NOTIFY
    while True:
        await asyncio.sleep(3600)
```

- `handle_notification`:

```python
import json
from server.app.core.realtime import send_event_to_user

def _handle_notification(connection, pid, channel, payload: str):
    # callback sync -> sẽ cần wrap sang asyncio.ensure_future
    data = json.loads(payload)
    user_id = data.get("user_id")
    event_type = data.get("type")
    event_payload = data.get("payload")
    if not user_id or not event_type:
        return
    asyncio.get_event_loop().create_task(
        send_event_to_user(user_id, event_type, event_payload)
    )
```

- Cần đảm bảo:
  - Dùng cùng `connect_args` như engine chính (tắt prepared statements, v.v.) để tương thích Supabase Pooler.
  - Có retry/reconnect khi connection tới DB bị mất.

### 4.2. Startup wiring

- Trong `server/app/main.py`:

```python
@app.on_event("startup")
async def startup() -> None:
    ...
    # start listener
    asyncio.create_task(listen_realtime_events())
```

- V1: không cần shutdown logic quá phức tạp; khi process dừng, connection sẽ được đóng.

---

## 5. Tích hợp với worker hiện tại

### 5.1. parse_worker / ParserPipelineService

- Hiện tại đã gọi `send_event_to_user` trực tiếp trong:
  - `ParserPipelineService.process_single_job` (khi job `running/success/failed`, document `parsed/error`).
- Phase 5.1 thay đổi:
  - Tách logic emit ra khỏi service:
    - Trong worker, dùng `EventBus.publish(...)` với:
      - `user_id` = owner của workspace (lấy bằng `get_workspace_owner_id` như hiện tại).
      - `event_type` = `job.status_updated` / `document.status_updated`.
      - `payload` giống contract Phase 5.
  - Trong API (listener), nhận NOTIFY và forward sang ConnectionManager như WebSocket event.
- Optional: các event từ API process (như `document.created`, `message.created`) có thể vẫn gọi `send_event_to_user` trực tiếp (không bắt buộc phải đi qua Postgres) vì chúng đã ở đúng process.

### 5.2. ingest_worker / IngestJobService

- Tương tự:
  - Thay `send_event_to_user` trong `jobs_ingest.py` bằng `EventBus.publish(...)` khi document được ingest thành công:
    - `event_type="document.status_updated"`
    - `payload={"workspace_id": ..., "document_id": ..., "status": "ingested"}`.

---

## 6. Behaviour & fallback

### 6.1. Khi mọi thứ bình thường

- Flow parse:
  - Worker:
    - Update DB (documents, parse_jobs).
    - `EventBus.publish` → `pg_notify`.
  - API:
    - Listener nhận notification → `send_event_to_user`.
  - Client:
    - WebSocket nhận `job.status_updated` / `document.status_updated`.

### 6.2. Khi API process tắt / không listen

- Worker vẫn publish `pg_notify`, nhưng không ai LISTEN:
  - Notification bị mất (LISTEN/NOTIFY không queue).
  - DB vẫn chứa trạng thái cuối cùng (parsed/ingested/error).
- Khi API lên lại:
  - Client sync lại trạng thái qua REST (React Query).
  - Realtime tiếp tục cho các event mới.

### 6.3. Khi worker tắt

- Không ảnh hưởng WebSocket layer.
- Tình trạng parse/ingest không đổi so với hiện tại (Phase 5).

---

## 7. Notes / TODO

- **An toàn & bảo mật:**
  - Payload nội bộ (worker → DB → API) không expose trực tiếp ra ngoài; chỉ đi trong hạ tầng backend.
  - `user_id` được tra từ DB (owner workspace) như hiện tại.
- **Performance:**
  - Số lượng event parse/ingest không quá lớn, nên overhead `pg_notify` + listener là chấp nhận được.
  - Nếu về sau số lượng event nhiều, có thể:
    - Dùng connection riêng cho EventBus (thay vì mỗi lần publish mở transaction mới).
    - Hoặc dùng batch / coalescing event.
- **Future extension:**
  - Nếu cần durability cao hơn:
    - Thêm bảng `event_log` và cho API đọc event non-realtime từ đó (polling nhẹ).
    - Hoặc dùng Supabase Realtime & replication để push trực tiếp tới client (khi đó thiết kế bridge thay đổi).

Phase 5.1 dừng ở mức đảm bảo **event từ worker có đường đi tới WebSocket client trong multi-process**, sử dụng đúng stack hiện có (Supabase Postgres) và không đổi contract đã public ở Phase 5. Implement backend sẽ chỉ cần tạo `EventBus`, listener ở API, và refactor các chỗ emit event trong worker sang publish qua bus.

