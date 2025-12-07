"""Chunker service for building RAG-Anything content_list (Phase 3).

This service bridges OCR results (docai_full_text + JSON raw on R2)
with the RAG engine by producing `content_list` items that LightRAG
can ingest.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.core.logging import get_logger
from server.app.db import models

logger = get_logger(__name__)


# Maximum approximate number of characters per content_list item when
# ingesting into RAG-Anything. This groups multiple UI segments into a
# larger macro-chunk so that retrieval sees longer, more natural pieces
# of text, while SEG tags still preserve per-segment identity.
MAX_INGEST_CHARS_PER_ITEM = 4000


def make_segment_id(document_id: str, segment_index: int) -> str:
    """Build a stable segment identifier for ID-based citations."""
    return f"{document_id}:{segment_index}"


def _extract_text_from_anchor(full_text: str, anchor: Dict[str, Any]) -> str:
    """Extract text for a layout.text_anchor from Document AI JSON.

    Document AI encodes text ranges either as:
    - text_anchor.text_segments[] with start_index/end_index, or
    - start_index/end_index directly on text_anchor (depending on version).
    """
    if not full_text:
        return ""

    if not isinstance(anchor, dict):
        return ""

    segments = anchor.get("text_segments") or []
    # Some variants may have start_index / end_index directly on the anchor.
    if not segments and ("start_index" in anchor or "end_index" in anchor):
        segments = [anchor]

    pieces: list[str] = []
    text_len = len(full_text)
    for seg in segments:
        try:
            start = int(seg.get("start_index", 0) or 0)
            end = int(seg.get("end_index", 0) or 0)
        except (TypeError, ValueError):
            continue
        if start < 0 or end <= start or start >= text_len:
            continue
        end = min(end, text_len)
        pieces.append(full_text[start:end])

    return "".join(pieces).strip()


def build_segments_from_docai(
    doc: Dict[str, Any],
    full_text: str,
    max_chunk_chars: int = 1500,
) -> List[dict]:
    """Build segments from Document AI JSON + full_text.

    - Ưu tiên dùng pages[*].paragraphs[*].layout.text_anchor.
    - Nếu không có paragraphs, fallback sang pages[*].lines[*].
    - Mỗi anchor → một hoặc nhiều segments; nếu đoạn quá dài, tiếp tục
      chia theo fixed-size window để giữ segment vừa phải.

    Nếu JSON không hợp lệ hoặc không có cấu trúc cần thiết, trả về []
    để caller có thể fallback sang `chunk_full_text_to_segments`.
    """
    full_text = (full_text or "").strip()
    if not full_text or not isinstance(doc, dict):
        return []

    doc_text = (doc.get("text") or "").strip()
    # Nếu doc.text khác với full_text trong DB, ưu tiên doc.text để
    # giữ alignment chính xác với text_anchor.
    if doc_text:
        if doc_text != full_text:
            logger.warning(
                "Document AI JSON text differs from docai_full_text; using JSON text for segmentation."
            )
        full_text = doc_text

    pages = doc.get("pages") or []
    if not isinstance(pages, list) or not pages:
        return []

    segments: List[dict] = []
    segment_index = 0

    for page_idx, page in enumerate(pages):
        if not isinstance(page, dict):
            continue

        paras = page.get("paragraphs") or []
        # Fallback: nếu không có paragraphs, dùng lines.
        if not paras:
            paras = page.get("lines") or []

        if not isinstance(paras, list):
            continue

        for para in paras:
            if not isinstance(para, dict):
                continue
            layout = para.get("layout") or {}
            if not isinstance(layout, dict):
                continue
            anchor = layout.get("text_anchor") or {}
            text = _extract_text_from_anchor(full_text, anchor)
            text = (text or "").strip()
            if not text:
                continue

            # Nếu đoạn quá dài, tiếp tục chia theo fixed-size window.
            if len(text) > max_chunk_chars:
                start = 0
                text_len = len(text)
                while start < text_len:
                    end = min(start + max_chunk_chars, text_len)
                    chunk = text[start:end].strip()
                    if chunk:
                        segments.append(
                            {
                                "segment_index": segment_index,
                                "page_idx": page_idx,
                                "text": chunk,
                            }
                        )
                        segment_index += 1
                    start = end
            else:
                segments.append(
                    {
                        "segment_index": segment_index,
                        "page_idx": page_idx,
                        "text": text,
                    }
                )
                segment_index += 1

    return segments


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

            raw_key: Optional[str] = document.get("docai_raw_r2_key")  # type: ignore[assignment]

        workspace_id = str(document["workspace_id"])
        original_filename = str(file["original_filename"])

        # Ưu tiên dùng JSON Document AI để build segments sát với layout gốc.
        segments: List[dict] = []
        if raw_key:
            try:
                doc = await self._storage_r2.download_json(raw_key)
                segments = build_segments_from_docai(doc=doc, full_text=full_text)
            except Exception as exc:  # noqa: BLE001
                self._logger.warning(
                    "Failed to build segments from Document AI JSON for document %s: %s; falling back to heuristic chunking",
                    document_id,
                    str(exc),
                )

        if not segments:
            segments = chunk_full_text_to_segments(full_text)

        content_list: List[dict] = []
        # Build macro-chunks for ingestion: group multiple UI segments into
        # longer text blocks, but keep [SEG=doc:idx] markers inline so that
        # retrieval prompts still contain per-segment identifiers.
        current_text_parts: List[str] = []
        current_len = 0
        current_page_idx = 0

        def _flush_current() -> None:
            nonlocal current_text_parts, current_len, current_page_idx
            if not current_text_parts:
                return
            text_block = "\n\n".join(current_text_parts).strip()
            if text_block:
                content_list.append(
                    {
                        "type": "text",
                        "text": text_block,
                        "page_idx": current_page_idx,
                    }
                )
            current_text_parts = []
            current_len = 0

        for seg in segments:
            segment_index = int(seg.get("segment_index", 0))
            segment_id = make_segment_id(document_id, segment_index)
            seg_text = str(seg.get("text") or "").strip()
            if not seg_text:
                continue
            text_with_id = f"[SEG={segment_id}] {seg_text}"

            # Start new block if current one would grow too large.
            if (
                current_text_parts
                and current_len + len(text_with_id) + 2 > MAX_INGEST_CHARS_PER_ITEM
            ):
                _flush_current()

            if not current_text_parts:
                # First segment in a new block – use its page_idx as the
                # representative page for the whole block.
                try:
                    current_page_idx = int(seg.get("page_idx", 0))
                except (TypeError, ValueError):
                    current_page_idx = 0

            current_text_parts.append(text_with_id)
            current_len += len(text_with_id) + 2

        _flush_current()

        self._logger.info(
            "Built content_list for document %s (workspace=%s, filename=%s, chunks=%d)",
            document_id,
            workspace_id,
            original_filename,
            len(content_list),
        )

        return content_list
