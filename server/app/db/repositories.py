"""Repository helpers for Phase 1 using SQLAlchemy Core async."""

from typing import Any, Mapping, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.core.constants import (
    DOCUMENT_STATUS_ERROR,
    DOCUMENT_STATUS_INGESTED,
    DOCUMENT_STATUS_PARSED,
    DOCUMENT_STATUS_PENDING,
    PARSE_JOB_STATUS_FAILED,
    PARSE_JOB_STATUS_QUEUED,
    PARSE_JOB_STATUS_RUNNING,
    PARSE_JOB_STATUS_SUCCESS,
    PARSER_TYPE_GCP_DOCAI,
)
from server.app.db import models
from server.app.utils.ids import new_uuid


def _row_to_mapping(row: Any) -> Mapping[str, Any]:
    return row._mapping if row is not None else {}


# Workspace
async def create_workspace(session: AsyncSession, user_id: str, name: str, description: str | None = None) -> Mapping[str, Any]:
    workspace_id = new_uuid()
    stmt = (
        sa.insert(models.workspaces)
        .values(id=workspace_id, user_id=user_id, name=name, description=description)
        .returning(models.workspaces)
    )
    result = await session.execute(stmt)
    await session.commit()
    row = result.fetchone()
    return _row_to_mapping(row)


async def list_workspaces(session: AsyncSession, user_id: str) -> Sequence[Mapping[str, Any]]:
    stmt = (
        sa.select(models.workspaces)
        .where(models.workspaces.c.user_id == user_id)
        .order_by(models.workspaces.c.created_at.desc())
    )
    result = await session.execute(stmt)
    return [r._mapping for r in result.fetchall()]


async def get_workspace(session: AsyncSession, workspace_id: str, user_id: str) -> Mapping[str, Any] | None:
    stmt = sa.select(models.workspaces).where(
        models.workspaces.c.id == workspace_id,
        models.workspaces.c.user_id == user_id,
    )
    result = await session.execute(stmt)
    row = result.fetchone()
    return _row_to_mapping(row) if row else None


async def get_workspace_owner_id(session: AsyncSession, workspace_id: str) -> str | None:
    """Return user_id (owner) for a given workspace_id, or None if not found."""
    stmt = sa.select(models.workspaces.c.user_id).where(models.workspaces.c.id == workspace_id)
    result = await session.execute(stmt)
    row = result.fetchone()
    if not row:
        return None
    return str(row[0])


# Documents / Files / Parse Jobs
async def create_document(session: AsyncSession, workspace_id: str, title: str, source_type: str) -> Mapping[str, Any]:
    document_id = new_uuid()
    stmt = (
        sa.insert(models.documents)
        .values(
            id=document_id,
            workspace_id=workspace_id,
            title=title,
            source_type=source_type,
            status=DOCUMENT_STATUS_PENDING,
        )
        .returning(models.documents)
    )
    result = await session.execute(stmt)
    await session.commit()
    row = result.fetchone()
    return _row_to_mapping(row)


async def list_documents(session: AsyncSession, workspace_id: str) -> Sequence[Mapping[str, Any]]:
    stmt = (
        sa.select(models.documents)
        .where(models.documents.c.workspace_id == workspace_id)
        .order_by(models.documents.c.created_at.desc())
    )
    result = await session.execute(stmt)
    return [r._mapping for r in result.fetchall()]


async def get_document(session: AsyncSession, document_id: str, workspace_id: str) -> Mapping[str, Any] | None:
    stmt = sa.select(models.documents).where(
        models.documents.c.id == document_id,
        models.documents.c.workspace_id == workspace_id,
    )
    result = await session.execute(stmt)
    row = result.fetchone()
    return _row_to_mapping(row) if row else None


