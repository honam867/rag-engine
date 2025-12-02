"""Ingestion job service (Phase 3).

Responsible for taking documents that have been parsed (status='parsed')
and ingesting them into the RAG engine, updating `rag_documents` and
document statuses.
"""

from __future__ import annotations

from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from server.app.services.chunker import ChunkerService
from server.app.services.rag_engine import RagEngineService


class IngestJobService:
    """Service responsible for ingesting parsed documents into RAG."""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        chunker: ChunkerService,
        rag_engine: RagEngineService,
    ) -> None:
        self._session_factory = session_factory
        self._chunker = chunker
        self._rag_engine = rag_engine

    async def ingest_document(self, document_id: str) -> None:
        """Ingest a single parsed document into RAG."""
        raise NotImplementedError("Phase 3 - IngestJobService.ingest_document is not implemented yet")

    async def ingest_pending_documents(self, batch_size: int = 1) -> int:
        """Ingest a batch of parsed documents that have no rag_documents mapping."""
        raise NotImplementedError("Phase 3 - IngestJobService.ingest_pending_documents is not implemented yet")

