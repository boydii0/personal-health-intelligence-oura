import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from refresh_oura_from_phase_c import discover_pass_runs, refresh


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_run(root, day_folder, run_id, retrieved, sleep_data, daily_data, status="PASS", corrupt=False):
    run_dir = root / day_folder / run_id
    run_dir.mkdir(parents=True)
    sleep_sha = write_json(run_dir / "sleep.json", {"data": sleep_data})
    daily_sha = write_json(run_dir / "daily_sleep.json", {"data": daily_data})
    manifest = {
        "status": status,
        "run_id": run_id,
        "retrieved_at_utc": retrieved,
        "datasets": {
            "sleep": {"raw_file": "sleep.json", "checksum_sha256": sleep_sha},
            "daily_sleep": {"raw_file": "daily_sleep.json", "checksum_sha256": daily_sha},
        },
    }
    write_json(run_dir / "run_manifest.json", manifest)
    if corrupt:
        (run_dir / "sleep.json").write_text('{"data":[]}', encoding="utf-8")
    return run_dir


def raw(day, record_id, hr=60, hrv=40):
    return {
        "id": record_id,
        "day": day,
        "type": "long_sleep",
        "bedtime_start": day + "T00:00:00-05:00",
        "bedtime_end": day + "T08:00:00-05:00",
        "sleep_algorithm_version": "v2",
        "total_sleep_duration": 25200,
        "time_in_bed": 28800,
        "awake_time": 3600,
        "deep_sleep_duration": 5400,
        "light_sleep_duration": 14400,
        "rem_sleep_duration": 5400,
        "latency": 600,
        "efficiency": 88,
        "average_breath": 15.0,
        "average_heart_rate": hr,
        "lowest_heart_rate": 55,
        "average_hrv": hrv,
    }


def daily(day, record_id, score=80):
    return {
        "id": record_id,
        "day": day,
        "score": score,
        "contributors": {"deep_sleep": 90},
    }


class PhaseCNormalizationBridgeTests(unittest.TestCase):
    def test_pass_only_and_latest_snapshot_wins(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_run(root, "2026-08-21", "a", "2026-08-21T09:00:00Z", [raw("2026-08-21", "s1", 60)], [daily("2026-08-21", "d1", 80)])
            make_run(root, "2026-08-21", "b", "2026-08-21T19:00:00Z", [raw("2026-08-21", "s1", 62)], [daily("2026-08-21", "d1", 82)])
            make_run(root, "2026-08-21", "c", "2026-08-21T20:00:00Z", [raw("2026-08-21", "s2", 99)], [daily("2026-08-21", "d2", 99)], status="FAIL")
            runs = discover_pass_runs(root)
            sleep_doc, heart_doc = refresh({"records": []}, {"records": []}, runs)
            self.assertEqual(len(runs), 2)
            self.assertEqual(sleep_doc["records"][0]["oura_sleep_score"], 82)
            self.assertEqual(heart_doc["records"][0]["average_sleeping_heart_rate_bpm"], 62)

    def test_seed_history_is_preserved_and_recent_day_is_replaced(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_run(root, "2026-08-21", "a", "2026-08-21T19:00:00Z", [raw("2026-08-21", "new")], [daily("2026-08-21", "dn")])
            seed_sleep = {"records": [{"day": "2026-07-01", "x": 1}, {"day": "2026-08-21", "x": "old"}]}
            seed_heart = {"records": [{"day": "2026-07-01", "x": 1}, {"day": "2026-08-21", "x": "old"}]}
            sleep_doc, heart_doc = refresh(seed_sleep, seed_heart, discover_pass_runs(root))
            self.assertEqual([r["day"] for r in sleep_doc["records"]], ["2026-07-01", "2026-08-21"])
            self.assertEqual(sleep_doc["records"][0]["x"], 1)
            self.assertEqual(sleep_doc["records"][1]["source_sleep_record_id"], "new")
            self.assertEqual(heart_doc["records"][1]["source_sleep_record_id"], "new")

    def test_checksum_failure_blocks_normalization(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_run(root, "2026-08-21", "a", "2026-08-21T19:00:00Z", [raw("2026-08-21", "s")], [daily("2026-08-21", "d")], corrupt=True)
            with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
                discover_pass_runs(root)

    def test_no_pass_runs_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "No PASS"):
                refresh({"records": []}, {"records": []}, discover_pass_runs(Path(td)))

    def test_duration_rounding_matches_v01_normalizer(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            record = raw("2026-08-21", "s")
            record["time_in_bed"] = 28327
            record["awake_time"] = 3787
            make_run(root, "2026-08-21", "a", "2026-08-21T19:00:00Z", [record], [daily("2026-08-21", "d", 91)])
            sleep_doc, heart_doc = refresh({"records": []}, {"records": []}, discover_pass_runs(root))
            self.assertEqual(sleep_doc["records"][0]["time_in_bed_minutes"], 472.117)
            self.assertEqual(sleep_doc["records"][0]["awake_minutes"], 63.117)
            self.assertEqual(heart_doc["records"][0]["source_sleep_record_id"], "s")


if __name__ == "__main__":
    unittest.main()
