"""Per-user account recovery token schema — SHELL-7.

DDL lives only here; only migration 207 may call
`create_account_recovery_schema`. Backs `backend/security/recovery/`'s
`RecoveryTokenRepository` (SHELL-1 built the domain model and an in-memory
reference implementation only — this is the first phase that actually puts
`AccountRecoveryService` behind a real UI flow, so it needs to survive the
gap between "user requests recovery" and "user clicks the emailed link
five minutes later," which an in-memory store obviously can't).

Not to be confused with `installation_recovery_codes` (SHELL-2) — that's
the installation's own backup-code kit for recovering a LOCKED
installation; this table is per-user "I forgot my password" tokens.
"""
from __future__ import annotations

_ACCOUNT_RECOVERY_DDL = (
    """
    CREATE TABLE IF NOT EXISTS account_recovery_tokens (
        token_id        TEXT NOT NULL PRIMARY KEY,
        user_reference  TEXT NOT NULL,
        token_hash      TEXT NOT NULL UNIQUE,
        issued_at       TEXT NOT NULL,
        expires_at      TEXT NOT NULL,
        used_at         TEXT
    )
    """,
)

_ACCOUNT_RECOVERY_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_account_recovery_tokens_user "
    "ON account_recovery_tokens(user_reference)",
)


def create_account_recovery_schema(conn) -> None:
    for statement in _ACCOUNT_RECOVERY_DDL:
        conn.execute(statement)
    for index in _ACCOUNT_RECOVERY_INDEXES:
        conn.execute(index)
