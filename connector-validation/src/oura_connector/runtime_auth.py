from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Callable

from .config import OuraConfig
from .oauth_flow import OAuthError, TokenResult, run_authorization_code_flow
from .runtime_tokens import ProtectedTokenStore, TokenBundle
from .secure_utils import SecretGuard

TOKEN_URL = "https://api.ouraring.com/oauth/token"


def bundle_from_result(result: TokenResult, now: datetime | None = None) -> TokenBundle:
    anchor = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    expires_at = anchor + timedelta(seconds=result.expires_in)
    return TokenBundle(result.access_token, result.refresh_token, expires_at.isoformat(), result.scope_granted)


def authorize_and_persist(config: OuraConfig, store: ProtectedTokenStore, *, authorize_fn: Callable[[OuraConfig], TokenResult] = run_authorization_code_flow) -> TokenBundle:
    result = authorize_fn(config)
    if not result.refresh_token:
        raise OAuthError("Oura authorization returned no refresh token; Phase C cannot continue unattended.")
    bundle = bundle_from_result(result)
    store.save(bundle)
    return bundle


def refresh_access_token(config: OuraConfig, refresh_token: str) -> TokenResult:
    """Exchange one single-use Oura refresh token for a new token pair."""
    if not refresh_token:
        raise OAuthError("No refresh token is available.")
    fields = {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": config.client_id, "client_secret": config.client_secret}
    with SecretGuard(refresh_token, config.client_secret):
        request = urllib.request.Request(TOKEN_URL, data=urllib.parse.urlencode(fields).encode("utf-8"), headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                import json
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise OAuthError(f"Refresh-token exchange failed with HTTP {exc.code}.") from None
        except urllib.error.URLError as exc:
            raise OAuthError(f"Refresh-token exchange failed: {exc.reason}") from None

    access = payload.get("access_token")
    rotated_refresh = payload.get("refresh_token")
    expires_in = int(payload.get("expires_in", 0))
    scope = payload.get("scope", config.scope)
    if not access or not rotated_refresh or expires_in <= 0:
        raise OAuthError("Refresh-token exchange returned an incomplete token bundle.")
    return TokenResult(access_token=access, refresh_token=rotated_refresh, expires_in=expires_in, scope_granted=scope)


def ensure_fresh_token(config: OuraConfig, store: ProtectedTokenStore, *, min_valid_seconds: int = 300, force_refresh: bool = False, refresh_fn: Callable[[OuraConfig, str], TokenResult] = refresh_access_token, now: datetime | None = None) -> tuple[TokenBundle, bool]:
    bundle = store.load()
    anchor = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    remaining = (bundle.expires_at() - anchor).total_seconds()
    if not force_refresh and remaining > min_valid_seconds:
        return bundle, False
    result = refresh_fn(config, bundle.refresh_token)
    new_bundle = bundle_from_result(result, anchor)
    # Oura refresh tokens are single-use; persist the rotated token before data retrieval.
    store.save(new_bundle)
    return new_bundle, True
