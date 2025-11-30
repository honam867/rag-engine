# rag-engine – Architecture Overview

Mục tiêu: mô tả kiến trúc **nền móng** cho app mới sử dụng RAG‑Anything + Document AI + Supabase + Cloudflare R2.  
File này là source of truth high‑level; các file tech design theo phase sẽ bám theo kiến trúc này.

---

## 1. Các layer chính

**1. API & Orchestration (FastAPI)**  
- Nhận request từ client (REST/WebSocket).  
- Xử lý auth (JWT Supabase).  
- Orchestrate các service: DB, storage, parser, RAG engine, jobs.  

**2. Domain & Persistence (Supabase/Postgres)**  
- Nguồn sự thật (source of truth) cho:
  - Users (auth.users), workspaces, documents, files, parse_jobs, rag_documents, conversations, messages.  
- Không chứa logic business phức tạp, nhưng schema được thiết kế để hỗ trợ toàn bộ pipeline.

**3. Storage Layer (Cloudflare R2)**  
- Lưu file vật lý:
  - PDF, DOCX, hình ảnh, JSON raw từ Document AI.  
- Được wrap bởi 1 module `storage_r2`, các layer khác không đụng trực tiếp vào SDK R2.

**4. Parser Layer (Google Cloud Document AI + chunker)**  
- Sub‑layer 1: **Document AI client**  
  - Gọi Enterprise Document OCR, trả `Document` (hoặc JSON).  
- Sub‑layer 2: **Parser pipeline**  
  - Worker đọc `parse_jobs`, tải file từ R2, gọi Document AI, lưu `docai_full_text` + JSON raw key.  
- Sub‑layer 3: **Chunker**  
  - Dựa trên `docai_full_text` (và JSON raw nếu cần) → build `content_list` chuẩn RAG‑Anything.

**5. RAG Engine Layer (RAG‑Anything)**  
- Import như library, bọc trong module `rag_engine`.  
- Chịu trách nhiệm:
  - Ingest `content_list` → LightRAG (embeddings, vector store, graph).  
  - Query RAG (`aquery`) với system prompt phù hợp persona.  
- Không biết gì về Supabase, R2, Document AI; chỉ nhận input là `content_list` / `query`.

**6. Jobs / Worker Layer**  
- Xử lý bất đồng bộ:
  - `parse_jobs` (Phase 2).  
  - `ingest_jobs` (Phase 3 – từ doc đã OCR vào RAG).  
- Có thể dùng:
  - Worker riêng, hoặc background task/cron (chi tiết ở tech design).  

**7. Client / UI (future)**  
- Web UI hoặc tool khác (CLI, Postman) dùng các API đã thiết kế.  
- Không phải trọng tâm trong kiến trúc engine, nhưng cần biết API nào tồn tại.

---

## 2. Luồng dữ liệu high‑level

1. **User login** → nhận JWT từ Supabase.  
2. **Tạo workspace** → ghi vào DB.  
3. **Upload file vào workspace**:
   - API nhận file → save lên R2 → tạo `documents`, `files`, `parse_jobs`.  
4. **Worker Phase 2**:
   - Lấy `parse_jobs` → tải file từ R2 → gọi Document AI OCR → lưu `docai_full_text` + JSON raw key.  
5. **Worker Phase 3**:
   - Tìm documents `status='parsed'` → chunker tạo `content_list` → `rag_engine.ingest_content(...)` → lưu `rag_documents` + set `status='ingested'`.  
6. **Chat**:
   - `POST /conversations/{id}/messages` → lưu message `user` → gọi `rag_engine.query(...)` → lưu message `ai` + metadata (citations).  

---

## 2.1. ASCII flow – pipeline tổng (v1)

Đây là sơ đồ text để dễ hình dung lifecycle của RAG cho từng workspace.

**Ingestion (upload → parse → ingest vào RAG)**:

```text
[User]
  |
  v
[HTTP: POST /workspaces/{ws}/documents/upload]
  |
  v
[API server]
  |
  |---> Save file to R2
  |---> Insert: documents, files, parse_jobs(status='queued')
  v
[DB: Supabase Postgres]
  (documents, files, parse_jobs)

--- Phase 2: OCR worker ---

[parse_worker loop]
  |
  |---> SELECT parse_jobs WHERE status='queued'
  |---> For each job:
  |        - load file metadata
  |        - storage_r2.download_file(...)
  |        - docai_client.process_document_ocr(...)
  |        - documents.docai_full_text = text
  |        - upload JSON -> R2 (docai-raw/{document_id}.json)
  |        - documents.docai_raw_r2_key = that key
  |        - documents.status = 'parsed'
  |        - parse_jobs.status = 'success'
  v
[DB updated: document now PARSED]

--- Phase 3: ingest worker ---

[ingest_worker loop]
  |
  |---> SELECT documents
  |      WHERE status='parsed' AND no rag_documents
  |---> For each document_id:
  |        - chunker.build_content_list_from_document(document_id)
  |        - build file_path = "{workspace_id}/{document_id}/{original_filename}"
  |        - doc_id = str(document_id)
  |        - RagEngineService.ingest_content(
  |             workspace_id, document_id, content_list, file_path, doc_id
  |          )
  |             |
  |             |  -> RagEngineService._get_instance(workspace_id)
  |             |     (tạo hoặc lấy RAGAnything/LightRAG cho workspace đó,
  |             |      storage chính là Supabase PGVector)
  |             v
  |           [RAGAnything / LightRAG for this workspace]
  |             |
  |             |---> insert_content_list(...)
  |             v
  |        - INSERT rag_documents(document_id, workspace_id, rag_doc_id=doc_id)
  |        - UPDATE documents.status = 'ingested'
  v
[DB: documents INGESTED, rag_documents mapping ready]
```

