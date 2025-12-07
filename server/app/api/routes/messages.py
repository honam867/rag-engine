from typing import Any, Dict, List, Tuple
import uuid
import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.core.constants import (
    DOCUMENT_STATUS_INGESTED,
    DOCUMENT_STATUS_PARSED,
    MESSAGE_STATUS_DONE,
    MESSAGE_STATUS_ERROR,
    MESSAGE_STATUS_PENDING,
    RAG_DEFAULT_SYSTEM_PROMPT,
    ROLE_AI,
    ROLE_USER,
)
from server.app.core.config import get_settings
from server.app.core.realtime import send_event_to_user
from server.app.core.security import CurrentUser, get_current_user
from server.app.db import models, repositories as repo
from server.app.db.session import get_db_session, async_session
from server.app.schemas.conversations import Message, MessageCreate, MessageListResponse
from server.app.services.chunker import build_segments_from_docai, chunk_full_text_to_segments
from server.app.services import storage_r2
from server.app.services.answer_engine import AnswerEngineService

router = APIRouter(prefix="/api/conversations/{conversation_id}/messages")


def _to_message(row: dict) -> Message:
    return Message.model_validate(row)


async def _ensure_conversation(session: AsyncSession, conversation_id: str, user_id: str) -> dict:
    conv = await repo.get_conversation(session, conversation_id=conversation_id, user_id=user_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv


def _compute_similarity(a: str, b: str) -> float:
    """Backward-compatible wrapper (kept for potential future use).

    Phase 7.1 dùng similarity ở mức token (xem helpers bên dưới) nên
    hàm này hiện không còn được dùng trong mapping chính.
    """
    if not a or not b:
        return 0.0
    return 0.0


def _normalize_and_tokenize(text: str, max_len: int = 800) -> set[str]:
    """Normalize text and return a set of tokens for overlap matching."""
    if not text:
        return set()
    value = (text or "").strip().lower()
    if not value:
        return set()
    # Limit length to avoid heavy processing on very long texts.
    value = value[:max_len]
    # Replace basic punctuation with spaces, then split.
    for ch in [",", ".", ";", ":", "!", "?", "(", ")", "[", "]", "{", "}", "\"", "'"]:
        value = value.replace(ch, " ")
    tokens = [t for t in value.split() if t]
    return set(tokens)


def _token_overlap_score(a_tokens: set[str], b_tokens: set[str]) -> float:
    """Compute a simple Jaccard-like overlap score between two token sets."""
    if not a_tokens or not b_tokens:
        return 0.0
    common = len(a_tokens & b_tokens)
    denom = max(len(a_tokens), len(b_tokens))
    if denom == 0:
        return 0.0
    return common / denom


async def _build_citations_for_sections(
    workspace_id: str,
    sections: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Build citations for each section by matching against document segments.

    This function:
    - Loads parsed/ingested documents in the workspace.
    - Chunks `docai_full_text` into segments per document.
    - For each section, finds the best matching segment(s) and returns
      structured citations with real document_id + segment_index.
    """
    if not sections:
        return [], []

    # Step 1: load documents with OCR text for this workspace.
    async with async_session() as session:  # type: ignore[call-arg]
        assert isinstance(session, AsyncSession)
        stmt = (
            sa.select(
                models.documents.c.id,
                models.documents.c.docai_full_text,
                models.documents.c.docai_raw_r2_key,
                models.documents.c.status,
            )
            .where(
                models.documents.c.workspace_id == workspace_id,
                models.documents.c.status.in_([DOCUMENT_STATUS_PARSED, DOCUMENT_STATUS_INGESTED]),
                models.documents.c.docai_full_text.is_not(None),
            )
        )
        result = await session.execute(stmt)
        doc_rows = result.fetchall()

    # Step 2: build a global list of segments across all documents,
    # using Document AI JSON when available for high-fidelity segmentation.
    all_segments: List[Dict[str, Any]] = []

    for row in doc_rows:
        row_map = row._mapping
        doc_id = str(row_map["id"])
        full_text = (row_map.get("docai_full_text") or "").strip()
        if not full_text:
            continue

        raw_key = row_map.get("docai_raw_r2_key")
        segments: List[Dict[str, Any]] = []

        if raw_key:
            try:
                doc = await storage_r2.download_json(raw_key)
                segments = build_segments_from_docai(doc=doc, full_text=full_text)
            except Exception:
                segments = []

        if not segments:
            segments = chunk_full_text_to_segments(full_text)

        for seg in segments:
            seg_text = str(seg.get("text") or "").strip()
            tokens = _normalize_and_tokenize(seg_text)
            if not tokens:
                continue
            all_segments.append(
                {
                    "document_id": doc_id,
                    "segment_index": int(seg.get("segment_index", 0)),
                    "page_idx": int(seg.get("page_idx", 0)),
                    "text": seg_text,
                    "tokens": tokens,
                }
            )

    if not all_segments:
        # No OCR text available; cannot build citations.
        return sections, []

    sections_with_citations: List[Dict[str, Any]] = []
    citations_flat: List[Dict[str, Any]] = []

    # Step 3: for mỗi section, tìm segment phù hợp nhất với ràng buộc
    # thứ tự (monotone alignment) để tránh nhảy lùi bất hợp lý.
    last_segment_pos = 0
    num_segments = len(all_segments)

    for sec in sections:
        text_val = str(sec.get("text") or "").strip()
        if not text_val:
            sections_with_citations.append({**sec, "citations": []})
            continue

        section_tokens = _normalize_and_tokenize(text_val)
        if not section_tokens:
            sections_with_citations.append({**sec, "citations": []})
            continue

        best_score = 0.0
        best_pos: int | None = None

        for pos in range(last_segment_pos, num_segments):
            seg_entry = all_segments[pos]
            score = _token_overlap_score(section_tokens, seg_entry["tokens"])
            if score > best_score:
                best_score = score
                best_pos = pos

        citations_for_section: List[Dict[str, Any]] = []
        # Ngưỡng tối thiểu để chấp nhận citation.
        if best_pos is not None and best_score >= 0.3:
            seg_entry = all_segments[best_pos]
            snippet = seg_entry["text"].strip()
            if len(snippet) > 200:
                snippet = snippet[:200] + "..."
            citation = {
                "document_id": seg_entry["document_id"],
                "segment_index": seg_entry["segment_index"],
                "page_idx": seg_entry["page_idx"],
                "snippet_preview": snippet,
            }
            citations_for_section.append(citation)
            citations_flat.append(citation)

            # Giữ thứ tự không giảm giữa các section.
            if best_pos >= last_segment_pos:
                last_segment_pos = best_pos

        sections_with_citations.append({**sec, "citations": citations_for_section})

    return sections_with_citations, citations_flat


async def _build_citations_from_source_ids(
    workspace_id: str,
    sections: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Build citations for each section based on source_ids from RAG.

    source_ids are expected in the format "{document_id}:{segment_index}" and
    correspond to segments built from Document AI JSON or heuristic chunking.
    """
    if not sections:
        return [], []

    # Collect all unique (document_id, segment_index) pairs from sections.
    id_pairs: set[tuple[str, int]] = set()
    for sec in sections:
        src_ids = sec.get("source_ids") or []
        if not isinstance(src_ids, list):
            continue
        for raw_id in src_ids:
            if not isinstance(raw_id, str):
                continue
            raw_id = raw_id.strip()
            if not raw_id:
                continue
            # Expected format: "{document_id}:{segment_index}"
            parts = raw_id.split(":", 1)
            if len(parts) != 2:
                continue
            doc_id_part, seg_part = parts
            try:
                seg_idx = int(seg_part)
            except ValueError:
                continue
            # Validate that doc_id_part is a proper UUID; ignore invalid values
            # such as "1", "3" etc. to avoid DB errors and fall back gracefully.
            try:
                doc_uuid = uuid.UUID(doc_id_part)
            except (ValueError, AttributeError):
                continue
            doc_id_norm = str(doc_uuid)
            id_pairs.add((doc_id_norm, seg_idx))

    if not id_pairs:
        # Nothing to map by ID; caller should fall back to text-matching.
        return sections, []

    # Load documents in this workspace that are referenced by source_ids.
    async with async_session() as session:  # type: ignore[call-arg]
        assert isinstance(session, AsyncSession)
        doc_ids = [doc_id for doc_id, _ in id_pairs]
        stmt = (
            sa.select(
                models.documents.c.id,
                models.documents.c.docai_full_text,
                models.documents.c.docai_raw_r2_key,
                models.documents.c.status,
            )
            .where(
                models.documents.c.workspace_id == workspace_id,
                models.documents.c.status.in_([DOCUMENT_STATUS_PARSED, DOCUMENT_STATUS_INGESTED]),
                models.documents.c.docai_full_text.is_not(None),
                models.documents.c.id.in_(doc_ids),
            )
        )
        result = await session.execute(stmt)
        doc_rows = result.fetchall()

    # Build a lookup map: (doc_id, segment_index) -> segment info.
    segment_lookup: Dict[tuple[str, int], Dict[str, Any]] = {}

    for row in doc_rows:
        row_map = row._mapping
        doc_id_str = str(row_map["id"])
        full_text = (row_map.get("docai_full_text") or "").strip()
        if not full_text:
            continue

        raw_key = row_map.get("docai_raw_r2_key")
        segments: List[Dict[str, Any]] = []

        if raw_key:
            try:
                doc = await storage_r2.download_json(raw_key)
                segments = build_segments_from_docai(doc=doc, full_text=full_text)
            except Exception:
                segments = []

        if not segments:
            segments = chunk_full_text_to_segments(full_text)

        for seg in segments:
            seg_idx = int(seg.get("segment_index", 0))
            key = (doc_id_str, seg_idx)
            if key not in id_pairs:
                continue
            segment_lookup[key] = {
                "document_id": doc_id_str,
                "segment_index": seg_idx,
                "page_idx": int(seg.get("page_idx", 0)),
                "text": str(seg.get("text") or "").strip(),
            }

    sections_with_citations: List[Dict[str, Any]] = []
    citations_flat: List[Dict[str, Any]] = []

    for sec in sections:
        src_ids = sec.get("source_ids") or []
        citations_for_section: List[Dict[str, Any]] = []

        if isinstance(src_ids, list):
            for raw_id in src_ids:
                if not isinstance(raw_id, str):
                    continue
                raw_id = raw_id.strip()
                if not raw_id:
                    continue
                parts = raw_id.split(":", 1)
                if len(parts) != 2:
                    continue
                doc_id_part, seg_part = parts
                try:
                    seg_idx = int(seg_part)
                except ValueError:
                    continue
                key = (doc_id_part, seg_idx)
                seg_info = segment_lookup.get(key)
                if not seg_info:
                    continue
                snippet = seg_info["text"]
                if len(snippet) > 200:
                    snippet = snippet[:200] + "..."
                citation = {
                    "document_id": seg_info["document_id"],
                    "segment_index": seg_info["segment_index"],
                    "page_idx": seg_info["page_idx"],
                    "snippet_preview": snippet,
                }
                citations_for_section.append(citation)
                citations_flat.append(citation)

        sections_with_citations.append({**sec, "citations": citations_for_section})

    return sections_with_citations, citations_flat
async def _process_ai_message_background(
    ai_message_id: str,
    conversation_id: str,
    workspace_id: str,
    user_id: str,
    question: str,
) -> None:
    """Background task: call Answer Engine and update the AI message."""
    settings = get_settings()

    try:
        answer_engine = AnswerEngineService()
        result = await answer_engine.answer_question(
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            question=question,
        )

        answer = result.get("answer") or ""
        sections_with_citations = result.get("sections") or []
        citations_flat = result.get("citations") or []
        llm_usage = result.get("llm_usage")

        metadata: dict[str, Any] = {}
        if sections_with_citations:
            metadata["sections"] = sections_with_citations
        if citations_flat:
            metadata["citations"] = citations_flat
        if llm_usage:
            metadata["llm_usage"] = llm_usage

        # Update AI message as done in a fresh DB session.
        async with async_session() as bg_session:  # type: ignore[call-arg]
            updated_ai_msg = await repo.update_message(
                session=bg_session,
                message_id=ai_message_id,
                content=answer or "Xin lỗi, hiện tại mình không thể trả lời câu hỏi này.",
                status=MESSAGE_STATUS_DONE,
                metadata=metadata or None,
            )

        # Realtime event: AI message done.
        try:
            await send_event_to_user(
                user_id,
                "message.status_updated",
                {
                    "workspace_id": workspace_id,
                    "conversation_id": conversation_id,
                    "message_id": ai_message_id,
                    "status": MESSAGE_STATUS_DONE,
                    "content": updated_ai_msg.get("content") or answer,
                    "metadata": updated_ai_msg.get("metadata") or metadata or None,
                },
            )
        except Exception:
            # Best-effort realtime.
            pass
    except Exception as exc:
        # On failure, mark AI message as error.
        error_msg = f"Error generating response: {str(exc)}"
        async with async_session() as bg_session:  # type: ignore[call-arg]
            await repo.update_message(
                session=bg_session,
                message_id=ai_message_id,
                content=error_msg,
                status=MESSAGE_STATUS_ERROR,
            )

        try:
            await send_event_to_user(
                user_id,
                "message.status_updated",
                {
                    "workspace_id": workspace_id,
                    "conversation_id": conversation_id,
                    "message_id": ai_message_id,
                    "status": MESSAGE_STATUS_ERROR,
                },
            )
        except Exception:
            pass


@router.get("", response_model=MessageListResponse)
async def list_messages(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    await _ensure_conversation(session, conversation_id, current_user.id)
    rows = await repo.list_messages(session, conversation_id=conversation_id, user_id=current_user.id)
    return MessageListResponse(items=[_to_message(r) for r in rows])


@router.post("", response_model=MessageListResponse)
async def create_message(
    conversation_id: str,
    body: MessageCreate,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """Create a new user message and generate an AI response."""
    conv = await _ensure_conversation(session, conversation_id, current_user.id)
    workspace_id = str(conv["workspace_id"])

    # 1. Create User Message (Always Done)
    user_msg = await repo.create_message(
        session=session,
        conversation_id=conversation_id,
        role=ROLE_USER,
        content=body.content,
        status=MESSAGE_STATUS_DONE,
        metadata=None,
    )

    # 2. Create AI Message Placeholder (Pending)
    # This ensures that if the user refreshes immediately, they see a pending message.
    ai_msg = await repo.create_message(
        session=session,
        conversation_id=conversation_id,
        role=ROLE_AI,
        content="",  # Empty initially
        status=MESSAGE_STATUS_PENDING,
    )

    # 3. Send Realtime Events (User Created + AI Pending)
    # Best-effort: failures here should not rollback DB transaction
    try:
        user_created_at = user_msg.get("created_at")
        if hasattr(user_created_at, "isoformat"):
            user_created_at = user_created_at.isoformat()
        else:
            user_created_at = str(user_created_at) if user_created_at else None

        ai_created_at = ai_msg.get("created_at")
        if hasattr(ai_created_at, "isoformat"):
            ai_created_at = ai_created_at.isoformat()
        else:
            ai_created_at = str(ai_created_at) if ai_created_at else None

        # User Message Event
        await send_event_to_user(
            current_user.id,
            "message.created",
            {
                "workspace_id": workspace_id,
                "conversation_id": conversation_id,
                "message": {
                    "id": str(user_msg["id"]),
                    "conversation_id": conversation_id,
                    "workspace_id": workspace_id,
                    "role": user_msg["role"],
                    "content": user_msg["content"],
                    "status": MESSAGE_STATUS_DONE,
                    "created_at": user_created_at,
                    "metadata": user_msg.get("metadata"),
                },
            },
        )
        # AI Message Event (Pending)
        await send_event_to_user(
            current_user.id,
            "message.created",
            {
                "workspace_id": workspace_id,
                "conversation_id": conversation_id,
                "message": {
                    "id": str(ai_msg["id"]),
                    "conversation_id": conversation_id,
                    "workspace_id": workspace_id,
                    "role": ai_msg["role"],
                    "content": "",
                    "status": MESSAGE_STATUS_PENDING,
                    "created_at": ai_created_at,
                    "metadata": None,
                },
            },
        )
    except Exception:
        pass

    # 4. Trigger background RAG processing and return immediately.
    asyncio.get_event_loop().create_task(
        _process_ai_message_background(
            ai_message_id=str(ai_msg["id"]),
            conversation_id=conversation_id,
            workspace_id=workspace_id,
            user_id=current_user.id,
            question=body.content,
        )
    )

    # Return both user and AI pending messages so client has real IDs.
    return MessageListResponse(items=[_to_message(user_msg), _to_message(ai_msg)])


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
