# PHASE1_TASKS.md — 基礎設施

## 目標

建立專案結構、Pydantic schemas、Aggregator 純程式邏輯。**不接 LLM，不寫 prompt**，純粹打地基。

完成後人類 review，再進 Phase 2。

## 1. 建立專案結構

採用 src/ layout，目錄如下:

```
reviewer/
├── README.md                    # 專案介紹 + 安裝 + 快速使用範例
├── pyproject.toml               # Python 專案描述
├── .env.example                 # 環境變數範例（OPENAI_API_KEY 等）
├── .gitignore
├── src/
│   └── reviewer/
│       ├── __init__.py
│       ├── schemas.py           # 所有 Pydantic models（見任務 2）
│       ├── state.py             # LangGraph State 定義（見任務 3）
│       ├── aggregator.py        # 純 Python 整合邏輯（見任務 4）
│       ├── graph.py             # 還是空的，Phase 3 才實作
│       ├── nodes/               # 還是空的，Phase 2 才實作
│       │   └── __init__.py
│       └── prompts/             # 還是空的，Phase 2 才實作
└── tests/
    ├── __init__.py
    ├── test_schemas.py          # 任務 2 對應測試
    └── test_aggregator.py       # 任務 4 對應測試
```

`pyproject.toml` 內容:
- Python ≥ 3.11
- 依賴:`langgraph`, `langchain`, `langchain-openai`, `pydantic>=2.0`, `python-dotenv`
- 開發依賴:`pytest`, `pytest-cov`
- 套件名稱:`reviewer`

`.env.example`:
```
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o
```

`README.md` 包含:
- 一段話介紹
- 安裝步驟（`pip install -e .`）
- 兩種使用範例:作為 subgraph、作為函式
- 連到 PROJECT_SPEC.md

## 2. 實作 schemas.py

定義所有 Pydantic models，嚴格按照 PROJECT_SPEC §7 的 schema。

要實作的 models:

```python
# 列舉
class Severity(str, Enum):
    MUST_FIX = "must_fix"
    SHOULD_FIX = "should_fix"
    NICE_TO_FIX = "nice_to_fix"

class FixType(str, Enum):
    SEARCH_MORE = "search_more"
    REPLACE_SOURCE = "replace_source"
    REWRITE_SECTION = "rewrite_section"
    REMOVE_CLAIM = "remove_claim"
    ADD_PERSPECTIVE = "add_perspective"
    REFORMAT = "reformat"

class VerificationLevel(str, Enum):
    TEXT_ONLY = "text_only"
    KNOWLEDGE_BASED = "knowledge_based"
    SOURCE_VERIFIED = "source_verified"  # v2
    EXTERNAL_CHECK = "external_check"    # v2

class DimensionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"

class DimensionCode(str, Enum):
    QA = "QA"
    IR = "IR"
    CP = "CP"
    LC = "LC"
    SQ = "SQ"
    PS = "PS"

# 主要 models
class Feedback(BaseModel):
    id: str
    severity: Severity
    one_liner: str  # 必須 ≤ 25 字（用 validator 檢查）
    detail: str
    evidence_in_report: str  # 不可為空字串（validator 檢查）
    fix_type: FixType
    fix_target: str
    fix_hint: str
    verification_level: VerificationLevel
    confidence: float  # 0.0-1.0（validator 檢查）
    source_verification: Optional[Any] = None  # v1 永遠 None
    external_check_result: Optional[Any] = None  # v1 永遠 None

class DimensionReview(BaseModel):
    dimension: str  # "question_alignment" 等完整名稱
    dimension_summary: str
    confidence: float
    top_feedback: List[Feedback]  # 最多 5 條（validator 檢查）
    status: DimensionStatus

class ReviewMetadata(BaseModel):
    reviewer_version: str
    task_id: str
    report_id: str
    review_cost_tokens: int
    review_latency_seconds: float
    active_verification_used: bool = False
    failed_dimensions: List[str] = []

class HumanSummary(BaseModel):
    key_findings: str
    severity_distribution: Dict[str, int]  # {"must_fix": int, "should_fix": int, "nice_to_fix": int}
    dimensions_with_issues: List[str]
    dimensions_clean: List[str]
    highlights: List[str]

class V2Interface(BaseModel):
    citation_sources: Optional[Any] = None
    external_searches_performed: List = []
    fact_check_results: List = []

class ReviewOutput(BaseModel):
    review_metadata: ReviewMetadata
    human_summary: HumanSummary
    human_readable_text: str
    dimension_reviews: Dict[str, DimensionReview]  # key 是維度全名
    additional_observations: List[Feedback]
    v2_interface: V2Interface

# LLM 直接輸出的 schema（給 Phase 2 用，但先定義好）
class DimensionLLMOutput(BaseModel):
    """單個 reviewer node 期望從 LLM 取得的格式"""
    dimension: str
    dimension_summary: str
    confidence: float
    top_feedback: List[Feedback]
    additional_observations: List[Feedback] = []  # nice_to_fix 與超出條目
```

### Validators 要檢查的事項

`Feedback`:
- `one_liner` 長度 ≤ 25 字（中英文都算 1 字）
- `evidence_in_report` 不可為空字串
- `id` 格式必須符合 `[2字代號]-[3位數字]`，例如 `QA-001`、`IR-042`
- `confidence` 必須在 0.0-1.0
- `v1 限制`:`source_verification` 與 `external_check_result` 必須為 None

