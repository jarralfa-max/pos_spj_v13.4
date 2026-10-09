"""313 — Imágenes y videos para la pantalla del cliente (2026-10-08).

Hasta aquí el contenido IMAGE/VIDEO sólo admitía texto escrito a mano en
`body` y la pantalla mostraba un aviso en su lugar: no había dónde guardar el
archivo. `display_media` registra cada archivo copiado a la carpeta de media
de la aplicación; el contenido guarda su id. DDL en
`backend/infrastructure/db/schema/customer_display_schema.py`. Idempotente.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.customer_display_schema import create_display_media_schema

logger = logging.getLogger("spj.migrations.313")


def run(conn) -> None:
    create_display_media_schema(conn)
    conn.commit()
    logger.info("313: display_media lista.")


up = run
