"""Authentication attempt log schema — SHELL-7.

DDL lives only here; only migration 207 may call `create_authentication_schema`.

A full attempt log (`AuthenticationAttempt`, one row per try) rather than
the legacy `usuarios.intentos_fallidos`/`bloqueado_hasta` counter columns
that `core/services/auth_service.py` still uses today — `AccountLockoutPolicy`
(SHELL-1) reasons over the trailing-failure *sequence*, not a single
counter, which is what the master plan's §41 asks for. The two mechanisms
coexist during the migration: this table backs the new
`AuthenticateUserUseCase` path built in SHELL-7; the legacy columns keep
backing `AuthService` until SHELL-16/17 retires that path entirely.
"""
from __future__ import annotations

_AUTHENTICATION_DDL = (
    """
    CREATE TABLE IF NOT EXISTS authentication_attempts (
        id              TEXT NOT NULL PRIMARY KEY,
        user_reference  TEXT NOT NULL,
        workstation_id  TEXT NOT NULL DEFAULT '',
        success         INTEGER NOT NULL CHECK (success IN (0, 1)),
        failure_reason  TEXT NOT NULL DEFAULT '',
        occurred_at     TEXT NOT NULL
    )
    """,
)

_AUTHENTICATION_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_authentication_attempts_user "
    "ON authentication_attempts(user_reference, occurred_at)",
)


def create_authentication_schema(conn) -> None:
    for statement in _AUTHENTICATION_DDL:
        conn.execute(statement)
    for index in _AUTHENTICATION_INDEXES:
        conn.execute(index)
