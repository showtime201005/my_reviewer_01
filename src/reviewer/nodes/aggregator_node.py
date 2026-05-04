"""Aggregator node — wraps the pure-Python aggregate() for LangGraph."""

from __future__ import annotations

from reviewer.aggregator import aggregate
from reviewer.state import ReviewerState


def aggregator_node(state: ReviewerState) -> dict:
    """Combine all dimension reviews into the final ReviewOutput."""
    output = aggregate(state)
    return {"final_output": output}
