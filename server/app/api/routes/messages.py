from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.core.security import CurrentUser, get_current_user
from server.app.db import repositories as repo
from server.app.db.session import get_db_session
from server.app.schemas.conversations import Message, MessageCreate, MessageListResponse

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
):
    await _ensure_conversation(session, conversation_id, current_user.id)
    user_msg = await repo.create_message(
        session=session, conversation_id=conversation_id, role="user", content=body.content, metadata=None
    )
    # Optional mock AI reply for Phase 1
    ai_msg = await repo.create_message(
        session=session,
        conversation_id=conversation_id,
        role="ai",
        content="Engine chưa kết nối",
        metadata={"mock": True},
    )
    return _to_message(ai_msg)
