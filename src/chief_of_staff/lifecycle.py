"""Cross-message reasoning: completions close earlier tasks, and duplicates are merged."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rapidfuzz import fuzz

from chief_of_staff.models import ActionItem, ItemKind, Status
from chief_of_staff.text import content_tokens, first_name, object_tokens

_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


@dataclass(frozen=True)
class MatchPolicy:
    duplicate_jaccard: float = 0.5
    duplicate_fuzzy: float = 85.0
    object_overlap: float = 0.8
    object_min_shared: int = 2
    completion_min_shared: int = 2
    completion_jaccard: float = 0.2
    max_due_gap_days: int = 2


def _tokens(item: ActionItem) -> set[str]:
    return content_tokens(f"{item.action} {item.evidence}")


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left and right else 0.0


def _owners_compatible(left: ActionItem, right: ActionItem) -> bool:
    return (
        left.owner is None
        or right.owner is None
        or (first_name(left.owner) == first_name(right.owner))
    )


def is_duplicate(left: ActionItem, right: ActionItem, policy: MatchPolicy | None = None) -> bool:
    policy = policy or MatchPolicy()
    if left.message_id == right.message_id or not _owners_compatible(left, right):
        return False
    if (
        left.due_date
        and right.due_date
        and (abs((left.due_date - right.due_date).days) > policy.max_due_gap_days)
    ):
        return False
    if _jaccard(_tokens(left), _tokens(right)) >= policy.duplicate_jaccard:
        return True
    left_objects, right_objects = object_tokens(left.action), object_tokens(right.action)
    shared = len(left_objects & right_objects)
    if (
        shared >= policy.object_min_shared
        and shared / min(len(left_objects), len(right_objects)) >= policy.object_overlap
    ):
        return True
    return fuzz.token_set_ratio(left.action.casefold(), right.action.casefold()) >= (
        policy.duplicate_fuzzy
    )


def completion_score(
    completion: ActionItem, task: ActionItem, policy: MatchPolicy | None = None
) -> float:
    """Return a match score in [0, 1], or 0 when the completion cannot close the task."""
    policy = policy or MatchPolicy()
    if completion.timestamp < task.timestamp or task.kind is ItemKind.COMPLETION:
        return 0.0
    left, right = _tokens(completion), _tokens(task)
    shared = len(left & right)
    same_thread = completion.thread_id is not None and completion.thread_id == task.thread_id
    jaccard = _jaccard(left, right)
    if same_thread and shared >= 1:
        return max(jaccard, policy.completion_jaccard) + 0.5
    if shared >= policy.completion_min_shared and jaccard >= policy.completion_jaccard:
        return jaccard
    return 0.0


def apply_completions(
    items: Sequence[ActionItem], policy: MatchPolicy | None = None
) -> tuple[list[ActionItem], list[ActionItem], int]:
    """Return ``(tasks, unmatched_completions, matched_count)`` with closed tasks marked done."""
    tasks = [item for item in items if item.kind is not ItemKind.COMPLETION]
    completions = sorted(
        (item for item in items if item.kind is ItemKind.COMPLETION), key=lambda i: i.timestamp
    )
    unmatched: list[ActionItem] = []
    matched = 0
    for completion in completions:
        scored = [
            (completion_score(completion, task, policy), index)
            for index, task in enumerate(tasks)
            if tasks[index].status is Status.OPEN
        ]
        best_score, best_index = max(scored, default=(0.0, -1))
        if best_score <= 0:
            unmatched.append(completion)
            continue
        tasks[best_index] = tasks[best_index].model_copy(
            update={"status": Status.DONE, "resolved_by": completion.message_id}
        )
        matched += 1
    return tasks, unmatched, matched


def _rank(item: ActionItem) -> tuple[int, float, float]:
    priority = _PRIORITY_ORDER.get(item.priority.value if item.priority else "P3", 3)
    return (priority, -(item.score or 0.0), -item.confidence)


def deduplicate(
    items: Sequence[ActionItem], policy: MatchPolicy | None = None
) -> tuple[list[ActionItem], int]:
    """Merge duplicates, keeping the highest-priority representative. Returns (items, merged)."""
    parent = list(range(len(items)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i].status == items[j].status and is_duplicate(items[i], items[j], policy):
                parent[find(j)] = find(i)

    groups: dict[int, list[ActionItem]] = {}
    for index, item in enumerate(items):
        groups.setdefault(find(index), []).append(item)

    merged: list[ActionItem] = []
    for members in groups.values():
        best = min(members, key=_rank)
        related = sorted({m.message_id for m in members} - {best.message_id})
        dues = [m.due_date for m in members if m.due_date is not None]
        owner = best.owner or next((m.owner for m in members if m.owner), None)
        merged.append(
            best.model_copy(
                update={
                    "related_message_ids": related,
                    "due_date": min(dues) if dues else None,
                    "owner": owner,
                }
            )
        )
    return merged, len(items) - len(merged)
