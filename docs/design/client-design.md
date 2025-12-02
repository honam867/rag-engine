# client-design.md – Client logic & flows (v2 - Refactored Sidebar UI)

> Phiên bản v2: Thiết kế lại theo mô hình App-like với Global Sidebar (Workspaces) và Contextual Sidebar (Conversations).

---

## 1. Layout & Architecture (App Shell)

Thay vì các trang rời rạc, ứng dụng sử dụng **3-column layout** (hoặc 2-column tùy ngữ cảnh):

1.  **Left Sidebar (Global - Always Visible):**
    *   Hiển thị danh sách **Tất cả Workspaces**.
    *   Mỗi item là một Workspace (Icon Folder + Tên).
    *   Có thể Toggle (Expand/Collapse).
    *   **Top Item/Action:** "New Workspace" (Icon Folder + dấu cộng).
    *   Logic:
        *   Click "New Workspace" → Mở Modal tạo.
        *   Tạo xong → Workspace mới xuất hiện trên đầu danh sách ngay lập tức → Tự động select workspace đó.
        *   Click Workspace Item → Điều hướng sang `/workspaces/{workspaceId}`.

2.  **Main Content Area (Center):**
    *   Thay đổi nội dung dựa trên route hiện tại (Dashboard hoặc Chat).

3.  **Right Sidebar (Contextual):**
    *   Hiển thị danh sách **Conversations** của workspace đang chọn.
    *   **Logic ẩn/hiện:** Nếu workspace chưa có conversation nào → Ẩn sidebar này.

---

## 2. Các màn hình chi tiết

### 2.1. Workspace Dashboard (Trang chủ của 1 Workspace)

*   **URL:** `/workspaces/{workspaceId}` (Mặc định khi click vào workspace ở Left Sidebar).
*   **Giao diện:**
    *   **Khu vực trên (Input starter):**
        *   Một ô Input/Textarea lớn ở giữa màn hình (giống giao diện tìm kiếm/chat ban đầu).
        *   Logic:
            *   **Disabled** nếu Workspace chưa có Document nào (kèm tooltip/text nhắc user upload).
            *   **Enabled** nếu đã có Document.
            *   Nhập text và Enter/Send → Gọi API tạo Conversation mới với message đó → Chuyển hướng sang giao diện Chat.
    *   **Khu vực dưới (Documents List):**
        *   Danh sách các file đã upload.
        *   Có nút/khu vực Upload file mới.
        *   Hiển thị trạng thái parse/ingest (`pending`, `parsed`, `ingested`).

### 2.2. Chat Interface (Giao diện Chat)

*   **URL:** `/workspaces/{workspaceId}/conversations/{conversationId}`.
*   **Layout Fix (Yêu cầu quan trọng):**
    *   **Header:** Tên conversation.
    *   **Message List (Scrollable):** Chiếm toàn bộ không gian còn lại (`flex-1`, `overflow-y-auto`). Scrollbar nằm trong khu vực này, không scroll cả trang.
    *   **Input Area (Fixed Bottom):** Textarea nhập tin nhắn ghim dưới đáy màn hình.
*   **Behavior:**
    *   Khi vào conversation, Right Sidebar hiển thị list conversation, highlight conversation hiện tại, cái mới nhất nằm trên cùng.

### 2.3. Modal: Create Workspace

*   Popup đơn giản (Dialog).
*   Fields: Name, Description.
*   Action: Gọi API tạo → Success → Đóng modal → Refresh Left Sidebar → Redirect user đến workspace mới.

---

## 3. Data Flow & State Management

*   **Global State (React Query):**
    *   `['workspaces', 'list']`: Cần được fetch ở cấp độ Layout (hoặc Context) để Left Sidebar luôn có dữ liệu.
    *   `['conversations', 'list', workspaceId]`: Fetch ở layout con của Workspace hoặc component Right Sidebar.
*   **Refactor Routing:**
    *   Bỏ trang `/workspaces` (danh sách dạng bảng cũ).
    *   Redirect `/` hoặc `/workspaces` về workspace mới nhất (hoặc trang hướng dẫn chọn workspace).

## 4. API Mapping (Giữ nguyên Phase 1)

*   `GET /api/workspaces`: Dùng cho Left Sidebar.
*   `POST /api/workspaces`: Dùng cho Modal "New Workspace".
*   `GET /api/workspaces/{id}/documents`: Dùng cho Dashboard (dưới).
*   `GET /api/workspaces/{id}/conversations`: Dùng cho Right Sidebar.
*   `POST /api/conversations/{id}/messages`: Dùng cho Input starter và Chat input.