**Chat (user hỏi → RAG trả lời)**:

```text
[User]
  |
  v
[HTTP: POST /conversations/{conv_id}/messages]
  |
  v
[API server]
  |
  |---> load conversation -> workspace_id
  |---> save message(role='user', content=question)
  |---> call RagEngineService.query(workspace_id, question, system_prompt)
  |         |
  |         |  -> RagEngineService._get_instance(workspace_id)
  |         |     (dùng lại instance đã ingest tài liệu của workspace đó)
  |         v
  |       [RAGAnything / LightRAG for this workspace]
  |         |
  |         |---> aquery(question, mode="mix", system_prompt=...)
  |         v
  |<-------- answer + citations(file_path, page_idx)
  |
  |---> save message(role='ai', content=answer, metadata.citations=...)
  v
[HTTP response -> trả lời + citations]
```

Lưu ý quan trọng:

- Raw file & JSON Document AI luôn nằm trên **R2**;  
  RAG chỉ làm việc với `content_list` đã chunk + index trong Supabase Postgres (PGVector).  
- Mỗi `workspace_id` có instance RAG‑Anything/LightRAG riêng (hoặc namespace riêng),  
  nên tri thức giữa các workspace không bị lẫn nhau.

---

## 3. High‑level folder tree cho app mới

Đây là skeleton cho project Python/FastAPI mới (không phải repo RAG‑Anything hiện tại):

```text
server/
  app/
    main.py                # Entry FastAPI app

    core/
      config.py            # Đọc env, config (Supabase, R2, GCP, RAG)
      logging.py           # Thiết lập logging chung
      security.py          # Verify Supabase JWT, dependency current_user

    db/
      session.py           # Kết nối Postgres (SQLAlchemy Core/asyncpg, không phụ thuộc nặng ORM)
      models.py            # (Optional) ORM models / type hints mapping schema Supabase
      repositories.py      # Hàm truy vấn DB (workspaces, documents, jobs, conversations,...)

    api/
      routes/
        me.py              # /me
        workspaces.py      # CRUD workspace
        documents.py       # Upload/list documents
        conversations.py   # CRUD conversation, list messages
        messages.py        # POST message (chat)
        status.py          # (optional) endpoints xem trạng thái jobs/documents

    schemas/
      workspaces.py        # Pydantic schemas cho workspace
      documents.py         # Pydantic schemas cho documents/files
      conversations.py     # Pydantic schemas cho conversations/messages
      common.py            # Kiểu chung (pagination, error response,...)

    services/
      storage_r2.py        # Lớp wrap Cloudflare R2 (upload/download file, upload/download JSON)
      docai_client.py      # Lớp wrap Google Cloud Document AI OCR
      parser_pipeline.py   # Logic xử lý parse_jobs: lấy file → gọi docai → update documents
      chunker.py           # build_content_list_from_document(document_id)
      rag_engine.py        # Wrap RAG‑Anything: ingest_content, query, delete_document
      jobs_ingest.py       # Logic ingest documents đã parsed vào RAG (Phase 3)

    workers/
      parse_worker.py      # Worker/job runner cho parse_jobs
      ingest_worker.py     # Worker/job runner cho ingest_jobs (nếu tách riêng)

    utils/
      time.py              # Utilities về thời gian (timestamp, timezone)
      ids.py               # Sinh ID, validate uuid,... (optional)

client/                    # Placeholder cho UI (web/app) sẽ gọi API của server
  (hiện tại để trống, chỉ thiết kế API phía server)
```

Nguyên tắc:

- `api/` chỉ gọi **services** + **repositories** + **schemas**.  
- `services/` mới gọi:
  - `storage_r2` (R2),  
  - `docai_client` (Document AI),  
  - `rag_engine` (RAG‑Anything).  
- `db/` không biết gì về Document AI hoặc RAG‑Anything – chỉ lưu/truy xuất dữ liệu.  

---

## 4. Source of truth & pattern chung

- **Source of truth cho domain**: Postgres schema (file planning).  
  - Mọi service/API phải align với schema này.  
- **Source of truth cho knowledge**: RAG‑Anything/LightRAG storage (vector/graph) – nhưng luôn được điều khiển bởi DB:
  - `rag_documents` giữ mapping `document_id ↔ rag_doc_id`.  
- Pattern chung khi thiết kế phần mới:
  1. Bắt đầu từ **DB & service layer** (repositories + services).
  2. Thiết kế interface rõ ràng ở `services/` (hàm public, input/output đơn giản).  
  3. API/worker chỉ dùng các interface đó, không chọc sâu vào lib bên dưới.

---

## 5. Vai trò các file tech design theo phase

- `phase-1-design.md`:
  - Đi từ kiến trúc này, mô tả chi tiết:
    - Cách connect Supabase, R2.
    - Các route nào được implement.
    - Models/schemas cụ thể dùng trong Phase 1.

- `phase-2-design.md`:
  - Thiết kế cụ thể cho `docai_client`, `parser_pipeline`, worker parse_jobs, cách lưu `docai_full_text` + JSON raw.

- `phase-3-design.md`:
  - Thiết kế cụ thể cho `chunker`, `rag_engine` (cách init RAG‑Anything, config model, storage), wiring với API chat.

Các file tech design **không đổi kiến trúc nền** trong file này; nếu sau này cần đổi nền (breaking), phải cập nhật `architecture-overview.md` trước.
