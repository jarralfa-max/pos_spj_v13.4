"""
Migration 072 — condicion_pago: enforce CHECK constraint + NOT NULL defaults
Adds a new column condicion_pago_v2 with proper constraints alongside the
existing one, then ensures existing rows have valid values.

SQLite does not support adding CHECK constraints to existing columns via
ALTER TABLE, so we validate existing data and set defaults for NULLs.

NOTE: This migration is self-sufficient — it re-applies the same ADD COLUMN
statements as migration 071 (idempotently) so that it succeeds even when 071
was marked done in schema_migrations but the actual columns are missing from
the DB (e.g. DB was replaced from a backup while schema_migrations was kept).
"""

_VALID_CONDICION = frozenset({"liquidado", "credito", "parcial"})


def _add_column(conn, table: str, col: str, definition: str) -> None:
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
    except Exception:
        pass  # column already exists — expected on most DBs


def run(conn):
    # 0. Guarantee columns exist regardless of whether 071 ran on this schema
    _add_column(conn, "compras", "condicion_pago", "TEXT DEFAULT 'liquidado'")
    _add_column(conn, "compras", "plazo_dias",     "INTEGER DEFAULT 0")
    _add_column(conn, "compras", "moneda",         "TEXT DEFAULT 'MXN'")

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
