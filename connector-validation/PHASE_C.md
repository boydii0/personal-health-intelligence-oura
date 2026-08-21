# Phase C — Oura Durable Runtime Foundation

**Status:** implementation candidate; local owner validation required before scheduling.

This phase operationalizes the already validated Oura daily-scope retrieval path on
the owner's always-on Windows PC. It does **not** expand Oura permissions and it
does not enable Windows Task Scheduler or webhooks yet.

## Approved boundary

Phase C v0.1 may:

- persist OAuth access/refresh tokens outside `AI_Vault` using Windows DPAPI;
- rotate Oura's single-use refresh token and persist the newly returned token immediately;
- retrieve only the already validated `daily`-scope datasets: `daily_sleep`, `sleep`, `daily_readiness`, and `daily_activity`;
- poll a seven-day overlap window;
- retry bounded transient failures and honor `Retry-After` for HTTP 429;
- force exactly one token refresh/retry on HTTP 401;
- publish only complete four-dataset runs;
- write append-oriented raw snapshots with checksums and provenance to the canonical Oura source folder;
- prevent overlapping worker executions;
- write non-PHI operational status outside the vault.

Phase C v0.1 may **not**:

- request `heartrate`, `workout`, `spo2Daily`, or other new scopes;
- write OAuth secrets/tokens to GitHub, `AI_Vault`, or logs;
- use webhooks;
- schedule itself;
- normalize data or generate health insights;
- delete or overwrite prior raw source snapshots.

## Windows locations

Local canonical vault root used by the owner:

```text
C:\Users\boydi\My Drive\AI_Vault
```

The `.env` remains local and gitignored:

```text
VAULT_ROOT="C:\Users\boydi\My Drive\AI_Vault"
OURA_REDIRECT_URI=http://localhost:8000/callback
OURA_SCOPE=daily
```

Do not place real Client ID, Client Secret, access token, or refresh token in GitHub, chat, or `AI_Vault`.

Runtime secrets/state default to:

```text
%LOCALAPPDATA%\PHI\OuraRuntime\
```

`tokens.dat` is protected with Windows DPAPI under the Windows user account.

## Source landing layout

Phase B wrote one validation snapshot per dataset. Phase C becomes append-oriented because the worker can run repeatedly:

```text
03_Areas/Health/Personal Health Repository/Source Data/Oura/
└── YYYY-MM-DD/
    └── <UTC-run-id>/
        ├── daily_sleep.json
        ├── daily_sleep.metadata.json
        ├── sleep.json
        ├── sleep.metadata.json
        ├── daily_readiness.json
        ├── daily_readiness.metadata.json
        ├── daily_activity.json
        ├── daily_activity.metadata.json
        └── run_manifest.json
```

The run directory is published only after all four datasets and metadata files are written successfully to a staging directory.

## Local validation sequence

From `connector-validation` on the **always-on Windows PC**:

### 1. Check out the Phase C branch

```powershell
git fetch origin
git checkout phase-c-oura-runtime
git pull
```

### 2. Confirm the vault root

```powershell
$env:VAULT_ROOT
Test-Path "C:\Users\boydi\My Drive\AI_Vault"
```

If PowerShell has a stale `VAULT_ROOT`, set the current process value:

```powershell
$env:VAULT_ROOT = "C:\Users\boydi\My Drive\AI_Vault"
```

### 3. Run the synthetic tests

```powershell
python -m unittest discover -s tests -p "test_phase_c_runtime.py" -v
```

Expected: **8 tests PASS**.

### 4. Authorize once and persist the runtime token pair

```powershell
python run_phase_c_authorize.py
```

This is intentionally interactive and opens Oura once. It must report:

```text
Authorization: PASS
Token persistence: PASS — protected with Windows DPAPI
Secrets written to AI_Vault: NO
```

### 5. Close that browser flow and run the worker manually

```powershell
python run_phase_c_sync.py
```

This command must not open a browser. A successful run reports all four datasets, a seven-day overlap window, and one published run directory.

### 6. Validate the landed run

Open the reported folder and confirm:

- four raw JSON files exist;
- four metadata sidecars exist;
- `run_manifest.json` exists;
- manifest status is `PASS`;
- `secrets_written_to_vault` is `false`;
- no access token, refresh token, Client Secret, or `.env` content is present.

## Failure behavior

- No persisted token: stop and instruct operator to run Phase C authorization.
- Access token near expiry: refresh before retrieval.
- HTTP 401: force one refresh, persist the rotated token, restart the complete four-dataset retrieval; a second 401 fails closed.
- HTTP 429: bounded retry using Oura's `Retry-After` where available.
- Network/5xx: bounded retry.
- Partial dataset/pagination cap: fail the run; publish no canonical run folder.
- Vault unavailable: fail; do not redirect PHI elsewhere.
- Concurrent execution: fail on runtime lock.
- Crash-created lock older than two hours: treat as stale and recover.
- Any landing failure: remove staging data and publish no final run.

## Gate before scheduling

Windows Task Scheduler remains **NOT AUTHORIZED** until:

1. synthetic tests PASS on the always-on PC;
2. Phase C authorization PASS;
3. at least one browser-free manual sync PASS;
4. the landed run is owner-verified;
5. token rotation is demonstrated either by an intentional controlled refresh test or by a subsequent run after the access token needs refresh.

Only after that gate should a Task Scheduler definition be created.
