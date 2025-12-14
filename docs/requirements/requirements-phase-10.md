# rag-engine-phase-10 – Non-OCR Documents (Direct Text/JSON Ingest) Spec v1

## 1. Mục tiêu & Phạm vi (Goals & Scope)

- **Mục tiêu chính**:
  - Hỗ trợ ingest các tài liệu đã là text sẵn (ví dụ: `.txt`, `.md`, `.json`, có thể mở rộng thêm CSV/TSV) mà **không cần đi qua Google Document AI**.
  - Tận dụng lại pipeline hiện có (documents → files → parse_jobs → ingest) nhưng thêm một nhánh parser “raw text” để:
    - Tiết kiệm chi phí và thời gian gọi OCR.
    - Tránh các lỗi layout/format không cần thiết đối với tài liệu thuần text/JSON.
- **Phạm vi công việc**:
  - Thêm định nghĩa “non-OCR document / raw-text parser” trong pipeline.
  - Chỉnh sửa nhẹ luồng upload + parse_jobs + ParserPipeline để:
    - Tự động xác định file nào có thể xử lý như raw text.
    - Với những file này, bỏ qua Document AI, decode trực tiếp nội dung file và ghi vào `documents.docai_full_text`.
  - Không thay đổi API HTTP (route, path) hoặc schema DB.
- **Out of scope**:
  - Không thiết kế thêm schema extraction từ JSON (map sang bảng/field riêng); Phase 10 chỉ coi JSON như text để RAG có thể đọc được.
  - Không thay đổi client/websocket payload (vẫn dùng các trường hiện tại).
  - Không tối ưu hiệu năng ingest đặc biệt cho JSON/CSV (chỉ ingest bằng text).
- **Kết quả kỳ vọng (Deliverables)**:
  - Requirement rõ ràng cho parser type mới (ví dụ: `raw_text`) và tiêu chí chọn file non-OCR.
  - Thiết kế kỹ thuật (Phase 10 design) mô tả chi tiết các điểm chỉnh sửa:
    - API upload → cách set `parser_type` phù hợp.
    - ParserPipelineService → branch xử lý `raw_text` vs `gcp_docai`.
    - Repository helper để cập nhật `documents.docai_full_text` mà không cần JSON raw.

---

## 2. Các khái niệm & thực thể chính (Key Concepts & Entities)

### 2.1. Non-OCR Document

- Mô tả:
  - Document mà file gốc đã ở dạng text “sạch” (không cần OCR), ví dụ:
    - `.txt`, `.md` (Markdown), `.json`, có thể mở rộng thêm `.csv`, `.tsv`.
  - Nội dung đã có cấu trúc logic (hoặc ít nhất là text) mà pipeline chỉ cần đọc trực tiếp để đưa vào `docai_full_text`.
- Vai trò trong hệ thống:
  - Cho phép user feed kiến thức từ nguồn text/JSON mà không tốn chi phí Document AI.
  - Hạn chế các lỗi layout sinh ra bởi OCR với tài liệu vốn dĩ là text.

### 2.2. Raw Text Parser Type (`parser_type = 'raw_text'` hoặc tương đương)

- Mô tả:
  - Một kiểu parser mới trong `parse_jobs.parser_type` dùng cho non-OCR documents.
  - Khi job có `parser_type` này:
    - Worker **không gọi Document AI**.
    - Worker tải file từ R2, decode nội dung file (UTF-8) và ghi thẳng vào `documents.docai_full_text`.
- Vai trò:
  - Giữ nguyên kiến trúc parse_jobs (không tạo worker/queue mới).
  - Cho phép pipeline Phase 2/3 tận dụng chung logic ingest (vì `docai_full_text` vẫn là source chính cho RAG).

### 2.3. OCR Document (`parser_type = 'gcp_docai'` – hiện tại)

- Mô tả:
  - Document cần OCR (PDF scan, ảnh, hoặc các file mà muốn tận dụng layout của Document AI).
  - Sử dụng nhánh hiện tại:
    - Gọi Document AI → builder layout-aware → `docai_full_text`.
    - Lưu JSON Document AI vào R2 (`docai_raw_r2_key`).
