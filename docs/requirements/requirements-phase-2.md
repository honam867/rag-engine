# rag-engine-phase-2 – Document AI & Parser Pipeline (OCR only)

## 1. Mục tiêu Phase 2

- Tích hợp **Google Cloud Document AI – Enterprise Document OCR** làm parser chính.
- Thiết kế & triển khai **parser pipeline** xử lý `parse_jobs` ở background (worker):
  - Lấy file từ Cloudflare R2.
  - Gọi Document AI (sử dụng cả OCR + layout cơ bản như pages/tables/paragraphs).
  - Lưu lại:
    - `docai_full_text` (full text đã OCR, được rebuild lại dựa trên layout để giữ cấu trúc bảng/đoạn ở mức cơ bản) trong DB.
    - `docai_raw_r2_key` (key tới JSON raw của Document AI trên R2).
- Định nghĩa rõ **interface parser** để Phase 3 có thể dùng output này build `content_list` và ingest vào RAG Engine.

> Ghi chú: Phase 2 **chưa** gọi RAG Engine. RAG Engine sẽ được tích hợp ở Phase 3, sử dụng dữ liệu đã parse từ Phase 2.

---

## 2. Dịch vụ parser: Google Cloud Document AI (OCR + layout cơ bản)

- Sử dụng **Google Cloud Document AI – Enterprise Document OCR Processor**:
  - Tập trung vào việc **nhận dạng text** chính xác từ PDF/ảnh.
  - Tận dụng thông tin layout có sẵn (pages, tables, paragraphs, `text_anchor`) để build lại `docai_full_text` theo đúng thứ tự đọc và giữ cấu trúc bảng ở mức text (cột được phân tách bằng separator).
- Đầu vào:
  - File tài liệu (PDF/ảnh) đã được upload lên Cloudflare R2 ở Phase 1.
- Đầu ra (từ Document AI):
  - `Document.text`: full text của tài liệu sau OCR.
  - Cấu trúc (pages, tables, paragraphs, tokens, …).
    - Phase 2 **đã** dùng thông tin này để rebuild `docai_full_text` có layout tốt hơn (đặc biệt với bảng).
    - Phase sau vẫn có thể tận dụng sâu hơn nếu cần (ví dụ table schema, form fields).

Trong kiến trúc, ta coi Document AI như **một service bên ngoài**:

- Backend/worker chỉ tương tác qua một lớp client nội bộ (vd `docai_client`), không gọi API trực tiếp rải rác.

---

## 3. Bổ sung schema & lưu trữ kết quả parse

### 3.1. Thay đổi ở bảng `documents`

Thêm 2 cột:

- `docai_full_text` (TEXT, nullable):
  - Lưu **full text** đã được build từ kết quả OCR:
    - Với `parser_type = 'gcp_docai'`: dùng layout (tables/paragraphs) để rebuild text giữ cấu trúc ở mức cơ bản.
    - Với parser khác (nếu chưa có builder riêng): fallback từ `Document.text`.
  - Dùng cho:
    - Re‑chunk, re‑ingest vào RAG mà không phải gọi lại Document AI.
    - Debug, export nội dung text.

- `docai_raw_r2_key` (TEXT, nullable):
  - Lưu key của file JSON raw Document AI trên Cloudflare R2.
  - Dùng cho:
    - Debug khi cần xem đầy đủ cấu trúc Document AI.
    - Mở rộng future (phân tích layout sâu hơn, table, v.v.).

### 3.2. Lưu JSON raw lên R2

- Khi worker nhận được response Document AI (kiểu `Document`):
  - Serialize toàn bộ response sang JSON.
  - Upload file JSON này lên R2 với key gợi ý:
    - `docai-raw/{document_id}.json`
  - Ghi key đó vào `documents.docai_raw_r2_key`.

Việc “JSON vào R2” nghĩa là:

- R2 đóng vai trò **object storage**:
  - Tương tự S3, dùng để lưu file nhị phân/text lớn (PDF, JSON, …).
- Trong DB, ta chỉ lưu **key** (chuỗi) để có thể tải lại file JSON khi cần.

---

## 4. Lớp R2 storage – tách riêng

Các thao tác với Cloudflare R2 nên được gom vào **một lớp riêng**, ví dụ:

- Module `storage_r2` với các hàm kiểu:
  - `upload_file(bytes, key) -> None`
  - `download_file(key) -> bytes`
  - `upload_json(obj, key) -> None`
  - `download_json(key) -> dict`

Ý tưởng:

- Tất cả logic liên quan tới R2 (endpoint, access key, bucket, path key, retry, …) chỉ nằm trong lớp này.
- Các phần khác (upload endpoint, worker parser, …) **không biết chi tiết R2**, chỉ gọi hàm:
  - `storage_r2.upload_file(...)`
  - `storage_r2.download_file(...)`
  - `storage_r2.upload_json(...)`
- Nhờ đó:
  - Nếu sau này đổi sang S3 / GCS / local storage, chỉ cần sửa lớp `storage_r2`, không phải sửa toàn hệ thống.

Trả lời câu hỏi của bạn:  
> Những gì liên quan tới R2, thì nó là 1 lớp riêng để gọi đến đúng không, là chỉ xử lý những gì liên quan đến R2?

- Đúng: **mọi thứ liên quan tới R2 nên gom vào một “storage layer” riêng**.
  - Parser pipeline chỉ biết “tải file lên/xuống” thông qua storage layer.
  - Không trộn lẫn logic call R2 vào logic parser/RAG.

