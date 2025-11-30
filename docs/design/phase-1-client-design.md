# Phase 1 – Client Tech Design (Next.js UI)

Mục tiêu: chuyển `requirements-phase-1-client.md` thành thiết kế kỹ thuật cụ thể cho một agent coding khác implement client trong `client/` folder. Không viết code cụ thể, chỉ định nghĩa cấu trúc file, pattern, interface.

---

## 1. Project init & setup

### 1.1. Init Next.js app (App Router + TS + Tailwind)

- Tạo project mới trong `client/` (cùng level với `server/`):

  - Dùng `create-next-app` (Next.js >= 14, App Router default):
    - Template: TypeScript, ESLint, Tailwind, App Router, src directory optional (có thể không dùng `src/` để đơn giản).
  - Sau khi tạo xong, move toàn bộ vào `client/`.

- Cấu trúc root tối thiểu:

```text
client/
  app/
  public/
  styles/        # sẽ thêm tokens ở đây
  package.json
  next.config.js
  tailwind.config.js
  postcss.config.js
  tsconfig.json
```

### 1.2. Dependencies cần cài

Trong `client/`:

- Core:
  - `next`, `react`, `react-dom`.
  - `typescript`, `@types/react`, `@types/node`.
- Styling:
  - `tailwindcss`, `postcss`, `autoprefixer`.
  - shadcn/ui: `clsx`, `tailwind-merge`, `lucide-react`, các package mà shadcn yêu cầu.
- Data & state:
  - `@tanstack/react-query`.
  - `@tanstack/react-query-devtools` (optional dev).
- Supabase:
  - `@supabase/supabase-js`.
- Optional nhưng highly recommended:
  - `react-hook-form`, `@hookform/resolvers`.
  - `zod` (schema validation cho form).

Dev tools:
- ESLint, Prettier (Next template thường có sẵn).

---

## 2. Env & config layer

### 2.1. Env variables mapping

Thiết kế file `client/lib/config.ts`:

- Trách nhiệm:
  - Đọc các `process.env.NEXT_PUBLIC_*` và export dạng constant type-safe.
  - Nếu env quan trọng bị thiếu → throw Error trong `config.ts` (fail fast).

Interface gợi ý:

```ts
// lib/config.ts (pseudo)
export const API_BASE_URL: string;              // từ NEXT_PUBLIC_API_BASE_URL
export const SUPABASE_URL: string;              // từ NEXT_PUBLIC_SUPABASE_URL
export const SUPABASE_ANON_KEY: string;         // từ NEXT_PUBLIC_SUPABASE_ANON_KEY
export const IS_DEV_TOKEN_ENABLED: boolean;     // từ NEXT_PUBLIC_DEV_TOKEN_MODE (optional)
```

Yêu cầu:
- Agent không dùng `process.env` rải rác, luôn import từ `lib/config`.

### 2.2. Route & path constants

File `client/lib/routes.ts`:

- Chứa **client routes**:

```ts
export const ROUTES = {
  login: "/login",
  appRoot: "/app",
  workspaces: "/app/workspaces",
  workspaceDetail: (id: string) => `/app/workspaces/${id}`,
  workspaceConversations: (id: string) => `/app/workspaces/${id}/conversations`,
  conversationDetail: (wid: string, cid: string) =>
    `/app/workspaces/${wid}/conversations/${cid}`,
};
```

Không hard-code string route trong JSX, luôn dùng `ROUTES`.

### 2.3. API endpoints constants

File `client/lib/api-endpoints.ts`:

- Map đến backend FastAPI:

```ts
export const API_ENDPOINTS = {
  health: "/health",
  me: "/api/me",
  workspaces: "/api/workspaces",
  workspaceDetail: (id: string) => `/api/workspaces/${id}`,
  documents: (workspaceId: string) => `/api/workspaces/${workspaceId}/documents`,
  uploadDocuments: (workspaceId: string) =>
    `/api/workspaces/${workspaceId}/documents/upload`,
  conversations: (workspaceId: string) =>
    `/api/workspaces/${workspaceId}/conversations`,
  messages: (conversationId: string) =>
    `/api/conversations/${conversationId}/messages`,
};
```

Agent không viết `/api/...` inline.

### 2.4. Query keys (React Query)

File `client/lib/query-keys.ts`:

