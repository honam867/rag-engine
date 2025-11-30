from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class Document(BaseModel):
    id: UUID
    title: str
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    items: list[Document]


class UploadResponseItem(BaseModel):
    document: Document
    file_id: str


class UploadResponse(BaseModel):
    items: list[UploadResponseItem]
