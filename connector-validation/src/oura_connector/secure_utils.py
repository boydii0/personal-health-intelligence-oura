"""
Defense-in-depth helpers for keeping secret material out of anything that
could be printed, logged, written to disk, or committed.

These do not replace correct handling elsewhere in the codebase; they are a
last-resort net so that even a bug in another module cannot leak a token into
terminal output or an exception message.
"""
from __future__ import annotations

from typing import Iterable


def redact(text: str, secrets: Iterable[str]) -> str:
    """Return `text` with every non-empty value in `secrets` replaced by a
    fixed placeholder. Safe to call even if some values are None/empty."""
    out = text
    for value in secrets:
        if value:
            out = out.replace(value, "[REDACTED]")
    return out


class SecretGuard:
    """Context manager that redacts known secret values out of any exception
    message before it propagates, so tracebacks never contain raw secrets.

    Usage:
        with SecretGuard(client_secret, access_token, refresh_token):
            ... risky code ...
    """

    def __init__(self, *secrets: str) -> None:
        self._secrets = [s for s in secrets if s]

    def __enter__(self) -> "SecretGuard":
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is not None and self._secrets:
            try:
                cleaned_args = tuple(
                    redact(str(a), self._secrets) if isinstance(a, str) else a
                    for a in exc.args
                )
                exc.args = cleaned_args
            except Exception:
                # If redaction itself fails, fall back to a generic message
                # rather than risk leaking the original exception text.
                exc.args = ("[REDACTED EXCEPTION — secret material scrubbed]",)
        return False  # never suppress the exception, just sanitize it
