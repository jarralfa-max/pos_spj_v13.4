"""346 — Auditoría de Fidelidad 968e0bc (2026-10-22).

1. `loyalty_transactions.point_value` / `monetary_value` (FID-02): el valor del
   punto y el importe en pesos de CADA movimiento al momento de hacerlo. Un
   reintento del mismo canje devolvía `puntos × valor vigente`: si el valor del
   punto cambió entre intentos, la venta recibía otro descuento con un solo
   débito de puntos. Medido en la base real: 0 movimientos, nada que rellenar.
2. `loyalty_deferred_accruals` / `loyalty_deferred_accrual_collections`
   (FID-04): lo vendido a crédito acumula AL COBRARSE (decisión del usuario).
3. `loyalty_margin_floors` (FID-03): margen mínimo protegido por categoría con
   excepción por producto; ningún beneficio sin costo confiable.

Idempotente.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.346")


def _table(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (name,)).fetchone() is not None


def _columns(conn, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def run(conn) -> None:
    if _table(conn, "loyalty_transactions"):
        columnas = _columns(conn, "loyalty_transactions")
        for columna in ("point_value", "monetary_value"):
            if columna not in columnas:
                conn.execute(f"ALTER TABLE loyalty_transactions ADD COLUMN {columna} TEXT")
        from backend.infrastructure.db.schema.loyalty_schema import (
            create_loyalty_deferred_accrual_schema,
        )
        create_loyalty_deferred_accrual_schema(conn)
    logger.info("346: valor del punto por movimiento de fidelidad")
