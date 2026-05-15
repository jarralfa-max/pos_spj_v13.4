"""
078_compras_po_link.py
───────────────────────
Phase 3 — Vincula compras con PO (ordenes_compra).

Agrega a la tabla 'compras':
  - purchase_order_id  → FK nullable a ordenes_compra(id)
                         NULL = compra directa (flujo existente, sin PO)
                         NOT NULL = recepción asociada a una PO

Regla:
  Si purchase_order_id IS NULL → compra directa (comportamiento actual, sin cambio)
  Si purchase_order_id IS NOT NULL → recepción de PO (nueva funcionalidad Phase 4)

Esta migración NO modifica el flujo actual de compras directas.
"""


def run(conn):
    existing = {row[1] for row in conn.execute("PRAGMA table_info(compras)")}
    if "purchase_order_id" not in existing:
        conn.execute(
            "ALTER TABLE compras ADD COLUMN purchase_order_id INTEGER"
        )

    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_compras_po_id
            ON compras(purchase_order_id)
            WHERE purchase_order_id IS NOT NULL;
    """)