- Vai trò:
  - Giữ nguyên behavior Phase 2 đã có; Phase 10 **không thay đổi semantics** các file đã/đang dùng OCR.

---

## 3. Luồng nghiệp vụ (User/System Flows)

### 3.1. Upload tài liệu (mixed: PDF + text + JSON)

1. User chọn workspace và upload một hoặc nhiều file (PDF, text, JSON, …) qua `/workspaces/{workspace_id}/documents/upload`.
2. Backend lưu file lên R2 và tạo `documents` + `files` như hiện tại.
3. Với mỗi file:
   - Backend xác định **parser type** dựa trên `mime_type` và/hoặc extension:
     - Nếu `mime_type` thuộc nhóm text/JSON (ví dụ: `text/plain`, `application/json`, `text/markdown`, `text/csv`, `text/tab-separated-values`) **hoặc** extension nằm trong danh sách được hỗ trợ (`.txt`, `.md`, `.json`, `.csv`, `.tsv`):
       - Gán `parser_type = 'raw_text'`.
     - Ngược lại:
       - Gán `parser_type = 'gcp_docai'` (như hiện tại).
4. Backend tạo `parse_jobs` với `parser_type` tương ứng.
5. Realtime notifications không thay đổi (vẫn báo job `queued`).

### 3.2. Xử lý parse_jobs (Phase 2 mở rộng)

Worker Phase 2 (`ParserPipelineService`) đọc `parser_type` của từng job:

- Nếu `parser_type = 'gcp_docai'`:
  - Giữ nguyên behavior Phase 2 + update layout-aware hiện tại:
    - Tải file bytes từ R2.
    - Gọi Document AI.
    - Dùng builder `build_full_text_from_ocr_result` để tạo `full_text` (giữ layout).
    - Lưu `docai_full_text = full_text`.
    - Lưu JSON Document AI lên R2, ghi `docai_raw_r2_key`.
- Nếu `parser_type = 'raw_text'`:
  1. Tải file bytes từ R2.
  2. Decode bytes thành text:
     - Mặc định UTF-8, `errors="ignore"` hoặc `replace`.
     - Với `application/json`, có thể giữ nguyên string như file (không parse/pretty-print để tránh thay đổi nội dung).
  3. Ghi text này vào `documents.docai_full_text`.
  4. `docai_raw_r2_key`:
     - Có thể để `NULL` (không có JSON raw riêng) hoặc lưu lại file gốc JSON nếu muốn (decision sẽ ghi rõ ở tech design).
  5. Cập nhật:
     - `documents.status = 'parsed'`.
     - `parse_jobs.status = 'success'`.

### 3.3. Ingest vào RAG (Phase 3 – không đổi)

- Ingest worker (`IngestJobService`) không cần biết file thuộc loại nào:
  - Vẫn chỉ ingest document có `status='parsed'`.
  - Vẫn dùng `docai_full_text` làm source text:
    - Với OCR documents: `docai_full_text` = text từ Document AI.
    - Với raw text documents: `docai_full_text` = nội dung file text/JSON.
- `ChunkerService` vẫn đọc `docai_full_text` và build `content_list` một phần tử (full text) như hiện tại.

---

## 4. Kiến trúc & Thiết kế kỹ thuật (Architecture & Technical Design – High-level)

### 4.1. Backend / Service Layer

- Thêm một parser type mới:
  - `PARSER_TYPE_RAW_TEXT = "raw_text"` (tên sẽ được finalize ở Phase 10 design).
- Chỉnh sửa:
  - API upload (documents routes) để quyết định `parser_type` khi tạo `parse_jobs`.
  - `ParserPipelineService.process_single_job` để:
    - Branch xử lý theo `parser_type`.
    - Raw text branch bỏ qua Document AI, chỉ decode file bytes.
- Không thêm worker mới, không thay đổi event bus.

### 4.2. Database Schema (Supabase / Postgres)

