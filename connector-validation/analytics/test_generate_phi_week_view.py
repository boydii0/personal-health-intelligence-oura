import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_phi_week_view.py")
SPEC = importlib.util.spec_from_file_location("phi_week_view", MODULE_PATH)
week_view = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(week_view)


WEEKLY = """---
type: weekly-insight
status: candidate-owner-validation
version: 0.2
generated_for_date: 2026-08-23
project: Personal Health Intelligence
clinical_use: false
causality: association-only
---

# Cross-Source Weekly Insight — 2026-08-23

## Analysis Gate

**PASS — deterministic candidate generated.**

- Current window: `2026-08-15` through `2026-08-21`; Oura 7/7 days.
- Trailing baseline: `2026-07-25` through `2026-08-21`; Oura 28/28 days.
- Hume coverage: 3/7 current-window observation days; 15/28 trailing-window observation days.
- Function Health: verified single panel `2026-08-04`; static anchor only.
- Supplements: 2 event(s) inside current window.
- Medications: owner-confirmed context available within window.

## Executive Summary

### Oura — largest descriptive differences

1. **Sleep latency** was lower: 8 min vs 16 min (-50%).
2. **Average HRV** was higher: 40 ms vs 35 ms (+14.3%).
3. **Time in bed** was unchanged: 400 min vs 400 min (0%).

### Hume — aligned body composition

| Metric | Current mean | Trailing mean | Current n | Trailing n | Delta | Relative delta |
|---|---:|---:|---:|---:|---:|---:|
| Weight | 214.5 lb | 214.4 lb | 3 | 15 | +0.1 lb | +0.05% |
| Body fat | 30.5 % | 30.7 % | 3 | 15 | -0.2 pp | -0.65% |

## Limitations

- Hume coverage is partial.
- Function Health contributes one verified panel only.
- Temporal alignment does not establish causation.
"""


class PhiWeekViewTests(unittest.TestCase):
    def test_renders_derivative_and_preserves_source_status(self):
        rendered = week_view.render_week_view(WEEKLY)
        self.assertIn("type: phi-week-view", rendered)
        self.assertIn("source_status: candidate-owner-validation", rendered)
        self.assertIn("authority: derivative-zone-3", rendered)
        self.assertIn("clinical_use: false", rendered)
        self.assertIn("Cross-Source Weekly Insight - 2026-08-23", rendered)

    def test_direction_arrows_are_descriptive(self):
        rendered = week_view.render_week_view(WEEKLY)
        self.assertIn("**↓** **Sleep latency** was lower", rendered)
        self.assertIn("**↑** **Average HRV** was higher", rendered)
        self.assertIn("**→** **Time in bed** was unchanged", rendered)
        self.assertIn("do not mean clinically good or bad", rendered)

    def test_hume_rows_and_limitations_are_carried_forward(self):
        rendered = week_view.render_week_view(WEEKLY)
        self.assertIn("| Weight | 214.5 lb | 214.4 lb", rendered)
        self.assertIn("Hume coverage is partial", rendered)
        self.assertIn("Temporal alignment does not establish causation", rendered)

    def test_invalid_input_fails_closed(self):
        with self.assertRaises(week_view.WeekViewError):
            week_view.render_week_view("# not a weekly insight")

    def test_create_only_writer_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Cross-Source Weekly Insight - 2026-08-23.md"
            output = root / "2026-08-23 - PHI Week View.md"
            source.write_text(WEEKLY, encoding="utf-8")
            week_view.write_new_week_view(source, output)
            self.assertTrue(output.is_file())
            with self.assertRaises(week_view.WeekViewError):
                week_view.write_new_week_view(source, output)


if __name__ == "__main__":
    unittest.main()
