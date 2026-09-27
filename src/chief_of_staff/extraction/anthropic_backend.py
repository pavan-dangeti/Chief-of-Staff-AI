"""Claude backend using forced tool use for schema-constrained output."""

from __future__ import annotations

from typing import Any

from chief_of_staff.errors import require_extra
from chief_of_staff.extraction.base import ExtractionError, LLMExtractor
from chief_of_staff.extraction.prompt import SYSTEM_PROMPT, TOOL_NAME, WIRE_SCHEMA
from chief_of_staff.models import Usage

_TOOL = {
    "name": TOOL_NAME,
    "description": "Record every action item found in the message (empty list if none).",
    "input_schema": WIRE_SCHEMA,
}


class AnthropicExtractor(LLMExtractor):
    name = "anthropic"

    def __init__(self, client: Any, model: str, *, max_tokens: int = 1024) -> None:
        self._client = client
        self.model = model
        self._max_tokens = max_tokens

    async def _generate(self, prompt: str, repair_note: str | None) -> tuple[Any, Usage]:
        content = prompt if repair_note is None else f"{prompt}\n\n{repair_note}"
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=self._max_tokens,
            system=SYSTEM_PROMPT,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[{"role": "user", "content": content}],
        )
        usage = Usage(
            input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens
        )
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == TOOL_NAME:
                return block.input, usage
        raise ExtractionError("model response contained no tool_use block")


def create_anthropic_client(api_key: str, timeout_s: float) -> Any:
    anthropic = require_extra("anthropic", "anthropic")
    return anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_s, max_retries=0)
