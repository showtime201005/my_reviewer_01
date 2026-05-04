# Reviewer — Deep Research Report Reviewer

A LangGraph subgraph that reviews deep research reports and produces structured feedback for downstream agents to improve report quality.

Given a user's original question (`task`) and a deep research report (`report`), the reviewer evaluates six dimensions — Question Alignment, Information Recall, Completeness, Logical Coherence, Source Quality, and Presentation & Specificity — then outputs actionable feedback with severity levels and fix suggestions.

See [PROJECT_SPEC.md](PROJECT_SPEC.md) for the full specification.

## Installation

```bash
pip install -e .

# For development (pytest, coverage)
pip install -e ".[dev]"
```

## Configuration

Copy `.env.example` to `.env` and fill in your API key:

```bash
cp .env.example .env
```

Required environment variables:

| Variable | Default | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Your OpenRouter API key |
| `OPENROUTER_MODEL` | `openai/gpt-4o` | Model to use for review (OpenRouter format) |

## Quick Start

### As a function

```python
from dotenv import load_dotenv
load_dotenv()

from reviewer import review

output = review(
    task="比較 Apple 與 Samsung 2024 年的智慧手機策略",
    report="..."  # Your deep research report text
)

# Human-readable summary
print(output.human_readable_text)

# Structured data
print(output.human_summary.severity_distribution)
# {'must_fix': 3, 'should_fix': 5, 'nice_to_fix': 2}

# Iterate over each dimension's feedback
for dim_name, dim_review in output.dimension_reviews.items():
    for fb in dim_review.top_feedback:
        print(f"[{fb.severity.value}] {fb.id}: {fb.one_liner}")
```

### As a subgraph (embedded in a parent LangGraph)

```python
from reviewer import build_reviewer_graph
from reviewer.state import create_initial_state

# Build — optionally pass a custom LLM
reviewer_graph = build_reviewer_graph()

# Invoke directly
state = create_initial_state(task="...", report="...")
final_state = reviewer_graph.invoke(state)
output = final_state["final_output"]

# Or embed in a parent graph:
# parent_graph.add_node("reviewer", reviewer_graph)
```

## Output Structure

`ReviewOutput` contains:

| Field | Description |
|---|---|
| `review_metadata` | Version, IDs, token cost, latency, failed dimensions |
| `human_summary` | Key findings, severity distribution, highlights |
| `human_readable_text` | Markdown-formatted text for developers |
| `dimension_reviews` | Dict of 6 `DimensionReview` objects with `top_feedback` |
| `additional_observations` | `nice_to_fix` items — for developers, downstream agents should filter these out |
| `v2_interface` | Reserved for future active verification (all null in v1) |

### Severity Levels

- **must_fix**: Critical issues — the report has serious problems if unfixed
- **should_fix**: Recommended improvements — clearly improves quality
- **nice_to_fix**: Optional polish — always in `additional_observations`, never in `top_feedback`

## Development

```bash
# Run unit tests (excludes integration tests by default)
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=reviewer

# Run integration tests (requires OPENROUTER_API_KEY)
pytest tests/test_integration.py -m integration -v -s
```

## Examples

See the `examples/` directory:

- `simple_usage.py` — Function interface quickstart
- `subgraph_usage.py` — Embedding in a parent LangGraph
- `sample_task.txt` + `sample_report.md` — Sample input data


## Review Report 說明:
review_output.json 結構與 feedback 來源                                                                                                                                                                                                                                                                                                                                                           
  review_output.json                                                                                                                                                                                ├── review_metadata          ← 元資料（不是 feedback）    
  ├── human_summary            ← 摘要（不是 feedback，是總覽）
  ├── human_readable_text      ← 純文字版（給人看）
  ├── dimension_reviews        ← ⭐ 主要 feedback 來源
  │   ├── question_alignment.top_feedback[]    ← agent 要處理
  │   ├── information_recall.top_feedback[]    ← agent 要處理
  │   ├── completeness.top_feedback[]          ← agent 要處理
  │   ├── logical_coherence.top_feedback[]     ← agent 要處理
  │   ├── source_quality.top_feedback[]        ← agent 要處理
  │   └── presentation_specificity.top_feedback[] ← agent 要處理
  ├── additional_observations  ← ❌ nice_to_fix，agent 應過濾掉
  └── v2_interface             ← 預留欄位（忽略）

  Agent 要當 feedback 處理的

  dimension_reviews.*.top_feedback[] — 每條包含：

  ┌────────────────────┬─────────────────────────┬───────────────────────────────────────────────────────┐
  │        欄位        │          用途           │                         範例                          │
  ├────────────────────┼─────────────────────────┼───────────────────────────────────────────────────────┤
  │ id                 │ 唯一識別                │ LC-001                                                │
  ├────────────────────┼─────────────────────────┼───────────────────────────────────────────────────────┤
  │ severity           │ 優先順序                │ must_fix > should_fix                                 │
  ├────────────────────┼─────────────────────────┼───────────────────────────────────────────────────────┤
  │ one_liner          │ 一句話問題描述          │ "0%幻覺說法與57%後理性引用衝突"                       │
  ├────────────────────┼─────────────────────────┼───────────────────────────────────────────────────────┤
  │ detail             │ 詳細說明                │ 2-4 句                                                │
  ├────────────────────┼─────────────────────────┼───────────────────────────────────────────────────────┤
  │ evidence_in_report │ 報告中的原文依據        │ 定位修改位置用                                        │
  ├────────────────────┼─────────────────────────┼───────────────────────────────────────────────────────┤
  │ fix_type           │ 告訴 agent 要做什麼動作 │ search_more / rewrite_section / add_perspective / ... │
  ├────────────────────┼─────────────────────────┼───────────────────────────────────────────────────────┤
  │ fix_target         │ 改哪裡                  │ "第 4 章結論段"                                       │
  ├────────────────────┼─────────────────────────┼───────────────────────────────────────────────────────┤
  │ fix_hint           │ 怎麼改                  │ "補充具體數據佐證"                                    │
  ├────────────────────┼─────────────────────────┼───────────────────────────────────────────────────────┤
  │ confidence         │ 可信度                  │ 0.0-1.0                                               │
  └────────────────────┴─────────────────────────┴───────────────────────────────────────────────────────┘

