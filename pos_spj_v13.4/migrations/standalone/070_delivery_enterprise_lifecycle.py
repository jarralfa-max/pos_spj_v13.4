"""Migration 070: Delivery enterprise lifecycle columns.

Adds columns used by the v13.30 lifecycle event handlers and ticket printer
that may not exist in databases upgraded from older versions.

Safe to run multiple times (IF NOT EXISTS / try-except on ALTER).
"""
from __future__ import annotations


def run(conn) -> None:
    # delivery_orders: ensure all lifecycle tracking columns exist
    _add_columns(conn, "delivery_orders", [
        "tiempo_estimado INTEGER DEFAULT 30",
        "fecha_asignacion DATETIME",
        "fecha_entrega DATETIME",
        "pago_metodo TEXT DEFAULT ''",
        "pago_monto REAL DEFAULT 0",
        "costo_envio REAL DEFAULT 0",
        "weight_adjusted INTEGER DEFAULT 0",
        "corte_id TEXT DEFAULT 0",
    ])

    # delivery_items: ensure weight-adjustment columns exist
    _add_columns(conn, "delivery_items", [
        "requested_qty REAL",
        "prepared_qty REAL",
        "final_qty REAL",
        "prepared_by TEXT",
        "prepared_at DATETIME",
        "adjustment_reason TEXT",
        "tolerance_exceeded INTEGER DEFAULT 0",
    ])

    # delivery_driver_cuts: ensure all cut columns exist
    conn.execute("""
        CREATE TABLE IF NOT EXISTS delivery_driver_cuts (
            id TEXT PRIMARY KEY,
            driver_id TEXT NOT NULL,
            driver_nombre TEXT,
            turno_inicio DATETIME,
            turno_fin DATETIME DEFAULT (datetime('now')),
            entregas_total INTEGER DEFAULT 0,
            efectivo_cobrado REAL DEFAULT 0,
            tarjeta_cobrado REAL DEFAULT 0,
            transfer_cobrado REAL DEFAULT 0,
            total_cobrado REAL DEFAULT 0,
            efectivo_entregado REAL DEFAULT 0,
            diferencia REAL DEFAULT 0,
            usuario_corte TEXT,
            sucursal_id TEXT,
            notas TEXT
        )
    """)

    # Indexes for lifecycle query patterns
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_delivery_driver_id ON delivery_orders(driver_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_delivery_fecha_entrega ON delivery_orders(fecha_entrega)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_driver_cuts_driver ON delivery_driver_cuts(driver_id, turno_fin)"
    )

    try:
        conn.commit()
    except Exception:
        pass


def _add_columns(conn, table: str, col_defs: list) -> None:
    for col_def in col_defs:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
        except Exception:
            pass
