"""Deterministic Step 8A cross-source Weekly Insight generator."""
from __future__ import annotations
import argparse, json, re, statistics
from datetime import date, datetime, timedelta
from pathlib import Path

VERSION = "cross-source-weekly-insight-generator-0.1"
DISPLAY = {
    "total_sleep_minutes":"Total sleep","time_in_bed_minutes":"Time in bed",
    "deep_sleep_minutes":"Deep sleep","light_sleep_minutes":"Light sleep",
    "rem_sleep_minutes":"REM sleep","awake_minutes":"Awake time",
    "efficiency_percent":"Sleep efficiency","latency_minutes":"Sleep latency",
    "average_breaths_per_minute":"Average breathing rate","oura_sleep_score":"Oura sleep score",
    "average_sleeping_heart_rate_bpm":"Average sleeping heart rate",
    "lowest_sleeping_heart_rate_bpm":"Lowest sleeping heart rate","average_hrv_ms":"Average HRV",
}

def fmt(v):
    return "n/a" if v is None else (str(v) if isinstance(v,int) else f"{v:.3f}".rstrip("0").rstrip("."))

def fm(text,key):
    m=re.search(rf"(?m)^{re.escape(key)}:\s*(.+?)\s*$",text)
    return m.group(1).strip() if m else None

def events(text):
    out=[]
    for line in text.splitlines():
        if not line.startswith("|"): continue
        c=[x.strip() for x in line.strip().strip("|").split("|")]
        if len(c)<5: continue
        try: d=date.fromisoformat(c[0])
        except ValueError: continue
        out.append({"date":d,"event":c[1],"product":c[2],"detail":c[3],"evidence":c[4]})
    return out

def validate(oura,hume,function,regimen,timeline,meds):
    m=oura.get("metadata",{}); q=m.get("data_quality",{})
    for label,a,b in [
        ("current window",m.get("current_window",{}).get("present_days"),m.get("current_window",{}).get("expected_days")),
        ("baseline window",m.get("baseline_window",{}).get("present_days"),m.get("baseline_window",{}).get("expected_days")),
        ("sleep records",q.get("sleep_trusted_records"),q.get("sleep_expected_records")),
        ("heart records",q.get("heart_trusted_records"),q.get("heart_expected_records"))]:
        if a is None or a!=b: raise ValueError(f"Step 8A blocked: incomplete Oura {label}")
    if q.get("coverage_percent")!=100.0 or q.get("imputation_applied") or q.get("smoothing_applied"):
        raise ValueError("Step 8A blocked: Oura quality gate failed")
    if m.get("freshness",{}).get("state")=="stale" or not oura.get("metrics"):
        raise ValueError("Step 8A blocked: Oura freshness/metrics gate failed")
    if hume.get("source",{}).get("validation_status")!="PASS":
        raise ValueError("Step 8A blocked: Hume source validation is not PASS")
    hn=hume.get("normalization",{})
    if hn.get("imputation") or hn.get("smoothing") or hn.get("ai_interpretation") or not hume.get("records"):
        raise ValueError("Step 8A blocked: Hume normalization gate failed")
    if function.get("lab_panel",{}).get("verification_state")!="verified" or not function.get("controls",{}).get("owner_verified_all_candidate_rows"):
        raise ValueError("Step 8A blocked: Function Health verification gate failed")
    if function.get("controls",{}).get("clinical_interpretation"):
        raise ValueError("Step 8A blocked: Function Health clinical interpretation present")
    if fm(regimen,"owner_verified")!="true" or fm(regimen,"step7_status")!="complete-pass" or fm(timeline,"step7_status")!="complete-pass":
        raise ValueError("Step 8A blocked: supplement Step 7 verification gate failed")
    if meds.get("authority")!="owner_confirmed" or meds.get("status")!="active":
        raise ValueError("Step 8A blocked: medication authority gate failed")

def local_day(r):
    t=datetime.fromisoformat(r["observed_at_utc"].replace("Z","+00:00"))
    o=r.get("zone_offset","+00:00"); s=1 if o[0]=="+" else -1
    return (t+s*timedelta(hours=int(o[1:3]),minutes=int(o[4:6]))).date()

def hume_stats(hume,cs,ce,bs,be):
    out={}
    for metric in ("weight","body_fat_percentage"):
        rs=[r for r in hume["records"] if r.get("metric")==metric and r.get("data_quality_state")=="trusted"]
        c=[r for r in rs if cs<=local_day(r)<=ce]; b=[r for r in rs if bs<=local_day(r)<=be]
        def summ(x):
            vals=[r["value_normalized"] for r in x]
            return None if not vals else {"n":len(vals),"mean":statistics.mean(vals),"days":sorted({str(local_day(r)) for r in x})}
        x,y=summ(c),summ(b); d=p=None
        if x and y:
            d=x["mean"]-y["mean"]; p=d/y["mean"]*100 if y["mean"] else None
        out[metric]={"current":x,"baseline":y,"delta":d,"pct":p}
    return out

