"""The extractor contract shared by the offline heuristic and hosted LLM backends."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Protocol

from pydantic import ValidationError

from chief_of_staff.extraction.prompt import render_message, repair_instruction
from chief_of_staff.models import ExtractionResponse, Message, RawExtraction, Usage


class ExtractionError(RuntimeError):
    """The backend answered, but not with anything that validates against the schema."""


class Extractor(Protocol):
    name: str
    model: str

    async def extract(self, message: Message, body: str) -> RawExtraction:
        """Extract action items from ``body`` (the possibly redacted text of ``message``)."""
        ...


class LLMExtractor(ABC):
    """Base class for hosted models: renders the prompt, validates, and repairs once."""

    name: str
    model: str

    @abstractmethod
    async def _generate(self, prompt: str, repair_note: str | None) -> tuple[Any, Usage]:
        """Call the provider and return the raw structured payload plus token usage."""

    async def extract(self, message: Message, body: str) -> RawExtraction:
        prompt = render_message(message, body)
        payload, usage = await self._generate(prompt, None)
        try:
            response = _validate(payload)
        except ExtractionError as first_error:
            payload, repair_usage = await self._generate(
                prompt, repair_instruction(str(first_error))
            )
            usage = usage + repair_usage
            response = _validate(payload)
        return RawExtraction(items=response.items, usage=usage, backend=self.name, model=self.model)


def _validate(payload: Any) -> ExtractionResponse:
    try:
        if isinstance(payload, (str, bytes)):
            payload = json.loads(payload)
        if isinstance(payload, list):
            payload = {"items": payload}
        return ExtractionResponse.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise ExtractionError(str(exc)) from exc
