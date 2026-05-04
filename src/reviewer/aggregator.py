"""Aggregator — pure Python logic to combine six dimension reviews into ReviewOutput.

Does NOT call any LLM.  See PROJECT_SPEC.md §10.
"""

from __future__ import annotations

import time
from typing import Dict, List, Tuple

from reviewer.schemas import (
    ALL_DIMENSION_CODES,
    DimensionCode,
    DimensionLLMOutput,
    DimensionReview,
    DimensionStatus,
    Feedback,
    HumanSummary,
    ReviewMetadata,
    ReviewOutput,
    Severity,
    V2Interface,
)
from reviewer.state import ReviewerState

# Mapping: dimension full name → (state review key, state raw key, DimensionCode)
_DIMENSION_MAP: List[Tuple[str, str, str, str]] = [
    ("question_alignment", "qa_review", "qa_raw", "QA"),
    ("information_recall",  "ir_review", "ir_raw", "IR"),
    ("completeness",        "cp_review", "cp_raw", "CP"),
    ("logical_coherence",   "lc_review", "lc_raw", "LC"),
    ("source_quality",      "sq_review", "sq_raw", "SQ"),
    ("presentation_specificity", "ps_review", "ps_raw", "PS"),
]

_FAILED_SUMMARY = "此維度評估失敗，請參考其他維度"


