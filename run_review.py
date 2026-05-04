from dotenv import load_dotenv

load_dotenv()

from reviewer import review

task = "找最新關於「如何評量與改善 LLM 引用準確度」的方法，包含學術論文和實務做法"
report = open("dr_report/compass_artifact_wf-9742a24c-6d0b-4582-a4a4-43e493d64b72_text_markdown.md", encoding="utf-8").read()

output = review(task=task, report=report)

# Write results to file (avoids Windows encoding issues)
import json

with open("review_output.md", "w", encoding="utf-8") as f:
    f.write(output.human_readable_text)

with open("review_output.json", "w", encoding="utf-8") as f:
    json.dump(output.model_dump(), f, ensure_ascii=False, indent=2, default=str)

print("Done! Results written to review_output.md and review_output.json")