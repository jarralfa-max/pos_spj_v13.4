"""Persistencia de la estructura organizacional (tablas de la migración 351).

Un sitio de operación vive en DOS filas con el mismo id: `org_units` (tipo,
jerarquía, estado) y `sucursales` (la identidad que ya usan todos los módulos).
Este repositorio las mantiene juntas: crear, renombrar, desactivar o cerrar un
sitio también escribe su fila de `sucursales`. Nunca confirma: la frontera
transaccional es de quien llama.
"""

from __future__ import annotations

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

_COLS = ("id, company_id, parent_id, unit_type, code, name, status, created_by, closed_at,"
         " created_at, updated_at")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
    return unidad


class OrgStructureUnitOfWork(TransactionalUnitOfWork):
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.units = SqliteOrgUnitRepository(connection)
        self._completed = False


__all__ = ["OrgStructureUnitOfWork", "SqliteOrgUnitRepository", "register_initial_site"]
