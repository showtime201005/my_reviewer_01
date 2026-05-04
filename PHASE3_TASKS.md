# PHASE3_TASKS.md — Graph 組裝與整合

## 前置條件

Phase 1 與 Phase 2 已完成且通過 review。

## 目標

把六個 reviewer node + input validator + aggregator 組成完整的 LangGraph subgraph。提供兩種對外接口（subgraph、函式）。用 mock LLM 跑端到端測試。

## 1. 實作 input_validator node

```python
# src/reviewer/nodes/input_validator.py

class InputValidationError(Exception):
    pass

def input_validator_node(state: ReviewerState) -> dict:
    """
    驗證 task 與 report 合法。
    失敗則 raise InputValidationError（讓 graph 中斷）。
    """
    task = state.get("task", "")
    report = state.get("report", "")

    if not task or not task.strip():
        raise InputValidationError("task is empty")
    if not report or len(report.strip()) < 100:
        raise InputValidationError(f"report too short: {len(report)} chars (need ≥ 100)")

    # 粗略估算 token，避免 context overflow
    # 用 len(text) // 2 當粗略估算（中文字符較多）
    estimated_tokens = (len(task) + len(report)) // 2
    if estimated_tokens > 100_000:
        raise InputValidationError(f"input too long: ~{estimated_tokens} tokens")

    # 初始化 metadata
    return {
        "start_time": time.time(),
        "total_tokens": 0,
        "failed_dimensions": []
    }
```

## 2. 實作 aggregator node

包裝 Phase 1 的 `aggregate()` 為 LangGraph node:

```python
# src/reviewer/nodes/aggregator_node.py

def aggregator_node(state: ReviewerState) -> dict:
    """整合並產出最終 ReviewOutput"""
    output = aggregate(state)
    return {"final_output": output}
```

## 3. 實作 graph.py

```python
# src/reviewer/graph.py

from langgraph.graph import StateGraph, START, END
from .state import ReviewerState
from .llm import create_default_llm
from .nodes import (
    input_validator_node,
    QuestionAlignmentNode,
    InformationRecallNode,
    CompletenessNode,
    LogicalCoherenceNode,
    SourceQualityNode,
    PresentationSpecificityNode,
    aggregator_node
)


def build_reviewer_graph(llm=None):
    """
    建立 reviewer graph。

    Args:
        llm: 可選的 LLM instance。預設用 create_default_llm()。

    Returns:
        compiled LangGraph graph
    """
    if llm is None:
        llm = create_default_llm()

    # 建立各 node
    qa = QuestionAlignmentNode(llm)
    ir = InformationRecallNode(llm)
    cp = CompletenessNode(llm)
    lc = LogicalCoherenceNode(llm)
    sq = SourceQualityNode(llm)
    ps = PresentationSpecificityNode(llm)

    # 建 graph
    graph = StateGraph(ReviewerState)

    graph.add_node("input_validator", input_validator_node)
    graph.add_node("qa_reviewer", qa)
    graph.add_node("ir_reviewer", ir)
    graph.add_node("cp_reviewer", cp)
    graph.add_node("lc_reviewer", lc)
    graph.add_node("sq_reviewer", sq)
    graph.add_node("ps_reviewer", ps)
    graph.add_node("aggregator", aggregator_node)

    # 序列邊
    graph.add_edge(START, "input_validator")
    graph.add_edge("input_validator", "qa_reviewer")
    graph.add_edge("qa_reviewer", "ir_reviewer")
    graph.add_edge("ir_reviewer", "cp_reviewer")
    graph.add_edge("cp_reviewer", "lc_reviewer")
    graph.add_edge("lc_reviewer", "sq_reviewer")
    graph.add_edge("sq_reviewer", "ps_reviewer")
    graph.add_edge("ps_reviewer", "aggregator")
    graph.add_edge("aggregator", END)

    return graph.compile()
```

## 4. 實作對外接口

### 4.1 函式接口

```python
# src/reviewer/__init__.py

from .graph import build_reviewer_graph
from .schemas import ReviewOutput
from .state import create_initial_state


def review(
    task: str,
    report: str,
    task_id: str = None,
    report_id: str = None,
    llm = None
) -> ReviewOutput:
    """
    對一份 deep research report 做 review。

    Args:
        task: 使用者的研究問題
        report: deep research agent 產出的報告
        task_id, report_id: 可選的 ID
        llm: 可選的 LLM instance

    Returns:
        ReviewOutput Pydantic model
    """
    graph = build_reviewer_graph(llm=llm)
    initial_state = create_initial_state(task, report, task_id, report_id)
    final_state = graph.invoke(initial_state)
    return final_state["final_output"]


__all__ = ["review", "build_reviewer_graph", "ReviewOutput"]
```

### 4.2 Subgraph 使用範例

在 README.md 中加入範例:

