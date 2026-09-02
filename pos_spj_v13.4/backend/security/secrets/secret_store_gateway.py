"""SecretStoreGateway port — SHELL-1 security foundation.

Contract for every secret-store backend (Windows Credential Manager,
encrypted local fallback, and — when needed — macOS Keychain / Linux Secret
Service). The gateway is deliberately split into two access levels:

  * `describe()` / `list_references()` return a `SecretReference` — safe to
    hand to the UI (masked value only).
  * `get_secret()` returns the raw secret and is for backend/service code
    that needs the actual value to call an external API. The UI must never
    call this.

Nothing in this module stores or logs a raw secret value.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


def mask_secret(value: str, *, visible: int = 4) -> str:
    """Render a secret as a display-safe masked string, e.g. `sk_live_***abcd`.

    Never returns enough of the original value to reconstruct it.
    """
    if not value:
        return ""
    if len(value) <= visible:
        return "*" * len(value)
    return ("*" * (len(value) - visible)) + value[-visible:]


@dataclass(frozen=True)
class SecretReference:
    """UI-safe description of a stored secret. Never carries the raw value."""

    reference_id: str
    masked_value: str
    last_rotated_at: str
    status: str  # "ACTIVE" | "ROTATED" | "REVOKED"


@runtime_checkable
class SecretStoreGateway(Protocol):
    def set_secret(self, name: str, value: str) -> SecretReference:
        """Create or overwrite a secret. Returns a masked reference only."""
        ...

    def get_secret(self, name: str) -> str | None:
        """Return the raw secret value for backend use, or None if absent.
        Never call this from UI code."""
        ...

    def describe(self, name: str) -> SecretReference | None:
        """Return the UI-safe reference for a secret, or None if absent."""
        ...

    def rotate_secret(self, name: str, new_value: str) -> SecretReference:
        """Replace a secret's value, bumping `last_rotated_at`."""
        ...

    def delete_secret(self, name: str) -> None:
        """Permanently remove a secret. No-op if it does not exist."""
        ...

    def list_references(self) -> list[SecretReference]:
        """List every stored secret as UI-safe references."""
        ...
