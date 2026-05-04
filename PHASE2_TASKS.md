# PHASE2_TASKS.md — Reviewer Nodes 與 Prompts

## 前置條件

Phase 1 已完成且通過 review。

## 目標

實作六個 reviewer node 與對應的 prompt 檔。每個 node 負責呼叫 LLM 處理一個維度。**不串 graph**（Phase 3 才做），先確保每個 node 獨立可運作。

## 1. Prompt 檔案結構

每個維度一個獨立 .md 檔，放在 `src/reviewer/prompts/`:

```
src/reviewer/prompts/
├── __init__.py
├── _common.md              # 共用骨架的可重用片段
├── question_alignment.md
├── information_recall.md
├── completeness.md
├── logical_coherence.md
├── source_quality.md
└── presentation_specificity.md
```

`__init__.py` 提供 helper:

```python
def load_prompt(dimension_code: str) -> str:
    """讀取對應維度的 prompt template，回傳字串。"""
```

### 1.1 共用骨架 (`_common.md`)

包含可被所有維度引用的片段:

- `<role>` 模板
- `<constraints>` 共用部分（不能 fetch URL、寧少勿假等）
- `<severity_definition>` 完整定義
- `<output_format>` JSON schema 描述
- 防幻覺條款（evidence_in_report 必須存在、confidence 校準等）

各維度 prompt 引用此檔的方式由你決定（例如用 `{{include: _common.md::section}}` 標記後在 load_prompt 解析），或直接複製到每個檔案。我建議**直接複製**，避免增加複雜度，但保持各檔案中共用部分文字一致。

### 1.2 各維度 Prompt 設計

每個 prompt 必須包含以下區塊（順序固定）:

1. `<role>`:角色定義
2. `<context>`:`{task}` 與 `{report}` 兩個 placeholder
3. `<dimension_specific_instructions>`:該維度的關鍵檢查項
4. `<constraints>`:共用 + 該維度特殊限制
5. `<severity_definition>`:三級定義
6. `<selection_priority>`:選擇優先順序
7. `<output_format>`:JSON schema 描述

依 PROJECT_SPEC §9.2 寫各維度差異化重點:

**question_alignment.md**:
- 兩步驟思考:抽取主問題 → 檢查報告 vs 主問題
- 「若任務本身範圍寬鬆，應寬容判斷」
- 常見 must_fix:報告主章節討論非任務要的東西

**information_recall.md**:
- 「不要假裝知道某事實在哪可找到」
- 「若想到關鍵事實該出現但缺失，必須具體寫出該事實是什麼」
- 不可只說「缺重要資訊」

**completeness.md**:
- 區分「事實缺失（屬 IR）」與「論述面向缺失（屬 CP）」
- 「給出具體缺失面向，不可只說『不夠全面』」
- 常見 must_fix:任務要求 N 項比較但只比 N-1 項

**logical_coherence.md**:
- 主動掃描矛盾步驟
- 「指出矛盾時，必須引用兩處原文片段」
- 常見 must_fix:結論與證據強度不一致、推理跳躍

**source_quality.md**:
- **嚴格禁止「驗證 URL 內容」相關語句**
- 「即使覺得某 URL 內容可能不符，也只能寫 verification_level: text_only」
- 只能評估 domain 強度與引用形式

**presentation_specificity.md**:
- 提供模糊詞列表:許多、各種、通常、大幅、顯著、相關、有效、常見、主要、重要、複雜、簡單、不同、類似、可能、似乎、廣泛、深入
- 「不要為了湊滿 top 5 把 nice_to_fix 升級」

### 1.3 共用防幻覺條款（每個 prompt 都要包含）

```
- 對每條 feedback，evidence_in_report 必須是報告中真實存在的片段。
  如果你想不出 evidence，就不要報這條 feedback。
- confidence 必須誠實。如果你只是猜測，confidence 應 ≤ 0.5。
  confidence < 0.6 的條目應降為 nice_to_fix。
- 對於需要外部知識才能判斷的問題，verification_level 必須標 knowledge_based 並降低 confidence。
- top_feedback 最多 5 條。寧可少於 5 條，也不可硬湊。
- nice_to_fix 級永遠不放進 top_feedback，全部放進 additional_observations。
```

## 2. Reviewer Node 實作

每個維度一個 node 檔案，放在 `src/reviewer/nodes/`:

```
src/reviewer/nodes/
├── __init__.py
├── base.py                      # 共用 base class 或 helper
├── question_alignment.py
├── information_recall.py
├── completeness.py
├── logical_coherence.py
├── source_quality.py
└── presentation_specificity.py
```

### 2.1 base.py

提供共用邏輯:

