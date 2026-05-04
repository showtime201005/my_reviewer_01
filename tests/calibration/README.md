# Calibration Test Cases

Place your YAML calibration cases here. Each file should follow this format:

```yaml
# case_001.yaml
task: "使用者的原始問題"
report: |
  報告全文...
expected_issues:
  - dimension: IR        # QA, IR, CP, LC, SQ, PS
    severity: must_fix   # must_fix, should_fix, nice_to_fix
    summary: "缺 2024 Q3 數據"
  - dimension: LC
    severity: should_fix
    summary: "結論段與 section 3 數字不一致"
notes: "這份報告主要問題是資料缺漏與輕微的邏輯不一致"
```

Run calibration with:
```bash
python scripts/run_calibration.py
```
