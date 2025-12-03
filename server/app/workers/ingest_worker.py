"""Ingest worker for Phase 3 (RAG ingestion).

Runs a loop that finds parsed documents without a rag_documents mapping
and ingests them into the RAG engine.
"""

from __future__ import annotations

import asyncio
from dotenv import load_dotenv

from server.app.core.config import get_settings
from server.app.core.logging import get_logger, setup_logging
from server.app.db.session import async_session
from server.app.services import storage_r2
from server.app.services.chunker import ChunkerService
from server.app.services.jobs_ingest import IngestJobService
from server.app.services.rag_engine import RagEngineService


async def run_worker_loop() -> None:
    """Main worker loop for ingesting parsed documents into RAG."""
    # Ensure .env is loaded so RagEngineService can see OPENAI_API_KEY, etc.
    load_dotenv(".env")
    setup_logging()
    logger = get_logger(__name__)
    settings = get_settings()
    logger.info("Starting ingest worker", extra={"db_url": settings.database.db_url})

    rag_engine = RagEngineService(settings=settings.rag)
    chunker = ChunkerService(session_factory=async_session, storage_r2=storage_r2)
    ingest_service = IngestJobService(
        session_factory=async_session,
        chunker=chunker,
        rag_engine=rag_engine,
    )

    idle_sleep_seconds = 5
    busy_sleep_seconds = 1

    while True:
        try:
            processed = await ingest_service.ingest_pending_documents(batch_size=1)
            if processed == 0:
                await asyncio.sleep(idle_sleep_seconds)
            else:
                await asyncio.sleep(busy_sleep_seconds)
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error in ingest worker loop", extra={"error": str(exc)})
            await asyncio.sleep(idle_sleep_seconds)


def main() -> None:
    asyncio.run(run_worker_loop())


if __name__ == "__main__":
    main()
