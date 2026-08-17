"""
Oura OAuth2 Authorization Code flow — connectivity test only.

This module:
  1. Starts a temporary local HTTP listener on http://localhost:8000/callback
  2. Opens the Oura authorization URL in the default browser
  3. Waits for exactly one callback carrying an authorization code
  4. Exchanges the code for an access_token + refresh_token
  5. Returns those tokens to the caller IN MEMORY ONLY — nothing here writes
     tokens to disk, prints them, or logs them.

Personal Access Tokens are deprecated; this is the only supported flow
(authorization-code + refresh) as of the current Oura developer docs.

Scope: this file implements Phase 1 only. It does not implement webhook
subscriptions, refresh-token persistence, or any scheduling.
"""
from __future__ import annotations

import http.server
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from typing import Optional

from .config import OuraConfig
from .secure_utils import SecretGuard

AUTHORIZE_URL = "https://cloud.ouraring.com/oauth/authorize"
TOKEN_URL = "https://api.ouraring.com/oauth/token"
CALLBACK_HOST = "localhost"
CALLBACK_PORT = 8000
CALLBACK_TIMEOUT_SECONDS = 180


class OAuthError(RuntimeError):
    """Raised on any OAuth failure. Messages never contain secret values."""


@dataclass(frozen=True)
class TokenResult:
    access_token: str
    refresh_token: str
    expires_in: int
    scope_granted: str

    def secrets(self) -> tuple:
        return (self.access_token, self.refresh_token)


class _CallbackState:
    def __init__(self) -> None:
        self.code: Optional[str] = None
        self.error: Optional[str] = None
        self.received = threading.Event()


def _make_handler(expected_state: str, state_holder: _CallbackState):
    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # silence default request logging
            return

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return

            params = urllib.parse.parse_qs(parsed.query)
            returned_state = params.get("state", [None])[0]
            error = params.get("error", [None])[0]
            code = params.get("code", [None])[0]

            body = b"You can close this tab and return to the terminal."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

            if error:
                state_holder.error = error
            elif returned_state != expected_state:
                state_holder.error = "state_mismatch"
            elif not code:
                state_holder.error = "no_authorization_code_returned"
            else:
                state_holder.code = code
            state_holder.received.set()

    return CallbackHandler


def run_authorization_code_flow(config: OuraConfig) -> TokenResult:
    """Run Phase 1 end to end. Must be executed on the same machine as the
    browser that completes the Oura consent screen, because the redirect
    target is http://localhost:8000/callback."""

    state = secrets.token_urlsafe(24)
    callback_state = _CallbackState()
    handler_cls = _make_handler(state, callback_state)

    server = http.server.HTTPServer((CALLBACK_HOST, CALLBACK_PORT), handler_cls)
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    query = urllib.parse.urlencode(
        {
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "response_type": "code",
            "scope": config.scope,
            "state": state,
        }
    )
    authorize_url = f"{AUTHORIZE_URL}?{query}"

    print("Opening your browser to authorize with Oura...")
    print("If it does not open automatically, visit this URL:")
    print(authorize_url)
    webbrowser.open(authorize_url)

    got_callback = callback_state.received.wait(timeout=CALLBACK_TIMEOUT_SECONDS)
    try:
        server.server_close()
    except Exception:
        pass

    if not got_callback:
        raise OAuthError(
            f"Timed out after {CALLBACK_TIMEOUT_SECONDS}s waiting for the "
            "Oura authorization callback on http://localhost:8000/callback."
        )
    if callback_state.error:
        raise OAuthError(f"Authorization callback reported an error: {callback_state.error}")
    if not callback_state.code:
        raise OAuthError("No authorization code received.")

    return _exchange_code_for_tokens(config, callback_state.code)


def _exchange_code_for_tokens(config: OuraConfig, code: str) -> TokenResult:
    with SecretGuard(config.client_secret):
        data = urllib.parse.urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config.redirect_uri,
                "client_id": config.client_id,
                "client_secret": config.client_secret,
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = _read_json(response)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise OAuthError(
                f"Token exchange failed with HTTP {exc.code}: {body[:500]}"
            ) from None
        except urllib.error.URLError as exc:
            raise OAuthError(f"Token exchange request failed: {exc.reason}") from None

    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token", "")
    expires_in = int(payload.get("expires_in", 0))
    scope_granted = payload.get("scope", config.scope)

    if not access_token:
        raise OAuthError("Token exchange succeeded but no access_token was returned.")

    return TokenResult(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        scope_granted=scope_granted,
    )


def _read_json(response):
    import json

    raw = response.read().decode("utf-8")
    return json.loads(raw)