`DimensionReview`:
- `top_feedback` 長度 ≤ 5
- `top_feedback` 中不可有 `severity == NICE_TO_FIX` 的條目

`HumanSummary`:
- `severity_distribution` 必須包含 must_fix / should_fix / nice_to_fix 三個 key
- `dimensions_with_issues` 與 `dimensions_clean` 的 union 必須是 {QA, IR, CP, LC, SQ, PS}

## 3. 實作 state.py

```python
class ReviewerState(TypedDict):
    # 輸入
    task: str
    report: str
    task_id: str
    report_id: str

    # 中間結果（Phase 2 各 node 填）
    qa_review: Optional[DimensionReview]
    ir_review: Optional[DimensionReview]
    cp_review: Optional[DimensionReview]
    lc_review: Optional[DimensionReview]
    sq_review: Optional[DimensionReview]
    ps_review: Optional[DimensionReview]

    # 各維度的 raw LLM output（含 nice_to_fix 等，給 aggregator 用）
    qa_raw: Optional[DimensionLLMOutput]
    ir_raw: Optional[DimensionLLMOutput]
    cp_raw: Optional[DimensionLLMOutput]
    lc_raw: Optional[DimensionLLMOutput]
    sq_raw: Optional[DimensionLLMOutput]
    ps_raw: Optional[DimensionLLMOutput]

    # 元資料
    start_time: float
    total_tokens: int
    failed_dimensions: List[str]

    # 最終輸出（Phase 3 aggregator 填）
    final_output: Optional[ReviewOutput]
```

提供一個 helper:

```python
def create_initial_state(task: str, report: str, task_id: str = None, report_id: str = None) -> ReviewerState:
    """建立初始 state，所有中間結果為 None。"""
    ...
```

`task_id` 與 `report_id` 若未提供，自動產生 UUID。

## 4. 實作 aggregator.py

純 Python，不呼叫 LLM。輸入 `ReviewerState`，輸出 `ReviewOutput`。

主函式:

```python
def aggregate(state: ReviewerState) -> ReviewOutput:
    """
    整合六個 dimension reviews 為最終輸出。

    1. 從 state 收集六個 *_review 與 *_raw
    2. 從各 raw output 收集 nice_to_fix 與超出 top 5 的 → additional_observations
    3. 計算 severity_distribution（包含 additional_observations 的 nice_to_fix）
    4. 分類 dimensions_with_issues / dimensions_clean
    5. 抽 highlights（must_fix 前 5 條 by confidence）
    6. 拼 key_findings（六個 dimension_summary 串接）
    7. render_human_readable_text
    8. 組 ReviewMetadata（含 failed_dimensions）
    9. 回傳 ReviewOutput
    """
```

需要的 helper:

```python
def render_human_readable_text(
    key_findings: str,
    severity_dist: dict,
    dimensions_with_issues: List[str],
    dimensions_clean: List[str],
    highlights: List[str]
) -> str:
    """
    產生純文字版本，格式如 PROJECT_SPEC §10 的範例。
    使用 markdown 風格，方便人類閱讀。
    """
```

注意事項:
- 若某維度 status == "failed"，dimension_summary 改為「此維度評估失敗，請參考其他維度」
- highlights 取 must_fix 級，最多 5 條，按 confidence 降序排列
- key_findings 串接時，若某 dimension_summary 為空字串就跳過

## 5. 寫測試

### tests/test_schemas.py

至少測試:
- `Feedback` 的 validators:
  - one_liner > 25 字應 raise
  - evidence_in_report 為空應 raise
  - id 格式錯誤應 raise（例如 "qa-001"、"QA-1"）
  - confidence 超出 0-1 應 raise
  - source_verification 不為 None 應 raise（v1 限制）
- `DimensionReview` 的 validators:
  - top_feedback > 5 條應 raise
  - top_feedback 含 nice_to_fix 應 raise
- `HumanSummary` 的 validators:
  - severity_distribution 缺 key 應 raise
  - dimensions union 不完整應 raise

### tests/test_aggregator.py

至少測試:
- 全部維度都成功（has issues mix）的整合
- 部分維度 failed 的整合
- 全部維度 clean（沒任何 must_fix / should_fix）的整合
- nice_to_fix 條目正確進 additional_observations
- 超出 top 5 的條目（如果發生）正確進 additional_observations
- highlights 確實只取 must_fix 級且按 confidence 排序
- human_readable_text 包含必要訊息（key_findings、各維度狀況、highlights）

提供一些 fixture（mock 的 ReviewerState、DimensionReview 等）方便測試。

## 6. 執行驗收

完成所有任務後:

```bash
# 安裝
pip install -e ".[dev]"

# 跑測試
pytest tests/ -v

# 應該全部通過
```

## 7. Phase 1 完成後請回報

完成後請在最終回應中:

1. 列出建立的所有檔案（含路徑）
2. 列出測試結果（pass/fail 數量）
3. 列出實作中的任何 TODO 或不確定點
4. 列出做的微小決策（例如某個變數命名選擇）
5. **不要進入 Phase 2**，等待人類 review

## 8. 不要做的事

- 不要實作 LangGraph 的 graph（Phase 3 才做）
- 不要寫 reviewer node（Phase 2 才做）
- 不要寫 prompts（Phase 2 才做）
- 不要連線 OpenAI API（Phase 2 才做）
- 不要做 streaming / observability
