# client-design.md – Client logic & flows (v1)

> File này mô tả **logic FE** ở mức high‑level: màn hình nào, gọi API nào, luồng dữ liệu ra sao.  
> Không ràng buộc framework (React/Vue/…); chỉ là “bản đồ” để client kết nối đúng với backend.

---

## 1. Mục tiêu & scope

- Một UI nội bộ, single user (nhưng kiến trúc vẫn hỗ trợ multi‑user).
- Tập trung vào 3 luồng chính:
  - Auth qua Supabase → lấy JWT.
  - Quản lý workspace + tài liệu (upload, xem trạng thái parse/ingest).
  - Chat RAG theo workspace (conversation + messages, citations).
- Không thiết kế chi tiết UI/UX (màu sắc, layout pixel‑perfect), chỉ định nghĩa:
  - Màn hình / view chính.
  - Event chính của user.
  - API nào được gọi, data client cần giữ trong state.

---

## 2. Luồng tổng từ góc nhìn client

1. User mở app → nếu chưa có JWT hợp lệ:
   - Điều hướng đến màn hình **Login** (Supabase Auth).
2. Sau khi login:
   - Lưu access token (memory / localStorage tùy lựa chọn).
   - Thiết lập header `Authorization: Bearer <token>` cho mọi request đến backend.
3. Hiển thị màn hình **Workspace list**:
   - Gọi `GET /workspaces` → hiển thị danh sách.
4. User chọn một workspace:
   - Điều hướng đến **Workspace detail** với 2 tab chính:
     - **Documents**: quản lý tài liệu + trạng thái parse/ingest.
     - **Chat**: conversations + messages trong workspace đó.
5. Ở tab Documents:
   - User upload file → call API upload → thấy document mới với status `pending`.
   - App **polling** (hoặc F5 thủ công) `GET /workspaces/{workspace_id}/documents` để xem cập nhật `pending → parsed → ingested`.
6. Ở tab Chat:
   - User tạo conversation mới hoặc chọn conversation cũ.
   - Gửi câu hỏi → backend gọi RAG Engine → trả về answer + citations → hiển thị trong UI.
7. User có thể chuyển workspace bất kỳ lúc nào:
   - Mỗi workspace có tập documents, conversations, messages **hoàn toàn riêng** (isolation).

---

## 3. Màn hình & view chính

### 3.1. Auth (Login)

- Mục tiêu:
  - Lấy JWT từ Supabase Auth (email/password).
- Cách làm (logic):
  - UI có form email/password.
  - Gọi Supabase (trực tiếp, không qua backend này) bằng Supabase JS SDK hoặc HTTP:
    - `supabase.auth.signInWithPassword({ email, password })`.
  - Sau khi sign in thành công:
    - Lấy `access_token`.
    - Lưu token ở client.
    - Điều hướng sang `/workspaces`.
- Backend FastAPI không cần route login riêng; chỉ cần **nhận JWT** ở tất cả API protected.

### 3.2. Workspace list

- URL gợi ý: `/workspaces`.
- Data cần trong state:
  - `currentUser` (từ `/me`).
  - `workspaces` – list workspace của user.
- Khi mở màn hình:
  - Gọi `GET /me` → hiển thị email, hoặc dùng để test token.
  - Gọi `GET /workspaces`:
    - Hiển thị list: tên workspace, mô tả, created_at.
- Tạo workspace mới:
  - Form nhỏ (name, description).
  - Gọi `POST /workspaces` với body JSON tương ứng.
  - Nếu thành công:
    - Thêm vào list hoặc reload `GET /workspaces`.
- Chọn workspace:
  - Click item → điều hướng `/workspaces/{workspace_id}` (Workspace detail).

### 3.3. Workspace detail – Documents tab

- URL gợi ý: `/workspaces/{workspace_id}/documents`.
- Data cần trong state:
  - `workspace` (id, name, description).
  - `documents` – list các documents của workspace.
- Khi vào tab:
  - Gọi `GET /workspaces/{workspace_id}` (nếu cần chi tiết).
  - Gọi `GET /workspaces/{workspace_id}/documents`:
    - Hiển thị: title (hoặc original filename), status (`pending`, `parsed`, `ingested`, `error`), created_at.
    - Có thể hiển thị thêm: số file, size, v.v. nếu API trả.
- Upload file:
  - Cho phép chọn 1 (về sau nhiều) file từ máy.
  - Gửi `POST /workspaces/{workspace_id}/documents/upload` với multipart form:
    - `files[]`: các file được chọn.
  - Sau khi API trả documents mới:
    - Thêm vào list documents với status `pending`.
- Cập nhật trạng thái parse/ingest:
  - Định kỳ (ví dụ 5–10s) gọi lại `GET /workspaces/{workspace_id}/documents`.
  - Cập nhật status các document trong UI:
    - `pending` → `parsed` → `ingested`.
  - Nếu document `error`:
    - Hiển thị badge, tooltip lý do (nếu API có) và gợi ý retry (Phase sau).

> Ghi chú: V1 không bắt buộc hiển thị nội dung file hoặc preview trang; chỉ cần danh sách + trạng thái.  
> Về sau có thể thêm xem “file A – trang 5” dựa trên citations khi chat.

