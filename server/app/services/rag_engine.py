"""RAG Engine wrapper around RAG-Anything / LightRAG (Phase 3).

This module defines a thin adapter so that the rest of the backend does
not depend directly on RAG-Anything internals.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, Dict, List, Optional

from server.app.core.constants import RAG_DEFAULT_SYSTEM_PROMPT
from server.app.core.config import RagSettings, get_settings
from server.app.core.logging import get_logger


logger = get_logger(__name__)

# Regex to detect SEG tags embedded in ingested text, e.g.:
# [SEG={document_uuid}:{segment_index}]
_SEG_TAG_PATTERN = re.compile(
    r"\[SEG=(?P<id>[0-9a-fA-F\-]{36}:\d+)\]",
    flags=re.MULTILINE,
)


class RagEngineService:
    """Adapter between application code and RAG-Anything."""

    def __init__(self, settings: RagSettings | None = None) -> None:
        self.settings: RagSettings = settings or get_settings().rag
        # Actual RAG-Anything / LightRAG instances are initialized lazily per workspace.
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
        # Disable asyncpg statement cache when going through PgBouncer transaction pooler,
        # as recommended by asyncpg docs and error hints.
        os.environ.setdefault("POSTGRES_STATEMENT_CACHE_SIZE", "0")
        # Ensure EMBEDDING_DIM matches the OpenAI embedding model we use (text-embedding-3-large → 3072 dims)
        # so that PGVector tables are created with the correct vector dimension.
        os.environ.setdefault("EMBEDDING_DIM", "3072")

        logger.info(
            "Configured LightRAG POSTGRES_* from SUPABASE_DB_URL (host=%s, db=%s); "
            "statement_cache_size=0, SSL mode using asyncpg defaults",
            host,
            database,
        )

    def _get_rag_instance(self, workspace_id: str) -> Any:
        """Return (and lazily create) a RAGAnything instance for a workspace.

        Each workspace gets its own LightRAG working directory so knowledge
        is naturally isolated at the storage layer.
        """
        if workspace_id in self._instances:
            return self._instances[workspace_id]

        # Ensure LightRAG PGVector storage can connect to the same Supabase DB.
        self._ensure_postgres_env_from_supabase()

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

        # Configure LightRAG to use Supabase Postgres + PGVector as storage backend.
        # Workspace isolation is enforced via the LightRAG workspace field, which
        # maps to a "workspace" column in the lightrag_* tables.
        lightrag_kwargs: Dict[str, Any] = {
            "working_dir": workspace_dir,
            "workspace": workspace_id,
            "kv_storage": "PGKVStorage",
            "vector_storage": "PGVectorStorage",
            "doc_status_storage": "PGDocStatusStorage",
            "vector_db_storage_cls_kwargs": {
                # Align with LightRAG default cosine threshold (0.2) unless
                # overridden later; this can be tuned if needed.
                "cosine_better_than_threshold": 0.2,
            },
        }

        rag = RAGAnything(
            config=config,
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
            lightrag_kwargs=lightrag_kwargs,
        )
        self._instances[workspace_id] = rag
        logger.info(
            "Initialized RAG-Anything instance for workspace %s at %s using PGVector storage",
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

    async def get_segment_ids_for_query(
        self,
        workspace_id: str,
        question: str,
        mode: Optional[str] = None,
    ) -> List[str]:
        """Retrieve SEG-based segment IDs for a query without calling any LLM.

        This uses LightRAG's query pipeline in \"only_need_prompt\" mode to
        obtain the raw retrieval prompt, then extracts all
        [SEG={document_id}:{index}] tags in order. IDs are normalized to
        canonical UUID strings and integer indices.
        """
        rag = self._get_rag_instance(workspace_id)

        raw_str = await self._get_raw_prompt_for_query(
            rag=rag,
            workspace_id=workspace_id,
            question=question,
            mode=mode,
        )

        # Extract normalized segment IDs in order of appearance.
        seen: set[str] = set()
        ordered_ids: List[str] = []

        for match in _SEG_TAG_PATTERN.finditer(raw_str):
            seg_id = match.group("id")
            if not seg_id:
                continue
            parts = seg_id.split(":", 1)
            if len(parts) != 2:
                continue
            doc_part, seg_part = parts
            try:
                doc_uuid = uuid.UUID(doc_part)
                seg_idx = int(seg_part)
            except (ValueError, TypeError, AttributeError):
                continue
            normalized = f"{doc_uuid}:{seg_idx}"
            if normalized in seen:
                continue
            seen.add(normalized)
            ordered_ids.append(normalized)

        logger.info(
            "Retrieved %d unique SEG IDs for workspace=%s",
            len(ordered_ids),
            workspace_id,
        )

        return ordered_ids

    async def _get_raw_prompt_for_query(
        self,
        rag: Any,
        workspace_id: str,
        question: str,
        mode: Optional[str] = None,
    ) -> str:
        """Call LightRAG in only_need_prompt mode and return the raw prompt string."""

        # Ensure LightRAG is initialized for this RAGAnything instance. This is
        # required because lightrag.aquery() expects storages to be ready.
        try:
            init_result = await rag._ensure_lightrag_initialized()
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to initialize LightRAG for workspace=%s when retrieving segment IDs: %s",
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

        # Build a LightRAG QueryParam with only_need_prompt=True so that the
        # retrieval prompt is returned without generating a final answer via LLM.
        try:
            from lightrag import QueryParam  # type: ignore[import]
        except ImportError as exc:  # pragma: no cover - environment/config issue
            raise RuntimeError(
                "LightRAG must be installed to use get_segment_ids_for_query."
            ) from exc

        query_mode = mode or self.settings.query_mode
        query_param = QueryParam(mode=query_mode, only_need_prompt=True)

        logger.info(
            "Retrieving segment IDs (only_need_prompt) for workspace=%s mode=%s question_preview=%s",
            workspace_id,
            query_mode,
            question[:80],
        )

        raw_prompt = await rag.lightrag.aquery(question, param=query_param)
        raw_str = str(raw_prompt or "").strip()
        # Log a truncated preview for debugging.
        logger.info(
            "LightRAG raw prompt for workspace=%s (first 2000 chars): %s",
            workspace_id,
            raw_str[:2000],
        )
        return raw_str

    async def get_segments_for_query(
        self,
        workspace_id: str,
        question: str,
        mode: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve context segments (segment_id + text) for a query.

        This calls LightRAG in only_need_prompt mode and then parses the
        returned prompt to extract each [SEG={document_id}:{segment_index}]
        marker together with the text that follows it up to the next marker.

        The result is a list of dicts:
        {
          "segment_id": "doc_uuid:segment_index",
          "document_id": "doc_uuid",
          "segment_index": int,
          "text": "<segment text as seen by LightRAG>",
        }

        No additional ranking or DB access is performed here; this method
        simply reflects the context that RAG-Anything / LightRAG decided
        to use for the query.
        """
        rag = self._get_rag_instance(workspace_id)
        raw_str = await self._get_raw_prompt_for_query(
            rag=rag,
            workspace_id=workspace_id,
            question=question,
            mode=mode,
        )

        segments: List[Dict[str, Any]] = []

        # Find all SEG markers and slice text between them.
        matches = list(_SEG_TAG_PATTERN.finditer(raw_str))
        for idx, match in enumerate(matches):
            seg_id = match.group("id")
            if not seg_id:
                continue
            parts = seg_id.split(":", 1)
            if len(parts) != 2:
                continue
            doc_part, seg_part = parts
            try:
                doc_uuid = uuid.UUID(doc_part)
                seg_idx = int(seg_part)
            except (ValueError, TypeError, AttributeError):
                continue

            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw_str)
            text = raw_str[start:end].strip()
            if not text:
                continue

            segments.append(
                {
                    "segment_id": f"{doc_uuid}:{seg_idx}",
                    "document_id": str(doc_uuid),
                    "segment_index": seg_idx,
                    "text": text,
                }
            )

        logger.info(
            "Parsed %d context segments from LightRAG prompt for workspace=%s",
            len(segments),
            workspace_id,
        )

        return segments

    async def query(
        self,
        workspace_id: str,
        question: str,
        system_prompt: Optional[str] = None,
        mode: str = "mix",
    ) -> Dict[str, Any]:
        """Query RAG for a workspace and return answer + sections.

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
                "sections": [],
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
        # and append explicit JSON instructions (in English) so that the backend
        # can reliably extract sections + source_ids from the model output.
        base_prompt = system_prompt or RAG_DEFAULT_SYSTEM_PROMPT
        effective_system_prompt = (
            base_prompt
            + "\n\n"
            + "You will see context passages prefixed with tags in the form:\n"
            + "[SEG={document_id}:{segment_index}] <segment text>\n\n"
            + "Read the text normally, but ALWAYS keep track of these SEG IDs when you reference sources.\n\n"
            + "When possible, respond with a **SINGLE VALID JSON** object using the following structure:\n"
            + '{\n'
            + '  "sections": [\n'
            + '    {\n'
            + '      "text": "<answer section 1>",\n'
            + '      "source_ids": ["{document_id}:{segment_index}", "..."]\n'
            + "    },\n"
            + '    {\n'
            + '      "text": "<answer section 2>",\n'
            + '      "source_ids": ["{document_id}:{segment_index}"]\n'
            + "    }\n"
            + "  ]\n"
            + "}\n\n"
            + "- Every element in source_ids MUST come from a [SEG=...] tag that appears in the context.\n"
            + "- Do NOT invent new IDs that were not present in the context.\n"
            + "- If you cannot fully follow this format, return the closest valid JSON you can.\n"
            + "- If you absolutely cannot return JSON, then answer in plain text."
        )

        query_mode = mode or self.settings.query_mode

        # RAG-Anything's aquery does not accept system_prompt directly; it would
        # treat unknown kwargs as QueryParam and fail. Therefore we concatenate
        # persona + JSON instructions directly into the query text.
        combined_query = (
            effective_system_prompt
            + "\n\n"
            + "User question:\n"
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
        sections: List[Dict[str, Any]] = []

        # Best-effort: if the model followed the JSON instruction, parse it.
        # Nhiều model sẽ wrap JSON trong ```json ... ```, nên ta cố gắng
        # bóc ra phần {...} trước khi parse để tránh JSON bị show thẳng cho user.
        candidate_payloads: List[str] = []
        raw_str = raw_result.strip()
        candidate_payloads.append(raw_str)

        # Heuristic: nếu có dấu { và }, thử trích đoạn từ { đầu tiên tới } cuối cùng.
        start_brace = raw_str.find("{")
        end_brace = raw_str.rfind("}")
        if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
            inner = raw_str[start_brace : end_brace + 1].strip()
            if inner and inner != raw_str:
                candidate_payloads.insert(0, inner)

        parsed: Dict[str, Any] | None = None
        for payload in candidate_payloads:
            try:
                obj = json.loads(payload)
                if isinstance(obj, dict) and "sections" in obj:
                    parsed = obj
                    break
            except (json.JSONDecodeError, TypeError):
                continue

        try:
            if parsed is not None and isinstance(parsed, dict) and "sections" in parsed:
                raw_sections = parsed.get("sections") or []
            if isinstance(parsed, dict) and "sections" in parsed:
                raw_sections = parsed.get("sections") or []
                if isinstance(raw_sections, list):
                    for sec in raw_sections:
                        if not isinstance(sec, dict):
                            continue
                        text_val = sec.get("text")
                        if not isinstance(text_val, str):
                            continue
                        source_ids_val = sec.get("source_ids") or []

                        source_ids_clean: List[str] = []
                        if isinstance(source_ids_val, list):
                            for raw_id in source_ids_val:
                                if not isinstance(raw_id, str):
                                    continue
                                raw_id = raw_id.strip()
                                if not raw_id:
                                    continue
                                parts = raw_id.split(":", 1)
                                if len(parts) != 2:
                                    continue
                                doc_part, seg_part = parts
                                # Chỉ chấp nhận ID có document_id là UUID hợp lệ
                                # và segment_index là số nguyên.
                                try:
                                    doc_uuid = uuid.UUID(doc_part)
                                    _ = int(seg_part)
                                except (ValueError, AttributeError):
                                    continue
                                source_ids_clean.append(f"{doc_uuid}:{int(seg_part)}")

                        sections.append({"text": text_val, "source_ids": source_ids_clean})

                if sections:
                    # Build answer text by joining section texts with double newlines.
                    answer = "\n\n".join(str(sec["text"]) for sec in sections)
        except (json.JSONDecodeError, TypeError):
            # Model returned plain text; treat entire result as answer.
            logger.debug("RAG query result is not valid JSON; using raw text as answer.")

        logger.info(
            "RAG query completed for workspace=%s (sections=%d)",
            workspace_id,
            len(sections),
        )

        return {"answer": answer, "sections": sections}

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
