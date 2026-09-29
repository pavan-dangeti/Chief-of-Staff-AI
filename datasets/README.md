# Datasets

| Split | Examples | Gold items | Negatives | Purpose |
|---|---|---|---|---|
| `eval/dev.jsonl` | 70 | 47 | 26 | Error analysis and heuristic tuning. Numbers on this split are optimistic by construction. |
| `eval/test.jsonl` | 80 | 52 | 30 | Held out. The heuristic was frozen before its single scored run; report these numbers. |
| `eval/injection.jsonl` | 15 | 7 | 8 | Prompt-injection attacks. Used while designing the verification guard, so not held out. |
| `samples/*.json` | 18 | - | - | Demo inbox for `make demo`: duplicates across channels, a completion, automated mail. |
| `eval/external.jsonl` | 20 | 20 | 3 | Written by two people outside the project who had not seen the code. Held out: committed before any change it could inform. See below. |

### External examples (`eval/external.jsonl`)

Two people who had not seen the verification code each wrote ten messages meant to trip up an
extraction tool, with the answer they expected. They are stored as written: the message text is
verbatim (only the surrounding quotation marks were removed), and each record keeps the author
(`friend_a`, `friend_b`) and their original answer in `author_label`.

- **Categories.** `category` is `manipulation` (3 examples: an injected instruction, a third
  party claiming a promise, an impersonated account) or `hard_case` (17: deadline changes,
  tentative language, unclear ownership). Attack success is computed on manipulation examples
  only; with 3 of them it is anecdotal, not a rate.
- **Labels follow the rules below.** The authors listed only commitments someone had accepted;
  these rules also count direct requests. Where the two conflict, the text is unchanged, the
  expected items follow the rules, `label_adjusted` is true and `review_note` says why. That
  applies to 7 of 20 examples (`xa05`, `xa09`, `xb01`, `xb02`, `xb03`, `xb05`, `xb07`); every
  adjustment was confirmed by the dataset owner.
- **Send time.** Every message is dated Mon 21 Sep 2026 08:00 IST except `xb03`, dated Fri 18 Sep
  17:00 IST so that its "Monday 9 AM" means the following Monday, as its author intended.
- **Ambiguous.** `xb04` (a review that depended on cancelled work) is tagged `ambiguous`; it is
  kept but excluded from headline scores and reported separately.
- **Not measured.** Some expected behaviour is outside what the extraction eval scores, such as
  "should not be marked high priority" or "ideally flagged". It is recorded in `unscored`.
- **Transcripts.** Several examples are short conversations written as one message; they test
  reading a transcript, not a real multi-message thread.

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
