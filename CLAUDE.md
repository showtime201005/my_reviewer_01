# CLAUDE.md — Reviewer Graph 實作工作規範

This file provides guidance to Claude Code when working on this project.

## 專案背景

這是一個 **Deep Research Report Reviewer** 的實作專案。Reviewer 是一個 LangGraph subgraph，接收 deep research agent 產出的報告 + 使用者原始問題，輸出結構化的修改建議（feedback），讓下游 agent 在下一次重新產生報告時能改善品質。

完整規格見 `PROJECT_SPEC.md`。各階段任務見 `PHASE1_TASKS.md`、`PHASE2_TASKS.md`、`PHASE3_TASKS.md`、`PHASE4_TASKS.md`。

## 工作流程

**重要：本專案採用分階段實作**

每個 PhaseN_TASKS.md 是一次的工作範圍。完成一個 Phase 後**停止並等待人類 review**，不要主動進入下一個 Phase。

每個 Phase 的工作流程：

1. 仔細閱讀對應的 PhaseN_TASKS.md
2. 仔細閱讀 PROJECT_SPEC.md 中相關章節
3. 開始實作前，**簡述你打算怎麼做**（檔案清單、關鍵設計決策），等待確認
4. 實作完成後，跑過所有測試確保通過
5. 在最終回應中總結:做了什麼、檔案清單、有什麼決策需要使用者注意

## 技術 Stack

- **語言**: Python 3.11+
- **核心框架**: LangGraph (latest)
- **LLM SDK**: LangChain + langchain-openai (ChatOpenAI)
- **資料驗證**: Pydantic v2
- **測試**: pytest
- **打包**: 使用 `pyproject.toml`，採用 src/ layout

## 不要做的事

- **不要使用 LangSmith、streaming、observability** — MVP 階段不需要
- **不要做並行 node** — 六個維度 node 採序列執行（使用者明確要求）
- **不要主動 fetch URL 或執行搜尋** — 純被動 reviewer，但必須在 schema 預留 v2 主動驗證接口
- **不要自己發明 schema 欄位** — 完全照 PROJECT_SPEC.md 定義的 schema
- **不要在 prompt 中寫死領域知識** — prompt 只給通用指引，不偏向特定領域
- **不要為了湊滿 5 條 feedback 而降低標準** — 在 prompt 中強調「寧少勿假」

## 一定要做的事

- **Prompt 寫在獨立 .md 檔**，不寫在 Python string literal
- **每個 node 都要 retry 2 次**（exponential backoff）
- **Pydantic schema 嚴格驗證 LLM 輸出**，驗證失敗要重試
- **每條 feedback 必須有 evidence_in_report**，不能空字串
- **保留 v2 主動驗證接口**:`source_verification`、`external_check_result`、`v2_interface` 欄位 v1 都填 null 但結構必須在
- **Aggregator 用純 Python 實作**，不呼叫 LLM
- **錯誤處理**:單一維度 node 失敗（重試 2 次後仍失敗）時，該維度標為 failed，confidence = 0、top_feedback = []，其他維度照常執行

## 程式碼風格

- 用 type hints
- 用 dataclasses 或 Pydantic models（不要用裸 dict）
- 公開函式必須有 docstring
- 命名: snake_case for functions/variables, PascalCase for classes
- 不需要 100% 註解，但複雜邏輯必須有解釋
- 錯誤訊息要清楚（包含上下文）

## 測試規範

- 每個 phase 完成時必須通過所有單元測試
- Phase 1 主要測 schema 驗證、Aggregator 邏輯
- Phase 2 主要測各 reviewer node 能正確 parse LLM 輸出
- Phase 3 用 mock LLM response 測試完整 graph 流程
- Phase 4 用真實 LLM 跑端到端測試（需要 OPENAI_API_KEY）

## 重要設計原則

1. **以 feedback 為核心，無評分系統** — 不要產出任何 score、grade、percentage
2. **三級 severity**: must_fix / should_fix / nice_to_fix
3. **nice_to_fix 條目永遠不進 top_feedback**，全部進 additional_observations
4. **additional_observations 是給開發者看的**，下游 agent 應該過濾掉
5. **每個維度 top_feedback 最多 5 條**

## 與下游 agent 的接口

- 輸入: `task` (str) + `report` (str)
- 輸出: 結構化 JSON + 一段純文字 human-readable summary（雙輸出設計）
- 下游 agent 可以選擇用結構化 JSON（精細處理）或用純文字（簡單模式）

## 環境變數

- `OPENAI_API_KEY` — 必填
- `OPENAI_MODEL` — 預設 `gpt-4o`，可覆寫

## Commit 訊息

每個 phase 完成時建議 commit 訊息格式:
```
feat(phaseN): <一句話描述>

- 完成項目 1
- 完成項目 2
```

## 不確定時怎麼辦

如果 PROJECT_SPEC 或 PhaseN_TASKS 有模糊地方:

1. **不要自己發明** — 寧可暫停問使用者
2. 在程式碼中加 `# TODO: 待確認 - <問題描述>`，並在最終回應中列出所有 TODO
3. 對於微小的決策（變數命名、檔案位置等），可以自己決定，但要在最終回應簡述
