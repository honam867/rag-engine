# rag-engine – Tech Design (Phase 9.1: Source Attribution v2 on LightRAG)

**Mục tiêu**: Xây lại cơ chế trích xuất nguồn (citations) dựa trên LightRAG, đảm bảo:
- Mỗi câu trả lời RAG đều có citations rõ ràng (khi thông tin tồn tại trong tài liệu).
- Citations bám sát những chunk mà LightRAG thực sự dùng, không rebuild context từ DB theo cách riêng.
- Có thể map ổn định từ citation → document → vị trí trong raw viewer (kể cả với tài liệu dạng bảng/cột).

---

## 1. Tech Stack & Quyết định chính

- **Engine**: LightRAG (đã dùng trong Phase 9).
  - Sử dụng API `aquery_data` để lấy **structured retrieval data** (entities, relationships, `data.chunks`, `data.references`, `metadata`).
- **Chiến lược attribution**:
  - **Nguồn gốc citation** = `chunks[*]` của LightRAG.
  - Answer LLM **không được tự bịa document_id/segment_index**; nó chỉ tham chiếu tới `chunk_id`.
  - Backend chịu trách nhiệm map `chunk_id` → `document_id` + vị trí trong document/raw viewer.
- **Mapping chunk → document**:
  - Thiết kế **bảng mapping riêng trong DB ứng dụng** (`rag_chunks_mapping`) để:
    - Lưu quan hệ giữa `chunk_id` LightRAG và document/page/segment trong hệ thống.
    - Không phụ thuộc format nội bộ của file_path hay raw prompt.
  - Bảng mapping được build ở **thời điểm ingest** (khi biết `chunk_text` và document).
- **Ingest strategy**:
  - Dùng `LightRAG.ainsert_custom_chunks(full_text, text_chunks, doc_id)` để:
    - Chủ động kiểm soát `chunk_text`.
    - Tự tính được `chunk_id = compute_mdhash_id(chunk_text, prefix="chunk-")` giống hệt LightRAG.

Lý do chọn hướng này:
- Tránh việc “đoán lại” context từ DB sau khi LightRAG đã chunk/truncate theo token.
- Có `chunk_id` ổn định → dễ mapping, dễ debug.
- Bảng mapping tách biệt giúp pipeline dễ bảo trì, không lock-in vào chi tiết triển khai nội bộ của LightRAG.

---

## 2. Cấu trúc Folder & Module

Các module chính bị ảnh hưởng:

```text
server/
  app/
    db/
      models.py                # Thêm table rag_chunks_mapping
      repositories.py          # Thêm repository cho chunk mapping

    services/
      chunker.py               # Build text_chunks + segment metadata cho ingest
      rag_engine.py            # Dùng ainsert_custom_chunks + aquery_data
      answer_engine.py         # Retrieval + LLM answer + citations v2

    schemas/
      conversations.py         # Mở rộng schema metadata cho citations v2
      documents.py             # (optional) nếu expose raw mapping qua API
```

Các file client-design sẽ được mô tả riêng, nhưng schema response phải khớp với phần `schemas/*` ở đây.

---

## 3. Configuration & Environment

Không thêm env mới, nhưng cần lưu ý:

- LightRAG:
  - `EMBEDDING_DIM`, `TOP_K`, `CHUNK_TOP_K`, `MAX_TOTAL_TOKENS`… – có thể tinh chỉnh để đảm bảo context không bị cắt quá mạnh.
- Answer LLM:
  - Sử dụng cấu hình `AnswerSettings` (Phase 8) – model JSON-friendly, temperature thấp.

---

## 4. Database Layer Design

### 4.1. Bảng mới: `rag_chunks_mapping`

Mục đích:
- Lưu mapping cố định giữa `chunk_id` LightRAG và document + vị trí trong raw text.

Schema (Supabase / Postgres):

- `rag_chunks_mapping`
  - `id` (uuid, PK, default gen_random_uuid())
  - `workspace_id` (uuid, not null)
  - `chunk_id` (text, not null)  
    - Giá trị: `compute_mdhash_id(chunk_text, prefix="chunk-")`.
  - `document_id` (uuid, not null)
  - `page_start` (int, not null) – trang đầu tiên mà chunk cover.
  - `page_end` (int, not null) – trang cuối cùng (>= page_start).
  - `segment_start_index` (int, null) – index segment đầu tiên trong raw viewer thuộc chunk.
  - `segment_end_index` (int, null) – index segment cuối cùng.
  - `char_start` (int, null) – offset bắt đầu trong `docai_full_text` (nếu tính được).
  - `char_end` (int, null) – offset kết thúc.
  - `created_at` (timestamptz, default now())

