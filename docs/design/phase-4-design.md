# Phase 4 – Tech Design (Delete & Cleanup: Workspace / Conversation / Document / RAG / R2)

Mục tiêu: hiện thực hóa đặc tả Phase 4 trong `../requirements/requirements-phase-4.md` bằng thiết kế kỹ thuật cụ thể, bám kiến trúc `architecture-overview.md` và các layer hiện có (repositories, services, workers).

---

## 1. Phạm vi Phase 4 (tech)

- Thêm/xử lý các API xoá:
  - `DELETE /api/workspaces/{workspace_id}`
  - `DELETE /api/workspaces/{workspace_id}/conversations/{conversation_id}`
  - Nâng cấp `DELETE /api/workspaces/{workspace_id}/documents/{document_id}`.
  - Optional: `DELETE /api/conversations/{conversation_id}/messages/{message_id}`.
- Bổ sung cleanup cho:
  - DB: `files`, `parse_jobs`, `rag_documents`, `messages`, `conversations`, `documents`, `workspaces`.
  - Cloudflare R2: file gốc (`files.r2_key`), JSON OCR (`documents.docai_raw_r2_key`).
  - RAG-Anything: storage per workspace (`rag_workspaces/{workspace_id}`) và logical delete per document (tùy khả năng thư viện).

Phase 4 **không thay đổi**:
- Cách parse OCR (Phase 2).
- Cách ingest RAG (Phase 3).
- Hợp đồng API chat (chỉ gián tiếp hưởng lợi khi workspace/documents bị xoá không còn xuất hiện).

---

## 2. Các building blocks sẽ dùng lại

- DB:
  - Tables: `workspaces`, `documents`, `files`, `parse_jobs`, `rag_documents`, `conversations`, `messages`.
  - `server/app/db/repositories.py`:
    - Đã có: create/list/get cho workspaces, documents, conversations, messages, parse_jobs, rag_documents.
- R2:
  - `server/app/services/storage_r2.py`:
    - Đã có: `upload_file`, `download_file`, `upload_json`, `download_json`.
- RAG:
  - `server/app/services/rag_engine.py`:
    - Đã có: `ingest_content`, `query`, `delete_document` (hiện là no-op).
- API layer:
  - `server/app/api/routes/workspaces.py`
  - `server/app/api/routes/conversations.py`
  - `server/app/api/routes/documents.py`
  - `server/app/api/routes/messages.py`

Phase 4 sẽ:
- Thêm helpers delete vào repositories.
- Thêm hàm delete file/json vào `storage_r2.py`.
- Triển khai logic delete ở API layer thông qua các service/repo này.

---

## 3. R2 cleanup – storage_r2.py

### 3.1. Interface đề xuất

Trong `server/app/services/storage_r2.py`:

```python
def _delete_object_sync(key: str) -> None: ...

async def delete_object(key: str) -> None: ...
```

- `_delete_object_sync(key)`:
  - Dùng client S3 hiện có (`_get_client_and_bucket()`).
  - Gọi `client.delete_object(Bucket=bucket, Key=key)`.
  - Nếu R2 config thiếu hoặc lỗi → raise RuntimeError với message rõ ràng.
- `delete_object(key)`:
  - Wrapper async qua `run_in_threadpool`.

### 3.2. Sử dụng

- Khi xoá document:
  - Xoá:
    - `files.r2_key` (file gốc).
    - `documents.docai_raw_r2_key` (nếu không null).
- Khi xoá workspace:
  - Dùng dữ liệu `files` + `documents` để lặp & xoá tất cả key liên quan:
    - Không cần list từ R2 – chỉ dựa trên DB.

---

## 4. RAG cleanup – rag_engine.py

### 4.1. Document-level delete (v1)

Trong `RagEngineService.delete_document(workspace_id, rag_doc_id)`:

- V1 (Phase 3) đã là no-op; Phase 4:
  - Giữ no-op nếu RAG-Anything/LightRAG chưa có API xoá doc rõ ràng.
  - Cập nhật docstring + log để ghi rõ:
    - “Logical delete is handled at DB level; physical vector/graph cleanup will be implemented in a later phase.”

Nếu thư viện có API:

