# rag-engine – Tech Design (Phase 10 – Non-OCR Direct Text/JSON Ingest)

**Mục tiêu**: Thiết kế chi tiết cho việc hỗ trợ tài liệu non-OCR (text/JSON) đi qua pipeline hiện có mà **bỏ qua Document AI**, nhưng vẫn tận dụng chung `parse_jobs` + `docai_full_text` + ingest vào RAG.

---

## 1. Tech Stack & Quyết định chính

- **Backend**: Python + FastAPI (async) – giữ nguyên.
- **Database**: Supabase Postgres, SQLAlchemy Core async – giữ nguyên schema, chỉ dùng thêm giá trị mới cho `parse_jobs.parser_type`.
- **External Services**:
  - Cloudflare R2 – vẫn là nơi lưu file gốc.
  - Google Cloud Document AI – chỉ được gọi cho `parser_type='gcp_docai'`.
- **Quyết định chính**:
  - Thêm parser type mới: `raw_text` (tên final trong constants).
  - Chọn parser type ngay lúc upload dựa trên `mime_type` + extension.
  - Trong `ParserPipelineService`, branch logic theo parser type, không tạo worker/job mới.

---

## 2. Cấu trúc Folder & Module (Source Code)

Không thay đổi layout tổng, chỉ chỉnh/extend module hiện có:

```text
server/app/
  api/
    routes/
      documents.py        # thêm logic chọn parser_type khi upload
  core/
    constants.py          # thêm PARSER_TYPE_RAW_TEXT
  db/
    repositories.py       # (tuỳ chọn) cho phép set parser_type khi tạo parse_job
  services/
    parser_pipeline.py    # branch xử lý gcp_docai vs raw_text
    storage_r2.py         # đã có download_file
```

---

## 3. Configuration & Environment

### 3.1. Biến môi trường (Env Vars)

Phase 10 không bắt buộc env mới, nhưng có thể cân nhắc sau:

- (Optional) `NON_OCR_MIME_TYPES`: danh sách mime text/JSON được coi là raw_text; trước mắt hard-code trong code để đơn giản.

### 3.2. Config Loader

- Không thay đổi `get_settings` hoặc cấu trúc config; logic phân loại file nằm trong route/service.

---

## 4. Database Layer Design

### 4.1. Models (Schema Mapping)

- `parse_jobs.parser_type`:
  - Hiện tại default `'gcp_docai'`.
  - Phase 10 thêm giá trị hợp lệ thứ hai: `'raw_text'`.

### 4.2. Repositories / Data Access

- `create_parse_job(session, document_id)` hiện tại:
  - Set `parser_type=PARSER_TYPE_GCP_DOCAI`.
- Phase 10 – option thiết kế:
  - **Option A (đề xuất)**: thêm hàm overload mới:

    ```python
    async def create_parse_job(
        session: AsyncSession,
        document_id: str,
        parser_type: str | None = None,
    ) -> Mapping[str, Any]:
        parser_type = parser_type or PARSER_TYPE_GCP_DOCAI
        ...
    ```

    - Các call-site cũ không truyền `parser_type` → behavior giữ nguyên.
    - Route upload có thể truyền `parser_type='raw_text'` khi cần.

  - **Option B**: giữ hàm cũ, thêm hàm mới `create_parse_job_with_parser_type`. Đơn giản hơn về type hint, nhưng thừa. Ưu tiên Option A để tránh duplicate.

---

## 5. Service Layer & External Integrations

### 5.1. Parser Type Constant

- Trong `server/app/core/constants.py`:

  ```python
  PARSER_TYPE_GCP_DOCAI = "gcp_docai"
  PARSER_TYPE_RAW_TEXT = "raw_text"  # Phase 10
  ```

### 5.2. Upload Flow – chọn parser_type

