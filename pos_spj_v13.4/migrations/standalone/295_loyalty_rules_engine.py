"""295 — reglas de acumulación (§13) y combinación de beneficios (§24), 2026-10-03.

Decisión del usuario: "las reglas salen de Fidelidad y el POS las ejecuta".
Crea `loyalty_rules`, `loyalty_sale_evaluations`, `loyalty_rule_applications`
y `loyalty_stacking_rules`, y siembra la combinación de beneficios de
arranque: todo se permite salvo VARIOS CUPONES en una venta (un cupón por
venta). Es configuración: Fidelidad → Control → Combinación de beneficios la
cambia. Sin reglas activas el POS acumula exactamente como antes (la base de
la Configuración). Idempotente.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger("spj.migrations.295")

_ARRANQUE = (
    ("POINTS_COUPON", "ALLOW"), ("POINTS_VOUCHER", "ALLOW"), ("COUPON_VOUCHER", "ALLOW"),
    ("COUPON_COUPON", "DENY"), ("PROMOTION_COUPON", "ALLOW"),
    ("EMPLOYEE_DISCOUNT_COUPON", "ALLOW"), ("GIFT_CARD_POINTS", "ALLOW"),
    ("STORE_CREDIT_COUPON", "ALLOW"),
)


def run(conn) -> None:
    from backend.infrastructure.db.schema.loyalty_rules_schema import create_loyalty_rules_schema

    create_loyalty_rules_schema(conn)
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for combinacion, opcion in _ARRANQUE:
        conn.execute(
            "INSERT OR IGNORE INTO loyalty_stacking_rules (combination, option, priority_order,"
            " updated_at) VALUES (?, ?, '[]', ?)", (combinacion, opcion, ahora))
    conn.commit()
    logger.info("295: reglas de acumulación y combinación de beneficios listas.")


up = run
