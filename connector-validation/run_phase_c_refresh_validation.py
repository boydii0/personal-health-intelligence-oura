#!/usr/bin/env python3
"""Phase C controlled Oura refresh-token rotation validation.

This command deliberately forces exactly one OAuth refresh-token exchange,
verifies that the returned single-use refresh token was rotated and persisted
through the Windows DPAPI token store, then stops. It never prints token values,
writes secrets to AI_Vault, retrieves health data, normalizes data, or schedules
anything.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from oura_connector.config import ConfigError, load_config  # noqa: E402
from oura_connector.oauth_flow import OAuthError  # noqa: E402
from oura_connector.runtime_auth import ensure_fresh_token  # noqa: E402
from oura_connector.runtime_tokens import (  # noqa: E402
    TokenStoreError,
    default_runtime_dir,
    default_windows_token_store,
)


def main() -> int:
    print("Oura Phase C — controlled refresh-token rotation validation")
    try:
        config = load_config(PROJECT_ROOT)
        store = default_windows_token_store()
        before = store.load()
        after, refreshed = ensure_fresh_token(config, store, force_refresh=True)
        readback = store.load()
    except (ConfigError, TokenStoreError, OAuthError) as exc:
        print(f"Refresh validation: FAIL — {exc}")
        return 1

    refresh_rotated = bool(after.refresh_token) and after.refresh_token != before.refresh_token
    access_replaced = bool(after.access_token) and after.access_token != before.access_token
    persisted = (
        readback.access_token == after.access_token
        and readback.refresh_token == after.refresh_token
        and readback.expires_at_utc == after.expires_at_utc
        and readback.scope_granted == after.scope_granted
    )

    if not refreshed or not refresh_rotated or not persisted:
        print("Refresh validation: FAIL — rotation/persistence invariant was not satisfied.")
        print(f"Refresh exchange executed: {'YES' if refreshed else 'NO'}")
        print(f"Refresh token rotated: {'YES' if refresh_rotated else 'NO'}")
        print(f"DPAPI persistence read-back: {'PASS' if persisted else 'FAIL'}")
        return 1

    print("Refresh validation: PASS")
    print("Refresh exchange executed: YES")
    print("Refresh token rotated: YES")
    print(f"Access token replaced: {'YES' if access_replaced else 'NO'}")
    print("DPAPI persistence read-back: PASS")
    print(f"Runtime state directory: {default_runtime_dir()}")
    print("Token values displayed: NO")
    print("Secrets written to AI_Vault: NO")
    print("Health data retrieved: NO")
    print("Normalization executed: NO")
    print("Scheduling executed: NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
