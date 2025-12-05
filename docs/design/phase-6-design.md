# phase-6-design – Redis Event Bus & Worker Wake-up

Mục tiêu: thay thế lớp Event Bus dựa trên Postgres (LISTEN/NOTIFY) bằng Redis, để đảm bảo realtime cross-process (API ↔ workers) trong bối cảnh Supabase Transaction/Session Pooler và hạn chế IPv4 hiện tại.

---

## 1. Tổng quan kiến trúc

- Giữ nguyên:
  - WebSocket `/ws` + `ConnectionManager` (`server/app/core/realtime.py`).
  - Business layer: parse/ingest (Document AI, RAG), DB schema (`parse_jobs`, `documents`, `rag_documents`, `messages`).
  - Số process: 1 API + 2 workers (`parse_worker`, `ingest_worker`).
- Thay đổi:
  - Event Bus cross-process chuyển từ **Postgres LISTEN/NOTIFY** sang **Redis**.
  - parse_worker wake-up chuyển từ NOTIFY Postgres sang Redis (pub/sub hoặc queue).
- Redis chỉ dùng làm **event bus / wake-up**, Postgres vẫn là source of truth về state.

Sơ đồ mới:

```text
parse_worker / ingest_worker
  |  (publish)
  v
Redis (channels)
  ^  (subscribe)
  |
API process (FastAPI + WebSocket)
  |-- send_event_to_user --> ConnectionManager --> WebSocket clients
```

Wake-up parse_worker:

```text
API (upload document)
  |  (insert parse_jobs + publish)
  v
Redis (channel/queue parse_jobs)
  ^  (subscribe / BLPOP)
  |
parse_worker
  |-- fetch_and_process_next_jobs --> ParserPipelineService
```

---

## 2. Redis config & abstraction

### 2.1. Env & Settings

- Env:
  - `REDIS_URL=redis://localhost:6379/0` (ví dụ).
- Thêm `RedisSettings` trong `core/config.py`:

```python
class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = "redis://localhost:6379/0"
```

- Thêm field `redis: RedisSettings` vào `Settings`.

### 2.2. Redis client abstraction

- Thêm module: `server/app/core/redis_client.py`:
  - Chỉ định nghĩa abstraction đơn giản:

```python
import redis.asyncio as redis

_redis: redis.Redis | None = None

def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = redis.from_url(settings.redis.url, decode_responses=True)
    return _redis
```

- Cả API lẫn workers đều dùng `get_redis()` để có cùng client (connection pool).

---

## 3. Redis Event Bus (worker → API → WebSocket)

### 3.1. Channel & payload

- Channel: `rag_realtime`.
- Payload JSON giống Phase 5.1:

```jsonc
{
  "user_id": "uuid",
  "type": "document.status_updated",  // hoặc job.status_updated, message.created, ...
  "payload": { "...": "..." }         // payload đúng contract WebSocket Phase 5
}
```

### 3.2. Publisher (workers + API)

- Thay thế `EventBus.publish(...)` dựa trên Postgres bằng Redis:
  - File mới/updated: `server/app/core/event_bus.py`:

```python
from server.app.core.redis_client import get_redis

class EventBus:
    def __init__(self, channel: str = "rag_realtime") -> None:
        self._channel = channel

    async def publish(self, user_id: str, event_type: str, payload: dict[str, Any]) -> None:
        if not user_id or not event_type:
            return
        envelope = {"user_id": user_id, "type": event_type, "payload": payload}
        try:
            redis = get_redis()
            await redis.publish(self._channel, json.dumps(envelope))
        except Exception as exc:
            logger.warning("Failed to publish event via Redis", extra={"channel": self._channel, "error": str(exc)})
```

- Tất cả chỗ đang gọi `event_bus.publish` (parser_pipeline, jobs_ingest) giữ nguyên signature; chỉ đổi implementation phía dưới sang Redis.

### 3.3. Subscriber trong API process

- Thay `listen_realtime_events()` (Postgres LISTEN) bằng Redis subscriber:

```python
async def listen_realtime_events() -> None:
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe("rag_realtime")

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
        except Exception as exc:
            logger.warning("Failed to decode rag_realtime payload", extra={"error": str(exc)})
            continue

        user_id = data.get("user_id")
        event_type = data.get("type")
        payload = data.get("payload") or {}
        if not user_id or not event_type:
            continue

        asyncio.get_event_loop().create_task(send_event_to_user(user_id, event_type, payload))
```

- Startup wiring (`server/app/main.py`):

```python
@app.on_event("startup")
async def startup() -> None:
    ...
    asyncio.create_task(listen_realtime_events())
```

- Nếu Redis connect lỗi:
  - Log error, sleep vài giây rồi retry (giống pattern Phase 5.1).

---

## 4. Wake-up parse_worker qua Redis

### 4.1. Channel / Queue

Có 2 lựa chọn; Phase 6 chọn bản đơn giản, dễ implement:

- **Option A – pub/sub wake-up (giữ DB là queue)**:
  - Channel: `parse_jobs`.
  - API publish mỗi khi tạo parse_job mới, payload JSON:

```jsonc
{ "document_id": "uuid", "job_id": "uuid" }
```

  - parse_worker:
    - Có một task background subscribe channel `parse_jobs`.
    - Khi nhận message: set `wakeup_event` để vòng loop chính chạy `fetch_and_process_next_jobs()`.

