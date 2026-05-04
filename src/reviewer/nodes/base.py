"""Base class for all reviewer dimension nodes."""

from __future__ import annotations

import time
from typing import Any, Dict

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from reviewer.llm import parse_json_from_response
from reviewer.prompts import load_prompt
from reviewer.schemas import (
    DimensionLLMOutput,
    DimensionReview,
    DimensionStatus,
)
from reviewer.state import ReviewerState


class AllRetriesFailedError(Exception):
    """Raised when all retry attempts for a reviewer node have been exhausted."""


class ReviewerNodeBase:
    """Base class shared by all six dimension reviewer nodes.

    Subclasses only need to set four class attributes:
        dimension_code, dimension_full_name, state_review_key, state_raw_key

    The node is callable with LangGraph's signature: (state) -> dict of updates.
    """

    dimension_code: str          # e.g. "QA"
    dimension_full_name: str     # e.g. "question_alignment"
    state_review_key: str        # e.g. "qa_review"
    state_raw_key: str           # e.g. "qa_raw"

    def __init__(self, llm: ChatOpenAI) -> None:
        self.llm = llm
        self.prompt_template = load_prompt(self.dimension_full_name)

    def __call__(self, state: ReviewerState) -> Dict[str, Any]:
        """LangGraph node entry point: receive state, return state updates."""
        try:
            raw_output, dim_review, tokens_used = self._invoke_with_retry(state)
            return {
                self.state_review_key: dim_review,
                self.state_raw_key: raw_output,
                "total_tokens": tokens_used,  # reducer sums across parallel nodes
            }
        except AllRetriesFailedError:
            failed_review = self._build_failed_review()
            return {
                self.state_review_key: failed_review,
                self.state_raw_key: None,
                "failed_dimensions": [self.dimension_code],  # reducer concatenates
            }

    def _invoke_with_retry(
        self, state: ReviewerState
    ) -> tuple[DimensionLLMOutput, DimensionReview, int]:
        """Call LLM with up to 3 attempts (1 initial + 2 retries).

        Returns:
            Tuple of (validated DimensionLLMOutput, DimensionReview, tokens_used).

        Raises:
            AllRetriesFailedError: After all attempts are exhausted.
        """
        prompt_text = (
            self.prompt_template
            .replace("{task}", state["task"])
            .replace("{report}", state["report"])
        )

        last_error: Exception | None = None
        total_tokens = 0

        for attempt in range(3):
            try:
                response = self.llm.invoke([HumanMessage(content=prompt_text)])

                # Track token usage
                usage = getattr(response, "response_metadata", {}).get(
                    "token_usage", {}
                )
                total_tokens = (
                    usage.get("total_tokens", 0)
                    if isinstance(usage, dict)
                    else 0
                )

                # Parse JSON from response
                raw_json = parse_json_from_response(response.content)

                # Validate with Pydantic
                output = DimensionLLMOutput.model_validate(raw_json)

                # Check dimension consistency
                self._validate_dimension(output)

                # Build DimensionReview (also validates top_feedback constraints)
                dim_review = self._build_dimension_review(output)

                return output, dim_review, total_tokens

            except (ValidationError, Exception) as e:
                last_error = e
                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))  # 2s, 4s

        raise AllRetriesFailedError(
            f"{self.dimension_code}: all 3 attempts failed. "
            f"Last error: {last_error}"
        ) from last_error

    def _validate_dimension(self, output: DimensionLLMOutput) -> None:
        """Ensure the LLM responded for the correct dimension."""
        if output.dimension != self.dimension_full_name:
            raise ValueError(
                f"Dimension mismatch: expected '{self.dimension_full_name}', "
                f"got '{output.dimension}'"
            )

    def _build_dimension_review(self, raw: DimensionLLMOutput) -> DimensionReview:
        """Extract the DimensionReview (without additional_observations) from raw output."""
        return DimensionReview(
            dimension=self.dimension_full_name,
            dimension_summary=raw.dimension_summary,
            confidence=raw.confidence,
            top_feedback=raw.top_feedback,
            status=DimensionStatus.COMPLETED,
        )

    def _build_failed_review(self) -> DimensionReview:
        """Build a failed DimensionReview when all retries are exhausted."""
        return DimensionReview(
            dimension=self.dimension_full_name,
            dimension_summary="此維度評估失敗，請參考其他維度",
            confidence=0.0,
            top_feedback=[],
            status=DimensionStatus.FAILED,
        )
