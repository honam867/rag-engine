"""Parse worker for Phase 2 (Document AI OCR).

Runs a simple loop that polls parse_jobs in Supabase and processes them
via ParserPipelineService.
"""

from __future__ import annotations

import asyncio

from server.app.core.config import get_settings
from server.app.core.logging import get_logger, setup_logging
from server.app.db.session import async_session
from server.app.services.docai_client import DocumentAIClient
from server.app.services.parser_pipeline import ParserPipelineService


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

    while True:
        try:
            processed = await pipeline.fetch_and_process_next_jobs(batch_size=1)
            if processed == 0:
                await asyncio.sleep(idle_sleep_seconds)
            else:
                await asyncio.sleep(busy_sleep_seconds)
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error in parse worker loop", extra={"error": str(exc)})
            await asyncio.sleep(idle_sleep_seconds)


def main() -> None:
    asyncio.run(run_worker_loop())


if __name__ == "__main__":
    main()
