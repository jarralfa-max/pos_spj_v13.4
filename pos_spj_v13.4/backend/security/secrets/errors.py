"""Canonical secret-store errors — SHELL-1 security foundation."""
from __future__ import annotations


class SecretStoreUnavailableError(RuntimeError):
    """The backing secret store (OS credential vault or encrypted local
    store) could not be reached or written to. Callers must treat this as
    fatal for the operation in progress — never silently fall back to
    storing the secret in plaintext."""


class SecretNotFoundError(KeyError):
    """No secret is registered under the requested name."""
