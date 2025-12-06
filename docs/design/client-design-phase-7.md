# client-design-phase-7 – Explainable RAG & Raw Document Viewer (Summary for Frontend)

Mục tiêu: mô tả **những thay đổi ở API/contract** mà team client cần biết để:
- Hiển thị text thô của document sau khi parse.
- Hiển thị câu trả lời AI với “bong bóng số” citations per section.
- Map mỗi citation tới đúng đoạn text nguồn trong viewer.

File này bổ sung trên nền:
- `docs/design/client-design.md`
- `docs/design/phase-1-client-design.md`
- `docs/design/client-design-phase-5.md`

---

## 1. Phạm vi cho client (Phase 7)

Trong Phase 7, từ góc nhìn client:

- **Có thêm 1 API mới** để lấy text thô của document:
  - `GET /api/workspaces/{workspace_id}/documents/{document_id}/raw-text`.
- **Message AI** trong chat:
  - Vẫn có `content` là một string như cũ.
  - `metadata` (JSON) được mở rộng thêm:
    - `metadata.sections`: list các section (đoạn trả lời) với citations.
    - `metadata.citations`: list citations flatten (tổng hợp tất cả citations từ sections).
- WebSocket events `message.created` / `message.status_updated`:
  - Payload vẫn giống Phase 5, chỉ khác là nếu backend đã tính được sections/citations thì `message.metadata` sẽ có thêm các field mới nói trên.

Không thay đổi:
- Cách auth (Supabase JWT).
- Các REST endpoint hiện tại cho workspaces/documents/conversations/messages.
- Cấu trúc fields cơ bản của `Message` (id, role, content, status, metadata, created_at).

---

## 2. API contracts – những gì client cần biết

### 2.1. Viewer text thô – Documents

**Endpoint mới**

- `GET /api/workspaces/{workspace_id}/documents/{document_id}/raw-text`
  - Mục đích: lấy text thô (đã OCR) của document, đã được server cắt thành các **segments** để hiển thị và dùng làm nguồn citations.
  - Auth:
    - Dùng Supabase JWT (giống các API khác).
    - User phải là owner của workspace (server đã enforce như các documents API khác).

**Request**

- Method: `GET`
- Path params:
  - `workspace_id`: UUID của workspace hiện tại.
  - `document_id`: UUID document.
- Headers:
  - `Authorization: Bearer <JWT>` (như các API khác).

**Response (200 OK)**

```jsonc
{
  "document_id": "e1b9e4c1-...-...",
  "workspace_id": "a2f3b4d5-...-...",
  "status": "parsed",            // hoặc "ingested"
  "segments": [
    {
      "segment_index": 0,
      "page_idx": 0,             // hiện tại luôn 0 (chưa map page thật)
      "text": "Đoạn text 1..."
    },
    {
      "segment_index": 1,
      "page_idx": 0,
      "text": "Đoạn text 2..."
    }
  ]
}
```

**Error cases**

- `404 Not Found`:
  - Document không thuộc workspace hoặc không tồn tại.
- `409 Conflict`:
  - Document chưa parse xong (`status = 'pending'` hoặc `status = 'error'`).
  - Hoặc `docai_full_text` rỗng (parse lỗi, pipeline chưa đúng).

> Gợi ý logic client (ở mức contract):  
> - Khi user click document trong UI, client có thể gọi endpoint này để render viewer text thô theo thứ tự `segment_index`.  
> - Mỗi `segment` có thể gắn `data-segment-index={segment_index}` trong DOM để scroll/highlight dựa trên citations.

---

### 2.2. Chat messages – cấu trúc message AI & metadata

**Endpoint hiện tại (không đổi)**:

- `POST /api/conversations/{conversation_id}/messages`
  - Request body từ client **không thay đổi**:
    ```json
    {
      "content": "Câu hỏi của người dùng..."
    }
    ```

**Response (201)** – như Phase 3/5:

- Backend vẫn trả về `MessageListResponse` chứa:
  - Message `user` (role=`user`, status=`done`).
  - Message `ai` (role=`ai`, status=`pending`) để client show placeholder.
- Sau đó, khi background job gọi RAG xong:
  - Message `ai` sẽ được cập nhật (qua REST khi refetch hoặc qua WebSocket event `message.status_updated`).

**Cấu trúc `Message` từ API/WS** (nhắc lại, bổ sung phần metadata):

```jsonc
{
  "id": "uuid",
  "conversation_id": "uuid",
  "workspace_id": "uuid",
  "role": "ai" | "user",
  "content": "Nội dung trả lời cuối cùng...",
  "status": "pending" | "running" | "done" | "error",
  "created_at": "2025-12-06T12:00:00Z",
  "metadata": {
    // Phase 3: có thể có "citations": [...] (kiểu cũ, không structured)
    // Phase 7: thêm 2 field dưới đây khi là message AI
    "sections": [
      {
        "text": "Đoạn trả lời 1...",
        "citations": [
          {
            "document_id": "uuid-hoặc-null",
            "segment_index": 15,
            "page_idx": 2,
            "snippet_preview": "Đoạn text nguồn ngắn..."
          }
        ]
      },
      {
        "text": "Đoạn trả lời 2...",
        "citations": []
      }
    ],
    "citations": [
      {
        "document_id": "uuid-hoặc-null",
        "segment_index": 15,
        "page_idx": 2,
        "snippet_preview": "Đoạn text nguồn ngắn..."
      }
      // ... tất cả citations từ mọi section, flatten
    ]
  }
}
```

