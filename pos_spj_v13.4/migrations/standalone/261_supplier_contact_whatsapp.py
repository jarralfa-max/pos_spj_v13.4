"""261 — `supplier_contacts.whatsapp_e164`.

WhatsApp era uno de los grupos de datos del proveedor que faltaban: el contacto
sólo tenía `phone_e164`, y usar ese mismo número como WhatsApp es falso en la
práctica (fijo de oficina vs. móvil del contacto). El canal de WhatsApp es
además el que se usa para pedidos y avisos en esta instalación.

POR QUÉ EL `ALTER` VIVE AQUÍ Y NO EN EL ESQUEMA
------------------------------------------------
`backend/infrastructure/db/schema/supplier_schema.py` es DDL de creación pura:
`_DDL` + `_INDEXES` aplicados por `create_supplier_schema()`, todo
`CREATE TABLE IF NOT EXISTS`, SIN ningún mecanismo de columna guardada (no hay
`ALTER TABLE`, ni `_column_exists`, ni `PRAGMA table_info` en todo el archivo).
La columna se añadió allí para instalaciones NUEVAS; esta migración cubre las
EXISTENTES, que ya tienen la tabla creada y a las que un
`CREATE TABLE IF NOT EXISTS` no les añade nada.

Idempotente comprobando `PRAGMA table_info` — no por `try/except`, que también
taparía un error distinto.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.261")

TABLE = "supplier_contacts"
COLUMN = "whatsapp_e164"


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _has_column(conn, table: str, column: str) -> bool:
    return any(row[1] == column
               for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def run(conn) -> None:
    if not _table_exists(conn, TABLE):
        # Instalación sin el contexto de Proveedores todavía: `create_supplier_
        # schema()` ya crea la columna, así que no hay nada que migrar.
        logger.info("261: %s no existe; nada que migrar.", TABLE)
        return
    if _has_column(conn, TABLE, COLUMN):
        return
    conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} TEXT")
    conn.commit()
    logger.info("261: %s.%s agregada.", TABLE, COLUMN)


up = run
