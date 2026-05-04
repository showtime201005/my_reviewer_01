# Final Checklist

## 核心功能

- [x] 六個維度的 Pydantic schema 完整定義（schemas.py）
- [x] ReviewerState TypedDict + create_initial_state helper（state.py）
- [x] 純 Python Aggregator 邏輯（aggregator.py）
- [x] 六個維度的 prompt ≥ 800 字（prompts/*.md）
- [x] 六個 reviewer node 含 retry 邏輯（nodes/*.py）
- [x] Input validator node（nodes/input_validator.py）
- [x] LangGraph 序列圖組裝（graph.py）
- [x] 函式接口 `review()`（__init__.py）
- [x] Subgraph 接口 `build_reviewer_graph()`（graph.py）
- [x] JSON 解析工具含容錯（llm.py）

## 測試

- [x] Schema validation 測試通過（test_schemas.py）
- [x] Aggregator 邏輯測試通過（test_aggregator.py）
- [x] Prompt 載入與內容測試通過（test_prompts.py）
- [x] Node retry 邏輯測試通過（test_nodes.py）
- [x] Mock LLM 端到端測試通過（test_graph.py）
- [x] 真實 LLM integration 測試可運行（test_integration.py）
- [ ] Calibration precision ≥ 80%（等待使用者提供 calibration cases）

## 文件

- [x] README.md — 安裝、使用、開發指引
- [x] INTEGRATION_GUIDE.md — 給上游 agent 團隊
- [x] V2_INTERFACE.md — 給 v2 設計者
- [x] PROJECT_SPEC.md — 完整規格（原始提供）
- [x] examples/ — 可運行範例

## 工具

- [x] scripts/manual_test.py — 手動測試單一 node
- [x] scripts/run_calibration.py — 校準工具
- [x] tests/calibration/ — 校準 case 目錄（等待使用者填入）

## 待使用者完成

- [ ] 提供 5-10 份人工標註的校準測試報告（tests/calibration/case_*.yaml）
- [ ] 跑 `python scripts/run_calibration.py` 確認 precision/recall
- [ ] 若 precision < 80%，與 Claude Code 協作調整 prompt
