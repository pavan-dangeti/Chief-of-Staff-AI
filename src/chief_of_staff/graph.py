"""LangGraph orchestration with per-message ``Send`` fan-out, sharing the pipeline's stages."""

from __future__ import annotations

import operator
import time
from datetime import datetime
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from chief_of_staff.extraction.service import ExtractionService, MessageExtraction
from chief_of_staff.models import Digest, Message, SkippedMessage
from chief_of_staff.pipeline import build_digest, partition
from chief_of_staff.prioritization import Prioritizer


class GraphState(TypedDict, total=False):
    messages: list[Message]
    as_of: datetime | None
    started: float
    candidates: list[Message]
    skipped: list[SkippedMessage]
    extractions: Annotated[list[MessageExtraction], operator.add]
    digest: Digest


class _ExtractTask(TypedDict):
    message: Message


def build_graph(
    service: ExtractionService,
    prioritizer: Prioritizer | None = None,
    *,
    prefilter: bool = True,
    checkpointer: Any = None,
) -> Any:
    ranker = prioritizer or Prioritizer()

    def prefilter_node(state: GraphState) -> dict[str, Any]:
        candidates, skipped = partition(state["messages"], enabled=prefilter)
        return {"candidates": candidates, "skipped": skipped, "started": time.perf_counter()}

    def route(state: GraphState) -> list[Send] | str:
        if not state["candidates"]:
            return "assemble"
        return [Send("extract", {"message": message}) for message in state["candidates"]]

    async def extract_node(state: _ExtractTask) -> dict[str, Any]:
        return {"extractions": [await service.extract_message(state["message"])]}

    def assemble_node(state: GraphState) -> dict[str, Any]:
        digest = build_digest(
            state["messages"],
            state.get("extractions", []),
            state["skipped"],
            ranker,
            as_of=state.get("as_of"),
            wall_time_ms=(time.perf_counter() - state["started"]) * 1000,
        )
        return {"digest": digest}

    graph = StateGraph(GraphState)
    graph.add_node("prefilter", prefilter_node)
    graph.add_node("extract", extract_node)
    graph.add_node("assemble", assemble_node)
    graph.add_edge(START, "prefilter")
    graph.add_conditional_edges("prefilter", route, ["extract", "assemble"])
    graph.add_edge("extract", "assemble")
    graph.add_edge("assemble", END)
    return graph.compile(checkpointer=checkpointer)


async def run_graph(
    graph: Any,
    messages: list[Message],
    *,
    as_of: datetime | None = None,
    thread_id: str = "default",
) -> Digest:
    state = await graph.ainvoke(
        {"messages": messages, "as_of": as_of, "extractions": []},
        config={"configurable": {"thread_id": thread_id}},
    )
    digest: Digest = state["digest"]
    return digest
