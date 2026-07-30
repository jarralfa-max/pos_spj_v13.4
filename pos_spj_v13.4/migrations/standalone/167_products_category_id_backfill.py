# migrations/standalone/167_products_category_id_backfill.py
"""PROD corte de legacy — backfill de `products.category_id` desde legacy.

La migración 166 respaldó el catálogo `product_categories` desde las categorías
de texto libre de `productos`; ésta enlaza cada producto canónico con su
categoría, poblando `products.category_id` (que el backfill 148 dejó NULL). Con
esto los lectores de catálogo pueden leer la categoría por FK canónica en vez de
la columna de texto `productos.categoria`.

Aditiva e idempotente: sólo asigna `category_id` cuando está NULL y el producto
legacy tiene una `categoria` no vacía cuya normalización coincide con una
categoría canónica (por `name_normalized`). No crea categorías (eso lo hace 166)
ni toca productos ya enlazados.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.167")


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def run(conn) -> None:
    if not all(_table_exists(conn, t) for t in
               ("products", "productos", "product_categories")):
        logger.info("167: faltan tablas fuente/destino — omitido.")
        return

    cur = conn.execute(
        """
        UPDATE products
           SET category_id = (
                SELECT pc.id
                  FROM productos p
                  JOIN product_categories pc
                    ON pc.name_normalized = LOWER(TRIM(p.categoria))
                 WHERE p.id = products.id
                 LIMIT 1)
         WHERE category_id IS NULL
           AND EXISTS (
                SELECT 1 FROM productos p2
                 WHERE p2.id = products.id
                   AND TRIM(COALESCE(p2.categoria, '')) <> ''
                   AND EXISTS (
                        SELECT 1 FROM product_categories pc2
                         WHERE pc2.name_normalized = LOWER(TRIM(p2.categoria))))
        """)
    conn.commit()
    logger.info("167: %d producto(s) enlazado(s) a su categoría canónica.",
                cur.rowcount if cur.rowcount is not None else 0)


up = run
