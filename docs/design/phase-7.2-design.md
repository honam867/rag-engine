# rag-engine – Tech Design (Phase 7.2: ID‑Based Citations như NotebookLM)

> Mục tiêu: nâng Explainable RAG từ mức “dự đoán nguồn” (Phase 7/7.1) lên mức “theo dấu ID nguồn” giống NotebookLM:
> - Mỗi đoạn text thô (segment) có một ID ổn định.
> - ID này được đưa thẳng vào context khi query RAG.
> - LLM trả về JSON chứa danh sách ID nguồn cho từng section.
> - Backend chỉ việc map ID → `{document_id, segment_index, page_idx, text}`, không còn phải đoán bằng heuristic.

Phase 7.2 **không thay schema DB**, nhưng sẽ:
- Thay đổi cách build `content_list` khi ingest.
- Thay đổi prompt/JSON format trong `RagEngineService.query`.
- Đơn giản hóa mapping citations ở `messages` (dùng ID thay vì text‑matching).
- Cho phép client nhận metadata giàu hơn, chính xác hơn.

---

## 1. Bối cảnh & vấn đề của Phase 7 / 7.1

### 1.1. Những gì Phase 7 / 7.1 đã làm tốt

- Raw text viewer:
  - `/raw-text` dùng Document AI JSON (`text_anchor`) để cắt `segments` bám sát cấu trúc PDF (page/paragraph/line).
- Citation mapping Phase 7.1:
  - Thay vì để LLM bịa `document_id/segment_index`, backend:
    - Build segments từ `docai_full_text` + JSON.
    - So khớp nội dung giữa `section.text` và `segment.text` (token overlap + alignment theo thứ tự).
  - Đảm bảo `document_id` là UUID thật, `segment_index` trỏ vào đúng segment trong viewer.

### 1.2. Hạn chế còn lại (không thể giải quyết bằng heuristic)

- Bản chất Phase 7 / 7.1 vẫn là:
  - “Trả lời xong rồi **đoán ngược** xem câu đó lấy từ đoạn nào”.
  - Dù segmentation đã tốt, text‑matching vẫn có vô số corner case:
    - Câu trả lời dài, paraphrase, nhập nhằng → khó match chính xác.
    - Câu trả lời ngắn (tên người, mã số) → dễ match nhầm vào header chứa nhiều từ chung nhưng lại thiếu từ khóa chính (“Trần Phương”…).
    - Câu hỏi chỉ rõ “trang 3” nhưng thuật toán không dùng `page_idx` của segment.
    - Workspace có nhiều document → dễ nhầm document nếu nội dung giống nhau.
- Việc liên tục “nâng scoring” (thêm rule ưu tiên từ khóa, ưu tiên trang, v.v.) vẫn là heuristic, không thể phủ hết mọi trường hợp.

Kết luận:
- Nếu tiếp tục bám vào text‑matching post‑hoc, Explainable RAG luôn mang tính “dự đoán”.
- Để đạt độ chính xác kiểu NotebookLM, cần chuyển sang **ID‑based citations**: nguồn được track ngay từ lúc context được feed vào LLM.

---

## 2. Mục tiêu Phase 7.2

1. **Segment ID ổn định**
   - Mỗi segment text thô có một ID canonical:
     - Ví dụ: `segment_id = "{document_id}:{segment_index}"`.
   - ID này:
     - Được dùng khi ingest vào RAG‑Anything.
     - Được embed rõ ràng trong context (ví dụ `[SEG=doc:idx]`).

2. **LLM trả JSON với danh sách ID nguồn**
   - `RagEngineService.query` sẽ yêu cầu LLM trả:
     ```json
     {
       "sections": [
         {
           "text": "Đoạn trả lời...",
           "source_ids": ["{document_id}:{segment_index}", "..."]
         }
       ]
     }
     ```
   - LLM **không tự nghĩ ID**:
     - Chỉ được dùng ID xuất hiện trong context (`[SEG=...]`).

3. **Backend mapping = tra ID, không đoán nữa**
   - `messages` API chỉ cần:
     - Parse `source_ids`.
     - Map từng ID sang:
       - `document_id`, `segment_index`, `page_idx`, `snippet`.
   - Text‑matching Phase 7.1 trở thành **fallback** khi LLM không trả ID (JSON lỗi, model quá yếu…).

4. **Client UX kiểu NotebookLM**
   - Mỗi section có thể có nhiều nguồn:
     - Ví dụ: `source_ids = ["docA:5", "docA:6"]` → bong bóng 5 & 6, mỗi cái nhảy đúng đoạn.
   - Bong bóng cho câu “Trần Phương” phải trỏ đúng đoạn chứa “Trần Phương” trong viewer, không bị dừng ở header.

