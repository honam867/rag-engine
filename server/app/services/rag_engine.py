"""RAG Engine wrapper around RAG-Anything / LightRAG (Phase 3).

This module defines a thin adapter so that the rest of the backend does
not depend directly on RAG-Anything internals.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from server.app.core.constants import RAG_DEFAULT_SYSTEM_PROMPT
from server.app.core.config import RagSettings, get_settings
from server.app.core.logging import get_logger


logger = get_logger(__name__)


class RagEngineService:
    """Adapter between application code and RAG-Anything."""

    def __init__(self, settings: RagSettings | None = None) -> None:
        self.settings: RagSettings = settings or get_settings().rag
        # Actual RAG-Anything / LightRAG instances are initialized lazily per workspace.
        self._instances: dict[str, Any] = {}

    def _get_rag_instance(self, workspace_id: str) -> Any:
        """Return (and lazily create) a RAGAnything instance for a workspace.

        Each workspace gets its own LightRAG working directory so knowledge
        is naturally isolated at the storage layer.
        """
        if workspace_id in self._instances:
            return self._instances[workspace_id]

        try:
            from raganything import RAGAnything, RAGAnythingConfig
            from lightrag.llm.openai import openai_complete_if_cache, openai_embed
            from lightrag.utils import EmbeddingFunc
        except ImportError as exc:  # pragma: no cover - environment/config issue
            raise RuntimeError(
                "RAG-Anything (raganything) and LightRAG must be installed to use RagEngineService."
            ) from exc

        # Per-workspace storage directory under the configured base dir.
        workspace_dir = os.path.join(self.settings.working_dir, workspace_id)

        # Basic configuration: we only rely on pre-parsed content_list, so keep
        # parser/multimodal features at their defaults.
        config = RAGAnythingConfig(working_dir=workspace_dir)

        # Read model configuration from settings / environment.
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        llm_model_name = self.settings.llm_model
        embedding_model_name = self.settings.embedding_model

        if not api_key:
            logger.warning(
                "OPENAI_API_KEY is not set; RAG-Anything LLM/embedding calls will fail until it is configured."
            )

        def llm_model_func(
            prompt: str,
            system_prompt: Optional[str] = None,
            history_messages: Optional[list] = None,
            **kwargs: Any,
        ) -> str:
            """Wrapper around LightRAG's OpenAI helper.

            This function signature matches what RAG-Anything expects.
            """
            if history_messages is None:
                history_messages = []
            return openai_complete_if_cache(
                llm_model_name,
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                api_key=api_key,
                base_url=base_url,
                **kwargs,
            )

        embedding_func = EmbeddingFunc(
            embedding_dim=3072,
            max_token_size=8192,
            func=lambda texts: openai_embed(
                texts,
                model=embedding_model_name,
                api_key=api_key,
                base_url=base_url,
            ),
        )

        rag = RAGAnything(
            config=config,
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
        )
        self._instances[workspace_id] = rag
        logger.info(
            "Initialized RAG-Anything instance for workspace %s at %s",
            workspace_id,
            workspace_dir,
        )
        return rag

    async def ingest_content(
        self,
        workspace_id: str,
        document_id: str,
        content_list: List[dict],
        file_path: str,
        doc_id: Optional[str] = None,
    ) -> str:
        """Ingest content_list for a document into RAG storage.

        Returns the rag_doc_id used by the engine.
        """
        rag = self._get_rag_instance(workspace_id)

        # Use the document_id as RAG document identifier by default so that
        # DB ↔ RAG mapping is straightforward.
        rag_doc_id = doc_id or str(document_id)

        logger.info(
            "Ingesting content_list for workspace=%s document_id=%s rag_doc_id=%s (%d blocks)",
            workspace_id,
            document_id,
            rag_doc_id,
            len(content_list),
        )

        await rag.insert_content_list(
            content_list=content_list,
            file_path=file_path,
            doc_id=rag_doc_id,
        )

        logger.info(
            "Completed ingest for workspace=%s document_id=%s rag_doc_id=%s",
            workspace_id,
            document_id,
            rag_doc_id,
        )
        return rag_doc_id

    async def query(
        self,
        workspace_id: str,
        question: str,
        system_prompt: Optional[str] = None,
        mode: str = "mix",
    ) -> Dict[str, Any]:
        """Query RAG for a workspace and return answer + citations.

        If the underlying LLM/embedding configuration is missing (e.g. no
        OPENAI_API_KEY), this will return a graceful fallback answer instead
        of raising an internal error.
        """
        # Guard: if no API key is configured, avoid calling into RAG-Anything
        # which would fail anyway and surface as a 500 to clients.
        if not os.getenv("OPENAI_API_KEY"):
            logger.error(
                "OPENAI_API_KEY is not set; skipping RAG query for workspace=%s",
                workspace_id,
            )
            return {
                "answer": (
                    "Xin lỗi, engine RAG chưa được cấu hình LLM (OPENAI_API_KEY) nên hiện tại mình "
                    "chưa thể trả lời dựa trên tài liệu. Bạn hãy cấu hình khóa API trước rồi thử lại nhé."
                ),
                "citations": [],
            }
        rag = self._get_rag_instance(workspace_id)

        # Ensure LightRAG is initialized for this RAGAnything instance. This is
        # required because aquery() expects a non-None lightrag, and ingestion
        # may have been performed in a different process.
        try:
            init_result = await rag._ensure_lightrag_initialized()
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to initialize LightRAG for workspace=%s: %s",
                workspace_id,
                str(exc),
            )
            raise
        if isinstance(init_result, dict) and not init_result.get("success", True):
            logger.error(
                "LightRAG initialization reported failure for workspace=%s: %s",
                workspace_id,
                init_result.get("error"),
            )
            raise RuntimeError(f"Failed to initialize RAG engine for workspace {workspace_id}")

        # Merge caller-provided system prompt (if any) with the default persona,
        # and add a light instruction to prefer JSON output when possible so we
        # can extract citations in a structured way.
        base_prompt = system_prompt or RAG_DEFAULT_SYSTEM_PROMPT
        effective_system_prompt = (
            base_prompt
            + "\n\n"
            + "Khi có thể, hãy trả về JSON với cấu trúc:\n"
            + '{ "answer": "<câu trả lời>", "citations": [] }\n'
            + "Nếu không đáp ứng được, vẫn có thể trả lời bình thường."
        )

        query_mode = mode or self.settings.query_mode

        # Vì phiên bản RAG-Anything hiện tại không nhận system_prompt trực tiếp
        # (system_prompt sẽ bị đẩy vào kwargs và gây lỗi QueryParam), ta ghép
        # persona + hướng dẫn JSON vào ngay trong prompt truy vấn.
        combined_query = (
            effective_system_prompt
            + "\n\n"
            + "Câu hỏi của người dùng:\n"
            + question
        )

        logger.info(
            "Querying RAG for workspace=%s mode=%s question_preview=%s",
            workspace_id,
            query_mode,
            question[:80],
        )

        raw_result = await rag.aquery(
            combined_query,
            mode=query_mode,
        )

        answer: str = raw_result
        citations: List[Dict[str, Any]] = []

        # Best-effort: if the model followed the JSON instruction, parse it.
        try:
            parsed = json.loads(raw_result)
            if isinstance(parsed, dict) and "answer" in parsed:
                answer = str(parsed.get("answer", ""))
                raw_citations = parsed.get("citations") or []
                if isinstance(raw_citations, list):
                    # We don't enforce a strict schema here; the API layer can
                    # treat these as opaque metadata.
                    citations = [c for c in raw_citations if isinstance(c, dict)]
        except (json.JSONDecodeError, TypeError):
            # Model returned plain text; treat entire result as answer.
            logger.debug("RAG query result is not valid JSON; using raw text as answer.")

        logger.info(
            "RAG query completed for workspace=%s (citations=%d)",
            workspace_id,
            len(citations),
        )

        return {"answer": answer, "citations": citations}

    async def delete_document(self, workspace_id: str, rag_doc_id: str) -> None:
        """Delete a document from RAG storage."""
        # Current RAG-Anything / LightRAG APIs do not expose a simple document
        # deletion mechanism. For Phase 3/4 we treat this as a logical delete
        # at the application layer (DB + mapping). Physical cleanup of vectors
        # will be implemented when the library exposes a stable API.
        logger.warning(
            "delete_document called for workspace=%s rag_doc_id=%s, "
            "but physical deletion is not implemented and will be a no-op.",
            workspace_id,
            rag_doc_id,
        )

    async def delete_workspace_data(self, workspace_id: str) -> None:
        """Best-effort cleanup for a workspace's RAG storage directory.

        This removes the per-workspace working_dir on disk so that RAG data
        for a deleted workspace does not accumulate indefinitely.
        """
        workspace_dir = os.path.join(self.settings.working_dir, workspace_id)
        try:
            if os.path.isdir(workspace_dir):
                import shutil

                shutil.rmtree(workspace_dir, ignore_errors=True)
                logger.info("Deleted RAG workspace directory %s", workspace_dir)
            else:
                logger.info("RAG workspace directory %s does not exist; nothing to delete", workspace_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to delete RAG workspace directory %s: %s",
                workspace_dir,
                str(exc),
            )
