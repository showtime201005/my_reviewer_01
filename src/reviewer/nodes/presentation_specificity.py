"""Presentation & Specificity reviewer node."""

from reviewer.nodes.base import ReviewerNodeBase


class PresentationSpecificityNode(ReviewerNodeBase):
    dimension_code = "PS"
    dimension_full_name = "presentation_specificity"
    state_review_key = "ps_review"
    state_raw_key = "ps_raw"
