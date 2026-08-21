#!/usr/bin/env python3
"""Phase C unattended-safe Oura source sync — manual validation entry point.

No browser interaction occurs. The worker uses the DPAPI-protected token
bundle, rotates single-use refresh tokens when needed, retrieves the four
owner-validated daily-scope datasets over a 7-day overlap window, and
publishes one append-oriented run snapshot into the canonical Oura source
folder only when all datasets succeed.

This script does NOT schedule itself, use webhooks, normalize data, or generate
health insights. Windows Task Scheduler remains disabled until this command
passes local owner validation.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from oura_connector.config import ConfigError, load_config  # noqa: E402
from oura_connector.oauth_flow import OAuthError  # noqa: E402
from oura_connector.runtime_landing import RuntimeLandingError  # noqa: E402
from oura_connector.runtime_lock import RuntimeLock, RuntimeLockError  # noqa: E402
from oura_connector.runtime_status import RuntimeStatusError, write_runtime_status  # noqa: E402
from oura_connector.runtime_sync import RuntimeSyncError, execute_sync  # noqa: E402
from oura_connector.runtime_tokens import (  # noqa: E402
    TokenStoreError,
    default_runtime_dir,
    default_windows_token_store,
)


def _safe_status(runtime_dir: Path, payload: dict) -> None:
    try:
        write_runtime_status(runtime_dir, payload)
    except RuntimeStatusError:
        pass


def main() -> int:
    print("Oura Phase C — noninteractive source sync")
    try:
        config = load_config(PROJECT_ROOT)
        runtime_dir = default_runtime_dir()
        store = default_windows_token_store()
    except (ConfigError, TokenStoreError) as exc:
        print(f"Preflight: FAIL — {exc}")
        return 1

    lock = RuntimeLock(runtime_dir / "runtime.lock")
    try:
        with lock:
            result = execute_sync(config, store, overlap_days=7)
    except (
        RuntimeLockError,
        RuntimeSyncError,
        RuntimeLandingError,
        TokenStoreError,
        OAuthError,
    ) as exc:
        _safe_status(
            runtime_dir,
            {
                "operation": "sync",
                "status": "FAIL",
                "error": str(exc),
                "tokens_in_ai_vault": False,
            },
        )
        print(f"Sync: FAIL — {exc}")
        return 1

    _safe_status(
        runtime_dir,
        {
            "operation": "sync",
            "status": "PASS",
            "requested_start_date": result.start_date,
            "requested_end_date": result.end_date,
            "token_refreshed": result.token_refreshed,
            "auth_retry_used": result.auth_retry_used,
            "dataset_record_counts": result.dataset_record_counts,
            "run_id": result.landing.run_id,
            "run_dir": result.landing.run_dir,
            "tokens_in_ai_vault": False,
        },
    )

    print("Sync: PASS")
    print(f"Window: {result.start_date} through {result.end_date}")
    print(f"Token refreshed this run: {result.token_refreshed}")
    print(f"401 recovery path used: {result.auth_retry_used}")
    for name, count in result.dataset_record_counts.items():
        print(f"{name}: {count} records")
    print(f"Published run: {result.landing.run_dir}")
    print(f"Manifest: {result.landing.manifest_path}")
    print("Secrets written to AI_Vault: NO")
    print("Normalization executed: NO")
    print("Scheduling executed: NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
