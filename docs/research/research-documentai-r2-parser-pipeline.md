# Research: Google Document AI + Cloudflare R2 parser pipeline

- Date: 2025-12-01
- Context: Phase 2 – implement Document AI OCR + parser pipeline worker for rag-engine backend (FastAPI + Supabase + Cloudflare R2).

## 1. Perplexity MCP prompt

> We have an async FastAPI backend with SQLAlchemy async and a separate worker process that will:
> - Read parse_jobs from Postgres (Supabase)
> - Download source files from Cloudflare R2 (S3-compatible)
> - Call Google Cloud Document AI Enterprise Document OCR on PDFs/images
> - Store full text (docai_full_text) in Postgres and upload full JSON response to R2
>
> We need best practices for:
> 1. Using boto3 with Cloudflare R2 safely from async code (FastAPI or worker): client setup, thread-safety, using run_in_threadpool vs blocking I/O, connection reuse, and handling timeouts/retries.
> 2. Implementing a simple DocumentAI client in Python with google-cloud-documentai: how to pass bytes + mime_type, which request/response classes to use, how to extract full text, and how to convert the response to JSON/dict for storage.
> 3. Error handling patterns: what are common exceptions from boto3 and Document AI, how to classify retriable vs non-retriable errors, and how to record error_message in parse_jobs.
> 4. Any gotchas when running this as a long-running worker process (memory, auth refresh, gRPC channel reuse, etc.).
>
> Please base the answer on up-to-date docs and real-world examples.

## 2. Key findings (summary)

- **Boto3 + Cloudflare R2 in async code**
  - `boto3` is synchronous; when used from async FastAPI/worker code, heavy calls (e.g. `put_object`, `get_object`) should be wrapped in `run_in_threadpool` (Starlette) to avoid blocking the event loop.
  - Session objects are **not** thread-safe; client objects created from a session are generally safe to share across threads. For our use case, a single `boto3.client("s3", ...)` created at startup is acceptable and can be reused from threadpool tasks.
  - Use `botocore.config.Config` to tune:
    - `max_pool_connections` for high concurrency.
    - `retries={'max_attempts': N, 'mode': 'standard'}` for transient errors.
    - `tcp_keepalive=True` to reduce connection churn.
  - For Cloudflare R2 specifically:
    - Use `endpoint_url="https://<account_id>.r2.cloudflarestorage.com"` (or account-specific endpoint), `region_name="auto"`.
    - Auth via access key / secret key or R2 API tokens; in our case, env-based key/secret is fine.

- **Document AI client (google-cloud-documentai)**
  - Use the v1 client: `from google.cloud import documentai_v1 as documentai`.
  - Typical flow:
    - Build processor name: `projects/{project_id}/locations/{location}/processors/{processor_id}` from env/config.
    - Construct request:
      - `raw_document=documentai.RawDocument(content=file_bytes, mime_type=mime_type)`.
      - Wrap into `documentai.ProcessRequest(name=processor_name, raw_document=raw_document)`.
    - Call `client.process_document(request=request)` (sync).
    - The response is `documentai.Document`; `document.text` contains full OCR text.
  - Converting to JSON for storage:
    - Use protobuf JSON utilities, e.g. `google.protobuf.json_format.MessageToDict(document)` or `.MessageToJson` if needed.
    - Store the dict/JSON in R2 via `upload_json`; keep only the key in `documents.docai_raw_r2_key`.

- **Error handling / retry patterns**
  - Boto3:
    - Common retriable AWS-style error codes: `SlowDown`, `RequestLimitExceeded`, `ThrottlingException`, `ServiceUnavailable`, `InternalError`, `RequestTimeout`.
    - Use botocore’s built-in retry config, and additionally decide at our service layer whether to requeue a job or mark `failed`.
  - Document AI:
    - Errors are surfaced as `google.api_core.exceptions.*` (e.g. `DeadlineExceeded`, `ServiceUnavailable`, `InvalidArgument`).
    - Transient errors (deadline exceeded, unavailable) are candidates for retry; invalid input (unsupported MIME, bad processor id) should be marked as permanent failure and written into `parse_jobs.error_message`.
  - For our `parse_jobs`:
    - On retriable errors, we can either:
      - retry inside worker with backoff; or
      - keep `status='queued'` and rely on later runs.
    - For non-retriable / validation errors:
      - set `status='failed'`, store truncated error string in `error_message`, and optionally mark `documents.status='error'`.

- **Long-running worker considerations**
  - Prefer a long-lived Document AI client per process; the underlying gRPC channel benefits from reuse.
  - Monitor for memory growth; protobuf objects and large JSON dicts can accumulate—ensure we do not keep them in global caches.
  - When using service account JSON via env path, the Document AI client handles auth token refresh; no manual refresh needed in most cases.
  - Worker loop should:
    - Sleep when no jobs are available to avoid DB hammering.
    - Catch unexpected exceptions at top-level to log them and keep the worker process alive.

## 3. How this affects our design

- `storage_r2.py`:
  - Keep the pattern of a cached `boto3.client("s3", endpoint_url=..., aws_access_key_id=..., aws_secret_access_key=...)`.
  - Wrap all heavy operations (`put_object`, `get_object`) in `run_in_threadpool` to keep both API and worker async-safe.
  - Add minimal retry behavior via `Config(retries=...)` and surface errors clearly so the parser pipeline can decide how to update `parse_jobs`.

- `docai_client.py`:
  - Implement `DocumentAIClient` as a thin wrapper around `documentai.DocumentProcessorServiceClient`.
  - Expose async `process_document_ocr` that internally calls sync `client.process_document` via `run_in_threadpool` (or by isolating it in the worker if we keep worker sync).
  - Always extract `document.text` and convert the `Document` message to a dict for JSON storage.

- Parser pipeline:
  - Clearly separate retriable vs non-retriable errors:
    - Map boto3/Document AI exception types and error codes to our `parse_jobs.status` and `error_message`.
  - Keep job-level try/except in `process_single_job` and never let an exception crash the entire worker loop.

These points will guide the concrete implementation of `storage_r2` helpers, `DocumentAIClient`, and `ParserPipelineService` in Phase 2.

