# Phase 7.1 – High‑Fidelity Raw Text & Robust Citation Alignment

> Mục tiêu: ghi lại cách **khắc phục** các hạn chế của Phase 7 hiện tại mà không phá vỡ contract với client, đồng thời chuẩn bị nền tảng tốt hơn cho “Explainable RAG” về lâu dài.
>
> Phase 7.1 không thay thế spec Phase 7; nó là **bổ sung** tập trung vào:
> - Chuẩn hóa cách sinh `segments` từ Document AI (bám sát PDF hơn).
> - Cải thiện thuật toán map `sections` → `segments` để citation scroll & highlight chính xác hơn.

---

## 1. Bối cảnh & vấn đề hiện tại

### 1.1. Triệu chứng phía người dùng

- Raw text viewer:
  - Endpoint `/raw-text` đang trả về `segments`, nhưng trong thực tế nhiều tài liệu chỉ có **1 segment rất dài** (nguyên văn bản thô).
  - Khi click bong bóng citation:
    - Viewer vẫn scroll đúng document, nhưng highlight **cả block text dài**, không giống cảm giác “đúng đoạn” như NotebookLM.
- Citation mapping:
  - Hai bong bóng trong cùng một câu trả lời (2 sections khác nhau) có thể:
    - Cùng trỏ vào **cùng một segment** (ví dụ đều map vào “segment 2”), dù nội dung thực sự nằm ở đầu và giữa tài liệu.
    - Làm UX “Explainable RAG” bị mất niềm tin, vì người dùng thấy highlight không khớp cảm nhận.

### 1.2. Nguyên nhân gốc (Phase 7)

1. **Segmentation thụ động, không bám cấu trúc PDF**
   - `docai_full_text` là `document.text` từ Document AI (đã có breakline hợp lý).
   - `chunk_full_text_to_segments(full_text, max_chunk_chars=1500)` hiện tại (**deprecated in runtime; kept here as design background**):
     - Split theo `\n\n`, rồi fallback `\n`, rồi chia theo độ dài ký tự.
     - Không dùng JSON Document AI (`docai_raw_r2_key`) – nơi có thông tin paragraph/line với `text_anchor`.
   - Hậu quả:
     - Segment là “khối text” theo độ dài nhân tạo, không trùng với đoạn/paragraph gốc.
     - Viewer & citations tham chiếu vào những khối không phản ánh rõ layout thật.

2. **Thuật toán map section → segment quá đơn giản**
   - `_build_citations_for_sections`:
     - Duyệt từng `section.text` độc lập, so khớp với mọi segment bằng overlap ký tự.
     - Chọn segment có score cao nhất, không xét:
       - Thứ tự section (i < j) nên đi kèm segment_index không giảm.
       - Sự gần nhau giữa các segment.
   - Khi segment to, nhiều từ chung → rất dễ “nuốt” cả nhiều section khác nhau.

---

## 2. Mục tiêu Phase 7.1

### 2.1. Raw text & viewer

- Sinh `segments` sao cho:
  - Càng gần với **đoạn văn/thực thể** trong PDF càng tốt (paragraph/line).
  - `page_idx` phản ánh trang thật trong Document AI.
  - Độ dài segment vừa phải để:
    - Người dùng dễ đọc và đối chiếu.
    - Citation highlight đúng đoạn, không tô nguyên khối lớn.

### 2.2. Citation alignment

- Map mỗi `section` (trong câu trả lời AI) tới 1–N `segments`:
  - Ưu tiên **segment gần nhất về nội dung và vị trí**.
  - Tôn trọng **thứ tự tuyến tính**:
    - Section sau không đột ngột nhảy ngược lên trước trong tài liệu nếu không có lý do cực kỳ rõ ràng.
  - Giảm tối đa case:
    - Nhiều bong bóng khác nhau cùng highlight cùng một đoạn lớn.
    - Bong bóng đầu tiên highlight đoạn giữa, bong bóng sau highlight đoạn đầu.

### 2.3. Ràng buộc

- **Không đổi schema DB**:
  - Vẫn dùng `documents.docai_full_text`, `documents.docai_raw_r2_key`, `messages.metadata`.
- **Không đổi contract API với client**:
  - `/raw-text` vẫn trả `{ segment_index, page_idx, text }`.
  - Citation vẫn là `{ document_id, segment_index, page_idx?, snippet_preview? }`.
- Tập trung cải thiện **cách sinh `segments` + cách map**, không bắt client đổi shape dữ liệu.

---

## 3. Thiết kế 7.1 – Chuẩn hóa segments từ Document AI

### 3.1. Nguồn dữ liệu: Document AI JSON

- Phase 2 đã lưu:
  - `documents.docai_full_text` – `document.text` (full string).
  - `documents.docai_raw_r2_key` – JSON Document AI (`storage_r2.upload_json(doc, key=raw_key)`).
