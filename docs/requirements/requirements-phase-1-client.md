# Phase 1 – Client (Next.js) Requirements

Mục tiêu: đặc tả chi tiết cho web client Phase 1, dùng Next.js + Tailwind + shadcn/ui + TanStack Query + Supabase Auth, bám theo backend Phase 1 đã có.

File này là **đầu vào cho agent coding**, không chứa code, chỉ quy định:
- Tech stack, setup best practice (theo docs Next.js / TanStack Query / supabase-js mới).
- Cấu trúc folder client, pattern reuse, triết lý React.
- Flow UI tương ứng với API Phase 1.
- Quy ước constants, styling system, naming để agent khác code ổn định.

---

## 1. Tech stack & phiên bản

- **Framework**: Next.js (App Router, `app/` directory), TypeScript.
  - Dùng create-next-app mới nhất, App Router mặc định.
- **UI & styling**:
  - Tailwind CSS (utility-first).
  - shadcn/ui (dựa trên Radix + Tailwind) cho components cơ bản (Button, Input, Dialog, Sheet, Table, Skeleton, Toast).
  - Hệ thống design tokens (color, spacing, radius, typography) cấu hình trong `tailwind.config` + một file tokens riêng.
- **Data fetching / server state**:
  - TanStack Query v5 (`@tanstack/react-query`), dùng cho logic gọi API backend.
  - Chỉ dùng React Query cho **server state** (workspaces, documents, conversations, messages), tránh tự triển khai caching thủ công.
- **Supabase Auth**:
  - `@supabase/supabase-js` v2 (client-side auth).
  - Dùng access token Supabase để gọi backend Phase 1 (đặt vào header `Authorization: Bearer <token>`).
  - Phase 1: không cần build full auth flow phức tạp, nhưng cần:
    - Hoặc basic login màn hình (email/password) dùng supabase-js.
    - Hoặc “Dev token mode”: cho phép developer paste access token JWT (lưu vào localStorage) để test.
- **Form**:
  - Có thể dùng `react-hook-form` + `@hookform/resolvers` (không bắt buộc ở requirements, nhưng khuyến nghị nếu form phức tạp hơn).

**Yêu cầu environment** (client side):
- `NODE_VERSION` >= 20 (phù hợp supabase-js & tooling).
- `NEXT_PUBLIC_API_BASE_URL` – base URL backend FastAPI (ví dụ `http://127.0.0.1:8000`).
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` – cho Supabase JS.
- Không dùng secret server-side của Supabase bên client; chỉ public anon key.

---

## 2. Triết lý & pattern React cho client

Agent coding phải tuân theo các nguyên tắc sau:

### 2.1. Feature-first + clear boundaries

- Organize theo **feature/module**, không theo layer thuần:

```text
client/
  app/                  # Next.js App Router
  features/             # Feature modules (workspaces, documents, chat,...)
    auth/
    workspaces/
    documents/
    conversations/
    messages/
  components/           # Reusable presentational/components ui không gắn feature
  lib/                  # API client, config, hooks shared (supabase, react-query, routes,...)
  styles/               # Global styles, tokens
