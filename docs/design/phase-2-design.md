# Phase 2 – Tech Design (Document AI & Parser Pipeline)

Mục tiêu: chuyển đặc tả Phase 2 trong `../requirements/requirements-phase-2.md` thành thiết kế kỹ thuật cụ thể, bám theo kiến trúc trong `architecture-overview.md` và align với cách RAG‑Anything hoạt động (sẽ dùng ở Phase 3 qua `insert_content_list`).

---

## 1. Phạm vi & nguyên tắc

- Phase 2 chỉ xử lý **OCR + lưu kết quả parse**:
  - Lấy file đã upload lên Cloudflare R2 (Phase 1).
  - Gọi **Google Cloud Document AI – Enterprise Document OCR**.
  - Lưu:
    - `documents.docai_full_text` (TEXT).
    - JSON raw Document AI → Cloudflare R2, key lưu trong `documents.docai_raw_r2_key`.
  - Cập nhật `parse_jobs.status` và `documents.status` (`pending` → `parsed` / `failed`).
- **Chưa** gọi RAG‑Anything, chưa build `content_list`, chưa ingest.
  - Phase 3 sẽ đọc `docai_full_text` + JSON raw để tạo `content_list` và gọi `insert_content_list`.
- Worker Phase 2 là **process riêng**, không phụ thuộc vào vòng đời FastAPI:
  - Ví dụ chạy: `python -m app.workers.parse_worker`.
  - Khi API server restart/refresh, worker vẫn tiếp tục xử lý job trong DB.

Nguyên tắc quan trọng:

- Document AI & R2 được bọc trong lớp service (`docai_client`, `storage_r2`), API/worker không gọi SDK trực tiếp.
- DB (Supabase Postgres) vẫn là source of truth cho trạng thái document & parse_jobs.
- Thiết kế Phase 2 phải để **Phase 3 có thể build được `content_list` có `page_idx`** (file A – trang 5) dựa trên JSON raw.

---

## 2. Config & môi trường cho Document AI

### 2.1. Env variables mới (core/config.py)

Bổ sung nhóm config cho Google Cloud Document AI:

- `GCP_PROJECT_ID`
- `GCP_LOCATION` (vd: `us`, `eu`)
- `DOCAI_OCR_PROCESSOR_ID` (ID của Enterprise Document OCR Processor)
- `GCP_CREDENTIALS_PATH` (path tới file service account JSON, hoặc dùng ADC mặc định)

Trong `core/config.py`:

- Thêm `DocumentAISettings`:
  - `project_id: str`
  - `location: str`
  - `ocr_processor_id: str`
  - `credentials_path: Optional[str]`
- Inject `DocumentAISettings` vào `Settings` chung, giống cách đã làm cho DB & R2.

### 2.2. Thư viện

- Dùng SDK chính thức của Google:
  - `google-cloud-documentai` (ở mức design, chỉ cần nêu lib; cài đặt cụ thể để sau).
- Client sẽ được khởi tạo trong `services/docai_client.py`, sử dụng:
  - `project_id`, `location`, `processor_id`, `credentials_path` từ config.

---

## 3. Lớp storage R2 – mở rộng cho Phase 2

Phase 1 đã có `upload_file(...)`. Phase 2 cần thêm:

- `download_file(key: str) -> bytes`
  - Dùng `get_object` từ client S3‑compatible (Cloudflare R2).
  - Trả về raw bytes (PDF/ảnh).
- `upload_json(obj: dict, key: str) -> None`
  - Serialize `obj` → JSON bytes UTF‑8, `ContentType="application/json"`.
- `download_json(key: str) -> dict`
  - Tải object từ R2, parse JSON → `dict` (chủ yếu cho debug/dev; Phase 3 sẽ đọc JSON từ đây nếu cần).

Key conventions Phase 2:

- File gốc: đã có từ Phase 1, ví dụ `workspace/{workspace_id}/documents/{document_id}/{file_id}.pdf`.
- JSON raw Document AI:
  - `docai-raw/{document_id}.json`
  - Chuỗi key này sẽ được lưu vào `documents.docai_raw_r2_key`.

Tất cả code liên quan R2 vẫn chỉ nằm trong `services/storage_r2.py`; worker/parser không đụng trực tiếp SDK.

---

## 4. Lớp Document AI client (`services/docai_client.py`)

### 4.1. Interface

Định nghĩa lớp `DocumentAIClient` với interface tối giản, phù hợp Phase 2:

```python
class DocumentAIClient:
    def __init__(self, settings: DocumentAISettings): ...

    async def process_document_ocr(self, file_bytes: bytes, mime_type: str) -> dict:
        """
        Gọi Enterprise Document OCR cho 1 file.
        Trả về JSON (dict) của Document AI response (Document).
        """
```

- Ở mức thiết kế, `process_document_ocr`:
  - Khởi tạo client Document AI (sync hoặc async, nhưng interface cho phần còn lại là async để match FastAPI).
  - Build request `ProcessRequest` với:
    - `name = f"projects/{project_id}/locations/{location}/processors/{processor_id}"`.
    - Tập tin trong `raw_document` (`content=file_bytes`, `mime_type`).
  - Nhận response `Document` → convert về `dict` (vd `document.to_dict()`).