Index đề xuất:
- Unique index `uq_rag_chunks_mapping_workspace_chunk` trên `(workspace_id, chunk_id)`.
- Index trên `(document_id)` để query nhanh khi build citations cho 1 doc.

### 4.2. Repository

Trong `db/repositories.py` thêm repository (khớp style hiện tại):

- `ChunkMappingRepository`:
  - `upsert_mappings(workspace_id, mappings: list[ChunkMapping])`
  - `get_mapping_by_chunk_ids(workspace_id, chunk_ids: list[str]) -> dict[chunk_id, mapping_row]`
  - (Optional) `delete_mappings_for_document(workspace_id, document_id)`

---

## 5. Service Layer & External Integrations

### 5.1. Chunker & Ingest – xây text_chunks + mapping

File: `server/app/services/chunker.py`

**Mục tiêu Phase 9.1**:
- Vừa build `content_list` cho LightRAG ingest, vừa thu được:
  - `segments` (như hiện tại, từ Document AI JSON).
  - `text_chunks` – mỗi phần tử là chuỗi text dùng làm chunk cho LightRAG.
  - Metadata để map chunk ↔ segments.

#### 5.1.1. Xây segments (giữ nguyên Phase 7/9)

- `build_segments_from_docai`:
  - Dùng `doc.pages[*].paragraphs[*].layout.text_anchor` / `lines`.
  - Trả về `segments[*] = { segment_index, page_idx, text }`.
- `chunk_full_text_to_segments`:
  - Fallback khi không có JSON.

#### 5.1.2. Xây text_chunks từ segments

Thay vì chỉ build `content_list` inline, tách nhỏ thành 2 mức:

1. **Segment → Macro-chunk**:
   - Dùng logic giống hiện có (MAX_INGEST_CHARS_PER_ITEM):
     - Duyệt `segments` theo thứ tự (page, segment_index).
     - Gom nhiều segment liên tiếp thành một `chunk_text` sao cho:
       - Tổng độ dài ~ `MAX_INGEST_CHARS_PER_ITEM`.
   - Mỗi chunk lưu metadata:

```python
class ChunkBuildInfo(BaseModel):
    chunk_text: str          # nội dung sẽ gửi vào LightRAG
    page_start: int
    page_end: int
    segment_start_index: int
    segment_end_index: int
```

2. **Quyết định có giữ [SEG=...] hay không**:
   - Để đơn giản cho Phase 9.1:
     - **Không yêu cầu LLM parse [SEG] nữa**; citation sẽ dựa vào chunk_id.
     - Tuy nhiên, có thể giữ prefix nhẹ nếu muốn debug, ví dụ:

       ```text
       [DOC={document_id}, SEG_RANGE={seg_start}-{seg_end}]
       <text segments concat...>
       ```

     - Điều này chỉ phục vụ debugging, không bắt buộc cho logic attribution.

3. **Kết quả**:
   - `text_chunks: list[ChunkBuildInfo]` – dùng cho ingest và mapping.

#### 5.1.3. Ingest vào LightRAG + lưu mapping

Trong worker ingest (hoặc service gọi `ChunkerService`):

1. Gọi `ChunkerService.build_content_list_from_document` (refactor để trả về cả `text_chunks` thay vì chỉ `content_list`; Phase 9.1 có thể tách hàm mới như `build_chunks_for_document`).
2. Chuẩn bị:

```python
full_text = document.docai_full_text
text_chunks = [c.chunk_text for c in chunks_info]
```

3. Khởi tạo LightRAG qua `RagEngineService`:

```python
lightrag = rag_engine.get_lightrag_instance(workspace_id)
await lightrag.ainsert_custom_chunks(full_text, text_chunks, doc_id=document_id)
```

4. Tính `chunk_id` cho từng chunk_text **trước hoặc ngay sau khi gọi ainsert_custom_chunks**:

```python
from lightrag.utils import compute_mdhash_id

chunk_id = compute_mdhash_id(chunk_text, prefix="chunk-")
```

5. Tạo bản ghi mapping:

```python
ChunkMapping(
    workspace_id=workspace_id,
    chunk_id=chunk_id,
    document_id=document_id,
    page_start=info.page_start,
    page_end=info.page_end,
    segment_start_index=info.segment_start_index,
    segment_end_index=info.segment_end_index,
    # optional: char_start/char_end nếu tính được
)
```

