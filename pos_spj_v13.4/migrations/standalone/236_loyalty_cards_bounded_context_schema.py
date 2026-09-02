# migrations/standalone/236_loyalty_cards_bounded_context_schema.py
"""Loyalty Cards bounded context — born-clean UUIDv7 schema (LOY-16,
§31-32): card base record + rotatable public QR token.

Separate bounded context from Fidelidad/Loyalty and from the legacy
`tarjetas_fidelidad`/`card_batches`/`card_assignment_history`/
`historico_tarjetas` tables (migration m000) — master prompt §30: "El
subdominio Tarjetas debe ser especializado."
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.loyalty_cards_schema import create_loyalty_cards_schema

logger = logging.getLogger("spj.migrations.236")


def run(conn) -> None:
    create_loyalty_cards_schema(conn)
    conn.commit()
    logger.info("236: loyalty cards bounded context schema created (born-clean UUIDv7).")


up = run
