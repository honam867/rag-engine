"""Answer Orchestrator for Phase 8 – retrieval-only RAG + LLM answer box."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from server.app.core.config import AnswerSettings, get_settings
from server.app.core.logging import get_logger
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
        max_context_segments: int = 32,
    ) -> Dict[str, Any]:
        """End-to-end answer pipeline for a single user question."""
        # 1) Retrieve context segments (segment_id + text) from RAG-Anything / LightRAG.
        retrieved_segments: List[Dict[str, Any]] = []
        try:
            retrieved_segments = await self._rag_engine.get_segments_for_query(
                workspace_id=workspace_id,
                question=question,
                mode=None,
            )
        except Exception as exc:  # noqa: BLE001
            self._logger.error(
                "Failed to retrieve segments from RAG engine for workspace=%s: %s",
                workspace_id,
                str(exc),
            )

        # Normalize segments and build a lookup by segment_id for citations.
        canonical_segments: List[Dict[str, Any]] = []
        segment_by_segment_id: Dict[str, Dict[str, Any]] = {}
        for seg in retrieved_segments or []:
            seg_id_raw = str(seg.get("segment_id") or "").strip()
            if not seg_id_raw:
                continue
            # Ensure we have document_id and segment_index; fall back to parsing from seg_id.
            doc_id = str(seg.get("document_id") or "").strip()
            seg_index_val = seg.get("segment_index")
            if not doc_id or seg_index_val is None:
                parts = seg_id_raw.split(":", 1)
                if len(parts) == 2:
                    doc_id = doc_id or parts[0]
                    try:
                        seg_index_val = seg_index_val if seg_index_val is not None else int(parts[1])
                    except (TypeError, ValueError):
                        seg_index_val = seg_index_val if seg_index_val is not None else 0
            try:
                seg_index = int(seg_index_val)
            except (TypeError, ValueError):
                seg_index = 0

            text_val = str(seg.get("text") or "").strip()
            page_idx = 0  # Page index is not available from LightRAG prompt; keep 0 as placeholder.

            canonical = {
                "segment_id": seg_id_raw,
                "document_id": doc_id,
                "segment_index": seg_index,
                "page_idx": page_idx,
                "text": text_val,
            }
            canonical_segments.append(canonical)
            segment_by_segment_id[seg_id_raw] = canonical

        # Limit the number of context segments to avoid oversized prompts.
        if max_context_segments > 0 and len(canonical_segments) > max_context_segments:
            canonical_segments = canonical_segments[:max_context_segments]

        segment_ids: List[str] = [seg["segment_id"] for seg in canonical_segments]

        # Debug logging: show what RAG-Anything/LightRAG actually retrieved (as JSON).
        # This helps verify SEG IDs and the canonical segments we pass into the LLM.
        try:
            preview_segments = [
                {
                    "segment_id": seg.get("segment_id"),
                    "document_id": seg.get("document_id"),
                    "segment_index": seg.get("segment_index"),
                    "page_idx": seg.get("page_idx"),
                    "text_preview": (seg.get("text") or "")[:200],
                }
                for seg in canonical_segments
            ]
            self._logger.info(
                "AnswerEngine retrieval for workspace=%s conversation=%s: segment_ids=%s segments=%s",
                workspace_id,
                conversation_id,
                segment_ids,
                json.dumps(preview_segments, ensure_ascii=False),
            )
        except Exception as exc:  # noqa: BLE001
            self._logger.warning(
                "Failed to log retrieval preview for workspace=%s conversation=%s: %s",
                workspace_id,
                conversation_id,
                str(exc),
            )

        # 3) Build prompts.
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(question=question, segments=canonical_segments)

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

        if canonical_segments:
            result["retrieved_segments"] = canonical_segments

        if isinstance(usage, LLMUsage):
            result["llm_usage"] = {
                "model": usage.model,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }

        return result
