"""Source Quality reviewer node."""

from reviewer.nodes.base import ReviewerNodeBase


class SourceQualityNode(ReviewerNodeBase):
    dimension_code = "SQ"
    dimension_full_name = "source_quality"
    state_review_key = "sq_review"
    state_raw_key = "sq_raw"