---

## 3. Kiến trúc tổng thể (so với Phase 7/7.1)

### 3.1. RAG ingest & segments

- **Hiện tại**:
  - `ChunkerService.build_content_list_from_document(document_id)`:
    - Build `segments` từ `docai_full_text` (+ JSON).
    - `content_list` gửi vào RAG‑Anything:
      ```python
      {"type": "text", "text": seg["text"], "page_idx": seg["page_idx"]}
      ```
- **Phase 7.2**:
  - Giữ cấu trúc `content_list`, nhưng:
    - Thêm ID vào nội dung text để RAG‑Anything/LightRAG mang theo ID này trong context LLM nhìn thấy.
    - Đề xuất:
      ```python
      segment_id = f"{document_id}:{segment_index}"
      text_with_id = f"[SEG={segment_id}] {seg['text']}"
      content_list.append({
          "type": "text",
          "text": text_with_id,
          "page_idx": seg["page_idx"],
      })
      ```
    - `[SEG=...]` là một prefix dễ parse, LLM vẫn đọc được nội dung phía sau, và backend có thể khớp lại ID này trong context.

### 3.2. Query pipeline

- Không sửa `RagEngineService._get_rag_instance` hay cách gọi `rag.aquery`.
- Chỉ thay đổi:
  - **Prompt**: mô tả rõ format JSON mới và ý nghĩa tag `[SEG=...]`.
  - **Parsing kết quả**: đọc thêm `source_ids` cho từng section.

Ví dụ system prompt cho Phase 7.2:

```text
Trong phần ngữ cảnh, bạn sẽ thấy các đoạn văn bản có tiền tố dạng:

  [SEG={document_id}:{segment_index}] <nội dung đoạn>

- Hãy đọc nội dung như bình thường.
- Khi trả lời, bạn phải trả về JSON hợp lệ với cấu trúc:

{
  "sections": [
    {
      "text": "<đoạn trả lời 1>",
      "source_ids": ["{document_id}:{segment_index}", "..."]
    },
    ...
  ]
}

- Mỗi phần tử trong source_ids phải là một ID xuất hiện trong ngữ cảnh (từ [SEG=...]).
- Không tự bịa ID mới.
- Nếu không chắc, bạn có thể bỏ trống source_ids hoặc trả mảng rỗng cho section đó.
```

### 3.3. Messages / citations

- **Hiện tại (7/7.1)**:
  - `_build_citations_for_sections`:
    - Tải tất cả documents của workspace.
    - Build segments (từ JSON/heuristic).
    - So khớp `section.text` ↔ `segment.text`.
    - Chọn segment tốt nhất cho mỗi section → build `citations`.
- **Phase 7.2**:
  - Với mỗi section:
    - Nếu có `source_ids` trong result của `rag_engine.query`:
      - Parse từng ID:
        - Format chuẩn: `"{document_id}:{segment_index}"`.
      - Với mỗi ID:
        - Tra lại segment tương ứng bằng segmentation Document AI v7.1 (đảm bảo đúng `page_idx` + snippet).
      - Gán `citations` = list mapping từ ID → `{document_id, segment_index, page_idx, snippet_preview}`.
    - Nếu không có `source_ids` (hoặc JSON invalid):
      - Fallback dùng `_build_citations_for_sections` cũ (text‑matching).

> Lưu ý: text‑matching Phase 7.1 không bị xóa, nhưng được hạ xuống thành “plan B” cho trường hợp model không tuân thủ format.

---

## 4. Thiết kế chi tiết theo module

### 4.1. ChunkerService & content_list (ingest)

File: `server/app/services/chunker.py`

- **Thêm helper** (nội bộ, không đổi API public):

```python
def make_segment_id(document_id: str, segment_index: int) -> str:
    return f"{document_id}:{segment_index}"
```

- **Sửa `ChunkerService.build_content_list_from_document`**:
  - Ở đoạn build `segments`:
    - Hiện tại:
      ```python
      segments = build_segments_from_docai(...) or chunk_full_text_to_segments(...)
      content_list = [
          {"type": "text", "text": seg["text"], "page_idx": seg["page_idx"]}
          for seg in segments
      ]
      ```
    - Phase 7.2:
      ```python
      content_list = []
      for seg in segments:
          segment_index = int(seg["segment_index"])
          segment_id = make_segment_id(document_id, segment_index)
          text_with_id = f"[SEG={segment_id}] {seg['text']}"
          content_list.append(
              {
                  "type": "text",
                  "text": text_with_id,
                  "page_idx": seg["page_idx"],
              }
          )
      ```