Lưu ý:
- `metadata` có thể là `null` hoặc thiếu các field này trong các trường hợp:
  - Message `user`.
  - Message `ai` cũ (trước khi Phase 7 được deploy).
  - LLM trả JSON không hợp lệ, backend fallback sang plain text (không có sections).
- `content` luôn có đầy đủ câu trả lời dạng text (join các `sections[i].text`); client không bị bắt buộc phải sử dụng `sections` để hiển thị nếu không muốn.

---

### 2.3. WebSocket events – phần liên quan đến metadata mới

Phase 5 đã có:
- `message.created`
- `message.status_updated`

Phase 7 chỉ mở rộng **payload**:

**`message.created`**

- Cho message user / ai placeholder:
  - Format không đổi, `metadata` vẫn có thể `null`.

**`message.status_updated`** (khi message AI xong)

Hiện tại payload sẽ giống:

```jsonc
{
  "workspace_id": "uuid",
  "conversation_id": "uuid",
  "message_id": "uuid",
  "status": "done",
  "content": "Toàn bộ câu trả lời (text)...",
  "metadata": {
    "sections": [ /* giống cấu trúc ở trên */ ],
    "citations": [ /* flatten */ ]
  }
}
```

> Từ góc độ client:  
> - Nếu đã subscribe WS và đang giữ local state messages:
>   - Có thể dùng `message_id` để tìm message AI tương ứng, update `status`, `content` và `metadata`.
>   - `metadata.sections` có thể dùng để render từng đoạn trả lời + bong bóng citations.  
>   - `metadata.citations` có thể dùng nếu muốn hiển thị danh sách nguồn tổng kết ở cuối câu trả lời.

---

## 3. Logic mapping client có thể dựa vào (ở mức contract)

Mục tiêu: team client hiểu **quan hệ dữ liệu** để quyết định cách render, không cần chi tiết backend implement.

### 3.1. Quan hệ giữa citations và viewer segments

- Một citation trong `metadata.sections[*].citations[*]` có:
  - `document_id`: UUID document chứa đoạn nguồn (server tự tính, không phải do LLM bịa).
  - `segment_index`: segment trong document raw text viewer (index trong mảng `segments` backend trả).
  - `page_idx`: page index (hiện tại chủ yếu là placeholder, có thể dùng nếu cần).
  - `snippet_preview`: đoạn text nguồn ngắn mà backend đề xuất.

- Viewer raw text:
  - Lấy từ `GET /documents/{document_id}/raw-text`:
    - `segments[segment_index]` chính là đoạn chi tiết để hiển thị và scroll tới.

=> Mapping logic (conceptual):

1. Để render citation `[n]` trong câu trả lời:
   - Đọc `citation.document_id` và `citation.segment_index`.
   - Nếu viewer của `document_id` đã có `segments` trong client:
     - Tìm segment tương ứng trong array `segments`.
2. Khi hover:
   - Có thể show `snippet_preview` (nếu có) hoặc `segments[segment_index].text` (cắt ngắn client-side) trong popup.
3. Khi click:
   - Nếu viewer đang hiển thị `document_id` này:
     - Scroll tới DOM element gắn `data-segment-index = segment_index` và highlight.
   - Nếu chưa hiển thị:
     - Client có thể (tùy thiết kế) mở viewer với document tương ứng, gọi `/raw-text` nếu chưa load, rồi scroll khi data đã sẵn sàng.

### 3.2. Độ tin cậy

- Backend:
  - Dùng LLM để sinh `sections[*].text`.
  - Sau đó tự tính `citations` bằng cách so khớp text của section với các segments trong workspace (không dùng ID do LLM bịa).
- Độ chính xác:
  - Một citation trỏ tới **đoạn** (segment) đại diện cho nguồn chính của phần trả lời đó.
  - Không đảm bảo 100% từng câu luôn khớp hoàn hảo, nhưng đủ để người dùng đọc đoạn nguồn và thấy được bối cảnh.
- `snippet_preview` giúp tăng độ tin cậy UX:
  - Nội dung snippet nên tương ứng với text trong segment.
  - Nếu snippet và segment không khớp, client có thể ưu tiên hiển thị segment text để người dùng tự đánh giá.

---

## 4. Tóm tắt các thay đổi cho client

1. **API mới**:
   - `GET /api/workspaces/{workspace_id}/documents/{document_id}/raw-text`
     - Trả `segments[]` (segment_index, page_idx, text) để hiển thị document text thô.

2. **Message AI (REST + WebSocket)**:
   - Vẫn có `content` như cũ (text).
   - `metadata` có thể chứa:
     - `sections`: list section với `text` + `citations[]`.
     - `citations`: list citations flatten.

3. **Mapping citations → nguồn**:
   - Mỗi `citation` có `document_id` + `segment_index` + `snippet_preview`.
   - Client có thể dùng `segment_index` để scroll tới đúng đoạn trong viewer đã load raw text.

4. **Backward-compat**:
   - Nếu server không trả `metadata.sections` (ví dụ message cũ hoặc lỗi parse JSON), client vẫn dùng `content` để hiển thị như hiện tại.
   - Khi field mới xuất hiện, client có thể dần dần dùng để nâng UX (sections, bong bóng citations, scroll tới đoạn nguồn).

File này chỉ mô tả contract; team client có thể chọn cách tổ chức state (React Query, Zustand, Redux, v.v.) và UI cụ thể dựa trên các field nói trên.
