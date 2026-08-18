#!/usr/bin/env python3
"""Deterministically extract candidate lab rows from a Function Health "Data" PDF export.

Public code only. Never commit source PDFs or extracted personal health data to GitHub.
The parser preserves source text and fails conservatively; clinical interpretation and
trusted biomarker admission happen outside this utility after owner verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "phi.function_health_extraction.v0.1"
PARSER_VERSION = "function-health-data-pdf-parser-0.1"

CATEGORIES = {
    "Autoimmunity",
    "Blood",
    "Daily Metrics",
    "Electrolytes",
    "Environmental Toxins",
    "Heart",
    "Immune Regulation",
    "Kidney",
    "Liver",
    "Male Health",
    "Metabolic",
    "Nutrients",
    "Pancreas",
    "Stress & Aging",
    "Thyroid",
    "Urine",
}
NON_LAB_CATEGORIES = {"Daily Metrics"}
HEADER_PATTERNS = [
    re.compile(r"^\d{1,2}/\d{1,2}/\d{2},\s+\d{1,2}:\d{2}\s+[AP]M\s+Data$"),
    re.compile(r"^Damon Boyd$"),
    re.compile(r"^DOB:"),
]
STATUS_RE = re.compile(r"^(In Range|Below Range|Above Range|Out of Range)\s*[·•]\s*(.*)$")
UNITS = [
    "% by wt",
    "Million/uL",
    "Thousand/uL",
    "mL/min/1.73m2",
    "mL/kg/min",
    "cells/uL",
    "Angstrom",
    "mmol/L",
    "nmol/L",
    "mIU/mL",
    "mIU/L",
    "mcg/dL",
    "mg/dL",
    "ng/dL",
    "ng/mL",
    "pg/mL",
    "umol/L",
    "uIU/mL",
    "U/L",
    "g/dL",
    "fL",
    "pg",
    "ms",
    "cals",
    "min",
    "hours",
    "%",
]


class ExtractionError(ValueError):
    """Raised when the source cannot be parsed without guessing."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_layout_text(pdf_path: Path) -> str:
    """Use Poppler pdftotext layout mode so section and result order are preserved."""
    try:
        completed = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ExtractionError("pdftotext is required but was not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise ExtractionError(f"pdftotext failed with exit code {exc.returncode}") from exc
    return completed.stdout


def _split_value_unit(text: str) -> tuple[str, str | None]:
    source = text.strip()
    for unit in sorted(UNITS, key=len, reverse=True):
        match = re.match(rf"^(.*?)\s+({re.escape(unit)}(?:\s+\(calc\))?)$", source)
        if match:
            return match.group(1).strip(), match.group(2).strip()
    return source, None


def _clean_page(page_text: str) -> list[str]:
    lines: list[str] = []
    for raw in page_text.splitlines():
        value = raw.strip()
        if not value:
            continue
        if any(pattern.match(value) for pattern in HEADER_PATTERNS):
            continue
        lines.append(value)
    return lines


def parse_layout_text(text: str) -> dict[str, Any]:
    pages = text.split("\f")
    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    category: str | None = None
    pending_name: str | None = None
    pending_page: int | None = None

    for page_number, page_text in enumerate(pages, start=1):
        lines = _clean_page(page_text)
        index = 0

        if pending_name is not None and lines:
            match = STATUS_RE.match(lines[0])
            if match:
                status = match.group(1)
                result = match.group(2).strip()
                if not result:
                    if len(lines) < 2:
                        raise ExtractionError("cross-page result is incomplete")
                    result = lines[1]
                    index = 2
                else:
                    index = 1
                value, unit = _split_value_unit(result)
                record = {
                    "category_original": category,
                    "analyte_name_original": pending_name,
                    "range_flag_original": status,
                    "result_text_original": result,
                    "value_original": value,
                    "unit_original": unit,
                    "source_page": pending_page,
                    "source_page_continued": page_number,
                }
                (excluded if category in NON_LAB_CATEGORIES else candidates).append(record)
                pending_name = None
                pending_page = None

        while index < len(lines):
            line = lines[index]
            if line in CATEGORIES:
                category = line
                index += 1
                continue
            if category is None:
                index += 1
                continue

            analyte_name = line
            if index + 1 >= len(lines):
                pending_name = analyte_name
                pending_page = page_number
                index += 1
                continue

            next_line = lines[index + 1]
            if next_line in CATEGORIES:
                pending_name = analyte_name
                pending_page = page_number
                index += 1
                continue

            match = STATUS_RE.match(next_line)
            if match:
                status = match.group(1)
                result = match.group(2).strip()
                step = 2
                if not result:
                    if index + 2 >= len(lines):
                        pending_name = analyte_name
                        pending_page = page_number
                        index += 1
                        continue
                    result = lines[index + 2]
                    step = 3
            else:
                status = None
                result = next_line
                step = 2

            value, unit = _split_value_unit(result)
            record = {
                "category_original": category,
                "analyte_name_original": analyte_name,
                "range_flag_original": status,
                "result_text_original": result,
                "value_original": value,
                "unit_original": unit,
                "source_page": page_number,
            }
            (excluded if category in NON_LAB_CATEGORIES else candidates).append(record)
            index += step

    if pending_name is not None:
        raise ExtractionError(f"unresolved final source row: {pending_name}")

    name_counts = Counter(row["analyte_name_original"] for row in candidates)
    for row_index, row in enumerate(candidates, start=1):
        row["candidate_row_id"] = f"FH-{row_index:03d}"
        row["duplicate_name_occurrences"] = name_counts[row["analyte_name_original"]]
        row["duplicate_name_flag"] = row["duplicate_name_occurrences"] > 1
        row["verification_state"] = "unverified"
        row["parser_confidence"] = "high"

    for row_index, row in enumerate(excluded, start=1):
        row["excluded_row_id"] = f"FH-NONLAB-{row_index:03d}"
        row["exclusion_reason"] = (
            "Daily Metrics source section is not admitted to Function Health lab biomarker extraction."
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "extraction_controls": {
            "clinical_interpretation": False,
            "unit_normalization": False,
            "reference_range_inference": False,
            "deduplication": False,
            "daily_metrics_excluded_from_lab_candidates": True,
            "all_candidates_unverified": True,
        },
        "candidate_count": len(candidates),
        "excluded_non_lab_count": len(excluded),
        "duplicate_names": {
            name: count for name, count in sorted(name_counts.items()) if count > 1
        },
        "candidates": candidates,
        "excluded_non_lab_rows": excluded,
    }


def extract_pdf(pdf_path: Path) -> dict[str, Any]:
    parsed = parse_layout_text(extract_layout_text(pdf_path))
    parsed["source"] = {
        "file_name": pdf_path.name,
        "sha256": sha256_file(pdf_path),
        "source_system": "Function Health",
        "source_artifact_type": "Function Health Data PDF export",
        "collection_date": None,
        "report_date": None,
        "panel_identity": None,
    }
    parsed["verification_gate"] = {
        "state": "BLOCKED_PENDING_OWNER_VERIFICATION",
        "blocking_conditions": [
            "collection_date must not be inferred when absent from the source",
            "panel identity must not be inferred when absent from the source",
            "numeric reference-range boundaries must not be invented",
            "duplicate source occurrences must be reconciled before normalized admission",
        ],
    }
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_pdf", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()

    try:
        result = extract_pdf(args.source_pdf)
    except (OSError, ExtractionError) as exc:
        parser.error(str(exc))
        return 2

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"PASS: extracted {result['candidate_count']} lab candidate rows; "
        f"excluded {result['excluded_non_lab_count']} non-lab rows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
