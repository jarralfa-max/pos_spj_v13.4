"""352 — Estructura organizacional hacia el servidor central y perfiles de
sucursal (auditoría enterprise, cierre de pendientes de la Fase 1).

1. `org_outbox`: cada cambio de una unidad deja aquí un evento con la foto
   completa (unidad + capacidades). El motor único de replicación lo lee como
   cualquier otro outbox de contexto (`replication_sources.DEFAULT_SOURCES`).
2. Un evento `ORG_UNIT_REGISTERED` por cada unidad que todavía no tenga
   ninguno (las que respaldó la 351): sin él, el servidor central no sabría de
   la estructura que ya existía.
3. Perfil de sucursal (`branch_profiles`) para cada sitio que no lo tenga, con
   el MISMO código y nombre que su unidad, zona horaria y configuración
   regional de la empresa. Desde ahora sitio, `sucursales` y perfil se escriben
   juntos; antes había que registrar el perfil aparte.

Sólo agrega filas y una tabla. Idempotente.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.352")

_SITIOS = ("RETAIL_BRANCH", "PRODUCTION_PLANT", "DISTRIBUTION_CENTER", "WAREHOUSE",
           "CORPORATE_OFFICE", "LOGISTICS_OPERATION")

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS org_outbox (
        id TEXT NOT NULL PRIMARY KEY,
        event_name TEXT NOT NULL,
        aggregate_type TEXT NOT NULL DEFAULT 'org_unit',
        entity_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        operation_id TEXT,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_org_outbox_entity ON org_outbox(entity_id, created_at)",
)


def _table(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (name,)).fetchone() is not None


def _snapshot_events(conn, ahora: str) -> int:
    """Foto fija de `org_unit_repository.org_unit_snapshot`."""
    emitidos = 0
    filas = conn.execute(
        "SELECT id, company_id, parent_id, unit_type, code, name, status, closed_at, updated_at"
        " FROM org_units u WHERE NOT EXISTS (SELECT 1 FROM org_outbox o"
        " WHERE o.entity_id = u.id) ORDER BY created_at, id").fetchall()
    for uid, empresa, padre, tipo, codigo, nombre, estado, cerrada, actualizada in filas:
        caps = sorted(str(r[0]) for r in conn.execute(
            "SELECT capability FROM org_unit_capabilities WHERE org_unit_id=?", (uid,)))
        evento = {
            "event_id": new_uuid(), "event_name": "ORG_UNIT_REGISTERED",
            "operation_id": new_uuid(), "entity_id": uid, "branch_id": None,
            "user_id": None, "timestamp": ahora,
            "payload": {"unit_id": uid, "company_id": empresa, "parent_id": padre,
                        "unit_type": tipo, "code": codigo, "name": nombre, "status": estado,
                        "closed_at": cerrada, "is_operating_site": tipo in _SITIOS,
                        "capabilities": caps, "updated_at": actualizada}}
        conn.execute(
            "INSERT INTO org_outbox (id, event_name, aggregate_type, entity_id, payload_json,"
            " operation_id, created_at) VALUES (?,?,?,?,?,?,?)",
            (new_uuid(), "ORG_UNIT_REGISTERED", "org_unit", uid,
             json.dumps(evento, sort_keys=True), evento["operation_id"], ahora))
        emitidos += 1
    return emitidos


def _branch_profiles(conn, ahora: str) -> int:
    if not _table(conn, "branch_profiles"):
        return 0
    creados = 0
    filas = conn.execute(
        "SELECT u.id, u.code, u.name, u.status, c.default_timezone, c.default_locale"
        " FROM org_units u JOIN sucursales s ON s.id = u.id"
        " LEFT JOIN company_profiles c ON c.id = u.company_id"
        f" WHERE u.unit_type IN ({', '.join('?' for _ in _SITIOS)})"
        " AND NOT EXISTS (SELECT 1 FROM branch_profiles b WHERE b.branch_id = u.id)",
        _SITIOS).fetchall()
    for uid, codigo, nombre, estado, zona, region in filas:
        if conn.execute("SELECT 1 FROM branch_profiles WHERE code=?", (codigo,)).fetchone():
            logger.warning("352: el código %s ya lo usa otro perfil; %s queda sin perfil",
                           codigo, uid)
            continue
        conn.execute(
            "INSERT INTO branch_profiles (id, branch_id, code, name, timezone, locale, active,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (uid, uid, codigo, nombre, zona or "", region or "",
             1 if estado == "ACTIVE" else 0, ahora, ahora))
        creados += 1
    return creados


def run(conn) -> None:
    for sentencia in _DDL:
        conn.execute(sentencia)
    if not _table(conn, "org_units"):
        conn.commit()
        return
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    perfiles = _branch_profiles(conn, ahora)
    eventos = _snapshot_events(conn, ahora)
    conn.commit()
    logger.info("352: %s perfil(es) de sucursal creados; %s unidad(es) puestas en org_outbox.",
                perfiles, eventos)


up = run
