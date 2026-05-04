"""Calibration runner — compare reviewer output against human-annotated expected issues.

Usage:
    python scripts/run_calibration.py [--cases-dir tests/calibration] [--output calibration_report.md]

Requires OPENROUTER_API_KEY in .env.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from reviewer import review
from reviewer.schemas import Feedback, ReviewOutput


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ExpectedIssue:
    dimension: str      # "QA", "IR", etc.
    severity: str       # "must_fix", "should_fix", "nice_to_fix"
    summary: str        # short description of the expected issue
    matched: bool = False
    match_id: str = ""  # id of the matched feedback


@dataclass
class CalibrationCase:
    name: str
    task: str
    report: str
    expected_issues: list[ExpectedIssue]
    notes: str = ""


@dataclass
class MatchResult:
    expected: ExpectedIssue
    feedback: Optional[Feedback]
    match_type: str  # "exact", "partial_severity", "none"


@dataclass
class CaseResult:
    case: CalibrationCase
    output: ReviewOutput
    matches: list[MatchResult]
    false_positives: list[Feedback]  # reviewer found but not in expected
    false_negatives: list[ExpectedIssue]  # expected but not found
    precision: float = 0.0
    recall: float = 0.0


@dataclass
class DimensionStats:
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def precision(self) -> float:
        total = self.true_positives + self.false_positives
        return self.true_positives / total if total > 0 else 1.0

    @property
    def recall(self) -> float:
        total = self.true_positives + self.false_negatives
        return self.true_positives / total if total > 0 else 1.0


# Mapping from dimension full name to code
_DIM_NAME_TO_CODE = {
    "question_alignment": "QA",
    "information_recall": "IR",
    "completeness": "CP",
    "logical_coherence": "LC",
    "source_quality": "SQ",
    "presentation_specificity": "PS",
}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_calibration_cases(directory: str | Path) -> list[CalibrationCase]:
    """Load all .yaml calibration cases from a directory."""
    cases_dir = Path(directory)
    cases = []
    for yaml_path in sorted(cases_dir.glob("case_*.yaml")):
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        expected = [
            ExpectedIssue(
                dimension=issue["dimension"],
                severity=issue["severity"],
                summary=issue["summary"],
            )
            for issue in data.get("expected_issues", [])
        ]

        cases.append(CalibrationCase(
            name=yaml_path.stem,
            task=data["task"],
            report=data["report"],
            expected_issues=expected,
            notes=data.get("notes", ""),
        ))

    return cases


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """Simple tokenizer: split on whitespace and punctuation, lowercase."""
    import re
    return set(re.findall(r"[\w]+", text.lower()))


def _keyword_overlap(a: str, b: str) -> float:
    """Compute Jaccard-like keyword overlap between two strings."""
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def compare_with_expected(
    output: ReviewOutput,
    expected_issues: list[ExpectedIssue],
    keyword_threshold: float = 0.15,
) -> CaseResult:
    """Compare reviewer output against expected issues using keyword-based matching.

    Matching rules:
    - Dimension must match exactly.
    - Summary keyword overlap must be >= threshold.
    - Severity exact match = full match; off by one level = partial match.
    """
    # Collect all reviewer feedback (top_feedback from all dimensions)
    all_feedback: list[Feedback] = []
    for dim_name, dim_review in output.dimension_reviews.items():
        for fb in dim_review.top_feedback:
            all_feedback.append(fb)

    # Track which feedback items have been matched
    matched_feedback_ids: set[str] = set()
    matches: list[MatchResult] = []

    for expected in expected_issues:
        best_fb: Feedback | None = None
        best_score: float = 0.0
        best_match_type = "none"

        for fb in all_feedback:
            if fb.id in matched_feedback_ids:
                continue

            # Dimension must match
            fb_dim_code = fb.id[:2]
            if fb_dim_code != expected.dimension:
                continue

            # Keyword overlap on summary vs one_liner + detail
            fb_text = f"{fb.one_liner} {fb.detail}"
            score = _keyword_overlap(expected.summary, fb_text)

            if score >= keyword_threshold and score > best_score:
                best_score = score
                best_fb = fb
                if fb.severity.value == expected.severity:
                    best_match_type = "exact"
                else:
                    best_match_type = "partial_severity"

        if best_fb is not None:
            matched_feedback_ids.add(best_fb.id)
            expected.matched = True
            expected.match_id = best_fb.id
            matches.append(MatchResult(
                expected=expected,
                feedback=best_fb,
                match_type=best_match_type,
            ))
        else:
            matches.append(MatchResult(
                expected=expected,
                feedback=None,
                match_type="none",
            ))

    # False positives: feedback not matched to any expected issue
    false_positives = [fb for fb in all_feedback if fb.id not in matched_feedback_ids]

    # False negatives: expected issues not matched
    false_negatives = [e for e in expected_issues if not e.matched]

    # Precision & recall
    tp = sum(1 for m in matches if m.match_type != "none")
    total_feedback = len(all_feedback)
    total_expected = len(expected_issues)

    precision = tp / total_feedback if total_feedback > 0 else 1.0
    recall = tp / total_expected if total_expected > 0 else 1.0

    return CaseResult(
        case=CalibrationCase(name="", task="", report="", expected_issues=expected_issues),
        output=output,
        matches=matches,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
    )


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(
    cases: list[CalibrationCase],
    results: list[CaseResult],
) -> str:
    """Generate a markdown calibration report."""
    lines: list[str] = []

    # Summary
    total_expected = sum(len(c.expected_issues) for c in cases)
    total_feedback = sum(
        sum(len(dr.top_feedback) for dr in r.output.dimension_reviews.values())
        for r in results
    )
    total_tp = sum(
        sum(1 for m in r.matches if m.match_type != "none")
        for r in results
    )
    total_fp = sum(len(r.false_positives) for r in results)
    total_fn = sum(len(r.false_negatives) for r in results)

    overall_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 1.0
    overall_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 1.0

    lines.append("# Calibration Report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total cases: {len(cases)}")
    lines.append(f"- Total expected issues: {total_expected}")
    lines.append(f"- Total reviewer feedback (top_feedback): {total_feedback}")
    lines.append(f"- True positives: {total_tp}")
    lines.append(f"- False positives: {total_fp}")
    lines.append(f"- False negatives: {total_fn}")
    lines.append(f"- **Overall precision: {overall_precision:.2f}**")
    lines.append(f"- **Overall recall: {overall_recall:.2f}**")
    lines.append("")

    # Target check
    if overall_precision >= 0.80:
        lines.append("> Precision target (≥ 0.80) **PASSED**")
    else:
        lines.append("> Precision target (≥ 0.80) **NOT MET** — review false positives and adjust prompts")
    if overall_recall >= 0.70:
        lines.append("> Recall target (≥ 0.70) **PASSED**")
    else:
        lines.append("> Recall target (≥ 0.70) **NOT MET** — consider increasing prompt sensitivity")
    lines.append("")

    # Per-dimension stats
    dim_stats: dict[str, DimensionStats] = {}
    for code in ["QA", "IR", "CP", "LC", "SQ", "PS"]:
        dim_stats[code] = DimensionStats()

    for r in results:
        for m in r.matches:
            code = m.expected.dimension
            if m.match_type != "none":
                dim_stats[code].true_positives += 1
            else:
                dim_stats[code].false_negatives += 1
        for fb in r.false_positives:
            code = fb.id[:2]
            if code in dim_stats:
                dim_stats[code].false_positives += 1

    lines.append("## Per-dimension Stats")
    lines.append("")
    lines.append("| Dimension | Precision | Recall | TP | FP | FN |")
    lines.append("|-----------|-----------|--------|----|----|----| ")
    for code in ["QA", "IR", "CP", "LC", "SQ", "PS"]:
        s = dim_stats[code]
        lines.append(
            f"| {code} | {s.precision:.2f} | {s.recall:.2f} "
            f"| {s.true_positives} | {s.false_positives} | {s.false_negatives} |"
        )
    lines.append("")

    # Per-case details
    lines.append("## Per-case Details")
    lines.append("")

    for case, result in zip(cases, results):
        lines.append(f"### {case.name}")
        if case.notes:
            lines.append(f"*{case.notes}*")
        lines.append("")

        lines.append(f"Precision: {result.precision:.2f} | Recall: {result.recall:.2f}")
        lines.append("")

        lines.append("**Expected issues:**")
        for ei in case.expected_issues:
            status = f"MATCH ({ei.match_id})" if ei.matched else "MISSED"
            lines.append(f"- {ei.dimension}.{ei.severity}: {ei.summary} → {status}")
        lines.append("")

        if result.false_positives:
            lines.append("**False positives (reviewer found, not in expected):**")
            for fb in result.false_positives:
                lines.append(f"- {fb.id} ({fb.severity.value}): {fb.one_liner}")
            lines.append("")

        if result.false_negatives:
            lines.append("**False negatives (expected, not found):**")
            for fn in result.false_negatives:
                lines.append(f"- {fn.dimension}.{fn.severity}: {fn.summary}")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run reviewer calibration")
    parser.add_argument(
        "--cases-dir", default="tests/calibration",
        help="Directory with case_*.yaml files",
    )
    parser.add_argument(
        "--output", default="calibration_report.md",
        help="Output report file path",
    )
    args = parser.parse_args()

    cases = load_calibration_cases(args.cases_dir)
    if not cases:
        print(f"No calibration cases found in {args.cases_dir}/")
        print("Please add case_*.yaml files. See tests/calibration/README.md for format.")
        sys.exit(1)

    print(f"Found {len(cases)} calibration cases.")
    results: list[CaseResult] = []

    for i, case in enumerate(cases, 1):
        print(f"\n[{i}/{len(cases)}] Running: {case.name} ...")
        start = time.time()

        output = review(task=case.task, report=case.report)
        elapsed = time.time() - start

        result = compare_with_expected(output, case.expected_issues)
        result.case = case
        results.append(result)

        failed = output.review_metadata.failed_dimensions
        total_fb = sum(len(dr.top_feedback) for dr in output.dimension_reviews.values())
        print(
            f"  Done in {elapsed:.1f}s | "
            f"Feedback: {total_fb} | "
            f"Precision: {result.precision:.2f} | "
            f"Recall: {result.recall:.2f}"
            + (f" | Failed dims: {failed}" if failed else "")
        )

    # Generate report
    report = generate_report(cases, results)

    output_path = Path(args.output)
    output_path.write_text(report, encoding="utf-8")
    print(f"\nReport written to {output_path}")

    # Print summary
    total_tp = sum(sum(1 for m in r.matches if m.match_type != "none") for r in results)
    total_fp = sum(len(r.false_positives) for r in results)
    total_fn = sum(len(r.false_negatives) for r in results)
    p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 1.0
    r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 1.0

    print(f"\n{'='*50}")
    print(f"Overall Precision: {p:.2f} (target ≥ 0.80)")
    print(f"Overall Recall:    {r:.2f} (target ≥ 0.70)")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