def aggregate(state: ReviewerState) -> ReviewOutput:
    """Combine six dimension reviews into a single ReviewOutput.

    Steps:
    1. Collect dimension reviews and raw LLM outputs from state.
    2. Extract additional_observations (nice_to_fix items from raw outputs).
    3. Compute severity_distribution across all feedback.
    4. Classify dimensions into with_issues / clean.
    5. Extract highlights (top must_fix by confidence).
    6. Build key_findings from dimension summaries.
    7. Render human_readable_text.
    8. Assemble ReviewMetadata.
    9. Return ReviewOutput.
    """
    dimension_reviews: Dict[str, DimensionReview] = {}
    additional_observations: List[Feedback] = []

    for dim_name, review_key, raw_key, code in _DIMENSION_MAP:
        review: DimensionReview | None = state.get(review_key)
        raw: DimensionLLMOutput | None = state.get(raw_key)

        if review is None:
            # Dimension was never executed — treat as failed
            review = DimensionReview(
                dimension=dim_name,
                dimension_summary=_FAILED_SUMMARY,
                confidence=0.0,
                top_feedback=[],
                status=DimensionStatus.FAILED,
            )

        if review.status == DimensionStatus.FAILED:
            review = review.model_copy(update={
                "dimension_summary": _FAILED_SUMMARY,
                "confidence": 0.0,
                "top_feedback": [],
            })

        dimension_reviews[dim_name] = review

        # Collect nice_to_fix and additional observations from raw output
        if raw is not None:
            for fb in raw.additional_observations:
                additional_observations.append(fb)
            # Also collect nice_to_fix from top_feedback (shouldn't happen
            # after validation, but be defensive)
            for fb in raw.top_feedback:
                if fb.severity == Severity.NICE_TO_FIX:
                    additional_observations.append(fb)

    # Severity distribution — count across ALL feedback
    severity_dist = _count_severities(dimension_reviews, additional_observations)

    # Classify dimensions
    dimensions_with_issues: List[str] = []
    dimensions_clean: List[str] = []
    for dim_name, review_key, raw_key, code in _DIMENSION_MAP:
        dr = dimension_reviews[dim_name]
        if _has_must_or_should_fix(dr):
            dimensions_with_issues.append(code)
        else:
            dimensions_clean.append(code)

    # Highlights — must_fix items, sorted by confidence desc, max 5
    highlights = _extract_highlights(dimension_reviews, max_n=5)

    # Key findings — concatenate non-empty dimension summaries
    key_findings = " ".join(
        dr.dimension_summary
        for dr in dimension_reviews.values()
        if dr.dimension_summary and dr.dimension_summary != _FAILED_SUMMARY
    )

    # Human-readable text
    human_readable_text = render_human_readable_text(
        key_findings=key_findings,
        severity_dist=severity_dist,
        dimensions_with_issues=dimensions_with_issues,
        dimensions_clean=dimensions_clean,
        highlights=highlights,
    )

    # Metadata
    elapsed = time.time() - state["start_time"]
    metadata = ReviewMetadata(
        reviewer_version="v1.0-passive",
        task_id=state["task_id"],
        report_id=state["report_id"],
        review_cost_tokens=state.get("total_tokens", 0),
        review_latency_seconds=round(elapsed, 2),
        active_verification_used=False,
        failed_dimensions=list(state.get("failed_dimensions", [])),
    )

    return ReviewOutput(
        review_metadata=metadata,
        human_summary=HumanSummary(
            key_findings=key_findings,
            severity_distribution=severity_dist,
            dimensions_with_issues=dimensions_with_issues,
            dimensions_clean=dimensions_clean,
            highlights=highlights,
        ),
        human_readable_text=human_readable_text,
        dimension_reviews=dimension_reviews,
        additional_observations=additional_observations,
        v2_interface=V2Interface(),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_severities(
    dimension_reviews: Dict[str, DimensionReview],
    additional: List[Feedback],
) -> Dict[str, int]:
    """Count total feedback items per severity level."""
    counts = {"must_fix": 0, "should_fix": 0, "nice_to_fix": 0}
    for dr in dimension_reviews.values():
        for fb in dr.top_feedback:
            counts[fb.severity.value] += 1
    for fb in additional:
        counts[fb.severity.value] += 1
    return counts


def _has_must_or_should_fix(dr: DimensionReview) -> bool:
    """Return True if the dimension has any must_fix or should_fix feedback."""
    return any(
        fb.severity in (Severity.MUST_FIX, Severity.SHOULD_FIX)
        for fb in dr.top_feedback
    )


def _extract_highlights(
    dimension_reviews: Dict[str, DimensionReview],
    max_n: int = 5,
) -> List[str]:
    """Extract must_fix one-liners sorted by confidence desc."""
    must_fix_items: List[Feedback] = []
    for dr in dimension_reviews.values():
        for fb in dr.top_feedback:
            if fb.severity == Severity.MUST_FIX:
                must_fix_items.append(fb)

    must_fix_items.sort(key=lambda fb: fb.confidence, reverse=True)
    return [
        f"{fb.id}: {fb.one_liner} (must_fix)"
        for fb in must_fix_items[:max_n]
    ]


def render_human_readable_text(
    key_findings: str,
    severity_dist: Dict[str, int],
    dimensions_with_issues: List[str],
    dimensions_clean: List[str],
    highlights: List[str],
) -> str:
    """Render a markdown-formatted human-readable summary.

    Format follows the example in PROJECT_SPEC.md §10.
    """
    lines: List[str] = []
    lines.append("## Review Summary")
    lines.append("")
    lines.append(f"**主要發現**: {key_findings}" if key_findings else "**主要發現**: 無")
    lines.append("")
    lines.append(
        f"**問題分布**: "
        f"{severity_dist.get('must_fix', 0)} 個必修、"
        f"{severity_dist.get('should_fix', 0)} 個建議修、"
        f"{severity_dist.get('nice_to_fix', 0)} 個可選修"
    )
    lines.append("")

    if dimensions_with_issues:
        lines.append(f"**有問題的維度**: {', '.join(dimensions_with_issues)}")
    else:
        lines.append("**有問題的維度**: 無")

    if dimensions_clean:
        lines.append(f"**乾淨的維度**: {', '.join(dimensions_clean)}")
    else:
        lines.append("**乾淨的維度**: 無")

    lines.append("")

    if highlights:
        lines.append("**重點問題**:")
        for h in highlights:
            lines.append(f"- {h}")
    else:
        lines.append("**重點問題**: 無")

    lines.append("")
    lines.append("詳細 feedback 請見結構化 JSON 輸出。")

    return "\n".join(lines)
