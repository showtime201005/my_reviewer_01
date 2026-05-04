"""Shared test fixtures for the reviewer test suite."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

import pytest

from reviewer.schemas import (
    DimensionLLMOutput,
    DimensionReview,
    DimensionStatus,
    Feedback,
    FixType,
    Severity,
    VerificationLevel,
)
from reviewer.state import ReviewerState


# ---------------------------------------------------------------------------
# Dimension metadata used across fixtures
# ---------------------------------------------------------------------------

DIMENSIONS = [
    ("question_alignment", "QA"),
    ("information_recall", "IR"),
    ("completeness", "CP"),
    ("logical_coherence", "LC"),
    ("source_quality", "SQ"),
    ("presentation_specificity", "PS"),
]


# ---------------------------------------------------------------------------
# MockChatOpenAI — detects dimension from prompt and returns canned JSON
# ---------------------------------------------------------------------------

class MockChatOpenAI:
    """A mock LLM that returns pre-configured JSON for each dimension.

    Detects which dimension is being called by searching the prompt for
    the dimension full name inside the ``"dimension":`` marker.
    """

    def __init__(self, responses: dict[str, str]) -> None:
        """
        Args:
            responses: Mapping from dimension full name to JSON response string.
                       Use ``None`` as value to make that dimension raise an exception.
        """
        self.responses = responses
        self.call_log: list[str] = []

    def invoke(self, messages) -> MagicMock:
        prompt_text = messages[-1].content
        dimension = self._detect_dimension(prompt_text)
        self.call_log.append(dimension)

        response_text = self.responses.get(dimension)
        if response_text is None:
            raise RuntimeError(f"MockChatOpenAI: no response for '{dimension}'")

        mock_resp = MagicMock()
        mock_resp.content = response_text
        mock_resp.response_metadata = {
            "token_usage": {"total_tokens": 500, "prompt_tokens": 400, "completion_tokens": 100}
        }
        return mock_resp

    def _detect_dimension(self, prompt: str) -> str:
        # First pass: look for the exact JSON marker in the output_format section
        for dim_name, _ in DIMENSIONS:
            if f'"dimension": "{dim_name}"' in prompt or f'"dimension":"{dim_name}"' in prompt:
                return dim_name
        # Second pass: match by the <role> tag content which is unique per dimension
        prompt_lower = prompt.lower()
        # Order matters: check longer/more specific names first to avoid false matches
        role_markers = [
            ("presentation_specificity", "presentation & specificity"),
            ("question_alignment", "question alignment"),
            ("information_recall", "information recall"),
            ("logical_coherence", "logical coherence"),
            ("source_quality", "source quality"),
            ("completeness", "completeness"),
        ]
        for dim_name, marker in role_markers:
            # Match in the <role> section specifically
            role_start = prompt_lower.find("<role>")
            role_end = prompt_lower.find("</role>")
            if role_start != -1 and role_end != -1:
                role_section = prompt_lower[role_start:role_end]
                if marker in role_section:
                    return dim_name
        return "unknown"


# ---------------------------------------------------------------------------
# JSON response builders
# ---------------------------------------------------------------------------

def make_mock_json(
    dimension: str,
    code: str,
    *,
    has_issues: bool = False,
    nice_to_fix: bool = False,
) -> str:
    """Build a valid JSON response string for a dimension.

    Args:
        dimension: Full dimension name (e.g. "question_alignment").
        code: Dimension code (e.g. "QA").
        has_issues: If True, include must_fix and should_fix feedback.
        nice_to_fix: If True, include nice_to_fix in additional_observations.
    """
    top_feedback = []
    additional_observations = []

    if has_issues:
        top_feedback = [
            {
                "id": f"{code}-001",
                "severity": "must_fix",
                "one_liner": f"{code} 核心問題",
                "detail": f"{dimension} 維度發現嚴重問題。",
                "evidence_in_report": "報告中提到...",
                "fix_type": "rewrite_section",
                "fix_target": "section 1",
                "fix_hint": "需要重寫此部分",
                "verification_level": "text_only",
                "confidence": 0.9,
                "source_verification": None,
                "external_check_result": None,
            },
            {
                "id": f"{code}-002",
                "severity": "should_fix",
                "one_liner": f"{code} 次要問題",
                "detail": f"{dimension} 維度發現次要問題。",
                "evidence_in_report": "報告另一處提到...",
                "fix_type": "add_perspective",
                "fix_target": "section 2",
                "fix_hint": "補充觀點",
                "verification_level": "text_only",
                "confidence": 0.75,
                "source_verification": None,
                "external_check_result": None,
            },
        ]

    if nice_to_fix:
        additional_observations = [
            {
                "id": f"{code}-003",
                "severity": "nice_to_fix",
                "one_liner": f"{code} 小建議",
                "detail": "邊際改善。",
                "evidence_in_report": "報告提到...",
                "fix_type": "reformat",
                "fix_target": "formatting",
                "fix_hint": "調整格式",
                "verification_level": "text_only",
                "confidence": 0.4,
                "source_verification": None,
                "external_check_result": None,
            }
        ]

    return json.dumps({
        "dimension": dimension,
        "dimension_summary": f"{dimension} 維度分析完成。",
        "confidence": 0.85,
        "top_feedback": top_feedback,
        "additional_observations": additional_observations,
    }, ensure_ascii=False)


def build_responses(
    *,
    issues_for: set[str] | None = None,
    nice_to_fix_for: set[str] | None = None,
    fail_for: set[str] | None = None,
) -> dict[str, str | None]:
    """Build a full set of mock responses for all 6 dimensions.

    Args:
        issues_for: Set of dimension codes that should have must_fix/should_fix.
        nice_to_fix_for: Set of dimension codes that should have nice_to_fix observations.
        fail_for: Set of dimension codes that should return invalid JSON (trigger failure).
    """
    issues_for = issues_for or set()
    nice_to_fix_for = nice_to_fix_for or set()
    fail_for = fail_for or set()

    responses = {}
    for dim_name, code in DIMENSIONS:
        if code in fail_for:
            responses[dim_name] = "this is not valid json at all"
        else:
            responses[dim_name] = make_mock_json(
                dim_name, code,
                has_issues=code in issues_for,
                nice_to_fix=code in nice_to_fix_for,
            )
    return responses


def make_feedback(
    *,
    id: str = "QA-001",
    severity: Severity = Severity.MUST_FIX,
    one_liner: str = "報告偏離主題",
    detail: str = "報告未回答核心問題，偏向討論次要議題。",
    evidence_in_report: str = "報告第二段提到...",
    fix_type: FixType = FixType.REWRITE_SECTION,
    fix_target: str = "section 2",
    fix_hint: str = "重新聚焦於核心問題",
    verification_level: VerificationLevel = VerificationLevel.TEXT_ONLY,
    confidence: float = 0.9,
) -> Feedback:
    """Create a Feedback instance with sensible defaults."""
    return Feedback(
        id=id,
        severity=severity,
        one_liner=one_liner,
        detail=detail,
        evidence_in_report=evidence_in_report,
        fix_type=fix_type,
        fix_target=fix_target,
        fix_hint=fix_hint,
        verification_level=verification_level,
        confidence=confidence,
    )


def make_dimension_review(
    *,
    dimension: str = "question_alignment",
    dimension_summary: str = "報告基本對齊主問題，但有輕微偏移。",
    confidence: float = 0.85,
    top_feedback: list[Feedback] | None = None,
    status: DimensionStatus = DimensionStatus.COMPLETED,
) -> DimensionReview:
    """Create a DimensionReview instance with sensible defaults."""
    return DimensionReview(
        dimension=dimension,
        dimension_summary=dimension_summary,
        confidence=confidence,
        top_feedback=top_feedback if top_feedback is not None else [],
        status=status,
    )


def make_dimension_llm_output(
    *,
    dimension: str = "question_alignment",
    dimension_summary: str = "報告基本對齊主問題。",
    confidence: float = 0.85,
    top_feedback: list[Feedback] | None = None,
    additional_observations: list[Feedback] | None = None,
) -> DimensionLLMOutput:
    """Create a DimensionLLMOutput instance with sensible defaults."""
    return DimensionLLMOutput(
        dimension=dimension,
        dimension_summary=dimension_summary,
        confidence=confidence,
        top_feedback=top_feedback if top_feedback is not None else [],
        additional_observations=additional_observations if additional_observations is not None else [],
    )


def make_full_state(
    *,
    with_issues: bool = True,
    failed_dims: list[str] | None = None,
) -> ReviewerState:
    """Create a complete ReviewerState for aggregator testing.

    Args:
        with_issues: If True, QA and IR dimensions have must_fix/should_fix feedback.
        failed_dims: List of dimension codes to mark as failed (e.g. ["SQ"]).
    """
    failed_dims = failed_dims or []
    _failed_set = set(failed_dims)

    dims = [
        ("question_alignment", "qa_review", "qa_raw", "QA"),
        ("information_recall",  "ir_review", "ir_raw", "IR"),
        ("completeness",        "cp_review", "cp_raw", "CP"),
        ("logical_coherence",   "lc_review", "lc_raw", "LC"),
        ("source_quality",      "sq_review", "sq_raw", "SQ"),
        ("presentation_specificity", "ps_review", "ps_raw", "PS"),
    ]

    state: dict = {
        "task": "What are the benefits of microservices?",
        "report": "A" * 200,
        "task_id": "test-task-id",
        "report_id": "test-report-id",
        "start_time": time.time() - 10.0,  # started 10s ago
        "total_tokens": 5000,
        "failed_dimensions": list(failed_dims),
        "final_output": None,
    }

    for i, (dim_name, review_key, raw_key, code) in enumerate(dims):
        if code in _failed_set:
            state[review_key] = make_dimension_review(
                dimension=dim_name,
                dimension_summary="",
                confidence=0.0,
                top_feedback=[],
                status=DimensionStatus.FAILED,
            )
            state[raw_key] = None
            continue

        feedbacks: list[Feedback] = []
        nice_to_fix_obs: list[Feedback] = []

        if with_issues and code in ("QA", "IR"):
            feedbacks = [
                make_feedback(
                    id=f"{code}-001",
                    severity=Severity.MUST_FIX,
                    confidence=0.9 - i * 0.05,
                ),
                make_feedback(
                    id=f"{code}-002",
                    severity=Severity.SHOULD_FIX,
                    confidence=0.7,
                ),
            ]
            nice_to_fix_obs = [
                make_feedback(
                    id=f"{code}-003",
                    severity=Severity.NICE_TO_FIX,
                    confidence=0.4,
                ),
            ]

        state[review_key] = make_dimension_review(
            dimension=dim_name,
            dimension_summary=f"{dim_name} 維度分析完成。",
            confidence=0.85,
            top_feedback=feedbacks,
        )
        state[raw_key] = make_dimension_llm_output(
            dimension=dim_name,
            dimension_summary=f"{dim_name} 維度分析完成。",
            confidence=0.85,
            top_feedback=feedbacks,
            additional_observations=nice_to_fix_obs,
        )

    return state  # type: ignore[return-value]
