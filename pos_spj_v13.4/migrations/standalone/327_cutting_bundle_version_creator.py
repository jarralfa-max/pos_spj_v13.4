# migrations/standalone/327_cutting_bundle_version_creator.py
"""PROD-22 — creador de las versiones de despiece y de combo (§39).

Agrega `created_by` a `cutting_scheme_versions` y `bundle_versions` (vía el
esquema canónico de Productos). Sin esa identidad no había segregación: quien
capturaba una versión podía aprobarla y activarla él mismo. Las versiones ya
existentes quedan con creador desconocido (NULL) y no se bloquean.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.327")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("327: created_by en versiones de despiece y combo asegurado.")


up = run
