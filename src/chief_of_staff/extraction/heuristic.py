"""Offline rule-based extractor: the no-key baseline and the last-resort fallback."""

from __future__ import annotations

import re

from chief_of_staff.dates import find_deadline_phrase, resolve_deadline
from chief_of_staff.models import ExtractedItem, ItemKind, Message, RawExtraction
from chief_of_staff.text import split_sentences


def _rx(pattern: str, flags: int = re.IGNORECASE) -> re.Pattern[str]:
    return re.compile(pattern, flags)


_VERBS = (
    r"send|share|review|approve|sign|submit|fix|revert|deploy|push|ship|merge|update|prepare|"
    r"prep|put together|draft|write|finish|complete|schedule|book|pay|renew|file|upload|check|"
    r"investigate|look (?:at|into)|test|call|email|reply|respond|confirm|verify|order|hire|"
    r"interview|onboard|migrate|rotate|patch|roll ?back|escalate|close|resolve|clean up|set up|"
    r"create|build|add|remove|cancel|move|reach out|follow up|sync|present|record|invoice|"
    r"reconcile|decide|finalize|publish|launch|release|back ?up|audit|document|renegotiate|"
    r"collect|process|run|handle|own|cover|coordinate|arrange|chase|nudge|ping|train|install|"
    r"countersign|ask|redeem|claim|register|activate|enable|disable|restart|provision|circulate|"
    r"introduce|return|refund"
)
_IMPERATIVE_ONLY = r"get|make|keep|give|bring|take|do|join|fill (?:out|in)|sign up"
_PAST = (
    r"fixed|reverted|shipped|sent|signed|merged|deployed|redeployed|pushed|updated|submitted|"
    r"approved|resolved|completed|finished|paid|renewed|rotated|patched|rolled back|uploaded|"
    r"scheduled|booked|filed|bumped|added|published|released|removed|created|migrated|"
    r"processed|handled|countersigned|restarted|provisioned|cleaned up|set up"
)
ACTION_VERB = _rx(rf"\b(?:{_VERBS})\b")
IMPERATIVE_START = _rx(rf"^(?:{_VERBS}|{_IMPERATIVE_ONLY})\b")
STRONG_REQUEST = _rx(
    r"\b(?:can|could|would) (?:you|u|someone|anyone|somebody|one of you|either of you)\b"
    r"|\bplease\b|\bpls\b|\bplz\b"
    r"|\b(?:kar|bhej|le|de|dekh)\s+(?:dena|do|lena|lo)\b"
    r"|\bkindly\b|\bneed(?:s)? (?:someone|you|u|your"
    r"|somebody)\b|\b(?:will|'ll) need\b|\baction required\b"
    r"|\bwaiting on (?:you|your)\b|\bawaiting your\b|\bassign(?:ed|ing)?\b.{0,60}?\bto\b"
    r"|\bneeds? (?:your |a |an )?(?:review|approval|sign[- ]?off|signature|decision)\b"
    r"|\bdon'?t forget\b|\bremember to\b"
)
WEAK_REQUEST = _rx(
    r"\b(?:should|must|have to|has to|need to|needs to|let'?s|make sure|ensure|gotta|got to)\b"
)
COMMITMENT = _rx(
    r"\b(?:i'?ll|i will|i'?m going to|i am going to|i can take|i'?ve got (?:it|this)|let me"
    r"|we'?ll|we will|will do|i'?m on it)\b"
)
IN_PROGRESS = _rx(
    r"\b(?:rolling back|reverting|restarting|investigating|looking into (?:it|this)|fixing|"
    r"deploying|patching)\b.{0,20}\b(?:now|right now|asap|right away)\b"
)
NAMED_COMMITMENT = _rx(
    r"\b([A-Z][a-z]+) (?:will|is going to|'ll) (?:own|handle|take|lead|drive|send|review|fix|"
    r"prepare|cover|run|finish|update)\b",
    0,
)
COMPLETION = _rx(
    rf"\b(?:i|we|i've|we've|just|finally|already)\s+(?:have\s+|just\s+|already\s+|finally\s+)?"
    rf"(?:{_PAST}|closed)\b"
    rf"|^(?:just\s+)?(?:{_PAST})\b"
    r"|\b(?:is|are|has been|have been)\s+(?:now\s+)?(?:done|fixed|resolved|merged|deployed|"
    r"shipped|signed|live|sent|approved|reverted|paid|complete|completed|processed|back up)\b"
    r"|\ball set\b|\btaken care of\b|\b(?:kar|bhej|de)\s+(?:diya|di|diye)\b"
)
_ATTACHMENT_IDIOM = _rx(r"\bplease find\b.{0,40}?\b(?:attached|enclosed|below)\b")
_OPEN_CALL = _rx(
    r"\b(?:can|could|would|will) (?:someone|somebody"
    r"|anyone|anybody)\b|\bneeds? (?:someone|somebody)\b"
    r"|\b(?:someone|somebody|we) (?:should|must|needs? to"
    r"|has to|have to)\b|^(?:all|everyone|team)\b"
    r"|\b(?:you all|all of you|everyone)\b"
)
_UNASSIGNED_AUDIENCE = _rx(r"\b(?:one of you|either of you|any of you|you all|all of you)\b")
NEGATION = _rx(
    r"\b(?:no need to|don'?t need to|doesn'?t need to|no action (?:needed|required)|not needed"
    r"|nothing (?:to do|needed)|ignore (?:this|my (?:last|previous))|never ?mind|nvm|disregard"
    r"|no longer needed|already (?:handled|taken care of|done)|(?:is|been) cancel+ed|called off)\b"
)
HYPOTHETICAL = _rx(
    r"\b(?:would be (?:nice|cool|great) (?:to|if)|someday|some day|one day we|in an ideal world"
    r"|at some point|if we ever|maybe we could|wouldn'?t it be|what if we|down the road)\b"
)
SOCIAL = _rx(
    r"\b(?:lunch|dinner|drinks|coffee|boba|tacos?|pizza|happy hour|party|game night|movie"
    r"|bowling|karaoke|cake|potluck|anyone want to|who'?s (?:in|up for|down)|want to grab)\b"
)
PRAISE = _rx(
    r"\b(?:thanks|thank you|great (?:job|work|demo|call|stuff)|well done|kudos|congrats"
    r"|congratulations|nice work|awesome work|keep (?:it|up)|loved? the|great to see|shout ?out"
    r"|proud of)\b"
)
INFO_QUESTION = _rx(
    r"^(?:(?:does|do|did) (?:anyone|anybody|someone|you) know|anyone know|(?:where|what|which|who"
    r"|when|how) (?:is|are|was|were|do|does|did|'s)|is there|are there)\b"
)
MARKETING = _rx(
    r"\b(?:unsubscribe|newsletter|digest|webinar|% off|job alert|recommended for you"
    r"|view in browser|manage (?:your )?preferences)\b"
)
AUTOMATED_ACTION = _rx(
    r"\b(?:verify|confirm|expire[sd]?|expiring|renew|due|deadline|action required|submit"
    r"|complete your|pay|redeem|activate|respond by|last day)\b"
)
AUDIENCE = _rx(r"\b(?:you|your|u)\b")
_CUE_PREFIX = _rx(r"^(?:by|before|on|until|till|due|for|in|within|ahead of|prior to)\s+")
REFERENCE = _rx(r"\b(?:this|that|it|them)\b")
CONTINUATION = _rx(r"^(?:it|this|that|they|which)(?:'s|\b)")
OFFSET_BEFORE = _rx(r"\b(\d+)\s*(hours?|hrs?|days?)\s+(?:before|prior to|ahead of|in advance)\b")

