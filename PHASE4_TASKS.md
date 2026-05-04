# PHASE4_TASKS.md — 校準與文件確認

## 前置條件

Phase 1、2、3 已完成且通過 review。

## 目標

用真實 LLM 跑完整 review，對 reviewer 行為做品質檢驗（precision 為主）。產出最終文件給上游 agent 團隊與 v2 設計者。

## 1. 準備測試報告（由使用者提供）

**這部分由使用者準備測試報告，Claude Code 不需自行生成。**

使用者會提供 5-10 份測試報告，每份附帶:

- task: 使用者原始問題
- report: deep research agent 產出的報告
- expected_issues: 人工標註的「該被抓出的問題」清單，含維度、嚴重度、簡述

預期格式:

```yaml
# tests/calibration/case_001.yaml
task: "..."
report: |
  ...
expected_issues:
  - dimension: IR
    severity: must_fix
    summary: "缺 2024 Q3 數據"
  - dimension: LC
    severity: should_fix
    summary: "結論段與 section 3 數字不一致"
  # ...
notes: "這份報告主要問題是資料缺漏與輕微的邏輯不一致"
```

若使用者尚未提供測試報告，**這個 phase 暫停**，等待使用者準備。

Claude Code 可以先做以下準備工作:

## 2. 實作校準工具

### 2.1 calibration runner

```python
# scripts/run_calibration.py

"""
跑校準測試:對每份測試報告跑 reviewer，比對 expected_issues 與實際 feedback。

輸出:
- precision: 實際 feedback 中有多少符合 expected_issues
- recall: expected_issues 中有多少被抓到
- 各維度的 precision / recall
- false positives 列表（reviewer 抓了但不該抓的）
- false negatives 列表（reviewer 漏抓的）
"""

def load_calibration_cases(directory: str) -> List[CalibrationCase]:
    """從 yaml 檔載入測試案例"""

def run_review_on_case(case: CalibrationCase) -> ReviewOutput:
    """對一個 case 跑 reviewer"""

def compare_with_expected(
    review_output: ReviewOutput,
    expected_issues: List[ExpectedIssue]
) -> CalibrationResult:
    """
    比對。注意 LLM 輸出有變動性，比對時需要寬鬆 matching:
    - 維度必須一致
    - severity 容許差一級（例如人標 must_fix，reviewer 報 should_fix 算半對）
    - one_liner / summary 用 LLM 做語意比對（可選），或人工 review
    """

def main():
    cases = load_calibration_cases("tests/calibration/")
    results = []
    for case in cases:
        output = run_review_on_case(case)
        result = compare_with_expected(output, case.expected_issues)
        results.append(result)

    # 印出彙總
    print_summary(results)

    # 寫詳細 report 到檔案
    write_detailed_report(results, "calibration_report.md")
```

### 2.2 比對策略

精確比對很困難（LLM 輸出有變動性），建議:

- **嚴格比對**:同一個維度抓到「相同問題」（用人工判定或 keyword overlap）算 match
- **寬鬆比對**:reviewer 抓出的 issue 涉及 expected 的關鍵字算 match
- **語意比對**（可選）:用另一個 LLM call 比對「這兩條 feedback 是否在說同一件事」

MVP 階段建議**先做寬鬆比對**（keyword-based），人工確認結果。語意比對留待之後。

### 2.3 輸出 report 格式

`calibration_report.md` 內容:

```markdown
# Calibration Report

## Summary

- Total cases: 7
- Total expected issues: 42
- Total reviewer feedback: 51 (top_feedback only, excluding additional_observations)
- Overall precision: 0.78
- Overall recall: 0.71

## Per-dimension stats

| Dimension | Precision | Recall | False Positives | False Negatives |
|-----------|-----------|--------|-----------------|-----------------|
| QA        | 0.83      | 0.75   | 2               | 3               |
| IR        | 0.71      | 0.68   | ...             | ...             |
| ...

## Per-case details

### Case 001 (...)

**Expected issues**:
- IR.must_fix: 缺 2024 Q3 數據

**Reviewer found**:
- IR-001 (must_fix): 缺 2024 Q3 數據 ✓ MATCH
- LC-001 (should_fix): 結論未充分論述 ✗ FALSE POSITIVE

**Notes**:
- LC-001 是合理發現但人類沒標到，可能不是 false positive 而是補充

### ...
```

## 3. 校準目標

依 v2 設計文件第 10 章建議:

- **Precision ≥ 80%**:reviewer 抓的問題大部分是真問題（避免誤導 agent）
- **Recall ≥ 70%**（次要目標）:能抓到大部分真問題

**Precision 比 Recall 重要**。若 precision 不達標，prompt 需加強防幻覺;若 recall 不達標但 precision 高，可調整 prompt 提高敏感度。

## 4. 若校準結果不達標

如果 precision < 80%，需要調整 prompt。建議流程:

