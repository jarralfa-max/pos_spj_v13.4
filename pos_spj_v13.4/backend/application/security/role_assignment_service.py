"""Roles adicionales con ámbito: otorgar, revocar y consultar (auditoría
enterprise, Fase 2; decisión D4).

La única puerta de la pantalla. Autoriza en la capa de aplicación
(`CONFIGURACION.usuario.ver` para ver, `CONFIGURACION.usuario.asignaciones` para
cambiar), abre la transacción, sube la versión de concesiones (las sesiones
abiertas recargan sus permisos y roles, PER-08) y anota en `audit_logs`.

Reglas contra el escalamiento (las mismas que ya rigen el rol principal):

* nadie se otorga ni se revoca roles a sí mismo;
* el rol de dueño no se otorga por asignación (es el rol principal de UNA cuenta);
* sólo quien tiene acceso total otorga o revoca un rol de acceso total;
* quien no tiene acceso total sólo otorga roles cuyos permisos ya tiene él.

El ámbito tiene que existir: `COMPANY` es la empresa de esta instalación;
`ORG_UNIT`, una unidad activa de esa empresa.
"""

from __future__ import annotations

from datetime import date
from typing import Callable

from backend.application.configuracion.permissions import ConfiguracionPermissions as P
from backend.application.organization.org_structure_service import (
    OrgStructureQueryService,
    resolve_company_id,
)
from backend.application.security.permission_query_service import PermissionQueryService
from backend.domain.organization.org_unit import OrgUnitStatus
from backend.domain.organization.role_assignment import (
    RoleAssignment,
    RoleAssignmentError,
    ScopeType,
)
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)
from backend.infrastructure.db.repositories.security.role_assignment_repository import (
    RoleAssignmentUnitOfWork,
    SqliteRoleAssignmentRepository,
)
from backend.security.permissions.codes import is_granted, normalize_permission
from backend.security.permissions.principals import is_full_access_role, is_owner_role
from backend.shared.ids import new_uuid

AUDIT_ENTITY = "user_role_assignment"


