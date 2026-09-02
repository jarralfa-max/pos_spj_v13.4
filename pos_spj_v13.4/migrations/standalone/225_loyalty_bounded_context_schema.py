# migrations/standalone/225_loyalty_bounded_context_schema.py
"""Fidelidad/Loyalty bounded context — born-clean UUIDv7 schema (LOY-3).

Creates the new `loyalty_program_definitions`/`loyalty_accounts`/
`loyalty_memberships`/`loyalty_transactions`/`loyalty_outbox` tables for the
domain entities built in LOY-2 (backend/domain/loyalty/entities/). These are
NEW tables, distinct from and not a replacement for the legacy
`loyalty_programs`/`loyalty_ledger`/`loyalty_pasivo_log`/`tarjetas_fidelidad`
tables (`migrations/m000_base_schema.py::_create_loyalty`) — see
backend/infrastructure/db/schema/loyalty_schema.py's own docstring for the
naming collision this phase found and fixed (a first draft literally named
this table `loyalty_programs`, colliding with the legacy one) and
docs/refactor/LOY-0_auditoria.md for what still owns production traffic
today (`core/services/loyalty_service.py`).
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema

logger = logging.getLogger("spj.migrations.225")


def run(conn) -> None:
    create_loyalty_schema(conn)
    conn.commit()
    logger.info("225: loyalty bounded context schema created (born-clean UUIDv7).")


up = run
