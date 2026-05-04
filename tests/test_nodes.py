"""Tests for reviewer nodes — uses mock LLM, no real API calls."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from reviewer.nodes import (
    AllRetriesFailedError,
    CompletenessNode,
    InformationRecallNode,
    LogicalCoherenceNode,
    PresentationSpecificityNode,
    QuestionAlignmentNode,
    ReviewerNodeBase,
    SourceQualityNode,
)
from reviewer.schemas import DimensionStatus, Severity
from reviewer.state import create_initial_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_llm_json(
    dimension: str = "question_alignment",
    code: str = "QA",
) -> str:
    """Return a valid JSON response string for a dimension."""
    return json.dumps({
        "dimension": dimension,
        "dimension_summary": "報告基本對齊主問題。",
        "confidence": 0.85,
        "top_feedback": [
            {
                "id": f"{code}-001",
                "severity": "must_fix",
                "one_liner": "報告偏離主題",
                "detail": "報告未回答核心問題。",
                "evidence_in_report": "報告第二段提到...",
                "fix_type": "rewrite_section",
                "fix_target": "section 2",
                "fix_hint": "重新聚焦於核心問題",
                "verification_level": "text_only",
                "confidence": 0.9,
                "source_verification": None,
                "external_check_result": None,
            }
        ],
        "additional_observations": [],
    }, ensure_ascii=False)


def _make_mock_response(content: str) -> MagicMock:
    """Create a mock AIMessage-like response."""
    mock = MagicMock()
    mock.content = content
    mock.response_metadata = {
        "token_usage": {"total_tokens": 500, "prompt_tokens": 400, "completion_tokens": 100}
    }
    return mock


def _make_state() -> dict:
    """Create a minimal state for testing nodes."""
    return create_initial_state(
        task="比較 Apple 與 Samsung 的策略",
        report="這是一份測試報告。" * 20,
    )


# ---------------------------------------------------------------------------
# Node attribute tests
# ---------------------------------------------------------------------------

ALL_NODES = [
    (QuestionAlignmentNode, "QA", "question_alignment", "qa_review", "qa_raw"),
    (InformationRecallNode, "IR", "information_recall", "ir_review", "ir_raw"),
    (CompletenessNode, "CP", "completeness", "cp_review", "cp_raw"),
    (LogicalCoherenceNode, "LC", "logical_coherence", "lc_review", "lc_raw"),
    (SourceQualityNode, "SQ", "source_quality", "sq_review", "sq_raw"),
    (PresentationSpecificityNode, "PS", "presentation_specificity", "ps_review", "ps_raw"),
]


class TestNodeAttributes:
    """Verify each node has correct class attributes."""

    @pytest.mark.parametrize(
        "node_cls, code, full_name, review_key, raw_key",
        ALL_NODES,
    )
    def test_attributes(self, node_cls, code, full_name, review_key, raw_key):
        assert node_cls.dimension_code == code
        assert node_cls.dimension_full_name == full_name
        assert node_cls.state_review_key == review_key
        assert node_cls.state_raw_key == raw_key


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestNodeHappyPath:
    """Test node with valid LLM response."""

    @patch("reviewer.nodes.base.time.sleep")
    def test_valid_response_parses_correctly(self, mock_sleep):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_mock_response(
            _make_valid_llm_json("question_alignment", "QA")
        )

        node = QuestionAlignmentNode(mock_llm)
        state = _make_state()
        result = node(state)

        assert "qa_review" in result
        assert "qa_raw" in result
        assert result["qa_review"].status == DimensionStatus.COMPLETED
        assert result["qa_review"].dimension == "question_alignment"
        assert len(result["qa_review"].top_feedback) == 1
        assert result["qa_review"].top_feedback[0].severity == Severity.MUST_FIX
        mock_sleep.assert_not_called()

    @patch("reviewer.nodes.base.time.sleep")
    def test_token_tracking(self, mock_sleep):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_mock_response(
            _make_valid_llm_json("question_alignment", "QA")
        )

        node = QuestionAlignmentNode(mock_llm)
        state = _make_state()
        result = node(state)

        assert result["total_tokens"] == 500  # reducer handles accumulation

    @patch("reviewer.nodes.base.time.sleep")
    def test_json_in_fenced_block(self, mock_sleep):
        """LLM wraps JSON in ```json ... ```."""
        fenced = f"Here is the result:\n```json\n{_make_valid_llm_json('question_alignment', 'QA')}\n```"
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_mock_response(fenced)

        node = QuestionAlignmentNode(mock_llm)
        result = node(_make_state())

        assert result["qa_review"].status == DimensionStatus.COMPLETED


# ---------------------------------------------------------------------------
# Retry on invalid JSON
# ---------------------------------------------------------------------------

class TestNodeRetry:
    """Test retry behavior on various failure modes."""

    @patch("reviewer.nodes.base.time.sleep")
    def test_invalid_json_triggers_retry_then_succeeds(self, mock_sleep):
        mock_llm = MagicMock()
        # First call: invalid JSON. Second call: valid.
        mock_llm.invoke.side_effect = [
            _make_mock_response("this is not json"),
            _make_mock_response(_make_valid_llm_json("question_alignment", "QA")),
        ]

        node = QuestionAlignmentNode(mock_llm)
        result = node(_make_state())

        assert result["qa_review"].status == DimensionStatus.COMPLETED
        assert mock_llm.invoke.call_count == 2
        mock_sleep.assert_called_once_with(2)  # first retry: 2^1 = 2

    @patch("reviewer.nodes.base.time.sleep")
    def test_three_failures_returns_failed_review(self, mock_sleep):
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            _make_mock_response("not json 1"),
            _make_mock_response("not json 2"),
            _make_mock_response("not json 3"),
        ]

        node = QuestionAlignmentNode(mock_llm)
        state = _make_state()
        result = node(state)

        assert result["qa_review"].status == DimensionStatus.FAILED
        assert result["qa_review"].confidence == 0.0
        assert result["qa_review"].top_feedback == []
        assert result["qa_raw"] is None
        assert "QA" in result["failed_dimensions"]
        assert mock_sleep.call_count == 2  # sleeps between attempts 1-2, 2-3

    @patch("reviewer.nodes.base.time.sleep")
    def test_api_error_triggers_retry(self, mock_sleep):
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            Exception("API timeout"),
            _make_mock_response(_make_valid_llm_json("question_alignment", "QA")),
        ]

        node = QuestionAlignmentNode(mock_llm)
        result = node(_make_state())

        assert result["qa_review"].status == DimensionStatus.COMPLETED

    @patch("reviewer.nodes.base.time.sleep")
    def test_nice_to_fix_in_top_feedback_triggers_retry(self, mock_sleep):
        """If LLM puts nice_to_fix in top_feedback, Pydantic validation fails → retry."""
        bad_json = json.dumps({
            "dimension": "question_alignment",
            "dimension_summary": "Summary.",
            "confidence": 0.8,
            "top_feedback": [
                {
                    "id": "QA-001",
                    "severity": "nice_to_fix",  # This should NOT be in top_feedback
                    "one_liner": "小問題",
                    "detail": "Detail.",
                    "evidence_in_report": "Evidence.",
                    "fix_type": "reformat",
                    "fix_target": "section 1",
                    "fix_hint": "Fix hint.",
                    "verification_level": "text_only",
                    "confidence": 0.3,
                    "source_verification": None,
                    "external_check_result": None,
                }
            ],
            "additional_observations": [],
        }, ensure_ascii=False)

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            _make_mock_response(bad_json),
            _make_mock_response(_make_valid_llm_json("question_alignment", "QA")),
        ]

        node = QuestionAlignmentNode(mock_llm)
        result = node(_make_state())

        # Should have retried and succeeded
        assert result["qa_review"].status == DimensionStatus.COMPLETED
        assert mock_llm.invoke.call_count == 2

    @patch("reviewer.nodes.base.time.sleep")
    def test_over_5_top_feedback_triggers_retry(self, mock_sleep):
        """If LLM returns > 5 top_feedback, validation fails → retry."""
        feedbacks = [
            {
                "id": f"QA-{i:03d}",
                "severity": "must_fix",
                "one_liner": f"問題 {i}",
                "detail": "Detail.",
                "evidence_in_report": "Evidence.",
                "fix_type": "rewrite_section",
                "fix_target": "section",
                "fix_hint": "Fix.",
                "verification_level": "text_only",
                "confidence": 0.9,
                "source_verification": None,
                "external_check_result": None,
            }
            for i in range(1, 7)  # 6 items, exceeds max of 5
        ]
        bad_json = json.dumps({
            "dimension": "question_alignment",
            "dimension_summary": "Summary.",
            "confidence": 0.8,
            "top_feedback": feedbacks,
            "additional_observations": [],
        }, ensure_ascii=False)

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            _make_mock_response(bad_json),
            _make_mock_response(_make_valid_llm_json("question_alignment", "QA")),
        ]

        node = QuestionAlignmentNode(mock_llm)
        result = node(_make_state())

        assert result["qa_review"].status == DimensionStatus.COMPLETED
        assert mock_llm.invoke.call_count == 2

    @patch("reviewer.nodes.base.time.sleep")
    def test_dimension_mismatch_triggers_retry(self, mock_sleep):
        """If LLM returns wrong dimension name, retry."""
        wrong_dim_json = _make_valid_llm_json("completeness", "CP")

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            _make_mock_response(wrong_dim_json),
            _make_mock_response(_make_valid_llm_json("question_alignment", "QA")),
        ]

        node = QuestionAlignmentNode(mock_llm)
        result = node(_make_state())

        assert result["qa_review"].status == DimensionStatus.COMPLETED
        assert result["qa_review"].dimension == "question_alignment"
        assert mock_llm.invoke.call_count == 2


# ---------------------------------------------------------------------------
# Exponential backoff
# ---------------------------------------------------------------------------

class TestExponentialBackoff:
    """Test that retry delays follow exponential backoff."""

    @patch("reviewer.nodes.base.time.sleep")
    def test_backoff_delays(self, mock_sleep):
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            _make_mock_response("fail 1"),
            _make_mock_response("fail 2"),
            _make_mock_response("fail 3"),
        ]

        node = QuestionAlignmentNode(mock_llm)
        node(_make_state())

        # Should have slept twice: 2s and 4s
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(2)
        mock_sleep.assert_any_call(4)