_NAME_STOPWORDS = frozenset(
    """hi hey hello dear yo team guys folks all everyone thanks reminder update note heads please
    pls also so and but ok okay quick fyi urgent re fwd morning yes no great sorry just hope btw
    today tomorrow friday monday tuesday wednesday thursday saturday sunday i we you""".split()
)
_LEADING_ADDRESS = _rx(r"^\s*(?:(?:hey|hi|hello|dear|yo)\s+)?@?([A-Z][a-zA-Z]+)\s*[,:]\s+", 0)
_LEADING_ADDRESS_LOWER = _rx(
    r"^\s*(?:(?:hey|hi|hello|dear|yo)\s+)?@?([a-zA-Z]+)\s*,\s*(?:can|could|would|pls|please|kindly)\b"
)
_MENTION = _rx(r"@([A-Za-z][\w.\-]*[A-Za-z0-9])")
_ASSIGN = _rx(r"\bassign(?:ed|ing)?\b.{0,60}?\bto\s+@?([A-Z][a-zA-Z]+)", 0)
_NAME_TO_OWN = _rx(
    r"\b@?([A-Z][a-zA-Z]+) to (?:own|handle|take|lead|drive|review|fix|look into)\b", 0
)
_NAME_CAN_YOU = _rx(r"\b([A-Z][a-zA-Z]+),? (?:can|could) you\b", 0)
_FILLER_PREFIX = _rx(
    r"^(?:(?:hey|hi|hello|dear|yo|so|also|and|ok|okay"
    r"|btw|fyi|heads up|reminder|quick one)\b[\s,:\-]*"
    r"|@[\w.\-]+[\s,:]*|(?:can|could|would) (?:you|u|someone|anyone|somebody)(?: please| pls)?\s+"
    r"|(?:please|pls|plz|kindly)\s+|(?:i'?ll|i will|we'?ll|we will|i'?m going to|let me)\s+"
    r"|(?:will need|need(?:s)? (?:someone|somebody|you|u) to|going to need someone to)\s+"
    r"|(?:someone|somebody|we|you) (?:should|must|need to|needs to|have to|has to)(?: probably)?\s+"
    r"|(?:let'?s|make sure to|don'?t forget to|remember to)\s+)+"
)


