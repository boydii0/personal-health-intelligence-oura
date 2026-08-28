"""Deterministic Step 8B cross-source Monthly Review generator."""
from __future__ import annotations

import math
import re
import statistics
from datetime import date, datetime, timedelta

VERSION = "cross-source-monthly-review-generator-0.1"
MIN_CORRELATION_PAIRS = 5


def fm(text: str, key: str):
    m = re.search(rf"(?m)^{re.escape(key)}:\s*(.+?)\s*$", text)
    return m.group(1).strip() if m else None


def events(text: str):
    out = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) < 5:
            continue
        try:
            d = date.fromisoformat(c[0])
        except ValueError:
            continue
        out.append({"date": d, "event": c[1], "product": c[2], "detail": c[3], "evidence": c[4]})
    return out


def local_day(record: dict) -> date:
    t = datetime.fromisoformat(record["observed_at_utc"].replace("Z", "+00:00"))
    o = record.get("zone_offset", "+00:00")
    sign = 1 if o[0] == "+" else -1
    return (t + sign * timedelta(hours=int(o[1:3]), minutes=int(o[4:6]))).date()


def _trusted(records):
    return [r for r in records if r.get("data_quality_state") == "trusted"]


def validate(sleep, heart, hume, function, regimen, timeline, meds):
    for label, doc in (("Oura sleep", sleep), ("Oura heart", heart)):
        if not doc.get("records"):
            raise ValueError(f"Step 8B blocked: {label} core has no records")
        m = doc.get("metadata", {})
        if m.get("imputation_applied") or m.get("smoothing_applied") or m.get("ai_interpretation_applied"):
            raise ValueError(f"Step 8B blocked: {label} core quality controls failed")
        if not _trusted(doc["records"]):
            raise ValueError(f"Step 8B blocked: {label} has no trusted records")
    if hume.get("source", {}).get("validation_status") != "PASS":
        raise ValueError("Step 8B blocked: Hume source validation is not PASS")
    hn = hume.get("normalization", {})
    if hn.get("imputation") or hn.get("smoothing") or hn.get("ai_interpretation") or not hume.get("records"):
        raise ValueError("Step 8B blocked: Hume normalization gate failed")
    if function.get("lab_panel", {}).get("verification_state") != "verified" or not function.get("controls", {}).get("owner_verified_all_candidate_rows"):
        raise ValueError("Step 8B blocked: Function Health verification gate failed")
    if function.get("controls", {}).get("clinical_interpretation"):
        raise ValueError("Step 8B blocked: Function Health clinical interpretation present")
    if fm(regimen, "owner_verified") != "true" or fm(regimen, "step7_status") != "complete-pass" or fm(timeline, "step7_status") != "complete-pass":
        raise ValueError("Step 8B blocked: supplement Step 7 verification gate failed")
    if meds.get("authority") != "owner_confirmed" or meds.get("status") != "active":
        raise ValueError("Step 8B blocked: medication authority gate failed")


def _mean(values):
    return None if not values else statistics.mean(values)


def _pearson(pairs):
    if len(pairs) < MIN_CORRELATION_PAIRS:
        return None
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    den = math.sqrt(sum(x * x for x in dx) * sum(y * y for y in dy))
    if den == 0:
        return None
    return sum(x * y for x, y in zip(dx, dy)) / den


def _window(records, start, end):
    return [r for r in records if start <= date.fromisoformat(r["day"]) <= end]


def _hume_window(records, metric, start, end):
    return [r for r in records if r.get("metric") == metric and r.get("data_quality_state") == "trusted" and start <= local_day(r) <= end]


def _fmt(v, digits=2):
    return "n/a" if v is None else f"{v:.{digits}f}".rstrip("0").rstrip(".")