---

## 5. Lớp Document AI client – tách riêng

Tương tự R2, các call tới Document AI nên qua một lớp client riêng, ví dụ `docai_client`:

- Các hàm chính (Phase 2):
  - `process_document_ocr(file_bytes) -> Document`
    - Bên trong:
      - Gọi Google Cloud Document AI Enterprise OCR.
      - Trả về object `Document` (hoặc dict JSON).

Parser pipeline sẽ chỉ làm việc với interface này, không dính chi tiết HTTP/credential của GCP.

Lợi ích:

- Nếu sau này muốn:
  - Đổi sang Layout Parser.
  - Thêm loại processor khác (invoice, form, …).
- Ta mở rộng `docai_client` mà không phải đổi parse_jobs/worker nhiều.

---

## 6. Luồng xử lý parse_jobs (mức khái niệm)

### 6.1. Trạng thái parse_jobs

- `queued` → job mới tạo sau upload file (Phase 1 đã tạo).
- `running` → worker đang xử lý.
- `success` → đã parse xong, đã lưu `docai_full_text` và `docai_raw_r2_key`.
- `failed` → parse lỗi, có `error_message`.

### 6.2. Worker / background process

Worker (có thể là một process độc lập hoặc một task loop trong backend) sẽ:

1. Định kỳ lấy một số job `status='queued'` từ `parse_jobs`.
2. Đặt `status='running'`, `started_at=now()`.
3. Với mỗi job:
   - Lấy `document_id` → load `files.r2_key` tương ứng.
   - Gọi `storage_r2.download_file(r2_key)` để lấy file bytes.
   - Gọi `docai_client.process_document_ocr(file_bytes)` để nhận `Document` (dict).
   - Từ `Document`:
     - Gọi helper layout-aware, ví dụ:

       ```python
       full_text = build_full_text_from_ocr_result(parser_type=job.parser_type, doc=result)
       ```

       - Với `parser_type = 'gcp_docai'`:
         - Dùng thông tin layout của Google Document AI (`pages.tables`, `paragraphs`, `text_anchor`) để rebuild text theo thứ tự đọc, giữ cấu trúc bảng bằng cách nối từng cell bằng separator (ví dụ `" | "`).
       - Với parser khác (chưa cấu hình riêng) → fallback: dùng `result["text"]`.

     - Ghi `full_text` vào `documents.docai_full_text`.
     - Serialize `Document` → JSON → `storage_r2.upload_json(json, key='docai-raw/{document_id}.json')`.
     - Ghi `documents.docai_raw_r2_key = 'docai-raw/{document_id}.json'`.
   - Cập nhật:
     - `parse_jobs.status = 'success'`, `finished_at = now()`.
     - `documents.status = 'parsed'` (chưa `ingested` vì RAG để Phase 3).
4. Nếu lỗi:
   - Ghi `parse_jobs.status = 'failed'`, `error_message`, `finished_at`.

### 6.3. Giao diện API quan sát trạng thái

- Bổ sung endpoint (Phase 2):
  - `GET /workspaces/{workspace_id}/documents/{document_id}`
    - Trả về trạng thái `documents.status` + `parse_jobs.status` mới nhất.
  - (Option) `GET /workspaces/{workspace_id}/parse-jobs` để xem danh sách job & trạng thái.

---

## 7. Interface parser cho Phase 3

Phase 2 cần định nghĩa **interface parser** mà Phase 3 sẽ dùng để tạo `content_list`:

Ở mức khái niệm:

```python
def build_content_list_from_document(document_id: str) -> list[dict]:
    """
    - Đọc documents.docai_full_text (và nếu cần, docai_raw_r2_key).
    - Cắt text theo trang/độ dài để tạo content_list phù hợp RAG Engine.
    - RETURN: content_list chuẩn (type, page_idx, content, metadata...).
    """
```

- Phase 2:
  - Chỉ cần thiết kế interface và phác logic chunk ở mức high‑level (văn bản).
  - Chưa cần implement chi tiết, vì ingest vào RAG Engine thuộc Phase 3.
- Phase 3:
  - Sẽ dùng hàm này để:
    - Lấy `content_list` → gọi `RAG Engine.ingest_content(...)`.

---

## 8. Kết quả & độ sẵn sàng sau Phase 2

Sau Phase 2, hệ thống đạt được:

- Upload file (Phase 1) → tạo parse_job.
- Worker Phase 2:
  - Tự động lấy file từ R2.
  - Gọi Google Cloud Document AI (OCR) để parse.
  - Lưu:
    - `docai_full_text` trong `documents`.
    - `docai_raw_r2_key` trỏ tới JSON đầy đủ trên R2.
  - Cập nhật trạng thái `documents.status = 'parsed'`.
- API có thể cho phép bạn:
  - Xem trạng thái parse của từng document.
  - Đảm bảo dữ liệu đã ở dạng “đã OCR xong, sẵn sàng để ingest vào RAG Engine”.

Phase 2 như vậy là một **bước đệm rõ ràng giữa “file gốc” và “dữ liệu sẵn sàng cho RAG”**, giúp Phase 3 (RAG Engine integration) tập trung vào:

- Thiết kế chiến lược chunking → `content_list`.
- Gắn với RAG‑Anything (hoặc engine khác) mà không phải lo parser/OCR nữa.
