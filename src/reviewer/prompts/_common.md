# _common.md — 共用片段參考

以下片段被各維度 prompt 直接引用（複製到各檔）。修改時請同步更新所有維度。

---

## Constraints 共用部分

```
- 你只能根據報告文字判斷，不能 fetch URL，不能執行搜尋。
- 不要寫「該 URL 內容不符」這類你無法驗證的話。
- 不要編造修復建議，必須基於報告中可見的線索。
- top_feedback 最多 5 條。寧可少報也不可硬湊。
- nice_to_fix 級永遠不進 top_feedback，全部放進 additional_observations。
```

## Severity Definition

```
severity 三級定義：
- must_fix：必修。不修報告就有嚴重問題。可能造成傷害的錯誤建議、明顯與內部知識衝突的事實、報告完全偏離任務、關鍵資訊缺失、明顯邏輯矛盾。
- should_fix：建議修。能明顯提升品質但不算嚴重缺陷。論述深度不足、來源強度可改善、結構不夠清晰。
- nice_to_fix：可選修。邊際改善：呈現細節、輕微冗餘。永遠不進 top_feedback，全部進 additional_observations。
```

## Selection Priority

```
選擇優先順序：
1. must_fix 條目優先進 top_feedback。
2. 接著 should_fix 條目按 confidence 降序填入。
3. nice_to_fix 永遠只放進 additional_observations。
4. 若 must_fix + should_fix 合計不足 5 條，就少於 5 條，不要硬湊。
```

## 防幻覺條款

```
- 對每條 feedback，evidence_in_report 必須是報告中真實存在的片段。
  如果你想不出 evidence，就不要報這條 feedback。
- confidence 必須誠實。如果你只是猜測，confidence 應 ≤ 0.5。
  confidence < 0.6 的條目應降為 nice_to_fix。
- 對於需要外部知識才能判斷的問題，verification_level 必須標 knowledge_based 並降低 confidence。
- top_feedback 最多 5 條。寧可少於 5 條，也不可硬湊。
- nice_to_fix 級永遠不放進 top_feedback，全部放進 additional_observations。
```

## Output Format

```
你必須回傳一個嚴格的 JSON object，格式如下：

{
  "dimension": "<維度全名>",
  "dimension_summary": "<一句話描述此維度的整體狀況>",
  "confidence": <0.0-1.0>,
  "top_feedback": [
    {
      "id": "<維度代號>-<三位數流水號>",
      "severity": "must_fix" | "should_fix",
      "one_liner": "<≤ 25 字摘要>",
      "detail": "<2-4 句話詳細描述>",
      "evidence_in_report": "<報告中支持此 feedback 的原文片段>",
      "fix_type": "search_more" | "replace_source" | "rewrite_section" | "remove_claim" | "add_perspective" | "reformat",
      "fix_target": "<修改目標位置>",
      "fix_hint": "<1-2 句修復建議>",
      "verification_level": "text_only" | "knowledge_based",
      "confidence": <0.0-1.0>,
      "source_verification": null,
      "external_check_result": null
    }
  ],
  "additional_observations": [
    // nice_to_fix 條目放這裡，格式同上但 severity 為 "nice_to_fix"
  ]
}

注意：
- id 格式必須為 [大寫兩字母代號]-[三位數字]，例如 QA-001、IR-042。
- one_liner 必須 ≤ 25 字（中英文各算 1 字）。
- evidence_in_report 不可為空字串。
- confidence 必須在 0.0-1.0 之間。
- source_verification 和 external_check_result 必須為 null（v1 限制）。
- top_feedback 中不可有 nice_to_fix 級條目。
- 只回傳 JSON，不要有其他文字。
```
