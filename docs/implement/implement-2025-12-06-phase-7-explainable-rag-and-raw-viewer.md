# Implement: Phase 7 – Explainable RAG & Raw Document Viewer

> Note: This log documents the original segmentation-based behavior (helpers like `chunk_full_text_to_segments` and segment-based citations).  
> In the current implementation, these helpers are **deprecated** – raw-text API returns `docai_full_text` as a single segment and ingestion passes the full OCR text into LightRAG without explicit segment building.

## 1. Summary
- Scope: server, Phase 7.
- Added a raw-text viewer API for parsed documents and extended the RAG query pipeline to return structured sections + citations metadata, enabling the UI to show document text and attach per-section citation “bubbles” that can be mapped back to source segments.

## 2. Related spec / design
- Requirements:
  - `docs/requirements/requirements-phase-7.md`
- Design:
  - `docs/design/phase-7-design.md`
- Architecture:
  - `docs/design/architecture-overview.md`

## 3. Files touched
-- `server/app/services/chunker.py` – Refactored chunking into a reusable `chunk_full_text_to_segments(full_text, max_chunk_chars=1500)` helper that produces ordered segments (`segment_index`, `page_idx`, `text`), and updated `build_content_list_from_document` to reuse this helper for RAG ingestion. Later refined the helper to use a more robust, multi-step segmentation strategy (blank lines → single newlines → fixed-size windows) so that documents without clear paragraph breaks still produce multiple reasonably sized segments for the raw-text viewer and citation mapping.
- `server/app/schemas/documents.py` – Added `DocumentSegment` and `DocumentRawTextResponse` schemas to represent raw OCR text segments per document. (**Segment-based schema is now deprecated; current implementation uses `DocumentRawTextResponse` with a single `text` field.**)
- `server/app/api/routes/documents.py` – Added `GET /api/workspaces/{workspace_id}/documents/{document_id}/raw-text` endpoint that validates workspace ownership, checks document status (`parsed`/`ingested`), chunks `docai_full_text` into segments via `chunk_full_text_to_segments`, and returns `DocumentRawTextResponse`. (**Runtime has since been simplified to return `docai_full_text` as a single text block instead of segments[].**) 
- `server/app/services/rag_engine.py` – Extended `RagEngineService.query` to instruct the LLM to return JSON with `sections[].text` only (no citations), parse that JSON when possible, and return `{answer, sections}` where `answer` is built by joining section texts.
- `server/app/api/routes/messages.py` – Added server-side citation mapping: after calling `RagEngineService.query`, the background task now loads parsed/ingested documents in the workspace, chunks `docai_full_text` into segments via `chunk_full_text_to_segments`, computes a simple similarity score between each section text và mỗi segment, rồi gán citations với `document_id` (UUID thật), `segment_index`, `page_idx` và `snippet_preview` vào `metadata.sections` (và flatten vào `metadata.citations`); event `message.status_updated` gửi kèm `metadata` này cho client.

## 4. API changes

### 4.1. New endpoint – raw text viewer

- `GET /api/workspaces/{workspace_id}/documents/{document_id}/raw-text`
  - **Auth**: Supabase JWT; user must own the workspace (same as other documents routes).
  - **Behavior**:
    - Ensures workspace exists and belongs to the current user.
    - Loads the document; 404 if not found.
    - Only allows documents with `status` in `{"parsed", "ingested"}`; otherwise returns `409 Conflict` with a “not parsed yet” message.
    - Reads `docai_full_text`; if empty, returns `409 Conflict` indicating missing OCR text.
    - Uses `chunk_full_text_to_segments(full_text)` to split text into ordered segments.
  - **Response example**:
    ```json
    {
      "document_id": "uuid",
      "workspace_id": "uuid",
      "status": "parsed",
      "segments": [
        {
          "segment_index": 0,
          "page_idx": 0,
          "text": "Đoạn text 1..."
        },
        {
          "segment_index": 1,
          "page_idx": 0,
          "text": "Đoạn text 2..."
        }
      ]
    }
    ```

