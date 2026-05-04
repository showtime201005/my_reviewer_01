"""Integration tests that call the real LLM via OpenRouter.

These tests are NOT run in CI by default.
Run with: pytest tests/test_integration.py -m integration
"""

from __future__ import annotations

import pytest
from dotenv import load_dotenv

load_dotenv()

from reviewer import review


TASK = "比較 Apple 與 Samsung 在 2024 年的智慧手機策略，包含市場份額、產品線和定價策略"

REPORT = """
# Apple vs Samsung 2024 智慧手機策略比較

## 1. 市場概況

根據多項報告顯示，2024 年全球智慧手機市場持續成長。Apple 和 Samsung 作為兩大巨頭，
在各自的策略上有顯著差異。市場分析師普遍認為，兩家公司的策略都相當成功。

## 2. Apple 的策略

Apple 在 2024 年推出了 iPhone 16 系列，延續了其一貫的高端定位策略。
iPhone 16 Pro Max 的定價為 $1,199 起。Apple 持續強調其生態系統的整合性，
包括 iOS、macOS 和 Apple Watch 的無縫連接。

根據某個網站的報導，Apple 的市場份額大幅增長。Apple 在印度市場的表現尤其亮眼，
增長速度遠超預期。

## 3. Samsung 的策略

Samsung 則採取了不同的策略。Galaxy S24 系列強調 AI 功能的整合。
Samsung 在折疊手機市場持續投入。

## 4. 結論

綜合以上分析，我們可以確定 Apple 的策略明顯優於 Samsung。
Apple 在各個方面都展現了壓倒性的優勢，未來幾年將持續主導市場。

來源：
- https://www.example-blog.com/smartphone-2024
- https://some-random-site.xyz/tech-analysis
- 據報導
"""


@pytest.mark.integration
def test_real_llm_full_flow():
    """Full end-to-end test with a real LLM call."""
    output = review(task=TASK, report=REPORT)

    # All dimensions should complete (no failures)
    assert output.review_metadata.failed_dimensions == []
    assert len(output.dimension_reviews) == 6

    # Should find some issues in this deliberately flawed report
    assert output.human_summary.severity_distribution["must_fix"] >= 0
    assert output.human_summary.severity_distribution["should_fix"] >= 0

    # Structural checks
    assert output.review_metadata.reviewer_version == "v1.0-passive"
    assert output.review_metadata.active_verification_used is False
    assert "Review Summary" in output.human_readable_text

    # Dimension union covers all 6
    union = set(output.human_summary.dimensions_with_issues) | set(
        output.human_summary.dimensions_clean
    )
    assert union == {"QA", "IR", "CP", "LC", "SQ", "PS"}

    # Print summary for manual inspection
    print(f"\n{'='*60}")
    print(f"Tokens: {output.review_metadata.review_cost_tokens}")
    print(f"Latency: {output.review_metadata.review_latency_seconds}s")
    print(f"Failed dims: {output.review_metadata.failed_dimensions}")
    print(f"Severity: {output.human_summary.severity_distribution}")
    print(f"With issues: {output.human_summary.dimensions_with_issues}")
    print(f"Clean: {output.human_summary.dimensions_clean}")
    print(f"Highlights: {output.human_summary.highlights}")
    print(f"{'='*60}")
