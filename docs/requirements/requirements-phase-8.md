# rag-engine – Phase 8 Requirements (Retrieval-Only RAG & Answer Orchestrator)

## 1. Mục tiêu & Phạm vi (Goals & Scope)

- **Mục tiêu chính**
  - Tách hoàn toàn bước **truy xuất (retrieval)** khỏi bước **trả lời (answer generation)**:
    - RAG-Anything/LightRAG được dùng như **hạ tầng ingest + retrieval** (vector + graph).
    - Hệ thống rag-engine tự xây dựng một **Answer Orchestrator** làm “hộp đen trả lời” duy nhất.
  - Đưa Explainable RAG lên mức:
    - **Ưu tiên độ chính xác** của trích dẫn (không “chắp vá” text-matching toàn workspace).
    - Luôn lưu lại được nguồn context đã dùng (retrieved_segments), phục vụ hiển thị và debug.
  - Chuẩn hóa pipeline để sau này có thể **scale & mở rộng**:
    - Dễ đổi model, tích hợp LangChain / tools, thêm các chiến lược memory, tracking chi phí/tokens.

- **Phạm vi công việc**
  - Backend / server:
    - Thiết kế và implement:
      - Lớp **retrieval-only** trên RAG-Anything (không dùng `rag.aquery` cho chat nữa).
      - Service mới **Answer Orchestrator** (ví dụ: `AnswerEngineService`) chịu trách nhiệm:
        - Lấy retrieved_segments.
        - Build prompt (context + history + hệ thống).
        - Gọi LLM (OpenAI hoặc provider khác) và parse JSON `sections + source_ids`.
        - Gắn citations dựa trên ID (document_id + segment_index).
        - Ghi lại metadata (sections, citations, retrieved_segments, usage).
      - Abstraction cho LLM client (model routing, token tracking).
    - Điều chỉnh API chat hiện tại (`POST /conversations/{id}/messages`) để:
      - Không còn gọi `RagEngineService.query` (dựa trên `rag.aquery`).
      - Gọi qua Answer Orchestrator mới.
  - Các phase trước giữ nguyên ingestion:
    - Phase 2: Document AI OCR + lưu `docai_full_text` + JSON raw.
    - Phase 3: chunker + ingest vào RAG-Anything bằng `content_list`.
    - Phase 7.1: segmentation từ JSON (build_segments_from_docai) cho raw viewer.
    - Phase 7.2: segment_id `[SEG={document_id}:{segment_index}]` đã embed vào `content_list`.

- **Out of scope**
  - Không redesign kiến trúc tổng trong `architecture-overview.md`.
  - Không thay đổi cách parse/ingest tài liệu (Document AI, R2, bảng documents, rag_documents vẫn giữ như hiện tại).
  - Không bắt buộc phải migrate toàn bộ dữ liệu cũ; behavior với workspace/doc cũ sẽ được định nghĩa rõ (citations có thể yếu hơn).

- **Deliverables**
  - Tài liệu thiết kế:
    - `docs/design/phase-8-design.md`.
  - Thay đổi code (sau phase này):
    - Service retrieval-only + Answer Orchestrator.
    - Cập nhật `messages` API để dùng pipeline mới.
  - Cập nhật implement log:
    - `docs/implement/implement-*-phase-8-*.md` khi implement xong.

---

## 2. Các khái niệm & thực thể chính (Key Concepts & Entities)

### 2.1. RetrievedSegment

- Mô tả:
  - Một đoạn văn bản (segment) được retrieval engine chọn ra làm context cho một câu hỏi.
  - Liên kết 1-1 với segment trong raw viewer (`/raw-text`) nhờ `document_id` + `segment_index`.
- Thuộc tính (conceptual):
  - `segment_id: string` – dạng chuẩn `"${document_id}:${segment_index}"`.
  - `document_id: UUID` – id tài liệu trong bảng `documents`.
  - `segment_index: int` – số thứ tự đoạn, trùng với `segments[*].segment_index` trong `/raw-text`.
  - `page_idx: int | null` – trang gốc (từ Document AI JSON nếu có).
  - `text: string` – nội dung đoạn.
  - `score: float` – độ liên quan từ retrieval (vector/graph).

### 2.2. AnswerSection & Citation

- **AnswerSection**
  - Một “mảng” trong câu trả lời của AI, tương tự cách NotebookLM chia đoạn.
  - Thuộc tính chính:
    - `text: string` – đoạn trả lời.
    - `source_ids: string[]` – danh sách `segment_id` mà LLM cho rằng liên quan (từ context).
    - `citations: Citation[]` – citations đã được backend map từ `source_ids` → segment cụ thể (document_id + segment_index).

