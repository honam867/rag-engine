"""Helpers to build OCR full_text with basic layout preservation.

This module is intentionally provider-aware:
- For known OCR providers (e.g. Google Cloud Document AI) we try to
  reconstruct a text representation that preserves layout better
  (tables, row/column grouping, basic reading order).
- For unknown providers we fall back to whatever raw text they return.

At runtime the parser pipeline calls `build_full_text_from_ocr_result`
with the `parser_type` from `parse_jobs` so that we can plug in other
OCR engines in the future without changing the pipeline logic.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from server.app.core.constants import PARSER_TYPE_GCP_DOCAI


def build_full_text_from_ocr_result(parser_type: str, doc: Mapping[str, Any]) -> str:
    """Return a layout-aware full_text string for an OCR result.

    - For Google Cloud Document AI (`PARSER_TYPE_GCP_DOCAI`), use the
      structured layout information (pages/tables/paragraphs) to
      rebuild the text in reading order and keep table structure using
      simple separators between columns.
    - For other parser types (or if the structured layout is missing),
      fall back to `doc["text"]` as-is.
    """
    parser_type = (parser_type or "").strip() or PARSER_TYPE_GCP_DOCAI

    if parser_type == PARSER_TYPE_GCP_DOCAI:
        full_text = _build_docai_full_text_with_layout(doc)
        if full_text:
            return full_text

    # Fallback: best-effort raw text.
    return (doc.get("text") or "").strip()


def _build_docai_full_text_with_layout(doc: Mapping[str, Any]) -> str:
    """Build full_text using Document AI layout information.

    Strategy:
    - Iterate over pages.
    - For each page, collect:
      - Tables (with overall layout bounding box).
      - Paragraphs that are *not* inside any table box.
    - Sort all items on the page by (y, x) of their layout center to
      approximate reading order.
    - For tables:
      - Render header rows then body rows.
      - Join columns with " | " so that structure is visible even in
        proportional fonts / HTML.
    - For paragraphs:
      - Extract text via text_anchor spans.

    If anything looks wrong (no pages/anchors), we fall back to the
    original doc["text"].
    """
    text = (doc.get("text") or "").strip()
    pages: Sequence[Mapping[str, Any]] = doc.get("pages") or []
    if not pages:
        return text

    lines: list[str] = []

    for page_idx, page in enumerate(pages):
        page_items: list[dict[str, Any]] = []

        # Pre-compute table bounding boxes so we can filter out paragraphs
        # that fall inside tables (to avoid duplicating table text).
        table_entries: list[dict[str, Any]] = []
        for table in page.get("tables") or []:
            layout = table.get("layout") or {}
            bbox = layout.get("bounding_poly") or {}
            box = _bounding_box_from_poly(bbox)
            cy, cx = _center_from_box(box)
            table_entries.append(
                {
                    "kind": "table",
                    "table": table,
                    "box": box,
                    "y": cy,
                    "x": cx,
                }
            )

        page_items.extend(table_entries)

        # Collect paragraphs that are outside table bounding boxes.
        for para in page.get("paragraphs") or []:
            layout = para.get("layout") or {}
            bbox = layout.get("bounding_poly") or {}
            box = _bounding_box_from_poly(bbox)
            cy, cx = _center_from_box(box)

            if _is_inside_any_table(box, table_entries):
                continue

            page_items.append(
                {
                    "kind": "paragraph",
                    "layout": layout,
                    "box": box,
                    "y": cy,
                    "x": cx,
                }
            )

        # If we somehow have no structured items, fall back to raw text.
        if not page_items:
            if text:
                return text
            continue

        # Sort by vertical position first, then horizontal, to approximate
        # reading order (supports simple multi-column layouts reasonably).
        page_items.sort(key=lambda it: (it["y"], it["x"]))

        if page_idx > 0 and lines:
            # Page break: keep a blank line between pages.
            lines.append("")

        for item in page_items:
            if item["kind"] == "paragraph":
                anchor = (item["layout"] or {}).get("text_anchor") or {}
                para_text = _extract_text_from_anchor(doc, anchor).strip()
                if para_text:
                    lines.append(para_text)
            else:  # table
                table = item["table"]
                # Header rows, if any.
                for row in table.get("header_rows") or []:
                    row_text = _render_table_row(doc, row)
                    if row_text:
                        lines.append(row_text)
                # Body rows.
                for row in table.get("body_rows") or []:
                    row_text = _render_table_row(doc, row)
                    if row_text:
                        lines.append(row_text)

                # Blank line after each table to visually separate.
                if table.get("header_rows") or table.get("body_rows"):
                    lines.append("")

    full_text = "\n".join(lines).strip()
    return full_text or text


def _render_table_row(doc: Mapping[str, Any], row: Mapping[str, Any]) -> str:
    """Render a single table row as a pipe-separated string."""
    cells = row.get("cells") or []
    cell_texts: list[str] = []
    for cell in cells:
        layout = cell.get("layout") or {}
        anchor = layout.get("text_anchor") or {}
        text = _extract_text_from_anchor(doc, anchor).strip()
        cell_texts.append(text)

    # If all cells are empty, skip the row.
    if not any(cell_texts):
        return ""
    # Use " | " so structure stays visible in HTML / proportional fonts.
    return " | ".join(cell_texts)


def _extract_text_from_anchor(doc: Mapping[str, Any], anchor: Mapping[str, Any]) -> str:
    """Extract text from Document.text using a text_anchor dict."""
    if not anchor:
        return ""

    full_text = doc.get("text") or ""
    segments = anchor.get("text_segments") or []
    if not full_text or not segments:
        return ""

    parts: list[str] = []
    for seg in segments:
        start = int(seg.get("start_index", 0) or 0)
        end = int(seg.get("end_index", 0) or 0)
        if end <= start or start < 0:
            continue
        # Defensive guard against out-of-range indices.
        start = max(0, min(start, len(full_text)))
        end = max(start, min(end, len(full_text)))
        parts.append(full_text[start:end])

    return "".join(parts)


def _bounding_box_from_poly(poly: Mapping[str, Any]) -> tuple[float, float, float, float]:
    """Compute a simple (min_x, min_y, max_x, max_y) bounding box.

    Document AI may return either `normalized_vertices` (0..1) or
    absolute `vertices`. We treat both the same for ordering / containment
    checks because we only compare relative positions on the page.
    """
    vertices = poly.get("normalized_vertices") or poly.get("vertices") or []
    if not vertices:
        # Entire page fallback.
        return (0.0, 0.0, 1.0, 1.0)

    xs = []
    ys = []
    for v in vertices:
        # Values may be strings or numbers depending on JSON conversion.
        x_raw = v.get("x", 0)
        y_raw = v.get("y", 0)
        try:
            xs.append(float(x_raw))
            ys.append(float(y_raw))
        except (TypeError, ValueError):
            continue

    if not xs or not ys:
        return (0.0, 0.0, 1.0, 1.0)

    return (min(xs), min(ys), max(xs), max(ys))


def _center_from_box(box: tuple[float, float, float, float]) -> tuple[float, float]:
    """Return (cy, cx) center from a bounding box."""
    min_x, min_y, max_x, max_y = box
    return ((min_y + max_y) / 2.0, (min_x + max_x) / 2.0)


def _is_inside_any_table(
    box: tuple[float, float, float, float],
    table_entries: Sequence[Mapping[str, Any]],
) -> bool:
    """Return True if the given box center lies inside any table box."""
    cy, cx = _center_from_box(box)
    for entry in table_entries:
        t_min_x, t_min_y, t_max_x, t_max_y = entry["box"]
        if t_min_x <= cx <= t_max_x and t_min_y <= cy <= t_max_y:
            return True
    return False

