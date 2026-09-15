# migrations/standalone/258_recipes_reverse_reconstruction_allowed.py
"""258 — recipes.reverse_reconstruction_allowed (ERP integration master
prompt §16, Fase 7) — extends the schema.

A DISASSEMBLY/CUTTING_YIELD recipe (whole chicken -> breast/leg/wing) can
sometimes be run in reverse: reconstruct the base product from its parts
when direct stock is 0. Not every recipe should allow this (grinding meat
must never reverse into a whole cut), so it is a per-recipe policy flag,
defaulting to False (fail-closed) so no existing recipe becomes reversible
by migration alone.

Re-runs the idempotent ``create_products_schema`` (same pattern as 137/253):
DDL lives solely in ``products_schema.py``, which now declares
``reverse_reconstruction_allowed`` on ``recipes`` and guards the column
with an ALTER for tables created by an earlier run of that same function.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.258")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("258: recipes.reverse_reconstruction_allowed asegurada.")


up = run
