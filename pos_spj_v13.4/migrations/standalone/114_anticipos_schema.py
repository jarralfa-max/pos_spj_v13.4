"""Migración 114 — Esquema de anticipos (born-clean UUIDv7).

Centraliza el esquema que `api/routers/anticipos.py` creaba ad-hoc con
`CREATE TABLE IF NOT EXISTS ... id INTEGER PRIMARY KEY AUTOINCREMENT`
(REGLA 11 + REGLA 13: el schema vive en migrations/, no en la capa API/UI).

La identidad es UUIDv7 TEXT y las FK funcionales (venta_id, sucursal_id,
usuario_id) son TEXT; sin DEFAULT 1. Consistente con:
  • FinanceService.controlar_anticipo (INSERT id, venta_id, monto, ...)
  • api/routers/anticipos.py (INSERT id=new_uuid(), ...)

050_wa_integration ya sólo ALTERa esta tabla (referencia, fecha_pago) cuando
existe; esta migración garantiza su existencia con el esquema correcto.
"""

VERSION = "114"
DESCRIPTION = "Esquema de anticipos (UUIDv7 born-clean)"


def run(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS anticipos(
            id          TEXT PRIMARY KEY,
            venta_id    TEXT NOT NULL,
            monto       REAL NOT NULL,
            metodo      TEXT DEFAULT 'mercadopago',
            estado      TEXT DEFAULT 'pendiente',
            referencia  TEXT DEFAULT '',
            usuario_id  TEXT DEFAULT '',
            sucursal_id TEXT DEFAULT '',
            fecha       TEXT DEFAULT (datetime('now')),
            fecha_pago  TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_anticipos_venta ON anticipos(venta_id);
        CREATE INDEX IF NOT EXISTS idx_anticipos_estado ON anticipos(estado);
        """
    )