```python
class ReviewerNodeBase:
    """所有 reviewer node 的共用 base"""

    dimension_code: str  # "QA", "IR" 等
    dimension_full_name: str  # "question_alignment" 等
    state_review_key: str  # "qa_review" 等
    state_raw_key: str  # "qa_raw" 等

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm
        self.prompt_template = load_prompt(self.dimension_full_name)

    def __call__(self, state: ReviewerState) -> dict:
        """LangGraph node 簽名:接收 state，回傳要更新的 state 欄位"""
        try:
            raw_output = self._invoke_with_retry(state)
            dim_review = self._build_dimension_review(raw_output)
            return {
                self.state_review_key: dim_review,
                self.state_raw_key: raw_output,
                "total_tokens": state["total_tokens"] + raw_output.usage_tokens
            }
        except AllRetriesFailedError:
            failed_review = self._build_failed_review()
            return {
                self.state_review_key: failed_review,
                self.state_raw_key: None,
                "failed_dimensions": state["failed_dimensions"] + [self.dimension_code]
            }

    def _invoke_with_retry(self, state: ReviewerState) -> DimensionLLMOutput:
        """執行 LLM call，含 retry 與 schema 驗證"""
        last_error = None
        for attempt in range(3):  # 第 1 次 + 2 次 retry
            try:
                prompt = self.prompt_template.format(
                    task=state["task"], report=state["report"]
                )
                response = self.llm.invoke([
                    SystemMessage(content="..."),  # 從 prompt 切出 system
                    HumanMessage(content=prompt)
                ])
                # 解析為 JSON
                raw_json = parse_json_from_response(response)
                # 用 Pydantic 驗證
                output = DimensionLLMOutput.model_validate(raw_json)
                # 額外檢查維度一致性
                self._validate_dimension(output)
                return output
            except (ValidationError, JSONDecodeError, OpenAIError) as e:
                last_error = e
                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))  # 2s, 4s
        raise AllRetriesFailedError(...) from last_error

    def _build_dimension_review(self, raw: DimensionLLMOutput) -> DimensionReview:
        """從 LLM raw output 抽出 top_feedback 部分（不含 additional）"""
        return DimensionReview(
            dimension=self.dimension_full_name,
            dimension_summary=raw.dimension_summary,
            confidence=raw.confidence,
            top_feedback=raw.top_feedback,
            status=DimensionStatus.COMPLETED
        )

    def _build_failed_review(self) -> DimensionReview:
        return DimensionReview(
            dimension=self.dimension_full_name,
            dimension_summary="此維度評估失敗，請參考其他維度",
            confidence=0.0,
            top_feedback=[],
            status=DimensionStatus.FAILED
        )

    def _validate_dimension(self, output: DimensionLLMOutput):
        """檢查 LLM 真的有按指定維度回應（避免 LLM 弄混）"""
        # 例如檢查 output.dimension == self.dimension_full_name
```

### 2.2 各 node 實作

每個 node 繼承 base，只需設定 class attributes:

```python
# question_alignment.py
class QuestionAlignmentNode(ReviewerNodeBase):
    dimension_code = "QA"
    dimension_full_name = "question_alignment"
    state_review_key = "qa_review"
    state_raw_key = "qa_raw"
```

其他五個維度照辦。

### 2.3 LLM 設定

提供一個 helper 建立預設 LLM:

```python
# src/reviewer/llm.py
def create_default_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        temperature=0.2,  # 偏向確定性
        timeout=120,
        max_retries=0  # 我們自己處理 retry
    )
```

## 3. JSON 解析的注意事項

LLM 回傳的 JSON 可能包含:
- ` ```json ` 區塊包覆
- 前後多餘文字
- 中文引號（“ ” 而非 " "）

提供 `parse_json_from_response()` 處理這些 case:

```python
def parse_json_from_response(response: AIMessage) -> dict:
    text = response.content
    # 1. 抽出 ```json ... ``` 區塊（如果有）
    # 2. 否則嘗試找出第一個 { ... } 完整 JSON object
    # 3. 替換中文引號
    # 4. json.loads
    # 5. 失敗則 raise JSONDecodeError
```

## 4. 寫測試

### tests/test_nodes.py

不要呼叫真實 OpenAI API。用 Mock。

至少測試:

- 每個 node 的 dimension_code、dimension_full_name 設定正確
- LLM 回傳合法 JSON 時，正確 parse 為 DimensionReview
- LLM 回傳 invalid JSON 時觸發 retry
- LLM 連續 3 次失敗時，回傳 failed review（status=FAILED）
- failed_dimensions 正確更新
- LLM 回傳 nice_to_fix 在 top_feedback 時觸發 validation error → retry
- LLM 回傳超過 5 條 top_feedback 時觸發 validation error → retry
- LLM 回傳的 dimension 名稱與 node 不符時觸發 retry

### tests/test_prompts.py

至少測試:

- 每個 prompt 檔可以正確 load
- 每個 prompt 包含必要區塊（role, context, constraints, severity_definition, output_format）
- 每個 prompt 包含共用防幻覺條款（檢查特定關鍵字存在）
- `{task}` 與 `{report}` placeholder 存在

## 5. 手動驗證（可選但建議）

寫一個簡單的腳本 `scripts/manual_test.py`:

```python
"""
手動測試單一 reviewer node 用真實 OpenAI。
僅供開發者驗證，不在 CI 跑。
"""
def main():
    task = "比較 Apple 與 Samsung 2024 年的智慧手機策略"
    report = """[一份故意有問題的測試報告]"""

    llm = create_default_llm()
    node = QuestionAlignmentNode(llm)

    # 模擬 state
    state = create_initial_state(task=task, report=report)

    result = node(state)
    print(json.dumps(result, ensure_ascii=False, indent=2))
```

可選:寫六個 cli 工具，方便逐一測試各維度。

## 6. Phase 2 完成後請回報

完成後請在最終回應中:

1. 列出建立的所有檔案（含路徑）
2. 列出 prompts 的字數統計（每個 prompt 應在 800-2000 字之間）
3. 列出測試結果
4. 列出每個 node 的關鍵設計決策
5. 若手動測試了某些 node，附上實際 LLM 輸出範例
6. **不要進入 Phase 3**，等待人類 review

## 7. 不要做的事

- 不要把六個 node 串成 graph（Phase 3 才做）
- 不要實作 graph.py
- 不要做主動驗證（fetch URL 等）
- 不要在 prompt 中寫死領域知識（保持通用性）
- 不要為了讓測試過而放寬 schema 驗證
