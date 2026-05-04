"""LLM factory and response parsing utilities."""

from __future__ import annotations

import json
import os
import re
from json import JSONDecodeError

from langchain_openai import ChatOpenAI


def create_default_llm() -> ChatOpenAI:
    """Create the default ChatOpenAI instance via OpenRouter.

    Reads OPENROUTER_API_KEY and OPENROUTER_MODEL from env.
    Temperature is low (0.2) for deterministic output.
    Retries are handled at the node level, so max_retries=0 here.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key or api_key == "your-key-here":
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Please configure it in your .env file."
        )

    return ChatOpenAI(
        model=os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b"),
        temperature=0.2,
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "https://github.com/showtime201005/my_project_01",
            "X-Title": "Deep Research Reviewer",
        },
        timeout=120,
        max_retries=0,
    )


# Regex to extract ```json ... ``` fenced blocks
_JSON_FENCE_RE = re.compile(r"```json\s*\n?(.*?)\n?\s*```", re.DOTALL)

# Regex to find the outermost { ... } JSON object
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

# Chinese quote pairs to replace
_CHINESE_QUOTES = [
    ("\u201c", '"'),  # "
    ("\u201d", '"'),  # "
    ("\u2018", "'"),  # '
    ("\u2019", "'"),  # '
]


def parse_json_from_response(text: str) -> dict:
    """Extract and parse a JSON object from an LLM response string.

    Handles:
    - ```json ... ``` fenced code blocks
    - Bare JSON objects with surrounding text
    - Chinese quotation marks

    Args:
        text: The raw LLM response text.

    Returns:
        The parsed JSON as a dict.

    Raises:
        json.JSONDecodeError: If no valid JSON can be extracted.
    """
    # Normalize Chinese quotes
    for cn, en in _CHINESE_QUOTES:
        text = text.replace(cn, en)

    # Try fenced code block first
    fence_match = _JSON_FENCE_RE.search(text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except JSONDecodeError:
            pass  # Fall through to next strategy

    # Try finding outermost { ... }
    obj_match = _JSON_OBJECT_RE.search(text)
    if obj_match:
        try:
            return json.loads(obj_match.group(0))
        except JSONDecodeError:
            pass

    # Nothing worked
    raise JSONDecodeError(
        "No valid JSON object found in LLM response",
        text,
        0,
    )
