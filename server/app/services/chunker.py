"""Chunker service for building RAG-Anything content_list (Phase 3).

This service bridges OCR results (docai_full_text + JSON raw on R2)
with the RAG engine by producing `content_list` items that LightRAG
can ingest.
"""

from __future__ import annotations

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession


class ChunkerService:
    """Service responsible for turning documents into content_list."""

    def __init__(self, session_factory, storage_r2) -> None:  # type: ignore[no-untyped-def]
        self._session_factory = session_factory
        self._storage_r2 = storage_r2

    async def build_content_list_from_document(self, document_id: str) -> List[dict]:
        """Build RAG-Anything content_list for a given document.

        See `docs/design/phase-3-design.md` for the target format and
        chunking strategy.
        """
        raise NotImplementedError("Phase 3 - ChunkerService.build_content_list_from_document is not implemented yet")

