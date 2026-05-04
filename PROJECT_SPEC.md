# PROJECT_SPEC.md — Reviewer Graph 完整規格

## 1. 專案目標

實作一個 LangGraph subgraph，作為 Deep Research Report 的 reviewer。

**輸入**: 使用者問題 + deep research agent 產出的報告
**輸出**: 結構化 JSON feedback（給上游 agent 程式化處理）+ 純文字摘要（給開發者快速讀）

Reviewer 不打分，純粹產出「該怎麼修」的具體建議。

## 2. 核心設計原則

1. **以 feedback 為核心** — 沒有任何 score / grade / percentage
2. **被動 reviewer** — 只讀文字，不 fetch URL、不執行搜尋（v2 才會加主動驗證）
3. **每輪獨立** — 不讀過往歷史，每次都是全新 review
4. **六個維度序列執行** — 一個 LLM 處理一個維度
5. **寧少勿假** — 對不確定的問題不報，避免 hallucination
6. **預留 v2 接口** — Schema 中保留主動驗證相關欄位（v1 全部填 null）

## 3. 六個評分維度

| 維度 | 代號 | 評估內容 |
|---|---|---|
| Question Alignment | QA | 報告是否真的回答任務的核心問題;有無偏離主題或誤解任務範圍 |
| Information Recall | IR | 是否取回任務需要的具體事實 / 數據;有無關鍵資訊缺失;範圍是否齊全 |
| Completeness | CP | 論述層面的完整度:該討論的面向是否都討論;trade-off / 反向觀點是否考量 |
| Logical Coherence | LC | 結論是否從證據推得;前後段是否矛盾;推理鏈是否有跳躍 |
| Source Quality | SQ | 引用來源權威性;一手 vs 二手來源使用;關鍵數據是否有引用 |
| Presentation & Specificity | PS | 結構清晰度、格式合規、避免空泛模糊用語、具體層級足夠 |

維度執行順序:**QA → IR → CP → LC → SQ → PS**（按依賴順序，沒對齊主問題前討論其他維度意義不大）

## 4. Severity 三級

| Severity | 含義 | 典型情境 |
|---|---|---|
| `must_fix` | 必修 | 不修報告就有嚴重問題:可能造成傷害的錯誤建議、明顯與內部知識衝突的事實、報告完全偏離任務、關鍵資訊缺失、明顯邏輯矛盾 |
| `should_fix` | 建議修 | 能明顯提升品質但不算嚴重缺陷:論述深度不足、來源強度可改善、結構不夠清晰 |
| `nice_to_fix` | 可選修 | 邊際改善:呈現細節、輕微冗餘。**永遠不進 top_feedback，全部進 additional_observations** |

**Top 5 機制**:
- 每維度 top_feedback 最多 5 條
- 優先選 must_fix → should_fix
- nice_to_fix 永遠進 additional_observations
- 寧可少於 5 條也不可硬湊

## 5. Fix Type 六分類

| fix_type | Agent 行動 | 典型情境 |
|---|---|---|
| `search_more` | 執行新的搜尋 | 資料缺失、需要更多細節 |
| `replace_source` | 換掉現有引用 | 引用權威性不足、二手聚合來源 |
| `rewrite_section` | 純改寫，不需新資料 | 結構混亂、邏輯不清、矛盾陳述 |
| `remove_claim` | 刪除某個陳述 | 該陳述明顯錯誤、無支持 |
| `add_perspective` | 補充另一個觀點 | 缺反向觀點、缺 trade-off |
| `reformat` | 改變呈現格式 | 格式不符任務要求、應用表格卻用段落 |

## 6. Verification Level

每條 feedback 必須標記 `verification_level`:

| Level | v1 用嗎 | 意義 |
|---|---|---|
| `text_only` | ✓（預設） | 純讀報告判斷，未驗證任何外部資訊 |
| `knowledge_based` | ✓ | 基於 LLM 內部知識判斷與報告陳述衝突，confidence 通常較低 |
| `source_verified` | ✗（v2.x） | 已 fetch URL 並比對 |
| `external_check` | ✗（v2.x） | 已執行額外搜尋 |

