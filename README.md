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
