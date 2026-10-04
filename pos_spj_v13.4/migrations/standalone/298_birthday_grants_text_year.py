"""298 — `loyalty_birthday_grants.year` deja de ser entero (2026-10-03).

La 297 creó la tabla con `PRIMARY KEY (program_id, customer_id, year)` y
`year INTEGER`. La validación de arranque (REGLA CERO: ninguna columna de
llave primaria entera, `assert_uuid_identity`) la rechazó y la aplicación no
abría. Se reconstruye con `year TEXT`, copiando las filas; las migraciones
corren antes de esa validación, así que el siguiente arranque ya pasa.

`legacy_alter_table=ON` por la vista legacy rota de la base real (ver la 292).
Idempotente.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.298")

_NUEVA = """
    CREATE TABLE loyalty_birthday_grants__new (
        program_id TEXT NOT NULL,
        customer_id TEXT NOT NULL,
        year TEXT NOT NULL,
        granted_at TEXT NOT NULL,
        PRIMARY KEY (program_id, customer_id, year)
    )"""


def _year_type(conn) -> str | None:
    for fila in conn.execute("PRAGMA table_info(loyalty_birthday_grants)"):
        if fila[1] == "year":
            return str(fila[2] or "").upper()
    return None


def run(conn) -> None:
    tipo = _year_type(conn)
    if tipo is None or tipo == "TEXT":
        logger.info("298: nada que reconstruir (%s).", tipo or "sin tabla")
        return
    conn.commit()
    legacy_previo = conn.execute("PRAGMA legacy_alter_table").fetchone()[0]
    conn.execute("PRAGMA legacy_alter_table=ON")
    try:
        conn.execute(_NUEVA)
        conn.execute("INSERT INTO loyalty_birthday_grants__new (program_id, customer_id, year,"
                     " granted_at) SELECT program_id, customer_id, CAST(year AS TEXT), granted_at"
                     " FROM loyalty_birthday_grants")
        conn.execute("DROP TABLE loyalty_birthday_grants")
        conn.execute("ALTER TABLE loyalty_birthday_grants__new RENAME TO loyalty_birthday_grants")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute(f"PRAGMA legacy_alter_table={'ON' if legacy_previo else 'OFF'}")
    logger.info("298: loyalty_birthday_grants.year ahora es TEXT.")


up = run
