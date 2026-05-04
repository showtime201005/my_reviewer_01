"""Deep Research Report Reviewer — LangGraph subgraph for structured feedback."""

from __future__ import annotations

__version__ = "1.0.0"

from reviewer.graph import build_reviewer_graph
from reviewer.schemas import ReviewOutput
from reviewer.state import create_initial_state


def review(
    task: str,
    report: str,
    task_id: str | None = None,
    report_id: str | None = None,
    llm=None,
) -> ReviewOutput:
    """Run a full review on a deep research report.

    Args:
        task: The user's original research question.
        report: The deep research agent's report text.
        task_id: Optional identifier for the task.
        report_id: Optional identifier for the report.
        llm: Optional LLM instance (ChatOpenAI-compatible).

    Returns:
        A ReviewOutput Pydantic model with structured feedback.
    """
    graph = build_reviewer_graph(llm=llm)
    initial_state = create_initial_state(task, report, task_id, report_id)
    final_state = graph.invoke(initial_state)
    return final_state["final_output"]


__all__ = ["review", "build_reviewer_graph", "ReviewOutput", "create_initial_state"]
