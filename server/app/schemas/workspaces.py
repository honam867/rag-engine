from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class WorkspaceCreate(BaseModel):
    name: str
    description: Optional[str] = None


class Workspace(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
