"""Answer Orchestrator for Phase 8 – retrieval-only RAG + LLM answer box.

This service coordinates:
- Retrieval from RAG-Anything / LightRAG (segments with SEG IDs).
- Prompt construction with context segments.
- Calling an OpenAI-compatible LLM via LLMClient.
- Mapping source_ids -> citations aligned with raw-text segments.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Tuple

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.core.config import AnswerSettings, get_settings
from server.app.core.logging import get_logger
from server.app.db import models
from server.app.db.session import async_session
from server.app.services import storage_r2
from server.app.services.chunker import build_segments_from_docai, chunk_full_text_to_segments
from server.app.services.llm_client import LLMClient, LLMUsage
from server.app.services.rag_engine import RagEngineService


logger = get_logger(__name__)


class AnswerEngineService:
    """High-level answer engine that owns the chat pipeline for Phase 8."""

    def __init__(
        self,
        rag_engine: RagEngineService | None = None,
        llm_client: LLMClient | None = None,
        settings: AnswerSettings | None = None,
    ) -> None:
        settings_all = get_settings()
        self._answer_settings: AnswerSettings = settings or settings_all.answer
        self._rag_engine = rag_engine or RagEngineService(settings=settings_all.rag)
        self._llm_client = llm_client or LLMClient(settings=self._answer_settings)
        self._logger = get_logger(__name__)

    async def _load_segments_for_ids(
        self,
        workspace_id: str,
        segment_ids: List[str],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        """Resolve segment_ids -> canonical segments via Document AI segmentation.

        Returns (ordered_list, segment_lookup_by_segment_id).
        """
        if not segment_ids:
            return [], {}

        # Parse and normalize IDs: "{document_uuid}:{segment_index}"
        id_pairs: List[tuple[str, int]] = []
        id_pair_set: set[tuple[str, int]] = set()
        for raw_id in segment_ids:
            if not isinstance(raw_id, str):
                continue
            value = raw_id.strip()
            if not value:
                continue
            parts = value.split(":", 1)
            if len(parts) != 2:
                continue
            doc_part, seg_part = parts
            try:
                doc_uuid = uuid.UUID(doc_part)
                seg_idx = int(seg_part)
            except (ValueError, TypeError, AttributeError):
                continue
            normalized_pair = (str(doc_uuid), seg_idx)
            if normalized_pair not in id_pair_set:
                id_pair_set.add(normalized_pair)
                id_pairs.append(normalized_pair)

        if not id_pairs:
            return [], {}

        # Load documents for these IDs within the workspace.
        async with async_session() as session:  # type: ignore[call-arg]
            assert isinstance(session, AsyncSession)
            doc_ids = [doc_id for doc_id, _ in id_pairs]
            stmt = (
                sa.select(
                    models.documents.c.id,
                    models.documents.c.docai_full_text,
                    models.documents.c.docai_raw_r2_key,
                    models.documents.c.status,
                )
                .where(
                    models.documents.c.workspace_id == workspace_id,
                    models.documents.c.docai_full_text.is_not(None),
                    models.documents.c.id.in_(doc_ids),
                )
            )
            result = await session.execute(stmt)
            doc_rows = result.fetchall()

        # Build lookup (doc_id, segment_index) -> segment info.
        segment_lookup: Dict[tuple[str, int], Dict[str, Any]] = {}

        for row in doc_rows:
            row_map = row._mapping
            doc_id_str = str(row_map["id"])
            full_text = (row_map.get("docai_full_text") or "").strip()
            if not full_text:
                continue

            raw_key = row_map.get("docai_raw_r2_key")
            segments: List[Dict[str, Any]] = []

            if raw_key:
                try:
                    doc = await storage_r2.download_json(raw_key)
                    segments = build_segments_from_docai(doc=doc, full_text=full_text)
                except Exception:  # noqa: BLE001
                    segments = []

            if not segments:
                segments = chunk_full_text_to_segments(full_text)

            for seg in segments:
                seg_idx = int(seg.get("segment_index", 0))
                key = (doc_id_str, seg_idx)
                if key not in id_pair_set:
                    continue
                segment_lookup[key] = {
                    "segment_id": f"{doc_id_str}:{seg_idx}",
                    "document_id": doc_id_str,
                    "segment_index": seg_idx,
                    "page_idx": int(seg.get("page_idx", 0)),
                    "text": str(seg.get("text") or "").strip(),
                }

        # Build ordered list of retrieved segments.
        ordered_segments: List[Dict[str, Any]] = []
        for doc_id_str, seg_idx in id_pairs:
            seg_info = segment_lookup.get((doc_id_str, seg_idx))
            if not seg_info:
                continue
            ordered_segments.append(seg_info)

        # Also expose a lookup by segment_id for fast citation mapping.
        segment_by_segment_id: Dict[str, Dict[str, Any]] = {
            seg["segment_id"]: seg for seg in ordered_segments
        }

        return ordered_segments, segment_by_segment_id

    def _build_system_prompt(self) -> str:
        """Build the (English) system prompt for the answer LLM."""
        return """You are an AI assistant that answers user questions based on provided context segments.
