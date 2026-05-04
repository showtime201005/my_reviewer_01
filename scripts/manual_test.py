"""Manual test script for individual reviewer nodes with real OpenAI API.

Usage:
    python scripts/manual_test.py [dimension]

    dimension: qa, ir, cp, lc, sq, ps (default: qa)

Requires OPENROUTER_API_KEY in environment or .env file.
NOT for CI — developer verification only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

from reviewer.llm import create_default_llm
from reviewer.nodes import (
    CompletenessNode,
    InformationRecallNode,
    LogicalCoherenceNode,
    PresentationSpecificityNode,
    QuestionAlignmentNode,
    SourceQualityNode,
)
from reviewer.state import create_initial_state

NODE_MAP = {
    "qa": QuestionAlignmentNode,
    "ir": InformationRecallNode,
    "cp": CompletenessNode,
    "lc": LogicalCoherenceNode,
    "sq": SourceQualityNode,
    "ps": PresentationSpecificityNode,
}

# A deliberately flawed test report for testing
TEST_TASK = "比較 Apple 與 Samsung 在 2024 年的智慧手機策略，包含市場份額、產品線和定價策略"

TEST_REPORT = """
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


def main():
    dim_code = sys.argv[1].lower() if len(sys.argv) > 1 else "qa"

    if dim_code not in NODE_MAP:
        print(f"Unknown dimension: {dim_code}")
        print(f"Available: {', '.join(NODE_MAP.keys())}")
        sys.exit(1)

    print(f"=== Testing {dim_code.upper()} node ===\n")

    llm = create_default_llm()
    node_cls = NODE_MAP[dim_code]
    node = node_cls(llm)

    state = create_initial_state(task=TEST_TASK, report=TEST_REPORT)

    print("Calling LLM...")
    result = node(state)

    review_key = node.state_review_key
    raw_key = node.state_raw_key

    print(f"\n--- DimensionReview ({review_key}) ---")
    review = result[review_key]
    print(f"Status: {review.status.value}")
    print(f"Summary: {review.dimension_summary}")
    print(f"Confidence: {review.confidence}")
    print(f"Top feedback count: {len(review.top_feedback)}")
    for fb in review.top_feedback:
        print(f"  [{fb.severity.value}] {fb.id}: {fb.one_liner}")

    raw = result.get(raw_key)
    if raw and raw.additional_observations:
        print(f"\n--- Additional observations ---")
        for fb in raw.additional_observations:
            print(f"  [{fb.severity.value}] {fb.id}: {fb.one_liner}")

    if "total_tokens" in result:
        print(f"\nTokens used: {result['total_tokens']}")

    if "failed_dimensions" in result:
        print(f"Failed dimensions: {result['failed_dimensions']}")

    # Also dump full raw JSON for inspection
    if raw:
        print(f"\n--- Full raw JSON ---")
        print(json.dumps(raw.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
