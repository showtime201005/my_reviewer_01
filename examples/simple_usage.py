"""Simple usage example — call review() as a function."""

from dotenv import load_dotenv
load_dotenv()

from reviewer import review

task = "比較 Apple 與 Samsung 2024 年的智慧手機策略"
report = open("examples/sample_report.md", encoding="utf-8").read()

output = review(task=task, report=report)

# Human-readable summary
print(output.human_readable_text)

# Structured data
print(f"\nSeverity: {output.human_summary.severity_distribution}")
print(f"Dimensions with issues: {output.human_summary.dimensions_with_issues}")

# Iterate over feedback
for dim_name, dim_review in output.dimension_reviews.items():
    for fb in dim_review.top_feedback:
        print(f"  [{fb.severity.value}] {fb.id}: {fb.one_liner}")