async def create_file(
    session: AsyncSession,
    document_id: str,
    r2_key: str,
    original_filename: str,
    mime_type: str,
    size_bytes: int,
    checksum: str,
    file_id: str | None = None,
) -> Mapping[str, Any]:
    file_id = file_id or new_uuid()
    stmt = (
        sa.insert(models.files)
        .values(
            id=file_id,
            document_id=document_id,
            r2_key=r2_key,
            original_filename=original_filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            checksum=checksum,
        )
        .returning(models.files)
    )
    result = await session.execute(stmt)
    await session.commit()
    row = result.fetchone()
    return _row_to_mapping(row)


async def create_parse_job(session: AsyncSession, document_id: str) -> Mapping[str, Any]:
    job_id = new_uuid()
    stmt = (
        sa.insert(models.parse_jobs)
        .values(
            id=job_id,
            document_id=document_id,
            status=PARSE_JOB_STATUS_QUEUED,
            parser_type=PARSER_TYPE_GCP_DOCAI,
        )
        .returning(models.parse_jobs)
    )
    result = await session.execute(stmt)
    await session.commit()
    row = result.fetchone()
    return _row_to_mapping(row)


async def get_parse_job(session: AsyncSession, job_id: str) -> Mapping[str, Any] | None:
    stmt = sa.select(models.parse_jobs).where(models.parse_jobs.c.id == job_id)
    result = await session.execute(stmt)
    row = result.fetchone()
    return _row_to_mapping(row) if row else None


async def fetch_queued_parse_jobs(session: AsyncSession, batch_size: int) -> Sequence[Mapping[str, Any]]:
    stmt = (
        sa.select(models.parse_jobs)
        .where(models.parse_jobs.c.status == PARSE_JOB_STATUS_QUEUED)
        .order_by(models.parse_jobs.c.id.asc())
        .limit(batch_size)
    )
    result = await session.execute(stmt)
    return [r._mapping for r in result.fetchall()]


async def get_latest_parse_job_for_document(session: AsyncSession, document_id: str) -> Mapping[str, Any] | None:
    stmt = sa.select(models.parse_jobs).where(models.parse_jobs.c.document_id == document_id).limit(1)
    result = await session.execute(stmt)
    row = result.fetchone()
    return _row_to_mapping(row) if row else None


async def mark_parse_job_running(session: AsyncSession, job_id: str) -> None:
    stmt = (
        sa.update(models.parse_jobs)
        .where(models.parse_jobs.c.id == job_id)
        .values(status=PARSE_JOB_STATUS_RUNNING, started_at=sa.func.now())
    )
    await session.execute(stmt)
    await session.commit()


async def mark_parse_job_success(session: AsyncSession, job_id: str) -> None:
    stmt = (
        sa.update(models.parse_jobs)
        .where(models.parse_jobs.c.id == job_id)
        .values(status=PARSE_JOB_STATUS_SUCCESS, finished_at=sa.func.now(), error_message=None)
    )
    await session.execute(stmt)
    await session.commit()


async def mark_parse_job_failed(session: AsyncSession, job_id: str, error_message: str) -> None:
    stmt = (
        sa.update(models.parse_jobs)
        .where(models.parse_jobs.c.id == job_id)
        .values(
            status=PARSE_JOB_STATUS_FAILED,
            finished_at=sa.func.now(),
            error_message=error_message[:1000],
        )
    )
    await session.execute(stmt)
    await session.commit()


async def requeue_parse_job(session: AsyncSession, job_id: str, retry_count: int, error_message: str | None = None) -> None:
    """Move a job back to queued state with incremented retry_count."""
    values: dict[str, Any] = {
        "status": PARSE_JOB_STATUS_QUEUED,
        "retry_count": retry_count,
        "started_at": None,
        "finished_at": None,
    }
    if error_message:
        values["error_message"] = error_message[:1000]
    stmt = sa.update(models.parse_jobs).where(models.parse_jobs.c.id == job_id).values(**values)
    await session.execute(stmt)
    await session.commit()


