"""Google Cloud Document AI client wrapper (Phase 2).

This module defines the interface used by the parser pipeline without
binding the rest of the codebase to the concrete SDK. The actual
integration with `google-cloud-documentai` can be implemented later.
"""

from __future__ import annotations

from typing import Any, Dict

from google.api_core.exceptions import GoogleAPIError
from google.cloud import documentai_v1 as documentai
from google.protobuf.json_format import MessageToDict
from starlette.concurrency import run_in_threadpool

from server.app.core.config import DocumentAISettings, get_settings


class DocumentAIClient:
    """Thin wrapper around Google Cloud Document AI OCR."""

    def __init__(self, settings: DocumentAISettings | None = None) -> None:
        self.settings: DocumentAISettings = settings or get_settings().docai
        if not self.settings.project_id or not self.settings.location or not self.settings.ocr_processor_id:
            raise RuntimeError("Document AI settings are incomplete. Please configure GCP_PROJECT_ID, GCP_LOCATION and DOCAI_OCR_PROCESSOR_ID.")

        client_options: Dict[str, Any] = {}
        if self.settings.credentials_path:
            client_options["client_options"] = {"quota_project_id": self.settings.project_id}

        # The SDK will pick up Application Default Credentials; we only pass client_options if needed.
        self._client = documentai.DocumentProcessorServiceClient(**client_options)
        self._processor_name = self._client.processor_path(
            self.settings.project_id,
            self.settings.location,
            self.settings.ocr_processor_id,
        )

    def _process_sync(self, file_bytes: bytes, mime_type: str) -> Dict[str, Any]:
        """Synchronous call to Document AI, wrapped for use in a thread."""
        raw_document = documentai.RawDocument(content=file_bytes, mime_type=mime_type)
        request = documentai.ProcessRequest(name=self._processor_name, raw_document=raw_document)
        try:
            result = self._client.process_document(request=request)
        except GoogleAPIError as exc:  # pragma: no cover - thin wrapper around SDK
            raise RuntimeError(f"Document AI processing failed: {exc}") from exc

        # Convert Document protobuf to dict so it can be serialized and stored.
        # Fix: result.document is a proto-plus wrapper; access the underlying protobuf via ._pb
        return MessageToDict(result.document._pb, preserving_proto_field_name=True)

    async def process_document_ocr(self, file_bytes: bytes, mime_type: str) -> Dict[str, Any]:
        """Call Enterprise Document OCR for a single file and return the Document as dict."""
        return await run_in_threadpool(self._process_sync, file_bytes, mime_type)