- **Citation**
  - Đoạn nguồn cụ thể dùng cho bong bóng số:
    - `document_id: UUID`
    - `segment_index: int`
    - `page_idx: int | null`
    - `snippet_preview: string` – trích ngắn 1 phần của segment text để preview.

### 2.3. RetrievedSegmentsEnvelope / AnswerMetadata

- **RetrievedSegmentsEnvelope**
  - Object nội bộ giữ toàn bộ `retrieved_segments` cho một lần query:
    - Giúp debug, audit, và dùng làm “nguồn fallback” nếu không có `source_ids`.
- **AnswerMetadata** (lưu trong `messages.metadata`):
  - Tối thiểu:
    - `sections: AnswerSection[]`
    - `citations: Citation[]` (flatten).
  - Optional:
    - `retrieved_segments: RetrievedSegment[]` (có thể rút gọn cho client hoặc chỉ log nội bộ).
    - `llm_usage: { model, prompt_tokens, completion_tokens, total_tokens, cost? }`.

### 2.4. Retrieval Engine vs Answer Orchestrator

- **Retrieval Engine** (RAG-Anything / LightRAG-based)
  - Nhiệm vụ:
    - Nhận câu hỏi text.
    - Truy xuất top-k segments liên quan (dựa trên vector + graph).
    - Trả về danh sách `RetrievedSegment`.
  - Không trực tiếp gọi LLM để sinh câu trả lời.

- **Answer Orchestrator**
  - Nhiệm vụ:
    - Nhận `question`, `workspace_id`, (optional) history.
    - Gọi Retrieval Engine → lấy `retrieved_segments`.
    - Build prompt chuẩn (có `[SEG=doc_id:segment_index]` từ `retrieved_segments`).
    - Gọi LLM thông qua LLM client abstraction.
    - Ép LLM trả JSON `{ sections: [{ text, source_ids[] }] }`.
    - Map `source_ids` ↔ `retrieved_segments` → build `citations`.
    - Lưu `metadata` (sections, citations, usage) vào message.
    - Trả dữ liệu cho API / client.

---

## 3. Luồng nghiệp vụ (User/System Flows)

### 3.1. Chat với Explainable RAG (Phase 8)

1. User gửi câu hỏi:
   - `POST /api/conversations/{conversation_id}/messages` với `content`.
2. API:
   - Lưu message `role='user'`.
   - Tạo message `role='ai'` với `status='pending'`.
   - Trigger background task `AnswerOrchestrator.answer_question(...)`.
3. Answer Orchestrator:
   - Load `workspace_id` từ conversation.
   - Gọi Retrieval Engine:
     - Input: `workspace_id`, `question`, (optional) config về top_k.
     - Output: `retrieved_segments: RetrievedSegment[]`.
   - Build prompt:
     - Context:
       - Mỗi segment được render dạng: `[SEG={document_id}:{segment_index}] <segment text>`.
       - Có thể kèm thêm vài message history gần nhất (Phase sau).
     - System prompt: persona, yêu cầu JSON format, quy tắc trích dẫn.
     - User question: nội dung câu hỏi.
   - Gọi LLM (OpenAI hoặc provider tương thích) qua LLM client:
     - Nhận response dạng string (expected JSON).
     - Parse JSON thành `{ sections[*].{text, source_ids[]} }`.
   - Map citations:
     - Với mỗi `source_id` nằm trong `retrieved_segments`:
       - Parse `segment_id` → `document_id`, `segment_index`.
       - Lấy `page_idx`, `text` từ `retrieved_segments` → build `Citation`.
     - **Không** tạo citations bằng text-matching toàn workspace (tránh “chắp vá”).
   - Build `answer_text`: join `sections[*].text` bằng `\n\n`.
   - Lưu `messages`:
     - `content = answer_text`.
     - `metadata.sections = AnswerSection[]` (đã gắn citations).
     - `metadata.citations = flatten(citations)`.
     - Optional: `metadata.retrieved_segments` (nếu muốn expose) + `metadata.llm_usage`.
4. API background:
   - Update message AI → `status='done'`.
   - Gửi event realtime `message.status_updated` với `content` + `metadata`.
5. Client:
   - Render answer như hiện tại.
   - Render bong bóng số theo `sections[*].citations`.
   - Click → fetch raw-text viewer (đã có) và scroll tới `segment_index`.

