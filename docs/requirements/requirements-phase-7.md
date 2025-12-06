# rag-engine-phase-7 – Explainable RAG & Raw Document Viewer

## 1. Mục tiêu & Phạm vi (Goals & Scope)

- **Mục tiêu chính**
  - Tăng độ tin cậy và giải thích được của câu trả lời RAG bằng cách:
    - Cho phép người dùng xem **text thô** sau khi parse từng document.
    - Liên kết từng đoạn trả lời của AI với **đoạn text nguồn cụ thể** trong document (kiểu “bong bóng số” như NotebookLM).
  - Không đụng tới cách connect Supabase/R2/RAG-Anything, chỉ bổ sung tầng explainability + viewer.

- **Phạm vi công việc**
  - Backend (server):
    - Thêm API để lấy text thô đã parse cho từng document (ở mức segment).
    - Mở rộng response của chat/RAG để:
      - Trả về cấu trúc **sections** trong message AI.
      - Mỗi section kèm danh sách citations tham chiếu tới **segment nguồn**.
  - Client (UI):
    - Thêm viewer cho document ở dạng text thô.
    - Khi click trích dẫn trong câu trả lời AI:
      - Scroll viewer đến đúng đoạn text nguồn tương ứng.
      - Highlight đoạn đó để người dùng dễ đối chiếu.

- **Ngoài phạm vi (out-of-scope) cho Phase 7**
  - Không thay đổi kiến trúc tổng trong `architecture-overview.md`.
  - Không thêm/chỉnh sửa schema DB Supabase (tận dụng `docai_full_text` hiện có).
  - Không thay đổi pipeline parse (Phase 2) và ingest (Phase 3) ngoài việc tái sử dụng dữ liệu đã có.

- **Kết quả kỳ vọng (Deliverables)**
  - API server:
    - Endpoint lấy text thô parse theo document.
    - Response chat AI có cấu trúc sections + citations (ở dạng JSON ổn định).
  - UI client:
    - Màn hình/ô viewer document dạng text thô.
    - Interaction hover/click trên citations để xem và nhảy tới đoạn nguồn.

---

## 2. Các khái niệm & thực thể chính (Key Concepts & Entities)

### 2.1. Document Raw Text & Segments

- **Document raw text**:
  - Là nội dung `docai_full_text` của document sau khi Phase 2 OCR bằng Document AI.
  - Được server cắt (chunk) thành các **segments** để:
    - Dùng cho viewer (hiển thị text thô).
    - Dùng làm đơn vị nguồn (source segment) cho citations trong câu trả lời AI.

- **Segment**
  - Đơn vị đoạn text nhỏ, gắn với:
    - `document_id` (thuộc document nào).
    - `segment_index` (số thứ tự trong document, 0,1,2,…).
    - `page_idx` (nếu xác định được từ chunker / JSON Document AI, v1 có thể là 0 hoặc gần đúng).
    - `text` (đoạn text thô).
  - Segment là “source of truth” mà cả viewer và RAG citations cùng tham chiếu tới.

### 2.2. Chat Sections & Citations

- **Section (trong message AI)**
  - Là một phần của câu trả lời AI (ví dụ một đoạn văn hoặc một bullet group) mà UI có thể gán một hoặc nhiều citations.
  - Mỗi section có:
    - `text`: đoạn trả lời của AI (string).
    - `citations`: danh sách các tham chiếu tới segments nguồn (mỗi citation chứa ít nhất `document_id` + `segment_index`, có thể thêm `page_idx`).

- **Citation**
  - Cấu trúc dùng để nối từ câu trả lời AI → nguồn trong document.
  - V1 yêu cầu:
    - `document_id`: document chứa đoạn nguồn (UUID thực từ DB, không phải do LLM bịa).
    - `segment_index`: segment trong document đó mà AI dùng để trả lời.
    - (Optional nhưng khuyến nghị): `page_idx`, `snippet_preview` (đoạn text ngắn để hiển thị nhanh).
  - Citations sẽ được lưu trong `messages.metadata` ở DB, để client render bong bóng số.
  - **Mapping citations không giao cho LLM**:
    - LLM chỉ sinh `sections[*].text`.
    - Backend sẽ dùng text của section để tìm đoạn nguồn phù hợp nhất trong các segments (`docai_full_text` đã chunk), rồi tự gán `document_id` + `segment_index` cho citations.

