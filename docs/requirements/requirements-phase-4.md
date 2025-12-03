# rag-engine-phase-4 – Delete & Cleanup (Workspace / Conversation / Document / RAG / R2)

## 1. Mục tiêu Phase 4

- Hoàn thiện **vòng đời xoá (delete lifecycle)** cho:
  - Workspaces.
  - Conversations.
  - Documents (nâng cấp từ Phase 3).
  - Messages (optional).
- Đảm bảo khi xoá, hệ thống xử lý đồng bộ:
  - Dữ liệu DB (Postgres / Supabase).
  - Blob trên Cloudflare R2 (file PDF + JSON OCR).
  - Dữ liệu knowledge trong RAG-Anything (ít nhất về mặt logical / storage per workspace).

Phase 4 **không** thêm logic RAG mới (retrieval, rerank) – chỉ tập trung vào **cleanup chính xác, an toàn**.

---

## 2. Phạm vi & ưu tiên

### 2.1. Phạm vi bắt buộc

- Bổ sung các API xoá còn thiếu:
  - `DELETE /api/workspaces/{workspace_id}`
  - `DELETE /api/workspaces/{workspace_id}/conversations/{conversation_id}`
- Nâng cấp API xoá document:
  - `DELETE /api/workspaces/{workspace_id}/documents/{document_id}`
    - Đã có từ Phase 3, nhưng cần nâng cấp behaviour:
      - Xoá record DB liên quan.
      - Xoá file trên R2.
      - Xử lý RAG mapping và storage tương ứng.

### 2.2. Phạm vi optional

- Xoá message đơn lẻ:
  - `DELETE /api/conversations/{conversation_id}/messages/{message_id}`:
    - Optional cho Phase 4, chỉ làm nếu thời gian cho phép và hợp với UI.
- Soft delete:
  - V1 Phase 4 chấp nhận xoá **hard delete** (xóa row).
  - Nếu sau này cần audit log, có thể bổ sung `deleted_at` / `is_deleted` ở Phase sau.

---

## 3. Luồng xoá workspace (DELETE /workspaces/{workspace_id})

### 3.1. Hành vi mong muốn

- Khi user xoá workspace:
  - Người dùng không còn thấy workspace, documents, conversations, messages trong UI.
  - Dữ liệu liên quan được dọn:
    - **DB**:
      - `conversations` + `messages` thuộc workspace.
      - `documents` + `files` + `parse_jobs` + `rag_documents` thuộc workspace.
      - Bản thân `workspaces` row.
    - **Cloudflare R2**:
      - File gốc: `files.r2_key` (PDF/doc).
      - File OCR raw: `documents.docai_raw_r2_key` (JSON Document AI).
    - **RAG-Anything**:
      - Knowledge store cho workspace bị xoá:
        - V1 (Phase 4): xoá **toàn bộ working_dir của workspace** (vd `rag_workspaces/{workspace_id}`) trên filesystem/volume.

### 3.2. Yêu cầu chi tiết

- Auth:
  - Chỉ cho phép xoá workspace của chính user (`workspaces.user_id = current_user.id`).
- Transaction / nhất quán:
  - Xoá DB theo thứ tự an toàn (messages → conversations → parse_jobs → rag_documents → files → documents → workspaces).
  - Xử lý lỗi R2 / filesystem:
    - Nếu xoá R2 hoặc thư mục RAG thất bại:
      - Log rõ ràng.
      - Không roll back DB (v1 chấp nhận “dangling blob”).
      - Có thể ghi thêm log/metrics để phase sau cleanup offline.

---

## 4. Luồng xoá conversation (DELETE /workspaces/{workspace_id}/conversations/{conversation_id})

### 4.1. Hành vi mong muốn

- Khi user xoá một conversation trong workspace:
  - conversation + tất cả messages thuộc nó bị xoá khỏi DB.
  - RAG knowledge **không bị xoá**:
    - Conversation không tạo knowledge riêng; chỉ là view chat.
  - Không xoá document hoặc file.

