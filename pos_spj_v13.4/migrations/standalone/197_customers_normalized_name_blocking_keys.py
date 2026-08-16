# migrations/standalone/197_customers_normalized_name_blocking_keys.py
"""CRM-41 — Fase 7 (Base de datos): blocking keys para detección de
duplicados.

`CustomerDuplicatePolicy` (CRM-3) comparaba el candidato contra TODOS los
clientes en cada alta (`find_duplicate_rows()` sin filtro) — con 2 filas
en dev es invisible, con producción real sería un full scan en cada
creación de cliente. Esta migración agrega las columnas derivadas
(`normalized_name`/`normalized_legal_name`, ya escritas por
`CustomerRepository.save()`/`update()` desde este cambio) para que
`find_duplicate_rows_matching()` pueda filtrar por SQL en vez de cargar
todo — ver ese método y `backend/infrastructure/db/schema/
customers_crm_schema.py` para el detalle completo.

Igual que la migración 193 (bridge legacy): `create_customers_crm_schema()`
por sí sola no agrega columnas a una tabla `customers` que ya existía
antes de este cambio — se requiere un `ALTER TABLE` explícito e idempotente,
más el backfill de las filas ya existentes (que de otro modo quedarían con
`normalized_name=''`, invisibles para la detección de duplicados hasta su
próxima edición).
"""

from __future__ import annotations

import logging
import re
import unicodedata

from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema

logger = logging.getLogger("spj.migrations.197")


def _normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", (value or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", text)


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _column_exists(conn, table: str, column: str) -> bool:
    return any(row[1] == column
               for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _add_column(conn, table: str, column: str, ddl_type: str) -> None:
    if not _table_exists(conn, table):
        logger.info("197: %s no existe todavía; el esquema born-clean lo crea con %s",
                    table, column)
        return
    if _column_exists(conn, table, column):
        logger.info("197: %s.%s ya existe; idempotente", table, column)
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
    logger.info("197: %s.%s agregado", table, column)


def _backfill(conn) -> int:
    if not _table_exists(conn, "customers"):
        return 0
    rows = conn.execute(
        "SELECT id, display_name, legal_name FROM customers"
        " WHERE COALESCE(normalized_name,'') = ''").fetchall()
    for customer_id, display_name, legal_name in rows:
        conn.execute(
            "UPDATE customers SET normalized_name=?, normalized_legal_name=? WHERE id=?",
            (_normalize_name(display_name), _normalize_name(legal_name), customer_id))
    return len(rows)


def run(conn) -> None:
    _add_column(conn, "customers", "normalized_name", "TEXT NOT NULL DEFAULT ''")
    _add_column(conn, "customers", "normalized_legal_name", "TEXT NOT NULL DEFAULT ''")
    create_customers_crm_schema(conn)
    backfilled = _backfill(conn)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_customers_normalized_name ON customers(normalized_name)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_customers_normalized_legal_name"
        " ON customers(normalized_legal_name)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_customer_contacts_phone ON customer_contacts(phone_e164)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_customer_contacts_email ON customer_contacts(email)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_customer_tax_profiles_identifier"
        " ON customer_tax_profiles(tax_identifier)")
    conn.commit()
    logger.info("197: %d clientes backfilled con nombre normalizado.", backfilled)


up = run
