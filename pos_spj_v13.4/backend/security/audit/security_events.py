"""Canonical security event names — SHELL-1 security foundation.

Single source of truth for the Authentication/Recovery/Session event
vocabulary (see the master refactor plan §73 "Autenticación"/"Contexto").
Other SHELL-1 modules (session_manager, account_recovery_service) import
these rather than redefining their own string literals, so every caller —
today's in-process audit_sink and a future EventBus/audit_logs writer —
agrees on the exact event name.

This is a leaf module: it has no dependencies on the rest of the security
package, so importing it never risks a cycle.
"""
from __future__ import annotations

# ── Autenticación ────────────────────────────────────────────────────────────
USER_AUTHENTICATION_SUCCEEDED = "USER_AUTHENTICATION_SUCCEEDED"
USER_AUTHENTICATION_FAILED = "USER_AUTHENTICATION_FAILED"
ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
PASSWORD_CHANGED = "PASSWORD_CHANGED"

# ── Recuperación de cuenta ───────────────────────────────────────────────────
ACCOUNT_RECOVERY_REQUESTED = "ACCOUNT_RECOVERY_REQUESTED"
ACCOUNT_RECOVERY_COMPLETED = "ACCOUNT_RECOVERY_COMPLETED"

# ── Instalación (SHELL-2) ────────────────────────────────────────────────────
INSTALLATION_PROVISIONING_STARTED = "INSTALLATION_PROVISIONING_STARTED"
INSTALLATION_PROVISIONED = "INSTALLATION_PROVISIONED"
INSTALLATION_LOCKED = "INSTALLATION_LOCKED"
INSTALLATION_RECOVERY_STARTED = "INSTALLATION_RECOVERY_STARTED"
INSTALLATION_RECOVERED = "INSTALLATION_RECOVERED"

# ── Sesiones ─────────────────────────────────────────────────────────────────
USER_SESSION_CREATED = "USER_SESSION_CREATED"
USER_SESSION_REVOKED = "USER_SESSION_REVOKED"
USER_SESSION_EXPIRED = "USER_SESSION_EXPIRED"

# ── Secretos ─────────────────────────────────────────────────────────────────
RECOVERY_CODES_ROTATED = "RECOVERY_CODES_ROTATED"

ALL_SECURITY_EVENTS = frozenset(
    {
        USER_AUTHENTICATION_SUCCEEDED,
        USER_AUTHENTICATION_FAILED,
        ACCOUNT_LOCKED,
        PASSWORD_CHANGED,
        ACCOUNT_RECOVERY_REQUESTED,
        ACCOUNT_RECOVERY_COMPLETED,
        INSTALLATION_PROVISIONING_STARTED,
        INSTALLATION_PROVISIONED,
        INSTALLATION_LOCKED,
        INSTALLATION_RECOVERY_STARTED,
        INSTALLATION_RECOVERED,
        USER_SESSION_CREATED,
        USER_SESSION_REVOKED,
        USER_SESSION_EXPIRED,
        RECOVERY_CODES_ROTATED,
    }
)
