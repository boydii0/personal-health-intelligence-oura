import unittest
from datetime import date

from calculate_oura_baselines import calculate


class BaselineTests(unittest.TestCase):
    def _documents(self, days=28):
        sleep = {"metadata": {"missing_primary_sleep_days": []}, "records": []}
        heart = {"metadata": {}, "records": []}

        for i in range(1, days + 1):
            day = f"2026-01-{i:02d}"
            sleep["records"].append(
                {
                    "day": day,
                    "data_quality_state": "trusted",
                    "total_sleep_minutes": 300 + i,
                    "time_in_bed_minutes": 330 + i,
                    "deep_sleep_minutes": 60,
                    "light_sleep_minutes": 180,
                    "rem_sleep_minutes": 60,
                    "awake_minutes": 30,
                    "efficiency_percent": 90,
                    "latency_minutes": 10,
                    "average_breaths_per_minute": 14.5,
                    "oura_sleep_score": 80,
                }
            )
            heart["records"].append(
                {
                    "day": day,
                    "data_quality_state": "trusted",
                    "average_sleeping_heart_rate_bpm": 60,
                    "lowest_sleeping_heart_rate_bpm": 52,
                    "average_hrv_ms": 45,
                }
            )

        return sleep, heart

    def test_28_day_baseline_and_7_day_overlap(self):
        sleep, heart = self._documents()
        output = calculate(sleep, heart, date(2026, 1, 29))

        self.assertEqual(output["metadata"]["baseline_overlap_days"], 7)
        self.assertFalse(output["metadata"]["comparison_independent"])
        self.assertEqual(output["metadata"]["baseline_window"]["present_days"], 28)
        self.assertEqual(output["metadata"]["current_window"]["present_days"], 7)
        self.assertEqual(output["metadata"]["freshness"]["state"], "fresh")
        self.assertEqual(output["metadata"]["data_quality"]["coverage_percent"], 100.0)

    def test_requires_28_aligned_days(self):
        sleep, heart = self._documents(days=27)
        with self.assertRaisesRegex(ValueError, "At least 28 aligned complete days"):
            calculate(sleep, heart, date(2026, 1, 28))

    def test_fails_closed_when_metric_has_no_values(self):
        sleep, heart = self._documents()
        for record in sleep["records"]:
            record["rem_sleep_minutes"] = None

        with self.assertRaisesRegex(ValueError, "rem_sleep_minutes"):
            calculate(sleep, heart, date(2026, 1, 29))


if __name__ == "__main__":
    unittest.main()
