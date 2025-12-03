"""Chunker service for building RAG-Anything content_list (Phase 3).

This service bridges OCR results (docai_full_text + JSON raw on R2)
with the RAG engine by producing `content_list` items that LightRAG
can ingest.
"""

from __future__ import annotations

from typing import List

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.core.logging import get_logger
from server.app.db import models

class ChunkerService:
    """Service responsible for turning documents into content_list."""

    def __init__(self, session_factory, storage_r2) -> None:  # type: ignore[no-untyped-def]
        self._session_factory = session_factory
        self._storage_r2 = storage_r2
        self._logger = get_logger(__name__)

    async def build_content_list_from_document(self, document_id: str) -> List[dict]:
        """Build RAG-Anything content_list for a given document.

        See `docs/design/phase-3-design.md` for the target format and
        chunking strategy.
        """
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

        # Simple V1 chunking strategy: split by paragraphs and fall back to fixed-size chunks.
        chunks: List[str] = []
        current: list[str] = []
        current_len = 0
        max_chunk_chars = 1500

        # Prefer paragraph boundaries (double newline) when present.
        paragraphs = [p for p in full_text.split("\n\n") if p.strip()]
        if len(paragraphs) == 1:
            # If there are no clear paragraphs, fall back to single string chunking.
            paragraphs = [full_text]

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            # If adding this paragraph would exceed the limit, flush current chunk.
            if current and current_len + len(para) + 1 > max_chunk_chars:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            current.append(para)
            current_len += len(para) + 2  # account for separators

        if current:
            chunks.append("\n\n".join(current))

        if not chunks:
            # Fallback: use the whole text as a single chunk.
            chunks = [full_text]

        content_list: List[dict] = []
        for chunk in chunks:
            content_list.append(
                {
                    "type": "text",
                    "text": chunk,
                    # Phase 3 v1: we do not yet map precise pages; use 0 as placeholder.
                    "page_idx": 0,
                }
            )

        self._logger.info(
            "Built content_list for document %s (workspace=%s, filename=%s, chunks=%d)",
            document_id,
            workspace_id,
            original_filename,
            len(content_list),
        )

        return content_list
