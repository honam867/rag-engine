import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.core.constants import (
    DOCUMENT_STATUS_INGESTED,
    DOCUMENT_STATUS_PARSED,
    DOCUMENT_STATUS_PENDING,
    PARSE_JOB_STATUS_QUEUED,
)
from server.app.core.event_bus import notify_parse_job_created
from server.app.core.realtime import send_event_to_user
from server.app.core.security import CurrentUser, get_current_user
from server.app.db import repositories as repo
from server.app.db.session import get_db_session
from server.app.schemas.documents import (
    Document,
    DocumentDetail,
    DocumentListResponse,
    DocumentRawTextResponse,
    DocumentSegment,
    ParseJobInfo,
    UploadResponse,
    UploadResponseItem,
)
from server.app.services.chunker import build_segments_from_docai, chunk_full_text_to_segments
from server.app.services.rag_engine import RagEngineService
from server.app.services import storage_r2
from server.app.utils.ids import new_uuid

router = APIRouter(prefix="/api/workspaces/{workspace_id}/documents")


def _to_document(row: dict) -> Document:
    return Document.model_validate(row)


async def _ensure_workspace(session: AsyncSession, workspace_id: str, user_id: str) -> dict:
    ws = await repo.get_workspace(session, workspace_id=workspace_id, user_id=user_id)
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return ws