def generate_markdown(sleep, heart, hume, function, regimen, timeline, meds):
    validate(sleep, heart, hume, function, regimen, timeline, meds)
    sleep_records = sorted(_trusted(sleep["records"]), key=lambda r: r["day"])
    heart_records = sorted(_trusted(heart["records"]), key=lambda r: r["day"])
    heart_by_day = {r["day"]: r for r in heart_records}
    aligned_days = [r["day"] for r in sleep_records if r["day"] in heart_by_day]
    if not aligned_days:
        raise ValueError("Step 8B blocked: no aligned trusted Oura sleep/heart days")

    report_date = date.fromisoformat(max(aligned_days))
    current_start = report_date - timedelta(days=27)
    prior_end = current_start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=27)
    cs = _window(sleep_records, current_start, report_date)
    ch = _window(heart_records, current_start, report_date)
    ps = _window(sleep_records, prior_start, prior_end)
    ph = _window(heart_records, prior_start, prior_end)
    current_complete = len(cs) == 28 and len(ch) == 28
    prior_complete = len(ps) == 28 and len(ph) == 28

    metrics = [
        ("total_sleep_minutes", "Total sleep", "min", cs, ps),
        ("efficiency_percent", "Sleep efficiency", "%", cs, ps),
        ("oura_sleep_score", "Oura sleep score", "score", cs, ps),
        ("average_sleeping_heart_rate_bpm", "Average sleeping heart rate", "bpm", ch, ph),
        ("lowest_sleeping_heart_rate_bpm", "Lowest sleeping heart rate", "bpm", ch, ph),
        ("average_hrv_ms", "Average HRV", "ms", ch, ph),
    ]

    rows = []
    for key, label, unit, cur, prev in metrics:
        cmean = _mean([r[key] for r in cur if r.get(key) is not None])
        pmean = _mean([r[key] for r in prev if r.get(key) is not None]) if prior_complete else None
        delta = cmean - pmean if cmean is not None and pmean is not None else None
        pct = (delta / pmean * 100) if delta is not None and pmean else None
        rows.append((label, unit, cmean, pmean, delta, pct))

    hume_stats = {}
    for metric, label, unit in (("weight", "Weight", "lb"), ("body_fat_percentage", "Body fat", "%")):
        cur = _hume_window(hume["records"], metric, current_start, report_date)
        prev = _hume_window(hume["records"], metric, prior_start, prior_end)
        hume_stats[metric] = {
            "label": label, "unit": unit, "current": cur, "prior": prev,
            "current_mean": _mean([r["value_normalized"] for r in cur]),
            "prior_mean": _mean([r["value_normalized"] for r in prev]),
        }

    sleep_by_day = {date.fromisoformat(r["day"]): r for r in cs}
    heart_day = {date.fromisoformat(r["day"]): r for r in ch}
    correlations = []
    for hmetric, hlabel in (("weight", "Weight"), ("body_fat_percentage", "Body fat")):
        daily = {}
        for r in hume_stats[hmetric]["current"]:
            daily.setdefault(local_day(r), []).append(r["value_normalized"])
        hmean = {d: statistics.mean(v) for d, v in daily.items()}
        for okey, olabel, source in (("total_sleep_minutes", "Total sleep", sleep_by_day), ("average_hrv_ms", "Average HRV", heart_day)):
            pairs = [(hmean[d], source[d][okey]) for d in sorted(set(hmean) & set(source)) if source[d].get(okey) is not None]
            correlations.append((hlabel, olabel, len(pairs), _pearson(pairs)))

    ev = events(timeline)
    current_events = [e for e in ev if current_start <= e["date"] <= report_date]
    prior_events = [e for e in ev if prior_start <= e["date"] <= prior_end]
    panel = function["lab_panel"]
    med_date = date.fromisoformat(meds["last_confirmed"])

    L = [
        "---", "type: monthly-review", "status: candidate-owner-validation", "version: 0.1",
        f"generated_for_date: {report_date}", "project: Personal Health Intelligence", "source: cross-source",
        f"generator_version: {VERSION}", "clinical_use: false", "causality: association-only", "---", "",
        f"# Cross-Source Monthly Review — {report_date}", "", "## Analysis Gate", "",
        "**PASS — deterministic Step 8B candidate generated; owner validation still required.**", "",
        f"- Current 28-day window: `{current_start}` through `{report_date}`; Oura sleep {len(cs)}/28 days, heart {len(ch)}/28 days.",
        f"- Prior 28-day comparison window: `{prior_start}` through `{prior_end}`; Oura sleep {len(ps)}/28 days, heart {len(ph)}/28 days.",
        f"- Full prior-window comparison available: **{'YES' if prior_complete else 'NO'}**.",
        "- When the prior window is incomplete, month-over-month deltas are intentionally withheld rather than calculated from a partial period.",
        "- No imputation, smoothing, clinical thresholding, diagnosis, treatment recommendation, or causal inference.", "",
        "## Sustained Oura Trends", "", "| Metric | Current 28-day mean | Prior 28-day mean | Delta | Relative delta |", "|---|---:|---:|---:|---:|",
    ]
    for label, unit, c, p, d, pct in rows:
        L.append(f"| {label} | {_fmt(c)} {unit} | {_fmt(p)} {unit} | {_fmt(d)} {unit} | {_fmt(pct)}% |")

    L += ["", "## Body Composition", "", "| Metric | Current observations | Current mean | Prior observations | Prior mean |", "|---|---:|---:|---:|---:|"]
    for s in hume_stats.values():
        L.append(f"| {s['label']} | {len(s['current'])} | {_fmt(s['current_mean'],3)} {s['unit']} | {len(s['prior'])} | {_fmt(s['prior_mean'],3)} {s['unit']} |")
    L += ["", "Hume remains intermittent; missing dates are not imputed and observation counts are shown explicitly.", "", "## Cross-Source Co-Movement", ""]
    for a, b, n, r in correlations:
        if r is None:
            L.append(f"- **{a} vs {b}:** insufficient paired observations for a stable descriptive coefficient (`n={n}`; minimum {MIN_CORRELATION_PAIRS}).")
        else:
            L.append(f"- **{a} vs {b}:** Pearson `r={r:.3f}` across `n={n}` same-day observations. This is descriptive co-movement only and does not establish causation.")

    L += ["", "## Intervention Windows", "", f"### Current window ({len(current_events)} event(s))"]
    L += [f"- `{e['date']}` — **{e['event']} {e['product']}**: {e['detail']} ({e['evidence']})." for e in current_events] or ["- No dated supplement events in the current window."]
    L += ["", f"### Prior window ({len(prior_events)} event(s))"]
    L += [f"- `{e['date']}` — **{e['event']} {e['product']}**: {e['detail']} ({e['evidence']})." for e in prior_events] or ["- No dated supplement events in the prior window."]

    L += ["", "## Function Health Anchor", "",
          f"- Verified panel collected `{panel['collection_date']}` with {function['normalized_biomarker_count']} normalized biomarkers.",
          "- A single panel is static context only; no laboratory trend is inferred until a later verified panel is available.", "",
          "## Medication Context", "", f"- Owner-confirmed medication baseline last confirmed `{meds['last_confirmed']}`.",
          f"- Confirmation is {'inside' if current_start <= med_date <= report_date else 'outside'} the current 28-day observation window; context only, no medication recommendation is generated.", "",
          "## Data-Quality Gaps", ""]
    if not current_complete:
        L.append(f"- Current Oura coverage is incomplete: sleep {len(cs)}/28; heart {len(ch)}/28.")
    if not prior_complete:
        L.append(f"- Prior Oura comparison coverage is incomplete: sleep {len(ps)}/28; heart {len(ph)}/28. Full month-over-month claims are withheld.")
    for s in hume_stats.values():
        L.append(f"- {s['label']} coverage: {len(s['current'])} current-window observations and {len(s['prior'])} prior-window observations.")
    L.append("- Function Health has one verified panel only; panel-to-panel lab trend is unavailable.")

    L += ["", "## Questions Worth Investigating", ""]
    if not prior_complete:
        L.append("- Does the direction of the current 28-day Oura profile persist once a complete prior 28-day comparison window becomes available?")
    strong = sorted([x for x in correlations if x[3] is not None], key=lambda x: abs(x[3]), reverse=True)
    if strong:
        a, b, n, r = strong[0]
        L.append(f"- Does the observed same-day co-movement between {a} and {b} (`r={r:.3f}`, n={n}) persist with more observations, or does it attenuate as coverage grows?")
    L.append("- Which intervention-window changes remain directionally consistent across future monthly reviews without implying causation?")
    L.append("- What data-quality gaps should be closed before making stronger longitudinal interpretations?")

    L += ["", "## Provenance and Boundaries", "",
          f"- Oura sleep: `{sleep.get('metadata',{}).get('transformation_version','unknown')}`.",
          f"- Oura heart: `{heart.get('metadata',{}).get('transformation_version','unknown')}`.",
          f"- Hume: `{hume.get('normalizer_version','unknown')}`; source validation PASS.",
          f"- Function Health: `{function.get('normalizer_version','unknown')}`; verified single-panel anchor.",
          "- Supplements: owner-confirmed current regimen and dated timeline; planned regimen is not treated as proof of adherence.",
          f"- Medications: `{meds['authority']}` context only.", f"- Generator: `{VERSION}`.", "",
          "## Owner Validation Gate", "",
          "Step 8B remains open until the owner validates window coverage, sustained-trend calculations, co-movement math, intervention chronology, data-quality limitations, and non-causal/non-clinical boundaries.", ""]
    return "\n".join(L)
