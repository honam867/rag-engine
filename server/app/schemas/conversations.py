from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ConversationCreate(BaseModel):
    title: str


class Conversation(BaseModel):
    id: UUID
    workspace_id: UUID
    title: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ConversationListResponse(BaseModel):
    items: list[Conversation]


class Message(BaseModel):
    id: UUID
    role: str
    content: str
    metadata: Optional[dict] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MessageCreate(BaseModel):
    content: str


class MessageListResponse(BaseModel):
    items: list[Message]
