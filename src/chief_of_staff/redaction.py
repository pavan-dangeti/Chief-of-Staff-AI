"""Reversible masking of PII and secrets before text leaves the machine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_LABELLED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "SECRET",
        re.compile(
            r"\b(?:sk-(?:ant-)?[A-Za-z0-9_\-]{16,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}"
            r"|xox[abposr]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_\-]{30,})\b"
        ),
    ),
    ("URL", re.compile(r"\bhttps?://[^\s<>\"')\]]*[^\s<>\"')\].,;:!?]", re.IGNORECASE)),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){12,18}\d\b")),
    (
        "GOVID",
        re.compile(
            r"\b(?:\d{3}-\d{2}-\d{4}|[A-Z]{5}\d{4}[A-Z])\b"
            r"|(?<!\d )(?<!\d)\d{4}\s\d{4}\s\d{4}(?!\s?\d)"
        ),
    ),
    (
        "PHONE",
        re.compile(
            r"(?<![\w/-])(?:\+\d{1,3}[\s-]?)?(?:\(\d{1,4}\)[\s-]?)?\d{2,5}(?:[\s-]?\d{2,5}){1,3}(?![\w/-])"
        ),
    ),
    ("CODE", re.compile(r"(?i)\b(?:code|otp|pin|passcode)\b(?:\s*(?:is|:))?\s*(\d{4,8})\b")),
)


def _luhn_valid(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


_ISO_DATE = re.compile(r"\d{4}-\d{1,2}-\d{1,2}")


def _accept(label: str, original: str) -> bool:
    digits = re.sub(r"\D", "", original)
    if label == "CARD":
        return _luhn_valid(digits)
    if label == "PHONE":
        return 8 <= len(digits) <= 15 and not _ISO_DATE.fullmatch(original)
    return True


@dataclass
class RedactedText:
    text: str
    mapping: dict[str, str] = field(default_factory=dict)

    def restore(self, value: str | None) -> str | None:
        if value is None or not self.mapping:
            return value
        for placeholder, original in self.mapping.items():
            value = value.replace(placeholder, original)
        return value


class Redactor:
    def redact(self, text: str) -> RedactedText:
        mapping: dict[str, str] = {}
        reverse: dict[str, str] = {}
        counters: dict[str, int] = {}

        def placeholder_for(label: str, original: str) -> str:
            key = f"{label}:{original}"
            if key not in reverse:
                counters[label] = counters.get(label, 0) + 1
                token = f"[{label}_{counters[label]}]"
                reverse[key] = token
                mapping[token] = original
            return reverse[key]

        for label, pattern in _LABELLED_PATTERNS:

            def substitute(match: re.Match[str], label: str = label) -> str:
                original = match.group(match.lastindex or 0)
                if not _accept(label, original):
                    return match.group(0)
                replacement = placeholder_for(label, original)
                return match.group(0).replace(original, replacement)

            text = pattern.sub(substitute, text)
        return RedactedText(text=text, mapping=mapping)


class NoopRedactor(Redactor):
    def redact(self, text: str) -> RedactedText:
        return RedactedText(text=text)
