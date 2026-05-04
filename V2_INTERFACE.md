# v2 Active Verification Interface

當 v2 加入主動驗證（fetch URL、external search）時的接口契約。給 v2 設計者參考。

## v1 預留欄位

### 每條 Feedback 預留

| 欄位 | v1 值 | v2 用途 |
|---|---|---|
| `source_verification` | `None` | 主動 fetch URL 後的比對結果 |
| `external_check_result` | `None` | 額外搜尋的結果 |

### 整體輸出預留

| 欄位 | v1 值 | v2 用途 |
|---|---|---|
| `v2_interface.citation_sources` | `None` | 從報告抽取的 citation URLs |
| `v2_interface.external_searches_performed` | `[]` | 執行過的搜尋列表 |
| `v2_interface.fact_check_results` | `[]` | 事實檢查結果 |

### Metadata 預留

| 欄位 | v1 值 | v2 用途 |
|---|---|---|
| `review_metadata.active_verification_used` | `False` | 是否執行了主動驗證 |

### Verification Level 預留

| Level | v1 使用 | v2 使用 |
|---|---|---|
| `text_only` | ✓（預設） | ✓ |
| `knowledge_based` | ✓ | ✓ |
| `source_verified` | ✗ | ✓ fetch URL 並比對後標記 |
| `external_check` | ✗ | ✓ 執行額外搜尋後標記 |

## v2 升級時不該改的東西

- 整體 schema 結構（`ReviewOutput`、`DimensionReview`、`Feedback` 的欄位組成）
- 下游 agent 接口（`review()` 函式簽名、`build_reviewer_graph()`）
- 六個維度的分割方式
- Severity 三級定義（`must_fix` / `should_fix` / `nice_to_fix`）
- Top 5 機制（每維度 top_feedback 最多 5 條）
- `nice_to_fix` 只進 `additional_observations` 的規則
- Aggregator 的純 Python 實作方式

## v2 升級時可改的東西

- 個別 reviewer node 內部邏輯（加入 fetch URL / search 步驟）
- Prompt 內容（提供工具使用指引）
- `verification_level` 列舉值的使用範圍（v2 可用 `source_verified` / `external_check`）
- `source_verification` 和 `external_check_result` 欄位填充（v1 強制為 None，v2 可填入實際結果）
- `v2_interface` 下的三個子欄位

## 升級節奏建議

1. **先升級 Source Quality Reviewer**（最受益於主動驗證）
   - 可 fetch URL 驗證引用來源內容是否與報告描述一致
   - `verification_level` 改為 `source_verified`
   - 填充 `source_verification` 欄位

2. **再升級 Information Recall Reviewer**（驗證關鍵事實存在性）
   - 可執行外部搜尋確認事實是否存在
   - `verification_level` 改為 `external_check`
   - 填充 `external_check_result` 欄位

3. **其他四個維度 v2 仍保持被動**
   - QA、CP、LC、PS 主要依賴文本分析，主動驗證收益較低

## 建議的 v2 接入方式

```python
def review(
    task: str,
    report: str,
    # --- v1 既有 ---
    task_id: str = None,
    report_id: str = None,
    llm = None,
    # --- v2 新增 ---
    citation_sources: dict[str, str] | None = None,  # URL → 已抓取的內容
    enable_active_verification: bool = False,         # 是否執行主動搜尋
) -> ReviewOutput:
    ...
```

### `citation_sources` 預先傳入

如果父 agent 在 research 階段已經 fetch 過 URL，可以直接傳入，避免 reviewer 重複 fetch：

```python
# 父 agent 已有的 URL 內容
citations = {
    "https://example.com/report": "頁面內容...",
    "https://news.example.com/article": "文章內容...",
}

output = review(
    task="...",
    report="...",
    citation_sources=citations,
    enable_active_verification=True,
)
```

### Schema 向後相容

v2 的 `ReviewOutput` 結構不會改變。下游 agent 的程式碼：

```python
# 這段 v1 的程式碼在 v2 依然有效
for dim_review in output.dimension_reviews.values():
    for fb in dim_review.top_feedback:
        print(fb.severity, fb.one_liner)
```

唯一的差異：v2 的 feedback 可能有 `source_verification` 和 `external_check_result` 不為 None。下游 agent 可以選擇使用或忽略這些額外資訊。

## v2 設計者注意事項

1. **成本控制**：主動 fetch URL 會增加延遲和成本。建議只對 `must_fix` 候選項進行主動驗證。
2. **Rate limiting**：fetch 外部 URL 需要考慮速率限制和超時處理。
3. **隱私**：fetch URL 可能暴露 reviewer 的存在，某些場景下需要考慮。
4. **Schema 驗證**：`source_verification` 和 `external_check_result` 目前型別為 `Optional[Any]`，v2 應定義具體的 Pydantic model。
5. **Prompt 修改**：v2 的 SQ 和 IR prompt 需要加入工具使用指引（如何使用 fetch 結果、如何解讀搜尋結果）。
