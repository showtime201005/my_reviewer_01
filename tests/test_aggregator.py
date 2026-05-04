"""Tests for reviewer.aggregator — pure Python aggregation logic."""

import pytest

from reviewer.aggregator import aggregate, render_human_readable_text
from reviewer.schemas import (
    DimensionStatus,
    Severity,
)

from tests.conftest import (
    make_dimension_llm_output,
    make_dimension_review,
    make_feedback,
    make_full_state,
)


class TestAggregateHappyPath:
    """Test aggregation with a mix of issues and clean dimensions."""

    def test_all_dimensions_present(self):
        state = make_full_state(with_issues=True)
        result = aggregate(state)
        assert len(result.dimension_reviews) == 6

    def test_severity_distribution_correct(self):
        state = make_full_state(with_issues=True)
        result = aggregate(state)
        dist = result.human_summary.severity_distribution
        # QA: 1 must_fix + 1 should_fix, IR: 1 must_fix + 1 should_fix
        # nice_to_fix come from additional_observations (QA-003, IR-003)
        assert dist["must_fix"] == 2
        assert dist["should_fix"] == 2
        assert dist["nice_to_fix"] == 2

    def test_dimensions_with_issues(self):
        state = make_full_state(with_issues=True)
        result = aggregate(state)
        assert set(result.human_summary.dimensions_with_issues) == {"QA", "IR"}

    def test_dimensions_clean(self):
        state = make_full_state(with_issues=True)
        result = aggregate(state)
        assert set(result.human_summary.dimensions_clean) == {"CP", "LC", "SQ", "PS"}

    def test_union_covers_all(self):
        state = make_full_state(with_issues=True)
        result = aggregate(state)
        union = set(result.human_summary.dimensions_with_issues) | set(
            result.human_summary.dimensions_clean
        )
        assert union == {"QA", "IR", "CP", "LC", "SQ", "PS"}

    def test_metadata(self):
        state = make_full_state(with_issues=True)
        result = aggregate(state)
        assert result.review_metadata.reviewer_version == "v1.0-passive"
        assert result.review_metadata.task_id == "test-task-id"
        assert result.review_metadata.active_verification_used is False

    def test_v2_interface_null(self):
        state = make_full_state(with_issues=True)
        result = aggregate(state)
        assert result.v2_interface.citation_sources is None
        assert result.v2_interface.external_searches_performed == []
        assert result.v2_interface.fact_check_results == []


class TestAggregateNiceToFix:
    """Test that nice_to_fix items go to additional_observations."""

    def test_nice_to_fix_in_additional(self):
        state = make_full_state(with_issues=True)
        result = aggregate(state)
        assert len(result.additional_observations) == 2  # QA-003, IR-003
        for fb in result.additional_observations:
            assert fb.severity == Severity.NICE_TO_FIX

    def test_nice_to_fix_not_in_top_feedback(self):
        state = make_full_state(with_issues=True)
        result = aggregate(state)
        for dr in result.dimension_reviews.values():
            for fb in dr.top_feedback:
                assert fb.severity != Severity.NICE_TO_FIX


class TestAggregateHighlights:
    """Test highlights extraction from must_fix items."""

    def test_highlights_only_must_fix(self):
        state = make_full_state(with_issues=True)
        result = aggregate(state)
        for h in result.human_summary.highlights:
            assert "must_fix" in h

    def test_highlights_sorted_by_confidence_desc(self):
        state = make_full_state(with_issues=True)
        result = aggregate(state)
        # QA-001 confidence=0.9, IR-001 confidence=0.85
        assert len(result.human_summary.highlights) == 2
        assert "QA-001" in result.human_summary.highlights[0]
        assert "IR-001" in result.human_summary.highlights[1]

    def test_highlights_max_5(self):
        state = make_full_state(with_issues=True)
        result = aggregate(state)
        assert len(result.human_summary.highlights) <= 5


