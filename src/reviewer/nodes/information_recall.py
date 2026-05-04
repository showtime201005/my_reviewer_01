"""Information Recall reviewer node."""

from reviewer.nodes.base import ReviewerNodeBase


class InformationRecallNode(ReviewerNodeBase):
    dimension_code = "IR"
    dimension_full_name = "information_recall"
    state_review_key = "ir_review"
    state_raw_key = "ir_raw"
