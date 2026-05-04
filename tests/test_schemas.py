"""Tests for reviewer.schemas — validators and model integrity."""

import pytest
from pydantic import ValidationError

from reviewer.schemas import (
    DimensionReview,
    DimensionStatus,
    Feedback,
    FixType,
    HumanSummary,
    Severity,
    VerificationLevel,
)

from tests.conftest import make_feedback, make_dimension_review


# ===================================================================
# Feedback validators
# ===================================================================

class TestFeedbackValidators:
    """Tests for Feedback field validators."""

    def test_valid_feedback(self):
        fb = make_feedback()
        assert fb.id == "QA-001"
        assert fb.severity == Severity.MUST_FIX

    # --- id format ---

    def test_id_lowercase_rejected(self):
        with pytest.raises(ValidationError, match="id must match"):
            make_feedback(id="qa-001")

    def test_id_missing_leading_zeros_rejected(self):
        with pytest.raises(ValidationError, match="id must match"):
            make_feedback(id="QA-1")

    def test_id_too_many_digits_rejected(self):
        with pytest.raises(ValidationError, match="id must match"):
            make_feedback(id="QA-0001")

    def test_id_wrong_prefix_length_rejected(self):
        with pytest.raises(ValidationError, match="id must match"):
            make_feedback(id="QAX-001")

    def test_id_valid_formats(self):
        for valid_id in ("QA-001", "IR-042", "PS-999"):
            fb = make_feedback(id=valid_id)
            assert fb.id == valid_id

    # --- one_liner length ---

    def test_one_liner_exactly_25_chars(self):
        fb = make_feedback(one_liner="a" * 25)
        assert len(fb.one_liner) == 25

    def test_one_liner_over_25_chars_rejected(self):
        with pytest.raises(ValidationError, match="one_liner must be"):
            make_feedback(one_liner="a" * 26)

    def test_one_liner_chinese_25_chars(self):
        fb = make_feedback(one_liner="報" * 25)
        assert len(fb.one_liner) == 25

    def test_one_liner_chinese_over_25_rejected(self):
        with pytest.raises(ValidationError, match="one_liner must be"):
            make_feedback(one_liner="報" * 26)

    # --- evidence_in_report ---

    def test_evidence_empty_string_rejected(self):
        with pytest.raises(ValidationError, match="evidence_in_report must not be empty"):
            make_feedback(evidence_in_report="")

    def test_evidence_whitespace_only_rejected(self):
        with pytest.raises(ValidationError, match="evidence_in_report must not be empty"):
            make_feedback(evidence_in_report="   ")

    # --- confidence ---

    def test_confidence_zero_ok(self):
        fb = make_feedback(confidence=0.0)
        assert fb.confidence == 0.0

    def test_confidence_one_ok(self):
        fb = make_feedback(confidence=1.0)
        assert fb.confidence == 1.0

    def test_confidence_negative_rejected(self):
        with pytest.raises(ValidationError):
            make_feedback(confidence=-0.1)

    def test_confidence_over_one_rejected(self):
        with pytest.raises(ValidationError):
            make_feedback(confidence=1.1)

    # --- v1 null constraints ---

    def test_source_verification_not_none_rejected(self):
        with pytest.raises(ValidationError, match="source_verification must be None in v1"):
            Feedback(
                id="QA-001",
                severity=Severity.MUST_FIX,
                one_liner="test",
                detail="detail",
                evidence_in_report="evidence",
                fix_type=FixType.REWRITE_SECTION,
                fix_target="section 1",
                fix_hint="fix it",
                verification_level=VerificationLevel.TEXT_ONLY,
                confidence=0.9,
                source_verification={"url": "http://example.com"},
            )

    def test_external_check_result_not_none_rejected(self):
        with pytest.raises(ValidationError, match="external_check_result must be None in v1"):
            Feedback(
                id="QA-001",
                severity=Severity.MUST_FIX,
                one_liner="test",
                detail="detail",
                evidence_in_report="evidence",
                fix_type=FixType.REWRITE_SECTION,
                fix_target="section 1",
                fix_hint="fix it",
                verification_level=VerificationLevel.TEXT_ONLY,
                confidence=0.9,
                external_check_result="some result",
            )


# ===================================================================
# DimensionReview validators
# ===================================================================

class TestDimensionReviewValidators:
    """Tests for DimensionReview field validators."""

    def test_valid_dimension_review(self):
        dr = make_dimension_review()
        assert dr.status == DimensionStatus.COMPLETED

    def test_top_feedback_max_5(self):
        feedbacks = [make_feedback(id=f"QA-{i:03d}") for i in range(1, 6)]
        dr = make_dimension_review(top_feedback=feedbacks)
        assert len(dr.top_feedback) == 5

    def test_top_feedback_over_5_rejected(self):
        feedbacks = [make_feedback(id=f"QA-{i:03d}") for i in range(1, 7)]
        with pytest.raises(ValidationError):
            make_dimension_review(top_feedback=feedbacks)

    def test_top_feedback_nice_to_fix_rejected(self):
        nice_fb = make_feedback(severity=Severity.NICE_TO_FIX)
        with pytest.raises(ValidationError, match="nice_to_fix"):
            make_dimension_review(top_feedback=[nice_fb])

    def test_top_feedback_must_fix_and_should_fix_ok(self):
        feedbacks = [
            make_feedback(id="QA-001", severity=Severity.MUST_FIX),
            make_feedback(id="QA-002", severity=Severity.SHOULD_FIX),
        ]
        dr = make_dimension_review(top_feedback=feedbacks)
        assert len(dr.top_feedback) == 2


# ===================================================================
# HumanSummary validators
# ===================================================================

class TestHumanSummaryValidators:
    """Tests for HumanSummary field validators."""

    def _make_summary(self, **overrides) -> HumanSummary:
        defaults = {
            "key_findings": "Some findings.",
            "severity_distribution": {"must_fix": 1, "should_fix": 2, "nice_to_fix": 3},
            "dimensions_with_issues": ["QA", "IR"],
            "dimensions_clean": ["CP", "LC", "SQ", "PS"],
            "highlights": ["QA-001: issue (must_fix)"],
        }
        defaults.update(overrides)
        return HumanSummary(**defaults)

    def test_valid_summary(self):
        s = self._make_summary()
        assert s.severity_distribution["must_fix"] == 1

    def test_severity_distribution_missing_key_rejected(self):
        with pytest.raises(ValidationError, match="severity_distribution must contain"):
            self._make_summary(severity_distribution={"must_fix": 1, "should_fix": 2})

    def test_severity_distribution_missing_must_fix_rejected(self):
        with pytest.raises(ValidationError, match="severity_distribution must contain"):
            self._make_summary(
                severity_distribution={"should_fix": 2, "nice_to_fix": 3}
            )

    def test_dimensions_union_incomplete_rejected(self):
        with pytest.raises(ValidationError, match="dimensions_with_issues ∪ dimensions_clean"):
            self._make_summary(
                dimensions_with_issues=["QA"],
                dimensions_clean=["IR"],  # missing CP, LC, SQ, PS
            )

    def test_dimensions_union_complete_with_all_in_issues(self):
        s = self._make_summary(
            dimensions_with_issues=["QA", "IR", "CP", "LC", "SQ", "PS"],
            dimensions_clean=[],
        )
        assert len(s.dimensions_with_issues) == 6

    def test_dimensions_union_complete_with_all_clean(self):
        s = self._make_summary(
            dimensions_with_issues=[],
            dimensions_clean=["QA", "IR", "CP", "LC", "SQ", "PS"],
        )
        assert len(s.dimensions_clean) == 6