- JSON Document AI (về mặt concept):
  - `text`: chuỗi toàn bộ nội dung OCR (đã lưu vào `docai_full_text`).
  - `pages[*].paragraphs[*].layout.text_anchor` hoặc `pages[*].lines[*].layout.text_anchor`:
    - Mỗi entity có `text_segments[*].start_index` / `end_index` trỏ vào `text`.
  - Điều này cho phép:
    - Tái dựng từng đoạn text gốc bằng slicing `text[start:end]`.
    - Gắn `page_idx` từ chỉ số trang.

### 3.2. Segment v2 – từ JSON, không chunk tay

Đề xuất thay đổi `chunk_full_text_to_segments` theo hướng:

1. **Interface mở rộng (ý tưởng, không đổi signature public)**:
   - Giữ signature public để không phá vỡ chỗ đang dùng:
     - `def chunk_full_text_to_segments(full_text: str, max_chunk_chars: int = 1500) -> list[dict]`
   - Bên trong, nếu có context (vd: JSON Document AI) sẽ:
     - Sử dụng helper mới, ví dụ:
       - `build_segments_from_docai(doc: dict, full_text: str, max_chunk_chars: int = 1500) -> list[dict]` (**deprecated in current implementation; segmentation now works directly on `docai_full_text`**)

2. **Logic đề xuất `build_segments_from_docai`**

- Bước 1: load JSON từ R2
  - Từ `documents.docai_raw_r2_key`, dùng `storage_r2.download_json`.
  - Lấy `doc["text"]` và đảm bảo trùng với `docai_full_text` (nếu lệch thì ưu tiên `doc["text"]` nhưng log cảnh báo).

- Bước 2: duyệt cấu trúc theo page
  - Ưu tiên sử dụng **paragraph**:
    - Với mỗi `page_idx, page`:
      - Với mỗi `paragraph` trong `page["paragraphs"]`:
        - Lấy `text_anchor = paragraph["layout"]["text_anchor"]`.
        - Lấy `text_segments[*]` → gom lại (nhiều segment nếu anchor discontiguous).
        - Dùng `start_index`/`end_index` để slice `full_text[start:end]`.
  - Nếu `paragraphs` không có/không ổn định:
    - Fallback dùng `lines` (`page["lines"]`) với logic tương tự.

- Bước 3: build segments
  - Tăng `segment_index` theo thứ tự xuất hiện: page 0 → page 1 → …
  - Mỗi segment:
    ```jsonc
    {
      "segment_index": <int>,   // 0-based, global
      "page_idx": <page index>, // 0-based
      "text": "<chuỗi text từ text_anchor>"
    }
    ```
  - Có thể merge các paragraph rất ngắn liên tiếp (nếu cần) nhưng **không vượt quá** `max_chunk_chars`.

3. **Fallback nếu không có JSON / trường hợp lỗi**

- Nếu `docai_raw_r2_key` trống hoặc download JSON lỗi:
  - Log cảnh báo.
  - Fallback về heuristic hiện tại:
    - Split theo `\n\n` → `\n` → fixed-size window, như đã làm trong Phase 7.

4. **Nơi sử dụng segments v2**

- Raw viewer:
  - `GET /documents/{document_id}/raw-text`:
    - Thay vì gọi trực tiếp `chunk_full_text_to_segments(full_text)` theo heuristic,
    - Sẽ:
      - Nếu có JSON → `build_segments_from_docai(...)`.
      - Nếu không → fallback heuristic.
- RAG ingest (`ChunkerService.build_content_list_from_document`):
  - Nên dùng chung đoạn logic xây `segments` v2:
    - `content_list[i].text = segments[i].text`
    - `content_list[i].page_idx = segments[i].page_idx`
  - Giữ cho segmentation giữa ingest và viewer nhất quán.

---

## 4. Thiết kế 7.1 – Citation alignment v2

### 4.1. Vấn đề với cách map hiện tại

- `_build_citations_for_sections` (Phase 7) hiện:
  - Ghép từng `section` một cách độc lập:
    - Tính similarity đơn giản giữa `section.text` và từng `segment.text`.
    - Chọn segment có score cao nhất nếu score ≥ 0.3.
  - Không xét:
    - Thứ tự tương đối giữa sections và segments.
    - Thực tế là sections thường lần lượt mô tả các phần khác nhau của cùng một tài liệu.
- Khi segments đã cụ thể hơn (từ JSON), cách map này vẫn có thể:
  - Gán nhiều section vào cùng một segment nếu câu trả lời tham chiếu chung nhiều lần.
  - Nhưng ít nhất highlight tại đúng đoạn paragraph; điều này đã tốt hơn.

### 4.2. Đề xuất alignment có thứ tự (monotone alignment)

Mục tiêu: vẫn giữ chi phí thấp (không dùng embedding server), nhưng thông minh hơn:

1. **Similarity ở mức token**
   - Chuẩn hóa text:
     - lower‑case, bỏ dấu câu cơ bản, cắt khoảng trắng dư.
   - Tách từ (split whitespace).
   - Tính score trên tập từ:
     - `score = |words_section ∩ words_segment| / max(|words_section|, |words_segment|)`.

