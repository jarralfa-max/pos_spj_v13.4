"""
Migration 071 — compras: condicion_pago + plazo_dias
Adds payment-condition and credit-term columns to the compras table,
enabling Estatus pago display in the purchase history tab.
"""


def run(conn):
    def _add(table: str, col: str, definition: str) -> None:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
        except Exception:
            pass  # column already exists

    _add("compras", "condicion_pago", "TEXT DEFAULT 'liquidado'")
    _add("compras", "plazo_dias",     "INTEGER DEFAULT 0")
    _add("compras", "moneda",         "TEXT DEFAULT 'MXN'")
    conn.commit()
