"""Recall-first noise gate: skip only messages with noise markers and no action or deadline cue."""

from __future__ import annotations

import re

from chief_of_staff.dates import find_deadline_phrase
from chief_of_staff.models import Message

_ACTION_CUE = re.compile(
    r"\b(?:please|pls|kindly|can you|could you|can someone"
    r"|could someone|need(?:s|ed)? (?:to|you|someone|your)"
    r"|will need|must|required|requires|action required|asap|urgent|deadline|due|expires?|expiring"
    r"|verify|confirm|approve|sign|submit|review|reply|respond|renew|pay|fix|revert|deploy|block(?:er|ing)?"
    r"|i'll|i will|let's|make sure|remember to|don't forget|reminder)\b",
    re.IGNORECASE,
)
_MARKETING = re.compile(
    r"\b(?:unsubscribe|newsletter|digest|webinar|% off"
    r"|sale ends|job alert|jobs? (?:for|matching) you"
    r"|recommended for you|view in browser|manage (?:your )?preferences"
    r"|you(?:'re| are) receiving this)\b",
    re.IGNORECASE,
)
_CHATTER = re.compile(
    r"^\W*(?:lol|lmao|haha+|nice|cool|thanks?(?: you)?"
    r"|ty|thx|\+1|same|agreed|congrats!*|gm|good morning"
    r"|ok(?:ay)?|kk|yep|yup|nope|sounds good|love (?:it|this)|:\w+:)\W*$",
    re.IGNORECASE,
)
_SYSTEM_EVENT = re.compile(r"\bhas (?:joined|left) the channel\b", re.IGNORECASE)


def skip_reason(message: Message) -> str | None:
    """Return why a message can be skipped, or ``None`` if it must be extracted."""
    if message.sender_verified is False:
        return "unverified_sender"
    text = message.text.strip()
    if not text:
        return "empty"
    if _SYSTEM_EVENT.search(text):
        return "system_event"
    if _CHATTER.match(text):
        return "chatter"
    has_cue = bool(_ACTION_CUE.search(text)) or find_deadline_phrase(text) is not None
    if has_cue:
        return None
    if message.is_automated or _MARKETING.search(text):
        return "automated_no_action"
    return None
