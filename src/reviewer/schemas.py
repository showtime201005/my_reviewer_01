"""Pydantic models and enums for the Reviewer graph.

All schemas strictly follow PROJECT_SPEC.md §7.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    MUST_FIX = "must_fix"
    SHOULD_FIX = "should_fix"
    NICE_TO_FIX = "nice_to_fix"


class FixType(str, Enum):
    SEARCH_MORE = "search_more"
    REPLACE_SOURCE = "replace_source"
    REWRITE_SECTION = "rewrite_section"
    REMOVE_CLAIM = "remove_claim"
    ADD_PERSPECTIVE = "add_perspective"
    REFORMAT = "reformat"


class VerificationLevel(str, Enum):
    TEXT_ONLY = "text_only"
    KNOWLEDGE_BASED = "knowledge_based"
    SOURCE_VERIFIED = "source_verified"  # v2
    EXTERNAL_CHECK = "external_check"    # v2


class DimensionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"


class DimensionCode(str, Enum):
    QA = "QA"
    IR = "IR"
    CP = "CP"
    LC = "LC"
    SQ = "SQ"
    PS = "PS"


ALL_DIMENSION_CODES = {code.value for code in DimensionCode}

# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

_FEEDBACK_ID_RE = re.compile(r"^[A-Z]{2}-\d{3}$")


class Feedback(BaseModel):
    """A single feedback item produced by a dimension reviewer."""

    id: str
    severity: Severity
    one_liner: str = Field(..., description="≤ 25 characters summary")
    detail: str
    evidence_in_report: str
    fix_type: FixType
    fix_target: str
    fix_hint: str
    verification_level: VerificationLevel
    confidence: float = Field(..., ge=0.0, le=1.0)
    source_verification: Optional[Any] = None
    external_check_result: Optional[Any] = None

    @field_validator("id")
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        if not _FEEDBACK_ID_RE.match(v):
            raise ValueError(
                f"id must match '[A-Z]{{2}}-[0-9]{{3}}' (e.g. 'QA-001'), got '{v}'"
            )
        return v

    @field_validator("one_liner")
    @classmethod
    def validate_one_liner_length(cls, v: str) -> str:
        if len(v) > 25:
            raise ValueError(
                f"one_liner must be ≤ 25 characters, got {len(v)}"
            )
        return v

    @field_validator("evidence_in_report")
    @classmethod
    def validate_evidence_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("evidence_in_report must not be empty")
        return v

    @field_validator("source_verification")
    @classmethod
    def validate_source_verification_null(cls, v: Any) -> Any:
        if v is not None:
            raise ValueError("source_verification must be None in v1")
        return v

    @field_validator("external_check_result")
    @classmethod
    def validate_external_check_null(cls, v: Any) -> Any:
        if v is not None:
            raise ValueError("external_check_result must be None in v1")
        return v


# ---------------------------------------------------------------------------
# DimensionReview
# ---------------------------------------------------------------------------

class DimensionReview(BaseModel):
    """Review result for a single dimension."""

    dimension: str
    dimension_summary: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    top_feedback: List[Feedback] = Field(default_factory=list, max_length=5)
    status: DimensionStatus

    @field_validator("top_feedback")
    @classmethod
    def validate_no_nice_to_fix(cls, v: List[Feedback]) -> List[Feedback]:
        for fb in v:
            if fb.severity == Severity.NICE_TO_FIX:
                raise ValueError(
                    f"top_feedback must not contain nice_to_fix items, "
                    f"but found {fb.id}"
                )
        return v


# ---------------------------------------------------------------------------
# ReviewMetadata
# ---------------------------------------------------------------------------

class ReviewMetadata(BaseModel):
    reviewer_version: str
    task_id: str
    report_id: str
    review_cost_tokens: int
    review_latency_seconds: float
    active_verification_used: bool = False
    failed_dimensions: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# HumanSummary
# ---------------------------------------------------------------------------

_REQUIRED_SEVERITY_KEYS = {"must_fix", "should_fix", "nice_to_fix"}


class HumanSummary(BaseModel):
    key_findings: str
    severity_distribution: Dict[str, int]
    dimensions_with_issues: List[str]
    dimensions_clean: List[str]
    highlights: List[str]

    @field_validator("severity_distribution")
    @classmethod
    def validate_severity_keys(cls, v: Dict[str, int]) -> Dict[str, int]:
        missing = _REQUIRED_SEVERITY_KEYS - v.keys()
        if missing:
            raise ValueError(
                f"severity_distribution must contain keys {_REQUIRED_SEVERITY_KEYS}, "
                f"missing {missing}"
            )
        return v

    @model_validator(mode="after")
    def validate_dimensions_union(self) -> "HumanSummary":
        union = set(self.dimensions_with_issues) | set(self.dimensions_clean)
        if union != ALL_DIMENSION_CODES:
            raise ValueError(
                f"dimensions_with_issues ∪ dimensions_clean must equal "
                f"{ALL_DIMENSION_CODES}, got {union}"
            )
        return self


# ---------------------------------------------------------------------------
# V2Interface
# ---------------------------------------------------------------------------

class V2Interface(BaseModel):
    citation_sources: Optional[Any] = None
    external_searches_performed: List = Field(default_factory=list)
    fact_check_results: List = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ReviewOutput (top-level aggregator output)
# ---------------------------------------------------------------------------

class ReviewOutput(BaseModel):
    review_metadata: ReviewMetadata
    human_summary: HumanSummary
    human_readable_text: str
    dimension_reviews: Dict[str, DimensionReview]
    additional_observations: List[Feedback]
    v2_interface: V2Interface


# ---------------------------------------------------------------------------
# DimensionLLMOutput (raw LLM response schema — used in Phase 2)
# ---------------------------------------------------------------------------

class DimensionLLMOutput(BaseModel):
    """Schema for the raw output a dimension reviewer LLM is expected to return."""

    dimension: str
    dimension_summary: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    top_feedback: List[Feedback]
    additional_observations: List[Feedback] = Field(default_factory=list)