- **Không thêm bảng mới**, không thay đổi schema hiện tại:
  - `documents`:
    - Vẫn dùng `docai_full_text` cho cả OCR và non-OCR documents.
    - `docai_raw_r2_key`:
      - Có thể để `NULL` với `parser_type='raw_text'` nếu không cần JSON raw riêng.
  - `parse_jobs`:
    - Đã có `parser_type` với default `'gcp_docai'`.
    - Phase 10 chỉ sử dụng thêm một giá trị mới cho field này.

### 4.3. External Services / Storage

- **Document AI**:
  - Không thay đổi cấu hình, chỉ bỏ qua khi `parser_type='raw_text'`.
- **Cloudflare R2**:
  - Vẫn lưu file gốc như Phase 1.
  - Với raw text documents:
    - Có thể không upload thêm JSON raw phụ (tùy quyết định ở design, để đơn giản nên không).

---

## 5. API Endpoints (Dự kiến)

Phase 10 **không thêm endpoint mới**, chỉ chỉnh behavior:

### 5.1. Documents – Upload

- `POST /api/workspaces/{workspace_id}/documents/upload`
  - Input: giữ nguyên (list `UploadFile`).
  - Behavior mới:
    - Khi tạo `parse_job`, xác định `parser_type` dựa trên `mime_type`/extension:
      - `raw_text` cho `.txt`, `.md`, `.json`, `.csv`, `.tsv` (có thể cấu hình).
      - `gcp_docai` cho phần còn lại (PDF, hình, DOCX, …).
  - Response: giữ nguyên (`UploadResponse`).

### 5.2. Các API khác

- `GET /documents`, `/raw-text`, chat endpoints, ingest worker… không cần thay đổi contract.

---

## 6. Kế hoạch triển khai (Implementation Plan)

1. **Bước 1 – Định nghĩa parser type mới**:
   - Thêm constant `PARSER_TYPE_RAW_TEXT` trong `server/app/core/constants.py`.
   - Cập nhật requirement & design (file hiện tại + `phase-10-design.md`).
2. **Bước 2 – Quyết định parser_type khi upload**:
   - Chỉnh `server/app/api/routes/documents.py`:
     - Sau khi đọc `UploadFile`, dựa vào `upload.content_type` và extension để chọn `parser_type`.
     - Truyền `parser_type` này khi gọi repository tạo parse_job (có thể cần overload hoặc thêm arg).
3. **Bước 3 – Branch xử lý trong ParserPipelineService**:
   - Chỉnh `server/app/services/parser_pipeline.py`:
     - Đọc `parser_type` từ job.
     - Nếu `gcp_docai` → giữ nguyên (gọi Document AI + builder layout-aware).
     - Nếu `raw_text` → tải file từ R2, decode bytes trực tiếp, ghi `docai_full_text`, set status `parsed`.
4. **Bước 4 – Repository & helpers**:
   - Nếu cần, thêm helper riêng để update `documents.docai_full_text` cho raw text (không cần `docai_raw_r2_key`).
5. **Bước 5 – Testing & sanity check**:
   - Test manual:
     - Upload `.txt` → document đi từ `pending` → `parsed` mà không có call DocAI.
     - Upload PDF → vẫn đi qua Document AI như cũ.
   - Đảm bảo ingest (Phase 3) hoạt động bình thường cho cả hai loại.

---

## 7. Ghi chú & Giả định (Notes & Assumptions)

- Giả định:
  - Môi trường lưu file (R2) và DB hiện có đủ để xử lý file text/JSON mà không cần mở rộng schema.
  - Các file text/JSON đều được encode UTF-8 (hoặc ít nhất decode được với chiến lược `errors="ignore"`).
- Quy ước:
  - Phase 10 không thay đổi tên trường `docai_full_text` để tránh đụng nhiều chỗ; về semantics, đây trở thành “full_text sau khi parse”, không chỉ riêng cho Document AI.
- Open questions:
  - Danh sách mime/extension cụ thể cho raw text sẽ là hard-code hay cấu hình qua env?
  - Với JSON, có cần pretty-print để dễ đọc trong raw viewer hay giữ nguyên string gốc (đề xuất: giữ nguyên để không bất ngờ về nội dung). 

