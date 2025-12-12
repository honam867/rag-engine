from typing import Any, Dict
import uuid
import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.core.constants import (
    DOCUMENT_STATUS_INGESTED,
    DOCUMENT_STATUS_PARSED,
    MESSAGE_STATUS_DONE,
    MESSAGE_STATUS_ERROR,
    MESSAGE_STATUS_PENDING,
    RAG_DEFAULT_SYSTEM_PROMPT,
    ROLE_AI,
    ROLE_USER,
)
from server.app.core.config import get_settings
from server.app.core.realtime import send_event_to_user
from server.app.core.security import CurrentUser, get_current_user
from server.app.db import repositories as repo
from server.app.db.session import get_db_session, async_session
from server.app.schemas.conversations import Message, MessageCreate, MessageListResponse
from server.app.services.answer_engine import AnswerEngineService

router = APIRouter(prefix="/api/conversations/{conversation_id}/messages")


def _to_message(row: dict) -> Message:
    return Message.model_validate(row)


async def _ensure_conversation(session: AsyncSession, conversation_id: str, user_id: str) -> dict:
    conv = await repo.get_conversation(session, conversation_id=conversation_id, user_id=user_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv
async def _process_ai_message_background(
    ai_message_id: str,
    conversation_id: str,
    workspace_id: str,
    user_id: str,
    question: str,
) -> None:
    """Background task: call Answer Engine and update the AI message."""

    try:
        answer_engine = AnswerEngineService()
        result = await answer_engine.answer_question(
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            question=question,
        )

        answer = result.get("answer") or ""
        llm_usage = result.get("llm_usage")
        sections = result.get("sections")
        citations = result.get("citations")

        metadata: dict[str, Any] = {}
        if sections:
            metadata["sections"] = sections
        if citations:
            metadata["citations"] = citations
        if llm_usage:
            metadata["llm_usage"] = llm_usage

        # Update AI message as done in a fresh DB session.
        async with async_session() as bg_session:  # type: ignore[call-arg]
            updated_ai_msg = await repo.update_message(
                session=bg_session,
                message_id=ai_message_id,
                content=answer or "Xin lỗi, hiện tại mình không thể trả lời câu hỏi này.",
                status=MESSAGE_STATUS_DONE,
                metadata=metadata or None,
            )

        # Realtime event: AI message done.
        try:
            await send_event_to_user(
                user_id,
                "message.status_updated",
                {
                    "workspace_id": workspace_id,
                    "conversation_id": conversation_id,
                    "message_id": ai_message_id,
                    "status": MESSAGE_STATUS_DONE,
                    "content": updated_ai_msg.get("content") or answer,
                    "metadata": updated_ai_msg.get("metadata") or metadata or None,
                },
            )
        except Exception:
            # Best-effort realtime.
            pass
    except Exception as exc:
        # On failure, mark AI message as error.
        error_msg = f"Error generating response: {str(exc)}"
        async with async_session() as bg_session:  # type: ignore[call-arg]
            await repo.update_message(
                session=bg_session,
                message_id=ai_message_id,
                content=error_msg,
                status=MESSAGE_STATUS_ERROR,
            )

        try:
            await send_event_to_user(
                user_id,
                "message.status_updated",
                {
                    "workspace_id": workspace_id,
                    "conversation_id": conversation_id,
                    "message_id": ai_message_id,
                    "status": MESSAGE_STATUS_ERROR,
                },
            )
        except Exception:
            pass


@router.get("", response_model=MessageListResponse)
async def list_messages(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    await _ensure_conversation(session, conversation_id, current_user.id)
    rows = await repo.list_messages(session, conversation_id=conversation_id, user_id=current_user.id)
    return MessageListResponse(items=[_to_message(r) for r in rows])


@router.post("", response_model=MessageListResponse)
async def create_message(
    conversation_id: str,
    body: MessageCreate,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """Create a new user message and generate an AI response."""
    conv = await _ensure_conversation(session, conversation_id, current_user.id)
    workspace_id = str(conv["workspace_id"])

    # 1. Create User Message (Always Done)
    user_msg = await repo.create_message(
        session=session,
        conversation_id=conversation_id,
        role=ROLE_USER,
        content=body.content,
        status=MESSAGE_STATUS_DONE,
        metadata=None,
    )

    # 2. Create AI Message Placeholder (Pending)
    # This ensures that if the user refreshes immediately, they see a pending message.
    ai_msg = await repo.create_message(
        session=session,
        conversation_id=conversation_id,
        role=ROLE_AI,
        content="",  # Empty initially
        status=MESSAGE_STATUS_PENDING,
    )

    # 3. Send Realtime Events (User Created + AI Pending)
    # Best-effort: failures here should not rollback DB transaction
    try:
        user_created_at = user_msg.get("created_at")
        if hasattr(user_created_at, "isoformat"):
            user_created_at = user_created_at.isoformat()
        else:
            user_created_at = str(user_created_at) if user_created_at else None

        ai_created_at = ai_msg.get("created_at")
        if hasattr(ai_created_at, "isoformat"):
            ai_created_at = ai_created_at.isoformat()
        else:
            ai_created_at = str(ai_created_at) if ai_created_at else None

        # User Message Event
        await send_event_to_user(
            current_user.id,
            "message.created",
            {
                "workspace_id": workspace_id,
                "conversation_id": conversation_id,
                "message": {
                    "id": str(user_msg["id"]),
                    "conversation_id": conversation_id,
                    "workspace_id": workspace_id,
                    "role": user_msg["role"],
                    "content": user_msg["content"],
                    "status": MESSAGE_STATUS_DONE,
                    "created_at": user_created_at,
                    "metadata": user_msg.get("metadata"),
                },
            },
        )
        # AI Message Event (Pending)
        await send_event_to_user(
            current_user.id,
            "message.created",
            {
                "workspace_id": workspace_id,
                "conversation_id": conversation_id,
                "message": {
                    "id": str(ai_msg["id"]),
                    "conversation_id": conversation_id,
                    "workspace_id": workspace_id,
                    "role": ai_msg["role"],
                    "content": "",
                    "status": MESSAGE_STATUS_PENDING,
                    "created_at": ai_created_at,
                    "metadata": None,
                },
            },
        )
    except Exception:
        pass

    # 4. Trigger background RAG processing and return immediately.
    asyncio.get_event_loop().create_task(
        _process_ai_message_background(
            ai_message_id=str(ai_msg["id"]),
            conversation_id=conversation_id,
            workspace_id=workspace_id,
            user_id=current_user.id,
            question=body.content,
        )
    )

    # Return both user and AI pending messages so client has real IDs.
    return MessageListResponse(items=[_to_message(user_msg), _to_message(ai_msg)])


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    conversation_id: str,
    message_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Delete a single message from a conversation."""
    await _ensure_conversation(session, conversation_id, current_user.id)
    msg = await repo.get_message(
        session=session,
        message_id=message_id,
        conversation_id=conversation_id,
        user_id=current_user.id,
    )
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    await repo.delete_message(session=session, message_id=message_id)
