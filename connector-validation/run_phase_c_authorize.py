#!/usr/bin/env python3
"""Phase C one-time/recovery authorization for the Oura unattended runtime.

This is the only Phase C command that opens a browser. It stores the returned
access/refresh token pair under the current Windows user using DPAPI. Tokens
are not stored in AI_Vault, GitHub, logs, or terminal output.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from oura_connector.config import ConfigError, load_config  # noqa: E402
from oura_connector.oauth_flow import OAuthError  # noqa: E402
from oura_connector.runtime_auth import authorize_and_persist  # noqa: E402
from oura_connector.runtime_status import write_runtime_status  # noqa: E402
from oura_connector.runtime_tokens import (  # noqa: E402
    TokenStoreError,
    default_runtime_dir,
    default_windows_token_store,
)


def main() -> int:
    print("Oura Phase C — secure runtime authorization")
    try:
        config = load_config(PROJECT_ROOT)
        runtime_dir = default_runtime_dir()
        store = default_windows_token_store()
        bundle = authorize_and_persist(config, store)
        write_runtime_status(
            runtime_dir,
            {
                "operation": "authorize",
                "status": "PASS",
                "scope_granted": bundle.scope_granted,
                "token_store": "Windows DPAPI",
                "tokens_in_ai_vault": False,
            },
        )
    except (ConfigError, OAuthError, TokenStoreError) as exc:
        print(f"Authorization: FAIL — {exc}")
        return 1

    print("Authorization: PASS")
    print(f"Granted scope: {bundle.scope_granted}")
    print("Token persistence: PASS — protected with Windows DPAPI")
    print(f"Runtime state directory: {runtime_dir}")
    print("Secrets written to AI_Vault: NO")
    print("Next step: run `python run_phase_c_sync.py` manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