---

## 3. Luồng nghiệp vụ (User/System Flows)

### 3.1. View text thô của một document

1. User chọn một workspace từ UI.
2. User vào danh sách documents (đã có từ Phase 1/2/3).
3. User click vào một document trong danh sách.
4. Client gọi API mới (Phase 7) để lấy text thô đã parse:
   - Ví dụ: `GET /api/workspaces/{workspace_id}/documents/{document_id}/raw-text`.
5. Server:
   - Kiểm tra quyền truy cập workspace (Supabase JWT, ownership như hiện tại).
   - Đọc `documents.docai_full_text`:
     - Nếu `status != 'parsed'` và `status != 'ingested'` → trả lỗi hoặc message “document chưa parse xong”.
   - Cắt text thành `segments` theo strategy đơn giản (tương đồng với Chunker Phase 3).
   - Trả JSON gồm danh sách segments: `{ segment_index, page_idx, text }`.
6. Client:
   - Render viewer hiển thị tất cả segments (theo thứ tự), mỗi segment có thể được gắn `data-segment-index` để phục vụ scroll/highlight.

### 3.2. Chat với RAG + nhận citations theo segment

1. User mở một conversation trong workspace (luồng Phase 3/5 hiện tại).
2. User gửi câu hỏi (message `role='user'`).
3. Server:
   - Lưu message `user` như Phase 3/5.
   - Gọi RAG Engine (`RagEngineService.query`) với:
     - `workspace_id`, `question`.
   - RAG Engine:
     - Lấy context từ LightRAG / RAG-Anything như cũ (theo workspace).
     - Trong prompt gửi vào LLM:
       - Đưa kèm các đoạn context có gắn thông tin segment (ví dụ: “SEG_15: <text segment>”), dựa trên chunker/segments.
       - Yêu cầu LLM trả JSON chứa:
         - `sections[]` (mỗi section text + danh sách mã segment mà section đó dựa vào).
   - Server parse JSON kết quả, map các mã segment về `document_id` + `segment_index`.
   - Lưu message `ai` với:
     - `content`: có thể là:
       - Chuỗi text gộp từ các sections (để backward-compatible).
     - `metadata.sections`: mảng sections như RAG trả (đã chuẩn hóa).
4. Client nhận message `ai` (qua HTTP response + WebSocket Phase 5).
5. Client hiển thị câu trả lời:
   - Với mỗi section:
     - Render text như bình thường.
     - Render bong bóng số `[1]`, `[2]` theo thứ tự citations list; mỗi bong bóng tương ứng với một `citation` (link tới `document_id` + `segment_index`).

### 3.3. Hover/Click citation để xem đoạn nguồn

1. User hover vào bong bóng số `[n]` trong section.
2. Client:
   - Từ `citation` lấy ra:
     - `document_id`, `segment_index`, `snippet_preview` (nếu đã được server trả).
   - Nếu viewer document tương ứng đang mở và đã có segments trong memory:
     - Highlight tạm thời segment tương ứng.
     - Option: show popup nhỏ với snippet (text segment, có thể cắt ngắn).
   - Nếu viewer chưa mở:
     - Có thể:
       - a) Chỉ show snippet trong popup (không scroll), hoặc
       - b) Tự động mở viewer document (tuỳ thiết kế UI – Phase 7 chỉ yêu cầu “có thể”).
3. User click vào bong bóng số `[n]`:
   - Client đảm bảo viewer của document tương ứng được mở (nếu chưa có, mở tab/pane viewer).
   - Scroll viewer đến `segment_index` tương ứng (dựa trên `data-segment-index`).
   - Highlight segment đó (vd đổi màu nền), có thể giữ highlight cho đến khi user click chỗ khác.

---

