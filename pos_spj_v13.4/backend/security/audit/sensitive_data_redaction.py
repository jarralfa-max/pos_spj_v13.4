"""SensitiveDataRedactionPolicy — SHELL-1 security foundation.

A safety net for structured logging and audit payloads: recursively masks
known-sensitive keys (`password`, `pin`, `token`, `api_key`, `authorization`,
`secret`, `card_data`, and close variants) so a stray `logger.info(payload)`
somewhere in the codebase can never leak a credential into log files.

This is a backstop, not a substitute for not logging secrets in the first
place — callers should still avoid passing raw credentials into logging
calls. `SensitiveDataRedactionFilter` wires this into the stdlib `logging`
module so it applies even when a call site gets it wrong.
"""
from __future__ import annotations

import logging
import re
from typing import Any

_SENSITIVE_KEY_FRAGMENTS = (
    "password", "contraseña", "contrasena", "pwd", "passwd",
    "pin",
    "token",
    "api_key", "apikey",
    "authorization", "auth_header", "bearer",
    "secret",
    "card_data", "card_number", "cvv", "cvc",
    "client_secret",
)

_REDACTED = "***REDACTED***"

# Matches `key: value` / `key=value` / `"key": "value"` style fragments in
# freeform text, so a sensitive value embedded in a formatted log message
# (not a dict) also gets masked.
_INLINE_PATTERN = re.compile(
    r"""(?i)\b(""" + "|".join(re.escape(f) for f in _SENSITIVE_KEY_FRAGMENTS) + r""")
        (["']?\s*[:=]\s*["']?)
        ([^\s"',}]+)
    """,
    re.VERBOSE,
)


def _is_sensitive_key(key: Any) -> bool:
    key_lower = str(key or "").lower()
    return any(fragment in key_lower for fragment in _SENSITIVE_KEY_FRAGMENTS)


def redact_mapping(data: Any) -> Any:
    """Recursively redact sensitive values in dicts/lists. Non-container
    values pass through unchanged; the input is never mutated in place."""
    if isinstance(data, dict):
        return {
            key: (_REDACTED if _is_sensitive_key(key) else redact_mapping(value))
            for key, value in data.items()
        }
    if isinstance(data, (list, tuple)):
        redacted = [redact_mapping(item) for item in data]
        return type(data)(redacted) if isinstance(data, tuple) else redacted
    return data


def redact_text(text: str) -> str:
    """Redact `key=value`/`key: value` sensitive fragments inside a freeform
    string, e.g. a formatted log message."""
    if not text:
        return text
    return _INLINE_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}{_REDACTED}", text)


class SensitiveDataRedactionFilter(logging.Filter):
    """A `logging.Filter` that redacts `record.msg`/`record.args` in place.

    Attach to a handler or logger:
        handler.addFilter(SensitiveDataRedactionFilter())
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if isinstance(record.msg, dict):
            record.msg = redact_mapping(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = redact_mapping(record.args)
            else:
                record.args = tuple(
                    redact_text(a) if isinstance(a, str) else redact_mapping(a)
                    for a in record.args
                )
        return True
