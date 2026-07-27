"""Migration 112 — reconcile the loyalty-card schema for CardBatchEngine.

``core/services/card_batch_engine.py`` was written against a "v14" card schema
that was never created, so every operation failed on missing columns and the
engine was dead (clientes.py degraded with "Actualice la base de datos a v14").
This migration adds the missing, non-destructive columns idempotently so the
engine becomes functional:

* ``tarjetas_fidelidad`` : ``numero`` (printed card number, UNIQUE),
  ``batch_id`` (lote FK, declared TEXT → UUIDv7-ready), ``activa`` (active flag).
* ``card_batches``       : ``generado_por`` (issuer), ``fecha_cierre`` (close ts).

Identity stays TEXT NOT NULL PRIMARY KEY here; the UUIDv7 cut of the id columns to TEXT
is migración 200. ``batch_id`` is TEXT so it already accepts a UUID once
``card_batches.id`` becomes TEXT (SQLite type affinity matches str↔int meanwhile).
"""
from __future__ import annotations


def _add_column(conn, table: str, ddl: str) -> None:
    """ALTER TABLE ... ADD COLUMN, ignoring 'column already exists'."""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
    except Exception:
        pass  # column already present — idempotent


def run(conn) -> None:
    # ── tarjetas_fidelidad: columnas que el motor espera ──────────────────────
    _add_column(conn, "tarjetas_fidelidad", "numero TEXT")
    _add_column(conn, "tarjetas_fidelidad", "batch_id TEXT")
    _add_column(conn, "tarjetas_fidelidad", "activa INTEGER DEFAULT 1")

    # ON CONFLICT(numero) del motor exige un índice UNIQUE total sobre numero.
    # SQLite permite múltiples NULL en un índice UNIQUE, así que las filas legacy
    # sin numero no colisionan.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_tarjetas_fidelidad_numero "
        "ON tarjetas_fidelidad(numero)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tarjetas_fidelidad_batch "
        "ON tarjetas_fidelidad(batch_id)"
    )

    # ── card_batches: columnas que el motor espera ────────────────────────────
    _add_column(conn, "card_batches", "generado_por TEXT")
    _add_column(conn, "card_batches", "fecha_cierre DATETIME")

    conn.commit()
