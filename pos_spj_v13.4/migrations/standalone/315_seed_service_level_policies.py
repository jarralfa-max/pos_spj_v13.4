"""315 — políticas de SLA por prioridad para los casos de atención (§31).

POR QUÉ HACE FALTA (medido en una copia de la base viva el 2026-10-08)
-------------------------------------------------------------------
``service_level_policies`` estaba vacía: ``CreateServiceCaseUseCase`` sólo crea
la instancia de SLA si alguna política coincide, así que ningún caso tenía
vencimiento, el tablero «Casos fuera de SLA» marcaba siempre 0 y el
escalamiento por SLA vencido no podía dispararse.

DECISIÓN DEL USUARIO (2026-10-08 — «tiempos estándar»)
--------------------------------------------------------
Primera respuesta / resolución, por prioridad (cualquier tipo, canal y
sucursal; una política más específica creada después gana por especificidad):

* Baja       8 h / 72 h
* Normal     4 h / 48 h
* Alta       1 h / 24 h
* Urgente   30 min / 8 h
* Crítica   30 min / 8 h

Editables desde Clientes y CRM → Atención → SLA (se retiran y se crean
otras). Sólo siembra la prioridad que no tenga ya una política genérica
activa: nunca pisa lo que alguien configuró.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.315")

#: (código, nombre, prioridad, primera respuesta en min, resolución en min)
_POLICIES = (
    ("SLA-BAJA", "Prioridad baja", "LOW", 8 * 60, 72 * 60),
    ("SLA-NORMAL", "Prioridad normal", "NORMAL", 4 * 60, 48 * 60),
    ("SLA-ALTA", "Prioridad alta", "HIGH", 60, 24 * 60),
    ("SLA-URGENTE", "Prioridad urgente", "URGENT", 30, 8 * 60),
    ("SLA-CRITICA", "Prioridad crítica", "CRITICAL", 30, 8 * 60),
)


def _tabla_existe(conn, nombre: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nombre,)
    ).fetchone() is not None


def run(conn) -> None:
    if not _tabla_existe(conn, "service_level_policies"):
        logger.info("315: sin tabla service_level_policies; nada que sembrar.")
        return
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sembradas = 0
    for code, name, priority, first_minutes, resolution_minutes in _POLICIES:
        ya = conn.execute(
            "SELECT 1 FROM service_level_policies WHERE active=1 AND priority=?"
            " AND case_type IS NULL AND origin_branch_id IS NULL AND channel IS NULL",
            (priority,),
        ).fetchone()
        if ya is not None or conn.execute(
                "SELECT 1 FROM service_level_policies WHERE code=?", (code,)).fetchone():
            continue
        conn.execute(
            "INSERT INTO service_level_policies (id, code, name, first_response_minutes,"
            " resolution_minutes, case_type, priority, origin_branch_id, channel,"
            " at_risk_threshold_pct, active, created_at, updated_at)"
            " VALUES (?,?,?,?,?,NULL,?,NULL,NULL,80,1,?,?)",
            (new_uuid(), code, name, first_minutes, resolution_minutes, priority, ahora, ahora),
        )
        sembradas += 1
    conn.commit()
    logger.info("315: %s políticas de SLA sembradas.", sembradas)


up = run
