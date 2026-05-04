"""Tests for prompt loading and content validation."""

import pytest

from reviewer.prompts import load_prompt

DIMENSIONS = [
    "question_alignment",
    "information_recall",
    "completeness",
    "logical_coherence",
    "source_quality",
    "presentation_specificity",
]

REQUIRED_SECTIONS = [
    "<role>",
    "<context>",
    "<constraints>",
    "<severity_definition>",
    "<output_format>",
]

ANTI_HALLUCINATION_KEYWORDS = [
    "evidence_in_report",
    "confidence",
    "nice_to_fix",
    "knowledge_based",
]


class TestLoadPrompt:
    """Test that prompts can be loaded correctly."""

    @pytest.mark.parametrize("dim", DIMENSIONS)
    def test_load_prompt_returns_string(self, dim: str):
        prompt = load_prompt(dim)
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_load_prompt_unknown_dimension_raises(self):
        with pytest.raises(ValueError, match="Unknown dimension"):
            load_prompt("nonexistent_dimension")


class TestPromptSections:
    """Test that each prompt contains all required sections."""

    @pytest.mark.parametrize("dim", DIMENSIONS)
    @pytest.mark.parametrize("section", REQUIRED_SECTIONS)
    def test_contains_required_section(self, dim: str, section: str):
        prompt = load_prompt(dim)
        assert section in prompt, (
            f"Prompt '{dim}' is missing required section '{section}'"
        )


class TestPromptPlaceholders:
    """Test that each prompt has {task} and {report} placeholders."""

    @pytest.mark.parametrize("dim", DIMENSIONS)
    def test_contains_task_placeholder(self, dim: str):
        prompt = load_prompt(dim)
        assert "{task}" in prompt, f"Prompt '{dim}' missing {{task}} placeholder"

    @pytest.mark.parametrize("dim", DIMENSIONS)
    def test_contains_report_placeholder(self, dim: str):
        prompt = load_prompt(dim)
        assert "{report}" in prompt, f"Prompt '{dim}' missing {{report}} placeholder"


class TestAntiHallucination:
    """Test that each prompt contains anti-hallucination clauses."""

    @pytest.mark.parametrize("dim", DIMENSIONS)
    @pytest.mark.parametrize("keyword", ANTI_HALLUCINATION_KEYWORDS)
    def test_contains_anti_hallucination_keyword(self, dim: str, keyword: str):
        prompt = load_prompt(dim)
        assert keyword in prompt, (
            f"Prompt '{dim}' is missing anti-hallucination keyword '{keyword}'"
        )


class TestDimensionSpecificContent:
    """Test dimension-specific content is present."""

    def test_qa_has_two_step_approach(self):
        prompt = load_prompt("question_alignment")
        assert "主問題" in prompt or "核心問題" in prompt

    def test_ir_has_no_fake_knowledge_warning(self):
        prompt = load_prompt("information_recall")
        assert "不要假裝" in prompt

    def test_cp_distinguishes_from_ir(self):
        prompt = load_prompt("completeness")
        assert "Information Recall" in prompt or "事實缺失" in prompt

    def test_lc_has_contradiction_scan(self):
        prompt = load_prompt("logical_coherence")
        assert "矛盾" in prompt
        assert "兩處" in prompt or "兩處原文" in prompt

    def test_sq_prohibits_url_verification(self):
        prompt = load_prompt("source_quality")
        assert "不能嘗試驗證 URL" in prompt or "絕對不能" in prompt

    def test_ps_has_vague_word_list(self):
        prompt = load_prompt("presentation_specificity")
        for word in ["許多", "各種", "通常", "大幅", "顯著"]:
            assert word in prompt, f"PS prompt missing vague word '{word}'"