### 4.2. Yêu cầu chi tiết

- Auth:
  - Chỉ cho phép xoá conversation nếu:
    - `conversations.workspace_id = workspace_id` hiện tại.
    - `conversations.user_id = current_user.id`.
- DB:
  - Xoá toàn bộ `messages` thuộc `conversation_id`.
  - Xoá row `conversations`.
- Ảnh hưởng R2 / RAG:
  - Không gọi R2 / RagEngineService.

---

## 5. Luồng xoá document (DELETE /workspaces/{workspace_id}/documents/{document_id}) – Nâng cấp

### 5.1. Hành vi hiện tại (Phase 3)

- Phase 3 mới chỉ:
  - Xoá mapping `rag_documents` trong DB.
  - Gọi `RagEngineService.delete_document(workspace_id, rag_doc_id)` (hiện là no-op).
  - Xoá row `documents` (file R2 & các row liên quan chưa cleanup đầy đủ).

### 5.2. Hành vi mong muốn sau Phase 4

- Khi user xoá document:
  - **DB**:
    - Xoá:
      - Row `rag_documents` tương ứng.
      - Row `parse_jobs` của document.
      - Row `files` của document.
      - Row `documents` chính nó.
  - **Cloudflare R2**:
    - Xoá:
      - File gốc: `files.r2_key`.
      - JSON OCR: `documents.docai_raw_r2_key` (nếu không null).
  - **RAG-Anything**:
    - Logical delete:
      - V1 Phase 4 vẫn ưu tiên delete ở DB + storage per workspace.
      - `RagEngineService.delete_document`:
        - Nếu RAG-Anything/LightRAG có API delete doc → gọi thật.
        - Nếu chưa có → ghi rõ là no-op, chấp nhận vector cũ tồn tại nhưng không còn mapping từ app (tài liệu đã xoá không còn được chọn lại để ingest/query).

### 5.3. Behavior về pipeline

- Xoá document **không** ảnh hưởng tới workspace hay conversations khác.
- Nếu ingest worker đang chạy:
  - Khi document bị xoá khỏi DB:
    - `list_parsed_documents_without_rag` sẽ không trả về doc đó nữa.
  - Nếu document bị xoá giữa chừng ingest:
    - Có thể gây lỗi ingestion (handled bằng log + bỏ qua), chấp nhận cho v1.

---

## 6. Optional: Xoá message đơn lẻ

### 6.1. Endpoint đề xuất

- `DELETE /api/conversations/{conversation_id}/messages/{message_id}`

### 6.2. Behavior

- Chỉ xoá 1 message, không ảnh hưởng đến document, R2 hoặc RAG.
- Auth:
  - Xác nhận `conversation_id` thuộc user hiện tại.
  - Xác nhận `message_id` thuộc conversation đó.
- Dùng cho:
  - UI muốn cho user “dọn chat history” thủ công ở mức message.
  - Không bắt buộc cho Phase 4 nếu không cần ở UI.

---

## 7. Kết quả sau Phase 4

Sau Phase 4, hệ thống đạt được:

- Vòng đời xoá đầy đủ:
  - Xoá workspace → dọn DB + R2 + storage RAG cho workspace.
  - Xoá conversation → dọn messages liên quan.
  - Xoá document → dọn DB liên quan + file gốc + JSON OCR + mapping RAG.
- Hành vi delete rõ ràng, tránh rác dữ liệu:
  - Hạn chế tối đa “dangling rows” trong Postgres.
  - Hạn chế “dangling blobs” trên R2 và storage RAG (ít nhất ở mức workspace).
- Giữ kiến trúc:
  - DB cleanup thông qua repositories.
  - R2 cleanup thông qua `services/storage_r2.py`.
  - RAG cleanup thông qua `services/rag_engine.py`.

Phase 5 (nếu có) có thể tập trung vào:
- Soft delete / audit log.
- Thêm công cụ admin để quét & cleanup dữ liệu còn sót (offline jobs).
