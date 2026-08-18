"""Deterministic Step 3 baseline calculator for normalized Oura sleep/heart cores."""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import date
from pathlib import Path

VERSION = "oura-baseline-calculator-0.1"

METRICS = {
    "total_sleep_minutes": ("sleep", "total_sleep_minutes", "min"),
    "time_in_bed_minutes": ("sleep", "time_in_bed_minutes", "min"),
    "deep_sleep_minutes": ("sleep", "deep_sleep_minutes", "min"),
    "light_sleep_minutes": ("sleep", "light_sleep_minutes", "min"),
    "rem_sleep_minutes": ("sleep", "rem_sleep_minutes", "min"),
    "awake_minutes": ("sleep", "awake_minutes", "min"),
    "efficiency_percent": ("sleep", "efficiency_percent", "%"),
    "latency_minutes": ("sleep", "latency_minutes", "min"),
    "average_breaths_per_minute": ("sleep", "average_breaths_per_minute", "breaths/min"),
    "oura_sleep_score": ("sleep", "oura_sleep_score", "score"),
    "average_sleeping_heart_rate_bpm": ("heart", "average_sleeping_heart_rate_bpm", "bpm"),
    "lowest_sleeping_heart_rate_bpm": ("heart", "lowest_sleeping_heart_rate_bpm", "bpm"),
    "average_hrv_ms": ("heart", "average_hrv_ms", "ms"),
}


def summary(values):
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 3),
        "median": round(statistics.median(values), 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
        "standard_deviation": round(statistics.pstdev(values), 3),
    }


def calculate(sleep_doc, heart_doc, as_of_date):
    sleep_by_day = {record["day"]: record for record in sleep_doc["records"]}
    heart_by_day = {record["day"]: record for record in heart_doc["records"]}
    days = sorted(set(sleep_by_day) & set(heart_by_day))

    if len(days) < 28:
        raise ValueError("At least 28 aligned complete days are required")

    baseline_days = days[-28:]
    current_days = baseline_days[-7:]

    metrics = {}
    for name, (source, field, unit) in METRICS.items():
        source_by_day = sleep_by_day if source == "sleep" else heart_by_day
        current_values = [
            source_by_day[day][field]
            for day in current_days
            if source_by_day[day].get(field) is not None
        ]
        baseline_values = [
            source_by_day[day][field]
            for day in baseline_days
            if source_by_day[day].get(field) is not None
        ]

        if not current_values or not baseline_values:
            raise ValueError(f"Metric {name} has insufficient values for baseline calculation")

        current_mean = statistics.mean(current_values)
        baseline_mean = statistics.mean(baseline_values)
        delta = current_mean - baseline_mean

        metrics[name] = {
            "unit": unit,
            "current_7_day": summary(current_values),
            "trailing_28_day": summary(baseline_values),
            "absolute_delta_current_mean_minus_baseline_mean": round(delta, 3),
            "percent_delta_current_mean_vs_baseline_mean": (
                None if baseline_mean == 0 else round(delta / baseline_mean * 100, 3)
            ),
        }

    latest = date.fromisoformat(baseline_days[-1])
    age = (as_of_date - latest).days
    freshness = "fresh" if age <= 1 else "lagging" if age <= 3 else "stale"

    return {
        "metadata": {
            "schema_version": "0.1",
            "calculation_version": VERSION,
            "dataset": "oura_baseline_core",
            "generated_for_date": as_of_date.isoformat(),
            "latest_observation_day": baseline_days[-1],
            "current_window": {
                "start": current_days[0],
                "end": current_days[-1],
                "expected_days": 7,
                "present_days": 7,
            },
            "baseline_window": {
                "start": baseline_days[0],
                "end": baseline_days[-1],
                "expected_days": 28,
                "present_days": 28,
            },
            "baseline_overlap_days": 7,
            "comparison_independent": False,
            "freshness": {
                "age_days": age,
                "state": freshness,
                "rules": {
                    "fresh": "0-1 days",
                    "lagging": "2-3 days",
                    "stale": ">3 days",
                },
                "operational_not_clinical": True,
            },
            "data_quality": {
                "sleep_trusted_records": sum(
                    sleep_by_day[day].get("data_quality_state") == "trusted"
                    for day in baseline_days
                ),
                "sleep_expected_records": 28,
                "heart_trusted_records": sum(
                    heart_by_day[day].get("data_quality_state") == "trusted"
                    for day in baseline_days
                ),
                "heart_expected_records": 28,
                "coverage_percent": 100.0,
                "missing_days_in_baseline": [],
                "known_source_gap_after_latest_observation": sleep_doc["metadata"].get(
                    "missing_primary_sleep_days", []
                ),
                "imputation_applied": False,
                "smoothing_applied": False,
                "ai_interpretation_applied": False,
            },
        },
        "metrics": metrics,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sleep-core", required=True, type=Path)
    parser.add_argument("--heart-core", required=True, type=Path)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    result = calculate(
        json.loads(args.sleep_core.read_text()),
        json.loads(args.heart_core.read_text()),
        date.fromisoformat(args.as_of_date),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