- **Raw viewer** (`/raw-text`) **không đổi**:
  - Vẫn trả `text` nguyên gốc (không chứa `[SEG=...]`), vì viewer chỉ cần hiển thị text thô.

### 4.2. RagEngineService.query – JSON với source_ids

File: `server/app/services/rag_engine.py`

- **Prompt**:
  - Mở rộng `effective_system_prompt` hiện tại:
    - Thay vì chỉ nói:
      - “trả JSON { sections: [{text}] }”
    - Giờ yêu cầu:
      - `sections[*].text` + `sections[*].source_ids: string[]`.
      - Mỗi `source_id` phải đến từ tag `[SEG=...]` trong context.

- **Parsing kết quả**:
  - Hiện tại:
    ```python
    parsed = json.loads(raw_result)
    sections = [{"text": sec["text"]}, ...]
    answer = "\n\n".join(section["text"] for section in sections)
    ```
  - Phase 7.2:
    ```python
    parsed = json.loads(raw_result)
    sections = []
    for sec in parsed.get("sections", []):
        text_val = sec.get("text")
        source_ids = sec.get("source_ids") or []
        # validate: list of strings
        source_ids_clean = [s for s in source_ids if isinstance(s, str)]
        sections.append({"text": text_val, "source_ids": source_ids_clean})

    answer = "\n\n".join(sec["text"] for sec in sections)
    ```

- **Return value** của `query`:
  - Vẫn là:
    ```python
    {"answer": answer, "sections": sections}
    ```
  - Nhưng giờ mỗi `section` có thể có thêm `source_ids`.

### 4.3. Messages API – mapping source_ids → citations

File: `server/app/api/routes/messages.py`

- **Thay đổi chính trong `_process_ai_message_background`**:
  - Sau khi gọi `rag_engine.query`:
    ```python
    rag_result = await rag_engine.query(...)
    answer = rag_result.get("answer") or ""
    raw_sections = rag_result.get("sections") or []
    ```
  - Thay vì luôn gọi `_build_citations_for_sections` (text‑matching), Phase 7.2:
    - Tách 2 luồng:
      1. **Ưu tiên ID‑based**:
         - Nếu bất kỳ section nào có `source_ids`:
           - Gọi helper mới `_build_citations_from_source_ids(workspace_id, raw_sections)`.
           - Helper này:
             - Thu thập tất cả `{document_id, segment_index}` từ `source_ids`.
             - Với mỗi document_id:
               - Load `docai_full_text` + JSON (dùng lại logic từ 7.1) → build segments.
             - Map từng `source_id` → segment tương ứng:
               - Tìm segment với `segment_index` phù hợp.
               - Lấy `page_idx` + `text` để build `snippet_preview`.
           - Trả về:
             - `sections_with_citations` (gắn citations theo từng section).
             - `citations_flat`.
      2. **Fallback text‑matching**:
         - Nếu tất cả sections đều không có `source_ids` (hoặc JSON parse fail):
           - Gọi lại `_build_citations_for_sections` cũ (giữ nguyên behavior 7.1).

- **Metadata**:
  - Giữ format:
    ```json
    "metadata": {
      "sections": [
        {
          "text": "...",
          "source_ids": ["doc:5", "doc:6"],
          "citations": [
            {
              "document_id": "uuid",
              "segment_index": 5,
              "page_idx": 2,
              "snippet_preview": "..."
            }
          ]
        }
      ],
      "citations": [ /* flatten */ ]
    }
    ```
  - Client cũ:
    - Vẫn có thể dùng chỉ `citations[*]`.
  - Client mới:
    - Có thể hiển thị theo kiểu NotebookLM: mỗi section biết `source_ids` nào liên quan.

---

## 5. Ảnh hưởng tới dữ liệu hiện tại & migration

### 5.1. Documents đã ingest trước 7.2

- Các document đã ingest vào RAG‑Anything **trước** khi thêm `[SEG=...]`:
  - Content trong LightRAG không có tag ID.
  - Khi query, LLM sẽ không thấy `[SEG=...]` trong context → không thể trả `source_ids` đúng.
- Lựa chọn:
  - **Khuyến nghị** (đơn giản, an toàn):
    - Đối với workspace cần Explainable RAG chuẩn 7.2:
      - Tạo workspace mới.
      - Upload lại tài liệu (parse lại, ingest lại).
    - Đánh dấu trong docs Phase 7.2:
      - “Để hưởng lợi đầy đủ từ ID‑based citations, tài liệu cần được ingest sau khi 7.2 deploy.”
  - Tùy chọn nâng cao (có thể phase sau):
    - Viết job xóa RAG storage cho workspace (`RagEngineService.delete_workspace_data`) + re‑ingest từ DB.
    - Nhưng điều này tiềm ẩn rủi ro và vượt scope 7.2 (có thể note TODO).

