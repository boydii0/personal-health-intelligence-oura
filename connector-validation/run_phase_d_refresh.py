"""Phase D: refresh canonical Oura normalized cores and baseline from Phase C runs."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
ANALYTICS_DIR = PROJECT_ROOT / "analytics"
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(ANALYTICS_DIR))
sys.path.insert(0, str(SRC_DIR))

from oura_connector.config import _load_dotenv  # noqa: E402
from calculate_oura_baselines import calculate as calculate_baseline  # noqa: E402
from refresh_oura_from_phase_c import discover_pass_runs, refresh, write_atomic  # noqa: E402


def paths_from_vault(vault_root: Path) -> dict[str, Path]:
    repo = vault_root / "03_Areas" / "Health" / "Personal Health Repository"
    return {
        "source_root": repo / "Source Data" / "Oura",
        "sleep_core": repo / "Normalized Data" / "Sleep" / "oura_sleep_core_v0.1.json",
        "heart_core": repo / "Normalized Data" / "Heart" / "oura_heart_core_v0.1.json",
        "baseline": repo / "Insights" / "Baselines" / "oura_baseline_core_v0.1.json",
    }


def load_vault_root() -> Path:
    _load_dotenv(PROJECT_ROOT / ".env")
    raw = os.environ.get("VAULT_ROOT", "").strip()
    if not raw:
        raise RuntimeError("VAULT_ROOT is missing from environment/.env")
    root = Path(raw)
    if not root.is_dir():
        raise RuntimeError(f"VAULT_ROOT does not exist: {root}")
    return root


def write_status(status: dict) -> None:
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PHI" / "OuraRuntime"
    local.mkdir(parents=True, exist_ok=True)
    path = local / "analytics_last_status.json"
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true", help="Build and validate outputs without replacing canonical files")
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    try:
        vault = load_vault_root()
        p = paths_from_vault(vault)
        for key in ("sleep_core", "heart_core"):
            if not p[key].is_file():
                raise RuntimeError(f"Canonical seed missing: {p[key]}")

        seed_sleep = json.loads(p["sleep_core"].read_text(encoding="utf-8"))
        seed_heart = json.loads(p["heart_core"].read_text(encoding="utf-8"))
        runs = discover_pass_runs(p["source_root"])
        sleep_doc, heart_doc = refresh(seed_sleep, seed_heart, runs)
        baseline_doc = calculate_baseline(sleep_doc, heart_doc, date.today())

        latest_day = baseline_doc["metadata"]["latest_observation_day"]
        status = {
            "status": "PASS",
            "mode": "validate-only" if args.validate_only else "publish",
            "started_at_utc": started.isoformat(),
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "phase_c_pass_runs": len(runs),
            "latest_phase_c_run_id": runs[-1].run_id,
            "sleep_core_records": len(sleep_doc["records"]),
            "heart_core_records": len(heart_doc["records"]),
            "latest_observation_day": latest_day,
            "baseline_freshness": baseline_doc["metadata"]["freshness"]["state"],
            "canonical_write_executed": not args.validate_only,
            "ai_interpretation_executed": False,
        }

        if not args.validate_only:
            # Publish only after both normalized cores and the baseline calculate successfully.
            write_atomic(p["sleep_core"], sleep_doc)
            write_atomic(p["heart_core"], heart_doc)
            write_atomic(p["baseline"], baseline_doc)

        write_status(status)
        print("Oura Phase D — normalization + baseline refresh")
        print("Refresh: PASS")
        print(f"Mode: {status['mode']}")
        print(f"PASS source runs discovered: {len(runs)}")
        print(f"Latest source run: {runs[-1].run_id}")
        print(f"Sleep core records: {len(sleep_doc['records'])}")
        print(f"Heart core records: {len(heart_doc['records'])}")
        print(f"Latest observation day: {latest_day}")
        print(f"Baseline freshness: {status['baseline_freshness']}")
        print(f"Canonical write executed: {'YES' if not args.validate_only else 'NO'}")
        print("AI interpretation executed: NO")
        return 0
    except Exception as exc:
        status = {
            "status": "FAIL",
            "started_at_utc": started.isoformat(),
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "canonical_write_executed": False,
            "ai_interpretation_executed": False,
        }
        try:
            write_status(status)
        except Exception:
            pass
        print(f"Refresh: FAIL — {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
