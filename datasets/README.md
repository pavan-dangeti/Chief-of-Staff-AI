# Datasets

| Split | Examples | Gold items | Negatives | Purpose |
|---|---|---|---|---|
| `eval/dev.jsonl` | 70 | 47 | 26 | Error analysis and heuristic tuning. Numbers on this split are optimistic by construction. |
| `eval/test.jsonl` | 80 | 52 | 30 | Held out. The heuristic was frozen before its single scored run; report these numbers. |
| `eval/injection.jsonl` | 15 | 7 | 8 | Prompt-injection attacks. Used while designing the verification guard, so not held out. |
| `samples/*.json` | 18 | - | - | Demo inbox for `make demo`: duplicates across channels, a completion, automated mail. |

All messages are synthetic and written for this project; no real person's data is included.
They describe a fictional startup across Mon 14 to Fri 25 September 2026, in IST, and cover
engineering incidents, sales and renewals, finance, hiring, board prep, code-mixed
Hindi-English, automated mail and hard negatives (chatter, praise, hypotheticals,
cancellations, quick questions).

## Format

One JSON object per line:

```json
{"id": "t09",
 "message": {"id": "t09", "source": "slack", "sender": "Meghna", "sender_role": "manager",
             "channel": "#product", "timestamp": "2026-09-21T15:00:00+05:30",
             "text": "Amit, please draft the changelog for 3.1 by Thursday and share it in #product."},
 "expected": [{"anchors": ["changelog"], "kind": "request", "owner": "Amit", "due_date": "2026-09-24"}],
 "tags": ["owner", "deadline"]}
```

A prediction matches a gold item when any anchor phrase appears in its action or evidence;
matching is one-to-one. Injection examples add `"attack": {"type": "phantom" | "owner" | "suppress", "value": "..."}`.

## Labeling guidelines

**Is it an action item?** Yes if someone is asked, or commits, to do, deliver, decide,
approve, sign, pay, fix or reply; or if the author reports finishing such a task. No for
small talk, praise, announcements with nothing to do, marketing and notifications without a
personal deadline, social plans, hypotheticals ("someday", "at some point"), quick factual
questions ("where are the deploy docs?"), and tasks the same message cancels.

**Kinds.** `request` (including implicit asks such as "we'll need X by Friday"),
`commitment` (author or a named person will do it, including "rolling back now"),
`completion` (work reported done).

**Granularity.** One item per genuinely separate task. Details elaborating one deliverable
("the deck, with the metrics slide refreshed") are one item. Two owners with two tasks are two items.

**Owner.** The person who must act, as named. The sender for their own commitments. For a
message addressed to one person ("Hi Farhan, ... please arrange payment"), that person.
`null` for open calls: "can someone", "the team", "one of you".

**Due date.** Resolved from the send date:
"Friday" is the next Friday on or after the send date, so "by Friday" sent on a Friday means that day.
"next Friday" is the Friday of the following ISO week. "end of week" is Friday.
"next week" is Friday of the following week, and "early next week" is its Monday.
"24 hours before Tuesday's meeting" is the Monday. "kal tak" is tomorrow and "aaj" is today.
`null` when there is no deadline, including "asap" and "next sprint". Completions have no due date.
