from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.core.security import CurrentUser, get_current_user
from server.app.db import repositories as repo
from server.app.db.session import get_db_session
from server.app.schemas.conversations import Conversation, ConversationCreate, ConversationListResponse

router = APIRouter(prefix="/api/workspaces/{workspace_id}/conversations")


def _to_conversation(row: dict) -> Conversation:
    return Conversation.model_validate(row)


async def _ensure_workspace(session: AsyncSession, workspace_id: str, user_id: str) -> dict:
    ws = await repo.get_workspace(session, workspace_id=workspace_id, user_id=user_id)
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return ws


@router.post("", response_model=Conversation)
async def create_conversation(
    workspace_id: str,
    body: ConversationCreate,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    await _ensure_workspace(session, workspace_id, current_user.id)
    row = await repo.create_conversation(session, workspace_id=workspace_id, user_id=current_user.id, title=body.title)
    return _to_conversation(row)


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    workspace_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    await _ensure_workspace(session, workspace_id, current_user.id)
    rows = await repo.list_conversations(session, workspace_id=workspace_id, user_id=current_user.id)
    return ConversationListResponse(items=[_to_conversation(r) for r in rows])
