"""LangGraph state definition for the Reviewer graph."""

from __future__ import annotations

import operator
import time
import uuid
from typing import Annotated, Dict, List, Optional, TypedDict

from reviewer.schemas import DimensionLLMOutput, DimensionReview, ReviewOutput


def _add_ints(a: int, b: int) -> int:
    """Reducer: sum two ints (for total_tokens)."""
    return a + b


class ReviewerState(TypedDict):
    """State that flows through the Reviewer LangGraph."""

    # Inputs
    task: str
    report: str
    task_id: str
    report_id: str

    # Intermediate results — filled by each dimension reviewer node
    qa_review: Optional[DimensionReview]
    ir_review: Optional[DimensionReview]
    cp_review: Optional[DimensionReview]
    lc_review: Optional[DimensionReview]
    sq_review: Optional[DimensionReview]
    ps_review: Optional[DimensionReview]

    # Raw LLM outputs — contain additional_observations for aggregator
    qa_raw: Optional[DimensionLLMOutput]
    ir_raw: Optional[DimensionLLMOutput]
    cp_raw: Optional[DimensionLLMOutput]
    lc_raw: Optional[DimensionLLMOutput]
    sq_raw: Optional[DimensionLLMOutput]
    ps_raw: Optional[DimensionLLMOutput]

    # Metadata — use reducers for fields written by parallel nodes
    start_time: float
    total_tokens: Annotated[int, _add_ints]
    failed_dimensions: Annotated[List[str], operator.add]

    # Final output — filled by aggregator
    final_output: Optional[ReviewOutput]


def create_initial_state(
    task: str,
    report: str,
    task_id: str | None = None,
    report_id: str | None = None,
) -> ReviewerState:
    """Create an initial ReviewerState with all intermediate results set to None."""
    return ReviewerState(
        task=task,
        report=report,
        task_id=task_id or str(uuid.uuid4()),
        report_id=report_id or str(uuid.uuid4()),
        qa_review=None,
        ir_review=None,
        cp_review=None,
        lc_review=None,
        sq_review=None,
        ps_review=None,
        qa_raw=None,
        ir_raw=None,
        cp_raw=None,
        lc_raw=None,
        sq_raw=None,
        ps_raw=None,
        start_time=time.time(),
        total_tokens=0,
        failed_dimensions=[],
        final_output=None,
    )