## 7. 完整 Schema 定義

### 7.1 整體輸出（Aggregator 產出）

```python
{
  "review_metadata": {
    "reviewer_version": "v1.0-passive",
    "task_id": str,
    "report_id": str,
    "review_cost_tokens": int,
    "review_latency_seconds": float,
    "active_verification_used": False,  # v1 永遠 False
    "failed_dimensions": []  # 若有 dimension 重試 2 次後仍失敗，列在這
  },

  "human_summary": {
    "key_findings": str,  # Aggregator 拼接六個維度的 dimension_summary
    "severity_distribution": {
      "must_fix": int,
      "should_fix": int,
      "nice_to_fix": int
    },
    "dimensions_with_issues": [str],  # 例如 ["IR", "LC"]
    "dimensions_clean": [str],
    "highlights": [str]  # must_fix 級的前 3-5 條 one_liner
  },

  "human_readable_text": str,  # 純文字版本，給開發者讀或下游 agent 簡單模式用

  "dimension_reviews": {
    "question_alignment": DimensionReview,
    "information_recall": DimensionReview,
    "completeness": DimensionReview,
    "logical_coherence": DimensionReview,
    "source_quality": DimensionReview,
    "presentation_specificity": DimensionReview
  },

  "additional_observations": [Feedback],  # 給開發者看，下游 agent 應過濾

  "v2_interface": {
    "citation_sources": None,  # v1 永遠 None
    "external_searches_performed": [],
    "fact_check_results": []
  }
}
```

### 7.2 DimensionReview

```python
{
  "dimension": str,  # "question_alignment" 等
  "dimension_summary": str,  # 一句話以內整體狀況
  "confidence": float,  # 0.0-1.0
  "top_feedback": [Feedback],  # 最多 5 條
  "status": "completed" | "failed"  # 重試 2 次後仍失敗則 failed
}
```

### 7.3 Feedback 條目

```python
{
  "id": str,  # 格式 "[維度代號]-[流水號]" 例 "QA-001"
  "severity": "must_fix" | "should_fix" | "nice_to_fix",
  "one_liner": str,  # ≤ 25 字摘要
  "detail": str,  # 2-4 句話詳細描述
  "evidence_in_report": str,  # 報告中支持此 feedback 的原文片段
  "fix_type": "search_more" | "replace_source" | "rewrite_section" | "remove_claim" | "add_perspective" | "reformat",
  "fix_target": str,  # 修改目標位置
  "fix_hint": str,  # 1-2 句修復建議
  "verification_level": "text_only" | "knowledge_based" | "source_verified" | "external_check",
  "confidence": float,  # 0.0-1.0
  "source_verification": None,  # v1 永遠 None
  "external_check_result": None  # v1 永遠 None
}
```

## 8. LangGraph 架構

### 8.1 整體 Graph 結構

```
START
  ↓
[input_validator]
  ↓
[qa_reviewer]   (Question Alignment)
  ↓
[ir_reviewer]   (Information Recall)
  ↓
[cp_reviewer]   (Completeness)
  ↓
[lc_reviewer]   (Logical Coherence)
  ↓
[sq_reviewer]   (Source Quality)
  ↓
[ps_reviewer]   (Presentation & Specificity)
  ↓
[aggregator]
  ↓
END
```

序列執行（使用者明確選擇）。每個 reviewer node 是一個 LLM call。

### 8.2 State 設計

```python
class ReviewerState(TypedDict):
    # 輸入
    task: str
    report: str
    task_id: str
    report_id: str

    # 中間結果（每個維度跑完後填）
    qa_review: Optional[DimensionReview]
    ir_review: Optional[DimensionReview]
    cp_review: Optional[DimensionReview]
    lc_review: Optional[DimensionReview]
    sq_review: Optional[DimensionReview]
    ps_review: Optional[DimensionReview]

    # 元資料
    start_time: float
    total_tokens: int
    failed_dimensions: List[str]

    # 最終輸出（aggregator 填）
    final_output: Optional[Dict]
```

### 8.3 與父 Graph 的整合

