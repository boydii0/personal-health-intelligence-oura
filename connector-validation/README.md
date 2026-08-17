# Oura Connector Validation Test (PHI project)

Standalone, dependency-free Python script that proves the registered Oura
OAuth2 application can authenticate, pull a small bounded sample of your own
`daily_sleep` data, and land it losslessly as a raw source artifact in the
canonical PHI repository path. Nothing more.

This is execution of the already-approved Oura connector validation step
(step 4 of the v0.1 build sequence). It does not create any new durable
architectural decision and does not modify PHI governance, architecture,
decision logs, or templates.

## Why this must run on your own machine, not in a cloud AI session

The registered redirect URI is `http://localhost:8000/callback`. That only
resolves back to this script if the browser completing the Oura consent
screen and the process listening on port 8000 are the **same machine**. A
cloud-hosted assistant session cannot receive that redirect. Run this
locally.

## What this script does (and only this)

1. **Phase 1 — OAuth2 Authorization Code flow.** Starts a temporary local
   listener on `http://localhost:8000/callback`, opens the Oura authorize
   URL in your browser, exchanges the returned code for an access token —
   all in one process, in memory. Tokens are never written to disk, printed,
   or logged.
2. **Phase 2 — one bounded API call.** `GET /v2/usercollection/daily_sleep`
   for the most recent 7 days. Reports HTTP status, scope granted, record
   count, and whether pagination was present. Never prints token values.
3. **Phase 3 — raw landing.** Only if Phase 2 returns HTTP 200: writes the
   exact raw response bytes and a provenance/metadata file (retrieved_at,
   source, endpoint, requested date range, source record IDs, SHA-256
   checksum) under:
   ```
   <VAULT_ROOT>/03_Areas/Health/Personal Health Repository/Source Data/Oura/<YYYY-MM-DD>/
     daily_sleep.json
     daily_sleep.metadata.json
   ```
   No transformation or normalization happens here.
4. **Phase 4 — manual UI comparison.** Prints the retrieved dates/scores so
   you can eyeball them against the Oura app for 3-5 days, then records your
   PASS / PARTIAL / FAIL judgment. No medical interpretation is performed by
   the script.
5. **Phase 5 — hard stop.** The script has no code paths for backfill (30-90
   day), detailed `/sleep` parsing, HRV/RHR normalization, webhook
   subscriptions, scheduling, GitHub Actions, or PHI application logic. Those
   require a separate, explicitly approved step.

## Setup

```bash
cd oura_phi_validation
cp .env.example .env
```

Edit `.env` **locally, in your own editor** — never paste real values into a
chat window with any AI assistant:

```
OURA_CLIENT_ID=<from cloud.ouraring.com/oauth/applications>
OURA_CLIENT_SECRET=<from cloud.ouraring.com/oauth/applications>
OURA_REDIRECT_URI=http://localhost:8000/callback
OURA_SCOPE=daily
VAULT_ROOT=/absolute/path/to/your/local/AI_Vault
```

`VAULT_ROOT` must be the folder that directly contains `00_System`,
`01_Daily`, `02_Projects`, `03_Areas`, `04_People`, `05_Resources`,
`06_Memory`. The script refuses to write anywhere else and will report the
constraint instead of guessing a location if this is missing or wrong.

No `pip install` is required — everything uses the Python standard library
(`http.server`, `urllib`, `webbrowser`, `hashlib`, `json`).

## Run

```bash
python run_validation.py
```

Your browser opens to Oura's consent screen. Approve access, and the script
completes automatically. At the end it prints a report in this format:

```
Oura Connector Validation
OAuth authorization: PASS / FAIL
Token exchange: PASS / FAIL
API endpoint: /v2/usercollection/daily_sleep
HTTP status: ...
Scope granted: ...
Date range: ...
Records returned: ...
Raw file written to: ...
Raw checksum created: YES / NO
Oura UI comparison: PASS / PARTIAL / FAIL
Credential leakage detected: NO
GitHub health data committed: NO
Errors / limitations: ...
Recommended next step: ...
```

## Security notes

- Client ID/Secret and tokens are read only from your local `.env` /
  environment — never typed into a chat window, never logged, never
  committed. `.gitignore` in this project blocks `.env`, token/credential
  files, and any raw Oura JSON from ever being committed.
- `secure_utils.SecretGuard` scrubs known secret values out of exception
  messages before they can propagate to the terminal, as a defense-in-depth
  measure.
- If a Client Secret, access token, or refresh token ever appears in
  terminal output, logs, a generated file, or Git history, stop immediately,
  rotate the credential in the Oura developer portal, and treat it as
  compromised — do not just delete the output.
- This repository (`boydii0/personal-health-intelligence-oura`) is public.
  Only non-sensitive documentation and connector source code belong here.
  Raw Oura data, vault exports, and credentials never do.

## Scope boundaries (do not extend without separate approval)

- No 30-90 day backfill
- No detailed `/v2/usercollection/sleep` parsing or HRV/RHR normalization
- No webhook subscriptions
- No scheduling, cron, or GitHub Actions
- No PHI application server/code
- No reports, insights, or supplement correlation
- No medical interpretation of any retrieved value

## Reference

- Oura API V2 base: `https://api.ouraring.com/v2`
- OAuth authorize: `https://cloud.ouraring.com/oauth/authorize`
- OAuth token: `https://api.ouraring.com/oauth/token`
- Personal Access Tokens are deprecated; OAuth2 authorization-code flow is
  required even for single-user personal use.
