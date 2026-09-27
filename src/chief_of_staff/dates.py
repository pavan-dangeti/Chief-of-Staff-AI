"""Resolve deadline phrases to calendar dates relative to the send time.

Conventions are documented and labeled in ``datasets/README.md``.
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

DateOrder = Literal["DMY", "MDY"]

_WEEKDAYS = {
    alias: index
    for index, aliases in enumerate(
        (
            "mon monday",
            "tue tues tuesday",
            "wed wednesday",
            "thu thur thurs thursday",
            "fri friday",
            "sat saturday",
            "sun sunday",
        )
    )
    for alias in aliases.split()
}
_FULL_WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
_MONTHS = {
    alias: index
    for index, aliases in enumerate(
        (
            "jan january",
            "feb february",
            "mar march",
            "apr april",
            "may",
            "jun june",
            "jul july",
            "aug august",
            "sep sept september",
            "oct october",
            "nov november",
            "dec december",
        ),
        start=1,
    )
    for alias in aliases.split()
}
_NUMBER_WORDS = {
    **{
        word: value
        for value, word in enumerate("one two three four five six seven eight nine ten".split(), 1)
    },
    "a": 1,
    "an": 1,
    "twelve": 12,
    "couple of": 2,
    "few": 3,
}

_WD = (
    r"(?P<wd>mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:s(?:day)?)?)?"
    r"|fri(?:day)?|sat(?:urday)?|sun(?:day)?)"
)
_MON = (
    r"(?P<mon>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?"
    r"|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_NUM = (
    r"(?:a\s+)?(?P<n>\d+|couple of|few|a|an|one|two|three|four|five|six"
    r"|seven|eight|nine|ten|twelve)"
)
_PROBE = datetime(2026, 1, 5, 12, 0)
_CUE = re.compile(
    r"(?:\b(?:by|before|until|till|due|no later than|on|for|in|within|ahead of|prior to)\s+)$"
)


@dataclass(frozen=True)
class _Rule:
    name: str
    pattern: re.Pattern[str]
    resolve: Callable[[re.Match[str], datetime, DateOrder], date | None]
    cue_required: bool = False


def _count(token: str) -> int:
    return int(token) if token.isdigit() else _NUMBER_WORDS[token.lower()]


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _on_or_after(day: date, weekday: int) -> date:
    return day + timedelta(days=(weekday - day.weekday()) % 7)


def _end_of_week(day: date) -> date:
    friday = _monday(day) + timedelta(days=4)
    return friday if day <= friday else friday + timedelta(days=7)


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _add_business_days(day: date, count: int) -> date:
    current = day
    while count > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            count -= 1
    return current


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _calendar_date(month: int, day: int, year: str | None, ref: date) -> date | None:
    if year:
        full_year = int(year) + 2000 if len(year) == 2 else int(year)
        return _safe_date(full_year, month, day)
    candidate = _safe_date(ref.year, month, day)
    if candidate is not None and candidate < ref - timedelta(days=30):
        return _safe_date(ref.year + 1, month, day)
    return candidate


def _iso(m: re.Match[str], ref: datetime, _: DateOrder) -> date | None:
    return _safe_date(int(m["y"]), int(m["m"]), int(m["d"]))


def _day_month(m: re.Match[str], ref: datetime, _: DateOrder) -> date | None:
    return _calendar_date(_MONTHS[m["mon"].lower()], int(m["d"]), m["y"], ref.date())


def _numeric(m: re.Match[str], ref: datetime, order: DateOrder) -> date | None:
    first, second = int(m["a"]), int(m["b"])
    if first > 12 >= second:
        day, month = first, second
    elif second > 12 >= first:
        month, day = first, second
    elif order == "DMY":
        day, month = first, second
    else:
        month, day = first, second
    return _calendar_date(month, day, m["y"], ref.date())


def _offset_before(m: re.Match[str], ref: datetime, order: DateOrder) -> date | None:
    anchor = resolve_deadline(m["rest"], ref, date_order=order)
    if anchor is None:
        return None
    count, unit = _count(m["n"]), m["unit"].lower()
    if unit.startswith(("hour", "hr")):
        return anchor - timedelta(days=count // 24)
    if unit.startswith("week"):
        return anchor - timedelta(weeks=count)
    return anchor - timedelta(days=count)


def _offset_after(m: re.Match[str], ref: datetime, _: DateOrder) -> date | None:
    count, unit = _count(m["n"]), m["unit"].lower()
    if unit.startswith(("hour", "hr")):
        return (ref + timedelta(hours=count)).date()
    if unit.startswith(("business", "working")):
        return _add_business_days(ref.date(), count)
    if unit.startswith("week"):
        return ref.date() + timedelta(weeks=count)
    return ref.date() + timedelta(days=count)


def _day_ordinal(m: re.Match[str], ref: datetime, _: DateOrder) -> date | None:
    day, today = int(m["d"]), ref.date()
    candidate = _safe_date(today.year, today.month, day)
    if candidate is not None and candidate >= today:
        return candidate
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return _safe_date(year, month, day)


def _next_weekday(m: re.Match[str], ref: datetime, _: DateOrder) -> date:
    return _monday(ref.date()) + timedelta(days=7 + _WEEKDAYS[m["wd"].lower()])


def _weekday(m: re.Match[str], ref: datetime, _: DateOrder) -> date:
    return _on_or_after(ref.date(), _WEEKDAYS[m["wd"].lower()])


def _quarter_end(ref: date) -> date:
    last_month = ((ref.month - 1) // 3 + 1) * 3
    return _month_end(ref.year, last_month)


def _next_month_end(ref: date) -> date:
    year, month = (ref.year + 1, 1) if ref.month == 12 else (ref.year, ref.month + 1)
    return _month_end(year, month)


def _fixed(fn: Callable[[date], date]) -> Callable[[re.Match[str], datetime, DateOrder], date]:
    return lambda _m, ref, _o: fn(ref.date())


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


_RULES: tuple[_Rule, ...] = (
    _Rule(
        "offset_before",
        _rx(
            rf"\b{_NUM}\s*(?P<unit>hours?|hrs?|days?|weeks?)\s+"
            r"(?:before|prior to|ahead of|in advance of)\s+(?P<rest>[^.;!?\n]+)"
        ),
        _offset_before,
    ),
    _Rule("iso", _rx(r"\b(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})\b"), _iso),
    _Rule(
        "day_month",
        _rx(rf"\b(?P<d>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MON}\b\.?(?:,?\s+(?P<y>\d{{4}}))?"),
        _day_month,
    ),
    _Rule(
        "month_day",
        _rx(rf"\b{_MON}\.?\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(?P<y>\d{{4}}))?"),
        _day_month,
    ),
    _Rule(
        "numeric",
        _rx(r"\b(?P<a>\d{1,2})/(?P<b>\d{1,2})(?:/(?P<y>\d{4}|\d{2}))?\b"),
        _numeric,
        cue_required=True,
    ),
    _Rule(
        "offset_after",
        _rx(
            rf"\b(?:in|within|next)\s+(?:the\s+next\s+)?{_NUM}\s*"
            r"(?P<unit>hours?|hrs?|business days?|working days?|days?|weeks?)\b"
        ),
        _offset_after,
    ),
    _Rule(
        "day_after_tomorrow",
        _rx(r"\bday after (?:tomorrow|tmrw)\b"),
        _fixed(lambda d: d + timedelta(days=2)),
    ),
    _Rule(
        "tomorrow",
        _rx(r"\b(?:tomorrow|tmrw|tmr|tomo|kal tak)\b"),
        _fixed(lambda d: d + timedelta(days=1)),
    ),
    _Rule(
        "today",
        _rx(
            r"\b(?:today|tonight|eod|cob|eob|close of business|aaj"
            r"|end of (?:the )?(?:day|business))\b"
        ),
        _fixed(lambda d: d),
    ),
    _Rule(
        "today_soft",
        _rx(r"\bthis (?:morning|afternoon|evening)\b"),
        _fixed(lambda d: d),
        cue_required=True,
    ),
    _Rule(
        "early_next_week",
        _rx(r"\b(?:early|start of|beginning of)\s+next week\b"),
        _fixed(lambda d: _monday(d) + timedelta(days=7)),
    ),
    _Rule("before_next_week", _rx(r"\bbefore next week\b"), _fixed(_end_of_week)),
    _Rule(
        "next_week",
        _rx(r"\b(?:(?:the )?end of )?next week\b"),
        _fixed(lambda d: _monday(d) + timedelta(days=11)),
    ),
    _Rule("end_of_week", _rx(r"\b(?:end of (?:the |this )?week|eow)\b"), _fixed(_end_of_week)),
    _Rule("this_week", _rx(r"\bthis week\b"), _fixed(_end_of_week)),
    _Rule(
        "weekend",
        _rx(r"\b(?:this |the )?weekend\b"),
        _fixed(lambda d: _on_or_after(d, 6)),
        cue_required=True,
    ),
    _Rule("end_of_next_month", _rx(r"\bend of next month\b"), _fixed(_next_month_end)),
    _Rule(
        "end_of_month",
        _rx(r"\b(?:end of (?:the |this )?month|eom|month[- ]end)\b"),
        _fixed(lambda d: _month_end(d.year, d.month)),
    ),
    _Rule(
        "end_of_quarter",
        _rx(r"\b(?:end of (?:the |this )?quarter|eoq|quarter[- ]end)\b"),
        _fixed(_quarter_end),
    ),
    _Rule(
        "end_of_year",
        _rx(r"\b(?:end of (?:the |this )?year|eoy|year[- ]end)\b"),
        _fixed(lambda d: date(d.year, 12, 31)),
    ),
    _Rule("next_weekday", _rx(rf"\bnext\s+{_WD}\b"), _next_weekday),
    _Rule("weekday", _rx(rf"\b(?:this\s+)?{_WD}\b"), _weekday),
    _Rule(
        "day_ordinal",
        _rx(r"\bthe (?P<d>\d{1,2})(?:st|nd|rd|th)\b"),
        _day_ordinal,
        cue_required=True,
    ),
    _Rule(
        "clock_time",
        _rx(r"\b(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)|noon|midday)\b"),
        _fixed(lambda d: d),
        cue_required=True,
    ),
)


def resolve_deadline(
    text: str | None, reference: datetime, *, date_order: DateOrder = "DMY"
) -> date | None:
    """Resolve the first recognizable deadline expression in ``text`` to a calendar date."""
    if not text:
        return None
    for rule in _RULES:
        match = rule.pattern.search(text)
        if match:
            resolved = rule.resolve(match, reference, date_order)
            if resolved is not None:
                return resolved
    return None


def find_deadline_phrase(text: str) -> str | None:
    """Leftmost resolvable deadline phrase in free text; ambiguous tokens need a cue like "by"."""
    best: tuple[int, int] | None = None
    for rule in _RULES:
        for match in rule.pattern.finditer(text):
            start, end = match.span()
            cue = _CUE.search(text[:start].lower()[-20:])
            weekday = match.groupdict().get("wd")
            ambiguous = rule.cue_required or (
                weekday is not None and weekday.lower() not in _FULL_WEEKDAYS
            )
            if ambiguous and cue is None:
                continue
            if rule.resolve(match, _PROBE, "DMY") is None:
                continue
            if cue is not None:
                start -= len(cue.group(0))
            if best is None or start < best[0]:
                best = (start, end)
            break
    return text[best[0] : best[1]].strip() if best else None
