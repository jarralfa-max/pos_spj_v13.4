"""
Migration 079 — proveedores: normalizar condicion_pago

Garantiza que la tabla proveedores tenga la columna condicion_pago (singular).
La migración 047 añadió condiciones_pago (plural) pero varias queries en
compras_pro.py usan el nombre singular. Esta migración añade ambas si faltan,
sin romper instancias que ya tengan una u otra.
"""


def run(conn):
    def _col_exists(table: str, col: str) -> bool:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        return col in cols

    try:
        if not _col_exists("proveedores", "condicion_pago"):
            conn.execute(
                "ALTER TABLE proveedores ADD COLUMN condicion_pago TEXT DEFAULT ''"
            )
        if not _col_exists("proveedores", "condiciones_pago"):
            conn.execute(
                "ALTER TABLE proveedores ADD COLUMN condiciones_pago INTEGER DEFAULT 30"
            )
        conn.commit()
    except Exception:
        pass