class TestAggregateFailedDimensions:
    """Test aggregation with some dimensions failed."""

    def test_failed_dimension_summary(self):
        state = make_full_state(with_issues=True, failed_dims=["SQ"])
        result = aggregate(state)
        sq = result.dimension_reviews["source_quality"]
        assert sq.status == DimensionStatus.FAILED
        assert "失敗" in sq.dimension_summary
        assert sq.confidence == 0.0
        assert sq.top_feedback == []

    def test_failed_dimension_in_clean(self):
        """Failed dims with no must/should feedback end up in 'clean'."""
        state = make_full_state(with_issues=True, failed_dims=["SQ"])
        result = aggregate(state)
        # SQ has no must/should feedback (it's failed), so it goes to clean
        assert "SQ" in result.human_summary.dimensions_clean

    def test_other_dimensions_unaffected(self):
        state = make_full_state(with_issues=True, failed_dims=["SQ"])
        result = aggregate(state)
        qa = result.dimension_reviews["question_alignment"]
        assert qa.status == DimensionStatus.COMPLETED
        assert len(qa.top_feedback) == 2


class TestAggregateAllClean:
    """Test aggregation when no dimension has must_fix or should_fix."""

    def test_all_clean(self):
        state = make_full_state(with_issues=False)
        result = aggregate(state)
        assert set(result.human_summary.dimensions_clean) == {
            "QA", "IR", "CP", "LC", "SQ", "PS"
        }
        assert result.human_summary.dimensions_with_issues == []

    def test_no_highlights_when_clean(self):
        state = make_full_state(with_issues=False)
        result = aggregate(state)
        assert result.human_summary.highlights == []

    def test_severity_all_zero_when_clean(self):
        state = make_full_state(with_issues=False)
        result = aggregate(state)
        dist = result.human_summary.severity_distribution
        assert dist["must_fix"] == 0
        assert dist["should_fix"] == 0
        assert dist["nice_to_fix"] == 0


class TestRenderHumanReadableText:
    """Test the human-readable text rendering."""

    def test_contains_key_findings(self):
        text = render_human_readable_text(
            key_findings="報告主題偏移。",
            severity_dist={"must_fix": 1, "should_fix": 0, "nice_to_fix": 0},
            dimensions_with_issues=["QA"],
            dimensions_clean=["IR", "CP", "LC", "SQ", "PS"],
            highlights=["QA-001: 偏離主題 (must_fix)"],
        )
        assert "報告主題偏移" in text

    def test_contains_severity_counts(self):
        text = render_human_readable_text(
            key_findings="Some findings.",
            severity_dist={"must_fix": 3, "should_fix": 8, "nice_to_fix": 12},
            dimensions_with_issues=["IR", "LC", "SQ"],
            dimensions_clean=["QA", "CP", "PS"],
            highlights=["IR-001: issue (must_fix)"],
        )
        assert "3 個必修" in text
        assert "8 個建議修" in text
        assert "12 個可選修" in text

    def test_contains_dimension_info(self):
        text = render_human_readable_text(
            key_findings="Findings.",
            severity_dist={"must_fix": 0, "should_fix": 0, "nice_to_fix": 0},
            dimensions_with_issues=[],
            dimensions_clean=["QA", "IR", "CP", "LC", "SQ", "PS"],
            highlights=[],
        )
        assert "QA" in text
        assert "Review Summary" in text

    def test_contains_highlights(self):
        text = render_human_readable_text(
            key_findings="Findings.",
            severity_dist={"must_fix": 1, "should_fix": 0, "nice_to_fix": 0},
            dimensions_with_issues=["QA"],
            dimensions_clean=["IR", "CP", "LC", "SQ", "PS"],
            highlights=["QA-001: 偏離主題 (must_fix)"],
        )
        assert "QA-001" in text
        assert "偏離主題" in text

    def test_integration_from_aggregate(self):
        state = make_full_state(with_issues=True)
        result = aggregate(state)
        text = result.human_readable_text
        assert "Review Summary" in text
        assert "必修" in text
