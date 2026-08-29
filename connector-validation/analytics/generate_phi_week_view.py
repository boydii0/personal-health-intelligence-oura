"""Render a compact PHI Week View from an existing detailed Weekly Insight.

This module is presentation-only. It performs no health calculations and does
not read source systems. The detailed Cross-Source Weekly Insight remains the
evidence-oriented artifact and calculation authority.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

VERSION = "phi-week-view-renderer-0.1"


class WeekViewError(ValueError):
    """Raised when the detailed Weekly Insight cannot be safely reduced."""


def _frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    if not match:
        raise WeekViewError("Weekly Insight is missing YAML frontmatter")
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line or line.startswith(" "):
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def _section(text: str, heading: str, next_heading_level: int = 2) -> str:
    pattern = rf"(?ms)^{'#' * next_heading_level} {re.escape(heading)}\n(.*?)(?=^{'#' * next_heading_level} |\Z)"
    match = re.search(pattern, text)
    return "" if match is None else match.group(1).strip()


def _subsection(text: str, heading: str) -> str:
    pattern = rf"(?ms)^### {re.escape(heading)}\n(.*?)(?=^### |^## |\Z)"
    match = re.search(pattern, text)
    return "" if match is None else match.group(1).strip()


def _bullet_with_prefix(section: str, prefix: str) -> str:
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"- {prefix}"):
            return stripped[2:]
    raise WeekViewError(f"missing required analysis-gate bullet: {prefix}")


def _direction(line: str) -> str:
    lowered = line.lower()
    if " was lower:" in lowered:
        return "↓"
    if " was higher:" in lowered:
        return "↑"
    if " was unchanged:" in lowered:
        return "→"
    return "↕"


def _clean_numbered(line: str) -> str:
    return re.sub(r"^\d+\.\s*", "", line.strip())


def _extract_oura_lines(text: str) -> list[str]:
    section = _subsection(text, "Oura — largest descriptive differences")
    rows = [line.strip() for line in section.splitlines() if re.match(r"^\d+\.\s", line.strip())]
    if not rows:
        raise WeekViewError("Weekly Insight has no Oura descriptive-difference rows")
    return rows[:5]


def _extract_hume_rows(text: str) -> list[list[str]]:
    section = _subsection(text, "Hume — aligned body composition")
    rows: list[list[str]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped or "Metric" in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) >= 7 and cells[0] in {"Weight", "Body fat"}:
            rows.append(cells[:7])
    return rows


def _extract_limitations(text: str) -> list[str]:
    section = _section(text, "Limitations")
    return [line.strip()[2:] for line in section.splitlines() if line.strip().startswith("- ")]


def _source_link(generated_for_date: str) -> str:
    return f"[[Cross-Source Weekly Insight - {generated_for_date}]]"


def render_week_view(weekly_insight: str) -> str:
    """Create a one-screen derivative from one detailed Weekly Insight."""

    fm = _frontmatter(weekly_insight)
    if fm.get("type") != "weekly-insight":
        raise WeekViewError("input must have type: weekly-insight")
    generated_for_date = fm.get("generated_for_date")
    if not generated_for_date:
        raise WeekViewError("input is missing generated_for_date")

    source_status = fm.get("status", "unknown")
    gate = _section(weekly_insight, "Analysis Gate")
    current_window = _bullet_with_prefix(gate, "Current window:")
    trailing_window = _bullet_with_prefix(gate, "Trailing baseline:")
    hume_coverage = _bullet_with_prefix(gate, "Hume coverage:")
    function_state = _bullet_with_prefix(gate, "Function Health:")
    supplement_state = _bullet_with_prefix(gate, "Supplements:")
    medication_state = _bullet_with_prefix(gate, "Medications:")

    oura_lines = _extract_oura_lines(weekly_insight)
    hume_rows = _extract_hume_rows(weekly_insight)
    limitations = _extract_limitations(weekly_insight)

    current_match = re.search(r"`(\d{4}-\d{2}-\d{2})` through `(\d{4}-\d{2}-\d{2})`", current_window)
    if current_match is None:
        raise WeekViewError("cannot parse current observation window")
    window_start, window_end = current_match.groups()

    lines = [
        "---",
        "type: phi-week-view",
        "status: owner-review",
        f"generated_for_date: {generated_for_date}",
        f"observation_window_start: {window_start}",
        f"observation_window_end: {window_end}",
        "project: Personal Health Intelligence",
        f"source_artifact: Cross-Source Weekly Insight - {generated_for_date}.md",
        f"source_status: {source_status}",
        "authority: derivative-zone-3",
        "clinical_use: false",
        "causality: association-only",
        f"renderer_version: {VERSION}",
        "realization_state: trial",
        "---",
        "",
        f"# PHI Week View — {generated_for_date}",
        "",
        f"> **Compact descriptive view.** Arrows show direction versus the trailing comparison window; they do not mean clinically good or bad. This view is derivative. See {_source_link(generated_for_date)} for evidence, provenance, limitations, and traceable claims.",
        "",
        "## Data Coverage",
        "",
        f"- {current_window}",
        f"- {trailing_window}",
        f"- {hume_coverage}",
        f"- {function_state}",
        f"- {supplement_state}",
        f"- {medication_state}",
        "",
        "## This Week — Descriptive Direction",
        "",
    ]

    for raw in oura_lines:
        lines.append(f"- **{_direction(raw)}** {_clean_numbered(raw)}")

    if hume_rows:
        lines.extend(
            [
                "",
                "## Body Composition",
                "",
                "| Metric | Current | Trailing | Current n | Trailing n | Delta | Relative delta |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in hume_rows:
            lines.append("| " + " | ".join(row) + " |")

    lines.extend(
        [
            "",
            "## What Changed Around the Same Time",
            "",
            f"- {supplement_state}",
            f"- {medication_state}",
            "- These are chronology/context only. Planned regimen does not prove adherence, and temporal alignment does not establish causation.",
            "",
            "## Limitations",
            "",
        ]
    )
    if limitations:
        lines.extend(f"- {item}" for item in limitations)
    else:
        lines.append("- See the detailed Weekly Insight for source limitations.")

    lines.extend(
        [
            "",
            "## Carry Forward",
            "",
            "- Compare the next dated Week View before treating any one-week movement as persistent.",
            "- Prefer denser source coverage before increasing confidence in body-composition direction.",
            "- Keep laboratory interpretation static until the PHI project has a second verified panel.",
            "",
            "## Evidence",
            "",
            f"- Detailed weekly evidence: {_source_link(generated_for_date)}",
            "- This compact file does not upgrade the detailed source artifact's validation status.",
            "",
            "## Realization Check",
            "",
            "- Owner reviewed: **pending**",
            "- Realized value: **trial**",
            "- Owner note: _Record whether this compact view is materially easier to use than the detailed Weekly Insight._",
            "",
        ]
    )
    return "\n".join(lines)


def write_new_week_view(source: Path, output: Path) -> None:
    """Write one new dated Week View and refuse overwrite or parent creation."""

    if not source.is_file():
        raise WeekViewError(f"source Weekly Insight does not exist: {source}")
    if output.exists():
        raise WeekViewError(f"output already exists: {output}")
    if not output.parent.is_dir():
        raise WeekViewError(f"output parent does not exist: {output.parent}")
    if output.suffix.lower() != ".md":
        raise WeekViewError("output must be a .md file")
    output.write_text(render_week_view(source.read_text(encoding="utf-8")) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create one derivative PHI Week View")
    parser.add_argument("--weekly-insight", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    write_new_week_view(args.weekly_insight, args.output)


if __name__ == "__main__":
    main()
