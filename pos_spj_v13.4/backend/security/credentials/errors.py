"""Canonical credential errors — SHELL-1 security foundation."""
from __future__ import annotations


class PasswordDebilError(ValueError):
    """Alias kept for continuity with security/auth.py's naming."""


class PasswordPolicyViolationError(ValueError):
    """Raised when a candidate password fails one or more PasswordPolicy rules.

    `violations` lists every rule that failed (not just the first one) so
    callers can show the user a complete checklist instead of a single
    generic rejection.
    """

    def __init__(self, violations: list[str]) -> None:
        self.violations = list(violations)
        super().__init__("; ".join(self.violations) or "Contraseña inválida.")


class MissingPasswordHashingBackendError(RuntimeError):
    """The argon2-cffi backend is not installed. There is no fallback —
    hashing or verifying a password without a real cryptographic backend
    (plain text, unsalted SHA-256, etc.) is a vulnerability, not an
    acceptable degradation. Fail fast instead."""
