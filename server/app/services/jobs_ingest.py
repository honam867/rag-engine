"""Ingestion job service (Phase 3).

Responsible for taking documents that have been parsed (status='parsed')
and ingesting them into the RAG engine, updating `rag_documents` and
document statuses.
"""

from __future__ import annotations

from typing import Callable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.core.constants import DOCUMENT_STATUS_INGESTED, DOCUMENT_STATUS_PARSED
from server.app.core.logging import get_logger
from server.app.core.realtime import send_event_to_user
from server.app.db import models, repositories as repo
from server.app.services.chunker import ChunkerService
from server.app.services.rag_engine import RagEngineService


class IngestJobService:
    """Service responsible for ingesting parsed documents into RAG."""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        chunker: ChunkerService,
        rag_engine: RagEngineService,
    ) -> None:
        self._session_factory = session_factory
        self._chunker = chunker
        self._rag_engine = rag_engine
        self._logger = get_logger(__name__)

    async def ingest_document(self, document_id: str) -> None:
        """Ingest a single parsed document into RAG."""
        # Load document + file metadata and ensure it is in the correct state.
        async with self._session_factory() as session:  # type: ignore[call-arg]
            assert isinstance(session, AsyncSession)

            doc_stmt = sa.select(models.documents).where(models.documents.c.id == document_id)
            doc_result = await session.execute(doc_stmt)
            doc_row = doc_result.fetchone()
            if not doc_row:
                self._logger.warning("Document not found for ingestion", extra={"document_id": document_id})
                return
            document = doc_row._mapping

            if document["status"] != DOCUMENT_STATUS_PARSED:
                # Only ingest documents that have been successfully parsed.
                self._logger.info(
                    "Skipping ingestion for document with non-parsed status",
                    extra={"document_id": document_id, "status": document["status"]},
                )
                return

            file_stmt = sa.select(models.files).where(models.files.c.document_id == document_id).limit(1)
            file_result = await session.execute(file_stmt)
            file_row = file_result.fetchone()
            if not file_row:
                raise RuntimeError(f"No file metadata found for document id={document_id}")
            file = file_row._mapping

        workspace_id = str(document["workspace_id"])
        original_filename = str(file["original_filename"])
        file_path = f"{workspace_id}/{document_id}/{original_filename}"

        try:
            # Build content_list from OCR text.
            content_list = await self._chunker.build_content_list_from_document(document_id=document_id)

            # Ingest into RAG engine.
            rag_doc_id = await self._rag_engine.ingest_content(
                workspace_id=workspace_id,
                document_id=document_id,
                content_list=content_list,
                file_path=file_path,
                doc_id=str(document_id),
            )

            # Persist mapping and mark document as ingested.
            async with self._session_factory() as session:  # type: ignore[call-arg]
                await repo.insert_rag_document(session=session, document_id=document_id, rag_doc_id=rag_doc_id)
                await repo.update_document_ingested_success(session=session, document_id=document_id)

            self._logger.info(
                "Document ingested into RAG",
                extra={
                    "document_id": document_id,
                    "workspace_id": workspace_id,
                    "rag_doc_id": rag_doc_id,
                    "file_path": file_path,
                    "chunks": len(content_list),
                },
            )
            # Realtime notification: document is now ingested/ready.
            try:
                async with self._session_factory() as session:  # type: ignore[call-arg]
                    owner_id = await repo.get_workspace_owner_id(session, workspace_id=workspace_id)
                if owner_id:
                    await send_event_to_user(
                        owner_id,
                        "document.status_updated",
                        {
                            "workspace_id": workspace_id,
                            "document_id": document_id,
                            "status": DOCUMENT_STATUS_INGESTED,
                        },
                    )
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            # Keep document in 'parsed' state so ingestion can be retried later.
            self._logger.error(
                "Failed to ingest document into RAG",
                extra={"document_id": document_id, "workspace_id": workspace_id, "error": str(exc)},
            )

    async def ingest_pending_documents(self, batch_size: int = 1) -> int:
        """Ingest a batch of parsed documents that have no rag_documents mapping."""
        async with self._session_factory() as session:  # type: ignore[call-arg]
            assert isinstance(session, AsyncSession)
            docs = await repo.list_parsed_documents_without_rag(session, batch_size=batch_size)

        processed = 0
        for doc in docs:
            await self.ingest_document(document_id=str(doc["id"]))
            processed += 1

        return processed
