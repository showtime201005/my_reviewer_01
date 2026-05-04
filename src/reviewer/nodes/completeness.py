"""Completeness reviewer node."""

from reviewer.nodes.base import ReviewerNodeBase


class CompletenessNode(ReviewerNodeBase):
    dimension_code = "CP"
    dimension_full_name = "completeness"
    state_review_key = "cp_review"
    state_raw_key = "cp_raw"