def _valid_name(candidate: str | None) -> str | None:
    if not candidate or candidate.casefold() in _NAME_STOPWORDS or len(candidate) < 2:
        return None
    return candidate


def _owner_for_request(sentence: str, message: Message, message_owner: str | None) -> str | None:
    if _UNASSIGNED_AUDIENCE.search(sentence):
        return None
    for pattern in (
        _ASSIGN,
        _NAME_TO_OWN,
        _MENTION,
        _LEADING_ADDRESS,
        _LEADING_ADDRESS_LOWER,
        _NAME_CAN_YOU,
    ):
        match = pattern.search(sentence)
        if match and (name := _valid_name(match.group(1))):
            return name
    if _OPEN_CALL.search(sentence):
        return None
    if message_owner:
        return message_owner
    if len(message.recipients) == 1:
        return message.recipients[0]
    return None


def _with_message_deadline(item: ExtractedItem, message: Message, body: str) -> ExtractedItem:
    """Attach a deadline stated elsewhere in the message, including "24 hours before" offsets."""
    offset = OFFSET_BEFORE.search(item.evidence)
    anchor = item.deadline_text or find_deadline_phrase(body)
    if offset and anchor and offset.group(0) not in anchor:
        phrase: str | None = (
            f"{offset.group(1)} {offset.group(2)} before {_CUE_PREFIX.sub('', anchor)}"
        )
    elif resolve_deadline(item.deadline_text, message.timestamp) is not None:
        return item
    else:
        phrase = item.deadline_text or anchor
    if phrase is None or phrase == item.deadline_text:
        return item
    return item.model_copy(
        update={"deadline_text": phrase, "confidence": min(item.confidence + 0.05, 0.95)}
    )


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def _action_text(sentence: str) -> str:
    text = _FILLER_PREFIX.sub("", _LEADING_ADDRESS.sub("", sentence.strip())).strip()
    text = _shorten(text.rstrip(" ?!.,;:"), 120)
    return (text[:1].upper() + text[1:]) if text else sentence.strip()


