import copy
import unittest

from extract_function_health_data import parse_layout_text


def page(*lines):
    return "\n".join(lines)


class FunctionHealthExtractionTests(unittest.TestCase):
    def test_preserves_range_flag_value_and_unit(self):
        source = page(
            "Autoimmunity",
            "Example Biomarker",
            "Below Range · 12.3 mg/dL",
        ) + "\f"
        result = parse_layout_text(source)
        row = result["candidates"][0]
        self.assertEqual(row["range_flag_original"], "Below Range")
        self.assertEqual(row["value_original"], "12.3")
        self.assertEqual(row["unit_original"], "mg/dL")

    def test_preserves_inequality_without_inventing_unit(self):
        source = page("Autoimmunity", "Example Antibody", "In Range · <2") + "\f"
        row = parse_layout_text(source)["candidates"][0]
        self.assertEqual(row["result_text_original"], "<2")
        self.assertEqual(row["unit_original"], None)

    def test_excludes_daily_metrics_from_lab_candidates(self):
        source = page(
            "Daily Metrics",
            "Example Activity Metric",
            "42 ms",
            "Electrolytes",
            "Example Electrolyte",
            "In Range · 4.2 mmol/L",
        ) + "\f"
        result = parse_layout_text(source)
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["excluded_non_lab_count"], 1)

    def test_duplicate_names_are_preserved_not_deduplicated(self):
        source = page(
            "Electrolytes",
            "Example Mineral",
            "In Range · 9.1 mg/dL",
            "Kidney",
            "Example Mineral",
            "In Range · 9.1 mg/dL",
        ) + "\f"
        result = parse_layout_text(source)
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["duplicate_names"], {"Example Mineral": 2})
        self.assertTrue(all(r["duplicate_name_flag"] for r in result["candidates"]))

    def test_cross_page_result_is_preserved(self):
        source = (
            page("Liver", "Example Protein")
            + "\f"
            + page(
                "In Range · 7.0 g/dL",
                "Male Health",
                "Example Hormone",
                "In Range · 10 ng/mL",
            )
            + "\f"
        )
        result = parse_layout_text(source)
        first = result["candidates"][0]
        self.assertEqual(first["analyte_name_original"], "Example Protein")
        self.assertEqual(first["result_text_original"], "7.0 g/dL")
        self.assertEqual(first["source_page"], 1)
        self.assertEqual(first["source_page_continued"], 2)

    def test_no_clinical_or_reference_range_inference(self):
        source = page("Metabolic", "Example Marker", "Above Range · 100 mg/dL") + "\f"
        result = parse_layout_text(source)
        self.assertFalse(result["extraction_controls"]["clinical_interpretation"])
        self.assertFalse(result["extraction_controls"]["reference_range_inference"])
        self.assertEqual(result["candidates"][0]["verification_state"], "unverified")

    def test_output_is_deterministic(self):
        source = page("Thyroid", "Example Marker", "In Range · 2.3 mIU/L") + "\f"
        a = parse_layout_text(source)
        b = parse_layout_text(copy.deepcopy(source))
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
