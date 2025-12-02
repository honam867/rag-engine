"""RAG Engine wrapper around RAG-Anything / LightRAG (Phase 3).

This module defines a thin adapter so that the rest of the backend does
not depend directly on RAG-Anything internals.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from server.app.core.config import RagSettings, get_settings


class RagEngineService:
    """Adapter between application code and RAG-Anything."""

    def __init__(self, settings: RagSettings | None = None) -> None:
        self.settings: RagSettings = settings or get_settings().rag
        # Actual RAG-Anything / LightRAG instances will be initialized lazily per workspace in Phase 3.
        self._instances: dict[str, Any] = {}

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
        raise NotImplementedError("Phase 3 - RagEngineService.ingest_content is not implemented yet")

    async def query(
        self,
        workspace_id: str,
        question: str,
        system_prompt: Optional[str] = None,
        mode: str = "mix",
    ) -> Dict[str, Any]:
        """Query RAG for a workspace and return answer + citations."""
        raise NotImplementedError("Phase 3 - RagEngineService.query is not implemented yet")

    async def delete_document(self, workspace_id: str, rag_doc_id: str) -> None:
        """Delete a document from RAG storage."""
        raise NotImplementedError("Phase 3 - RagEngineService.delete_document is not implemented yet")

