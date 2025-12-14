# Implement: Env Vars Cleanup & .env.example Restructure

## 1. Summary
- Mục tiêu: rà soát các biến môi trường backend/client đang dùng và cập nhật `.env.example` cho dễ cấu hình:
  - Gom nhóm theo service (Supabase, R2, Document AI, Redis, RAG/LightRAG, Answer LLM, client).
  - Loại bỏ biến legacy không còn dùng.
  - Ghi chú rõ biến nào required, biến nào optional/advanced.

## 2. Related spec / design
- Phase 1 / backend:
  - `docs/requirements/requirements-phase-1.md`
  - `docs/design/phase-1-design.md`
- Phase 1 / client:
  - `docs/requirements/requirements-phase-1-client.md`
  - `docs/design/phase-1-client-design.md`
- Phase 2 (Document AI OCR):
  - `docs/requirements/requirements-phase-2.md`
  - `docs/design/phase-2-design.md`
- Phase 3 / 9 (RAG & LightRAG):
  - `docs/design/phase-3-design.md`
  - `docs/requirements/requirements-phase-9.md`
  - `docs/design/phase-9-design.md`
- Phase 6 (Redis Event Bus):
  - `docs/requirements/requirements-phase-6.md`
  - `docs/design/phase-6-design.md`
- Phase 8 (Answer Orchestrator):
  - `docs/design/phase-8-design.md`
  - `docs/implement/implement-2025-12-07-phase-8-answer-engine-and-retrieval.md`

## 3. Files touched
- `.env.example`
  - Trước đây:
    - Liệt kê một số biến `SUPABASE_*`, `R2_*`, GCP DocAI, `OPENAI_API_KEY`, `REDIS_URL`.
    - Có `CONTEXT_WINDOW`, `MAX_CONTEXT_TOKENS` nhưng **không được dùng** ở backend hiện tại.
    - Một số biến Answer LLM được ghi thẳng, chưa gom nhóm rõ ràng.
  - Hiện tại (đã restructure):
    - **Backend – Supabase Postgres & Auth**
      - `SUPABASE_DB_URL` – bắt buộc, DSN kết nối Supabase Postgres.
      - `SUPABASE_JWT_SECRET` – bắt buộc, secret verify JWT của Supabase.
    - **Backend – Cloudflare R2 (file storage)**
      - `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`.
    - **Backend – Google Cloud Document AI (Phase 2 OCR)**
      - `GCP_PROJECT_ID`, `GCP_LOCATION`, `DOCAI_OCR_PROCESSOR_ID` – required nếu muốn dùng OCR.
      - `GCP_CREDENTIALS_PATH` – optional, path tới file service-account JSON (nếu không set sẽ dùng Application Default Credentials).
    - **Backend – Redis Event Bus (Phase 6)**
      - `REDIS_URL` – default `redis://localhost:6379/0`, dùng cho API + workers.
    - **Backend – OpenAI-compatible LLM / embeddings**
      - `OPENAI_API_KEY` – required cho LightRAG và Answer LLM (nếu không có `ANSWER_API_KEY`).
      - `OPENAI_BASE_URL` – optional, base URL cho OpenAI-compatible endpoint.
    - **Backend – RAG / LightRAG configuration (RagSettings)**
      - (tất cả đều optional, có default trong code):
        - `RAG_WORKING_DIR` – thư mục workspace LightRAG (default `./rag_workspaces`).
        - `RAG_QUERY_MODE` – mode query mặc định (`mix`, `hybrid`, `local`, `global`, `naive`, `bypass`).
        - `RAG_LLM_MODEL` – tên model LLM.
        - `RAG_EMBEDDING_MODEL` – tên model embedding.
        - `RAG_LLM_TEMPERATURE` – nhiệt độ mặc định cho LLM trong LightRAG (default 0.4).
    - **Backend – LightRAG Postgres / PGVector (advanced)**
      - Chỉ dùng khi muốn override config derive từ `SUPABASE_DB_URL`:
        - `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DATABASE`.
        - `POSTGRES_MAX_CONNECTIONS`, `POSTGRES_SSL_MODE`, `POSTGRES_STATEMENT_CACHE_SIZE`.
        - `EMBEDDING_DIM` – optional, override dimension vector; nếu không set, backend auto-set từ embedding model.
      - Ghi chú: các biến tuning khác của LightRAG (`TOP_K`, `CHUNK_TOP_K`, `MAX_TOTAL_TOKENS`, `RERANK_BINDING`, ...) **không liệt kê chi tiết** ở đây; người dùng có thể xem thêm `LightRAG/env.example` nếu cần tinh chỉnh sâu.
    - **Backend – Answer Orchestrator LLM (Phase 8, optional)** – map 1-1 với `AnswerSettings`:
      - `ANSWER_MODEL` – tên model chat.
      - `ANSWER_API_KEY` – API key riêng; nếu không set sẽ fallback `OPENAI_API_KEY`.
      - `ANSWER_BASE_URL` – base URL endpoint chat completions.
      - `ANSWER_MAX_TOKENS` – giới hạn tokens cho completion.
      - `ANSWER_TEMPERATURE` – nhiệt độ cho Answer LLM (không ảnh hưởng LightRAG).
    - **Client (Next.js) – API & Supabase**
      - Ghi chú là nên copy sang `client/.env`:
        - `NEXT_PUBLIC_API_BASE_URL` – base URL backend HTTP API (bắt buộc, dùng trong `client/lib/config.ts`).
        - `NEXT_PUBLIC_API_URL` – base URL backend WebSocket (optional; `RealtimeContext` fallback `http://localhost:8000` nếu không set).
        - `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` – config Supabase JS client.
  - Loại bỏ các biến không còn dùng:
    - `CONTEXT_WINDOW`, `MAX_CONTEXT_TOKENS` – không xuất hiện trong code/backend hiện tại → đã xoá khỏi `.env.example` để tránh nhầm lẫn.
  - Bổ sung chú thích ngắn gọn (tiếng Việt) cho từng nhóm, nêu rõ:
    - Nhóm nào là bắt buộc để backend chạy được.
    - Nhóm nào chỉ cần thiết nếu bật OCR / Answer Orchestrator / tuning LightRAG.
    - Liên kết ngắn tới LightRAG/env.example cho các env nâng cao.

## 4. API changes
- Không có thay đổi API hoặc behavior runtime; chỉ thay đổi file template `.env.example` cho dễ cấu hình và đồng bộ với code thực tế.

## 5. Notes / TODO
- Nếu sau này bổ sung thêm field vào `RagSettings`, `AnswerSettings`, `RedisSettings`, `DocumentAISettings`, ... cần:
  - Cập nhật `.env.example` cùng lúc để tránh lệch.
  - Ghi rõ biến bắt buộc vs optional trong comment.
- Với các môi trường production dùng config khác Supabase:
  - Có thể set `POSTGRES_*` + `EMBEDDING_DIM` trực tiếp và bỏ qua cơ chế derive từ `SUPABASE_DB_URL`.
  - Khi đó nên cập nhật docs deploy riêng, nhưng `.env.example` hiện tại đã đủ gợi ý cơ bản.

