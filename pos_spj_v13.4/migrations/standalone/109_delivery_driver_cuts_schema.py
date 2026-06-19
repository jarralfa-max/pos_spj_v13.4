"""Migration 109 — canonical schema for delivery driver settlement tables."""
from __future__ import annotations


def run(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS delivery_driver_cuts (
            id                TEXT PRIMARY KEY,
            driver_id         INTEGER NOT NULL,
            driver_nombre     TEXT NOT NULL,
            turno_inicio      DATETIME,
            turno_fin         DATETIME DEFAULT (datetime('now')),
            entregas_total    INTEGER DEFAULT 0,
            efectivo_cobrado  REAL DEFAULT 0,
            tarjeta_cobrado   REAL DEFAULT 0,
            transfer_cobrado  REAL DEFAULT 0,
            total_cobrado     REAL DEFAULT 0,
            efectivo_entregado REAL DEFAULT 0,
            diferencia        REAL DEFAULT 0,
            usuario_corte     TEXT,
            sucursal_id       INTEGER DEFAULT 0,
            notas             TEXT,
            created_at        DATETIME DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS delivery_cut_items (
            id            TEXT PRIMARY KEY,
            cut_id        TEXT NOT NULL REFERENCES delivery_driver_cuts(id),
            order_id      INTEGER NOT NULL,
            cliente_nombre TEXT,
            total         REAL DEFAULT 0,
            pago_metodo   TEXT,
            pago_monto    REAL DEFAULT 0
        )
    """)
    # Add created_at if table pre-existed without it (migration idempotency)
    try:
        conn.execute(
            "ALTER TABLE delivery_driver_cuts ADD COLUMN created_at DATETIME DEFAULT (datetime('now'))"
        )
    except Exception:
        pass  # column already exists

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ddc_driver ON delivery_driver_cuts(driver_id, created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ddc_sucursal ON delivery_driver_cuts(sucursal_id, created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ddci_cut ON delivery_cut_items(cut_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ddci_order ON delivery_cut_items(order_id)"
    )

    # Add corte_id column to delivery_orders if not present (TEXT FK to delivery_driver_cuts.id)
    try:
        conn.execute("ALTER TABLE delivery_orders ADD COLUMN corte_id TEXT")
    except Exception:
        pass  # column already exists

    conn.commit()
