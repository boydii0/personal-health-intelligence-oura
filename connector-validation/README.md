# Oura Connector Validation + Phase B Backfill (PHI project)

This directory contains the bounded local Oura connector used by the Personal
Health Intelligence project. It is designed to run on the same computer as the
browser used to approve Oura access because the OAuth callback is
`http://localhost:8000/callback`.

The public GitHub repository contains connector code/documentation only. Raw
health data, credentials, access tokens, refresh tokens, and vault exports do
not belong here.

## Current governed phases

### Phase A — COMPLETE / validated 2026-08-16

`run_validation.py`

Purpose: prove the registered Oura OAuth2 application can authenticate, pull a
small 7-day `daily_sleep` sample, land it losslessly in the canonical PHI
repository, create provenance/checksum metadata, and support manual comparison
against the Oura app.

### Phase B — IMPLEMENTED / local execution validation pending

`run_phase_b.py`

Purpose: expand the already-validated mechanism without adding unattended
automation or broader OAuth permissions.

It performs one bounded **30-day** retrieval for these `daily`-scope datasets:

- `daily_sleep` — `/v2/usercollection/daily_sleep`
- `sleep` — `/v2/usercollection/sleep`
- `daily_readiness` — `/v2/usercollection/daily_readiness`
- `daily_activity` — `/v2/usercollection/daily_activity`

The runner follows Oura pagination with a hard page cap, then writes one raw
JSON artifact and one metadata sidecar per dataset under:

```text
<VAULT_ROOT>/03_Areas/Health/Personal Health Repository/Source Data/Oura/<YYYY-MM-DD>/
  daily_sleep.json
  daily_sleep.metadata.json
  sleep.json
  sleep.metadata.json
  daily_readiness.json
  daily_readiness.metadata.json
  daily_activity.json
  daily_activity.metadata.json
```

The metadata records retrieval time, endpoint, requested date range, granted
scope, source record IDs, record count, pages fetched, and SHA-256 checksum.
No normalization or medical interpretation occurs during raw landing.

## Setup

```bash
cd connector-validation
cp .env.example .env
```

Edit `.env` locally in your own editor. Never paste real values into chat:

```text
OURA_CLIENT_ID=<from cloud.ouraring.com/oauth/applications>
OURA_CLIENT_SECRET=<from cloud.ouraring.com/oauth/applications>
OURA_REDIRECT_URI=http://localhost:8000/callback
OURA_SCOPE=daily
VAULT_ROOT=/absolute/path/to/your/AI_Vault
```

`VAULT_ROOT` must directly contain `00_System`, `01_Daily`, `02_Projects`,
`03_Areas`, `04_People`, `05_Resources`, and `06_Memory`.

No `pip install` is required; the connector uses Python standard-library
modules only.

## Run Phase A

```bash
python run_validation.py
```

Use this only when re-checking the original connectivity slice.

## Run Phase B

```bash
python run_phase_b.py
```

Expected sequence:

1. The script starts the localhost OAuth callback listener.
2. Your default browser opens Oura authorization.
3. Authenticate locally (including passkey if offered by Oura/browser).
4. The authorization code returns to the local Python process.
5. The script retrieves the four approved datasets for the bounded 30-day
   range and follows pagination up to the configured hard cap.
6. Each successful dataset is landed separately in the canonical Oura raw
   folder with provenance/checksum metadata.
7. The script reports PASS/PARTIAL/FAIL and stops.
8. Manually compare representative records against Oura before treating the
   backfill as semantically validated. Pay special attention to detailed sleep
   session boundaries and the HRV/resting-heart-rate fields that will feed the
   next normalization step.

If any dataset fails or pagination reaches the hard cap, the run is incomplete.
Do not normalize or generate insights from that run until the failure is
resolved and the bounded retrieval is repeated successfully.

## Current stop conditions

Phase B deliberately does **not** implement:

- `heartrate`, `workout`, or `spo2Daily` OAuth-scope expansion;
- HRV/resting-heart-rate normalization;
- normalized Health Core writes;
- weekly/monthly/semiannual insight generation;
- token or refresh-token persistence;
- incremental synchronization;
- webhooks;
- cron, scheduled jobs, or GitHub Actions;
- Personal Health App code;
- medical interpretation.

Those remain separate governed steps.

## Security notes

- Client secret and OAuth tokens remain local/in-memory and must never be
  committed or copied into `AI_Vault`.
- `.gitignore` blocks `.env`, token/credential files, and raw Oura JSON.
- `SecretGuard` redacts known secret values from propagated exception text.
- The canonical raw-data destination is the restricted health-repository
  subtree in `AI_Vault`; the script refuses to invent an alternate persistent
  location if `VAULT_ROOT` is invalid.
- If a secret ever appears in output, logs, generated files, or Git history,
  stop and rotate the credential in the Oura developer portal.

## Code locations

```text
connector-validation/
├── run_validation.py                  # Phase A 7-day validation runner
├── run_phase_b.py                     # Phase B bounded 30-day runner
├── .env.example                       # non-secret local config template
└── src/oura_connector/
    ├── config.py                       # local environment/config validation
    ├── oauth_flow.py                   # localhost OAuth authorization flow
    ├── oura_api.py                     # bounded API + pagination helpers
    ├── raw_landing.py                  # canonical raw/provenance landing
    └── secure_utils.py                 # secret redaction guard
```

## Reference

- Oura API V2 base: `https://api.ouraring.com/v2`
- OAuth authorize: `https://cloud.ouraring.com/oauth/authorize`
- OAuth token: `https://api.ouraring.com/oauth/token`
