"""Turn raw email bodies into the text a human actually wrote."""

from __future__ import annotations

import html
import re

_HTML_HINT = re.compile(
    r"<!DOCTYPE|<html[\s>]|<body[\s>]|&zwnj;|<div[\s>]|<table[\s>]|<p[\s>]", re.IGNORECASE
)
_INVISIBLE = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad\u034f]")
_REPLY_HEADER = re.compile(
    r"^(?:On .{4,200}wrote:|-{2,}\s*Original Message\s*-{2,}|From: .+|_{5,})\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_SIGNATURE = re.compile(r"^(?:--\s*|Sent from my \w+.*)$", re.MULTILINE)


def looks_like_html(text: str) -> bool:
    return bool(_HTML_HINT.search(text[:2000]))


def html_to_text(raw_html: str) -> str:
    text = re.sub(r"<(script|style|head)[^>]*>.*?</\1>", " ", raw_html, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</div>|</tr>|</li>|</h\d>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _INVISIBLE.sub("", html.unescape(text))
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\s*\n\s*", "\n", text).strip()


def strip_quoted_reply(text: str) -> str:
    """Drop quoted history and signatures so old threads are not re-extracted as new asks."""
    match = _REPLY_HEADER.search(text)
    if match:
        text = text[: match.start()]
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))
    signature = _SIGNATURE.search(text)
    if signature:
        text = text[: signature.start()]
    return text.strip()


def clean_email_body(body: str, *, max_chars: int = 4000) -> str:
    text = html_to_text(body) if looks_like_html(body) else _INVISIBLE.sub("", body)
    return strip_quoted_reply(text)[:max_chars].strip()
