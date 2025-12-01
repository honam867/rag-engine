"""Parser pipeline service (Phase 2).

Responsible for orchestrating parse_jobs:
  - Load job and associated document/file metadata.
  - Download file bytes from R2.
  - Call Document AI OCR.
  - Persist docai_full_text and JSON raw key.
  - Update job and document statuses.

Implementation is deferred to Phase 2; this file only establishes the interface.
"""

from __future__ import annotations

from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from server.app.services.docai_client import DocumentAIClient


class ParserPipelineService:
    """Service orchestrating parse_jobs → Document AI → DB updates."""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        docai_client: DocumentAIClient | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._docai_client = docai_client or DocumentAIClient()

    async def process_single_job(self, job_id: str) -> None:
        """Process a single parse_job.

        See `docs/design/phase-2-design.md` for the detailed steps.
        """
        raise NotImplementedError("Phase 2 - ParserPipelineService.process_single_job is not implemented yet")

    async def fetch_and_process_next_jobs(self, batch_size: int = 1) -> int:
        """Fetch a batch of queued jobs and process them.

        Returns the number of jobs processed (success + failed).
        """
        raise NotImplementedError("Phase 2 - ParserPipelineService.fetch_and_process_next_jobs is not implemented yet")

