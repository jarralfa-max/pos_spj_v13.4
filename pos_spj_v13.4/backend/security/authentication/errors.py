"""Canonical authentication errors — SHELL-7 §75."""
from __future__ import annotations


class AuthenticationFailedError(RuntimeError):
    """Generic, deliberately non-specific failure — never reveals whether
    the username existed, whether the password was wrong, or whether the
    account is inactive. Callers show the same message either way."""
