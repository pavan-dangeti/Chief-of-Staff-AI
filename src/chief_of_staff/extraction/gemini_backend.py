"""Gemini backend using a JSON response schema for structured output."""

from __future__ import annotations

from typing import Any

from chief_of_staff.errors import require_extra
from chief_of_staff.extraction.base import LLMExtractor
from chief_of_staff.extraction.prompt import SYSTEM_PROMPT, WIRE_SCHEMA
from chief_of_staff.models import Usage


class GeminiExtractor(LLMExtractor):
    name = "gemini"

    def __init__(self, client: Any, model: str, *, temperature: float | None = None) -> None:
        self._client = client
        self.model = model
        self._temperature = temperature

    async def _generate(self, prompt: str, repair_note: str | None) -> tuple[Any, Usage]:
        types = require_extra("google.genai.types", "gemini")
        contents = prompt if repair_note is None else f"{prompt}\n\n{repair_note}"
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=self._temperature,
            response_mime_type="application/json",
            response_json_schema=WIRE_SCHEMA,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        response = await self._client.aio.models.generate_content(
            model=self.model, contents=contents, config=config
        )
        metadata = response.usage_metadata
        usage = Usage(
            input_tokens=(metadata.prompt_token_count or 0) if metadata else 0,
            output_tokens=(metadata.candidates_token_count or 0) if metadata else 0,
        )
        return response.text or "", usage


def create_gemini_client(api_key: str, timeout_s: float) -> Any:
    genai = require_extra("google.genai", "gemini")
    types = require_extra("google.genai.types", "gemini")
    return genai.Client(
        api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000))
    )
