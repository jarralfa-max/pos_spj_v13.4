"""
Migration 075 — plantillas_compra + plantillas_compra_items
Purchase template tables referenced by _poblar_plantillas_sidebar() and
_cargar_plantilla_sidebar() in modulos/compras_pro.py but never created
by any prior migration. Absence of these tables caused a startup crash
(sqlite3.OperationalError escaped a too-narrow except clause).
"""


def run(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS plantillas_compra (
            id          TEXT PRIMARY KEY,
            nombre      TEXT    NOT NULL,
            descripcion TEXT,
            proveedor_id TEXT,
            sucursal_id TEXT,
            activo      INTEGER DEFAULT 1,
            creado_por  TEXT,
            fecha       TEXT    DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS plantillas_compra_items (
            id           TEXT PRIMARY KEY,
            plantilla_id TEXT NOT NULL
                             REFERENCES plantillas_compra(id) ON DELETE CASCADE,
            producto_id  TEXT NOT NULL,
            cantidad     REAL    NOT NULL DEFAULT 1,
            costo_unitario REAL  DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS ix_plantillas_compra_items_plantilla
            ON plantillas_compra_items(plantilla_id)
    """)

    conn.commit()