- File: `server/app/api/routes/documents.py`
- Mở rộng logic trong `upload_documents`:

  ```python
  from server.app.core.constants import PARSER_TYPE_GCP_DOCAI, PARSER_TYPE_RAW_TEXT

  def _detect_parser_type(original_filename: str, mime_type: str | None) -> str:
      # pseudo-code
      ext = Path(original_filename).suffix.lower()
      mt = (mime_type or "").lower()

      TEXT_EXTS = {".txt", ".md", ".markdown", ".json", ".csv", ".tsv"}
      TEXT_MIMES = {
          "text/plain",
          "text/markdown",
          "application/json",
          "text/csv",
          "text/tab-separated-values",
      }

      if ext in TEXT_EXTS or mt in TEXT_MIMES:
          return PARSER_TYPE_RAW_TEXT
      return PARSER_TYPE_GCP_DOCAI
  ```

- Trong vòng lặp upload:

  ```python
  parser_type = _detect_parser_type(original_filename, upload.content_type)
  parse_job = await repo.create_parse_job(
      session=session,
      document_id=doc_row["id"],
      parser_type=parser_type,
  )
  ```

- Các field khác (documents, files, realtime events) giữ nguyên.

### 5.3. ParserPipelineService – branch xử lý

- File: `server/app/services/parser_pipeline.py`
- Hiện tại đã có:
  - Lấy job → `parser_type = (job.get("parser_type") or "").strip()`.
  - Gọi Document AI, dùng builder layout-aware, lưu `docai_full_text`, `docai_raw_r2_key`.
- Phase 10 bổ sung:

  ```python
  from server.app.core.constants import PARSER_TYPE_GCP_DOCAI, PARSER_TYPE_RAW_TEXT
  from server.app.services.storage_r2 import download_file

  ...
  parser_type = (job.get("parser_type") or "").strip() or PARSER_TYPE_GCP_DOCAI
  ...
  # Sau khi load file metadata:
  r2_key = file_row["r2_key"]
  mime_type = file_row["mime_type"]
  file_bytes = await storage_r2.download_file(r2_key)

  if parser_type == PARSER_TYPE_RAW_TEXT:
      # Raw-text branch: không gọi Document AI
      full_text = _decode_raw_text(file_bytes, mime_type, original_filename)
      raw_key = None  # hoặc "" – sẽ quyết định phần repo update bên dưới
  else:
      # GCP DocAI branch (giữ nguyên behavior hiện tại)
      doc = await self._docai_client.process_document_ocr(
          file_bytes=file_bytes,
          mime_type=mime_type,
      )
      full_text = build_full_text_from_ocr_result(parser_type=parser_type, doc=doc)
      if not full_text:
          raise RuntimeError("Document AI returned empty text")
      raw_key = f"docai-raw/{document_id}.json"
      await storage_r2.upload_json(doc, key=raw_key)

  if not full_text:
      raise RuntimeError("Parsed text is empty")

  # Update document + job success
  await repo.update_document_parsed_success(
      session=session,
      document_id=document_id,
      full_text=full_text,
      raw_r2_key=raw_key,
  )
  ```

#### 5.3.1. Hàm `_decode_raw_text(...)`

- Đề xuất helper private trong `parser_pipeline.py` (hoặc một module utils riêng nếu cần dùng lại):

  ```python
  def _decode_raw_text(file_bytes: bytes, mime_type: str, original_filename: str) -> str:
      # v1: luôn decode UTF-8, bỏ BOM, ignore errors
      text = file_bytes.decode("utf-8", errors="ignore")
      return text.strip()
  ```

- Ghi chú:
  - Với JSON:
    - Ta **không parse rồi pretty-print** để tránh thay đổi nội dung; để nguyên string as-is (chỉ strip).
  - Nếu cần tinh chỉnh thêm cho CSV/TSV (ví dụ normalize `\r\n`) có thể thêm ở đây, nhưng Phase 10 không bắt buộc.

### 5.4. Repository Update – raw_key nullable

- `update_document_parsed_success(session, document_id, full_text, raw_r2_key)`:
  - Hiện tại gán `docai_raw_r2_key=raw_r2_key` và set status `'parsed'`.
