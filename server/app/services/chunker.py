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


def chunk_full_text_to_segments(full_text: str, max_chunk_chars: int = 1500) -> List[dict]:
    """Split a full OCR text into logical segments.

    This helper is shared between the ingestion pipeline (content_list)
    and the raw-text viewer API so that segmentation is consistent.

    Heuristics (v2, Phase 7):
    - Ưu tiên giữ ranh giới đoạn theo "blank line" (`\\n\\n`) nếu có.
    - Nếu tài liệu hầu như không có `\\n\\n`, fallback lần lượt:
      - Tách theo dòng đơn (`\\n`) rồi gộp lại theo max_chunk_chars.
      - Nếu vẫn chỉ còn một khối dài, chia theo fixed-size window dựa trên
        độ dài ký tự để tránh chỉ có 1 segment cho toàn bộ văn bản.
    """
    full_text = (full_text or "").strip()
    segments: List[dict] = []
    if not full_text:
        return segments

    chunks: List[str] = []

    def _flush_current(buf: list[str]) -> None:
        if not buf:
            return
        chunks.append("\n".join(buf))
        buf.clear()

    # Step 1: try split by blank lines (paragraphs separated by \n\n).
    paragraphs = [p for p in full_text.split("\n\n") if p.strip()]
    if len(paragraphs) <= 1:
        # Fallback: split by single newlines to get shorter units.
        paragraphs = [p for p in full_text.split("\n") if p.strip()]
    if not paragraphs:
        paragraphs = [full_text]

    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # Nếu đoạn hiện tại + para mới vượt quá max_chunk_chars,
        # flush đoạn hiện tại trước khi thêm para mới.
        if current and current_len + len(para) + 1 > max_chunk_chars:
            _flush_current(current)
            current_len = 0
        current.append(para)
        current_len += len(para) + 1

    _flush_current(current)

    # Step 2: nếu vì lý do nào đó vẫn chỉ có 1 chunk rất dài,
    # chia thêm theo fixed-size window để tránh chỉ 1 segment cho cả document.
    if len(chunks) == 1 and len(chunks[0]) > max_chunk_chars:
        text = chunks[0]
        chunks = []
        start = 0
        text_len = len(text)
        while start < text_len:
            end = min(start + max_chunk_chars, text_len)
            chunks.append(text[start:end].strip())
            start = end

    for idx, chunk in enumerate(chunks):
        segments.append(
            {
                "segment_index": idx,
                # Phase 7 v1: page information is not yet mapped,
                # so we keep 0 as a placeholder.
                "page_idx": 0,
                "text": chunk,
            }
        )

    return segments


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

        content_list: List[dict] = []
        segments = chunk_full_text_to_segments(full_text)
        for seg in segments:
            content_list.append(
                {
                    "type": "text",
                    "text": seg["text"],
                    "page_idx": seg["page_idx"],
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
