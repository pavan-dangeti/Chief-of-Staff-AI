"""OpenAI-compatible chat completions backend (NVIDIA API Catalog and similar hosts), over httpx."""

from __future__ import annotations

import re
from typing import Any

import httpx

from chief_of_staff.extraction.base import ExtractionError, LLMExtractor
from chief_of_staff.extraction.prompt import SYSTEM_PROMPT, WIRE_SCHEMA
from chief_of_staff.models import Usage

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


class OpenAICompatExtractor(LLMExtractor):
    name = "nvidia"

    def __init__(
        self,
        client: httpx.AsyncClient,
        model: str,
        *,
        max_tokens: int = 1024,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self._client = client
        self.model = model
        self._max_tokens = max_tokens
        self._extra_body = extra_body or {}

    async def _generate(self, prompt: str, repair_note: str | None) -> tuple[Any, Usage]:
        content = prompt if repair_note is None else f"{prompt}\n\n{repair_note}"
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "temperature": 0,
            "max_tokens": self._max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "action_items", "schema": WIRE_SCHEMA},
            },
            **self._extra_body,
        }
        response = await self._client.post("/chat/completions", json=body)
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage") or {}
        tokens = Usage(
            input_tokens=usage.get("prompt_tokens") or 0,
            output_tokens=usage.get("completion_tokens") or 0,
        )
        try:
            text = data["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ExtractionError(f"response had no message content: {exc}") from exc
        return _FENCE.sub("", _THINK.sub("", text).strip()), tokens


def create_openai_compat_client(base_url: str, api_key: str, timeout_s: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        timeout=timeout_s,
    )