### 3.4. Workspace detail – Chat tab

- URL gợi ý: `/workspaces/{workspace_id}/chat` hoặc `/workspaces/{workspace_id}/conversations/{conversation_id?}`.
- Data cần trong state:
  - `workspace`.
  - `conversations` – list conversation trong workspace.
  - `currentConversation` – conversation đang mở.
  - `messages` – list message (role, content, created_at, metadata).

**Luồng khi mở tab Chat:**

1. Gọi `GET /workspaces/{workspace_id}/conversations`:
   - Hiển thị list ở sidebar: tên conversation, updated_at.
2. Nếu user chọn một conversation:
   - Gọi `GET /conversations/{conversation_id}/messages`.
   - Render chat history:
     - Tin nhắn `role='user'` (mình).
     - Tin nhắn `role='ai'` (câu trả lời từ RAG).
3. Nếu chưa có conversation nào:
   - Hiển thị nút “Create new conversation”.

**Tạo conversation mới:**

- Gọi `POST /workspaces/{workspace_id}/conversations` với body `{ "title": <optional> }`.
- Backend trả về `conversation_id`.
- Điều hướng ngay sang `/workspaces/{workspace_id}/conversations/{conversation_id}` và load messages (sẽ trống).

**Gửi câu hỏi (message):**

- Ở view conversation:
  - Textarea / input cho câu hỏi.
  - Khi bấm Send:
    - Gọi `POST /conversations/{conversation_id}/messages` với body `{ "content": "<câu hỏi>" }`.
    - V1:
      - Backend lưu message `role='user'`.
      - Backend gọi RAG Engine (Phase 3):
        - Lưu message `role='ai'` với `content` là answer và `metadata.citations` (nếu có).
      - Trả về cả 2 message hoặc state mới (tùy thiết kế chi tiết).
    - Client:
      - Append message user ngay (optimistic).
      - Sau khi nhận response, append/replace message `ai`.

**Hiển thị citations “file A – trang 5”:**

- Mỗi message `role='ai'` có thể có `metadata.citations`:
  - Ví dụ: `[{ "document_id": "...", "file_name": "file-a.pdf", "page_number": 5 }]`.
- UI:
  - Dưới câu trả lời, hiển thị list:
    - `file-a.pdf – trang 5`
  - Click citation:
    - Mở panel/overlay:
      - V1 chỉ cần hiển thị thông tin text đơn giản (`file name`, `page`).
      - Về sau có thể:
        - Mở viewer PDF trên R2 với highlight page tương ứng.

---

## 4. State management & navigation (logic tổng, không phụ thuộc framework)

- **State lõi** của app client:
  - `auth`: access token, currentUser (`/me`), trạng thái logged‑in.
  - `workspaces`: danh sách, `currentWorkspaceId`.
  - `documents`: theo `currentWorkspaceId`.
  - `conversations`: theo `currentWorkspaceId`.
  - `messages`: theo `currentConversationId`.
- **Navigation**:
  - Dù dùng router nào (React Router, Vue Router, …), nên cố gắng giữ shape URL:
    - `/login`
    - `/workspaces`
    - `/workspaces/:workspaceId`
    - `/workspaces/:workspaceId/documents`
    - `/workspaces/:workspaceId/conversations/:conversationId`
- **Auth guard**:
  - Nếu không có token → redirect `/login`.
  - Nếu token invalid (API trả 401) → clear token + redirect `/login`.

---

## 5. Polling & feedback người dùng

- **Polling document status**:
  - Sau khi upload, bật timer (setInterval) cho workspace hiện tại:
    - Mỗi X giây gọi `GET /workspaces/{workspace_id}/documents`.
    - Tắt timer khi user rời khỏi workspace.
- **Feedback**:
  - Loading state khi gọi API (spinner, button disabled).
  - Toast/alert cho lỗi:
    - 401 → “Phiên đăng nhập hết hạn, vui lòng login lại.”
    - 4xx khác → hiển thị message từ server (nếu phù hợp).
    - 5xx → “Hệ thống đang gặp lỗi, thử lại sau.”

---

## 6. Mở rộng tương lai (không bắt buộc ở v1)

- Streaming câu trả lời:
  - Thay `POST /conversations/{id}/messages` trả full message → dùng SSE/WebSocket để stream từng chunk.
- Realtime documents status:
  - Dùng WebSocket để push cập nhật parse/ingest thay vì polling.
- Nhiều tab view trong workspace:
  - “Documents”, “Chat”, “Analytics” (thống kê số câu hỏi, tài liệu sử dụng nhiều, v.v.)

---

## 7. Kết luận

- File này chỉ ra **luồng logic client**:
  - Thứ tự màn hình.
  - API nào map vào view nào.
  - Cách giữ state tối thiểu để không “lạc” giữa workspace/conversation.
- Khi bắt đầu xây client thực tế:
  - Chọn framework (React/Vue/…).
  - Áp dụng router + state management dựa trên sơ đồ URL & state ở đây.
  - Test trước các API Phase 1 bằng Postman / curl rồi mới gắn UI để giảm lỗi.