### 3.2. Flow với document / workspace cũ

- Documents đã ingest trước Phase 7.2 (không có `[SEG=...]`):
  - Retrieval Engine vẫn trả segments, nhưng:
    - `segment_id` không theo chuẩn `"{document_id}:{segment_index}"` hoặc không có DocAI JSON đầy đủ.
  - Requirements Phase 8:
    - **Không cố gắng text-match toàn workspace để tạo citations**.
    - Chấp nhận:
      - `sections[*].citations` có thể rỗng.
      - `retrieved_segments` vẫn được log để debug (có thể cho UI hiển thị “context tham khảo” dạng khác).

---

## 4. Kiến trúc & Thiết kế kỹ thuật (Architecture & Technical Design – high level)

### 4.1. Backend / Service Layer

- Thêm 2 layer rõ ràng:
  - **Retrieval Engine Service** (RAG-Anything adapter v2):
    - Cung cấp interface `retrieve_segments(workspace_id, question, top_k, ...) -> RetrievedSegment[]`.
    - Dùng LightRAG / RAG-Anything chỉ cho retrieval, không dùng `rag.aquery` trong flow chat.
  - **Answer Orchestrator Service**:
    - Nhận `workspace_id`, `question`, (optional) history.
    - Gọi Retrieval Engine → `retrieved_segments`.
    - Gọi LLM client → JSON sections + source_ids.
    - Map citations, build metadata, update messages.

- Lớp LLM client:
  - Một abstraction riêng (ví dụ: `LLMClient`):
    - `generate_json_answer(prompt, ...) -> (raw_text, parsed_json, usage)`.
    - Có thể route tới nhiều provider/model khác nhau.
    - Dễ plug-in LangChain / tools ở bên trong nếu cần.

### 4.2. Database Schema (Supabase / Postgres)

- **Không bắt buộc thêm bảng mới** trong Phase 8:
  - Vẫn dùng:
    - `documents` (docai_full_text, docai_raw_r2_key, status).
    - `rag_documents` (mapping document_id ↔ rag_doc_id).
    - `conversations`, `messages` (metadata JSON).
- Thông tin mới (usage, retrieved_segments) có thể lưu vào `messages.metadata`:
  - `metadata.retrieved_segments` (optional).
  - `metadata.llm_usage`.
- Nếu cần thêm bảng riêng để log long-term (Phase sau):
  - Có thể tạo `llm_traces` / `rag_queries` để lưu trace chi tiết; Phase 8 chỉ cần spec-level (design), chưa bắt buộc implement DB mới.

### 4.3. External Services / Storage

- **RAG-Anything / LightRAG**:
  - Giữ:
    - `insert_content_list` cho ingest (như Phase 3/7.2).
    - Storage PGVector + graph như hiện tại.
  - Bỏ trong flow chat:
    - Không dùng `aquery` của RAG-Anything nữa cho messages.
  - Retrieval:
    - Dùng API/khả năng của LightRAG để lấy top-k chunks; nếu không có public API phù hợp, có thể:
      - Dùng LightRAG internal helper (nếu exposed).
      - Hoặc đọc trực tiếp từ các bảng vector/graph do LightRAG tạo.

- **LLM Provider**:
  - Không dùng `openai_complete_if_cache` của LightRAG cho bước answer nữa.
  - Thay bằng LLM client riêng, trực tiếp gọi OpenAI / tương thích OpenAI APIs (hoặc provider khác).

---

## 5. API Endpoints (Dự kiến)

### 5.1. Chat / Messages (giữ nguyên contract HTTP)

- `POST /api/conversations/{conversation_id}/messages`
  - Request: không đổi (vẫn gửi `content`, optional `metadata` từ client).
  - Response: vẫn trả `MessageListResponse` với 2 messages (user + ai pending).
  - Behavior mới:
    - Background task gọi Answer Orchestrator (thay vì `RagEngineService.query`).
    - AI message done có:
      - `content`: câu trả lời (join sections).
      - `metadata.sections[*].{text, source_ids[], citations[]}`.
      - `metadata.citations` (flatten).
      - Optional: `metadata.llm_usage`, `metadata.retrieved_segments`.

### 5.2. Debug / Observability (optional)