async def fetch_stale_running_parse_jobs(
    session: AsyncSession,
    older_than_seconds: int,
) -> Sequence[Mapping[str, Any]]:
    """Return parse_jobs stuck in running state longer than the given threshold.

    Uses started_at as the reference time; jobs without started_at are ignored.
    """
    if older_than_seconds <= 0:
        return []
    # Build a Postgres expression: started_at < now() - interval '<seconds> seconds'
    interval_expr = sa.text(f"interval '{older_than_seconds} seconds'")
    stmt = (
        sa.select(models.parse_jobs)
        .where(
            models.parse_jobs.c.status == PARSE_JOB_STATUS_RUNNING,
            models.parse_jobs.c.started_at.is_not(None),
            models.parse_jobs.c.started_at < sa.func.now() - interval_expr,
        )
    )
    result = await session.execute(stmt)
    return [r._mapping for r in result.fetchall()]


async def update_document_parsed_success(
    session: AsyncSession, document_id: str, full_text: str, raw_r2_key: str
) -> None:
    stmt = (
        sa.update(models.documents)
        .where(models.documents.c.id == document_id)
        .values(
            docai_full_text=full_text,
            docai_raw_r2_key=raw_r2_key,
            status=DOCUMENT_STATUS_PARSED,
            updated_at=sa.func.now(),
        )
    )
    await session.execute(stmt)
    await session.commit()


async def update_document_parse_error(session: AsyncSession, document_id: str) -> None:
    stmt = (
        sa.update(models.documents)
        .where(models.documents.c.id == document_id)
        .values(
            status=DOCUMENT_STATUS_ERROR,
            updated_at=sa.func.now(),
        )
    )
    await session.execute(stmt)
    await session.commit()


# RAG documents / ingestion
async def list_parsed_documents_without_rag(session: AsyncSession, batch_size: int) -> Sequence[Mapping[str, Any]]:
    """Return documents with status='parsed' that have no rag_documents mapping."""
    stmt = (
        sa.select(models.documents)
        .select_from(
            models.documents.outerjoin(
                models.rag_documents, models.documents.c.id == models.rag_documents.c.document_id
            )
        )
        .where(
            models.documents.c.status == DOCUMENT_STATUS_PARSED,
            models.rag_documents.c.id.is_(None),
        )
        .order_by(models.documents.c.created_at.asc())
        .limit(batch_size)
    )
    result = await session.execute(stmt)
    return [r._mapping for r in result.fetchall()]


async def insert_rag_document(session: AsyncSession, document_id: str, rag_doc_id: str) -> Mapping[str, Any]:
    """Insert a mapping row into rag_documents for a newly ingested document."""
    rag_id = new_uuid()
    stmt = (
        sa.insert(models.rag_documents)
        .values(id=rag_id, document_id=document_id, rag_doc_id=rag_doc_id)
        .returning(models.rag_documents)
    )
    result = await session.execute(stmt)
    await session.commit()
    row = result.fetchone()
    return _row_to_mapping(row)


async def update_document_ingested_success(session: AsyncSession, document_id: str) -> None:
    """Mark a document as successfully ingested into RAG."""
    stmt = (
        sa.update(models.documents)
        .where(models.documents.c.id == document_id)
        .values(status=DOCUMENT_STATUS_INGESTED, updated_at=sa.func.now())
    )
    await session.execute(stmt)
    await session.commit()


async def delete_rag_document_mapping(session: AsyncSession, document_id: str) -> None:
    """Delete rag_documents mapping rows for a given document."""
    stmt = sa.delete(models.rag_documents).where(models.rag_documents.c.document_id == document_id)
    await session.execute(stmt)
    await session.commit()


