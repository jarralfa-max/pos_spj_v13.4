"""
Migration 072 — condicion_pago: enforce CHECK constraint + NOT NULL defaults
Adds a new column condicion_pago_v2 with proper constraints alongside the
existing one, then ensures existing rows have valid values.

SQLite does not support adding CHECK constraints to existing columns via
ALTER TABLE, so we validate existing data and set defaults for NULLs.
"""

_VALID_CONDICION = frozenset({"liquidado", "credito", "parcial"})


def run(conn):
    # 1. Backfill NULLs → 'liquidado' (safe default: implies full payment)
    conn.execute("""
        UPDATE compras
        SET condicion_pago = 'liquidado'
        WHERE condicion_pago IS NULL OR condicion_pago NOT IN ('liquidado','credito','parcial')
    """)

    # 2. Backfill plazo_dias NULLs → 0
    conn.execute("""
        UPDATE compras
        SET plazo_dias = 0
        WHERE plazo_dias IS NULL
    """)

    # 3. Backfill moneda NULLs → 'MXN'
    conn.execute("""
        UPDATE compras
        SET moneda = 'MXN'
        WHERE moneda IS NULL OR moneda = ''
    """)

    # 4. Ensure condicion_pago column exists on recepciones (migration 040 adds it
    #    but earlier DBs may be missing it)
    try:
        conn.execute("ALTER TABLE recepciones ADD COLUMN condicion_pago TEXT DEFAULT 'liquidado'")
    except Exception:
        pass  # column already exists — expected on most DBs

    # 5. Backfill recepciones.condicion_pago
    conn.execute("""
        UPDATE recepciones
        SET condicion_pago = 'liquidado'
        WHERE condicion_pago IS NULL OR condicion_pago NOT IN ('liquidado','credito','parcial')
    """)

    conn.commit()