### 4.2. Kết quả dùng cho Phase 2/3

- Phase 2 chỉ cần:
  - `full_text = document["text"]` (hoặc field tương ứng).
  - Toàn bộ `dict` → upload JSON raw lên R2.
- Phase 3 sẽ:
  - Đọc lại JSON raw (qua `storage_r2.download_json`) và `docai_full_text` để build `content_list` có `page_idx`.

---

## 5. Parser pipeline (`services/parser_pipeline.py`)

### 5.1. Trách nhiệm

- Là lớp service “orchestrator” cho Phase 2:
  - Lấy job từ `parse_jobs` (DB).
  - Lấy `file`/`document` tương ứng.
  - Download file từ R2 (`storage_r2.download_file`).
  - Gọi `DocumentAIClient.process_document_ocr`.
  - Lưu kết quả vào `documents` + JSON raw lên R2.
  - Cập nhật trạng thái `parse_jobs` + `documents.status`.

### 5.2. Interface đề xuất

```python
class ParserPipelineService:
    def __init__(
        self,
        db_session_factory,
        storage_r2: StorageR2,
        docai_client: DocumentAIClient,
    ): ...

    async def process_single_job(self, job_id: str) -> None: ...

    async def fetch_and_process_next_jobs(self, batch_size: int = 1) -> int:
        """
        Lấy một batch parse_jobs ở trạng thái 'queued', xử lý lần lượt.
        Trả về số job đã xử lý (success + failed).
        """
```

Chi tiết logic `process_single_job(job_id)`:

1. **Load job & document**:
   - Từ `parse_jobs` lấy job, kiểm tra:
     - `status == 'queued'` (tránh chạy lại job cũ).
   - Từ `document_id` trong job → lấy `documents` và `files` tương ứng:
     - Dùng `repositories.py` (DocumentRepository, FileRepository) để truy DB.
2. **Đánh dấu job đang chạy**:
   - `parse_jobs.status = 'running'`, `started_at = now()`.
3. **Download file từ R2**:
   - Dùng `file.r2_key` → `storage_r2.download_file` → `file_bytes`.
   - Sử dụng `file.mime_type` hoặc suy ra từ filename (backup).
4. **Gọi Document AI**:
   - `result = await docai_client.process_document_ocr(file_bytes, mime_type)`.
   - `full_text = result["text"]` (hoặc tương đương) – xử lý trường hợp không có text → coi là lỗi.
5. **Lưu kết quả**:
   - `documents.docai_full_text = full_text`.
   - Tạo key JSON raw: `key = f"docai-raw/{document_id}.json"`.
   - `storage_r2.upload_json(result, key)`.
   - `documents.docai_raw_r2_key = key`.
   - `documents.status = 'parsed'`.
6. **Hoàn tất job**:
   - `parse_jobs.status = 'success'`.
   - `parse_jobs.finished_at = now()`.
7. **Error handling**:
   - Nếu bất kỳ bước nào ném exception:
     - Ghi log lỗi chi tiết.
     - `parse_jobs.status = 'failed'`, `error_message = str(e)[:N]`, `finished_at = now()`.
     - `documents.status` có thể:
       - Giữ `pending` hoặc set `'error'`/`'parse_failed'` (tuỳ enum cụ thể trong planning; nếu chưa có, Phase 2 có thể đề xuất thêm trạng thái lỗi rõ ràng).

### 5.3. Fetch batch jobs

`fetch_and_process_next_jobs(batch_size: int)`:

- Mở một DB session, chọn N job:

  - `status = 'queued'`,
  - `ORDER BY created_at ASC`,
  - `LIMIT batch_size`.

- Với mỗi job:
  - Gọi `process_single_job(job.id)` (có thể chạy tuần tự hoặc dùng semaphore để concurrency nhẹ).

Worker sẽ gọi hàm này trong vòng lặp (xem phần 6).

---

## 6. Worker parse_jobs (`workers/parse_worker.py`)

### 6.1. Kiểu chạy

- Worker là **process riêng**, ví dụ file `server/app/workers/parse_worker.py` có entrypoint:

```python
async def run_worker_loop():
    """
    Vòng lặp vô hạn/long-running:
    - Mỗi chu kỳ: fetch batch job, xử lý, sleep một chút.
    """

if __name__ == "__main__":
    asyncio.run(run_worker_loop())
```

- Chạy bằng: `python -m app.workers.parse_worker` hoặc tương đương.

### 6.2. Vòng lặp worker

Pseudo-flow:

```python
async def run_worker_loop():
    settings = get_settings()
    pipeline = ParserPipelineService(...)

    while True:
        processed = await pipeline.fetch_and_process_next_jobs(batch_size=1)
        if processed == 0:
            await asyncio.sleep(SLEEP_SECONDS_IDLE)
        else:
            # Có job, xử lý liên tục, có thể sleep ngắn hơn
            await asyncio.sleep(SLEEP_SECONDS_BUSY)
```

Các tham số:

- `SLEEP_SECONDS_IDLE`: ví dụ 5–10s khi không có job.
- `SLEEP_SECONDS_BUSY`: ví dụ 0.5–1s để tránh spam DB.
- Có thể thêm env `PARSE_WORKER_BATCH_SIZE`, `PARSE_WORKER_IDLE_SLEEP`, … vào config nếu cần.

### 6.3. Restart & an toàn

- Vì trạng thái job nằm trong DB:
  - Nếu worker crash hoặc server restart:
    - Job `queued` vẫn còn, sẽ được xử lý ở vòng lặp tiếp theo khi worker chạy lại.
    - Job `running` bị kẹt có thể:
      - Phase 2 v1: để nguyên (chấp nhận một số job hiếm khi bị kẹt).  
      - Phase sau: thêm logic “job timeout”:
        - Job `running` quá X phút → chuyển sang `failed` hoặc `queued` lại.

---

## 7. API & quan sát trạng thái parse

Phase 2 không tạo API mới phức tạp, nhưng cần **expose trạng thái parse** rõ ràng cho UI/dev.

### 7.1. Documents endpoint – bổ sung trạng thái parse

Trong `api/routes/documents.py`:

- `GET /workspaces/{workspace_id}/documents`
  - Mở rộng response để trả:
    - `status` của document (`pending`, `parsed`, `ingested` (sau), `parse_failed` nếu thêm).
    - Thời gian tạo/cập nhật.
- `GET /workspaces/{workspace_id}/documents/{document_id}`
  - Trả chi tiết:
    - Thông tin document (title, status, created_at, updated_at).
    - Thông tin parse_job gần nhất cho document đó (join hoặc query từ `parse_jobs`):
      - `status`, `error_message`, `started_at`, `finished_at`.

### 7.2. (Optional) Parse jobs endpoint

- (Tuỳ mức cần thiết ở v1) có thể thêm:
  - `GET /workspaces/{workspace_id}/parse-jobs`
    - Trả list job cho workspace đó (id, document_id, status, timestamps).
  - `POST /documents/{document_id}/parse/retry`
    - Tạo `parse_job` mới với `status='queued'` cho document đó (khi job cũ `failed`).

Việc “retry parse” không phụ thuộc cache của RAG‑Anything; chỉ cần tạo job mới, worker sẽ gọi lại Document AI và overwrite `docai_full_text` / JSON raw (document vẫn là cùng `document_id`).

---

## 8. Quan hệ với Phase 3 & RAG‑Anything

Phase 2 phải đảm bảo dữ liệu đủ để Phase 3 có thể tích hợp với RAG‑Anything qua `insert_content_list`:

- Mỗi document sau Phase 2 có:
  - `docai_full_text` (TEXT): dùng để chunk text → tạo `content_list` các block `"type": "text"`.
  - `docai_raw_r2_key` (JSON raw trên R2): dùng để, khi cần, xác định:
    - Số trang, page index của đoạn text (phục vụ mục tiêu “file A – trang 5”).  
    - Các cấu trúc khác (paragraph, table, …) nếu Phase sau muốn nâng cấp.
- Phase 3 sẽ:
  - Định nghĩa `chunker.build_content_list_from_document(document_id)`:
    - Đọc `docai_full_text` (+ JSON raw nếu cần).
    - Tạo `content_list` đúng schema RAG‑Anything (ít nhất `{"type": "text", "text": ..., "page_idx": ...}`).
  - Gọi `rag_engine.ingest_content(...)` → nội bộ dùng `rag.insert_content_list(...)`, truyền:
    - `doc_id` = giá trị do mình quyết (thường là `str(document_id)`).
    - `file_path` = chuỗi human‑readable, ví dụ `"{workspace_id}/{document_id}/{original_filename}"` để citations dễ hiểu và không trùng giữa workspaces.

Nhờ đó, Phase 2 không cần biết gì về RAG‑Anything, nhưng vẫn chuẩn bị đủ dữ liệu để Phase 3 xây dựng `content_list` có `page_idx` và enable citations “file A – trang 5”.

---

## 9. Tóm tắt mức sẵn sàng sau Phase 2 (tech)

Sau khi implement Phase 2 theo thiết kế này, hệ thống backend sẽ có:

- Worker `parse_worker` độc lập, đọc queue `parse_jobs` từ DB, tự động:
  - Download file từ R2.
  - Gọi Google Cloud Document AI (OCR).
  - Lưu `docai_full_text` + JSON raw (R2) + cập nhật status.
- API hiện có (workspaces, documents) được bổ sung đủ thông tin để UI giám sát trạng thái parse và xem lỗi nếu có.
- DB & storage giữ đầy đủ dữ liệu OCR để Phase 3 có thể:
  - Chunk text, build `content_list` chuẩn RAG‑Anything.
  - Ingest vào RAG‑Anything và tạo pipeline chat với citations chi tiết theo workspace.

Thiết kế này giữ nguyên kiến trúc tổng, không lock‑in vào MinerU/Docling của RAG‑Anything, và ưu tiên “source of truth” ở layer của bạn (DB + R2 + Document AI).
