"""338 — instalador y actualizador (2026-10-14).

Crea `software_station_settings` (versión instalada, esquema, canal y ventana
de mantenimiento por estación) y `software_update_events` (traza de
búsquedas, descargas, instalaciones, reversiones y cambios de canal). DDL en
`backend/infrastructure/db/schema/software_updates_schema.py`. Idempotente.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.software_updates_schema import (
    create_software_updates_schema,
)

logger = logging.getLogger("spj.migrations.338")


def run(conn) -> None:
    create_software_updates_schema(conn)
    conn.commit()
    logger.info("338: software_station_settings/software_update_events listos.")


up = run
