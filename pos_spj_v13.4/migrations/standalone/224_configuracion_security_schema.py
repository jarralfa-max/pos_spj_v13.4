# migrations/standalone/224_configuracion_security_schema.py
"""SET-1 — Configuración security schema (Auditoría en caliente, §60).

Creates `configuracion_authorization_log` (hot-authorization audit
trail — who requested, who authorized, why) and `configuracion_audit_log`
(before/after state for critical Configuración mutations: device status
changes, document template version status changes), mirroring the shape
already proven by `inventory_authorization_log`/`inventory_audit_log`
(migration 121, `backend/infrastructure/db/schema/inventory_schema.py`).

DDL lives in backend/infrastructure/db/schema/configuracion_security_schema.py;
only this migration may call create_configuracion_security_schema.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.configuracion_security_schema import (
    create_configuracion_security_schema,
)

logger = logging.getLogger("spj.migrations.224")


def run(conn) -> None:
    create_configuracion_security_schema(conn)
    conn.commit()
    logger.info("224: configuracion_authorization_log/configuracion_audit_log schema created.")


up = run