1. 列出所有 false positives，分析原因（reviewer 為什麼亂指責）
2. 找出共通模式（例如 reviewer 老是把「合理但簡短」當成「論述深度不足」）
3. 在對應維度的 prompt 加入更精確的指引
4. 重跑校準，看是否改善

每次 prompt 調整後 commit，方便追蹤改動效果。

## 5. 文件交付

完成校準後，產出以下文件供上游 agent 團隊參考:

### 5.1 INTEGRATION_GUIDE.md

```markdown
# Reviewer Integration Guide

給上游 deep research agent 團隊參考。

## 接口

### 函式呼叫

```python
from reviewer import review

output = review(task=user_question, report=report_content)
```

### Subgraph 嵌入

...

## 輸出處理

ReviewOutput 包含三個給 agent 用的部分與一個給人看的部分:

### Agent 應處理

1. `dimension_reviews.*.top_feedback` — 主要的 feedback 列表
2. `human_summary.severity_distribution` — 快速判斷整體狀況
3. `review_metadata.failed_dimensions` — 注意是否有維度失敗

### Agent 應過濾掉

- `additional_observations` — 這部分只給開發者看，不要當作 feedback 處理

### 給開發者看

- `human_readable_text` — 純文字版本，方便人類快速掃描

## 處理 feedback 的建議邏輯

```python
def process_review(review_output):
    # 過濾掉開發者用的部分
    review_output.additional_observations = []

    # 按 severity 排序處理
    must_fix_items = []
    for dim_review in review_output.dimension_reviews.values():
        for fb in dim_review.top_feedback:
            if fb.severity == "must_fix":
                must_fix_items.append(fb)

    # 按 fix_type 分組
    by_fix_type = group_by(must_fix_items, key=lambda fb: fb.fix_type)

    # 對每組執行對應動作
    for fix_type, items in by_fix_type.items():
        if fix_type == "search_more":
            # 執行新搜尋
            ...
        elif fix_type == "rewrite_section":
            # 重寫對應 section
            ...
        # ...
```

## 注意事項

- `confidence < 0.7` 的 feedback 可考慮降低處理優先順序
- `verification_level == "knowledge_based"` 的 feedback 是 reviewer 用內部知識判斷，不一定可靠
- failed_dimensions 包含的維度，agent 應該知道該維度沒有評估到
```

### 5.2 V2_INTERFACE.md

給 v2 主動驗證設計者參考:

```markdown
# v2 Active Verification Interface

當 v2 加入主動驗證（fetch URL、external search）時，與 v1 的接口契約。

## v1 預留欄位

每條 feedback 已預留:
- `source_verification`: 主動 fetch URL 後的比對結果
- `external_check_result`: 額外搜尋的結果

整體輸出已預留:
- `v2_interface.citation_sources`: 從報告抽取的 citation URLs
- `v2_interface.external_searches_performed`: 執行過的搜尋
- `v2_interface.fact_check_results`: 事實檢查結果

## v2 升級時不該改的東西

- 整體 schema 結構
- 下游 agent 接口
- 維度分割
- Severity 三級
- top 5 機制

## v2 升級時可改的東西

- 個別 reviewer node 內部邏輯（加入 fetch URL 步驟）
- prompt（提供工具使用指引）
- verification_level 列舉值的使用（v1 一律 text_only / knowledge_based，v2 可用 source_verified / external_check）

## 升級節奏建議

1. 先升級 Source Quality Reviewer（最受益於主動驗證）
2. 再升級 Information Recall Reviewer（驗證關鍵事實存在性）
3. 其他四個維度 v2 仍保持被動

## 接入方式

提供建議的 API:

```python
def review(
    task: str,
    report: str,
    citation_sources: Optional[Dict[str, str]] = None,  # v2 新增:URL → 內容
    enable_active_verification: bool = False,  # v2 新增:是否執行主動搜尋
    ...
):
    ...
```

`citation_sources` 預先傳入時，reviewer 不需自己 fetch（節省成本）。
```

## 6. Phase 4 完成後請回報

完成後請在最終回應中:

1. 列出 calibration 結果（precision / recall by dimension）
2. 列出 prompt 調整紀錄（如有）
3. 列出建立的所有最終文件
4. 列出建議 v2 設計者注意事項
5. 若使用者尚未提供 calibration cases，列出仍需使用者完成的工作

## 7. 整體專案完成檢查表

最後產出一份 `FINAL_CHECKLIST.md`:

- [ ] 六個維度的 prompt 都 ≥ 800 字
- [ ] 所有 schema validation 測試通過
- [ ] Mock LLM 端到端測試通過
- [ ] 真實 LLM integration 測試通過
- [ ] Calibration precision ≥ 80%（若有 cases）
- [ ] README、INTEGRATION_GUIDE、V2_INTERFACE 文件齊全
- [ ] examples/ 包含可運行範例
- [ ] CI 設定（如需要）
- [ ] 所有 TODO 已記錄或解決
