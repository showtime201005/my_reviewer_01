"""End-to-end tests for the reviewer graph using mock LLM."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from reviewer.graph import build_reviewer_graph
from reviewer.nodes.input_validator import InputValidationError
from reviewer.schemas import DimensionStatus, ReviewOutput
from reviewer.state import create_initial_state

from tests.conftest import MockChatOpenAI, build_responses

SAMPLE_TASK = "比較 Apple 與 Samsung 2024 年的智慧手機策略"
SAMPLE_REPORT = "這是一份關於 Apple 與 Samsung 智慧手機策略的測試報告。" * 10  # > 100 chars


def _run_graph(responses: dict, task: str = SAMPLE_TASK, report: str = SAMPLE_REPORT) -> ReviewOutput:
    """Helper: build graph with mock LLM, invoke, return ReviewOutput."""
    mock_llm = MockChatOpenAI(responses)
    graph = build_reviewer_graph(llm=mock_llm)
    state = create_initial_state(task=task, report=report)
    final_state = graph.invoke(state)
    return final_state["final_output"]


# ---------------------------------------------------------------------------
# 1. Full success with mixed issues
# ---------------------------------------------------------------------------

class TestFullSuccessMixed:
    """Mixed responses: some dimensions have issues, some are clean."""

    @patch("reviewer.nodes.base.time.sleep")
    def test_all_6_dimensions_present(self, mock_sleep):
        responses = build_responses(
            issues_for={"QA", "IR", "LC"},
            nice_to_fix_for={"QA"},
        )
        output = _run_graph(responses)

        assert isinstance(output, ReviewOutput)
        assert len(output.dimension_reviews) == 6

    @patch("reviewer.nodes.base.time.sleep")
    def test_dimensions_with_issues_correct(self, mock_sleep):
        responses = build_responses(issues_for={"QA", "IR", "LC"})
        output = _run_graph(responses)

        assert set(output.human_summary.dimensions_with_issues) == {"QA", "IR", "LC"}
        assert set(output.human_summary.dimensions_clean) == {"CP", "SQ", "PS"}

    @patch("reviewer.nodes.base.time.sleep")
    def test_severity_distribution_reflects_issues(self, mock_sleep):
        responses = build_responses(
            issues_for={"QA", "IR"},
            nice_to_fix_for={"QA"},
        )
        output = _run_graph(responses)
        dist = output.human_summary.severity_distribution

        assert dist["must_fix"] == 2   # QA-001, IR-001
        assert dist["should_fix"] == 2  # QA-002, IR-002
        assert dist["nice_to_fix"] == 1  # QA-003 from additional_observations

    @patch("reviewer.nodes.base.time.sleep")
    def test_additional_observations_populated(self, mock_sleep):
        responses = build_responses(
            issues_for={"QA"},
            nice_to_fix_for={"QA", "IR"},
        )
        output = _run_graph(responses)

        assert len(output.additional_observations) == 2


# ---------------------------------------------------------------------------
# 2. All clean report
# ---------------------------------------------------------------------------

class TestAllClean:
    """No dimension has must_fix or should_fix."""

    @patch("reviewer.nodes.base.time.sleep")
    def test_all_dimensions_clean(self, mock_sleep):
        responses = build_responses()  # no issues at all
        output = _run_graph(responses)

        assert output.human_summary.dimensions_with_issues == []
        assert set(output.human_summary.dimensions_clean) == {
            "QA", "IR", "CP", "LC", "SQ", "PS"
        }

    @patch("reviewer.nodes.base.time.sleep")
    def test_severity_all_zero(self, mock_sleep):
        responses = build_responses()
        output = _run_graph(responses)
        dist = output.human_summary.severity_distribution

        assert dist["must_fix"] == 0
        assert dist["should_fix"] == 0
        assert dist["nice_to_fix"] == 0

    @patch("reviewer.nodes.base.time.sleep")
    def test_highlights_empty(self, mock_sleep):
        responses = build_responses()
        output = _run_graph(responses)
        assert output.human_summary.highlights == []


# ---------------------------------------------------------------------------
# 3. All bad report — every dimension has issues
# ---------------------------------------------------------------------------

class TestAllBad:
    """Every dimension has must_fix and should_fix."""

    @patch("reviewer.nodes.base.time.sleep")
    def test_all_dimensions_have_issues(self, mock_sleep):
        responses = build_responses(
            issues_for={"QA", "IR", "CP", "LC", "SQ", "PS"},
        )
        output = _run_graph(responses)

        assert set(output.human_summary.dimensions_with_issues) == {
            "QA", "IR", "CP", "LC", "SQ", "PS"
        }
        assert output.human_summary.dimensions_clean == []

    @patch("reviewer.nodes.base.time.sleep")
    def test_highlights_not_empty(self, mock_sleep):
        responses = build_responses(
            issues_for={"QA", "IR", "CP", "LC", "SQ", "PS"},
        )
        output = _run_graph(responses)
        assert len(output.human_summary.highlights) > 0
        assert len(output.human_summary.highlights) <= 5

    @patch("reviewer.nodes.base.time.sleep")
    def test_severity_counts(self, mock_sleep):
        responses = build_responses(
            issues_for={"QA", "IR", "CP", "LC", "SQ", "PS"},
        )
        output = _run_graph(responses)
        dist = output.human_summary.severity_distribution

        assert dist["must_fix"] == 6   # 1 per dimension
        assert dist["should_fix"] == 6  # 1 per dimension


# ---------------------------------------------------------------------------
# 4. Partial dimension failure
# ---------------------------------------------------------------------------

class TestPartialFailure:
    """One dimension fails (invalid JSON 3x), others succeed."""

    @patch("reviewer.nodes.base.time.sleep")
    def test_failed_dimension_marked(self, mock_sleep):
        responses = build_responses(
            issues_for={"QA"},
            fail_for={"SQ"},
        )
        output = _run_graph(responses)

        sq = output.dimension_reviews["source_quality"]
        assert sq.status == DimensionStatus.FAILED
        assert sq.confidence == 0.0
        assert sq.top_feedback == []

    @patch("reviewer.nodes.base.time.sleep")
    def test_failed_dimensions_in_metadata(self, mock_sleep):
        responses = build_responses(fail_for={"SQ"})
        output = _run_graph(responses)

        assert "SQ" in output.review_metadata.failed_dimensions

    @patch("reviewer.nodes.base.time.sleep")
    def test_other_dimensions_succeed(self, mock_sleep):
        responses = build_responses(
            issues_for={"QA"},
            fail_for={"SQ"},
        )
        output = _run_graph(responses)

        qa = output.dimension_reviews["question_alignment"]
        assert qa.status == DimensionStatus.COMPLETED
        assert len(qa.top_feedback) == 2

    @patch("reviewer.nodes.base.time.sleep")
    def test_still_produces_full_output(self, mock_sleep):
        responses = build_responses(fail_for={"SQ"})
        output = _run_graph(responses)

        assert isinstance(output, ReviewOutput)
        assert len(output.dimension_reviews) == 6


# ---------------------------------------------------------------------------
# 5. All dimensions fail
# ---------------------------------------------------------------------------

class TestAllFail:
    """Every dimension returns invalid JSON — all fail after retries."""

    @patch("reviewer.nodes.base.time.sleep")
    def test_all_failed(self, mock_sleep):
        responses = build_responses(
            fail_for={"QA", "IR", "CP", "LC", "SQ", "PS"},
        )
        output = _run_graph(responses)

        assert len(output.review_metadata.failed_dimensions) == 6
        for dr in output.dimension_reviews.values():
            assert dr.status == DimensionStatus.FAILED

    @patch("reviewer.nodes.base.time.sleep")
    def test_still_produces_review_output(self, mock_sleep):
        responses = build_responses(
            fail_for={"QA", "IR", "CP", "LC", "SQ", "PS"},
        )
        output = _run_graph(responses)

        assert isinstance(output, ReviewOutput)
        assert output.human_summary.severity_distribution["must_fix"] == 0


# ---------------------------------------------------------------------------
# 6 & 7. Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:
    """Test input_validator_node rejects bad input."""

    @patch("reviewer.nodes.base.time.sleep")
    def test_empty_task_raises(self, mock_sleep):
        responses = build_responses()
        mock_llm = MockChatOpenAI(responses)
        graph = build_reviewer_graph(llm=mock_llm)
        state = create_initial_state(task="", report="A" * 200)

        with pytest.raises(InputValidationError, match="task is empty"):
            graph.invoke(state)

    @patch("reviewer.nodes.base.time.sleep")
    def test_whitespace_task_raises(self, mock_sleep):
        responses = build_responses()
        mock_llm = MockChatOpenAI(responses)
        graph = build_reviewer_graph(llm=mock_llm)
        state = create_initial_state(task="   ", report="A" * 200)

        with pytest.raises(InputValidationError, match="task is empty"):
            graph.invoke(state)

    @patch("reviewer.nodes.base.time.sleep")
    def test_short_report_raises(self, mock_sleep):
        responses = build_responses()
        mock_llm = MockChatOpenAI(responses)
        graph = build_reviewer_graph(llm=mock_llm)
        state = create_initial_state(task="valid task", report="too short")

        with pytest.raises(InputValidationError, match="report too short"):
            graph.invoke(state)

    @patch("reviewer.nodes.base.time.sleep")
    def test_valid_input_passes(self, mock_sleep):
        responses = build_responses()
        output = _run_graph(responses)
        assert isinstance(output, ReviewOutput)


# ---------------------------------------------------------------------------
# Metadata checks
# ---------------------------------------------------------------------------

class TestMetadata:
    """Verify metadata fields in the output."""

    @patch("reviewer.nodes.base.time.sleep")
    def test_reviewer_version(self, mock_sleep):
        responses = build_responses()
        output = _run_graph(responses)
        assert output.review_metadata.reviewer_version == "v1.0-passive"

    @patch("reviewer.nodes.base.time.sleep")
    def test_active_verification_false(self, mock_sleep):
        responses = build_responses()
        output = _run_graph(responses)
        assert output.review_metadata.active_verification_used is False

    @patch("reviewer.nodes.base.time.sleep")
    def test_v2_interface_null(self, mock_sleep):
        responses = build_responses()
        output = _run_graph(responses)
        assert output.v2_interface.citation_sources is None

    @patch("reviewer.nodes.base.time.sleep")
    def test_human_readable_text_present(self, mock_sleep):
        responses = build_responses(issues_for={"QA"})
        output = _run_graph(responses)
        assert "Review Summary" in output.human_readable_text
        assert "必修" in output.human_readable_text
