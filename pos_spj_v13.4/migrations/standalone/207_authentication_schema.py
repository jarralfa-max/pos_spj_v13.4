# migrations/standalone/207_authentication_schema.py
"""SHELL-7 — Authentication schema.

Creates `authentication_attempts` (backs the new AccountLockoutPolicy-based
login path) and `account_recovery_tokens` (backs AccountRecoveryService,
now that it's wired into a real LoginWindow "forgot password" flow instead
of only existing as a tested-but-unused SHELL-1 component).

DDL lives in backend/infrastructure/db/schema/authentication_schema.py and
account_recovery_schema.py; only this migration may call them.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.account_recovery_schema import create_account_recovery_schema
from backend.infrastructure.db.schema.authentication_schema import create_authentication_schema

logger = logging.getLogger("spj.migrations.207")


def run(conn) -> None:
    create_authentication_schema(conn)
    create_account_recovery_schema(conn)
    conn.commit()
    logger.info("207: authentication_attempts + account_recovery_tokens schema created.")


up = run
