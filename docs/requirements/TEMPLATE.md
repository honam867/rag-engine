# [Tên Project/Module] – [Mô tả ngắn] Spec [Version]

## 1. Mục tiêu & Phạm vi (Goals & Scope)

- **Mục tiêu chính**: Mô tả ngắn gọn mục đích của tài liệu hoặc giai đoạn này (Ví dụ: Xây dựng khung backend, Tích hợp module X).
- **Phạm vi công việc**:
  - Những tính năng/module sẽ được triển khai.
  - Những phần nằm *ngoài* phạm vi (out of scope).
- **Kết quả kỳ vọng (Deliverables)**:
  - Code, API endpoints, Schema database, Tài liệu, v.v.

---

## 2. Các khái niệm & thực thể chính (Key Concepts & Entities)

Định nghĩa các thuật ngữ và thực thể nghiệp vụ quan trọng trong phạm vi tài liệu này.

### 2.1. [Tên thực thể A]
- Mô tả: ...
- Vai trò trong hệ thống: ...

### 2.2. [Tên thực thể B]
- Mô tả: ...

---

## 3. Luồng nghiệp vụ (User/System Flows)

Mô tả các bước tương tác của người dùng hoặc quy trình xử lý của hệ thống.

### 3.1. [Tên Flow 1 - Ví dụ: Upload tài liệu]
1. User thực hiện hành động A...
2. Hệ thống xử lý B...
3. Kết quả trả về C...

### 3.2. [Tên Flow 2 - Ví dụ: Xử lý background]
- Bước 1: Worker nhận job...
- Bước 2: Gọi service bên thứ 3...
- Bước 3: Cập nhật DB...

---

## 4. Kiến trúc & Thiết kế kỹ thuật (Architecture & Technical Design)

### 4.1. Backend / Service Layer
- Mô tả cấu trúc module, các service mới.
- Các pattern sử dụng (Dependency Injection, Factory, v.v.).

### 4.2. Database Schema (Supabase / Postgres)
Liệt kê các bảng (tables) mới hoặc các thay đổi trên bảng cũ.

- `table_name`
  - `id` (PK)
  - `column_name` (data_type, constraints) - Mô tả
  - `created_at`, `updated_at`

### 4.3. External Services / Storage
- **Service A (ví dụ: Cloudflare R2)**:
  - Cách tích hợp, thư viện sử dụng.
  - Cấu trúc lưu trữ (folder structure, key format).
- **Service B**:
  - Interface giao tiếp.

---

## 5. API Endpoints (Dự kiến)

Danh sách các API cần implement.

### 5.1. [Nhóm API A - Ví dụ: Workspaces]
- `GET /path`: Mô tả input/output.
- `POST /path`: Mô tả body, action.

### 5.2. [Nhóm API B]
- ...

---

## 6. Kế hoạch triển khai (Implementation Plan)

Các bước thực hiện cụ thể (Step-by-step).

1. **Bước 1**: Thiết lập môi trường / DB migration.
2. **Bước 2**: Implement core services.
3. **Bước 3**: Implement API & wiring.
4. **Bước 4**: Testing & Integration.

---

## 7. Ghi chú & Giả định (Notes & Assumptions)

- Các giả định kỹ thuật (ví dụ: giả định service X đã available).
- Các vấn đề cần lưu ý (security, performance).
- Open questions (nếu có).
