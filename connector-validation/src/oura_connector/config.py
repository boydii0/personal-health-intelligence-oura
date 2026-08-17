"""
Configuration loader. Reads credentials and paths from environment variables
only. Never logs, prints, or returns secret values in any repr/str form that
could be accidentally printed by a caller.

A minimal, dependency-free .env loader is included so this project needs no
pip install to run. If a real .env file is present next to this project, its
values are loaded into os.environ (without overriding variables the caller
already exported in their shell).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class OuraConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    scope: str
    vault_root: str

    def secrets(self) -> tuple:
        """Return the tuple of secret values for redaction purposes only.
        Callers must never print, log, or serialize this tuple's contents."""
        return (self.client_secret,)


class ConfigError(RuntimeError):
    """Raised when required configuration is missing. Message text never
    contains a secret value — only the names of missing variables."""


def load_config(project_root: Path) -> OuraConfig:
    _load_dotenv(project_root / ".env")

    client_id = os.environ.get("OURA_CLIENT_ID", "").strip()
    client_secret = os.environ.get("OURA_CLIENT_SECRET", "").strip()
    redirect_uri = os.environ.get("OURA_REDIRECT_URI", "http://localhost:8000/callback").strip()
    scope = os.environ.get("OURA_SCOPE", "daily").strip()
    vault_root = os.environ.get("VAULT_ROOT", "").strip()

    missing = [
        name
        for name, value in (
            ("OURA_CLIENT_ID", client_id),
            ("OURA_CLIENT_SECRET", client_secret),
            ("VAULT_ROOT", vault_root),
        )
        if not value
    ]
    if missing:
        raise ConfigError(
            "Missing required configuration: "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill in real values locally. "
            "Do not paste these into chat with any AI assistant."
        )

    if redirect_uri != "http://localhost:8000/callback":
        raise ConfigError(
            "OURA_REDIRECT_URI must be exactly http://localhost:8000/callback "
            "for this validation test (it must match the redirect URI "
            "registered on the Oura application)."
        )

    if scope != "daily":
        raise ConfigError(
            "This validation test is scoped to the 'daily' permission only. "
            "Requesting heartrate/workout/spo2Daily requires a separate "
            "approved step. Set OURA_SCOPE=daily to proceed."
        )

    return OuraConfig(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=scope,
        vault_root=vault_root,
    )