- Có thể thêm endpoint nội bộ (Phase 8 hoặc phase sau):
  - `GET /api/conversations/{conversation_id}/messages/{message_id}/retrieval`
    - Trả về `retrieved_segments` + `llm_usage` để debug RAG pipeline.
  - Phase 8 chỉ cần ghi nhận nhu cầu này trong design, không bắt buộc implement ngay.

Các endpoint khác (`/raw-text`, `/documents`, `/workspaces`) không đổi behavior HTTP.

---

## 6. Kế hoạch triển khai (Implementation Plan)

1. **Thiết kế Retrieval Engine adapter**
   - Đọc LightRAG / RAG-Anything để tìm cách lấy top-k chunks:
     - Ưu tiên dùng API chính thức (nếu có).
     - Nếu không, define rõ cách đọc từ PGVector tables.
   - Chuẩn hóa thành `RetrievedSegment[]` (segment_id, document_id, segment_index, page_idx, text, score).
   - Đảm bảo reuse segmentation từ Phase 7.1 (`build_segments_from_docai`) khi cần.

2. **Thiết kế & implement Answer Orchestrator**
   - Tạo service mới (ví dụ: `AnswerEngineService`):
     - API: `answer_question(workspace_id, conversation_id, question, ...)`.
     - Chỉ sử dụng `RagEngineService` cho retrieval (ingest giữ nguyên).
   - Định nghĩa prompt format chuẩn (context + `[SEG=...]` + instructions JSON).
   - Định nghĩa JSON schema output và parser robust (tolerant với lỗi).

3. **LLM Client abstraction**
   - Tạo lớp `LLMClient`:
     - Đọc config model từ `RagSettings` hoặc `LLMSettings` mới.
     - Gọi API tương thích OpenAI (hoặc provider khác).
     - Ghi nhận `usage` (tokens, model) và trả về cùng response.
   - Chuẩn bị chỗ hook để sau này tích hợp LangChain / tools (function calling).

4. **Cập nhật messages API**
   - Thay `_process_ai_message_background`:
     - Không gọi `RagEngineService.query`.
     - Gọi `AnswerEngineService.answer_question`.
     - Map kết quả về `messages` như current contract (content + metadata).
   - Đảm bảo realtime event `message.status_updated` mang đủ metadata mới.

5. **Dọn dẹp / hạ cấp logic cũ**
   - Ghi rõ trong code và docs:
     - `RagEngineService.query` không còn dùng cho chat (có thể giữ để phục vụ API khác, nếu cần).
     - `_build_citations_for_sections` (text-matching Phase 7.1) chỉ còn là helper fallback cho legacy, không dùng trong pipeline chính.
   - Cập nhật docs Phase 7.2 để reference sang Phase 8 khi đọc lại.

6. **Testing & rollout**
   - Test với workspace mới (tài liệu ingest sau 7.2) để đảm bảo:
     - Có citations chính xác (theo document_id + segment_index).
     - Raw viewer + bong bóng số hoạt động đúng.
   - Với workspace cũ:
     - Đảm bảo không crash, nhưng chấp nhận citations có thể rỗng / yếu hơn.

---

## 7. Ghi chú & Giả định (Notes & Assumptions)

- RAG-Anything / LightRAG:
  - Được dùng lâu dài như hạ tầng ingest + retrieval (vector + graph), không bị “vứt bỏ”.
  - Version hiện tại trong repo được giữ ổn định; nếu upgrade, cần kiểm tra lại API retrieval.
- Phase 2, 3, 7, 7.1, 7.2:
  - **Vẫn giữ**:
    - Document AI OCR + JSON raw trên R2.
    - Segmentation từ JSON (`build_segments_from_docai`) là nguồn chuẩn cho `segment_index`.
    - Ingest vào RAG-Anything với text prefix `[SEG={document_id}:{segment_index}]`.
    - Raw text viewer `/raw-text`.
  - **Không sử dụng nữa trong pipeline chính Phase 8**:
    - `RagEngineService.query` dựa trên `rag.aquery` để sinh answer.
    - Chiến lược text-matching toàn workspace (`_build_citations_for_sections`) để đoán citations.
    - Dependency vào LLM của RAG-Anything bên trong flow chat (chỉ còn dùng LLM riêng).
- Ưu tiên:
  - Khi phải trade-off “luôn có citations” vs “độ chính xác”:
    - **Primary citations** (bong bóng số) chỉ được tạo khi có ID match với `retrieved_segments`.
    - Thông tin retrieve thêm (top-k segments) có thể log riêng hoặc expose dưới dạng khác, nhưng không bắt user hiểu đó là “nguồn chắc chắn”.

