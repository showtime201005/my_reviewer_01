"""Question Alignment reviewer node."""

from reviewer.nodes.base import ReviewerNodeBase


class QuestionAlignmentNode(ReviewerNodeBase):
    dimension_code = "QA"
    dimension_full_name = "question_alignment"
    state_review_key = "qa_review"
    state_raw_key = "qa_raw"
