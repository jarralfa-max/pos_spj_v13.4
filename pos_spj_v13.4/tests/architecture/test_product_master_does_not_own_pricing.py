"""PRC-9 audit (refuerzo) — el maestro canónico `products` no posee precio/costo.

Productos define *qué es* el artículo; Pricing/Costing fija *cuánto vale*. La tabla
canónica `products` no debe declarar columnas de precio ni costo; ese dato vive en
`product_price` / `product_cost`. (El legacy `productos.precio`/`costo` residual lo
elimina PROD-19; aquí se protege el esquema canónico ya construido.)
"""

from __future__ import annotations

import sqlite3

from backend.infrastructure.db.schema.products_schema import create_products_schema

_FORBIDDEN_TOKENS = ("precio", "price", "costo", "cost")


def test_products_table_has_no_price_or_cost_columns():
    conn = sqlite3.connect(":memory:")
    create_products_schema(conn)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(products)").fetchall()]
    conn.close()
    offenders = [c for c in cols
                 if any(tok in c.lower() for tok in _FORBIDDEN_TOKENS)]
    assert not offenders, (
        f"El maestro `products` no debe poseer precio/costo (vive en Pricing): "
        f"{offenders}")
