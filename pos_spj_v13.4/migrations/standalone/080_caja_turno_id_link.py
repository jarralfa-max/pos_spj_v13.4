# migrations/standalone/080_caja_turno_id_link.py
"""
Add turno_id FK to cierres_caja for direct link between a corte Z and its turno.
Also adds branch_id index on movimientos_caja for faster turno lookups.
"""


def run(conn):
    # Add turno_id to cierres_caja (nullable — preserves existing rows)
    try:
        conn.execute(
            "ALTER TABLE cierres_caja ADD COLUMN turno_id TEXT"
        )
    except Exception:
        pass  # column already exists

    # Index for fast corte history queries
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cierres_turno ON cierres_caja(turno_id)"
    )

    # Index for movimientos_caja turno lookups (used by get_movimientos_turno)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mov_caja_turno ON movimientos_caja(turno_id)"
    )

    # Index for movimientos_caja date queries (KPI bar)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mov_caja_fecha ON movimientos_caja(sucursal_id, fecha)"
    )

    conn.commit()