6. Sử dụng `ChunkMappingRepository.upsert_mappings` để lưu xuống DB.

> Ghi chú: nếu LightRAG sau này thay cách tính chunk_id, việc dùng `compute_mdhash_id(chunk_text, "chunk-")` từ cùng thư viện sẽ giữ đồng bộ.

### 5.2. RagEngineService – retrieval-only context

File: `server/app/services/rag_engine.py`

Thêm API:

```python
class RetrievalContext(BaseModel):
    chunks: list[RetrievalChunk]
    references: list[ReferenceInfo]
    metadata: dict[str, Any]


class RetrievalChunk(BaseModel):
    chunk_id: str
    content: str
    reference_id: str | None
    file_path: str | None
```

```python
async def retrieve_context(
    self,
    workspace_id: str,
    question: str,
    mode: str | None = None,
) -> RetrievalContext:
    lightrag = self._get_lightrag_instance(workspace_id)
    from lightrag import QueryParam

    query_mode = mode or self.settings.query_mode
    param = QueryParam(mode=query_mode)
    data = await lightrag.aquery_data(question, param)
    # data theo format đã mô tả trong base.py
```

Mapping:

- `chunks = [RetrievalChunk(...)]` từ `data["data"]["chunks"]`:
  - `chunk_id = chunk["chunk_id"]`
  - `content = chunk["content"]`
  - `reference_id = chunk.get("reference_id")`
  - `file_path = chunk.get("file_path")`
- `references` từ `data["data"]["references"]`.
- `metadata = data["metadata"]`.

### 5.3. AnswerEngineService – answer + citations v2

File: `server/app/services/answer_engine.py`

#### 5.3.1. Interface

```python
class AnswerEngineService:
    async def answer_with_citations(
        self,
        workspace_id: str,
        conversation_id: UUID,
        question: str,
        history: list[dict] | None = None,
    ) -> dict[str, Any]:
        """
        Trả về:
        {
          "answer": str,
          "sections": list[AnswerSectionV2],
          "citations": list[CitationV2],
          "llm_usage": LLMUsage | None,
        }
        """
```

#### 5.3.2. Bước 1 – Retrieval

1. Gọi `context = await rag_engine.retrieve_context(...)`.
2. Lấy `chunks = context.chunks`.
3. Nếu `chunks` rỗng:
   - Có thể trả lời “Không tìm thấy thông tin” và không gắn citations.

#### 5.3.3. Bước 2 – Build prompt cho Answer LLM

System prompt (tiếng Anh, khái quát):

- Giải thích:
  - Bạn được cung cấp nhiều **chunks** context.
  - Mỗi chunk bắt đầu bằng `[CHUNK_ID=chunk:xxxx]`.
  - Bạn phải:
    - Trả lời câu hỏi dựa trên thông tin trong chunks.
    - Chia câu trả lời thành `sections`.
    - Với mỗi section, trả về danh sách `source_ids` là các chuỗi `chunk:{chunk_id}` bạn đã dùng.
  - Nếu không đủ thông tin trong context, trả lời “Không tìm thấy thông tin trong tài liệu” và **không bịa số liệu**.

User prompt (structure):

```text
Context chunks:

[CHUNK_ID=chunk:abc123]
<content của chunk 1>

[CHUNK_ID=chunk:def456]
<content của chunk 2>
...

User question:
<question text>
```

Yêu cầu LLM trả JSON:

```jsonc
{
  "sections": [
    {
      "text": "....",
      "source_ids": ["chunk:abc123", "chunk:def456"]
    }
  ]
}
```

#### 5.3.4. Bước 3 – Gọi Answer LLM

- Dùng `LLMClient` (Phase 8) với `response_format={"type": "json_object"}`.
- Parse JSON:
  - Nếu fail → fallback: treat toàn bộ answer là một section, `source_ids = []` (không citation).

#### 5.3.5. Bước 4 – Map source_ids → RetrievalChunk

1. Build dict:

```python
chunk_by_id = {f"chunk:{c.chunk_id}": c for c in chunks}
```

2. Với mỗi `section.source_ids[*]`:
   - Nếu không nằm trong `chunk_by_id` → bỏ (tránh bịa).
   - Thu thập set `used_chunk_ids` cho tất cả sections.

#### 5.3.6. Bước 5 – Map RetrievalChunk → Citation v2

1. Lấy tất cả `used_chunk_ids` → query mapping từ DB:

```python
mappings = chunk_mapping_repo.get_mapping_by_chunk_ids(workspace_id, used_chunk_ids)
```

