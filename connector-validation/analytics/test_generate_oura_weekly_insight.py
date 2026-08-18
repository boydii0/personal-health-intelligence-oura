import unittest
from pathlib import Path
import importlib.util

MODULE_PATH = Path(__file__).with_name("generate_oura_weekly_insight.py")
SPEC = importlib.util.spec_from_file_location("weekly", MODULE_PATH)
weekly = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(weekly)


def sample():
    metrics = {}
    for name in weekly.DISPLAY_NAMES:
        metrics[name] = {
            "unit": "unit",
            "current_7_day": {"n": 7, "mean": 110.0, "median": 110, "min": 100, "max": 120, "standard_deviation": 5},
            "trailing_28_day": {"n": 28, "mean": 100.0, "median": 100, "min": 90, "max": 120, "standard_deviation": 8},
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
            "source_files": [],
        },
        "metrics": metrics,
    }


class WeeklyInsightTests(unittest.TestCase):
    def test_generates_traceable_report(self):
        report = weekly.generate_markdown(sample())
        self.assertIn("**PASS — normal weekly insight permitted.**", report)
        self.assertIn("OURA-WK-001", report)
        self.assertIn("calculated trend", report)
        self.assertIn("does **not** imply clinical significance", report)

    def test_stale_data_blocks_report(self):
        doc = sample()
        doc["metadata"]["freshness"]["state"] = "stale"
        with self.assertRaises(ValueError):
            weekly.generate_markdown(doc)

    def test_incomplete_records_block_report(self):
        doc = sample()
        doc["metadata"]["data_quality"]["heart_trusted_records"] = 27
        with self.assertRaises(ValueError):
            weekly.generate_markdown(doc)

    def test_imputation_blocks_report(self):
        doc = sample()
        doc["metadata"]["data_quality"]["imputation_applied"] = True
        with self.assertRaises(ValueError):
            weekly.generate_markdown(doc)


if __name__ == "__main__":
    unittest.main()