```python
await self._get_rag_instance(workspace_id).delete_document(rag_doc_id)
```

nhưng đây là optional/để sau, chỉ ghi chú trong code + design.

### 4.2. Workspace-level delete

- Ý tưởng: mỗi workspace có folder riêng `rag_workspaces/{workspace_id}`.
- Khi xoá workspace:

```python
async def delete_workspace_data(self, workspace_id: str) -> None:
    workspace_dir = os.path.join(self.settings.working_dir, workspace_id)
    # best-effort: remove directory tree if exists
```

- Implementation:
  - Dùng `shutil.rmtree(workspace_dir, ignore_errors=True)`.
  - Log success/error.
  - Không cần khóa/đồng bộ phức tạp, vì worker ingest/chat sẽ ngừng dùng workspace này sau khi DB bị xoá.

---

## 5. DB cleanup – repositories.py

### 5.1. Document-level helpers

Thêm vào `server/app/db/repositories.py`:

- `async def get_document_with_relations(session, document_id: str, workspace_id: str) -> Mapping | None`:
  - Join `documents` + `files` (LEFT join) để lấy:
    - `documents.docai_raw_r2_key`
    - `files.r2_key`
  - Giúp API delete document có đủ key R2 để xoá.

- `async def delete_document_cascade(session, document_id: str) -> None`:
  - Xoá theo thứ tự:
    - `messages` không liên quan trực tiếp → bỏ qua.
    - `rag_documents` (WHERE document_id=...).
    - `parse_jobs` (WHERE document_id=...).
    - `files` (WHERE document_id=...).
    - `documents` (WHERE id=...).
  - Gói trong transaction của session (commit 1 lần).

### 5.2. Workspace-level helpers

- `async def list_workspace_files_and_docs(session, workspace_id: str) -> Sequence[Mapping]`:
  - SELECT join `documents` + `files`:
    - `documents.id`, `documents.docai_raw_r2_key`, `files.r2_key`.
  - Dùng để biết toàn bộ key R2 cần xoá.

- `async def delete_workspace_cascade(session, workspace_id: str, user_id: str) -> None`:
  - Kiểm tra workspace thuộc user_id trước (hoặc bên API).
  - Thứ tự xoá gợi ý:
    - `messages`:
      - Join `messages` → `conversations` → `workspaces` để xoá messages thuộc workspace.
    - `conversations` của workspace.
    - `rag_documents`:
      - Join `rag_documents` → `documents` → `workspaces`.
    - `parse_jobs`:
      - Join `parse_jobs` → `documents` → `workspaces`.
    - `files`:
      - Join `files` → `documents` → `workspaces`.
    - `documents` thuộc workspace.
    - Cuối cùng `workspaces` row.

> Lưu ý: tuỳ schema/foreign key, cần đảm bảo thứ tự xoá không vi phạm constraint (hoặc dùng `ON DELETE CASCADE` nếu đã được cấu hình trên DB; ở đây assume không có cascade).

---

## 6. API layer – routes design

### 6.1. DELETE workspace

Endpoint:  
`DELETE /api/workspaces/{workspace_id}`

File:  
`server/app/api/routes/workspaces.py`

Steps:

1. Auth:
   - Lấy `current_user` từ JWT.
2. Check ownership:
   - `get_workspace(session, workspace_id, user_id=current_user.id)`:
     - Nếu không có → 404.
3. Chuẩn bị cleanup:
   - Dùng repo helper `list_workspace_files_and_docs` để lấy danh sách:
     - `files.r2_key`.
     - `documents.docai_raw_r2_key`.
4. DB delete:
   - Gọi `delete_workspace_cascade(session, workspace_id, current_user.id)`.
5. R2 cleanup (best-effort):
   - Loop qua danh sách key R2 đã thu được:
     - `await storage_r2.delete_object(key)` cho từng key.
   - Nếu lỗi → log warning, không rollback DB.
6. RAG cleanup (best-effort):
   - `RagEngineService.delete_workspace_data(workspace_id)`:
     - Xoá thư mục `rag_workspaces/{workspace_id}`.
   - Nếu lỗi → log warning.
7. Response:
   - 204 No Content.

### 6.2. DELETE conversation

Endpoint:  
`DELETE /api/workspaces/{workspace_id}/conversations/{conversation_id}`

