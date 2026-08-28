"""Vault-aware deterministic Step 8B Monthly Review runner."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
ANALYTICS_DIR = PROJECT_ROOT / "analytics"
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(ANALYTICS_DIR))
sys.path.insert(0, str(SRC_DIR))

from generate_cross_source_monthly_review import generate_markdown  # noqa: E402
from oura_connector.config import _load_dotenv  # noqa: E402


def load_vault_root() -> Path:
    _load_dotenv(PROJECT_ROOT / ".env")
    raw = os.environ.get("VAULT_ROOT", "").strip()
    if not raw:
        raise RuntimeError("VAULT_ROOT is missing from environment/.env")
    root = Path(raw)
    if not root.is_dir():
        raise RuntimeError(f"VAULT_ROOT does not exist: {root}")
    return root


def paths_from_vault(vault_root: Path) -> dict[str, Path]:
    repo = vault_root / "03_Areas" / "Health" / "Personal Health Repository"
    return {
        "sleep_core": repo / "Normalized Data" / "Sleep" / "oura_sleep_core_v0.1.json",
        "heart_core": repo / "Normalized Data" / "Heart" / "oura_heart_core_v0.1.json",
        "hume_core": repo / "Normalized Data" / "Body Composition" / "hume_body_composition_core_v0.1.json",
        "function_core": repo / "Normalized Data" / "Biomarkers" / "function_health_biomarker_core_v0.1.json",
        "supplement_regimen": repo / "Supplements" / "Supplement Regimen - Current.md",
        "supplement_timeline": repo / "Supplements" / "Supplement Timeline.md",
        "medications": repo / "Normalized Data" / "Medications" / "current_medications_v0.1.json",
        "monthly_dir": repo / "Insights" / "Monthly",
    }


def write_status(payload: dict) -> None:
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PHI" / "OuraRuntime"
    local.mkdir(parents=True, exist_ok=True)
    path = local / "monthly_review_last_status.json"
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def atomic_create(path: Path, text: str) -> str:
    payload = (text + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == payload:
            return "NOOP_IDENTICAL"
        raise RuntimeError(f"Monthly Review already exists with different content: {path}")
    temp = path.with_name(path.name + ".tmp")
    with temp.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)
    return "CREATED"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    try:
        vault = load_vault_root()
        p = paths_from_vault(vault)
        required = ("sleep_core", "heart_core", "hume_core", "function_core", "supplement_regimen", "supplement_timeline", "medications")
        for key in required:
            if not p[key].is_file():
                raise RuntimeError(f"Canonical input missing: {p[key]}")
        sleep = json.loads(p["sleep_core"].read_text(encoding="utf-8"))
        heart = json.loads(p["heart_core"].read_text(encoding="utf-8"))
        hume = json.loads(p["hume_core"].read_text(encoding="utf-8"))
        function = json.loads(p["function_core"].read_text(encoding="utf-8"))
        regimen = p["supplement_regimen"].read_text(encoding="utf-8")
        timeline = p["supplement_timeline"].read_text(encoding="utf-8")
        meds = json.loads(p["medications"].read_text(encoding="utf-8"))
        report = generate_markdown(sleep, heart, hume, function, regimen, timeline, meds)
        generated_for = max(r["day"] for r in sleep["records"] if r.get("data_quality_state") == "trusted" and r["day"] in {h["day"] for h in heart["records"] if h.get("data_quality_state") == "trusted"})
        output = p["monthly_dir"] / f"Cross-Source Monthly Review - {generated_for}.md"
        state = "VALIDATE_ONLY" if args.validate_only else atomic_create(output, report)
        status = {
            "status": "PASS", "mode": "validate-only" if args.validate_only else "publish",
            "started_at_utc": started.isoformat(), "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "generated_for_date": generated_for, "output": str(output), "publish_state": state,
            "ai_interpretation_executed": False,
        }
        write_status(status)
        print("PHI Cross-Source Monthly Review")
        print("Review: PASS")
        print(f"Mode: {status['mode']}")
        print(f"Generated for date: {generated_for}")
        print(f"Output: {output}")
        print(f"Publish state: {state}")
        print("AI interpretation executed: NO")
        return 0
    except Exception as exc:
        try:
            write_status({"status":"FAIL","error_type":type(exc).__name__,"error":str(exc),"ai_interpretation_executed":False})
        except Exception:
            pass
        print(f"Review: FAIL — {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