- Always answer in the SAME LANGUAGE as the user's question.
- Prefer to base your answer on the context segments. If the context does not contain
  enough information to answer safely, say that clearly instead of guessing.
- The context segments are prefixed with tags of the form:
    [SEG={document_id}:{segment_index}] <segment text>
- When you reference sources, you must track these SEG IDs.

Your response MUST be a single valid JSON object with the structure:
{
  "sections": [
    {
      "text": "<answer section 1>",
      "source_ids": ["{document_id}:{segment_index}", "..."]
    },
    {
      "text": "<answer section 2>",
      "source_ids": ["{document_id}:{segment_index}"]
    }
  ]
}

Rules for source_ids:
- Every source_id MUST come from a [SEG=...] tag that appears in the context.
- Do NOT invent new IDs that are not present in the context.
- If you are not sure which segment supports a section, you may use an empty array [].
"""

    def _build_user_prompt(self, question: str, segments: List[Dict[str, Any]]) -> str:
        """Build the user prompt including context segments and the question."""
        lines: List[str] = []
        for seg in segments:
            segment_id = seg.get("segment_id")
            text = seg.get("text") or ""
            if not segment_id or not text:
                continue
            lines.append(f"[SEG={segment_id}] {text}")

        context_block = "Context segments:\n\n" + ("\n\n".join(lines) if lines else "(no context available)")

        user_block = (
            context_block
            + "\n\n"
            + "User question:\n"
            + question
            + "\n\n"
            + "Answer the question based on the context when possible and follow the JSON response structure "
            "described in the system prompt."
        )

        return user_block

    def _normalize_sections_from_llm(
        self,
        raw_text: str,
        parsed: Dict[str, Any] | None,
    ) -> List[Dict[str, Any]]:
        """Normalize sections from LLM JSON output into [{text, source_ids}]."""
        sections: List[Dict[str, Any]] = []
        if isinstance(parsed, dict) and "sections" in parsed:
            raw_sections = parsed.get("sections") or []
            if isinstance(raw_sections, list):
                for sec in raw_sections:
                    if not isinstance(sec, dict):
                        continue
                    text_val = sec.get("text")
                    if not isinstance(text_val, str):
                        continue
                    src_ids_val = sec.get("source_ids") or []
                    source_ids: List[str] = []
                    if isinstance(src_ids_val, list):
                        for raw_id in src_ids_val:
                            if not isinstance(raw_id, str):
                                continue
                            value = raw_id.strip()
                            if not value:
                                continue
                            # Do not validate UUID here; mapping step will filter.
                            source_ids.append(value)
                    sections.append({"text": text_val, "source_ids": source_ids})

        if not sections:
            # Fallback: treat entire LLM output as a single section without sources.
            fallback_text = raw_text.strip() or "I'm sorry, I could not generate an answer."
            sections = [{"text": fallback_text, "source_ids": []}]

        return sections

    def _attach_citations(
        self,
        sections: List[Dict[str, Any]],
        segment_by_segment_id: Dict[str, Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Attach citations to each section based on source_ids and known segments."""
        sections_with_citations: List[Dict[str, Any]] = []
        citations_flat: List[Dict[str, Any]] = []

        for sec in sections:
            src_ids = sec.get("source_ids") or []
            citations_for_section: List[Dict[str, Any]] = []

            if isinstance(src_ids, list):
                for raw_id in src_ids:
                    if not isinstance(raw_id, str):
                        continue
                    seg_info = segment_by_segment_id.get(raw_id.strip())
                    if not seg_info:
                        continue
                    snippet = seg_info.get("text") or ""
                    if len(snippet) > 200:
                        snippet = snippet[:200] + "..."
                    citation = {
                        "document_id": seg_info["document_id"],
                        "segment_index": seg_info["segment_index"],
                        "page_idx": seg_info["page_idx"],
                        "snippet_preview": snippet,
                    }
                    citations_for_section.append(citation)
                    citations_flat.append(citation)

            sections_with_citations.append({**sec, "citations": citations_for_section})

        return sections_with_citations, citations_flat

    async def answer_question(
        self,
        workspace_id: str,
        conversation_id: str,
        question: str,
        max_context_segments: int = 8,
    ) -> Dict[str, Any]:
        """End-to-end answer pipeline for a single user question."""
        # 1) Retrieve segment IDs from RAG-Anything / LightRAG.
        segment_ids: List[str] = []
        try:
            segment_ids = await self._rag_engine.get_segment_ids_for_query(
                workspace_id=workspace_id,
                question=question,
                mode=None,
            )
        except Exception as exc:  # noqa: BLE001
            self._logger.error(
                "Failed to retrieve segment IDs from RAG engine for workspace=%s: %s",
                workspace_id,
                str(exc),
            )

        # 2) Resolve segment IDs -> canonical segments from Document AI + DB.
        retrieved_segments: List[Dict[str, Any]] = []
        segment_by_segment_id: Dict[str, Dict[str, Any]] = {}
        if segment_ids:
            try:
                retrieved_segments, segment_by_segment_id = await self._load_segments_for_ids(
                    workspace_id=workspace_id,
                    segment_ids=segment_ids,
                )
            except Exception as exc:  # noqa: BLE001
                self._logger.error(
                    "Failed to load canonical segments for workspace=%s: %s",
                    workspace_id,
                    str(exc),
                )

        # Limit the number of context segments to avoid oversized prompts.
        if max_context_segments > 0 and len(retrieved_segments) > max_context_segments:
            retrieved_segments = retrieved_segments[:max_context_segments]

        # 3) Build prompts.
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(question=question, segments=retrieved_segments)

        # 4) Call LLM.
        raw_text, parsed_json, usage = await self._llm_client.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        # 5) Normalize sections and attach citations.
        sections = self._normalize_sections_from_llm(raw_text=raw_text, parsed=parsed_json)
        sections_with_citations, citations_flat = self._attach_citations(
            sections=sections,
            segment_by_segment_id=segment_by_segment_id,
        )

        # 6) Build answer string for message content.
        answer_text = "\n\n".join(str(sec.get("text") or "") for sec in sections_with_citations).strip()

        result: Dict[str, Any] = {
            "answer": answer_text or raw_text,
            "sections": sections_with_citations,
            "citations": citations_flat,
        }

        if retrieved_segments:
            result["retrieved_segments"] = retrieved_segments

        if isinstance(usage, LLMUsage):
            result["llm_usage"] = {
                "model": usage.model,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }

        return result
