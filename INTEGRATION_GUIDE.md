# Reviewer Integration Guide

給上游 deep research agent 團隊參考。

## 接口

### 函式呼叫

```python
from dotenv import load_dotenv
load_dotenv()

from reviewer import review

output = review(task=user_question, report=report_content)
```

### Subgraph 嵌入

```python
from reviewer import build_reviewer_graph
from reviewer.state import create_initial_state

reviewer_graph = build_reviewer_graph()

# 直接呼叫
state = create_initial_state(task="...", report="...")
final_state = reviewer_graph.invoke(state)
output = final_state["final_output"]

# 或嵌入父 graph
# parent_graph.add_node("reviewer", reviewer_graph)
```

### 自訂 LLM

```python
from langchain_openai import ChatOpenAI

custom_llm = ChatOpenAI(model="...", temperature=0.2)
output = review(task="...", report="...", llm=custom_llm)
```

## 輸出結構

`ReviewOutput` 包含以下欄位：

| 欄位 | 型態 | 用途 |
|---|---|---|
| `review_metadata` | `ReviewMetadata` | 版本、ID、token 成本、延遲、失敗維度 |
| `human_summary` | `HumanSummary` | 摘要：key findings、severity 分布、highlights |
| `human_readable_text` | `str` | Markdown 格式純文字，給人類快速閱讀 |
| `dimension_reviews` | `Dict[str, DimensionReview]` | 六個維度的詳細 review |
| `additional_observations` | `List[Feedback]` | nice_to_fix 條目，僅供開發者參考 |
| `v2_interface` | `V2Interface` | v2 預留欄位（v1 全部為 null/空） |

## Agent 應處理的部分

### 1. `dimension_reviews.*.top_feedback`

主要的 feedback 列表。每條 feedback 包含：

- `id`: 唯一識別碼（如 `QA-001`）
- `severity`: `must_fix` / `should_fix`
- `one_liner`: ≤ 25 字摘要
- `detail`: 2-4 句詳細描述
- `evidence_in_report`: 報告中的原文片段
- `fix_type`: 建議的修復動作類型
- `fix_target`: 修改目標位置
- `fix_hint`: 修復建議
- `confidence`: 0.0-1.0

### 2. `human_summary.severity_distribution`

快速判斷整體狀況：

```python
dist = output.human_summary.severity_distribution
# {"must_fix": 3, "should_fix": 5, "nice_to_fix": 2}

if dist["must_fix"] == 0:
    # 報告品質 OK，可能只需小幅修改
    ...
```

### 3. `review_metadata.failed_dimensions`

檢查是否有維度評估失敗：

```python
if output.review_metadata.failed_dimensions:
    # 某些維度未能完成評估
    print(f"Warning: {output.review_metadata.failed_dimensions} failed")
```

## Agent 應過濾掉的部分

- **`additional_observations`** — 這部分只給開發者看，包含 `nice_to_fix` 級的邊際建議。下游 agent 不應將這些當作 feedback 處理。

## 處理 Feedback 的建議邏輯

```python
def process_review(review_output):
    # 收集所有 must_fix feedback
    must_fix_items = []
    should_fix_items = []

    for dim_review in review_output.dimension_reviews.values():
        for fb in dim_review.top_feedback:
            if fb.severity.value == "must_fix":
                must_fix_items.append(fb)
            elif fb.severity.value == "should_fix":
                should_fix_items.append(fb)

    # 按 fix_type 分組，執行對應動作
    for fb in must_fix_items:
        if fb.fix_type.value == "search_more":
            # 執行新的搜尋，補充缺失資料
            ...
        elif fb.fix_type.value == "replace_source":
            # 換掉不夠權威的引用
            ...
        elif fb.fix_type.value == "rewrite_section":
            # 重寫指定段落
            ...
        elif fb.fix_type.value == "remove_claim":
            # 刪除不正確的陳述
            ...
        elif fb.fix_type.value == "add_perspective":
            # 補充反向觀點或 trade-off
            ...
        elif fb.fix_type.value == "reformat":
            # 調整呈現格式
            ...
```

## 注意事項

1. **`confidence < 0.7` 的 feedback** 可考慮降低處理優先順序
2. **`verification_level == "knowledge_based"`** 的 feedback 是 reviewer 用 LLM 內部知識判斷，不一定可靠，建議額外驗證
3. **`failed_dimensions`** 包含的維度表示該維度 LLM call 全部失敗（重試 3 次後），agent 應知道該維度未被評估
4. **每個維度最多 5 條 top_feedback**，按 must_fix → should_fix 優先順序排列
5. **`evidence_in_report`** 欄位指出報告中的具體片段，agent 可用此定位需要修改的位置

## 環境需求

- `OPENROUTER_API_KEY` 環境變數
- Python 3.11+
- 安裝：`pip install -e .`
