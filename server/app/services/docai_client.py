"""Google Cloud Document AI client wrapper (Phase 2).

This module defines the interface used by the parser pipeline without
binding the rest of the codebase to the concrete SDK. The actual
integration with `google-cloud-documentai` can be implemented later.
"""

from __future__ import annotations

from typing import Any, Dict

from server.app.core.config import DocumentAISettings, get_settings


class DocumentAIClient:
    """Thin wrapper around Google Cloud Document AI OCR.

    The class is intentionally minimal; it can be extended when Phase 2
    is implemented for real.
    """

    def __init__(self, settings: DocumentAISettings | None = None) -> None:
        self.settings: DocumentAISettings = settings or get_settings().docai

    async def process_document_ocr(self, file_bytes: bytes, mime_type: str) -> Dict[str, Any]:
        """Call Enterprise Document OCR for a single file.

        Phase 2 placeholder: this method is not implemented yet. When
        wiring up Document AI, follow the design in `docs/design/phase-2-design.md`.
        """
        raise NotImplementedError("Phase 2 - DocumentAIClient.process_document_ocr is not implemented yet")