File:  
`server/app/api/routes/conversations.py`

Steps:

1. Auth + ensure workspace:
   - `_ensure_workspace(session, workspace_id, current_user.id)`.
2. Check conversation:
   - `get_conversation(session, conversation_id, user_id=current_user.id)`:
     - Nếu không có hoặc không thuộc workspace → 404.
3. DB delete:
   - Xoá messages:

```python
await session.execute(
    sa.delete(models.messages).where(models.messages.c.conversation_id == conversation_id)
)
```

   - Xoá conversation:

```python
await session.execute(
    sa.delete(models.conversations).where(models.conversations.c.id == conversation_id)
)
await session.commit()
```

4. Không gọi R2/RAG.
5. Response: 204 No Content.

### 6.3. DELETE document (nâng cấp)

Endpoint:  
`DELETE /api/workspaces/{workspace_id}/documents/{document_id}`

File:  
`server/app/api/routes/documents.py`

Steps:

1. Auth + ensure workspace:
   - `_ensure_workspace(session, workspace_id, current_user.id)`.
2. Check document:
   - `get_document(session, document_id, workspace_id)`:
     - Nếu không tồn tại → 404.
3. Lấy metadata R2:
   - `get_document_with_relations(session, document_id, workspace_id)`:
     - Lấy `files.r2_key` (có thể nhiều file, v1 assume 1).
     - Lấy `documents.docai_raw_r2_key`.
4. DB delete:
   - `delete_document_cascade(session, document_id)`.
5. R2 cleanup:
   - Nếu có `files.r2_key` → `await storage_r2.delete_object(key)`.
   - Nếu có `docai_raw_r2_key` → `await storage_r2.delete_object(raw_key)`.
   - Lỗi → log warning.
6. RAG cleanup:
   - `RagEngineService.delete_document(workspace_id, rag_doc_id=str(document_id))`:
     - V1 Phase 4 có thể vẫn no-op; log rõ ràng.
7. Response: 204 No Content.

### 6.4. Optional: DELETE message

Endpoint:  
`DELETE /api/conversations/{conversation_id}/messages/{message_id}`

File:  
`server/app/api/routes/messages.py`

Steps:

1. Auth + ensure conversation:
   - `_ensure_conversation(session, conversation_id, current_user.id)`.
2. Check message thuộc conversation:
   - Query `messages` join `conversations` đảm bảo `conversation_id` + `user_id`.
3. Delete:

```python
await session.execute(
    sa.delete(models.messages).where(models.messages.c.id == message_id)
)
await session.commit()
```

4. Response: 204 No Content.

---

## 7. Observability & safety

- Logging:
  - Sau mỗi delete lớn (workspace/document), log:
    - user_id, workspace_id, document_id (nếu có), counts (số file R2 xoá được vs lỗi).
- Rate limit / protection:
  - Phase 4 không thêm layer rate-limit; nếu cần anti-abuse sẽ xử lý ở Phase sau hoặc ở layer khác (API gateway).
- Idempotency:
  - Nếu gọi DELETE nhiều lần:
    - Lần 1 → xoá thành công.
    - Lần 2 → 404 (vì row không còn) là chấp nhận được cho v1.

---

## 8. Kết nối với các Phase trước

- Phase 1:
  - Bảng DB và API khung đã có; Phase 4 chỉ bổ sung operations xoá, không đổi schema.
- Phase 2:
  - Delete document/workspace cần chú ý không làm gián đoạn parse worker:
    - Nếu parse đang chạy và document bị xoá → có thể log lỗi, bỏ qua; không cần đồng bộ phức tạp.
- Phase 3:
  - Delete document/workspace cần xử lý mapping `rag_documents` + storage RAG per workspace:
    - Đảm bảo sau xoá, ingest worker/chat không còn query/ingest trên doc/workspace đó (vì DB đã không còn row).

Thiết kế Phase 4 này giữ kiến trúc cũ:
- R2 cleanup chỉ đi qua `storage_r2`.
- RAG cleanup chỉ đi qua `RagEngineService`.
- API layer vẫn mỏng, gọi repositories + services, không truy vấn DB hoặc R2 trực tiếp ngoài đó.

