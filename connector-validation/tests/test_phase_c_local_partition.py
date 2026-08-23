from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oura_connector.runtime_landing import RuntimeDataset, land_runtime_run, local_operational_day


class PhaseCLocalPartitionTests(unittest.TestCase):
    def test_evening_central_run_stays_on_local_operating_day(self):
        local_evening = datetime(2026, 8, 22, 19, 0, 2, tzinfo=timedelta(hours=-5))
        self.assertEqual(local_operational_day(local_evening), "2026-08-22")

        with tempfile.TemporaryDirectory() as td:
            datasets = {
                "daily_sleep": RuntimeDataset(
                    "daily_sleep",
                    "/usercollection/daily_sleep",
                    [{"id": "record-1"}],
                    1,
                )
            }
            result = land_runtime_run(
                vault_root=td,
                start_date="2026-08-16",
                end_date="2026-08-22",
                scope_granted="extapi:daily",
                datasets=datasets,
                retrieved_at_utc="2026-08-23T00:00:02.624124+00:00",
                run_id="20260823T000002624124Z",
                operational_now=local_evening,
            )
            run_path = Path(result.run_dir)
            self.assertEqual(run_path.parent.name, "2026-08-22")
            self.assertEqual(run_path.name, "20260823T000002624124Z")
            manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(manifest["retrieved_at_utc"], "2026-08-23T00:00:02.624124+00:00")
            self.assertEqual(manifest["operational_day_local"], "2026-08-22")


if __name__ == "__main__":
    unittest.main()
