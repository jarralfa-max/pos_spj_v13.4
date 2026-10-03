"""Puente Fidelidad → Finanzas (2026-10-03): estado de lo ya contabilizado.

Fidelidad, Instrumentos comerciales y Sorteos escriben sus LIBROS (puntos,
vales, canjes de cupón, premios). Finanzas asienta su efecto económico. Estas
tablas guardan qué movimiento ya se asentó y, para los puntos, de qué
acumulación salió cada consumo (FIFO): sin eso no se sabe a qué valor se
reconoció el punto que hoy se canjea ni qué parte de una acumulación caduca.

- ``loyalty_finance_links``: un renglón por movimiento de origen procesado
  (POSTED, HELD = esperando que termine una reserva o una acreditación
  diferida, SKIPPED = sin efecto contable, FAILED = se reintenta).
- ``loyalty_finance_point_credits``: cada acumulación de puntos con el valor
  unitario con que se reconoció.
- ``loyalty_finance_point_allocations``: qué parte de qué acumulación consumió
  cada débito (HOLD = apartado aún sin confirmar).
"""

from __future__ import annotations

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS loyalty_finance_links (
        source_key TEXT NOT NULL PRIMARY KEY,
        source_type TEXT NOT NULL,
        source_id TEXT NOT NULL,
        status TEXT NOT NULL,
        amount TEXT NOT NULL DEFAULT '0',
        detail TEXT NOT NULL DEFAULT '',
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_loyalty_finance_links_status"
    " ON loyalty_finance_links (status, source_type)",
    """
    CREATE TABLE IF NOT EXISTS loyalty_finance_point_credits (
        credit_transaction_id TEXT NOT NULL PRIMARY KEY,
        loyalty_account_id TEXT NOT NULL,
        points TEXT NOT NULL,
        unit_value TEXT NOT NULL,
        amount TEXT NOT NULL,
        credit_created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_loyalty_finance_point_credits_account"
    " ON loyalty_finance_point_credits (loyalty_account_id, credit_created_at)",
    """
    CREATE TABLE IF NOT EXISTS loyalty_finance_point_allocations (
        id TEXT NOT NULL PRIMARY KEY,
        debit_transaction_id TEXT NOT NULL,
        credit_transaction_id TEXT NOT NULL
            REFERENCES loyalty_finance_point_credits(credit_transaction_id),
        points TEXT NOT NULL,
        amount TEXT NOT NULL,
        kind TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_loyalty_finance_alloc_debit"
    " ON loyalty_finance_point_allocations (debit_transaction_id)",
    "CREATE INDEX IF NOT EXISTS idx_loyalty_finance_alloc_credit"
    " ON loyalty_finance_point_allocations (credit_transaction_id, status)",
)


def create_loyalty_finance_tables(connection) -> None:
    for ddl in _DDL:
        connection.execute(ddl)


__all__ = ["create_loyalty_finance_tables"]
