"""Local stand-in for the Anthropic Messages API, used for production-style runs without a key.

Point the real SDK at it with ``ANTHROPIC_BASE_URL``. Responses have the provider's shape
(forced ``tool_use`` block, usage, error envelopes) and are filled by the rules engine, so the
run measures the system around the model: HTTP, retries, rate limiting, circuit breaking,
caching, escalation and verification. It says nothing about model quality.

Faults are seeded and configurable: ``SIM_LATENCY_MS``, ``SIM_RATE_429``, ``SIM_RATE_529``,
``SIM_LOW_CONFIDENCE``, ``SIM_SEED``.
"""

from __future__ import annotations

import asyncio
import os
import random
import re
import uuid
from collections import Counter
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from chief_of_staff.extraction.heuristic import HeuristicExtractor
from chief_of_staff.models import Message, Source

LATENCY_MS = float(os.environ.get("SIM_LATENCY_MS", "350"))
RATE_429 = float(os.environ.get("SIM_RATE_429", "0.08"))
RATE_529 = float(os.environ.get("SIM_RATE_529", "0.02"))
LOW_CONFIDENCE = float(os.environ.get("SIM_LOW_CONFIDENCE", "0.1"))
rng = random.Random(int(os.environ.get("SIM_SEED", "7")))

_FIELD = re.compile(r"^(\w+): (.*)$", re.MULTILINE)
_BODY = re.compile(r'<untrusted_message id="(\w+)">\n(.*)\n</untrusted_message id="\1">', re.S)
_SENDER = re.compile(r"^(.*) \(role: (.*)\)$")

app = FastAPI()
stats: Counter[str] = Counter()
rules = HeuristicExtractor()


def _message_from_prompt(prompt: str) -> Message:
    fields = dict(_FIELD.findall(prompt.split("<untrusted_message", 1)[0]))
    body_match = _BODY.search(prompt)
    body = body_match.group(2) if body_match else ""
    body = body.replace("<\\/untrusted_message", "</untrusted_message")
    sender = _SENDER.match(fields.get("sender", "unknown (role: unknown)"))
    recipients = fields.get("recipients", "-")
    return Message(
        id="simulated",
        source=Source(fields.get("source", "slack")),
        sender=sender.group(1) if sender else "unknown",
        sender_role=sender.group(2) if sender else "unknown",
        channel=fields.get("channel_or_subject"),
        timestamp=datetime.fromisoformat(fields["sent_at"].split(" ")[0]),
        text=body,
        recipients=() if recipients == "-" else tuple(r.strip() for r in recipients.split(",")),
        is_automated=fields.get("automated_sender") == "yes",
    )


def _error(status: int, kind: str, retry_after: str | None = None) -> JSONResponse:
    stats[f"http_{status}"] += 1
    headers = {"retry-after": retry_after} if retry_after else {}
    body = {"type": "error", "error": {"type": kind, "message": f"simulated {kind}"}}
    return JSONResponse(body, status_code=status, headers=headers)


@app.post("/v1/messages")
async def messages(request: Request) -> JSONResponse:
    payload: dict[str, Any] = await request.json()
    stats["requests"] += 1
    await asyncio.sleep(max(rng.gauss(LATENCY_MS, LATENCY_MS * 0.25), 20) / 1000)
    roll = rng.random()
    if roll < RATE_429:
        return _error(429, "rate_limit_error", retry_after="1")
    if roll < RATE_429 + RATE_529:
        return _error(529, "overloaded_error")

    prompt = payload["messages"][0]["content"]
    message = _message_from_prompt(prompt)
    items = [i.model_dump(mode="json") for i in rules.extract_items(message, message.text)]
    if "haiku" in payload["model"] and items and rng.random() < LOW_CONFIDENCE:
        items[0]["confidence"] = 0.4
        stats["low_confidence_answers"] += 1
    stats[f"model_{payload['model']}"] += 1
    stats["http_200"] += 1
    return JSONResponse(
        {
            "id": f"msg_{uuid.uuid4().hex[:24]}",
            "type": "message",
            "role": "assistant",
            "model": payload["model"],
            "content": [
                {
                    "type": "tool_use",
                    "id": f"toolu_{uuid.uuid4().hex[:24]}",
                    "name": payload["tool_choice"]["name"],
                    "input": {"items": items},
                }
            ],
            "stop_reason": "tool_use",
            "stop_sequence": None,
            "usage": {
                "input_tokens": (len(payload["system"]) + len(prompt)) // 4,
                "output_tokens": 20 + 60 * len(items),
            },
        }
    )


@app.get("/stats")
async def get_stats() -> dict[str, int]:
    return dict(stats)
