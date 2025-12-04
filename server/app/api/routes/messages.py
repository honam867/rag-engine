from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.core.constants import (
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
from server.app.db.session import get_db_session
from server.app.schemas.conversations import Message, MessageCreate, MessageListResponse
from server.app.services.rag_engine import RagEngineService

router = APIRouter(prefix="/api/conversations/{conversation_id}/messages")


def _to_message(row: dict) -> Message:
    return Message.model_validate(row)


async def _ensure_conversation(session: AsyncSession, conversation_id: str, user_id: str) -> dict:
    conv = await repo.get_conversation(session, conversation_id=conversation_id, user_id=user_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv


@router.get("", response_model=MessageListResponse)
async def list_messages(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    await _ensure_conversation(session, conversation_id, current_user.id)
    rows = await repo.list_messages(session, conversation_id=conversation_id, user_id=current_user.id)
    return MessageListResponse(items=[_to_message(r) for r in rows])


@router.post("", response_model=Message)
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

    # 4. Generate AI Response (RAG)
    # Note: This is synchronous/blocking in this V1 implementation.
    try:
        settings = get_settings()
        # Initialize RagEngineService with specific settings if needed, or defaults
        rag_engine = RagEngineService(settings=settings.rag)

        rag_result = await rag_engine.query(
            workspace_id=workspace_id,
            question=body.content,
            system_prompt=RAG_DEFAULT_SYSTEM_PROMPT,
            mode=settings.rag.query_mode,
        )
        answer = rag_result.get("answer") or ""
        citations = rag_result.get("citations") or []

        # 5. Update AI Message (Done)
        updated_ai_msg = await repo.update_message(
            session=session,
            message_id=str(ai_msg["id"]),
            content=answer or "Xin lỗi, hiện tại mình không thể trả lời câu hỏi này.",
            status=MESSAGE_STATUS_DONE,
            metadata={"citations": citations} if citations else {},
        )

        # 6. Send Realtime Event (AI Done)
        try:
            await send_event_to_user(
                current_user.id,
                "message.status_updated",
                {
                    "workspace_id": workspace_id,
                    "conversation_id": conversation_id,
                    "message_id": str(ai_msg["id"]),
                    "status": MESSAGE_STATUS_DONE,
                    "content": answer,
                },
            )
        except Exception:
            pass

        return _to_message(updated_ai_msg)

    except Exception as exc:
        # Handle Failure: Update AI message to Error
        # Ensure we capture the error state in DB
        error_msg = f"Error generating response: {str(exc)}"
        updated_ai_msg = await repo.update_message(
            session=session,
            message_id=str(ai_msg["id"]),
            content=error_msg,
            status=MESSAGE_STATUS_ERROR,
        )
        
        # Notify Error
        try:
             await send_event_to_user(
                current_user.id,
                "message.status_updated",
                {
                    "workspace_id": workspace_id,
                    "conversation_id": conversation_id,
                    "message_id": str(ai_msg["id"]),
                    "status": MESSAGE_STATUS_ERROR,
                },
            )
        except Exception:
            pass

        return _to_message(updated_ai_msg)


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