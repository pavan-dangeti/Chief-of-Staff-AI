"""Text normalization helpers shared by grounding, deduplication and completion matching."""

from __future__ import annotations

import re

_STOPWORDS = frozenset(
    """a an the and or but if then so to of in on at by for with from into onto about as is are was
    were be been being it its this that these those i me my we our us you your he she they them
    their his her can could would should will shall may might must do does did done have has had
    please pls plz just also still need needs needed someone anyone somebody team hey hi hello
    thanks thank ok okay up out over re fwd fw now today tomorrow asap all any some get got let
    lets go going make sure one what when where who how why there here which while than not
    no""".split()
)
_NON_OBJECT = frozenset(
    """put together send review sign approve prepare prep updat update fix finish complet complete
    share draft writ write submit check look refresh creat create build handl handle take own pay
    schedul schedule book follow reach call email reply confirm verify deliver have give bring
    monday tuesday wednesday thursday friday saturday sunday week month hour day eod eow before
    after until morning afternoon tonight next end soon latest""".split()
)
_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n+")
_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Casefold and collapse whitespace; strip quote characters that models often alter."""
    text = text.casefold().replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return _WHITESPACE.sub(" ", text).strip()


def _stem(token: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def content_tokens(text: str) -> set[str]:
    """Meaningful word stems, used for fuzzy matching between related action items."""
    return {
        _stem(token)
        for token in _TOKEN.findall(normalize(text))
        if token not in _STOPWORDS and len(token) > 1
    }


def object_tokens(text: str) -> set[str]:
    """Content stems minus verbs, time words and numbers: roughly *what* the task is about."""
    return {
        token for token in content_tokens(text) if token not in _NON_OBJECT and not token.isdigit()
    }


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_BREAK.split(text) if part and part.strip()]


def first_name(name: str) -> str:
    """Casefolded first token of a display name, without ``@`` or email domain."""
    cleaned = name.strip().lstrip("@").split("@")[0]
    parts = re.split(r"[\s._<>\"]+", cleaned)
    return next((part.casefold() for part in parts if part), "")