- Công thức: mỗi “domain” có object với các hàm nhỏ:

```ts
export const workspaceKeys = {
  all: ["workspaces"] as const,
  list: () => [...workspaceKeys.all, "list"] as const,
  detail: (id: string) => [...workspaceKeys.all, "detail", id] as const,
};

export const documentKeys = {
  list: (workspaceId: string) =>
    ["documents", "list", workspaceId] as const,
};

export const conversationKeys = {
  list: (workspaceId: string) =>
    ["conversations", "list", workspaceId] as const,
  messages: (conversationId: string) =>
    ["messages", "list", conversationId] as const,
};
```

Pattern:
- Không tự tạo `queryKey` inline, luôn dùng helper từ file này.

### 2.5. Domain constants

File `client/lib/constants.ts`:

- Sync với server (roles, status) để tránh mismatch:

```ts
export const MESSAGE_ROLES = {
  user: "user",
  ai: "ai",
} as const;

export const DOCUMENT_STATUS = {
  pending: "pending",
  parsed: "parsed",
  ingested: "ingested",
  error: "error",
} as const;
```

Không dùng `"user"` / `"ai"` / `"pending"` inline.

---

## 3. Core infrastructure: providers & clients

### 3.1. Supabase client wrapper

File `client/lib/supabase-client.ts`:

- Trách nhiệm:
  - Export một supabase client singleton cho browser.
  - Dùng `createClient(SUPABASE_URL, SUPABASE_ANON_KEY)` từ `@supabase/supabase-js`.
- Không gọi `createClient` ở các nơi khác.

### 3.2. Auth helper (dev token + Supabase session)

File `client/lib/auth.ts`:

- Trách nhiệm:
  - Abstract cách lấy JWT để gọi backend:
    - Nếu đang dùng Supabase Auth (đã login) → lấy access_token từ session.
    - Nếu dev token mode → lấy token từ localStorage (vd key `dev_jwt_token`).
- Interface:

```ts
export async function getAccessToken(): Promise<string | null>;
export function setDevToken(token: string): void;
export function clearDevToken(): void;
```

Agent:
- Không đọc localStorage trực tiếp trong components (trừ UI nhập token); luôn sử dụng helper.

### 3.3. API client (fetch wrapper)

File `client/lib/api-client.ts`:

- Trách nhiệm:
  - Wrap `fetch` với:
    - Base URL: `API_BASE_URL` từ config.
    - Default headers (JSON).
    - Authorization header `Bearer <token>` lấy từ `getAccessToken()`.
  - Xử lý:
    - `response.ok` false → throw error chuẩn (`{status, message, body}`).

Design:
- `apiFetch<T>(path: string, options?: RequestInit): Promise<T>` để parse JSON typed.
- For upload (multipart):
  - Không set `Content-Type` manually (để browser tự set).
  - Dùng overload/option cho `FormData`.

Agent sử dụng:
- Trong hooks, dùng `apiFetch` + React Query. Không dùng `fetch` thô.

### 3.4. React Query client & provider

File `client/lib/query-client.tsx`:

- Khởi tạo `QueryClient` với options default:
  - `staleTime` hợp lý (vd 30s–60s) cho list.
  - `retry` = 1–2 lần cho lỗi network nhẹ (optional).
- Xuất component `ReactQueryProvider`:

```tsx
export function ReactQueryProvider({ children }: { children: ReactNode }) {
  // wraps QueryClientProvider + maybe ReactQueryDevtools in dev
}
```

### 3.5. App-level providers

Trong `client/app/layout.tsx`:

- Bọc app với:
  - Theme provider (nếu shadcn hỗ trợ theme).
  - `ReactQueryProvider`.
  - Auth context (optional nếu cần).

Design doc chỉ yêu cầu:
- Có 1 file `client/app/providers.tsx` (hoặc tương đương) để gom provider:

```tsx
// app/providers.tsx (pseudo)
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ReactQueryProvider>
      {/* shadcn ThemeProvider, Toaster, etc. */}
      {children}
    </ReactQueryProvider>
  );
}
```

`app/layout.tsx` chỉ import `AppProviders`.

---

## 4. Styling system design

### 4.1. Tailwind config

- `tailwind.config.js`:
  - Extend theme với CSS variables từ tokens.
  - Khai báo content paths include `app`, `components`, `features`, `lib`.

