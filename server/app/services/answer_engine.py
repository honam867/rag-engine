"""Answer Orchestrator – LightRAG-backed plain answer box.

Reverted Phase 9.1:
- Delegates retrieval + answer generation entirely to LightRAG via
  RagEngineService.
- Does not build sections or citations on the server anymore.
"""

from __future__ import annotations

from typing import Any, Dict

from server.app.core.config import get_settings
from server.app.core.logging import get_logger
from server.app.services.rag_engine import RagEngineService


logger = get_logger(__name__)


class AnswerEngineService:
    """High-level answer engine that owns the chat pipeline."""

    def __init__(self, rag_engine: RagEngineService | None = None) -> None:
        settings_all = get_settings()
        self._rag_engine = rag_engine or RagEngineService(settings=settings_all.rag)
        self._logger = get_logger(__name__)

    async def answer_question(
        self,
        workspace_id: str,
        conversation_id: str,
        question: str,
    ) -> Dict[str, Any]:
        """Return an answer for a single user question using LightRAG only.

        The response keeps `sections`, `citations` and `llm_usage` keys for
        backward compatibility with clients, but these fields are always
        empty/None because server-side source attribution is disabled.
        """
        try:
            rag_result = await self._rag_engine.query_answer(
                workspace_id=workspace_id,
                question=question,
                system_prompt=None,
                mode=None,
            )
            answer_text = str(rag_result.get("answer") or "").strip()
            if not answer_text:
                answer_text = (
                    "Xin lỗi, mình không thể tạo được câu trả lời cho câu hỏi này dựa trên tài liệu hiện có."
                )
            return {
                "answer": answer_text,
                "sections": [],
                "citations": [],
                "llm_usage": None,
            }
        except Exception as exc:  # noqa: BLE001
            self._logger.error(
                "LightRAG query_answer failed for workspace=%s conversation=%s: %s",
                workspace_id,
                conversation_id,
                str(exc),
            )
            return {
                "answer": (
                    "Xin lỗi, đã xảy ra lỗi khi truy vấn engine RAG nên mình chưa thể trả lời câu hỏi này."
                ),
                "sections": [],
                "citations": [],
                "llm_usage": None,
            }