### 4.2. Chat / messages – structured metadata

- `POST /api/conversations/{conversation_id}/messages` (AI response)
  - HTTP contract (request/response) không đổi, nhưng nội dung message `ai` trong DB/realtime nay có thêm:
    - `messages.metadata.sections`: list các section:
      ```json
      {
        "text": "Đoạn trả lời 1...",
        "citations": [
          {
            "document_id": "uuid-or-null",
            "segment_index": 15,
            "page_idx": 2,
            "snippet_preview": "Đoạn nguồn rút gọn..."
          }
        ]
      }
      ```
    - `messages.metadata.citations`: list citations flatten (tổng hợp từ mọi section), dùng cho client muốn hiển thị ở mức tổng quát.
  - `content` của message AI vẫn là một string được build bằng cách join `section["text"]` với double newline, giữ backward-compat với client cũ.
  - Event `message.status_updated` hiện bao gồm `metadata` trong payload để UI realtime đọc sections/citations mà không cần refetch.

## 5. Sequence / flow

### 5.1. View raw document text

```mermaid
sequenceDiagram
  participant U as User
  participant UI as Client
  participant API as FastAPI
  participant DB as Supabase

  U->>UI: Click document in workspace
  UI->>API: GET /api/workspaces/{ws}/documents/{doc}/raw-text
  API->>DB: SELECT document (check workspace_id/status/docai_full_text)
  DB-->>API: document row
  API->>API: chunk_full_text_to_segments(docai_full_text)
  API-->>UI: DocumentRawTextResponse (segments[])  <!-- deprecated; now returns `text` only -->
  UI->>U: Render segments (text viewer) with segment_index anchors
```

### 5.2. Chat with structured sections + citations

```mermaid
sequenceDiagram
  participant U as User
  participant UI as Client
  participant API as FastAPI
  participant DB as Supabase
  participant RAG as RagEngineService/RAG-Anything

  U->>UI: Send chat message
  UI->>API: POST /api/conversations/{conv}/messages (content)
  API->>DB: INSERT user message
  API->>DB: INSERT AI pending message
  API-->>UI: user + AI (pending)
  API->>RAG: query(workspace_id, question, prompt_with_JSON_sections_schema)
  RAG->>RAG: rag.aquery(combined_query)
  RAG-->>API: raw_result (text or JSON)
  API->>API: parse JSON → sections; build answer string
  API->>API: text-match sections với segments (docai_full_text) → build citations (document_id, segment_index, page_idx, snippet_preview)
  API->>DB: UPDATE AI message (content=answer, metadata={sections,citations}, status=done)
  API->>UI: WS event message.status_updated (content + metadata)
  UI->>U: Render answer + citations bubbles per section
```

## 6. Notes / TODO

- Hiện tại `chunk_full_text_to_segments` đặt `page_idx = 0` cho mọi segment; mapping chính xác page từ JSON Document AI sẽ cần Phase sau.
- `RagEngineService.query` chỉ dựa trên LLM để trả JSON `sections[*].text`; citations được tính **hoàn toàn ở server** bằng text matching.
- Thuật toán similarity hiện tại là một phép đo overlap ký tự đơn giản, giới hạn độ dài text (~800 ký tự) để tránh tốn CPU quá mức; đủ tốt để chọn 1 segment đại diện cho mỗi section, có thể nâng cấp sau (cosine similarity trên vector, Jaccard trên token, v.v.).
- Cần cập nhật client để:
  - Gọi `/raw-text` khi user chọn document và dựng viewer segments.
  - Đọc `metadata.sections` từ message AI và hiển thị bong bóng citations tương ứng, rồi scroll tới `segment_index` khi người dùng click; có thể tin cậy rằng `document_id` là UUID thật do backend gán, không phải LLM bịa.
