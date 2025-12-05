from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

import sqlalchemy as sa

from server.app.core.config import get_settings
from server.app.core.logging import get_logger
from server.app.core.realtime import send_event_to_user
from server.app.db.session import engine

logger = get_logger(__name__)


class EventBus:
    """Lightweight Postgres LISTEN/NOTIFY based event bus.

    Phase 5.1 uses this to bridge events emitted from background workers
    into the API process, which then forwards them over WebSocket.
    """

    def __init__(self, channel: str = "rag_realtime") -> None:
        self._channel = channel

    async def publish(self, user_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        """Publish a typed event for a specific user to the configured channel.

        The payload shape matches the WebSocket contract. This call is best-effort:
        failures are logged but must not break business flows (workers, API).
        """
        if not user_id or not event_type:
            return

        envelope = {
            "user_id": user_id,
            "type": event_type,
            "payload": payload,
        }
        data = json.dumps(envelope)

        try:
            async with engine.begin() as conn:
                await conn.execute(
                    sa.text("select pg_notify(:channel, :payload)"),
                    {"channel": self._channel, "payload": data},
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to publish realtime event via Postgres NOTIFY",
                extra={"channel": self._channel, "error": str(exc)},
            )


event_bus = EventBus(channel="rag_realtime")


def _normalize_dsn(url: str) -> str:
    """Normalize SQLAlchemy-style URL to a plain asyncpg-compatible DSN."""
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


async def listen_realtime_events() -> None:
    """Background task: LISTEN for rag_realtime events and forward to WebSocket.

    Runs in the API process only. It uses a dedicated asyncpg connection so that
    LISTEN/NOTIFY does not interfere with SQLAlchemy's own connection pool.
    """
    import asyncpg  # imported here to avoid hard dependency at import time

    settings = get_settings()
    dsn = _normalize_dsn(settings.database.db_url)

    while True:
        try:
            conn = await asyncpg.connect(
                dsn=dsn,
                # Disable statement cache to be compatible with Supabase pooler.
                statement_cache_size=0,
            )
            logger.info("Listening for realtime events on channel 'rag_realtime'")

            def _handler(connection, pid, channel, payload: str) -> None:  # type: ignore[override]
                try:
                    data = json.loads(payload)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to decode rag_realtime notification payload",
                        extra={"error": str(exc)},
                    )
                    return

                user_id = data.get("user_id")
                event_type = data.get("type")
                event_payload = data.get("payload") or {}
                if not user_id or not event_type:
                    return

                loop = asyncio.get_event_loop()
                loop.create_task(send_event_to_user(user_id, event_type, event_payload))

            await conn.add_listener("rag_realtime", _handler)

            try:
                # Keep connection alive; asyncpg will invoke _handler on notifications.
                while True:
                    await asyncio.sleep(3600)
            finally:
                try:
                    await conn.close()
                except Exception:  # noqa: BLE001
                    pass
        except Exception as exc:  # noqa: BLE001
            logger.exception("Realtime listener encountered error; will retry")
            # Backoff before retrying connection
            await asyncio.sleep(5)


async def notify_parse_job_created(document_id: str, job_id: str) -> None:
    """Notify parse_worker that a new parse_job has been created.

    This uses a lightweight NOTIFY on the `parse_jobs` channel. The payload
    is informational; the worker still uses the database as the source of truth.
    """
    payload = json.dumps({"document_id": document_id, "job_id": job_id})
    try:
        async with engine.begin() as conn:
            await conn.execute(
                sa.text("select pg_notify('parse_jobs', :payload)"),
                {"payload": payload},
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to publish parse_jobs wake-up notification",
            extra={"error": str(exc)},
        )
