"""LLM client abstraction for the Phase 8 Answer Orchestrator.

This module provides a thin wrapper around an OpenAI-compatible chat API
so that the rest of the codebase does not depend directly on any SDK.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import requests

from server.app.core.config import AnswerSettings, get_settings
from server.app.core.logging import get_logger


logger = get_logger(__name__)


@dataclass
class LLMUsage:
    """Simple usage information for a single LLM call."""

    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class LLMClient:
    """OpenAI-compatible chat client for answer generation.

    This client is intentionally minimal and does not depend on the official
    OpenAI SDK so that it can work with any OpenAI-compatible endpoint.
    """

    def __init__(self, settings: Optional[AnswerSettings] = None) -> None:
        settings = settings or get_settings().answer
        self._settings = settings
        self._model = settings.model

        # Base URL resolution:
        # 1) ANSWER_BASE_URL from AnswerSettings
        # 2) OPENAI_BASE_URL from environment (if set)
        # 3) Default api.openai.com
        env_base_url = os.getenv("OPENAI_BASE_URL")
        base_url = settings.base_url or env_base_url or "https://api.openai.com/v1"
        self._base_url = base_url.rstrip("/")

        # API key resolution:
        # 1) ANSWER_API_KEY from AnswerSettings
        # 2) OPENAI_API_KEY from environment
        self._api_key = settings.api_key or os.getenv("OPENAI_API_KEY")

        self._max_tokens = settings.max_tokens
        self._temperature = settings.temperature

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema_hint: Optional[str] = None,
    ) -> Tuple[str, Optional[Dict[str, Any]], Optional[LLMUsage]]:
        """Generate a JSON-style answer from the LLM.

        Returns (raw_text, parsed_json_or_none, usage_or_none).
        """
        if not self._api_key:
            logger.error(
                "No API key configured for LLM client (ANSWER_API_KEY/OPENAI_API_KEY)."
            )
            fallback = (
                "Sorry, the language model is not configured on the server, "
                "so I cannot generate an answer right now."
            )
            return fallback, None, None

        return await asyncio.to_thread(
            self._sync_generate_json,
            system_prompt,
            user_prompt,
            json_schema_hint,
        )

    def _sync_generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema_hint: Optional[str] = None,
    ) -> Tuple[str, Optional[Dict[str, Any]], Optional[LLMUsage]]:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }

        # If the endpoint supports JSON mode, this nudges it towards strict JSON.
        # If unsupported, the server may ignore it or return an error; we handle
        # errors below.
        payload["response_format"] = {"type": "json_object"}

        if json_schema_hint:
            # Some providers support json_schema; for now we just include it
            # as an additional hint field if available.
            payload.setdefault("metadata", {})
            payload["metadata"]["json_schema_hint"] = json_schema_hint

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.error("Error calling LLM chat API: %s", str(exc))
            fallback = (
                "Sorry, there was an error while calling the language model. "
                "Please try again later."
            )
            return fallback, None, None

        # Extract text content.
        try:
            choices = data.get("choices") or []
            first = choices[0]
            message = first.get("message") or {}
            raw_text = str(message.get("content") or "")
        except Exception:  # noqa: BLE001
            logger.warning("Unexpected LLM response format; falling back to raw JSON.")
            raw_text = json.dumps(data, ensure_ascii=False)

        # Extract usage if present.
        usage_obj = data.get("usage") or {}
        usage: Optional[LLMUsage] = None
        try:
            if usage_obj:
                usage = LLMUsage(
                    model=self._model,
                    prompt_tokens=int(usage_obj.get("prompt_tokens") or 0),
                    completion_tokens=int(usage_obj.get("completion_tokens") or 0),
                    total_tokens=int(usage_obj.get("total_tokens") or 0),
                )
        except Exception:  # noqa: BLE001
            logger.debug("Failed to parse LLM usage information.", exc_info=True)
            usage = None

        # Best-effort JSON parsing from the returned text.
        parsed: Optional[Dict[str, Any]] = None
        text = raw_text.strip()
        if text:
            candidates = [text]

            # Heuristic: if there is a JSON object substring, try that first.
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                inner = text[start : end + 1].strip()
                if inner and inner != text:
                    candidates.insert(0, inner)

            for payload in candidates:
                try:
                    obj = json.loads(payload)
                    if isinstance(obj, dict):
                        parsed = obj
                        break
                except (json.JSONDecodeError, TypeError):
                    continue

        return raw_text, parsed, usage

