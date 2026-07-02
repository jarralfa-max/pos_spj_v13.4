"""Migration 069 — Delivery weight tracking + reservation columns.

Adds variable-weight support to delivery_items:
  requested_qty  — quantity asked by customer
  prepared_qty   — actual weight measured at prep time
  final_qty      — confirmed quantity used for inventory deduct
  prepared_by    — operator who measured
  prepared_at    — timestamp
  adjustment_reason — free text
  tolerance_exceeded — bool flag when diff > threshold

Adds weight_adjusted flag to delivery_orders for quick query.
"""


def run(conn):
    weight_cols = [
        "requested_qty      REAL",
        "prepared_qty       REAL",
        "final_qty          REAL",
        "prepared_by        TEXT",
        "prepared_at        DATETIME",
        "adjustment_reason  TEXT",
        "tolerance_exceeded INTEGER DEFAULT 0",
    ]
    for col in weight_cols:
        col_name = col.split()[0]
        try:
            conn.execute(f"ALTER TABLE delivery_items ADD COLUMN {col}")
        except Exception:
            pass  # column already exists

    order_cols = [
        "weight_adjusted    INTEGER DEFAULT 0",
        "pago_metodo        TEXT DEFAULT ''",
        "pago_monto         REAL DEFAULT 0",
        "costo_envio        REAL DEFAULT 0",
    ]
    for col in order_cols:
        col_name = col.split()[0]
        try:
            conn.execute(f"ALTER TABLE delivery_orders ADD COLUMN {col}")
        except Exception:
            pass

    # Ensure inventory_reservations exists (mirror of migration 023)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_reservations (
            id            TEXT PRIMARY KEY,
            branch_id     TEXT NOT NULL,
            product_id    TEXT NOT NULL,
            reserved_qty  REAL    NOT NULL CHECK(reserved_qty > 0),
            operation_id  TEXT    NOT NULL,
            operation_type TEXT   NOT NULL,
            expires_at    DATETIME NOT NULL,
            released      INTEGER NOT NULL DEFAULT 0,
            created_at    DATETIME NOT NULL DEFAULT (datetime('now'))
        )
    """)

    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_reservation_op "
            "ON inventory_reservations(operation_id, product_id, branch_id) WHERE released = 0"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reservation_branch_prod "
            "ON inventory_reservations(branch_id, product_id, released)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_delivery_items_delivery_id "
            "ON delivery_items(delivery_id)"
        )
    except Exception:
        pass

    try:
        conn.commit()
    except Exception:
        pass