def oura_rows(oura):
    rows=[]
    for name,v in oura["metrics"].items():
        d=v.get("absolute_delta_current_mean_minus_baseline_mean"); p=v.get("percent_delta_current_mean_vs_baseline_mean")
        rows.append({"name":name,"label":DISPLAY.get(name,name),"unit":v["unit"],"current":v["current_7_day"]["mean"],
                     "baseline":v["trailing_28_day"]["mean"],"delta":d,"pct":p,"mag":abs(p) if p is not None else -1})
    return sorted(rows,key=lambda r:r["mag"],reverse=True)

def generate_markdown(oura,hume,function,regimen,timeline,meds):
    validate(oura,hume,function,regimen,timeline,meds)
    m=oura["metadata"]; cw=m["current_window"]; bw=m["baseline_window"]
    cs,ce,bs,be=map(date.fromisoformat,[cw["start"],cw["end"],bw["start"],bw["end"]])
    rd=date.fromisoformat(m["generated_for_date"]); hs=hume_stats(hume,cs,ce,bs,be)
    ev=events(timeline); cur=[e for e in ev if cs<=e["date"]<=ce]; post=[e for e in ev if ce<e["date"]<=rd]
    top=oura_rows(oura)[:5]; panel=function["lab_panel"]; med_date=date.fromisoformat(meds["last_confirmed"])
    hd=max(len(hs[k]["current"]["days"]) if hs[k]["current"] else 0 for k in hs)
    bd=max(len(hs[k]["baseline"]["days"]) if hs[k]["baseline"] else 0 for k in hs)
    med_use="available within window" if med_date<=ce else "post-window confirmation; excluded from week-window interpretation"
    L=["---","type: weekly-insight","status: candidate-owner-validation","version: 0.2",
       f"generated_for_date: {m['generated_for_date']}","project: Personal Health Intelligence","source: cross-source",
       f"generator_version: {VERSION}","clinical_use: false","causality: association-only","---","",
       f"# Cross-Source Weekly Insight — {m['generated_for_date']}","","## Analysis Gate","",
       "**PASS — deterministic Step 8A candidate generated; owner validation still required.**","",
       f"- Current window: `{cw['start']}` through `{cw['end']}`; Oura {cw['present_days']}/{cw['expected_days']} days.",
       f"- Trailing baseline: `{bw['start']}` through `{bw['end']}`; Oura {bw['present_days']}/{bw['expected_days']} days.",
       f"- Hume coverage: {hd}/7 current-window observation days; {bd}/28 trailing-window observation days.",
       f"- Function Health: verified single panel `{panel['collection_date']}`; {function['normalized_biomarker_count']} normalized biomarkers; static anchor only.",
       f"- Supplements: {len(cur)} event(s) inside current window; {len(post)} post-window event(s) through report date.",
       f"- Medications: owner-confirmed `{meds['last_confirmed']}`; {med_use}.",
       "- No imputation, smoothing, clinical thresholds, diagnosis, treatment recommendations, or causal claims.","",
       "## Executive Summary","","### Oura — largest descriptive differences",""]
    for i,r in enumerate(top,1):
        sign="+" if r["pct"] is not None and r["pct"]>0 else ""
        direction="higher" if (r["delta"] or 0)>0 else "lower" if (r["delta"] or 0)<0 else "unchanged"
        L.append(f"{i}. **{r['label']}** was {direction}: {fmt(r['current'])} {r['unit']} vs {fmt(r['baseline'])} {r['unit']} ({sign}{fmt(r['pct'])}%).")
    L+=["","### Hume — aligned body composition","",
        "| Metric | Current mean | Trailing mean | Current n | Trailing n | Delta | Relative delta |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for k,label,unit in [("weight","Weight","lb"),("body_fat_percentage","Body fat","%")]:
        s=hs[k]
        if s["current"] and s["baseline"]:
            du="pp" if k=="body_fat_percentage" else unit
            L.append(f"| {label} | {fmt(s['current']['mean'])} {unit} | {fmt(s['baseline']['mean'])} {unit} | {s['current']['n']} | {s['baseline']['n']} | {s['delta']:+.3f} {du} | {s['pct']:+.3f}% |")
        else: L.append(f"| {label} | n/a | n/a | 0 | 0 | n/a | n/a |")
    L+=["","Hume is intermittent in this dataset; no missing observation days are imputed.","",
        "### Intervention chronology",""]
    L += [f"- `{e['date']}` — **{e['event']} {e['product']}**: {e['detail']} ({e['evidence']})." for e in cur] or ["- No current-window supplement events."]
    if post:
        L+=["","Post-window events are chronological context only and **excluded from current-window association logic**:"]
        L += [f"- `{e['date']}` — **{e['event']} {e['product']}**: {e['detail']}." for e in post]
    L+=["","### Function Health anchor","",
        f"- Verified panel collected `{panel['collection_date']}` with {function['normalized_biomarker_count']} normalized biomarkers.",
        "- One panel cannot establish a laboratory trend; individual biomarker values are not interpreted by this generator.","",
        "## Traceable Claims","",
        "| Claim ID | Claim | Classification | Evidence |","|---|---|---|---|",
        "| PHI-WK-001 | Oura passed completeness, freshness, trusted-record, and no-imputation/no-smoothing gates. | observed fact | Oura baseline metadata |"]
    n=2
    for r in top:
        sign="+" if r["pct"] is not None and r["pct"]>0 else ""
        L.append(f"| PHI-WK-{n:03d} | {r['label']}: {fmt(r['current'])} {r['unit']} vs {fmt(r['baseline'])} {r['unit']} ({sign}{fmt(r['pct'])}%). | calculated trend | Oura `metrics.{r['name']}` |"); n+=1
    for k,label,unit in [("weight","Weight","lb"),("body_fat_percentage","Body fat","%")]:
        s=hs[k]
        if s["current"] and s["baseline"]:
            L.append(f"| PHI-WK-{n:03d} | {label}: {fmt(s['current']['mean'])} {unit} vs {fmt(s['baseline']['mean'])} {unit} ({s['pct']:+.3f}% relative; intermittent observations). | calculated trend | Hume aligned trusted records |"); n+=1
    if cur:
        L.append(f"| PHI-WK-{n:03d} | Current-window regimen start event(s): {', '.join(e['product'] for e in cur)}. | observed fact | `Supplement Timeline.md` |"); n+=1
    L.append(f"| PHI-WK-{n:03d} | Function panel `{panel['collection_date']}` is verified and static; no lab trend inferred. | observed fact / limitation | Function Health panel metadata |")
    L+=["","## Associations / Hypotheses",""]
    if cur:
        L.append("Current-window supplement starts are temporally aligned with the Oura and Hume observations above. **Association-only:** planned regimen does not prove adherence, windows overlap, Hume is intermittent, and temporal alignment does **not** establish causation.")
    else: L.append("No intervention-window association asserted.")
    L+=["","## Medication Context","",f"- Authority: **{meds['authority']}**; last confirmed `{meds['last_confirmed']}`.",
        f"- Weekly-window use: **{med_use}**.","- Context only; no medication recommendation is generated.","",
        "## Limitations","",f"- Oura current window overlaps the trailing baseline by {m.get('baseline_overlap_days')} days.",
        f"- Hume coverage is partial ({hd}/7 current; {bd}/28 trailing observation days).",
        "- Function Health contributes one verified panel only.","- Supplement events are planned-regimen boundaries, not adherence evidence.",
        "- Relative changes are descriptive, not clinical thresholds.","- Temporal alignment does not establish causation.","",
        "## Provenance","",f"- Oura: `oura_baseline_core_v0.1.json` — `{m['calculation_version']}`.",
        f"- Hume: `hume_body_composition_core_v0.1.json` — `{hume['normalizer_version']}`; source SHA-256 `{hume['source']['sha256']}`.",
        f"- Function: `function_health_biomarker_core_v0.1.json` — `{function['normalizer_version']}`; verified.",
        "- Supplements: `Supplement Regimen - Current.md`, `Supplement Timeline.md` — owner-confirmed.",
        f"- Medications: `current_medications_v0.1.json` — `{meds['authority']}`.",f"- Generator: `{VERSION}`.","",
        "## Owner Validation Gate","",
        "Step 8A remains open until the owner validates source coverage/windows, Hume calculations, supplement chronology, and the non-causal/non-clinical boundaries.",""]
    return "\n".join(L)

def main():
    p=argparse.ArgumentParser()
    for a in ("oura-baseline","hume-core","function-core","supplement-regimen","supplement-timeline","medications","output"):
        p.add_argument("--"+a,required=True,type=Path)
    a=p.parse_args()
    report=generate_markdown(json.loads(a.oura_baseline.read_text()),json.loads(a.hume_core.read_text()),
        json.loads(a.function_core.read_text()),a.supplement_regimen.read_text(),a.supplement_timeline.read_text(),
        json.loads(a.medications.read_text()))
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(report+"\n")

if __name__=="__main__": main()