## 4. Kiến trúc & Thiết kế kỹ thuật (Overview – ở mức requirements)

> Chi tiết implementation sẽ được mô tả ở `docs/design/phase-7-design.md`. Phần này chỉ chốt yêu cầu high‑level để không phá vỡ kiến trúc hiện tại.

### 4.1. Backend / Service Layer

- Giữ nguyên các layer:
  - `api/routes/documents.py` – thêm endpoint raw-text viewer.
  - `api/routes/messages.py` – mở rộng cấu trúc response cho messages `ai`.
  - `services/chunker.py` – có thể reuse logic để cắt `docai_full_text` thành segments, nhưng Phase 7 không yêu cầu thay đổi pipeline ingest.
  - `services/rag_engine.py` – mở rộng `query()` để trả về dạng `{ answer_text, sections, citations }` thay vì chỉ `answer` string.

- Không yêu cầu thay đổi:
  - `services/docai_client.py`, `services/parser_pipeline.py`, `workers/parse_worker.py`.
  - `services/jobs_ingest.py`, `workers/ingest_worker.py` (ingest vẫn như Phase 3).

### 4.2. Database Schema (Supabase / Postgres)

- Không thêm bảng mới cho Phase 7.
- Lưu cấu trúc sections/citations trong message AI thông qua:
  - Trường `messages.metadata` (JSON):
    - Yêu cầu mới: metadata của message `role='ai'` cần có thể chứa:
      - `sections`: danh sách section kèm citations.
      - `citations_flat`: danh sách citations flatten (optional) nếu cần cho UI đơn giản.

### 4.3. External Services / Storage

- Cloudflare R2:
  - Không thay đổi; vẫn lưu file gốc và JSON Document AI như Phase 2.
- RAG‑Anything / LightRAG:
  - Không thay đổi cách khởi tạo hay storage.
  - Phase 7 chỉ thay đổi cách **gọi LLM** trong `RagEngineService.query` (prompt) để yêu cầu trả JSON có sections + citations, không thay đổi LightRAG query mode.

---

## 5. API Endpoints (Dự kiến)

### 5.1. Viewer text thô – Documents

