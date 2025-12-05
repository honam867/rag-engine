"""Parser pipeline service (Phase 2).

Responsible for orchestrating parse_jobs:
  - Load job and associated document/file metadata.
  - Download file bytes from R2.
  - Call Document AI OCR.
  - Persist docai_full_text and JSON raw key.
  - Update job and document statuses.

Implementation is deferred to Phase 2; this file only establishes the interface.
"""

from __future__ import annotations

from typing import Callable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.core.constants import (
    DOCUMENT_STATUS_ERROR,
    DOCUMENT_STATUS_PARSED,
    PARSE_JOB_STATUS_FAILED,
    PARSE_JOB_STATUS_QUEUED,
    PARSE_JOB_STATUS_RUNNING,
    PARSE_JOB_STATUS_SUCCESS,
)
from server.app.core.logging import get_logger
from server.app.core.event_bus import event_bus
from server.app.db import models, repositories as repo
from server.app.services import storage_r2
from server.app.services.docai_client import DocumentAIClient


class ParserPipelineService:
    """Service orchestrating parse_jobs → Document AI → DB updates."""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        docai_client: DocumentAIClient | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._docai_client = docai_client or DocumentAIClient()
        self._logger = get_logger(__name__)

    async def process_single_job(self, job_id: str) -> None:
        """Process a single parse_job.

        See `docs/design/phase-2-design.md` for the detailed steps.
        """
        async with self._session_factory() as session:  # type: ignore[call-arg]
            assert isinstance(session, AsyncSession)
            job = await repo.get_parse_job(session, job_id=job_id)
            if not job:
                self._logger.warning("parse_job not found", extra={"job_id": job_id})
                return

            document_id = str(job["document_id"])
            retry_count = int(job.get("retry_count", 0) or 0)

            # Load workspace + owner for realtime notifications.
            doc_stmt = (
                sa.select(models.documents.c.workspace_id)
                .where(models.documents.c.id == document_id)
                .limit(1)
            )
            doc_result = await session.execute(doc_stmt)
            doc_row = doc_result.fetchone()
            if not doc_row:
                self._logger.warning(
                    "Document not found for parse_job", extra={"job_id": job_id, "document_id": document_id}
                )
                return
            workspace_id = str(doc_row[0])
            user_id = await repo.get_workspace_owner_id(session, workspace_id=workspace_id)

        # Mark job running in a separate transaction.
        async with self._session_factory() as session:  # type: ignore[call-arg]
            await repo.mark_parse_job_running(session, job_id=job_id)
        if user_id:
            try:
                await event_bus.publish(
                    user_id,
                    "job.status_updated",
                    {
                        "job_id": job_id,
                        "job_type": "parse",
                        "workspace_id": workspace_id,
                        "document_id": document_id,
                        "status": PARSE_JOB_STATUS_RUNNING,
                        "retry_count": retry_count,
                        "error_message": job.get("error_message"),
                    },
                )
            except Exception:  # noqa: BLE001
                # Realtime is best-effort; do not break parse pipeline.
                pass

        try:
            # Load file metadata for the document.
            async with self._session_factory() as session:  # type: ignore[call-arg]
                stmt = sa.select(models.files).where(models.files.c.document_id == document_id).limit(1)
                result = await session.execute(stmt)
                row = result.fetchone()
                if not row:
                    raise RuntimeError("No file metadata found for document")
                file_row = row._mapping

            r2_key = file_row["r2_key"]
            mime_type = file_row["mime_type"]

            # Download file bytes from R2.
            file_bytes = await storage_r2.download_file(r2_key)

            # Call Document AI.
            doc = await self._docai_client.process_document_ocr(file_bytes=file_bytes, mime_type=mime_type)
            full_text = doc.get("text", "") or ""
            if not full_text:
                raise RuntimeError("Document AI returned empty text")

            raw_key = f"docai-raw/{document_id}.json"
            await storage_r2.upload_json(doc, key=raw_key)

            # Persist document fields and mark job success.
            async with self._session_factory() as session:  # type: ignore[call-arg]
                await repo.update_document_parsed_success(
                    session=session, document_id=document_id, full_text=full_text, raw_r2_key=raw_key
                )
                await repo.mark_parse_job_success(session=session, job_id=job_id)
            self._logger.info("parse_job processed successfully", extra={"job_id": job_id, "document_id": document_id})

            # Realtime notifications for success.
            if user_id:
                try:
                    await event_bus.publish(
                        user_id,
                        "document.status_updated",
                        {
                            "workspace_id": workspace_id,
                            "document_id": document_id,
                            "status": DOCUMENT_STATUS_PARSED,
                        },
                    )
                    await event_bus.publish(
                        user_id,
                        "job.status_updated",
                        {
                            "job_id": job_id,
                            "job_type": "parse",
                            "workspace_id": workspace_id,
                            "document_id": document_id,
                            "status": PARSE_JOB_STATUS_SUCCESS,
                            "retry_count": retry_count,
                            "error_message": None,
                        },
                    )
                except Exception:  # noqa: BLE001
                    pass
        except Exception as exc:  # noqa: BLE001
            self._logger.error(
                "parse_job processing failed",
                extra={"job_id": job_id, "document_id": document_id, "error": str(exc)},
            )
            # Decide whether to retry or mark as failed based on retry_count.
            async with self._session_factory() as session:  # type: ignore[call-arg]
                # Refresh job to get latest retry_count in case of concurrent updates.
                latest = await repo.get_parse_job(session, job_id=job_id)
                latest_retry = int(latest.get("retry_count", retry_count) or 0) if latest else retry_count
                max_retries = 3
                if latest_retry < max_retries:
                    await repo.requeue_parse_job(
                        session=session,
                        job_id=job_id,
                        retry_count=latest_retry + 1,
                        error_message=str(exc),
                    )
                    new_status = PARSE_JOB_STATUS_QUEUED
                    new_retry = latest_retry + 1
                    final_failure = False
                else:
                    await repo.mark_parse_job_failed(session=session, job_id=job_id, error_message=str(exc))
                    await repo.update_document_parse_error(session=session, document_id=document_id)
                    new_status = PARSE_JOB_STATUS_FAILED
                    new_retry = latest_retry
                    final_failure = True

            if user_id:
                try:
                    # Job status update.
                    await event_bus.publish(
                        user_id,
                        "job.status_updated",
                        {
                            "job_id": job_id,
                            "job_type": "parse",
                            "workspace_id": workspace_id,
                            "document_id": document_id,
                            "status": new_status,
                            "retry_count": new_retry,
                            "error_message": str(exc),
                        },
                    )
                    if final_failure:
                        await event_bus.publish(
                            user_id,
                            "document.status_updated",
                            {
                                "workspace_id": workspace_id,
                                "document_id": document_id,
                                "status": DOCUMENT_STATUS_ERROR,
                            },
                        )
                except Exception:  # noqa: BLE001
                    pass

    async def fetch_and_process_next_jobs(self, batch_size: int = 1) -> int:
        """Fetch a batch of queued jobs and process them.

        Returns the number of jobs processed (success + failed).
        """
        async with self._session_factory() as session:  # type: ignore[call-arg]
            jobs = await repo.fetch_queued_parse_jobs(session, batch_size=batch_size)

        processed = 0
        for job in jobs:
            await self.process_single_job(job_id=str(job["id"]))
            processed += 1
        return processed