```

- Mỗi feature chứa:
  - `components/` – UI components riêng cho feature.
  - `hooks/` – hooks React Query / hooks logic.
  - `api/` – hàm gọi API (fetch, axios… nhưng recommended fetch + React Query).
  - `types/` – TS types cho responses/requests riêng (nếu không dùng shared type).

### 2.2. Server state vs UI state

- Server state (data từ backend) luôn quản lý bằng **React Query**:
  - Không tự dùng `useState` cho dữ liệu fetch từ API (trừ trường hợp rất nhỏ, tạm thời).
  - Mọi list, detail, form submit liên quan backend đều đi qua `useQuery`, `useMutation`.
- UI state (modal open, tab selected, input text…) dùng `useState`/`useReducer` hoặc các hooks đơn giản.
- Không đưa state management framework khác (Redux, Zustand) vào Phase 1.

### 2.3. Constants & magic strings

- **Không hard-code** string quan trọng inline trong JSX/logic:
  - Route paths.
  - API endpoints.
  - Query keys cho React Query.
  - Status text, role (`user`, `ai`) nếu dùng client-side map.
- Tất cả đưa vào file constants, ví dụ:
  - `lib/routes.ts` – đường dẫn client (`/workspaces`, `/workspaces/[id]/conversations/...`).
  - `lib/api-endpoints.ts` – path backend (`/api/workspaces`, `/api/...`).
  - `lib/query-keys.ts` – hàm trả query key chuẩn (vd `workspaceKeys.list()`, `conversationKeys.messages(id)`).
  - `lib/constants.ts` – constants chung (roles, document status, job status – sync với server).

---

## 3. Cấu trúc folder client (Phase 1)

Yêu cầu high-level:

```text
client/
  app/
    layout.tsx
    page.tsx                 # landing / redirect
    (auth)/
      login/
        page.tsx             # Login + dev token mode
    (app)/
      layout.tsx             # main app layout (sidebar/topbar)
      workspaces/
        page.tsx             # list workspaces
      workspaces/
        [workspaceId]/
          page.tsx           # workspace detail + documents list
          conversations/
            page.tsx         # list conversations
            [conversationId]/
              page.tsx       # chat UI

  features/
    auth/
    workspaces/
    documents/
    conversations/
    messages/

  components/
    ui/                      # shadcn/ui re-exports + wrappers
    layout/                  # app shell, sidebar, header...

  lib/
    api-client.ts            # fetch wrapper, baseURL, error handling
    supabase-client.ts       # createSupabaseClient for browser
    auth.ts                  # helpers về token lấy từ Supabase / dev mode
    query-client.ts          # init QueryClient + provider
    routes.ts
    api-endpoints.ts
    query-keys.ts
    config.ts                # đọc env NEXT_PUBLIC_*

  styles/
    globals.css
    tokens.css               # hoặc tương đương: layer base tokens
