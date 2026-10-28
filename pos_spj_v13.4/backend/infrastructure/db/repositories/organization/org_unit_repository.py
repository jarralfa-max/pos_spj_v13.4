"""Persistencia de la estructura organizacional (migraciones 351 y 352).

Un sitio de operación vive en TRES filas con el mismo id: `org_units` (tipo,
jerarquía, estado), `sucursales` (la identidad que ya usan todos los módulos) y
`branch_profiles` (horario, tickets; su código es el prefijo de los folios).
Este repositorio las mantiene juntas: crear, renombrar, desactivar o cerrar un
sitio también escribe las otras dos, con el MISMO código y nombre.

Cada cambio deja además un evento en `org_outbox` con la foto completa de la
unidad (y sus capacidades): el motor de replicación lo lleva al servidor
central. Nunca confirma: la frontera transaccional es de quien llama.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from backend.domain.organization.org_unit import (
    Capability,
    OrgUnit,
    OrgUnitStatus,
    OrgUnitType,
    suggest_code,
)
from backend.infrastructure.db.transaction import TransactionalUnitOfWork
from backend.shared.ids import new_uuid

_COLS = ("id, company_id, parent_id, unit_type, code, name, status, created_by, closed_at,"
         " created_at, updated_at")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _table_exists(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (name,)).fetchone() is not None


def org_unit_snapshot(unit: OrgUnit, capabilities) -> dict:
    """Foto de la unidad que viaja en cada evento (transferencia de estado: el
    servidor central se queda con la más reciente por `updated_at`). Sin clave
    `branch_id`: el sobre lleva la sucursal de la ESTACIÓN que hizo el cambio."""
    return {"unit_id": unit.id, "company_id": unit.company_id, "parent_id": unit.parent_id,
            "unit_type": unit.unit_type.value, "code": unit.code, "name": unit.name,
            "status": unit.status.value, "closed_at": unit.closed_at,
            "is_operating_site": unit.unit_type.is_operating_site,
            "capabilities": sorted(c.value for c in capabilities),
            "updated_at": unit.updated_at}


def _row_to_unit(row) -> OrgUnit:
    return OrgUnit(id=str(row[0]), company_id=str(row[1]),
                   parent_id=str(row[2]) if row[2] else None,
                   unit_type=OrgUnitType(row[3]), code=row[4], name=row[5],
                   status=OrgUnitStatus(row[6]), created_by=row[7], closed_at=row[8],
                   created_at=row[9], updated_at=row[10])


class SqliteOrgUnitRepository:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    # ── lectura ──────────────────────────────────────────────────────────
    def get(self, unit_id: str) -> OrgUnit | None:
        fila = self._conn.execute(f"SELECT {_COLS} FROM org_units WHERE id=?",
                                  (str(unit_id),)).fetchone()
        return _row_to_unit(fila) if fila else None

    def get_by_code(self, company_id: str, code: str) -> OrgUnit | None:
        fila = self._conn.execute(
            f"SELECT {_COLS} FROM org_units WHERE company_id=? AND code=?",
            (str(company_id), str(code).strip().upper())).fetchone()
        return _row_to_unit(fila) if fila else None

    def list_for_company(self, company_id: str) -> list[OrgUnit]:
        return [_row_to_unit(r) for r in self._conn.execute(
            f"SELECT {_COLS} FROM org_units WHERE company_id=? ORDER BY name, code",
            (str(company_id),))]

    def active_children_count(self, unit_id: str) -> int:
        return int(self._conn.execute(
            "SELECT COUNT(*) FROM org_units WHERE parent_id=? AND status='ACTIVE'",
            (str(unit_id),)).fetchone()[0])

    def ancestor_ids(self, unit_id: str) -> list[str]:
        """Cadena hacia arriba, del superior inmediato a la raíz (sin la unidad)."""
        filas = self._conn.execute(
            "WITH RECURSIVE up(id, parent_id, depth) AS ("
            "  SELECT id, parent_id, 0 FROM org_units WHERE id=?"
            "  UNION ALL SELECT u.id, u.parent_id, up.depth + 1 FROM org_units u"
            "  JOIN up ON u.id = up.parent_id WHERE up.depth < 64)"
            " SELECT id FROM up WHERE depth > 0 ORDER BY depth", (str(unit_id),)).fetchall()
        return [str(r[0]) for r in filas]

    def descendant_ids(self, unit_id: str) -> list[str]:
        """La unidad y todo lo que cuelga de ella."""
        filas = self._conn.execute(
            "WITH RECURSIVE down(id, depth) AS ("
            "  SELECT id, 0 FROM org_units WHERE id=?"
            "  UNION ALL SELECT u.id, down.depth + 1 FROM org_units u"
            "  JOIN down ON u.parent_id = down.id WHERE down.depth < 64)"
            " SELECT id FROM down ORDER BY depth", (str(unit_id),)).fetchall()
        return [str(r[0]) for r in filas]

    def capabilities(self, unit_id: str) -> frozenset[Capability]:
        return frozenset(Capability(r[0]) for r in self._conn.execute(
            "SELECT capability FROM org_unit_capabilities WHERE org_unit_id=?",
            (str(unit_id),)))

    def site_capabilities(self, site_id: str) -> frozenset[str] | None:
        """Capacidades del sitio para la sesión; `None` si la base no tiene
        estructura organizacional o el sitio no tiene unidad (no se restringe)."""
        if not site_id or not _table_exists(self._conn, "org_units"):
            return None
        if self.get(site_id) is None:
            return None
        return frozenset(c.value for c in self.capabilities(site_id))

    def capabilities_by_unit(self, company_id: str) -> dict[str, frozenset[Capability]]:
        resultado: dict[str, set[Capability]] = {}
        for uid, cap in self._conn.execute(
                "SELECT c.org_unit_id, c.capability FROM org_unit_capabilities c"
                " JOIN org_units u ON u.id = c.org_unit_id WHERE u.company_id=?",
                (str(company_id),)):
            resultado.setdefault(str(uid), set()).add(Capability(cap))
        return {k: frozenset(v) for k, v in resultado.items()}

    def site_code_taken_by_other_branch(self, code: str, unit_id: str) -> bool:
        """El código ya lo usa el perfil de OTRA sucursal (`branch_profiles`)."""
        fila = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='branch_profiles'"
        ).fetchone()
        if fila is None:
            return False
        return self._conn.execute(
            "SELECT 1 FROM branch_profiles WHERE upper(code)=? AND branch_id<>?",
            (str(code).strip().upper(), str(unit_id))).fetchone() is not None

    def open_cash_shifts(self, site_id: str) -> int:
        if self._conn.execute("SELECT 1 FROM sqlite_master WHERE type='table'"
                              " AND name='cash_shifts'").fetchone() is None:
            return 0
        return int(self._conn.execute(
            "SELECT COUNT(*) FROM cash_shifts WHERE branch_id=?"
            " AND status NOT IN ('CLOSED','FORCE_CLOSED')", (str(site_id),)).fetchone()[0])

    def installation_branch_id(self) -> str | None:
        fila = self._conn.execute(
            "SELECT valor FROM configuraciones WHERE clave='sucursal_instalacion_id'"
        ).fetchone() if self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='configuraciones'"
        ).fetchone() else None
        return str(fila[0]) if fila and fila[0] else None

    # ── escritura ────────────────────────────────────────────────────────
    def save(self, unit: OrgUnit) -> None:
        self._conn.execute(
            f"INSERT INTO org_units ({_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET parent_id=excluded.parent_id,"
            " code=excluded.code, name=excluded.name, status=excluded.status,"
            " closed_at=excluded.closed_at, updated_at=excluded.updated_at",
            (unit.id, unit.company_id, unit.parent_id, unit.unit_type.value, unit.code,
             unit.name, unit.status.value, unit.created_by, unit.closed_at, unit.created_at,
             unit.updated_at))
        if unit.unit_type.is_operating_site:
            self._save_site(unit)

    def _save_site(self, unit: OrgUnit) -> None:
        """La fila de `sucursales` del sitio: mismo id, nombre y si opera."""
        activa = 1 if unit.status is OrgUnitStatus.ACTIVE else 0
        existe = self._conn.execute("SELECT 1 FROM sucursales WHERE id=?",
                                    (unit.id,)).fetchone()
        if existe:
            self._conn.execute("UPDATE sucursales SET nombre=?, activa=? WHERE id=?",
                               (unit.name, activa, unit.id))
        else:
            self._conn.execute("INSERT INTO sucursales (id, nombre, activa) VALUES (?,?,?)",
                               (unit.id, unit.name, activa))
        self._save_branch_profile(unit, activa)

    def _save_branch_profile(self, unit: OrgUnit, activa: int) -> None:
        """El perfil de la sucursal comparte código y nombre con la unidad; el
        horario, los tickets y lo demás siguen siendo del perfil."""
        if not _table_exists(self._conn, "branch_profiles"):
            return
        ahora = _utcnow()
        if self._conn.execute("SELECT 1 FROM branch_profiles WHERE branch_id=?",
                              (unit.id,)).fetchone():
            self._conn.execute(
                "UPDATE branch_profiles SET code=?, name=?, active=?, updated_at=?"
                " WHERE branch_id=?", (unit.code, unit.name, activa, ahora, unit.id))
            return
        zona, region = "", ""
        if _table_exists(self._conn, "company_profiles"):
            fila = self._conn.execute(
                "SELECT default_timezone, default_locale FROM company_profiles WHERE id=?",
                (unit.company_id,)).fetchone()
            if fila:
                zona, region = str(fila[0] or ""), str(fila[1] or "")
        self._conn.execute(
            "INSERT INTO branch_profiles (id, branch_id, code, name, timezone, locale, active,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (unit.id, unit.id, unit.code, unit.name, zona, region, activa, ahora, ahora))

    def emit(self, unit: OrgUnit, event_name: str, *, actor: str | None = None,
             operation_id: str | None = None) -> None:
        """Evento con la foto de la unidad en `org_outbox` (misma transacción)."""
        if not _table_exists(self._conn, "org_outbox"):
            return
        ahora = _utcnow()
        evento = {"event_id": new_uuid(), "event_name": event_name,
                  "operation_id": operation_id or new_uuid(), "entity_id": unit.id,
                  "branch_id": None, "user_id": actor or None, "timestamp": ahora,
                  "payload": org_unit_snapshot(unit, self.capabilities(unit.id))}
        self._conn.execute(
            "INSERT INTO org_outbox (id, event_name, aggregate_type, entity_id, payload_json,"
            " operation_id, created_at) VALUES (?,?,?,?,?,?,?)",
            (new_uuid(), event_name, "org_unit", unit.id, json.dumps(evento, sort_keys=True),
             evento["operation_id"], ahora))

    def grant_capability(self, unit_id: str, capability: Capability, *, actor: str | None,
                         reason: str) -> bool:
        cursor = self._conn.execute(
            "INSERT OR IGNORE INTO org_unit_capabilities (org_unit_id, capability, granted_by,"
            " reason, granted_at) VALUES (?,?,?,?,?)",
            (str(unit_id), capability.value, actor, reason, _utcnow()))
        return cursor.rowcount > 0

    def revoke_capability(self, unit_id: str, capability: Capability) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM org_unit_capabilities WHERE org_unit_id=? AND capability=?",
            (str(unit_id), capability.value))
        return cursor.rowcount > 0


def register_initial_site(connection: Any, *, company_id: str, branch_id: str,
                          name: str) -> OrgUnit | None:
    """Unidad de la primera sucursal, al aprovisionar la instalación (todavía no
    existe ningún usuario que autorizar). Mismo id que la fila de `sucursales`
    y todas las capacidades: igual que el respaldo de la migración 351. Se une a
    la transacción de quien llama; idempotente."""
    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table'"
                          " AND name='org_units'").fetchone() is None:
        return None
    unidades = SqliteOrgUnitRepository(connection)
    existente = unidades.get(branch_id)
    if existente is not None:
        return existente
    tomados = {u.code for u in unidades.list_for_company(company_id)}
    unidad = OrgUnit.create(company_id=company_id, unit_type=OrgUnitType.RETAIL_BRANCH,
                            code=suggest_code(name, tomados), name=name, unit_id=branch_id)
    unidades.save(unidad)
    for cap in Capability:
        unidades.grant_capability(unidad.id, cap, actor=None,
                                  reason="Sucursal inicial de la instalación")
    unidades.emit(unidad, "ORG_UNIT_CREATED")
    return unidad


class OrgStructureUnitOfWork(TransactionalUnitOfWork):
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.units = SqliteOrgUnitRepository(connection)
        self._completed = False


__all__ = ["OrgStructureUnitOfWork", "SqliteOrgUnitRepository", "org_unit_snapshot",
           "register_initial_site"]
