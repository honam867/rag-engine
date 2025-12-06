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


class ParseJobInfo(BaseModel):
    id: UUID
    status: str
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class DocumentDetail(BaseModel):
    document: Document
    parse_job: Optional[ParseJobInfo] = None


class UploadResponseItem(BaseModel):
    document: Document
    file_id: str


class UploadResponse(BaseModel):
    items: list[UploadResponseItem]


class DocumentSegment(BaseModel):
    segment_index: int
    page_idx: int
    text: str


class DocumentRawTextResponse(BaseModel):
    document_id: UUID
    workspace_id: UUID
    status: str
    segments: list[DocumentSegment]