2. Cho từng `source_id` hợp lệ:
   - `chunk_id = source_id.removeprefix("chunk:")`
   - `mapping = mappings.get(chunk_id)`
   - Nếu không có mapping → bỏ source_id (không thể map).
   - Nếu có:

```python
CitationV2(
    source_id=source_id,
    document_id=mapping.document_id,
    page_idx=mapping.page_start,  # hoặc range nếu cần
    segment_index=mapping.segment_start_index,  # dùng cho scroll
    snippet_preview=build_snippet(chunk.content),
)
```

3. Gán:
   - `section.citations` = danh sách citation tương ứng với `section.source_ids`.
   - `citations_flatten` = union tất cả citations (loại bỏ trùng lặp theo `(document_id, segment_index, source_id)`).

#### 5.3.7. Kết quả trả về

```python
return {
  "answer": "\n\n".join(sec.text for sec in sections),
  "sections": sections,
  "citations": citations_flatten,
  "llm_usage": usage,
}
```

---

## 6. API & Schemas

### 6.1. Pydantic schemas

Trong `schemas/conversations.py` (hoặc file thích hợp) thêm:

```python
class CitationV2(BaseModel):
    source_id: str
    document_id: UUID
    page_idx: int | None = None
    segment_index: int | None = None
    snippet_preview: str | None = None


class AnswerSectionV2(BaseModel):
    text: str
    source_ids: list[str]
    citations: list[CitationV2]
```

Metadata message AI:

```python
class AiMessageMetadata(BaseModel):
    sections: list[AnswerSectionV2] | None = None
    citations: list[CitationV2] | None = None
    llm_usage: LLMUsage | None = None
```

### 6.2. API `POST /messages`

- Response message AI:
  - `content`: join sections text.
  - `metadata.sections`: danh sách `AnswerSectionV2`.
  - `metadata.citations`: flatten citations.

Client có thể:
- Render số thứ tự bong bóng dựa trên `section.citations[*]` (order theo xuất hiện).
- Khi click:
  - Dùng `document_id` + `segment_index` (hoặc `page_idx`) để scroll raw viewer.

---

## 7. Background Jobs

- Worker ingest:
  - Sau khi parse Document AI:
    - Gọi chunker để build `text_chunks + ChunkBuildInfo`.
    - Gọi `lightrag.ainsert_custom_chunks`.
    - Tính `chunk_id` cho mỗi text_chunk.
    - Ghi mapping vào `rag_chunks_mapping`.

Không cần worker mới; chỉ mở rộng logic job ingest hiện tại.

---

## 8. Logging & Monitoring

- Log retrieval context:
  - workspace, conversation, số lượng chunks, top vài chunk_id + preview.
- Log mapping:
  - Khi ingest, log số mapping row ghi vào DB.
- Log citations:
  - Khi answer, log số citations per section.

Những log này hỗ trợ debug khi citation hiển thị sai.

---

## 9. Kế hoạch Implement & Testing

**Thứ tự đề xuất:**

1. Thêm bảng `rag_chunks_mapping` + repository.
2. Refactor chunker + ingest để:
   - Build `text_chunks` + `ChunkBuildInfo`.
   - Gọi `ainsert_custom_chunks`.
   - Lưu mapping chunk_id.
3. Implement `RagEngineService.retrieve_context` dựa trên `aquery_data`.
4. Implement `AnswerEngineService.answer_with_citations`:
   - Prompt LLM, parse sections + source_ids.
   - Map chunk_id → citations.
5. Cập nhật schema metadata + API `messages`.
6. Testing:
   - Unit test cho mapping chunk_id → document/segment.
   - E2E:
     - Upload PDF có bảng/cột.
     - Hỏi câu bám sát số liệu.
     - Kiểm tra:
       - Answer chính xác.
       - Bong bóng số highlight đúng dòng/đoạn trong raw viewer.

---

## 10. Ghi chú & Open Issues

- Độ chính xác cuối cùng phụ thuộc vào:
  - Chất lượng parse Document AI.
  - Chiến lược nhóm segments thành chunk_text (nếu chunk quá dài, highlight sẽ rộng).
  - Tham số retrieval LightRAG (top_k, max_total_tokens).
- Có thể cần Phase 9.2 để:
  - Tinh chỉnh segmentation theo từng domain (bảng, báo cáo tài chính…).
  - Thêm heuristic “sub-span highlighting” (char_start/char_end) thay vì highlight cả chunk.
  - Tích hợp thêm rerank model nếu LightRAG retrieval chưa đủ tốt cho 1 workspace chứa nhiều tài liệu.

