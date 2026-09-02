"""PasswordPolicy — SHELL-1 security foundation.

Pure validation logic: no DB access, no hashing. Given a candidate password
(and optionally the owning username, for the "username in password" check),
`validate()` either returns silently or raises `PasswordPolicyViolationError`
listing every rule that failed.
"""
from __future__ import annotations

import string
from dataclasses import dataclass, field

from backend.security.credentials.errors import PasswordPolicyViolationError

# Small, deliberately-scoped blocklist — not an exhaustive breached-password
# corpus, just the handful of defaults this codebase has actually shipped
# (admin123, demo, 1234, etc.) plus the most common English/Spanish picks.
_COMMON_PASSWORDS = frozenset(
    {
        "12345678", "123456789", "1234567890", "password", "contraseña",
        "admin123", "admin1234", "qwerty123", "letmein123", "welcome123",
        "abc12345", "password1", "iloveyou1", "changeme1", "administrador",
    }
)


@dataclass(frozen=True)
class PasswordPolicy:
    minimum_length: int = 12
    maximum_length: int = 128
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_number: bool = True
    require_symbol: bool = True
    prevent_common_passwords: bool = True
    prevent_username_in_password: bool = True
    password_history_count: int = 5
    failed_attempt_limit: int = 5
    lockout_duration_seconds: int = 900

    def validate(self, password: str, *, username: str = "") -> None:
        violations = self._collect_violations(password, username=username)
        if violations:
            raise PasswordPolicyViolationError(violations)

    def is_valid(self, password: str, *, username: str = "") -> bool:
        return not self._collect_violations(password, username=username)

    def _collect_violations(self, password: str, *, username: str) -> list[str]:
        password = password or ""
        violations: list[str] = []

        if len(password) < self.minimum_length:
            violations.append(
                f"Debe tener al menos {self.minimum_length} caracteres."
            )
        if len(password) > self.maximum_length:
            violations.append(
                f"No debe superar {self.maximum_length} caracteres."
            )
        if self.require_uppercase and not any(c.isupper() for c in password):
            violations.append("Debe incluir al menos una letra mayúscula.")
        if self.require_lowercase and not any(c.islower() for c in password):
            violations.append("Debe incluir al menos una letra minúscula.")
        if self.require_number and not any(c.isdigit() for c in password):
            violations.append("Debe incluir al menos un número.")
        if self.require_symbol and not any(c in string.punctuation for c in password):
            violations.append("Debe incluir al menos un símbolo (p. ej. !@#$%).")
        if self.prevent_common_passwords and password.lower() in _COMMON_PASSWORDS:
            violations.append("Es una contraseña de uso común; elija otra.")
        if self.prevent_username_in_password and username:
            uname = username.strip().lower()
            if uname and uname in password.lower():
                violations.append("No debe contener el nombre de usuario.")

        return violations


DEFAULT_PASSWORD_POLICY = PasswordPolicy()
