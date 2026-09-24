"""262 — contado/crédito y forma de pago preferida en `supplier_commercial_terms`.

Añade `is_credit` y `preferred_payment_method` (decisión del usuario sobre las
formas válidas: Transferencia SPEI y Efectivo — ver `PaymentMethod`).

Mismas dos patas que la 261, porque `supplier_schema.py` es DDL de creación pura
sin ningún mecanismo de columna guardada: las columnas están en el `CREATE` para
instalaciones nuevas, y esta migración las añade a las existentes.

RELLENO OBLIGATORIO: `is_credit` nace con DEFAULT 0 (contado). Sin rellenar, toda
condición ya capturada con `credit_days > 0` quedaría como "contado con días de
crédito", combinación que `PaymentTerms` rechaza al hidratar — la ficha de esos
proveedores dejaría de abrir. Por eso se marca crédito donde el dato ya lo decía.
`preferred_payment_method` se deja en NULL: no hay de dónde deducirlo, e inventar
un valor sería afirmar algo que nadie capturó.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.262")

TABLE = "supplier_commercial_terms"


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _has_column(conn, table: str, column: str) -> bool:
    return any(row[1] == column
               for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def run(conn) -> None:
    if not _table_exists(conn, TABLE):
        logger.info("262: %s no existe; nada que migrar.", TABLE)
        return
    if not _has_column(conn, TABLE, "is_credit"):
        conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN is_credit INTEGER NOT NULL DEFAULT 0")
    if not _has_column(conn, TABLE, "preferred_payment_method"):
        conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN preferred_payment_method TEXT")
    # Idempotente: sólo toca filas incoherentes.
    conn.execute(f"UPDATE {TABLE} SET is_credit = 1 WHERE credit_days > 0 AND is_credit = 0")
    conn.commit()
    logger.info("262: contado/crédito y forma de pago en %s.", TABLE)


up = run