class RoleAssignmentService:
    def __init__(self, connection, *, authorization, actor: Callable[[], str],
                 audit_log=None, grant_versions=None) -> None:
        self._conn = connection
        self._authorization = authorization
        self._actor = actor
        self._audit = audit_log
        self._grants = grant_versions
        self._permissions = PermissionQueryService(SqlitePermissionRepository(connection))

    def _require(self, permiso: str) -> str:
        actor = str(self._actor() or "")
        self._authorization.require(actor, permiso)
        return actor

    # ── lectura ──────────────────────────────────────────────────────────
    def list_for_user(self, user_id: str) -> list[dict]:
        self._require(P.USUARIOS_VIEW)
        repo = SqliteRoleAssignmentRepository(self._conn)
        return repo.list_for_user(user_id) if repo.available() else []

    def role_options(self) -> list[tuple[str, str]]:
        """Roles que se pueden otorgar (el de dueño nunca: es de UNA cuenta)."""
        self._require(P.USUARIOS_VIEW)
        return [(str(r["id"]), str(r["nombre"]))
                for r in SqliteRoleAssignmentRepository(self._conn).roles()
                if not is_owner_role(r["nombre"])]

    def scope_options(self) -> list[tuple[str, str, str]]:
        """`(scope_type, scope_id, etiqueta)` para el selector de ámbito."""
        self._require(P.USUARIOS_VIEW)
        empresa = resolve_company_id(self._conn)
        opciones = [("COMPANY", empresa, "Toda la empresa")] if empresa else []
        if empresa:
            for nodo in OrgStructureQueryService(self._conn).tree(empresa):
                if nodo.unit.status is OrgUnitStatus.ACTIVE:
                    opciones.append(("ORG_UNIT", nodo.unit.id, "  " * nodo.depth
                                     + f"{nodo.unit.name} ({nodo.unit.unit_type.label})"))
        return opciones

    # ── comandos ─────────────────────────────────────────────────────────
    def assign(self, *, user_id: str, role_id: str, scope_type: ScopeType | str,
               scope_id: str, reason: str, valid_from: date | None = None,
               valid_until: date | None = None) -> RoleAssignment:
        actor = self._require(P.USUARIOS_ASIGNACIONES)
        asignacion = RoleAssignment.create(
            user_id=user_id, role_id=role_id, scope_type=scope_type, scope_id=scope_id,
            reason=reason, valid_from=valid_from, valid_until=valid_until,
            granted_by=actor or None)
        with RoleAssignmentUnitOfWork(self._conn) as uow:
            repo = uow.assignments
            if not repo.available():
                raise RoleAssignmentError("Falta la migración 353 (asignaciones de rol)")
            if not repo.user_exists(asignacion.user_id):
                raise RoleAssignmentError("El usuario no existe")
            rol = repo.role(asignacion.role_id)
            if rol is None:
                raise RoleAssignmentError("El rol no existe")
            self._check_escalation(actor, asignacion.user_id, rol["nombre"])
            self._check_scope(asignacion)
            if repo.active_duplicate(asignacion):
                raise RoleAssignmentError(f"Ya tiene el rol «{rol['nombre']}» en ese ámbito")
            repo.save(asignacion)
            self._after(actor, "ROLE_ASSIGNMENT_GRANTED", asignacion, rol["nombre"],
                        asignacion.reason)
        return asignacion

    def revoke(self, assignment_id: str, *, reason: str) -> RoleAssignment:
        actor = self._require(P.USUARIOS_ASIGNACIONES)
        with RoleAssignmentUnitOfWork(self._conn) as uow:
            asignacion = uow.assignments.get(assignment_id)
            if asignacion is None:
                raise RoleAssignmentError("La asignación no existe")
            rol = uow.assignments.role(asignacion.role_id) or {"nombre": ""}
            self._check_escalation(actor, asignacion.user_id, rol["nombre"])
            asignacion.revoke(by=actor or None, reason=reason)
            uow.assignments.save(asignacion)
            self._after(actor, "ROLE_ASSIGNMENT_REVOKED", asignacion, rol["nombre"],
                        asignacion.revoke_reason or "")
        return asignacion

    # ── reglas ───────────────────────────────────────────────────────────
    def _check_escalation(self, actor: str, user_id: str, role_name: str) -> None:
        if actor and actor == str(user_id):
            raise RoleAssignmentError("Nadie se otorga ni se revoca roles a sí mismo")
        if is_owner_role(role_name):
            raise RoleAssignmentError("El rol de dueño no se otorga por asignación")
        roles_actor = self._permissions.roles_for(actor) if actor else ()
        acceso_total = any(is_full_access_role(r) for r in roles_actor)
        if is_full_access_role(role_name):
            if not acceso_total:
                raise RoleAssignmentError(
                    "Sólo un administrador o el dueño otorga o revoca un rol con acceso total")
            return
        if acceso_total:
            return
        repo = SqlitePermissionRepository(self._conn)
        rol_id = repo.role_id_for_name(role_name)
        del_rol = repo.role_permission_codes(rol_id) if rol_id else frozenset()
        mios = self._permissions.permission_codes_for_user(actor)
        faltan = sorted(c for c in del_rol if not is_granted(mios, normalize_permission(c)))
        if faltan:
            raise RoleAssignmentError(
                "No puede otorgar un rol con permisos que usted no tiene: "
                + ", ".join(faltan[:5]) + ("…" if len(faltan) > 5 else ""))

    def _check_scope(self, a: RoleAssignment) -> None:
        empresa = resolve_company_id(self._conn)
        if a.scope_type is ScopeType.COMPANY:
            if not empresa or a.scope_id != empresa:
                raise RoleAssignmentError("El ámbito «toda la empresa» debe ser esta empresa")
            return
        unidad = OrgStructureQueryService(self._conn).get(a.scope_id)
        if unidad is None or unidad.status is not OrgUnitStatus.ACTIVE:
            raise RoleAssignmentError("La unidad organizacional no existe o no está activa")
        if empresa and unidad.company_id != empresa:
            raise RoleAssignmentError("La unidad es de otra empresa")

    def _after(self, actor: str, accion: str, a: RoleAssignment, role_name: str,
               motivo: str) -> None:
        if self._grants is not None:
            self._grants.bump()
        if self._audit is not None:
            self._audit.record(
                action=accion, entity=AUDIT_ENTITY, entity_id=a.id, actor=actor,
                operation_id=new_uuid(), details=motivo,
                after={"user_id": a.user_id, "role": role_name, "scope_type": a.scope_type.value,
                       "scope_id": a.scope_id, "status": a.status.value,
                       "valid_from": a.valid_from.isoformat() if a.valid_from else None,
                       "valid_until": a.valid_until.isoformat() if a.valid_until else None})


__all__ = ["RoleAssignmentService"]
