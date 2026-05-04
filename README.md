# Claude Code Handoff Package

這個資料夾包含交付給 Claude Code 的全套實作資料。

## 檔案說明

| 檔案 | 用途 | 給誰看 |
|---|---|---|
| `CLAUDE.md` | 工作規範、技術 stack、不要做的事 | Claude Code（整個專案參考） |
| `PROJECT_SPEC.md` | 完整規格:六維度、schema、graph 架構 | Claude Code（每個 phase 都會參考） |
| `PHASE1_TASKS.md` | 第一階段任務:基礎設施、schema、aggregator | Claude Code（先做） |
| `PHASE2_TASKS.md` | 第二階段任務:reviewer nodes 與 prompts | Claude Code（review 後做） |
| `PHASE3_TASKS.md` | 第三階段任務:graph 組裝與整合 | Claude Code（review 後做） |
| `PHASE4_TASKS.md` | 第四階段任務:校準與文件 | Claude Code（review 後做） |
| `README.md` | 本檔 | 你（使用者） |

## 使用方式

### Step 1: 建立新專案資料夾

```bash
mkdir my_reviewer
cd my_reviewer
```

### Step 2: 把這些檔案放進去

把 `CLAUDE.md`、`PROJECT_SPEC.md`、`PHASE1_TASKS.md` ~ `PHASE4_TASKS.md` 都複製到專案根目錄。

```bash
cp /path/to/handoff/*.md ./
```

### Step 3: 初始化 git（建議）

```bash
git init
git add .
git commit -m "chore: add project specs"
```

### Step 4: 啟動 Claude Code

```bash
claude
```

或者在現有專案中:
```bash
cd my_reviewer
claude
```

### Step 5: 給 Claude Code 第一個指令

打開 Claude Code 後，輸入:

```
請依照 CLAUDE.md 與 PROJECT_SPEC.md 的規範，開始執行 PHASE1_TASKS.md 的任務。

開始實作前，請先簡述你的計畫（檔案清單、關鍵設計），等我確認後再動手。
```

### Step 6: 每個 Phase 完成後

Claude Code 會在 Phase 完成後停下來。你需要:

1. 跑測試確認沒壞
2. 查看 Claude Code 列出的 TODO 與決策
3. 確認沒問題後，給下一個指令:

```
Phase 1 我 review 過了，沒問題。請開始 PHASE2_TASKS.md。
```

如果有問題，可以叫它修:

```
Phase 1 中 schemas.py 的 X 部分有問題，請修正:[具體說明]
```

## 預期時程

- **Phase 1（基礎設施）**: Claude Code 約需 30-60 分鐘
- **Phase 2（Reviewer nodes 與 prompts）**: 60-90 分鐘（prompt 寫作較費時）
- **Phase 3（Graph 組裝）**: 30-45 分鐘
- **Phase 4（校準）**: 取決於你提供的測試資料量

中間人類 review 時間另計。

## 注意事項

### Phase 4 前你需要準備的東西

PHASE4_TASKS.md 提到需要 5-10 份「人工標註的測試報告」用於校準。**這部分 Claude Code 不應該自行生成**，需要你手動準備。

格式參考 PHASE4_TASKS.md 第 1 節的 yaml 範例。

### OpenAI API Key

執行到 Phase 2 後段（手動測試）與 Phase 3 後段（integration test）會需要 `OPENAI_API_KEY`。請先準備好。

### Token 與成本估計

整個專案的 LLM 成本主要來自:
- Phase 2 手動測試:約 USD $1-3
- Phase 3 integration test:約 USD $0.50-1 per case
- Phase 4 校準:約 USD $5-10（視 cases 數量）

總計約 USD $10-20。

## 若 Claude Code 卡住

如果 Claude Code 在某個地方卡住或產生不對的東西:

1. **不要繼續強行修補** — 通常重新給更明確的指令會比較好
2. 檢查它有沒有 follow CLAUDE.md 的「不要做的事」清單
3. 可以叫它 reset:「請忽略剛才的實作，重新依照 PHASE_X_TASKS.md 第 N 節重做」

## 聯絡與回饋

實作過程中如有規格疑問，請暫停並提出問題，避免 Claude Code 在錯誤方向上花太多時間。
