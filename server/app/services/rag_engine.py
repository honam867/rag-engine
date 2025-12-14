"""RAG Engine wrapper around LightRAG (Phase 9).

This module defines a thin adapter so that the rest of the backend does
not depend directly on LightRAG internals.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from server.app.core.config import RagSettings, get_settings
from server.app.core.logging import get_logger


logger = get_logger(__name__)


DEEP_RAG_USER_PROMPT = (
    "When answering the user query: "
    "1) Provide a detailed, step-by-step answer grounded only in the provided context; "
    "2) Add 1–3 short insights that highlight important patterns, caveats, or implications for the user; "
    "3) Add a short 'Follow-up questions' subsection with 2–3 concrete questions the user could ask to go deeper. "
    "Place the 'Follow-up questions' subsection before the `### References` section. "
    "If the context does not contain enough information to answer a part of the question, explicitly say that this "
    "information is not present in the context instead of guessing."
)


def _infer_embedding_dim(model_name: str) -> int:
    """Best-effort mapping from embedding model name → vector dimension.

    - text-embedding-3-small → 1536
    - text-embedding-3-large → 3072
    - fallback: 3072 (giữ nguyên behavior cũ nếu không rõ).
    """
    name = (model_name or "").lower()
    if "text-embedding-3-small" in name:
        return 1536
    if "text-embedding-3-large" in name:
        return 3072
    # Default: keep 3072 to match previous phases using text-embedding-3-large.
    return 3072

class RagEngineService:
    """Adapter between application code and LightRAG."""

    def __init__(self, settings: RagSettings | None = None) -> None:
        self.settings: RagSettings = settings or get_settings().rag
        # LightRAG instances are initialized lazily per workspace.
        self._instances: dict[str, Any] = {}

    def _ensure_postgres_env_from_supabase(self) -> None:
        """Derive POSTGRES_* env vars for LightRAG from SUPABASE_DB_URL if needed.

        LightRAG's PGVector backends read connection info from POSTGRES_* variables.
        To avoid duplicating config, we parse SUPABASE_DB_URL once and populate
        POSTGRES_* only when they are not already set.
        """
        # If POSTGRES_DATABASE is already set, assume the rest are configured.
        if os.getenv("POSTGRES_DATABASE"):
            return

        try:
            from sqlalchemy.engine.url import make_url
        except ImportError:
            logger.warning(
                "sqlalchemy is not available; cannot derive POSTGRES_* from SUPABASE_DB_URL."
            )
            return

        supabase_url = get_settings().database.db_url
        if not supabase_url:
            logger.warning(
                "SUPABASE_DB_URL is empty; cannot derive POSTGRES_* for LightRAG."
            )
            return

        try:
            url = make_url(supabase_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to parse SUPABASE_DB_URL for LightRAG Postgres config: %s", exc
            )
            return

        host = url.host or "localhost"
        port = url.port or 5432
        username = url.username or ""
        password = url.password or ""
        database = url.database or "postgres"

        os.environ.setdefault("POSTGRES_HOST", host)
        os.environ.setdefault("POSTGRES_PORT", str(port))
        os.environ.setdefault("POSTGRES_USER", username)
        os.environ.setdefault("POSTGRES_PASSWORD", password)
        os.environ.setdefault("POSTGRES_DATABASE", database)
        os.environ.setdefault("POSTGRES_MAX_CONNECTIONS", "10")
        # Disable asyncpg statement cache when going through PgBouncer transaction pooler.
        os.environ.setdefault("POSTGRES_STATEMENT_CACHE_SIZE", "0")

        # Ensure EMBEDDING_DIM matches the OpenAI embedding model we use so that
        # PGVector tables are created with the correct vector dimension.
        rag_settings = get_settings().rag
        emb_dim = _infer_embedding_dim(rag_settings.embedding_model)
        os.environ.setdefault("EMBEDDING_DIM", str(emb_dim))

        logger.info(
            "Configured LightRAG POSTGRES_* from SUPABASE_DB_URL (host=%s, db=%s); "
            "statement_cache_size=0, SSL mode using asyncpg defaults",
            host,
            database,
        )

    def _get_lightrag_instance(self, workspace_id: str) -> Any:
        """Return (and lazily create) a LightRAG instance for a workspace.

        Each workspace gets its own working directory so knowledge is
        naturally isolated at the storage layer.
        """
        if workspace_id in self._instances:
            return self._instances[workspace_id]

        # Ensure LightRAG PGVector storage can connect to the same Supabase DB.
        self._ensure_postgres_env_from_supabase()

        try:
            from lightrag import LightRAG  # type: ignore[import]
            from lightrag.llm.openai import openai_complete_if_cache, openai_embed  # type: ignore[import]
            from lightrag.utils import EmbeddingFunc  # type: ignore[import]
        except ImportError as exc:  # pragma: no cover - environment/config issue
            raise RuntimeError(
                "LightRAG (lightrag-hku) must be installed to use RagEngineService."
            ) from exc

        # Per-workspace storage directory under the configured base dir.
        workspace_dir = os.path.join(self.settings.working_dir, workspace_id)

        # Read model configuration from settings / environment.
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        llm_model_name = self.settings.llm_model
        embedding_model_name = self.settings.embedding_model
        embedding_dim = _infer_embedding_dim(embedding_model_name)
        llm_temperature = getattr(self.settings, "llm_temperature", 0.2)

        if not api_key:
            logger.warning(
                "OPENAI_API_KEY is not set; LightRAG LLM/embedding calls will fail until it is configured."
            )

        def llm_model_func(
            prompt: str,
            system_prompt: Optional[str] = None,
            history_messages: Optional[list] = None,
            **kwargs: Any,
        ) -> str:
            """Wrapper around LightRAG's OpenAI helper."""
            if history_messages is None:
                history_messages = []
            # Ensure a default temperature for all RAG LLM calls to keep
            # answers deterministic and grounded in retrieved context.
            kwargs.setdefault("temperature", llm_temperature)
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
            embedding_dim=embedding_dim,
            max_token_size=8192,
            func=lambda texts: openai_embed(
                texts,
                model=embedding_model_name,
                api_key=api_key,
                base_url=base_url,
            ),
        )

        # Configure LightRAG to use Supabase Postgres + PGVector as storage backend.
        # Workspace isolation is enforced via the LightRAG workspace field, which
        # maps to a "workspace" column in the lightrag_* tables.
        lightrag = LightRAG(
            working_dir=workspace_dir,
            workspace=workspace_id,
            kv_storage="PGKVStorage",
            vector_storage="PGVectorStorage",
            doc_status_storage="PGDocStatusStorage",
            embedding_func=embedding_func,
            llm_model_func=llm_model_func,
            vector_db_storage_cls_kwargs={
                "cosine_better_than_threshold": 0.2,
            },
        )

        self._instances[workspace_id] = lightrag
        logger.info(
            "Initialized LightRAG instance for workspace %s at %s using PGVector storage",
            workspace_id,
            workspace_dir,
        )
        return lightrag

    async def ingest_content(
        self,
        workspace_id: str,
        document_id: str,
        content_list: List[dict],
        file_path: str,
        doc_id: Optional[str] = None,
        chunks_info: Optional[List[dict]] = None,
    ) -> str:
        """Ingest document content into LightRAG.

        Phase 9.1:
        - If `chunks_info` is provided, we treat each entry as a macro-chunk and
          call `ainsert_custom_chunks` so that chunk IDs are stable and can be
          mapped back to document/segment ranges for citations.
        - If `chunks_info` is None, we fall back to the simpler Phase 9
          behavior: flatten content_list and let LightRAG chunk internally.
        """
        lightrag = self._get_lightrag_instance(workspace_id)

        # Ensure storages are initialized before inserting.
        await lightrag.initialize_storages()

        # Use the document_id as LightRAG document identifier by default so that
        # DB ↔ RAG mapping is straightforward.
        rag_doc_id = doc_id or str(document_id)

        # Concatenate all text blocks; ignore non-text fields.
        texts: List[str] = []
        for item in content_list:
            text = str(item.get("text") or "").strip()
            if text:
                texts.append(text)
        full_text = "\n\n".join(texts).strip()

        if not full_text:
            raise RuntimeError(
                f"Attempted to ingest empty content for document_id={document_id}"
            )

        logger.info(
            "Ingesting document into LightRAG workspace=%s document_id=%s rag_doc_id=%s (blocks=%d, chars=%d, custom_chunks=%s)",
            workspace_id,
            document_id,
            rag_doc_id,
            len(content_list),
            len(full_text),
            "yes" if chunks_info else "no",
        )

        if chunks_info:
            # Use custom chunks so that chunk_ids are deterministic from chunk_text.
            text_chunks: List[str] = [str(c.get("chunk_text") or "").strip() for c in chunks_info]
            # Filter out empty texts to avoid LightRAG errors.
            text_chunks = [c for c in text_chunks if c]
            if not text_chunks:
                raise RuntimeError(
                    f"Attempted to ingest with empty custom chunks for document_id={document_id}"
                )
            await lightrag.ainsert_custom_chunks(
                full_text=full_text,
                text_chunks=text_chunks,
                doc_id=rag_doc_id,
            )
        else:
            # Phase 9 fallback: let LightRAG perform its own chunking.
            await lightrag.ainsert(
                input=full_text,
                ids=rag_doc_id,
                file_paths=file_path,
            )

        logger.info(
            "Completed LightRAG ingest for workspace=%s document_id=%s rag_doc_id=%s",
            workspace_id,
            document_id,
            rag_doc_id,
        )
        return rag_doc_id

    async def query_answer(
        self,
        workspace_id: str,
        question: str,
        system_prompt: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query LightRAG for a workspace and return a plain-text answer.

        Phase 9 deliberately ignores structured citations and uses LightRAG's
        built-in LLM pipeline as the single source of truth. If the LLM
        configuration is missing, a graceful fallback answer is returned.
        """
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
            }

        lightrag = self._get_lightrag_instance(workspace_id)

        # Ensure storages are initialized before querying.
        await lightrag.initialize_storages()

        try:
            from lightrag import QueryParam  # type: ignore[import]
        except ImportError as exc:  # pragma: no cover - environment/config issue
            raise RuntimeError(
                "LightRAG must be installed to use RagEngineService.query_answer."
            ) from exc

        query_mode = mode or self.settings.query_mode
        param = QueryParam(mode=query_mode)
        # Instruct LightRAG's prompt builder to generate answers that are
        # more detailed, with extra insights and follow-up questions.
        param.user_prompt = DEEP_RAG_USER_PROMPT

        logger.info(
            "Querying LightRAG for workspace=%s mode=%s question_preview=%s",
            workspace_id,
            query_mode,
            question[:80],
        )

        raw = await lightrag.aquery_llm(
            question.strip(),
            param=param,
            system_prompt=system_prompt,
        )

        llm_resp = raw.get("llm_response", {}) if isinstance(raw, dict) else {}
        answer = str(llm_resp.get("content") or "").strip()

        if not answer:
            # If LightRAG returns no content, fall back to a safe message.
            answer = (
                "Xin lỗi, mình không thể tạo được câu trả lời cho câu hỏi này dựa trên tài liệu hiện có."
            )

        return {"answer": answer}

    async def retrieve_context(
        self,
        workspace_id: str,
        question: str,
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieve structured context (chunks) from LightRAG without generating an answer.

        This is the main entrypoint for Phase 9.1 source attribution v2. It
        wraps `LightRAG.aquery_data` and normalizes the result into a simple
        dict containing `chunks`, `references` and `metadata`.
        """
        if not os.getenv("OPENAI_API_KEY"):
            logger.error(
                "OPENAI_API_KEY is not set; skipping RAG retrieval for workspace=%s",
                workspace_id,
            )
            return {"chunks": [], "references": [], "metadata": {}}

        lightrag = self._get_lightrag_instance(workspace_id)
        await lightrag.initialize_storages()

        try:
            from lightrag import QueryParam  # type: ignore[import]
        except ImportError as exc:  # pragma: no cover - environment/config issue
            raise RuntimeError(
                "LightRAG must be installed to use RagEngineService.retrieve_context."
            ) from exc

        query_mode = mode or self.settings.query_mode
        param = QueryParam(mode=query_mode)

        logger.info(
            "Retrieving LightRAG context for workspace=%s mode=%s question_preview=%s",
            workspace_id,
            query_mode,
            question[:80],
        )

        raw = await lightrag.aquery_data(
            question.strip(),
            param=param,
        )

        if not isinstance(raw, dict):
            logger.warning("Unexpected aquery_data result type: %s", type(raw))
            return {"chunks": [], "references": [], "metadata": {}}

        data = raw.get("data") or {}
        chunks_raw = data.get("chunks") or []
        refs_raw = data.get("references") or []

        chunks: List[Dict[str, Any]] = []
        for item in chunks_raw:
            try:
                chunk_id = str(item.get("chunk_id") or "").strip()
                content = str(item.get("content") or "").strip()
            except Exception:  # noqa: BLE001
                continue
            if not chunk_id or not content:
                continue
            chunk = {
                "chunk_id": chunk_id,
                "content": content,
                "reference_id": item.get("reference_id"),
                "file_path": item.get("file_path"),
            }
            chunks.append(chunk)

        references: List[Dict[str, Any]] = []
        for ref in refs_raw:
            try:
                reference_id = str(ref.get("reference_id") or "").strip()
            except Exception:  # noqa: BLE001
                continue
            if not reference_id:
                continue
            references.append(
                {
                    "reference_id": reference_id,
                    "file_path": ref.get("file_path"),
                }
            )

        metadata = raw.get("metadata") or {}

        logger.info(
            "LightRAG retrieval produced %d chunks and %d references for workspace=%s",
            len(chunks),
            len(references),
            workspace_id,
        )

        return {
            "chunks": chunks,
            "references": references,
            "metadata": metadata,
        }

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
