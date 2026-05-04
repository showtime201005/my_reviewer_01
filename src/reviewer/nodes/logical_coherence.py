"""Logical Coherence reviewer node."""

from reviewer.nodes.base import ReviewerNodeBase


class LogicalCoherenceNode(ReviewerNodeBase):
    dimension_code = "LC"
    dimension_full_name = "logical_coherence"
    state_review_key = "lc_review"
    state_raw_key = "lc_raw"
