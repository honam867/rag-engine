"""Chunker service for building RAG content_list (Phase 3).

This service bridges OCR results (`docai_full_text` stored in DB)
with the RAG engine by producing `content_list` items that LightRAG
can ingest. It does not attempt to reconstruct complex layout from
Document AI JSON; it works directly on the flattened OCR text.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.core.logging import get_logger
from server.app.db import models

logger = get_logger(__name__)


class ChunkerService:
    """Service responsible for turning documents into content_list."""

    def __init__(self, session_factory, storage_r2) -> None:  # type: ignore[no-untyped-def]
        self._session_factory = session_factory
        self._storage_r2 = storage_r2
        self._logger = get_logger(__name__)

    async def _build_ingest_chunks_impl(self, document_id: str) -> tuple[List[dict], List[dict]]:
        """Internal helper to build content_list + chunk metadata for ingest."""
        async with self._session_factory() as session:  # type: ignore[call-arg]
            assert isinstance(session, AsyncSession)

            # Load document and its workspace_id.
            doc_stmt = sa.select(models.documents).where(models.documents.c.id == document_id)
            doc_result = await session.execute(doc_stmt)
            doc_row = doc_result.fetchone()
            if not doc_row:
                raise RuntimeError(f"Document not found for id={document_id}")
            document = doc_row._mapping

            # Load one file metadata row to get original_filename.
            file_stmt = sa.select(models.files).where(models.files.c.document_id == document_id).limit(1)
            file_result = await session.execute(file_stmt)
            file_row = file_result.fetchone()
            if not file_row:
                raise RuntimeError(f"No file metadata found for document id={document_id}")
            file = file_row._mapping
            full_text = (document.get("docai_full_text") or "").strip()
            if not full_text:
                raise RuntimeError(f"Document {document_id} has no OCR text (docai_full_text is empty)")

        workspace_id = str(document["workspace_id"])
        original_filename = str(file["original_filename"])

        content_list: List[dict] = [
            {
                "type": "text",
                "text": full_text,
                "page_idx": 0,
            }
        ]
        chunks_info: List[dict] = []

        self._logger.info(
            "Built content_list for document %s (workspace=%s, filename=%s, chunks=%d)",
            document_id,
            workspace_id,
            original_filename,
            len(content_list),
        )

        return content_list, chunks_info

    async def build_content_list_from_document(self, document_id: str) -> List[dict]:
        """Build RAG ingest content_list for a given document (legacy API).

        Phase 9.1 reuses the same logic but also needs per-chunk metadata
        for citation mapping. See `build_ingest_chunks_from_document`.
        """
        content_list, _ = await self._build_ingest_chunks_impl(document_id)
        return content_list

    async def build_ingest_chunks_from_document(self, document_id: str) -> tuple[List[dict], List[dict]]:
        """Build content_list + chunk metadata for ingest (Phase 9.1)."""
        return await self._build_ingest_chunks_impl(document_id)