```

**Lưu ý cho agent coding**:
- Không tạo API client chỗ khác ngoài `lib/api-client.ts`.
- Không gọi Supabase trực tiếp trong components UI (ngoại trừ phần login/signup auth feature). Mọi call backend app → dùng `api-client` + JWT Supabase.
- App Router:
  - Dùng `app/` directory, layout.tsx shared layout.
  - Ưu tiên **Server Components** cho page/layout khi chỉ render UI; nhưng **Client Components** khi cần hooks (React Query, Supabase client, form).

---

## 4. Styling system & UI

### 4.1. Tailwind + shadcn/ui setup yêu cầu

- Tailwind config chuẩn:
  - Định nghĩa theme (colors, spacing, font, radius) trong `tailwind.config.js`.
  - Dùng `@layer base` trong `globals.css` hoặc `tokens.css` để set CSS variables (vd `--color-bg`, `--color-primary`).
- shadcn/ui:
  - Dùng `components/ui` để chứa components import từ shadcn (Button, Input, Dialog, Sheet, ScrollArea, Card, Tabs, Toast, Skeleton).
  - Không sửa trực tiếp node_modules; mọi customization trong `components/ui/*`.

### 4.2. Design tokens & reusable styles

- Phải có một file tokens:
  - Ví dụ `styles/tokens.css`:
    - `:root { --color-bg: ...; --radius-lg: ...; }`.
  - Tailwind sử dụng tokens qua config (vd `borderRadius.lg = 'var(--radius-lg)'`).
- Quy ước:
  - Không dùng màu hex hard-code trong JSX (`className="text-[#123456]"`), chỉ dùng class Tailwind mapping tokens (`text-primary`, `bg-muted`).
  - Không lặp lại pattern layout dài; trích thành components (vd `<PageContainer>`, `<SectionHeader>`).

### 4.3. Layout / navigation

- Main layout:
  - App shell: header (current user email, logout), sidebar (danh sách workspace, link).
  - Content area scrollable, responsive.
- Loading & error:
  - Mỗi page có state loading/error rõ ràng, dùng Skeleton / Alert từ shadcn/ui.
  - Không để “blank screen” khi React Query đang loading.

---

## 5. API integration & auth (Phase 1)

### 5.1. Supabase Auth usage

- Client sử dụng:
  - `createClient(NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY)`.
- Auth flows Phase 1 (tùy chọn nhưng phải đặc tả):
  - **Option A (prefer)**: UI login email/password:
    - Dùng supabase-js `signInWithPassword` để lấy session + access token.
    - Access token lưu trong `localStorage` hoặc `supabase.auth` session; backend API gọi với Bearer token.
  - **Option B (dev mode)**: ô nhập “Dev JWT token”:
    - Developer paste token Supabase lấy từ Dashboard.
    - Lưu vào `localStorage` (`dev_jwt_token`), API client dùng header `Authorization: Bearer <token>`.

Requirements:
- Tối thiểu phải support được **dev mode** để agent khác có thể test không cần build full auth UI.
- Nếu implement thêm login UI, phải tách code trong feature `features/auth/` (components, hooks, api).

### 5.2. API client pattern

- Một chỗ duy nhất `lib/api-client.ts`:
  - Config `baseURL` từ `NEXT_PUBLIC_API_BASE_URL`.
  - Hàm `apiFetch(path, options)`:
    - Tự gắn header `Authorization` lấy từ:
      - Supabase session hiện tại, hoặc
      - Dev token trong localStorage.
    - Xử lý JSON parsing, error (throw object standardized).
- Không dùng axios nếu không cần; fetch chuẩn là đủ.
- React Query hooks được build trên `apiFetch`, không gọi fetch trực tiếp trong components.

---

## 6. Flows UI Phase 1 cần có

Các flow tương ứng API backend Phase 1:

1. **Health & profile check**
   - Khi app load (sau khi có token): gọi `/health` (optional) và `/api/me`.
   - Hiển thị user id/email ở header hoặc menu.

2. **Workspaces**
   - Screen list:
     - GET `/api/workspaces`.
     - Hiển thị danh sách (name, description, created_at).
     - Nút “Create workspace” → form (name, description) → POST `/api/workspaces` → invalidate list query.
   - Workspace detail:
     - GET `/api/workspaces/{workspace_id}` hoặc reuse data list.
     - Section “Documents in this workspace” (xem mục 3).

3. **Documents (upload & list)**
   - Trong workspace detail:
     - List documents: GET `/api/workspaces/{workspace_id}/documents`.
     - Hiển thị title, status, created_at.
   - Upload flow:
     - Form upload (multi file) → POST `/api/workspaces/{workspace_id}/documents/upload` (multipart).
     - Điều kiện R2:
       - Nếu R2 chưa config (backend trả lỗi phù hợp), UI hiện message rõ ràng, không crash.
     - Sau khi upload thành công:
       - Show toast thành công + refresh list documents.

4. **Conversations & messages (chat khung)**
   - Conversations list:
     - GET `/api/workspaces/{workspace_id}/conversations`.
     - Form create conversation (title) → POST `/api/workspaces/{workspace_id}/conversations`.
   - Conversation detail (chat UI):
     - GET `/api/conversations/{conversation_id}/messages`.
     - Show messages với phân tách role (`user` vs `ai`) bằng style khác nhau.
     - Input box gửi message:
       - POST `/api/conversations/{conversation_id}/messages`.
       - Hiển thị ngay message user và message AI mock `"Engine chưa kết nối"`.
     - Loading state khi gửi, disable input tạm.

5. **Basic error handling**
   - Nếu token invalid (401 từ API):
     - Redirect về `/login` hoặc hiện modal yêu cầu nhập token lại.
   - Error khác (network, 5xx):
     - Show toast + state error trong page, không “die” toàn app.

---

## 7. DX & friendly với agent coding

Yêu cầu giúp agent khác dễ code, dễ mở rộng:

- Có file **README client** riêng (sẽ viết sau trong implementation) mô tả:
  - Cách start client: `cd client && pnpm dev` (hoặc npm/yarn).
  - Cách config env.
  - Các feature folder và entry chính.
- Code style:
  - Dùng TypeScript strict; mọi API function đều có type.
  - Components nhỏ, pure, không làm quá nhiều việc.
  - Hooks `useXxx` đặt trong `features/*/hooks`.
- Reuse:
  - Không lặp nhiều UI pattern (form, list, loading) – nếu thấy lặp, refactor thành component/hook shared.
- Không override kiến trúc tổng (app router, lib folder); nếu cần mở rộng Phase 2, Phase 3, thêm feature modules mới.

---

## 8. Out of scope (Phase 1 client)

- Chưa cần:
  - UI cho Document AI result, RAG answer detail.
  - Realtime updates (Supabase realtime).
  - Complex theming (dark mode optional).
  - Deep analytics/tracking.
- Nhưng khi thiết kế files & pattern, phải để cửa cho:
  - Thêm feature Phase 2 (parser, job status, document detail viewer).
  - Thêm feature Phase 3 (RAG answers, citations viewer, filters).

