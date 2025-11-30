from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.core.security import CurrentUser, get_current_user
from server.app.db import repositories as repo
from server.app.db.session import get_db_session
from server.app.schemas.workspaces import Workspace, WorkspaceCreate

router = APIRouter(prefix="/api/workspaces")


def _to_workspace(row: dict) -> Workspace:
    return Workspace.model_validate(row)


@router.post("", response_model=Workspace)
async def create_workspace(
    body: WorkspaceCreate,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    row = await repo.create_workspace(session, user_id=current_user.id, name=body.name, description=body.description)
    return _to_workspace(row)


@router.get("", response_model=list[Workspace])
async def list_workspaces(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    rows = await repo.list_workspaces(session, user_id=current_user.id)
    return [_to_workspace(r) for r in rows]


@router.get("/{workspace_id}", response_model=Workspace)
async def get_workspace_detail(
    workspace_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    row = await repo.get_workspace(session, workspace_id=workspace_id, user_id=current_user.id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return _to_workspace(row)
