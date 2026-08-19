import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_cross_source_weekly_insight.py")
SPEC = importlib.util.spec_from_file_location("cross_weekly", MODULE_PATH)
weekly = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(weekly)


def sample_oura():
    metrics = {}
    for name in weekly.DISPLAY:
        metrics[name] = {
            "unit": "unit",
            "current_7_day": {"n": 7, "mean": 110.0},
            "trailing_28_day": {"n": 28, "mean": 100.0},
            "absolute_delta_current_mean_minus_baseline_mean": 10.0,
            "percent_delta_current_mean_vs_baseline_mean": 10.0,
        }
    return {
        "metadata": {
            "schema_version": "0.1",
            "calculation_version": "oura-baseline-calculator-0.1",
            "dataset": "oura_baseline_core",
            "generated_for_date": "2026-08-17",
            "latest_observation_day": "2026-08-16",
            "current_window": {"start": "2026-08-10", "end": "2026-08-16", "expected_days": 7, "present_days": 7},
            "baseline_window": {"start": "2026-07-20", "end": "2026-08-16", "expected_days": 28, "present_days": 28},
            "baseline_overlap_days": 7,
            "freshness": {"age_days": 1, "state": "fresh"},
            "data_quality": {
                "sleep_trusted_records": 28,
                "sleep_expected_records": 28,
                "heart_trusted_records": 28,
                "heart_expected_records": 28,
                "coverage_percent": 100.0,
                "imputation_applied": False,
                "smoothing_applied": False,
            },
        },
        "metrics": metrics,
    }


def hume_record(metric, day, value, offset="-05:00"):
    return {
        "metric": metric,
        "observed_at_utc": f"{day}T12:00:00Z",
        "zone_offset": offset,
        "value_normalized": value,
        "unit_normalized": "lb" if metric == "weight" else "percent",
        "data_quality_state": "trusted",
    }


def sample_hume():
    records = []
    for day, weight, bodyfat in [
        ("2026-07-28", 216.0, 31.0),
        ("2026-08-01", 215.0, 30.8),
        ("2026-08-05", 214.0, 30.7),
        ("2026-08-11", 215.0, 30.6),
        ("2026-08-12", 214.0, 30.5),
        ("2026-08-14", 213.0, 30.4),
    ]:
        records.append(hume_record("weight", day, weight))
        records.append(hume_record("body_fat_percentage", day, bodyfat))
    return {
        "normalizer_version": "hume-body-composition-v0.1",
        "source": {"validation_status": "PASS", "sha256": "abc123"},
        "normalization": {"imputation": False, "smoothing": False, "ai_interpretation": False},
        "records": records,
    }


def sample_function():
    return {
        "normalizer_version": "function-health-biomarker-normalizer-0.1",
        "lab_panel": {
            "collection_date": "2026-08-04",
            "verification_state": "verified",
        },
        "controls": {
            "owner_verified_all_candidate_rows": True,
            "clinical_interpretation": False,
        },
        "normalized_biomarker_count": 118,
    }


REGIMEN = """---
owner_verified: true
step7_status: complete-pass
---
# Regimen
"""

TIMELINE = """---
step7_status: complete-pass
---
| Date | Event | Product / Ingredient | Detail | Evidence State |
|---|---|---|---|---|
| 2026-08-10 | Started | Product A | 1 capsule daily | Owner-confirmed |
| 2026-08-17 | Started | Product B | dose unspecified | Owner-confirmed |
"""

MEDS = {
    "authority": "owner_confirmed",
    "status": "active",
    "last_confirmed": "2026-08-18",
}


class CrossSourceWeeklyTests(unittest.TestCase):
    def test_generates_cross_source_candidate(self):
        report = weekly.generate_markdown(
            sample_oura(), sample_hume(), sample_function(), REGIMEN, TIMELINE, MEDS
        )
        self.assertIn("Cross-Source Weekly Insight", report)
        self.assertIn("candidate-owner-validation", report)
        self.assertIn("Hume — aligned body composition", report)
        self.assertIn("Function Health anchor", report)
        self.assertIn("association-only", report.lower())

    def test_stale_oura_blocks(self):
        doc = sample_oura()
        doc["metadata"]["freshness"]["state"] = "stale"
        with self.assertRaises(ValueError):
            weekly.generate_markdown(doc, sample_hume(), sample_function(), REGIMEN, TIMELINE, MEDS)

    def test_incomplete_oura_blocks(self):
        doc = sample_oura()
        doc["metadata"]["current_window"]["present_days"] = 6
        with self.assertRaises(ValueError):
            weekly.generate_markdown(doc, sample_hume(), sample_function(), REGIMEN, TIMELINE, MEDS)

    def test_unvalidated_hume_blocks(self):
        doc = sample_hume()
        doc["source"]["validation_status"] = "PARTIAL"
        with self.assertRaises(ValueError):
            weekly.generate_markdown(sample_oura(), doc, sample_function(), REGIMEN, TIMELINE, MEDS)

    def test_unverified_function_blocks(self):
        doc = sample_function()
        doc["lab_panel"]["verification_state"] = "unverified"
        with self.assertRaises(ValueError):
            weekly.generate_markdown(sample_oura(), sample_hume(), doc, REGIMEN, TIMELINE, MEDS)

    def test_unverified_supplement_regimen_blocks(self):
        with self.assertRaises(ValueError):
            weekly.generate_markdown(
                sample_oura(), sample_hume(), sample_function(),
                REGIMEN.replace("owner_verified: true", "owner_verified: false"),
                TIMELINE, MEDS,
            )

    def test_local_date_alignment_uses_zone_offset(self):
        h = sample_hume()
        h["records"].append({
            "metric": "weight",
            "observed_at_utc": "2026-08-17T03:00:00Z",
            "zone_offset": "-05:00",
            "value_normalized": 212.0,
            "unit_normalized": "lb",
            "data_quality_state": "trusted",
        })
        stats = weekly.hume_stats(
            h,
            weekly.date.fromisoformat("2026-08-10"),
            weekly.date.fromisoformat("2026-08-16"),
            weekly.date.fromisoformat("2026-07-20"),
            weekly.date.fromisoformat("2026-08-16"),
        )
        self.assertIn("2026-08-16", stats["weight"]["current"]["days"])

    def test_post_window_supplement_event_is_excluded_from_association_window(self):
        report = weekly.generate_markdown(
            sample_oura(), sample_hume(), sample_function(), REGIMEN, TIMELINE, MEDS
        )
        self.assertIn("Post-window events", report)
        self.assertIn("excluded from current-window association logic", report)
        self.assertIn("Product B", report)

    def test_post_window_medication_confirmation_is_not_used_for_week(self):
        report = weekly.generate_markdown(
            sample_oura(), sample_hume(), sample_function(), REGIMEN, TIMELINE, MEDS
        )
        self.assertIn("post-window confirmation; excluded from week-window interpretation", report)


if __name__ == "__main__":
    unittest.main()