2. **Ma trận điểm `score[i][j]`**
   - Với mỗi section i (0..S‑1) và mỗi segment j (0..N‑1):
     - Tính `score[i][j]` như trên, với giới hạn độ dài (vd cắt text xuống ~800 ký tự để tiết kiệm CPU).

3. **Gán có ràng buộc thứ tự**
   - Dùng chiến lược greedy có ràng buộc (đơn giản, dễ implement):
     - Khởi tạo `last_assigned_segment = -1`.
     - Với `section i` từ 0..S‑1:
       - Xét các segment `j >= last_assigned_segment` (không lùi).
       - Tìm `j_best` có score cao nhất trong vùng này.
       - Nếu `score[i][j_best]` ≥ threshold (vd 0.3–0.4):
         - Gán `segment_index = j_best`.
         - Cập nhật `last_assigned_segment = max(last_assigned_segment, j_best)`.
       - Nếu không có segment nào đạt ngưỡng:
         - Không gán citation cho section đó (để tránh map sai).
   - Có thể tinh chỉnh:
     - Nếu segment trước đó (`j < last_assigned_segment`) có score cao hơn rất nhiều so với mọi segment sau đó, cho phép “nhảy lùi” trong một số trường hợp đặc biệt (optional).

4. **Kết quả metadata**

- Vẫn giữ format như Phase 7:
  - `metadata.sections[*].citations[*].{document_id, segment_index, page_idx, snippet_preview}`.
  - `metadata.citations` là flatten các citation từ tất cả sections.
- Lợi ích:
  - Hai section liên tiếp ít khi cùng gán vào một segment trừ khi thực sự dùng chung đoạn nguồn.
  - Bong bóng số đầu tiên có xác suất cao map vào đoạn đầu của tài liệu (nếu nội dung tương ứng), bong bóng sau map vào các đoạn phía sau.

---

## 5. Ảnh hưởng tới API & client

### 5.1. API / schema

- **Không thay đổi**:
  - `GET /api/workspaces/{workspace_id}/documents/{document_id}/raw-text`:
    - Vẫn trả `DocumentRawTextResponse`:
      - `segments[*].segment_index`
      - `segments[*].page_idx`
      - `segments[*].text`
  - `POST /api/conversations/{conversation_id}/messages`:
    - Message AI vẫn có:
      - `content: str`
      - `metadata.sections[*].text`
      - `metadata.sections[*].citations[*].{document_id, segment_index, page_idx, snippet_preview}`
      - `metadata.citations[*]` (flatten).

### 5.2. Client

- Không bắt buộc thay đổi code client:
  - Viewer vẫn dùng `segments[*]` để render `<p id="segment-{segment_index}">`.
  - Bong bóng citation vẫn dùng `{document_id, segment_index}` để scroll/highlight.
- Sự khác biệt:
  - Raw text giờ được chia **bám sát paragraph/line** hơn, không còn là một block dài.
  - Citation mapping tôn trọng thứ tự hơn → click bong bóng 1 thường scroll tới đoạn đầu đúng hơn, không còn cả 2 bong bóng cùng tô một đoạn bất hợp lý.

---

## 6. Kế hoạch implement (tóm tắt)

1. **Segments từ Document AI JSON** (**deprecated – kept as historical design; current implementation does not use build_segments_from_docai**)
   - Thêm helper mới, ví dụ:
     - `build_segments_from_docai(doc: dict, full_text: str, max_chunk_chars: int = 1500) -> list[dict]`.
   - Cập nhật:
     - `ChunkerService.build_content_list_from_document` → ưu tiên JSON.
     - Endpoint `/raw-text` → nếu `docai_raw_r2_key` có, dùng JSON; nếu không, fallback heuristic v7.

2. **Citation alignment v2**
   - Cập nhật `_build_citations_for_sections`:
     - Thay similarity char‑level bằng token‑level.
     - Thêm bước alignment có ràng buộc thứ tự như mô tả ở mục 4.2.

3. **Testing thực tế**
   - Dùng vài PDF thật:
     - Một file có nhiều đoạn ngắn (paragraph rõ ràng).
     - Một file ít xuống dòng.
   - Kiểm tra:
     - Raw viewer hiển thị đoạn “nhìn giống PDF”.
     - Click từng bong bóng: scroll tới đoạn hợp lý, không highlight toàn block dài.

---

## 7. Ghi chú

- Phase 7.1 là bước trung gian:
  - Giữ nguyên kiến trúc và contract, chỉ làm **source‑of‑truth** cho segments thông minh hơn (dựa trên Document AI) và mapping citations cẩn thận hơn.
  - Về sau, nếu cần richer UX giống NotebookLM hơn nữa (phân loại đoạn text vs bảng vs hình), có thể:
    - Bổ sung `source_type` / `block_type` vào segment & citation.
    - Sử dụng thêm metadata từ Document AI JSON (table, figure, heading).
