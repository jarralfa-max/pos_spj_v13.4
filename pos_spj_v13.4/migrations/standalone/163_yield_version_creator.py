# migrations/standalone/163_yield_version_creator.py
"""Rendimientos UI — columna `created_by` en yield_profile_versions (segregación).

Necesaria para §39: quien crea una versión de rendimiento no puede aprobarla ni
activarla. Idempotente: agrega la columna sólo si falta (DBs previas).
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.163")


def _column_exists(conn, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))


def run(conn) -> None:
    create_products_schema(conn)
    if not _column_exists(conn, "yield_profile_versions", "created_by"):
        conn.execute("ALTER TABLE yield_profile_versions ADD COLUMN created_by TEXT")
    conn.commit()
    logger.info("163: yield_profile_versions.created_by asegurada.")


up = run