- `GET /api/workspaces/{workspace_id}/documents/{document_id}/raw-text`
  - **Mục đích**: lấy text thô đã parse, chia thành segments để hiển thị và map citations.
  - **Auth**: yêu cầu Supabase JWT, user phải là owner của workspace.
  - **Input**:
    - Path params: `workspace_id`, `document_id`.
  - **Output (dự kiến)**:
    ```json
    {
      "document_id": "uuid",
      "workspace_id": "uuid",
      "status": "parsed | ingested",
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
  - **Error cases**:
    - 404 nếu document không thuộc workspace hoặc không tồn tại.
    - 409/400 nếu document chưa được parse (`status = 'pending'` hoặc `status = 'error'`).

### 5.2. Chat messages – mở rộng response AI

- `POST /api/conversations/{conversation_id}/messages`
  - Input không thay đổi (user gửi `{ content }`).
  - Output (với message `ai`) bổ sung:
    - `metadata.sections`: danh sách sections:
      ```json
      {
        "id": "ai-message-id",
        "role": "ai",
        "content": "Toàn bộ câu trả lời (có thể là join của sections)...",
        "metadata": {
          "sections": [
            {
              "text": "Đoạn trả lời 1...",
              "citations": [
                {
                  "document_id": "uuid",
                  "segment_index": 15,
                  "page_idx": 2,
                  "snippet_preview": "Đoạn text nguồn rút gọn..."
                }
              ]
            }
          ]
        }
      }
      ```
  - WebSocket events `message.created` / `message.status_updated` (Phase 5) không cần đổi tên event; payload chỉ cần mang theo `metadata` mới nếu có.

---

## 6. Kế hoạch triển khai (Implementation Plan – high level)

1. **Backend – raw text viewer**
   - Thêm endpoint `GET /documents/{document_id}/raw-text`.
   - Reuse/định nghĩa logic cắt `docai_full_text` thành segments (chia paragraph) có `segment_index`, `page_idx`.
   - Đảm bảo chỉ trả text cho document đã `parsed` hoặc `ingested`.
2. **Backend – RAG query với sections + citations**
   - Cập nhật `RagEngineService.query`:
     - Điều chỉnh system prompt/combined prompt để yêu cầu LLM **chỉ** trả JSON `{ sections: [ { "text": "..." }, ... ] }` (không yêu cầu LLM tự điền `document_id`/`segment_index`).
     - Parse JSON, chuẩn hóa cấu trúc sections (ít nhất có field `text` cho mỗi section).
   - Cập nhật `api/routes/messages.py` để:
     - Sau khi có `sections`, backend chạy bước mapping riêng:
       - Dùng `section.text` để tìm đoạn nguồn tương ứng trong segments của các document trong workspace (so khớp text).
       - Tạo `citations` với `document_id` + `segment_index` + `snippet_preview` dựa trên kết quả tìm kiếm (không dùng giá trị LLM bịa).
     - Lưu `metadata.sections` (đã có citations gắn vào từng section) và `metadata.citations` (flatten).
     - Giữ backward-compat (client cũ vẫn đọc được `content` text).
3. **Client – document viewer**
   - Thêm UI cho viewer text thô:
     - Gọi API raw-text khi click document.
     - Hiển thị segments theo thứ tự, mỗi segment gắn `segment_index` để scroll.
4. **Client – chat + citations interaction**
   - Đọc `metadata.sections` từ message AI:
     - Render sections và bong bóng số cho mỗi citation.
   - Hover:
     - Highlight snippet text nguồn (dựa trên segments đã load) và show popup (nếu cần).
   - Click:
     - Scroll viewer tới `segment_index` tương ứng và highlight.
5. **Testing & UX validation**
   - Test với:
     - Tài liệu dài vừa phải (nhiều trang).
     - Trường hợp document chưa parse/xảy ra lỗi parse.
   - Điều chỉnh độ dài segments (chunk size) để cân bằng giữa:
     - Dễ đọc.
     - Dễ mapping citations (mỗi citation dẫn tới một đoạn đủ ngắn để người dùng thấy rõ).

---

## 7. Ghi chú & Giả định (Notes & Assumptions)

- **Giả định kỹ thuật**
  - Phase 2/3 đã hoạt động ổn: `docai_full_text` luôn có dữ liệu cho document `status='parsed'` hoặc `status='ingested'`.
  - RAG-Anything + LightRAG đã được cấu hình dùng Supabase PGVector (theo Phase 3 thiết kế).
  - LLM (OpenAI hoặc tương đương) có thể trả JSON tương đối ổn định khi được prompt đúng (vẫn phải có fallback khi JSON invalid).

- **Về độ chính xác citations**
  - Phase 7 v1 sử dụng chiến lược **server-side text matching**:
    - LLM chỉ sinh `sections[*].text`.
    - Backend dùng text của section để tìm lại segment phù hợp nhất trong các document của workspace (dựa trên so khớp chuỗi).
  - Mức độ chính xác được kỳ vọng ở **cấp segment** (đoạn/bước), không phải từng câu 100% chính xác – tương tự các hệ thống RAG explainable phổ biến.
  - Có thể bổ sung chiến lược align bằng embedding (post-hoc) ở Phase sau nếu cần tăng độ chính xác hơn nữa.

- **Về hiệu năng**
  - Viewer trả full text thô một lần; Phase 7 không yêu cầu pagination, nhưng chunking thành segments phải đủ nhẹ để client render được.
  - Prompt RAG sẽ dài hơn (do thêm id + context), nhưng không được vượt quá giới hạn token của model sử dụng.

- **Open questions cho design**
  - Chi tiết format `segment_id`: dùng `"{document_id}:{segment_index}"` hay chỉ giữ pair `{document_id, segment_index}`.
  - Cách hiển thị nhiều citations trên một section (một bong bóng cho cả danh sách hay nhiều bong bóng?).
  - Có cần endpoint “preview” snippet riêng không, hay snippet luôn là `text` của segment (cắt ngắn phía client).
