import unittest
from normalize_oura_core import normalize

class NormalizeOuraCoreTests(unittest.TestCase):
    def test_selects_only_long_sleep_and_preserves_missing_day(self):
        sleep_doc = {"data": [
            {"id":"a","day":"2026-01-01","type":"long_sleep","bedtime_start":"x","bedtime_end":"y",
             "total_sleep_duration":3600,"time_in_bed":4200,"awake_time":600,"deep_sleep_duration":900,
             "light_sleep_duration":1800,"rem_sleep_duration":900,"latency":300,"efficiency":86,
             "average_breath":14.5,"average_heart_rate":60,"lowest_heart_rate":52,"average_hrv":45,
             "sleep_algorithm_version":"v2"},
            {"id":"b","day":"2026-01-01","type":"late_nap","bedtime_start":"x","bedtime_end":"y"}
        ]}
        daily_doc = {"data":[
            {"id":"d1","day":"2026-01-01","score":80,"contributors":{}},
            {"id":"d2","day":"2026-01-02","score":75,"contributors":{}}
        ]}
        sleep_core, heart_core = normalize(sleep_doc, daily_doc, "s", "d")
        self.assertEqual(len(sleep_core["records"]), 1)
        self.assertEqual(len(heart_core["records"]), 1)
        self.assertEqual(sleep_core["records"][0]["total_sleep_minutes"], 60.0)
        self.assertEqual(sleep_core["metadata"]["missing_primary_sleep_days"], ["2026-01-02"])

if __name__ == "__main__":
    unittest.main()