class HeuristicExtractor:
    name = "heuristic"
    model = "rules-v2"

    async def extract(self, message: Message, body: str) -> RawExtraction:
        return RawExtraction(
            items=self.extract_items(message, body), backend=self.name, model=self.model
        )

    def extract_items(self, message: Message, body: str) -> list[ExtractedItem]:
        automated = message.is_automated or bool(MARKETING.search(body))
        leading = _LEADING_ADDRESS.search(body) or _LEADING_ADDRESS_LOWER.search(body)
        message_owner = _valid_name(leading.group(1)) if leading else None
        items: list[ExtractedItem] = []
        previous: str | None = None
        previous_was_item = False
        for sentence in split_sentences(body):
            item = self._classify(sentence, message, automated, message_owner)
            if item is None:
                if previous_was_item and CONTINUATION.search(sentence):
                    last = items[-1]
                    items[-1] = last.model_copy(update={"evidence": f"{last.evidence} {sentence}"})
                previous_was_item = False
                previous = sentence
                continue
            if previous and REFERENCE.search(sentence) and not automated:
                context = _shorten(_action_text(previous), 60)
                item = item.model_copy(
                    update={
                        "action": f"{item.action} (re: {context})",
                        "evidence": f"{previous} {sentence}",
                    }
                )
            items.append(item)
            previous_was_item = True
            previous = sentence
        if automated and items:
            imperative = [i for i in items if IMPERATIVE_START.search(i.evidence)]
            items = [(imperative or items)[0]]
        if len(items) == 1:
            return [_with_message_deadline(items[0], message, body)]
        return items

    def _classify(
        self, sentence: str, message: Message, automated: bool, message_owner: str | None
    ) -> ExtractedItem | None:
        sentence = _ATTACHMENT_IDIOM.sub("", sentence).strip() or sentence
        if NEGATION.search(sentence) or HYPOTHETICAL.search(sentence):
            return None
        strong = bool(STRONG_REQUEST.search(sentence))
        has_verb = bool(ACTION_VERB.search(sentence))
        deadline = find_deadline_phrase(sentence)
        if SOCIAL.search(sentence) and not (has_verb and deadline):
            return None
        if automated:
            if not (AUTOMATED_ACTION.search(sentence) and AUDIENCE.search(sentence)):
                return None
            return self._item(
                ItemKind.REQUEST,
                sentence,
                owner=None,
                requester=None,
                deadline=deadline,
                base_confidence=0.6,
            )

        stripped = _FILLER_PREFIX.sub("", _LEADING_ADDRESS.sub("", sentence)).strip()
        if INFO_QUESTION.search(stripped) and not deadline:
            return None
        if strong:
            owner = _owner_for_request(sentence, message, message_owner)
            return self._item(
                ItemKind.REQUEST,
                sentence,
                owner=owner,
                requester=message.sender,
                deadline=deadline,
                base_confidence=0.75,
            )
        if COMPLETION.search(sentence):
            return self._item(
                ItemKind.COMPLETION,
                sentence,
                owner=message.sender,
                requester=None,
                deadline=None,
                base_confidence=0.75,
            )
        if PRAISE.search(sentence):
            return None
        if (named := NAMED_COMMITMENT.search(sentence)) and _valid_name(named.group(1)):
            return self._item(
                ItemKind.COMMITMENT,
                sentence,
                owner=named.group(1),
                requester=None,
                deadline=deadline,
                base_confidence=0.75,
            )
        if (COMMITMENT.search(sentence) and has_verb) or IN_PROGRESS.search(sentence):
            return self._item(
                ItemKind.COMMITMENT,
                sentence,
                owner=message.sender,
                requester=None,
                deadline=deadline,
                base_confidence=0.75,
            )
        if (WEAK_REQUEST.search(sentence) and has_verb) or IMPERATIVE_START.search(stripped):
            owner = _owner_for_request(sentence, message, message_owner)
            return self._item(
                ItemKind.REQUEST,
                sentence,
                owner=owner,
                requester=message.sender,
                deadline=deadline,
                base_confidence=0.6,
            )
        return None

    @staticmethod
    def _item(
        kind: ItemKind,
        sentence: str,
        *,
        owner: str | None,
        requester: str | None,
        deadline: str | None,
        base_confidence: float,
    ) -> ExtractedItem:
        confidence = base_confidence + (0.1 if deadline else 0.0) + (0.05 if owner else 0.0)
        return ExtractedItem(
            kind=kind,
            action=_action_text(sentence),
            owner=owner,
            requester=requester,
            deadline_text=deadline,
            evidence=sentence.strip(),
            confidence=round(min(confidence, 0.95), 2),
        )