- **Option B – Redis queue (job queue)**:
  - Sử dụng `LPUSH`/`BRPOP` để hoàn toàn điều phối job qua Redis.
  - Phức tạp hơn vì phải đảm bảo idempotency với DB.

> Phase 6 chọn **Option A** để giữ DB làm queue chính, Redis chỉ làm wake-up (đơn giản, ít đụng business).

### 4.2. API publish wake-up

- Trong `server/app/api/routes/documents.py` (hoặc repository parse_job):
  - Sau khi `create_parse_job`:

```python
from server.app.core.redis_client import get_redis

async def notify_parse_job_created(document_id: str, job_id: str) -> None:
    try:
        redis = get_redis()
        await redis.publish(
            "parse_jobs",
            json.dumps({"document_id": document_id, "job_id": job_id}),
        )
    except Exception as exc:
        logger.warning("Failed to publish parse_jobs wake-up", extra={"error": str(exc)})
```

### 4.3. parse_worker subscriber

- Trong `server/app/workers/parse_worker.py`:

```python
async def listen_parse_jobs_notifications(wakeup_event: asyncio.Event) -> None:
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe("parse_jobs")

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        # Không tin payload là source-of-truth; chỉ wake-up
        wakeup_event.set()
```

- Vòng loop chính:
  - Giữ cấu trúc Phase 5 hiện tại (retry, self-heal).
  - Idling:

```python
wakeup_event = asyncio.Event()
asyncio.create_task(listen_parse_jobs_notifications(wakeup_event))

while True:
    processed = await pipeline.fetch_and_process_next_jobs(batch_size=1)
    if processed == 0:
        try:
            await asyncio.wait_for(wakeup_event.wait(), timeout=idle_sleep_seconds)
        except asyncio.TimeoutError:
            pass
        wakeup_event.clear()
    else:
        await asyncio.sleep(busy_sleep_seconds)
```

- Hành vi:
  - Nếu Redis chạy bình thường:
    - parse_worker gần như không phải chờ hết `idle_sleep_seconds` khi có job mới.
  - Nếu Redis down:
    - Vẫn rơi về polling như Phase 5 (fallback).

---

## 5. Dọn dẹp Postgres LISTEN/NOTIFY (Phase 5.1)

Thiết kế Phase 6 yêu cầu:

- Xoá/disable hoàn toàn các phần sau:
  - Trong `server/app/core/event_bus.py`:
    - Mọi code dùng `pg_notify` / `asyncpg.connect` để LISTEN/NOTIFY.
    - Hàm `notify_parse_job_created` cũ dùng Postgres.
  - Trong `server/app/workers/parse_worker.py`:
    - Hàm `listen_parse_jobs_notifications` bản asyncpg.
    - Bất kỳ logic nào phụ thuộc vào channel Postgres `parse_jobs`.
- Đảm bảo không còn kết nối asyncpg riêng ngoài SQLAlchemy engine:
  - Từ giờ chỉ có:
    - SQLAlchemy AsyncEngine dùng `SUPABASE_DB_URL` cho business/truy vấn.
    - Redis client dùng `REDIS_URL` cho event bus.

---

## 6. Behaviour & fallback

### 6.1. Khi Redis ổn định

- Upload document:
  - API:
    - Insert document, file, parse_job.
    - Publish wake-up Redis `parse_jobs`.
  - parse_worker:
    - Nhận message, wake-up gần như ngay.
    - `fetch_and_process_next_jobs` xử lý job, update DB.
    - Publish sự kiện `job.status_updated` + `document.status_updated` lên `rag_realtime`.
  - API:
    - Listener Redis nhận event, forward tới WebSocket client.
- Ingest worker:
  - Sau khi ingest 1 document `parsed`:
    - Update DB → publish `document.status_updated (ingested)` lên `rag_realtime`.
    - API forward event tới WebSocket.

### 6.2. Khi Redis gặp sự cố

- API / workers:
  - Publish/subscribe có thể raise exception → log warning/error (không crash process).
  - parse_worker vẫn:
    - Poll DB theo idle_sleep/busy_sleep.
    - Retry/self-heal theo Phase 5.
- Client:
  - Có thể mất một số realtime event, nhưng:
    - REST trả state chuẩn từ DB.
    - Có thể thiết kế client để thỉnh thoảng refetch (React Query interval) nếu muốn an toàn.

---

## 7. Acceptance & validation

- Sau khi implement:
  - Không còn lỗi liên quan asyncpg LISTEN/NOTIFY ở log API/worker.
  - Redis connection được log ok (hoặc warning rõ ràng nếu thất bại).
  - Test manual:
    1. Start API + redis + parse_worker + ingest_worker.
    2. Upload document:
       - Quan sát log:
         - API publish wake-up.
         - parse_worker nhận wake-up gần như tức thì (không đợi hết 5s).
         - API nhận event từ `rag_realtime` và push WebSocket.
    3. Ingest (worker):
       - Sau khi ingest xong, client thấy `status='ingested'` realtime.

Thiết kế này giữ nguyên WebSocket contract với client (Phase 5), chỉ thay hạ tầng event bus từ Postgres sang Redis, phù hợp với constraint Supabase hiện tại.

