import copy
import json
import tempfile
import unittest
from pathlib import Path

from normalize_hume_body_composition import (
    DEFAULT_HUME_PACKAGE,
    KG_TO_LB,
    NormalizationError,
    normalize_document,
    normalize_file,
)


def source_fixture():
    return {
        "schema_version": "phi.health_connect_validation.v0.1",
        "generated_at_utc": "2026-08-18T12:00:00Z",
        "query_start_utc": "2026-07-19T12:00:00Z",
        "query_end_utc": "2026-08-18T12:00:00Z",
        "query_window_days": 30,
        "read_only": True,
        "network_transmission": False,
        "record_count": 2,
        "records": [
            {
                "record_id": "weight-1",
                "data_origin_package": DEFAULT_HUME_PACKAGE,
                "last_modified_at_utc": "2026-08-18T10:00:01Z",
                "recording_method": 2,
                "record_type": "weight",
                "observed_at_utc": "2026-08-18T10:00:00Z",
                "zone_offset": "-05:00",
                "value": 100.0,
                "unit": "kg",
            },
            {
                "record_id": "fat-1",
                "data_origin_package": DEFAULT_HUME_PACKAGE,
                "last_modified_at_utc": "2026-08-18T10:00:01Z",
                "recording_method": 2,
                "record_type": "body_fat",
                "observed_at_utc": "2026-08-18T10:00:00Z",
                "zone_offset": "-05:00",
                "value": 25.5,
                "unit": "percent",
            },
        ],
    }


class HumeNormalizationTests(unittest.TestCase):
    def test_weight_converts_to_pounds_and_preserves_original(self):
        result = normalize_document(
            source_fixture(), source_file_name="source.json", source_sha256="abc"
        )
        weight = next(r for r in result["records"] if r["metric"] == "weight")
        self.assertEqual(weight["value_original"], 100.0)
        self.assertEqual(weight["unit_original"], "kg")
        self.assertEqual(weight["value_normalized"], round(100.0 * KG_TO_LB, 1))
        self.assertEqual(weight["unit_normalized"], "lb")

    def test_body_fat_stays_percent(self):
        result = normalize_document(
            source_fixture(), source_file_name="source.json", source_sha256="abc"
        )
        fat = next(r for r in result["records"] if r["metric"] == "body_fat_percentage")
        self.assertEqual(fat["value_original"], 25.5)
        self.assertEqual(fat["value_normalized"], 25.5)
        self.assertEqual(fat["unit_normalized"], "percent")

    def test_rejects_unapproved_source_package(self):
        source = source_fixture()
        source["records"][0]["data_origin_package"] = "com.other.scale"
        with self.assertRaises(NormalizationError):
            normalize_document(source, source_file_name="source.json", source_sha256="abc")

    def test_rejects_duplicate_record_id(self):
        source = source_fixture()
        source["records"][1]["record_id"] = source["records"][0]["record_id"]
        with self.assertRaises(NormalizationError):
            normalize_document(source, source_file_name="source.json", source_sha256="abc")

    def test_rejects_record_count_mismatch(self):
        source = source_fixture()
        source["record_count"] = 3
        with self.assertRaises(NormalizationError):
            normalize_document(source, source_file_name="source.json", source_sha256="abc")

    def test_output_is_deterministic(self):
        source = source_fixture()
        a = normalize_document(copy.deepcopy(source), source_file_name="source.json", source_sha256="abc")
        b = normalize_document(copy.deepcopy(source), source_file_name="source.json", source_sha256="abc")
        self.assertEqual(a, b)

    def test_file_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "source.json"
            output_path = Path(tmp) / "out.json"
            source_path.write_text(json.dumps(source_fixture()), encoding="utf-8")
            result = normalize_file(source_path, output_path)
            disk = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result, disk)
            self.assertEqual(disk["record_count"], 2)


if __name__ == "__main__":
    unittest.main()
