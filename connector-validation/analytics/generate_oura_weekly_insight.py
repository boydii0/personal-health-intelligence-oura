"""Deterministic Step 4 Weekly Insight generator for the Oura baseline core."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

VERSION = "oura-weekly-insight-generator-0.1"

DISPLAY_NAMES = {
    "total_sleep_minutes": "Total sleep",
    "time_in_bed_minutes": "Time in bed",
    "deep_sleep_minutes": "Deep sleep",
    "light_sleep_minutes": "Light sleep",
    "rem_sleep_minutes": "REM sleep",
    "awake_minutes": "Awake time",
    "efficiency_percent": "Sleep efficiency",
    "latency_minutes": "Sleep latency",
    "average_breaths_per_minute": "Average breathing rate",
    "oura_sleep_score": "Oura sleep score",
    "average_sleeping_heart_rate_bpm": "Average sleeping heart rate",
    "lowest_sleeping_heart_rate_bpm": "Lowest sleeping heart rate",
    "average_hrv_ms": "Average HRV",
}


def _fmt(value):
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def _validate(baseline):
    metadata = baseline.get("metadata", {})
    quality = metadata.get("data_quality", {})
    current = metadata.get("current_window", {})
    trailing = metadata.get("baseline_window", {})
    freshness = metadata.get("freshness", {})

    required = [
        ("current window", current.get("present_days"), current.get("expected_days")),
        ("baseline window", trailing.get("present_days"), trailing.get("expected_days")),
        ("sleep trusted records", quality.get("sleep_trusted_records"), quality.get("sleep_expected_records")),
        ("heart trusted records", quality.get("heart_trusted_records"), quality.get("heart_expected_records")),
    ]
    for label, present, expected in required:
        if present is None or expected is None or present != expected:
            raise ValueError(f"Weekly Insight blocked: incomplete {label}")

    if quality.get("coverage_percent") != 100.0:
        raise ValueError("Weekly Insight blocked: baseline coverage is not 100%")
    if quality.get("imputation_applied"):
        raise ValueError("Weekly Insight blocked: imputed data present")
    if quality.get("smoothing_applied"):
        raise ValueError("Weekly Insight blocked: smoothed data present")
    if freshness.get("state") == "stale":
        raise ValueError("Weekly Insight blocked: source data is stale")
    if not baseline.get("metrics"):
        raise ValueError("Weekly Insight blocked: no metrics available")


def _claim_rows(baseline):
    rows = []
    for metric_name, metric in baseline["metrics"].items():
        pct = metric.get("percent_delta_current_mean_vs_baseline_mean")
        abs_delta = metric.get("absolute_delta_current_mean_minus_baseline_mean")
        current_mean = metric["current_7_day"]["mean"]
        baseline_mean = metric["trailing_28_day"]["mean"]
        direction = "higher" if (abs_delta or 0) > 0 else "lower" if (abs_delta or 0) < 0 else "unchanged"
        rows.append({
            "metric_name": metric_name,
            "display_name": DISPLAY_NAMES.get(metric_name, metric_name),
            "unit": metric["unit"],
            "current_mean": current_mean,
            "baseline_mean": baseline_mean,
            "abs_delta": abs_delta,
            "pct_delta": pct,
            "direction": direction,
            "magnitude": abs(pct) if pct is not None else -1,
        })
    return rows


def generate_markdown(baseline):
    _validate(baseline)
    metadata = baseline["metadata"]
    quality = metadata["data_quality"]
    current = metadata["current_window"]
    trailing = metadata["baseline_window"]
    freshness = metadata["freshness"]

    rows = _claim_rows(baseline)
    ranked = sorted(rows, key=lambda r: r["magnitude"], reverse=True)
    top = ranked[:5]

    lines = [
        "---",
        "type: weekly-insight",
        "status: complete",
        "version: 0.1",
        f"generated_for_date: {metadata['generated_for_date']}",
        "project: Personal Health Intelligence",
        "source: oura",
        f"generator_version: {VERSION}",
        f"baseline_calculation_version: {metadata['calculation_version']}",
        f"baseline_schema_version: {metadata['schema_version']}",
        "clinical_use: false",
        "---",
        "",
        f"# Oura Weekly Insight — {metadata['generated_for_date']}",
        "",
        "## Analysis Gate",
        "",
        "**PASS — normal weekly insight permitted.**",
        "",
        f"- Current window: `{current['start']}` through `{current['end']}` ({current['present_days']}/{current['expected_days']} days).",
        f"- Trailing baseline: `{trailing['start']}` through `{trailing['end']}` ({trailing['present_days']}/{trailing['expected_days']} days).",
        f"- Freshness: **{freshness['state']}** ({freshness['age_days']} day(s) since latest observation).",
        f"- Trusted sleep records: {quality['sleep_trusted_records']}/{quality['sleep_expected_records']}.",
        f"- Trusted heart records: {quality['heart_trusted_records']}/{quality['heart_expected_records']}.",
        f"- Coverage: {quality['coverage_percent']}%.",
        "- Imputation: none.",
        "- Smoothing: none.",
        "- AI interpretation in source baseline: none.",
        "",
        "## Executive Summary",
        "",
        "The largest relative differences between the current 7-day mean and the trailing 28-day mean are listed below. These are descriptive changes only; ranking by percentage difference does **not** imply clinical significance or causation.",
        "",
    ]

    for i, row in enumerate(top, 1):
        sign = "+" if row["pct_delta"] is not None and row["pct_delta"] > 0 else ""
        lines.append(
            f"{i}. **{row['display_name']}** was {row['direction']} in the current 7-day mean: "
            f"{_fmt(row['current_mean'])} {row['unit']} vs {_fmt(row['baseline_mean'])} {row['unit']} "
            f"({sign}{_fmt(row['pct_delta'])}%)."
        )

    lines += [
        "",
        "## Metric Comparison",
        "",
        "| Metric | Current 7-day mean | Trailing 28-day mean | Absolute delta | Relative delta |",
        "|---|---:|---:|---:|---:|",
    ]

    for row in rows:
        pct = "n/a" if row["pct_delta"] is None else f"{row['pct_delta']:+.3f}%"
        abs_delta = "n/a" if row["abs_delta"] is None else f"{row['abs_delta']:+.3f} {row['unit']}"
        lines.append(
            f"| {row['display_name']} | {_fmt(row['current_mean'])} {row['unit']} | "
            f"{_fmt(row['baseline_mean'])} {row['unit']} | {abs_delta} | {pct} |"
        )

    lines += [
        "",
        "## Traceable Claims",
        "",
        "| Claim ID | Claim | Classification | Evidence |",
        "|---|---|---|---|",
        "| OURA-WK-001 | The report passed freshness, completeness, trusted-record, and no-imputation/no-smoothing gates. | observed fact | `metadata.current_window`, `metadata.baseline_window`, `metadata.freshness`, `metadata.data_quality` |",
    ]

    claim_num = 2
    for row in top:
        sign = "+" if row["pct_delta"] is not None and row["pct_delta"] > 0 else ""
        claim = (
            f"{row['display_name']}: current 7-day mean {_fmt(row['current_mean'])} {row['unit']} "
            f"vs trailing 28-day mean {_fmt(row['baseline_mean'])} {row['unit']} "
            f"({sign}{_fmt(row['pct_delta'])}%)."
        )
        evidence = f"`metrics.{row['metric_name']}`"
        lines.append(f"| OURA-WK-{claim_num:03d} | {claim} | calculated trend | {evidence} |")
        claim_num += 1

    lines += [
        "",
        "## Associations / Hypotheses",
        "",
        "None asserted in this first Oura-only Weekly Insight. No intervention, Hume, laboratory, or contextual-event data was used.",
        "",
        "## Professional-Review Items",
        "",
        "None generated by this deterministic reporting layer. This report does not diagnose conditions, apply clinical thresholds, or recommend treatment or medication/supplement changes.",
        "",
        "## Limitations",
        "",
        f"- The current 7-day window is included inside the trailing 28-day baseline (`baseline_overlap_days = {metadata.get('baseline_overlap_days')}`), so the comparison is descriptive and not statistically independent.",
        "- This report is based on Oura-derived sleep/heart metrics only.",
        "- Relative percentage differences are not clinical thresholds.",
        "- Temporal or directional changes do not establish causation.",
        "- No external medical evidence was required because no clinical interpretation or treatment recommendation is made.",
        "",
        "## Provenance",
        "",
        f"- Baseline dataset: `{metadata['dataset']}`.",
        f"- Baseline calculation version: `{metadata['calculation_version']}`.",
        f"- Weekly Insight generator version: `{VERSION}`.",
        "- Source normalized files:",
    ]
    for src in metadata.get("source_files", []):
        lines.append(f"  - `{src['file']}` — schema `{src.get('schema_version')}`, transformation `{src.get('transformation_version')}`.")
    lines += [
        "",
        "## Next Action",
        "",
        "Step 4 is complete when this artifact is stored in the canonical Weekly Insights folder and its implementation/provenance is recorded in project governance.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    baseline = json.loads(args.baseline.read_text())
    report = generate_markdown(baseline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report + "\n")


if __name__ == "__main__":
    main()
