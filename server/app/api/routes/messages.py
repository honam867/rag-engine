from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.core.constants import RAG_DEFAULT_SYSTEM_PROMPT, ROLE_AI, ROLE_USER
from server.app.core.config import get_settings
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
):
    conv = await _ensure_conversation(session, conversation_id, current_user.id)

    # 1. Lưu message user
    user_msg = await repo.create_message(
        session=session, conversation_id=conversation_id, role=ROLE_USER, content=body.content, metadata=None
    )

    # 2. Gọi RAG Engine để lấy câu trả lời cho workspace tương ứng
    settings = get_settings()
    rag_engine = RagEngineService(settings=settings.rag)
    workspace_id = str(conv["workspace_id"])

    rag_result = await rag_engine.query(
        workspace_id=workspace_id,
        question=body.content,
        system_prompt=RAG_DEFAULT_SYSTEM_PROMPT,
        mode=settings.rag.query_mode,
    )
    answer = rag_result.get("answer") or ""
    citations = rag_result.get("citations") or []

    # 3. Lưu message AI với citations trong metadata
    ai_msg = await repo.create_message(
        session=session,
        conversation_id=conversation_id,
        role=ROLE_AI,
        content=answer or "Xin lỗi, hiện tại mình không thể trả lời câu hỏi này.",
        metadata={"citations": citations} if citations else {},
    )
    return _to_message(ai_msg)


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