### 5.2. Behavior với documents cũ

- Documents cũ vẫn có thể:
  - Được query bình thường (RAG vẫn trả lời).
  - Nhưng citations sẽ rơi về **fallback text‑matching** (Phase 7.1) vì context không có `[SEG=...]`.
- Docs Phase 7.2 cần ghi rõ:
  - “Có hai chế độ citations: ID‑based (ưu tiên, yêu cầu ingest mới) và text‑matching fallback (áp dụng cho document cũ hoặc khi model không tuân thủ JSON).”

---

## 6. Ảnh hưởng tới client (overview, chi tiết để ở client-design-7.2)

Tóm tắt thay đổi quan trọng cho client:

1. **Message AI metadata**:
   - Trước:
     - `metadata.sections[*].text`
     - `metadata.sections[*].citations[*]`
   - Sau 7.2:
     - Thêm `metadata.sections[*].source_ids: string[]`.
     - `citations` được build từ `source_ids` khi có.

2. **Bong bóng & mapping**:
   - Bong bóng vẫn dùng `{document_id, segment_index}` để scroll tới `segment` trong `/raw-text` như Phase 7.
   - Tuy nhiên:
     - Ta có thể hiển thị kiểu NotebookLM:
       - Mỗi section hiển thị các bong bóng theo `source_ids` (hoặc theo citations gắn vào section).
       - Một section có thể có 1 hoặc nhiều bong bóng (5, 6, …), mỗi cái map tới một đoạn liên quan.

3. **Backward‑compat**:
   - Nếu server không có `source_ids` (document cũ hoặc JSON lỗi), client vẫn đọc được `citations` như Phase 7/7.1.

---

## 7. Những thứ Phase 7.2 thay thế / hạ cấp (để tracking)

Phase 7.2 **không xóa code ngay**, nhưng thay đổi vai trò:

- `_build_citations_for_sections` (text‑matching) từ Phase 7.1:
  - Trước: luôn chạy để map `section.text` → segment.
  - Sau 7.2: chỉ dùng **như fallback** khi:
    - `sections[*].source_ids` không tồn tại hoặc mảng rỗng cho toàn bộ sections.
    - JSON từ LLM không parse được.
- Thuật toán similarity token‑overlap + monotone alignment:
  - Vẫn giữ để fallback có chất lượng tốt hơn Phase 7 gốc.
  - Nhưng không còn là “đường chính” cho citations.

Việc này cần được ghi rõ trong docs (file này) để sau này khi đọc lại:
- Biết rằng Phase 7.2 đã chuyển Explainable RAG sang ID‑based.
- Có thể cân nhắc xóa hẳn text‑matching fallback ở các phase tương lai nếu không còn cần.

---

## 8. Kế hoạch implement (cao cấp)

1. **Chunker / ingest (server)**
   - Thêm `make_segment_id(document_id, segment_index)`.
   - Sửa `ChunkerService.build_content_list_from_document`:
     - Embedding `[SEG={segment_id}]` vào `content_list[*].text`.

2. **RagEngineService.query**
   - Cập nhật prompt Phase 7.2 (JSON với `source_ids[]`, dùng `[SEG=...]` làm nguồn).
   - Cập nhật parsing JSON:
     - Lưu `sections[*].source_ids` bên cạnh `text`.

3. **Messages API**
   - Thêm `_build_citations_from_source_ids(workspace_id, sections)`:
     - Parse ID → document_id, segment_index.
     - Dùng segmentation từ Phase 7.1 để lấy `page_idx`, `snippet`.
   - Logic `_process_ai_message_background`:
     - Nếu có bất kỳ `source_ids`:
       - Dùng `_build_citations_from_source_ids`.
     - Ngược lại:
       - Dùng `_build_citations_for_sections` (fallback text‑matching).

4. **Docs**
   - File này (`phase-7.2-design.md`) là source of truth cho server.
   - Thêm/Update `client-design-phase-7.2.md` (sau) để client biết:
     - `source_ids` mới.
     - Cách render sections + bong bóng kiểu NotebookLM.
   - Update `docs/implement/implement-*.md` khi code xong.

Phase 7.2 đặt nền cho Explainable RAG “giống NotebookLM” hơn, dựa trên ID‑based citations thay vì heuristic text‑matching, và vẫn giữ được backward‑compat thông qua fallback.***
