# migrations/standalone/166_product_categories_backfill_from_legacy.py
"""PROD corte de legacy (repoint batch 3) — backfill de categorías canónicas.

Puebla `product_categories` (P1-01) a partir de las categorías de texto libre
distintas de la tabla legacy `productos.categoria`, para que los lectores de
catálogo de categorías puedan repuntarse a la fuente canónica **sin perder** las
categorías históricas en uso (el backfill 148 dejó `products.category_id` en
NULL y no migró las categorías).

Aditiva e idempotente: crea una categoría raíz por cada `categoria` no vacía que
no exista ya (comparando por `name_normalized`), con id UUIDv7, `code` único y
ruta materializada raíz (`/{id}/`, depth 0). No toca `products` ni asigna
`category_id` (eso se resuelve en un paso posterior con datos por producto).
"""

from __future__ import annotations

import logging
import re

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.166")


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _slug_code(name: str) -> str:
    base = re.sub(r"[^A-Z0-9]+", "_", name.strip().upper()).strip("_")
    return (base or "CAT")[:40]


def run(conn) -> None:
    if not (_table_exists(conn, "productos") and _table_exists(conn, "product_categories")):
        logger.info("166: sin tablas fuente/destino — omitido.")
        return

    legacy = [r[0] for r in conn.execute(
        "SELECT DISTINCT categoria FROM productos "
        "WHERE categoria IS NOT NULL AND TRIM(categoria) <> ''").fetchall()]
    if not legacy:
        logger.info("166: no hay categorías legacy que respaldar.")
        return

    existing_norm = {r[0] for r in conn.execute(
        "SELECT name_normalized FROM product_categories").fetchall()}
    existing_codes = {r[0] for r in conn.execute(
        "SELECT code FROM product_categories").fetchall()}

    created = 0
    for raw in legacy:
        name = raw.strip()
        norm = name.lower()
        if norm in existing_norm:
            continue  # ya respaldada (idempotente)
        code = _slug_code(name)
        candidate, n = code, 1
        while candidate in existing_codes:
            n += 1
            candidate = f"{code[:36]}_{n}"
        code = candidate
        cat_id = new_uuid()
        conn.execute(
            "INSERT INTO product_categories "
            "(id, code, name, name_normalized, parent_id, path, depth, sort_order, "
            "active, created_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cat_id, code, name, norm, None, f"/{cat_id}/", 0, 0, 1, "backfill-166"))
        existing_norm.add(norm)
        existing_codes.add(code)
        created += 1

    conn.commit()
    logger.info("166: %d categoría(s) canónica(s) respaldada(s) desde legacy.", created)


up = run