Reviewer 設計為 LangGraph subgraph，可被父 graph 用 `add_node()` 嵌入。

提供兩種使用方式:

```python
# 方式 1: 作為 subgraph 嵌入
from reviewer import build_reviewer_graph
parent_graph.add_node("reviewer", build_reviewer_graph())

# 方式 2: 作為函式直接呼叫
from reviewer import review
result = review(task="...", report="...")
```

兩種方式內部共用同一個 graph 實作。

## 9. 各維度的 Reviewer 設計重點

### 9.1 共用 Prompt 骨架

所有六個維度的 prompt 都遵循相同骨架（細節在 prompts/*.md）:

```
<role>
你是 [維度名稱] 的專業審稿人，專責檢查報告在此維度的問題。
你不為報告打分，只指出問題並提出修改建議。
</role>

<context>
任務描述: {task}
報告全文: {report}
</context>

<dimension_specific_instructions>
[該維度的關鍵檢查項]
</dimension_specific_instructions>

<constraints>
- 你只能根據報告文字判斷，不能 fetch URL，不能執行搜尋
- 不要寫'該 URL 內容不符'這類你無法驗證的話
- 不要編造修復建議，必須基於報告中可見的線索
- top_feedback 最多 5 條。寧可少報也不可硬湊
- nice_to_fix 級永遠不進 top_feedback
</constraints>

<severity_definition>
（見 PROJECT_SPEC §4）
</severity_definition>

<output_format>
（嚴格 JSON schema，見 PROJECT_SPEC §7.2）
</output_format>
```

### 9.2 各維度差異化重點

**Question Alignment**:
- 強調兩步驟:先抽取任務主問題、再檢查報告 vs 主問題
- 加入提示:「若任務本身範圍寬鬆，應寬容判斷」

**Information Recall**:
- 強調「不要假裝知道某事實在哪可找到」
- 加入提示:「若你想到某個關鍵事實該出現但報告沒有，必須具體寫出該事實是什麼」

**Completeness**:
- 明確區分「事實缺失（屬 IR）」與「論述面向缺失（屬 CP）」
- 加入提示:「給出具體缺失面向，不可只說『不夠全面』」

**Logical Coherence**:
- 加入「主動掃描矛盾」步驟:列出每個關鍵主張並比對前後文
- 「指出矛盾時，必須引用兩處原文片段」

**Source Quality**:
- 嚴格禁止「驗證 URL 內容」相關語句
- 「即使覺得某 URL 內容可能不符，也只能寫 verification_level: text_only」

**Presentation & Specificity**:
- 提供「模糊詞列表」:許多、各種、通常、大幅、顯著、相關、有效、常見等
- 「不要為了湊滿 top 5 把 nice_to_fix 升級」

### 9.3 防幻覺 Prompt 共用條款

每個 prompt 都應加入:

- 「對每條 feedback，evidence_in_report 必須是報告中真實存在的片段。如果想不出 evidence，就不要報這條」
- 「confidence 必須誠實。猜測時 confidence ≤ 0.5。confidence < 0.6 應降為 nice_to_fix」
- 「需要外部知識才能判斷的問題，verification_level 必須標 knowledge_based 並降低 confidence」

## 10. Aggregator 邏輯（純 Python）

```python
def aggregate(state: ReviewerState) -> dict:
    """整合六個 dimension reviews 為最終輸出。不呼叫 LLM。"""

    dimension_reviews = collect_dimension_reviews(state)

    # 1. 收集 additional_observations
    additional = []
    for dim_review in dimension_reviews.values():
        # nice_to_fix 條目（從各維度的 raw output 中找）
        # 超出 top 5 的條目（理論上不應有，但若有需保留）
        additional.extend(extract_nice_to_fix(dim_review))

    # 2. 計算 severity_distribution
    severity_dist = count_severities(dimension_reviews, additional)

    # 3. 分類維度狀況
    with_issues = []
    clean = []
    for dim_code, dim_review in dimension_reviews.items():
        if has_must_or_should_fix(dim_review):
            with_issues.append(dim_code)
        else:
            clean.append(dim_code)

    # 4. 抽 highlights（must_fix 前 3-5 條）
    highlights = extract_must_fix_highlights(dimension_reviews, max_n=5)

    # 5. 拼 key_findings
    key_findings = " ".join(
        dr["dimension_summary"]
        for dr in dimension_reviews.values()
        if dr["dimension_summary"]
    )

    # 6. 產出 human_readable_text（純文字版）
    human_readable = render_human_readable(
        key_findings, severity_dist, dimension_reviews
    )

    # 7. 組裝
    return {
        "review_metadata": {...},
        "human_summary": {
            "key_findings": key_findings,
            "severity_distribution": severity_dist,
            "dimensions_with_issues": with_issues,
            "dimensions_clean": clean,
            "highlights": highlights
        },
        "human_readable_text": human_readable,
        "dimension_reviews": dimension_reviews,
        "additional_observations": additional,
        "v2_interface": {
            "citation_sources": None,
            "external_searches_performed": [],
            "fact_check_results": []
        }
    }
```

`human_readable_text` 範例輸出:

```
## Review Summary

**主要發現**: 報告主要問題集中在資訊召回不足與部分結論缺乏支持。Question Alignment 整體 OK 但有輕微偏移。

**問題分布**: 3 個必修、8 個建議修、12 個可選修

**有問題的維度**: IR, LC, SQ
**乾淨的維度**: QA, CP, PS

**重點問題**:
- IR-001: 缺 2024 Q3 季度數據（must_fix）
- LC-001: 結論段與證據強度不一致（must_fix）
- SQ-002: section 3 多項數據無引用（must_fix）

詳細 feedback 請見結構化 JSON 輸出。
```

## 11. 錯誤處理

### 11.1 LLM Call 失敗

每個 reviewer node 採用以下策略:

1. 第一次嘗試
2. 失敗 → 等待 2 秒 → 第二次嘗試
3. 失敗 → 等待 4 秒 → 第三次嘗試
4. 仍失敗 → 該維度標 status = "failed"，confidence = 0.0、top_feedback = []
5. 該維度名稱加入 `state["failed_dimensions"]`

「失敗」包含以下情況:
- API 連線失敗、timeout、rate limit
- LLM 回傳無法 parse 為合法 JSON
- 回傳 JSON 但無法通過 Pydantic schema 驗證

### 11.2 部分維度失敗的處理

若 6 個維度中有部分失敗:
- 其他維度照常執行（序列流程不中斷）
- Aggregator 對 failed 維度的處理:`dimension_summary` 改為「此維度評估失敗，請參考其他維度」、`top_feedback` 為空陣列
- `review_metadata.failed_dimensions` 列出失敗的維度
- 若全部 6 個都失敗，整個 review 視為失敗，回傳 error response

### 11.3 輸入驗證失敗

`input_validator` node 若檢測到:
- task 為空字串
- report 為空字串或過短（< 100 字）
- task / report 過長（超過 model context limit）

應立即回傳 error，不執行後續流程。

## 12. 效能與成本目標

- 單次完整 review:< 60 秒（六個 LLM call 序列執行）
- 總 token 數:< 50K（取決於報告長度）
- 成本:每次 review < USD $0.50（用 gpt-4o）

若你發現實際遠超這些目標，請在最終回應中提醒使用者。

## 13. v2 主動驗證的升級路徑（不在本次實作範圍）

未來 v2 會加入:
- Source Quality reviewer 主動 fetch URL 比對內容
- Information Recall reviewer 執行外部搜尋確認事實存在性

v1 的設計必須讓 v2 升級時:
- Schema 結構不變（只填充既有的 null 欄位）
- 下游 agent 的程式碼不需修改
- 只需在 reviewer node 內部加入新邏輯，不需改 graph 結構

具體預留欄位:
- `feedback.source_verification`
- `feedback.external_check_result`
- `output.v2_interface.citation_sources`
- `output.v2_interface.external_searches_performed`
- `output.v2_interface.fact_check_results`
- `metadata.active_verification_used`
- `feedback.verification_level` 列舉值（已包含 v2 用的 source_verified、external_check）