Design tokens:
- File `client/styles/tokens.css`:
  - Định nghĩa `:root` variables (background, foreground, primary, border, radius, spacing base…).

Example (conceptual, không cần copy y nguyên):

```css
:root {
  --radius-sm: 0.25rem;
  --radius-md: 0.5rem;
  --radius-lg: 0.75rem;

  --color-bg: 255 255 255;
  --color-bg-muted: 248 250 252;
}
```

Tailwind mapping:
- Trong `tailwind.config.js`, map `borderRadius` và `colors` đến các biến này.

### 4.2. shadcn/ui integration

- Setup theo docs shadcn/ui:
  - Thêm `components/ui` folder chứa component shadcn đã generate (Button, Input, Dialog, Sheet, Card, Skeleton, Toast, ScrollArea).
- Design rule:
  - Không thêm UI primitive mới ở nơi khác; nếu cần component base, đặt vào `components/ui` hoặc `components/layout`.

### 4.3. Layout components

Tạo base layout components trong `client/components/layout/`:

- `AppShell` – khung toàn bộ app (sidebar + header + content).
- `PageContainer` – wrapper cho nội dung page (padding, max-width).
- `PageHeader` – tiêu đề + actions (button create).

Design rule:
- Mọi page trong `(app)` group nên dùng `PageContainer`, `PageHeader` để UI consistent.

---

## 5. Features design (workspaces, documents, conversations, messages)

### 5.1. Auth feature (dev-mode + optional login)

Folder: `client/features/auth/`

Sub-files:
- `components/DevTokenForm.tsx` – form đơn giản:
  - Input text area cho JWT token.
  - Button “Save token”.
  - Gọi `setDevToken` từ `lib/auth`.
- `hooks/useRequireAuth.ts`:
  - Hook để check nếu không có token thì redirect `/login`.
  - Logic:
    - Trong client component, check `getAccessToken()` (async → có thể wrap qua state/hook).
    - Nếu không có token → `router.push(ROUTES.login)`.

Page:
- `app/(auth)/login/page.tsx`:
  - Render DevTokenForm.
  - Option: nếu implement Supabase login UI, thêm form email/password tại đây.

### 5.2. Workspaces feature

Folder: `client/features/workspaces/`

Sub-files:
- `api/workspaces.ts`:
  - `fetchWorkspaces()`, `createWorkspace(payload)`, `fetchWorkspaceDetail(id)`.
  - Dùng `apiFetch` + `API_ENDPOINTS`.
- `hooks/useWorkspaces.ts`:
  - `useWorkspacesList()` – `useQuery({ queryKey: workspaceKeys.list(), queryFn: fetchWorkspaces })`.
  - `useCreateWorkspace()` – `useMutation` + `queryClient.invalidateQueries(workspaceKeys.list())`.
- `components/WorkspaceList.tsx` – presentational:
  - Nhận props `workspaces` + loading/error flags.
- `components/CreateWorkspaceDialog.tsx`:
  - Form (name, description) + dùng `useCreateWorkspace`.

Pages:
- `app/(app)/workspaces/page.tsx`:
  - Client component.
  - Dùng `useWorkspacesList`.
  - Display `WorkspaceList` + `CreateWorkspaceDialog`.

### 5.3. Documents feature

Folder: `client/features/documents/`

Sub-files:
- `api/documents.ts`:
  - `fetchWorkspaceDocuments(workspaceId)`.
  - `uploadDocuments(workspaceId, files: FileList)` – xây `FormData` + `apiFetch`.
- `hooks/useDocuments.ts`:
  - `useWorkspaceDocuments(workspaceId)`.
  - `useUploadDocuments(workspaceId)`.
- `components/DocumentsTable.tsx`:
  - Hiển thị list documents (title, status, createdAt).
- `components/UploadDocumentsForm.tsx`:
  - Input file (multiple).
  - On submit → call `useUploadDocuments` mutation.
  - Xử lý lỗi R2 (500) → show message.

Pages:
- `app/(app)/workspaces/[workspaceId]/page.tsx`:
  - Layout detail workspace.
  - Use:
    - `useWorkspaceDocuments(workspaceId)` để load list.
    - `UploadDocumentsForm`.

### 5.4. Conversations feature

Folder: `client/features/conversations/`

