"""Input validation node for the Reviewer graph."""

from __future__ import annotations

import time

from reviewer.state import ReviewerState


class InputValidationError(Exception):
    """Raised when input validation fails — aborts the graph."""


def input_validator_node(state: ReviewerState) -> dict:
    """Validate that task and report are usable before running reviewers.

    Raises:
        InputValidationError: If task is empty, report is too short, or input is too long.
    """
    task = state.get("task", "")
    report = state.get("report", "")

    if not task or not task.strip():
        raise InputValidationError("task is empty")

    if not report or len(report.strip()) < 100:
        raise InputValidationError(
            f"report too short: {len(report.strip())} chars (need ≥ 100)"
        )

    # Rough token estimate — Chinese chars count more, use len // 2 as heuristic
    estimated_tokens = (len(task) + len(report)) // 2
    if estimated_tokens > 100_000:
        raise InputValidationError(
            f"input too long: ~{estimated_tokens} estimated tokens"
        )

    return {
        "start_time": time.time(),
        "total_tokens": 0,
        "failed_dimensions": [],
    }
