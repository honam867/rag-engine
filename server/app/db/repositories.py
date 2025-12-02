"""Repository helpers for Phase 1 using SQLAlchemy Core async."""

from typing import Any, Mapping, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.core.constants import (
    DOCUMENT_STATUS_ERROR,
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
    session: AsyncSession, conversation_id: str, role: str, content: str, metadata: dict | None
) -> Mapping[str, Any]:
    message_id = new_uuid()
    stmt = (
        sa.insert(models.messages)
        .values(
            id=message_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata=metadata,
        )
        .returning(models.messages)
    )
    result = await session.execute(stmt)
    await session.commit()
    row = result.fetchone()
    return _row_to_mapping(row)
