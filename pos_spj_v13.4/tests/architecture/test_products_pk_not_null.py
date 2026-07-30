"""PROD Fase 11 — invariante de identidad del contexto Productos: ninguna PK TEXT
del esquema canónico de Productos puede quedar NULL en silencio.

El guardrail global `test_text_pk_not_null` documenta un riesgo residual sistémico
(muchas tablas born-clean declaran `id TEXT PRIMARY KEY` sin `NOT NULL`, mitigado
porque sus otras columnas NOT NULL rechazan un INSERT sin PK). Este guardrail
**acota el invariante al contexto Productos** con la prueba dura y real: para toda
tabla de `PRODUCT_TABLES` con PK TEXT de una sola columna, un `INSERT DEFAULT
VALUES` (que omite la PK) nunca deja una fila con PK NULL — SQLite lo rechaza o
inserta un valor, pero jamás un id nulo.

Esto capturó (y ahora fija en cero) la regresión de PROD-8: los perfiles
`product_catch_weight_config`/`product_quality_profiles`/`product_logistics_profiles`
tenían todas sus demás columnas con default, así que `DEFAULT VALUES` colaba una
fila con `product_id` NULL. Corregido a `product_id TEXT NOT NULL PRIMARY KEY`.
"""

from __future__ import annotations

import sqlite3

from backend.infrastructure.db.schema.products_schema import (
    PRODUCT_TABLES,
    create_products_schema,
)


def _products_schema() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_products_schema(conn)
    conn.commit()
    return conn


def _single_text_pk(conn: sqlite3.Connection, table: str):
    # PRAGMA table_info: (cid, name, type, notnull, dflt_value, pk)
    info = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    pk_cols = [r for r in info if r[5]]
    if len(pk_cols) == 1 and (pk_cols[0][2] or "").upper() == "TEXT":
        return pk_cols[0][1]
    return None


def test_product_tables_never_admit_null_pk_via_default_values():
    conn = _products_schema()
    offenders: list[str] = []
    for table in PRODUCT_TABLES:
        pk = _single_text_pk(conn, table)
        if pk is None:
            continue
        try:
            conn.execute(f'INSERT INTO "{table}" DEFAULT VALUES')
        except (sqlite3.IntegrityError, sqlite3.OperationalError):
            conn.rollback()
            continue  # rechazado: comportamiento correcto
        null_rows = conn.execute(
            f'SELECT COUNT(*) FROM "{table}" WHERE "{pk}" IS NULL').fetchone()[0]
        if null_rows:
            offenders.append(f"{table}.{pk}")
        conn.rollback()
    assert offenders == [], (
        "Tablas del contexto Productos que admiten una PK TEXT NULL (declara "
        f"`... TEXT NOT NULL PRIMARY KEY`): {offenders}")


def test_product_profile_tables_declare_not_null_pk():
    """Los 3 perfiles single-PK de Productos declaran explícitamente NOT NULL."""
    conn = _products_schema()
    for table in ("product_catch_weight_config", "product_quality_profiles",
                  "product_logistics_profiles"):
        info = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        pk = [r for r in info if r[5]][0]
        assert pk[3] == 1, f"{table}.{pk[1]} debe ser NOT NULL (born-clean)"