@router.post("/upload", response_model=UploadResponse)
async def upload_documents(
    workspace_id: str,
    files: list[UploadFile] = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    await _ensure_workspace(session, workspace_id, current_user.id)
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided")

    items: list[UploadResponseItem] = []
    for upload in files:
        data = await upload.read()
        checksum = hashlib.sha256(data).hexdigest()
        original_filename = upload.filename or "upload.bin"
        title = original_filename
        doc_row = await repo.create_document(session, workspace_id=workspace_id, title=title, source_type="upload")

        file_id = new_uuid()
        ext = Path(original_filename).suffix
        r2_key = f"workspace/{workspace_id}/document/{doc_row['id']}/{file_id}{ext}"

        await storage_r2.upload_file(data, key=r2_key, content_type=upload.content_type)

        file_row = await repo.create_file(
            session=session,
            document_id=doc_row["id"],
            r2_key=r2_key,
            original_filename=original_filename,
            mime_type=upload.content_type or "application/octet-stream",
            size_bytes=len(data),
            checksum=checksum,
            file_id=file_id,
        )

        parse_job = await repo.create_parse_job(session=session, document_id=doc_row["id"])

        # Best-effort realtime notifications for new document and queued parse job.
        try:
            created_at_str = doc_row.get("created_at")
            if hasattr(created_at_str, "isoformat"):
                created_at_str = created_at_str.isoformat()
            else:
                created_at_str = str(created_at_str) if created_at_str else None

            await send_event_to_user(
                current_user.id,
                "document.created",
                {
                    "workspace_id": workspace_id,
                    "document": {
                        "id": str(doc_row["id"]),
                        "title": doc_row["title"],
                        "status": DOCUMENT_STATUS_PENDING,
                        "source_type": doc_row["source_type"],
                        "created_at": created_at_str,
                    },
                },
            )
            await send_event_to_user(
                current_user.id,
                "job.status_updated",
                {
                    "job_id": str(parse_job["id"]),
                    "job_type": "parse",
                    "workspace_id": workspace_id,
                    "document_id": str(doc_row["id"]),
                    "status": PARSE_JOB_STATUS_QUEUED,
                    "retry_count": int(parse_job.get("retry_count", 0) or 0),
                    "error_message": parse_job.get("error_message"),
                },
            )
            # Wake up parse_worker via Postgres NOTIFY so it can pick up the job immediately.
            await notify_parse_job_created(document_id=str(doc_row["id"]), job_id=str(parse_job["id"]))
        except Exception:
            # Realtime is best-effort; failures must not affect upload.
            pass

        items.append(UploadResponseItem(document=_to_document(doc_row), file_id=str(file_row["id"])))

    return UploadResponse(items=items)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    workspace_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    await _ensure_workspace(session, workspace_id, current_user.id)
    rows = await repo.list_documents(session, workspace_id=workspace_id)
    return DocumentListResponse(items=[_to_document(r) for r in rows])


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document_detail(
    workspace_id: str,
    document_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    await _ensure_workspace(session, workspace_id, current_user.id)
    doc_row = await repo.get_document(session, document_id=document_id, workspace_id=workspace_id)
    if not doc_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Get latest parse_job for this document if any.
    parse_job_row = await repo.get_latest_parse_job_for_document(session, document_id=document_id)
    parse_job: ParseJobInfo | None = None
    if parse_job_row:
        parse_job = ParseJobInfo.model_validate(parse_job_row)

    return DocumentDetail(document=_to_document(doc_row), parse_job=parse_job)


@router.get("/{document_id}/raw-text", response_model=DocumentRawTextResponse)
async def get_document_raw_text(
    workspace_id: str,
    document_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentRawTextResponse:
    """Return OCR'ed raw text of a document as segments for viewer."""
    await _ensure_workspace(session, workspace_id, current_user.id)
    doc_row = await repo.get_document(session, document_id=document_id, workspace_id=workspace_id)
    if not doc_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    status_value = doc_row.get("status")
    if status_value not in {DOCUMENT_STATUS_PARSED, DOCUMENT_STATUS_INGESTED}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is not parsed yet",
        )

    full_text = (doc_row.get("docai_full_text") or "").strip()
    if not full_text:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document has no OCR text (docai_full_text is empty)",
        )

    segments_data: list[dict]
    # Ưu tiên dùng JSON Document AI nếu có để segmentation bám sát layout PDF.
    raw_key = doc_row.get("docai_raw_r2_key")
    if raw_key:
        try:
            doc = await storage_r2.download_json(raw_key)
            segments_data = build_segments_from_docai(doc=doc, full_text=full_text)
        except Exception:
            # Nếu JSON không đọc được, không cố gắng chia nhỏ theo heuristic nữa;
            # thay vào đó trả về một segment duy nhất để tránh tạo cảm giác
            # segmentation "giả".
            segments_data = []
    else:
        segments_data = []

    if not segments_data:
        # Không dùng chunk_full_text_to_segments để tránh fallback phức tạp.
        # Trả về một segment duy nhất chứa toàn bộ text thô.
        segments_data = [
            {
                "segment_index": 0,
                "page_idx": 0,
                "text": full_text,
            }
        ]
    segments: list[DocumentSegment] = [
        DocumentSegment(
            segment_index=int(seg["segment_index"]),
            page_idx=int(seg.get("page_idx", 0)),
            text=str(seg["text"]),
        )
        for seg in segments_data
    ]

    return DocumentRawTextResponse(
        document_id=doc_row["id"],
        workspace_id=doc_row["workspace_id"],
        status=status_value,
        segments=segments,
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    workspace_id: str,
    document_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Delete a document from a workspace and clean up related resources."""
    await _ensure_workspace(session, workspace_id, current_user.id)

    # Load document + basic file metadata so we can clean up R2 objects.
    doc_with_rel = await repo.get_document_with_relations(
        session=session, document_id=document_id, workspace_id=workspace_id
    )
    if not doc_with_rel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Extract R2 keys before deleting DB rows.
    file_r2_key = doc_with_rel.get("file_r2_key")
    docai_raw_r2_key = doc_with_rel.get("docai_raw_r2_key")

    # Delete DB rows in a cascade fashion (rag_documents, parse_jobs, files, document).
    await repo.delete_document_cascade(session=session, document_id=document_id)

    # Best-effort call to RAG engine delete (currently a logical no-op).
    rag_engine = RagEngineService()
    await rag_engine.delete_document(workspace_id=str(workspace_id), rag_doc_id=str(document_id))

    # Best-effort cleanup of blobs on R2. Failures here should not break the API.
    if file_r2_key:
        try:
            await storage_r2.delete_object(file_r2_key)
        except Exception:  # noqa: BLE001
            # Log inside storage_r2 via its own logger / wrapper if needed.
            pass

    if docai_raw_r2_key:
        try:
            await storage_r2.delete_object(docai_raw_r2_key)
        except Exception:  # noqa: BLE001
            pass