```python
# 作為 subgraph 嵌入父 graph
from reviewer import build_reviewer_graph
from langgraph.graph import StateGraph

reviewer_subgraph = build_reviewer_graph()

parent_graph = StateGraph(ParentState)
parent_graph.add_node("reviewer", reviewer_subgraph)
# ...

# 注意:父 graph 的 state 必須包含 reviewer 需要的欄位
# 或在 add_node 時提供 input/output mapping
```

## 5. Mock LLM 端到端測試

### 5.1 建立 mock LLM

```python
# tests/conftest.py

class MockChatOpenAI:
    """模擬 ChatOpenAI 回傳預設 JSON 的 mock"""

    def __init__(self, responses: dict[str, str]):
        """
        Args:
            responses: {"question_alignment": "<JSON string>", ...}
                      key 為 dimension full name，value 為要回傳的 JSON 字串
        """
        self.responses = responses
        self.call_log = []

    def invoke(self, messages):
        # 從 messages 中判斷是哪個維度的 prompt
        prompt_text = messages[-1].content
        dimension = self._detect_dimension(prompt_text)
        self.call_log.append(dimension)

        response_text = self.responses.get(dimension, '{"error": "no mock"}')
        return AIMessage(content=response_text)

    def _detect_dimension(self, prompt: str) -> str:
        # 用 prompt 中的特徵字串識別（或是 prompt 中加 marker）
        ...


@pytest.fixture
def good_report_responses():
    """所有維度都沒問題的 mock responses"""
    ...

@pytest.fixture
def bad_report_responses():
    """所有維度都有 must_fix / should_fix 的 mock responses"""
    ...

@pytest.fixture
def mixed_responses():
    """部分維度好、部分維度壞的 mock responses"""
    ...

@pytest.fixture
def failing_responses():
    """LLM 回傳 invalid JSON，會觸發 retry 然後 fail"""
    ...
```

### 5.2 測試案例

`tests/test_graph.py`:

至少包含以下測試:

1. **完整成功流程**:用 mixed_responses，確認最終輸出有完整 6 個 dimension_reviews
2. **全 clean 報告**:用 good_report_responses，確認 dimensions_with_issues 為空、severity_distribution 全是 0
3. **全 fail 報告**:用 bad_report_responses，確認 highlights 不為空、severity_distribution 反映實際數量
4. **部分維度失敗**:某個維度的 mock 回傳 invalid JSON 3 次，確認:
   - 該維度 status = "failed"
   - failed_dimensions 包含該維度
   - 其他維度照常完成
   - 最終仍有完整 ReviewOutput
5. **全部維度失敗**:所有 mock 都壞，確認最終 ReviewOutput 仍可產出（雖然內容很空）但 failed_dimensions 包含全部 6 個
6. **input_validator 拒絕**:task 為空時 raise InputValidationError
7. **input_validator 拒絕**:report < 100 字時 raise

## 6. 真實 LLM 端到端測試（標記為 integration）

`tests/test_integration.py`，預設不在 CI 跑（用 `@pytest.mark.integration`）:

```python
@pytest.mark.integration
def test_real_llm_full_flow():
    """需要 OPENAI_API_KEY，實際呼叫 OpenAI"""
    task = "..."  # 使用一個典型測試問題
    report = "..."  # 一份明顯有問題的測試報告

    output = review(task, report)

    # 寬鬆檢查（不檢查具體內容，因 LLM 輸出有變動性）
    assert output.review_metadata.failed_dimensions == []  # 期望都成功
    assert len(output.dimension_reviews) == 6
    assert output.human_summary.severity_distribution["must_fix"] >= 0
    assert "human_readable_text" in output.model_dump()
```

執行方式:
```bash
pytest tests/test_integration.py -m integration
```

## 7. 文件更新

### 7.1 更新 README.md

加入:
- 完整的快速開始範例（簡單版 + subgraph 版）
- 解釋 ReviewOutput 結構
- 提到 additional_observations 給開發者看、agent 應過濾的設計
- 環境變數設定
- 跑測試的指令

### 7.2 加入 examples/ 範例

```
examples/
├── simple_usage.py          # 用函式接口的最簡範例
├── subgraph_usage.py        # 嵌入父 graph 的範例
├── sample_task.txt          # 一個範例 task
└── sample_report.md         # 一份範例 report
```

## 8. Phase 3 完成後請回報

完成後請在最終回應中:

1. 列出建立的所有新檔案
2. 列出 graph 的 Mermaid 結構圖（用 graph.get_graph().draw_mermaid() 或文字描述）
3. 列出測試結果（mock 測試與 integration 測試分開回報）
4. 若跑了 integration 測試，列出實際 token 數與 latency
5. 列出對使用者的提醒（例如 OPENAI_API_KEY 設定、context 長度限制等）
6. **不要進入 Phase 4**，等待人類 review

## 9. 不要做的事

- 不要做並行 node（使用者明確選擇序列）
- 不要加 streaming
- 不要加 LangSmith 整合
- 不要在 graph 中嘗試實作 v2 主動驗證
