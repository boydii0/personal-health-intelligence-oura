import unittest

from normalize_function_health_biomarkers import NormalizationError, normalize, parse_result

BASE = {
    "candidates": [
        {
            "candidate_row_id": "FH-001",
            "analyte_name_original": "Glucose",
            "category_original": "Metabolic",
            "result_text_original": "100 mg/dL",
            "value_original": "100",
            "unit_original": "mg/dL",
            "range_flag_original": "Above Range",
            "reference_low_original": None,
            "reference_high_original": None,
            "reference_text_original": None,
            "source_document_ref": "doc",
            "source_document_sha256": "abc",
            "source_page": 1,
        }
    ]
}


class NormalizerTests(unittest.TestCase):
    def test_numeric(self):
        self.assertEqual(parse_result("100")["numeric_value"], 100.0)

    def test_censored_numeric(self):
        self.assertEqual(parse_result("<10")["comparator"], "<")

    def test_categorical(self):
        self.assertEqual(parse_result("Negative")["result_kind"], "categorical")

    def test_single_record(self):
        output = normalize(BASE, "2026-08-04", "2026-08-18T23:20:00Z")
        self.assertEqual(output["normalized_biomarker_count"], 1)

    def test_duplicate_same_reconciles(self):
        duplicate = {
            "candidates": [
                BASE["candidates"][0],
                {
                    **BASE["candidates"][0],
                    "candidate_row_id": "FH-002",
                    "source_page": 2,
                    "category_original": "Other",
                },
            ]
        }
        output = normalize(duplicate, "2026-08-04", "2026-08-18T23:20:00Z")
        self.assertEqual(output["normalized_biomarker_count"], 1)
        self.assertEqual(output["biomarkers"][0]["source_occurrence_count"], 2)

    def test_duplicate_conflict_fails(self):
        conflict = {
            "candidates": [
                BASE["candidates"][0],
                {
                    **BASE["candidates"][0],
                    "candidate_row_id": "FH-002",
                    "value_original": "101",
                    "result_text_original": "101 mg/dL",
                },
            ]
        }
        with self.assertRaises(NormalizationError):
            normalize(conflict, "2026-08-04", "2026-08-18T23:20:00Z")

    def test_bad_date_fails(self):
        with self.assertRaises(NormalizationError):
            normalize(BASE, "08/04/2026", "2026-08-18T23:20:00Z")


if __name__ == "__main__":
    unittest.main()
