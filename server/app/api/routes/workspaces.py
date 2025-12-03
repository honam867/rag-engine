from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.core.security import CurrentUser, get_current_user
from server.app.db import repositories as repo
from server.app.db.session import get_db_session
from server.app.schemas.workspaces import Workspace, WorkspaceCreate
from server.app.services.rag_engine import RagEngineService
from server.app.services import storage_r2

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


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Delete a workspace and clean up related DB records, R2 objects and RAG data."""
    # Ensure workspace belongs to current user.
    ws = await repo.get_workspace(session, workspace_id=workspace_id, user_id=current_user.id)
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    # Collect R2 keys before deleting DB rows.
    file_rows = await repo.list_workspace_files_and_docs(session=session, workspace_id=workspace_id)
    file_keys: set[str] = set()
    raw_keys: set[str] = set()
    for row in file_rows:
        if row.get("file_r2_key"):
            file_keys.add(row["file_r2_key"])
        if row.get("docai_raw_r2_key"):
            raw_keys.add(row["docai_raw_r2_key"])

    # Delete all related DB records in a cascade fashion.
    await repo.delete_workspace_cascade(session=session, workspace_id=workspace_id, user_id=current_user.id)

    # Best-effort R2 cleanup.
    for key in file_keys:
        try:
            await storage_r2.delete_object(key)
        except Exception:  # noqa: BLE001
            # Ignore individual failures; they can be cleaned up later offline.
            pass
    for key in raw_keys:
        try:
            await storage_r2.delete_object(key)
        except Exception:  # noqa: BLE001
            pass

    # Best-effort RAG storage cleanup for this workspace.
    rag_engine = RagEngineService()
    await rag_engine.delete_workspace_data(workspace_id=str(workspace_id))
