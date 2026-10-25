"""Estructura organizacional: consulta y comandos (auditoría enterprise, Fase 1).

* `OrgStructureQueryService` — lectura interna para otros contextos: árbol,
  descendientes (herencia de alcance, Fase 2), sitios bajo una unidad
  (consolidación financiera, Fase 3) y capacidades. No autoriza: quien lo usa ya
  decidió qué puede ver el actor.
* `OrgStructureService` — la ÚNICA puerta de la pantalla. Autoriza cada lectura
  y cada comando con `CONFIGURACION.organizacion.*` en la capa de aplicación
  (no en la UI), abre la transacción y anota en `audit_logs` antes/después.

Crear una unidad de sitio (sucursal, planta, CEDIS…) crea también su fila de
`sucursales` con el mismo id: es la primera vía de la aplicación para dar de
alta una sucursal nueva (N12). El perfil de la sucursal (`branch_profiles`) se
sigue registrando en «Empresa y sucursales», como hoy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from backend.application.configuracion.permissions import ConfiguracionPermissions as P
from backend.domain.organization.org_unit import (
    SUGGESTED_CAPABILITIES,
    Capability,
    OrgUnit,
    OrgUnitError,
    OrgUnitStatus,
    OrgUnitType,
    check_capabilities,
)
from backend.infrastructure.db.repositories.organization.org_unit_repository import (
    OrgStructureUnitOfWork,
    SqliteOrgUnitRepository,
    register_initial_site,
)
from backend.shared.ids import new_uuid

AUDIT_ENTITY = "org_unit"


def resolve_company_id(connection: Any) -> str | None:
    """La organización de esta instalación: `installation.company_id`; si la
    instalación no la tiene, el único perfil de empresa activo (un solo RFC)."""
    def _hay(tabla: str) -> bool:
        return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                                  (tabla,)).fetchone() is not None
    if _hay("installation"):
        fila = connection.execute("SELECT company_id FROM installation"
                                  " WHERE company_id IS NOT NULL LIMIT 1").fetchone()
        if fila and fila[0]:
            return str(fila[0])
    if _hay("company_profiles"):
        filas = connection.execute("SELECT id FROM company_profiles WHERE active=1").fetchall()
        if len(filas) == 1:
            return str(filas[0][0])
    return None


@dataclass(frozen=True)
class OrgUnitNode:
    unit: OrgUnit
    depth: int
    capabilities: frozenset[Capability]
    is_installation_site: bool = False


class OrgStructureQueryService:
    def __init__(self, connection: Any) -> None:
        self._units = SqliteOrgUnitRepository(connection)

    def tree(self, company_id: str) -> list[OrgUnitNode]:
        """Recorrido en profundidad: cada unidad seguida de sus dependientes."""
        unidades = self._units.list_for_company(company_id)
        capacidades = self._units.capabilities_by_unit(company_id)
        instalacion = self._units.installation_branch_id()
        por_padre: dict[str | None, list[OrgUnit]] = {}
        ids = {u.id for u in unidades}
        for u in unidades:
            # Un superior de otra empresa o inexistente no debe esconder la unidad.
            por_padre.setdefault(u.parent_id if u.parent_id in ids else None, []).append(u)
        salida: list[OrgUnitNode] = []

        def _visitar(padre: str | None, nivel: int) -> None:
            for u in por_padre.get(padre, []):
                salida.append(OrgUnitNode(u, nivel, capacidades.get(u.id, frozenset()),
                                          u.id == instalacion))
                if nivel < 64:
                    _visitar(u.id, nivel + 1)

        _visitar(None, 0)
        return salida

    def get(self, unit_id: str) -> OrgUnit | None:
        return self._units.get(unit_id)

    def descendant_ids(self, unit_id: str) -> list[str]:
        return self._units.descendant_ids(unit_id)

    def operating_site_ids_under(self, unit_id: str, *, active_only: bool = True) -> list[str]:
        """Ids de sitio (= `branch_id`) de la unidad y todo lo que cuelga de ella."""
        salida = []
        for uid in self._units.descendant_ids(unit_id):
            u = self._units.get(uid)
            if u is None or not u.unit_type.is_operating_site:
                continue
            if active_only and u.status is not OrgUnitStatus.ACTIVE:
                continue
            salida.append(u.id)
        return salida

    def has_capability(self, unit_id: str, capability: Capability) -> bool:
        return capability in self._units.capabilities(unit_id)


class OrgStructureService:
    def __init__(self, connection: Any, *, authorization, actor: Callable[[], str],
                 audit_log=None, company_id: str | None = None) -> None:
        self._conn = connection
        self._authorization = authorization
        self._actor = actor
        self._audit = audit_log
        self._company_id = company_id
        self._query = OrgStructureQueryService(connection)

    # ── apoyo ────────────────────────────────────────────────────────────
    def _require(self, permiso: str) -> str:
        actor = str(self._actor() or "")
        self._authorization.require(actor, permiso)
        return actor

    def can(self, permiso: str) -> bool:
        return bool(self._authorization.has_permission(str(self._actor() or ""), permiso))

    def company_id(self) -> str:
        empresa = self._company_id or resolve_company_id(self._conn)
        if not empresa:
            raise OrgUnitError("Registre primero la empresa en «Empresa y sucursales»")
        self._company_id = empresa
        return empresa

    def _load(self, uow: OrgStructureUnitOfWork, unit_id: str) -> OrgUnit:
        unidad = uow.units.get(unit_id)
        if unidad is None or unidad.company_id != self.company_id():
            raise OrgUnitError("Unidad organizacional no encontrada")
        return unidad

    def _record(self, *, action: str, unit: OrgUnit, actor: str, before: dict | None,
                reason: str = "") -> None:
        if self._audit is None:
            return
        self._audit.record(
            action=action, entity=AUDIT_ENTITY, entity_id=unit.id, actor=actor,
            operation_id=new_uuid(), details=reason, before=before, after=_snapshot(unit),
            branch_id=unit.id if unit.unit_type.is_operating_site else None)

    @staticmethod
    def _reason(reason: str) -> str:
        motivo = str(reason or "").strip()
        if not motivo:
            raise OrgUnitError("Indique el motivo")
        return motivo

    # ── lectura ──────────────────────────────────────────────────────────
    def tree(self) -> list[OrgUnitNode]:
        self._require(P.ORGANIZACION_VIEW)
        empresa = self._company_id or resolve_company_id(self._conn)
        return self._query.tree(empresa) if empresa else []

    # ── comandos ─────────────────────────────────────────────────────────
    def create_unit(self, *, unit_type: OrgUnitType | str, code: str, name: str,
                    parent_id: str | None = None,
                    capabilities: Iterable[Capability | str] | None = None) -> OrgUnit:
        actor = self._require(P.ORGANIZACION_CREAR)
        tipo = OrgUnitType(unit_type)
        caps = (SUGGESTED_CAPABILITIES[tipo] if capabilities is None
                else frozenset(Capability(c) for c in capabilities))
        check_capabilities(tipo, caps)
        empresa = self.company_id()
        with OrgStructureUnitOfWork(self._conn) as uow:
            padre = self._load(uow, parent_id) if parent_id else None
            unidad = OrgUnit.create(company_id=empresa, unit_type=tipo, code=code, name=name,
                                    parent=padre, created_by=actor or None)
            self._check_code_free(uow, unidad)
            uow.units.save(unidad)
            for cap in sorted(caps, key=lambda c: c.value):
                uow.units.grant_capability(unidad.id, cap, actor=actor or None,
                                           reason=f"Alta de {tipo.label.lower()}")
            self._record(action="ORG_UNIT_CREATED", unit=unidad, actor=actor, before=None)
        return unidad

    def update_unit(self, unit_id: str, *, name: str, code: str | None = None) -> OrgUnit:
        actor = self._require(P.ORGANIZACION_EDITAR)
        with OrgStructureUnitOfWork(self._conn) as uow:
            unidad = self._load(uow, unit_id)
            antes = _snapshot(unidad)
            unidad.rename(name=name, code=code)
            if unidad.code != antes["code"]:
                self._check_code_free(uow, unidad)
            uow.units.save(unidad)
            self._record(action="ORG_UNIT_UPDATED", unit=unidad, actor=actor, before=antes)
        return unidad

    def move_unit(self, unit_id: str, parent_id: str | None) -> OrgUnit:
        actor = self._require(P.ORGANIZACION_EDITAR)
        with OrgStructureUnitOfWork(self._conn) as uow:
            unidad = self._load(uow, unit_id)
            antes = _snapshot(unidad)
            padre = self._load(uow, parent_id) if parent_id else None
            unidad.move_under(padre, ancestors_of_parent=set(
                uow.units.ancestor_ids(padre.id)) if padre else set())
            uow.units.save(unidad)
            self._record(action="ORG_UNIT_MOVED", unit=unidad, actor=actor, before=antes)
        return unidad

    def deactivate(self, unit_id: str, *, reason: str) -> OrgUnit:
        actor = self._require(P.ORGANIZACION_CERRAR)
        motivo = self._reason(reason)
        with OrgStructureUnitOfWork(self._conn) as uow:
            unidad = self._load(uow, unit_id)
            antes = _snapshot(unidad)
            self._check_can_stop(uow, unidad)
            unidad.deactivate(active_children=uow.units.active_children_count(unidad.id))
            uow.units.save(unidad)
            self._record(action="ORG_UNIT_DEACTIVATED", unit=unidad, actor=actor,
                         before=antes, reason=motivo)
        return unidad

    def reactivate(self, unit_id: str, *, reason: str) -> OrgUnit:
        actor = self._require(P.ORGANIZACION_CERRAR)
        motivo = self._reason(reason)
        with OrgStructureUnitOfWork(self._conn) as uow:
            unidad = self._load(uow, unit_id)
            antes = _snapshot(unidad)
            if unidad.parent_id:
                padre = uow.units.get(unidad.parent_id)
                if padre is not None and padre.status is not OrgUnitStatus.ACTIVE:
                    raise OrgUnitError(f"Reactive primero «{padre.name}»")
            unidad.reactivate()
            uow.units.save(unidad)
            self._record(action="ORG_UNIT_REACTIVATED", unit=unidad, actor=actor,
                         before=antes, reason=motivo)
        return unidad

    def close(self, unit_id: str, *, reason: str) -> OrgUnit:
        actor = self._require(P.ORGANIZACION_CERRAR)
        motivo = self._reason(reason)
        with OrgStructureUnitOfWork(self._conn) as uow:
            unidad = self._load(uow, unit_id)
            antes = _snapshot(unidad)
            self._check_can_stop(uow, unidad)
            unidad.close(active_children=uow.units.active_children_count(unidad.id))
            uow.units.save(unidad)
            self._record(action="ORG_UNIT_CLOSED", unit=unidad, actor=actor, before=antes,
                         reason=motivo)
        return unidad

    def set_capability(self, unit_id: str, capability: Capability | str, *, enabled: bool,
                       reason: str) -> frozenset[Capability]:
        actor = self._require(P.ORGANIZACION_CAPACIDADES)
        motivo = self._reason(reason)
        cap = Capability(capability)
        with OrgStructureUnitOfWork(self._conn) as uow:
            unidad = self._load(uow, unit_id)
            if unidad.status is OrgUnitStatus.CLOSED:
                raise OrgUnitError("La unidad está cerrada")
            actuales = uow.units.capabilities(unidad.id)
            nuevas = actuales | {cap} if enabled else actuales - {cap}
            if nuevas == actuales:
                return actuales
            check_capabilities(unidad.unit_type, nuevas)
            if not enabled and cap is Capability.CASH and uow.units.open_cash_shifts(unidad.id):
                raise OrgUnitError("Hay turnos de caja abiertos en esta unidad")
            if enabled:
                uow.units.grant_capability(unidad.id, cap, actor=actor or None, reason=motivo)
            else:
                uow.units.revoke_capability(unidad.id, cap)
            if self._audit is not None:
                self._audit.record(
                    action="ORG_UNIT_CAPABILITY_GRANTED" if enabled
                    else "ORG_UNIT_CAPABILITY_REVOKED",
                    entity=AUDIT_ENTITY, entity_id=unidad.id, actor=actor,
                    operation_id=new_uuid(), details=motivo,
                    before={"capabilities": sorted(c.value for c in actuales)},
                    after={"capabilities": sorted(c.value for c in nuevas)},
                    branch_id=unidad.id if unidad.unit_type.is_operating_site else None)
        return nuevas

    def apply_capability_changes(self, unit_id: str, changes: Iterable[tuple[Capability | str,
                                                                              bool]], *,
                                 reason: str) -> frozenset[Capability]:
        """Varios cambios como UNA operación: si uno no procede, no queda ninguno."""
        self._require(P.ORGANIZACION_CAPACIDADES)
        resultado = SqliteOrgUnitRepository(self._conn).capabilities(unit_id)
        with OrgStructureUnitOfWork(self._conn):
            for capacidad, habilitada in changes:
                resultado = self.set_capability(unit_id, capacidad, enabled=habilitada,
                                                reason=reason)
        return resultado

    # ── reglas que necesitan la base ─────────────────────────────────────
    @staticmethod
    def _check_code_free(uow: OrgStructureUnitOfWork, unidad: OrgUnit) -> None:
        otra = uow.units.get_by_code(unidad.company_id, unidad.code)
        if otra is not None and otra.id != unidad.id:
            raise OrgUnitError(f"El código «{unidad.code}» ya lo usa «{otra.name}»")
        if unidad.unit_type.is_operating_site and uow.units.site_code_taken_by_other_branch(
                unidad.code, unidad.id):
            raise OrgUnitError(f"El código «{unidad.code}» ya lo usa el perfil de otra sucursal")

    @staticmethod
    def _check_can_stop(uow: OrgStructureUnitOfWork, unidad: OrgUnit) -> None:
        if not unidad.unit_type.is_operating_site:
            return
        if unidad.id == uow.units.installation_branch_id():
            raise OrgUnitError("Es la sucursal de esta instalación: cambie primero la sucursal "
                               "de la instalación")
        abiertos = uow.units.open_cash_shifts(unidad.id)
        if abiertos:
            raise OrgUnitError(f"Tiene {abiertos} turno(s) de caja sin cerrar")


def _snapshot(unit: OrgUnit) -> dict:
    return {"code": unit.code, "name": unit.name, "unit_type": unit.unit_type.value,
            "parent_id": unit.parent_id, "status": unit.status.value}


__all__ = ["OrgStructureQueryService", "OrgStructureService", "OrgUnitNode",
           "register_initial_site", "resolve_company_id"]
