# migrations/standalone/162_recipe_version_creator.py
"""Recetas UI — columna `created_by` en recipe_versions (segregación de funciones).

Necesaria para aplicar §39: quien crea una versión de receta no puede aprobarla ni
activarla. Idempotente: agrega la columna sólo si falta (DBs previas).
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.162")


def _column_exists(conn, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))


def run(conn) -> None:
    create_products_schema(conn)
    if not _column_exists(conn, "recipe_versions", "created_by"):
        conn.execute("ALTER TABLE recipe_versions ADD COLUMN created_by TEXT")
    conn.commit()
    logger.info("162: recipe_versions.created_by asegurada.")


up = run