Sub-files:
- `api/conversations.ts`:
  - `fetchConversations(workspaceId)`.
  - `createConversation(workspaceId, payload)`.
- `hooks/useConversations.ts`:
  - `useConversationList(workspaceId)`.
  - `useCreateConversation(workspaceId)`.
- `components/ConversationList.tsx`:
  - Hiển thị list.
  - Click item → push router tới conversation detail.
- `components/CreateConversationForm.tsx`.

Pages:
- `app/(app)/workspaces/[workspaceId]/conversations/page.tsx`:
  - Show list + create.

### 5.5. Messages / Chat feature

Folder: `client/features/messages/`

Sub-files:
- `api/messages.ts`:
  - `fetchMessages(conversationId)`.
  - `sendMessage(conversationId, content)`.
- `hooks/useMessages.ts`:
  - `useMessageList(conversationId)`.
  - `useSendMessage(conversationId)`:
    - `useMutation` → on success, `invalidateQueries(conversationKeys.messages(conversationId))`.
- `components/ChatMessageList.tsx`:
  - Hiển thị messages, style theo `MESSAGE_ROLES`.
- `components/ChatInput.tsx`:
  - Textarea + button send.
  - On submit → call `useSendMessage`.

Page:
- `app/(app)/workspaces/[workspaceId]/conversations/[conversationId]/page.tsx`:
  - Dùng `useMessageList` + `ChatMessageList` + `ChatInput`.
  - Loading khi gửi (disable button).

---

## 6. Navigation & layout wiring

### 6.1. App Router groups

Sử dụng route groups:

- `(auth)` cho login/dev token.
- `(app)` cho phần app chính (cần auth).

Design:
- `app/(auth)/layout.tsx` – layout đơn giản cho login page.
- `app/(auth)/login/page.tsx` – DevTokenForm + optional Supabase login.
- `app/(app)/layout.tsx`:
  - Wrap với `AppShell`, `useRequireAuth`.
  - Render sidebar (link tới routes workspace).

### 6.2. Sidebar workspace list

Option (Phase 1):
- Sidebar có thể chỉ có link “Workspaces” chung, không cần hiển thị tất cả workspace (đơn giản).
- Nếu muốn advanced:
  - Sidebar gọi `useWorkspacesList` để render list workspace và nav tới workspace detail.

---

## 7. Error handling & UX

### 7.1. Network / server errors

- ở `api-client.ts`, nếu `!response.ok`:
  - Parse JSON nếu có (`{ detail: string }` từ server) → throw error object.
- Ở hooks:
  - React Query `onError`:
    - Gửi error tới toast component (shadcn).
- Ở UI:
  - Mỗi page có state:
    - `isLoading` → show skeleton/list skeleton.
    - `isError` → show “Retry” button.

### 7.2. Auth errors (401)

- Nếu API trả 401:
  - Trong `api-client`, detect `status === 401` →:
    - Clear dev token (nếu có).
    - Optional: broadcast sự kiện global (vd set một `isAuthError` state qua context).
  - Ở app shell:
    - Nếu detect auth error global → redirect `/login`.

---

## 8. Testing & DX (high-level)

### 8.1. Manual E2E

- Quy ước minimal để agent/tester:
  1. Start backend (Phase 1) với Supabase DSN + JWT secret ok.
  2. Start client: `cd client && npm run dev`.
  3. Truy cập:
     - `/login` → nhập dev token.
     - `/app/workspaces` → tạo workspace, upload doc, tạo conversation, chat.

### 8.2. Future automated tests (not required Phase 1)

- Có thể thêm:
  - Playwright / Cypress test cho flows trên.
  - Unit test hooks (React Query) bằng MSW.

---

## 9. Extension points for Phase 2/3

Thiết kế hiện tại phải cho phép:

- Thêm feature:
  - `features/parsing/` – xem job status, hiển thị `docai_full_text`.
  - `features/rag/` – hiển thị citations, lọc theo document.
- Thêm route:
  - `/app/workspaces/[workspaceId]/documents/[documentId]` – chi tiết document.
- Reuse:
  - `api-client`, `query-keys`, `constants` không bị thay đổi mạnh, chỉ mở rộng.

Agent coding Phase 2/3 phải đọc file này + requirements client, sau đó thêm module mới theo cùng pattern (feature-first, shared lib). 

