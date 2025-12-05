from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

from server.app.core.logging import get_logger
from server.app.core.redis_client import get_redis
from server.app.core.realtime import send_event_to_user

logger = get_logger(__name__)


class EventBus:
    """Redis-based event bus for cross-process realtime (Phase 6).

    Workers publish events to a Redis channel; the API process subscribes and
    forwards them to connected WebSocket clients.
    """

    def __init__(self, channel: str = "rag_realtime") -> None:
        self._channel = channel

    async def publish(self, user_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        """Publish a typed event for a specific user to the configured channel.

        Payload shape matches the WebSocket contract. This call is best-effort:
        failures are logged but must not break business flows.
        """
        if not user_id or not event_type:
            return

        envelope = {
            "user_id": user_id,
            "type": event_type,
            "payload": payload,
        }
        try:
            redis = get_redis()
            await redis.publish(self._channel, json.dumps(envelope))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to publish realtime event via Redis",
                extra={"channel": self._channel, "error": str(exc)},
            )


event_bus = EventBus(channel="rag_realtime")


async def listen_realtime_events() -> None:
    """Background task: subscribe Redis channel and forward events to WebSocket."""
    while True:
        try:
            redis = get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe("rag_realtime")
            logger.info("Listening for realtime events on Redis channel 'rag_realtime'")

            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                data_raw = message.get("data")
                try:
                    data = json.loads(data_raw)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to decode rag_realtime Redis payload",
                        extra={"error": str(exc)},
                    )
                    continue

                user_id = data.get("user_id")
                event_type = data.get("type")
                event_payload = data.get("payload") or {}
                if not user_id or not event_type:
                    continue

                asyncio.get_event_loop().create_task(
                    send_event_to_user(user_id, event_type, event_payload)
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Redis realtime listener encountered error; will retry",
                extra={"error": str(exc)},
            )
            await asyncio.sleep(5)


async def notify_parse_job_created(document_id: str, job_id: str) -> None:
    """Notify parse_worker via Redis that a new parse_job has been created."""
    payload = {"document_id": document_id, "job_id": job_id}
    try:
        redis = get_redis()
        await redis.publish("parse_jobs", json.dumps(payload))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to publish parse_jobs wake-up notification via Redis",
            extra={"error": str(exc)},
        )
