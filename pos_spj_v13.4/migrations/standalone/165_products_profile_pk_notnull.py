# migrations/standalone/165_products_profile_pk_notnull.py
"""PROD Fase 11 — endurecer PK TEXT a NOT NULL en perfiles de producto.

`product_catch_weight_config`, `product_quality_profiles` y
`product_logistics_profiles` nacieron (PROD-8/PROD-5) con
``product_id TEXT PRIMARY KEY`` sin ``NOT NULL``. En SQLite una PRIMARY KEY TEXT
sin ``NOT NULL`` admite un id NULL en silencio (a diferencia de INTEGER PRIMARY
KEY), rompiendo el invariante born-clean (`test_text_pk_not_null`). El DDL
canónico en `products_schema.py` ya se corrigió a ``TEXT NOT NULL PRIMARY KEY``;
esta migración reconstruye las tablas **existentes** para alinearlas, sin
pérdida de datos.

Idempotente y guardada: reconstruye una tabla sólo si existe y su PK sigue
siendo nullable. En un bootstrap limpio (DDL ya corregido) no hace nada. Las 3
tablas no tienen índices propios; sólo FKs a `products`/`units_of_measure`, que
se recrean con la copia del DDL.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.165")

_TABLES = (
    "product_catch_weight_config",
    "product_quality_profiles",
    "product_logistics_profiles",
)


def _table_sql(conn, table: str) -> str | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,)).fetchone()
    return row[0] if row else None


def _pk_is_nullable(conn, table: str) -> bool:
    # PRAGMA table_info: (cid, name, type, notnull, dflt_value, pk)
    info = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    pk_cols = [r for r in info if r[5]]
    return len(pk_cols) == 1 and (pk_cols[0][2] or "").upper() == "TEXT" \
        and pk_cols[0][3] == 0


def _rebuild(conn, table: str) -> None:
    create_sql = _table_sql(conn, table)
    if not create_sql or "product_id TEXT PRIMARY KEY" not in create_sql:
        return
    new_sql = create_sql.replace(
        "product_id TEXT PRIMARY KEY", "product_id TEXT NOT NULL PRIMARY KEY", 1)
    # renombra sólo el nombre de la tabla en el CREATE (primera aparición);
    # las FKs referencian products/units_of_measure, no la tabla propia.
    new_sql = new_sql.replace(table, f"{table}__new", 1)

    cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
    col_list = ", ".join(f'"{c}"' for c in cols)

    conn.execute(new_sql)
    conn.execute(
        f'INSERT INTO "{table}__new" ({col_list}) '
        f'SELECT {col_list} FROM "{table}"')
    conn.execute(f'DROP TABLE "{table}"')
    conn.execute(f'ALTER TABLE "{table}__new" RENAME TO "{table}"')
    logger.info("165: %s reconstruida con product_id NOT NULL.", table)


def run(conn) -> None:
    pending = [t for t in _TABLES if _pk_is_nullable(conn, t)]
    if not pending:
        logger.info("165: perfiles de producto ya tienen PK NOT NULL — sin cambios.")
        return
    # foreign_keys sólo puede togglearse fuera de transacción.
    conn.commit()
    fk_was_on = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    if fk_was_on:
        conn.execute("PRAGMA foreign_keys=OFF")
    try:
        for table in pending:
            _rebuild(conn, table)
        conn.commit()
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"165: foreign_key_check falló: {violations}")
    finally:
        if fk_was_on:
            conn.execute("PRAGMA foreign_keys=ON")
    logger.info("165: %d perfil(es) de producto endurecidos a PK NOT NULL.",
                len(pending))


up = run
