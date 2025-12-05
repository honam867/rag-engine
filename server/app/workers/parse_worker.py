"""Parse worker for Phase 2 (Document AI OCR).

Runs a simple loop that polls parse_jobs in Supabase and processes them
via ParserPipelineService.
"""

from __future__ import annotations

import asyncio

from server.app.core.config import get_settings
from server.app.core.logging import get_logger, setup_logging
from server.app.core.redis_client import get_redis
from server.app.db import repositories as repo
from server.app.db.session import async_session
from server.app.services.docai_client import DocumentAIClient
from server.app.services.parser_pipeline import ParserPipelineService


async def listen_parse_jobs_notifications(wakeup_event: asyncio.Event) -> None:
    """Listen for Redis parse_jobs channel and wake the worker loop."""
    logger = get_logger(__name__)
    while True:
        try:
            redis = get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe("parse_jobs")
            logger.info("Listening for parse_jobs notifications via Redis")

            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                # Không tin payload là source-of-truth; chỉ wake-up vòng loop chính.
                wakeup_event.set()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "parse_jobs Redis listener encountered error; will retry",
                extra={"error": str(exc)},
            )
            await asyncio.sleep(5)


async def run_worker_loop() -> None:
    """Main worker loop for processing parse_jobs."""
    setup_logging()
    logger = get_logger(__name__)
    settings = get_settings()
    logger.info("Starting parse worker", extra={"db_url": settings.database.db_url})

    docai_client = DocumentAIClient()
    pipeline = ParserPipelineService(session_factory=async_session, docai_client=docai_client)

    idle_sleep_seconds = 5
    busy_sleep_seconds = 1

    # On startup, attempt to heal stale running parse_jobs so they can be retried.
    try:
        async with async_session() as session:  # type: ignore[call-arg]
            stale_threshold_seconds = 600  # 10 minutes
            jobs = await repo.fetch_stale_running_parse_jobs(
                session=session,
                older_than_seconds=stale_threshold_seconds,
            )
            if jobs:
                logger.info(
                    "Found stale running parse_jobs; resetting for retry",
                    extra={"count": len(jobs)},
                )
            for job in jobs:
                job_id = str(job["id"])
                retry_count = int(job.get("retry_count", 0) or 0)
                max_retries = 3
                if retry_count < max_retries:
                    await repo.requeue_parse_job(
                        session=session,
                        job_id=job_id,
                        retry_count=retry_count + 1,
                        error_message="stale-running",
                    )
                else:
                    await repo.mark_parse_job_failed(
                        session=session,
                        job_id=job_id,
                        error_message="stale-running",
                    )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to heal stale parse_jobs on startup", extra={"error": str(exc)})

    # Start background listener for NOTIFY wakeups.
    wakeup_event: asyncio.Event = asyncio.Event()
    asyncio.create_task(listen_parse_jobs_notifications(wakeup_event))

    while True:
        try:
            processed = await pipeline.fetch_and_process_next_jobs(batch_size=1)
            if processed == 0:
                # Wait either for a NOTIFY wake-up or for the idle timeout.
                try:
                    await asyncio.wait_for(wakeup_event.wait(), timeout=idle_sleep_seconds)
                except asyncio.TimeoutError:
                    pass
                wakeup_event.clear()
            else:
                await asyncio.sleep(busy_sleep_seconds)
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error in parse worker loop", extra={"error": str(exc)})
            await asyncio.sleep(idle_sleep_seconds)


def main() -> None:
    asyncio.run(run_worker_loop())


if __name__ == "__main__":
    main()
