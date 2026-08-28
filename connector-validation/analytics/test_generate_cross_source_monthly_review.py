from __future__ import annotations

import unittest
from datetime import date, timedelta

from generate_cross_source_monthly_review import generate_markdown


def fixtures(days=56):
    start = date(2026, 7, 1)
    sleep=[]; heart=[]
    for i in range(days):
        d=(start+timedelta(days=i)).isoformat()
        sleep.append({"day":d,"total_sleep_minutes":420+i%20,"efficiency_percent":85+i%5,"oura_sleep_score":80+i%10,"data_quality_state":"trusted"})
        heart.append({"day":d,"average_sleeping_heart_rate_bpm":60+i%4,"lowest_sleeping_heart_rate_bpm":54+i%3,"average_hrv_ms":45+i%8,"data_quality_state":"trusted"})
    sm={"metadata":{"imputation_applied":False,"smoothing_applied":False,"ai_interpretation_applied":False,"transformation_version":"oura-core-normalizer-0.1"},"records":sleep}
    hm={"metadata":{"imputation_applied":False,"smoothing_applied":False,"ai_interpretation_applied":False,"transformation_version":"oura-core-normalizer-0.1"},"records":heart}
    hume={"source":{"validation_status":"PASS"},"normalization":{"imputation":False,"smoothing":False,"ai_interpretation":False},"normalizer_version":"hume-body-composition-normalizer-0.1","records":[]}
    for i in range(0,days,2):
        obs=start+timedelta(days=i)
        ts=obs.isoformat()+"T12:00:00Z"
        hume["records"] += [
            {"metric":"weight","data_quality_state":"trusted","observed_at_utc":ts,"zone_offset":"+00:00","value_normalized":210+i*.1},
            {"metric":"body_fat_percentage","data_quality_state":"trusted","observed_at_utc":ts,"zone_offset":"+00:00","value_normalized":30-i*.01},
        ]
    function={"lab_panel":{"verification_state":"verified","collection_date":"2026-08-04"},"controls":{"owner_verified_all_candidate_rows":True,"clinical_interpretation":False},"normalized_biomarker_count":118,"normalizer_version":"function-health-biomarker-normalizer-0.1"}
    regimen="owner_verified: true\nstep7_status: complete-pass\n"
    timeline="step7_status: complete-pass\n| 2026-08-10 | START | Example | test | owner |\n"
    meds={"authority":"owner_confirmed","status":"active","last_confirmed":"2026-08-18"}
    return sm,hm,hume,function,regimen,timeline,meds


class MonthlyReviewTests(unittest.TestCase):
    def test_generates_full_month_comparison(self):
        text=generate_markdown(*fixtures(56))
        self.assertIn("Full prior-window comparison available: **YES**",text)
        self.assertIn("## Sustained Oura Trends",text)

    def test_partial_prior_window_is_explicit_and_deltas_withheld(self):
        text=generate_markdown(*fixtures(33))
        self.assertIn("Full prior-window comparison available: **NO**",text)
        self.assertIn("Full month-over-month claims are withheld",text)

    def test_untrusted_hume_blocks(self):
        x=list(fixtures()); x[2]["source"]["validation_status"]="FAIL"
        with self.assertRaises(ValueError): generate_markdown(*x)

    def test_imputed_oura_blocks(self):
        x=list(fixtures()); x[0]["metadata"]["imputation_applied"]=True
        with self.assertRaises(ValueError): generate_markdown(*x)

    def test_unverified_function_blocks(self):
        x=list(fixtures()); x[3]["lab_panel"]["verification_state"]="candidate"
        with self.assertRaises(ValueError): generate_markdown(*x)

    def test_unverified_supplements_block(self):
        x=list(fixtures()); x[4]="owner_verified: false\nstep7_status: complete-pass\n"
        with self.assertRaises(ValueError): generate_markdown(*x)

    def test_medication_authority_blocks(self):
        x=list(fixtures()); x[6]["authority"]="provider_only"
        with self.assertRaises(ValueError): generate_markdown(*x)

    def test_co_movement_is_noncausal(self):
        text=generate_markdown(*fixtures())
        self.assertIn("descriptive co-movement only and does not establish causation",text)
        self.assertIn("## Questions Worth Investigating",text)


if __name__ == "__main__":
    unittest.main()
