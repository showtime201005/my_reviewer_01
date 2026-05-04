"""Prompt loading utilities for reviewer dimensions."""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent

# Mapping from dimension full name to prompt file name
_DIMENSION_FILES = {
    "question_alignment": "question_alignment.md",
    "information_recall": "information_recall.md",
    "completeness": "completeness.md",
    "logical_coherence": "logical_coherence.md",
    "source_quality": "source_quality.md",
    "presentation_specificity": "presentation_specificity.md",
}


def load_prompt(dimension_name: str) -> str:
    """Load the prompt template for a given dimension.

    Args:
        dimension_name: Full dimension name (e.g. "question_alignment").

    Returns:
        The prompt template string with {task} and {report} placeholders.

    Raises:
        ValueError: If the dimension name is not recognized.
        FileNotFoundError: If the prompt file is missing.
    """
    if dimension_name not in _DIMENSION_FILES:
        raise ValueError(
            f"Unknown dimension '{dimension_name}'. "
            f"Valid dimensions: {list(_DIMENSION_FILES.keys())}"
        )
    path = _PROMPTS_DIR / _DIMENSION_FILES[dimension_name]
    return path.read_text(encoding="utf-8")