async def get_document_with_relations(
    session: AsyncSession,
    document_id: str,
    workspace_id: str,
) -> Mapping[str, Any] | None:
    """Return a document row plus basic file metadata (if any).

    This is primarily used for delete flows that need both DB and R2 keys.
    """
    stmt = (
        sa.select(
            models.documents,
            models.files.c.r2_key.label("file_r2_key"),
            models.files.c.id.label("file_id"),
        )
        .select_from(
            models.documents.outerjoin(
                models.files, models.documents.c.id == models.files.c.document_id
            )
        )
        .where(
            models.documents.c.id == document_id,
            models.documents.c.workspace_id == workspace_id,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    row = result.fetchone()
    return _row_to_mapping(row) if row else None


async def delete_document_cascade(session: AsyncSession, document_id: str) -> None:
    """Delete a document and all directly-related rows (rag_documents, parse_jobs, files)."""
    # rag_documents
    await session.execute(
        sa.delete(models.rag_documents).where(models.rag_documents.c.document_id == document_id)
    )
    # parse_jobs
    await session.execute(
        sa.delete(models.parse_jobs).where(models.parse_jobs.c.document_id == document_id)
    )
    # files
    await session.execute(sa.delete(models.files).where(models.files.c.document_id == document_id))
    # document
    await session.execute(sa.delete(models.documents).where(models.documents.c.id == document_id))
    await session.commit()


# Conversations
async def create_conversation(session: AsyncSession, workspace_id: str, user_id: str, title: str) -> Mapping[str, Any]:
    conversation_id = new_uuid()
    stmt = (
        sa.insert(models.conversations)
        .values(id=conversation_id, workspace_id=workspace_id, user_id=user_id, title=title)
        .returning(models.conversations)
    )
    result = await session.execute(stmt)
    await session.commit()
    row = result.fetchone()
    return _row_to_mapping(row)


async def get_conversation(session: AsyncSession, conversation_id: str, user_id: str) -> Mapping[str, Any] | None:
    stmt = sa.select(models.conversations).where(
        models.conversations.c.id == conversation_id,
        models.conversations.c.user_id == user_id,
    )
    result = await session.execute(stmt)
    row = result.fetchone()
    return _row_to_mapping(row) if row else None


async def list_conversations(session: AsyncSession, workspace_id: str, user_id: str) -> Sequence[Mapping[str, Any]]:
    stmt = (
        sa.select(models.conversations)
        .where(
            models.conversations.c.workspace_id == workspace_id,
            models.conversations.c.user_id == user_id,
        )
        .order_by(models.conversations.c.created_at.desc())
    )
    result = await session.execute(stmt)
    return [r._mapping for r in result.fetchall()]


# Messages
async def list_messages(session: AsyncSession, conversation_id: str, user_id: str) -> Sequence[Mapping[str, Any]]:
    stmt = (
        sa.select(models.messages)
        .join(models.conversations, models.messages.c.conversation_id == models.conversations.c.id)
        .where(
            models.messages.c.conversation_id == conversation_id,
            models.conversations.c.user_id == user_id,
        )
        .order_by(models.messages.c.created_at.asc())
    )
    result = await session.execute(stmt)
    return [r._mapping for r in result.fetchall()]


async def create_message(
    session: AsyncSession,
    conversation_id: str,
    role: str,
    content: str,
    status: str | None = None,
    metadata: dict | None = None,
) -> Mapping[str, Any]:
    message_id = new_uuid()
    values = {
        "id": message_id,
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "metadata": metadata,
    }
    if status:
        values["status"] = status
        
    stmt = (
        sa.insert(models.messages)
        .values(**values)
        .returning(models.messages)
    )
    result = await session.execute(stmt)
    await session.commit()
    row = result.fetchone()
    return _row_to_mapping(row)


async def update_message(
    session: AsyncSession,
    message_id: str,
    content: str | None = None,
    status: str | None = None,
    metadata: dict | None = None,
) -> Mapping[str, Any]:
    values: dict[str, Any] = {}
    if content is not None:
        values["content"] = content
    if status is not None:
        values["status"] = status
    if metadata is not None:
        values["metadata"] = metadata

    if not values:
        # No updates needed, return current state
        stmt = sa.select(models.messages).where(models.messages.c.id == message_id)
        result = await session.execute(stmt)
        row = result.fetchone()
        return _row_to_mapping(row)

    stmt = (
        sa.update(models.messages)
        .where(models.messages.c.id == message_id)
        .values(**values)
        .returning(models.messages)
    )
    result = await session.execute(stmt)
    await session.commit()
    row = result.fetchone()
    if not row:
        raise ValueError(f"Message {message_id} not found for update")
    return _row_to_mapping(row)


async def get_message(
    session: AsyncSession,
    message_id: str,
    conversation_id: str,
    user_id: str,
) -> Mapping[str, Any] | None:
    """Get a single message ensuring it belongs to the user's conversation."""
    stmt = (
        sa.select(models.messages)
        .join(models.conversations, models.messages.c.conversation_id == models.conversations.c.id)
        .where(
            models.messages.c.id == message_id,
            models.messages.c.conversation_id == conversation_id,
            models.conversations.c.user_id == user_id,
        )
    )
    result = await session.execute(stmt)
    row = result.fetchone()
    return _row_to_mapping(row) if row else None


async def delete_message(session: AsyncSession, message_id: str) -> None:
    """Delete a single message row."""
    stmt = sa.delete(models.messages).where(models.messages.c.id == message_id)
    await session.execute(stmt)
    await session.commit()


async def delete_conversation_cascade(session: AsyncSession, conversation_id: str) -> None:
    """Delete a conversation and all its messages."""
    await session.execute(
        sa.delete(models.messages).where(models.messages.c.conversation_id == conversation_id)
    )
    await session.execute(
        sa.delete(models.conversations).where(models.conversations.c.id == conversation_id)
    )
    await session.commit()


async def list_workspace_files_and_docs(session: AsyncSession, workspace_id: str) -> Sequence[Mapping[str, Any]]:
    """List R2 keys for all files and OCR JSON in a workspace."""
    stmt = (
        sa.select(
            models.documents.c.id.label("document_id"),
            models.documents.c.docai_raw_r2_key.label("docai_raw_r2_key"),
            models.files.c.r2_key.label("file_r2_key"),
        )
        .select_from(
            models.documents.outerjoin(
                models.files, models.documents.c.id == models.files.c.document_id
            )
        )
        .where(models.documents.c.workspace_id == workspace_id)
    )
    result = await session.execute(stmt)
    return [r._mapping for r in result.fetchall()]


async def delete_workspace_cascade(session: AsyncSession, workspace_id: str, user_id: str) -> None:
    """Delete a workspace and all related rows in a single transaction."""
    # Ensure workspace belongs to user_id to avoid accidental cross-user deletes.
    ws = await get_workspace(session, workspace_id=workspace_id, user_id=user_id)
    if not ws:
        return

    # messages -> conversations -> rag_documents/parse_jobs/files/documents -> workspace
    # messages (via conversations)
    conv_ids_subq = sa.select(models.conversations.c.id).where(
        models.conversations.c.workspace_id == workspace_id
    )
    await session.execute(
        sa.delete(models.messages).where(
            models.messages.c.conversation_id.in_(conv_ids_subq)
        )
    )
    # conversations
    await session.execute(
        sa.delete(models.conversations).where(models.conversations.c.workspace_id == workspace_id)
    )
    # rag_documents (via documents)
    doc_ids_subq = sa.select(models.documents.c.id).where(
        models.documents.c.workspace_id == workspace_id
    )
    await session.execute(
        sa.delete(models.rag_documents).where(models.rag_documents.c.document_id.in_(doc_ids_subq))
    )
    # parse_jobs (via documents)
    await session.execute(
        sa.delete(models.parse_jobs).where(models.parse_jobs.c.document_id.in_(doc_ids_subq))
    )
    # files (via documents)
    await session.execute(
        sa.delete(models.files).where(models.files.c.document_id.in_(doc_ids_subq))
    )
    # documents
    await session.execute(
        sa.delete(models.documents).where(models.documents.c.workspace_id == workspace_id)
    )
    # workspace
    await session.execute(sa.delete(models.workspaces).where(models.workspaces.c.id == workspace_id))
    await session.commit()