- Phase 10:
  - Cho phép `raw_r2_key` là `None` (hoặc `""`) mà không lỗi.
  - Behavior đề xuất:
    - `gcp_docai`: `raw_r2_key = 'docai-raw/{document_id}.json'` như cũ.
    - `raw_text`: `raw_r2_key = None` → cột `docai_raw_r2_key` có thể `NULL`.

Không cần function mới, chỉ cần đảm bảo call-site truyền `None`/`""` và DB chấp nhận (schema đã `nullable=True`).

---

## 6. API Design & Routes

### 6.1. Documents – Upload

- Endpoint: `POST /api/workspaces/{workspace_id}/documents/upload`
- Thay đổi duy nhất:
  - Logic server side:
    - Gọi `_detect_parser_type(...)`.
    - Truyền `parser_type` vào `create_parse_job`.
  - Response shape không đổi (`UploadResponse`).

### 6.2. Các route khác

- Không có thay đổi về contract:
  - `/documents` listing – chỉ cần đảm bảo status vẫn đúng (pending → parsed → ingested).
  - `/raw-text` – vẫn đọc `docai_full_text`.
  - Chat + websocket – vẫn dùng metadata hiện tại.

---

## 7. Background Workers / Jobs

- **Parse worker**:
  - Không thay đổi cách trigger; chỉ đổi logic xử lý job theo `parser_type`.
  - Logging nên bổ sung:

    ```python
    self._logger.info(
        "parse_job processed successfully",
        extra={"job_id": job_id, "document_id": document_id, "parser_type": parser_type},
    )
    ```

- **Ingest worker**:
  - Không cần chỉnh; vẫn ingest khi `status='parsed'` và `docai_full_text` không rỗng.

---

## 8. Security & Authentication

- Không thay đổi so với các phase trước:
  - Upload vẫn kiểm tra `workspace` thuộc về current user.
  - Parse/ingest workers chạy background, không expose endpoint mới.

---

## 9. Logging & Monitoring

- Bổ sung một vài log để dễ debug:
  - Ở upload route:

    ```python
    logger.info(
        "Created parse_job for document with parser_type",
        extra={"document_id": doc_row["id"], "parser_type": parser_type},
    )
    ```

  - Ở parser pipeline:
    - Log parser_type khi bắt đầu xử lý job.
    - Phân biệt error từ DocAI vs error decode raw text.

---

## 10. Kế hoạch Implement & Testing

- **Step-by-step**:
  1. Thêm `PARSER_TYPE_RAW_TEXT` trong constants.
  2. Mở rộng repository `create_parse_job` để nhận `parser_type`.
  3. Implement `_detect_parser_type` trong upload route và truyền parser_type khi tạo job.
  4. Branch logic trong `ParserPipelineService` cho `raw_text` vs `gcp_docai`, thêm `_decode_raw_text`.
  5. Đảm bảo `update_document_parsed_success` chấp nhận `raw_r2_key=None`.
  6. Test manual:
     - Upload `.txt` / `.json` → Document đi `pending → parsed` không call DocAI.
     - Upload PDF → behavior y như cũ.
     - Ingest và chat thử trên cả hai loại.

- **Testing strategy**:
  - Unit test (nếu hạ tầng cho phép) cho `_detect_parser_type` và `_decode_raw_text`.
  - Integration test manual với worker parse/ingest.

---

## 11. Ghi chú & Kết luận

- Phase 10 giúp pipeline linh hoạt hơn:
  - Giữ nguyên kiến trúc parse_jobs → documents → ingest.
  - Thêm khả năng xử lý tài liệu non-OCR mà không chạm vào Document AI.
- Semantics của `docai_full_text` được mở rộng:
  - Từ “full text từ Document AI” → “full text đã parse từ document” (có thể từ Document AI hoặc raw text).
- Nếu sau này cần thêm provider OCR khác hoặc parser đặc thù cho JSON/CSV, có thể reuse cùng pattern:
  - Thêm `parser_type` mới.
  - Thêm branch tương ứng trong `ParserPipelineService`. 

