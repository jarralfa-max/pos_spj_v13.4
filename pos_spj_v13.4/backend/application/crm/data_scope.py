"""CRMDataScopeResolver — OWN/TEAM/BRANCH/COMPANY scope for leads,
opportunities and cases (CRM-2, master prompt §60, §64-67).

CRM-43 (2026-10-08, re-auditoría sobre la base real): con sólo OWN/TEAM y un
equipo que nadie arma, ``TEAM`` degeneraba en "sólo yo" — hasta el dueño veía
únicamente lo asignado a sí mismo, y un prospecto recién creado (sin asignar)
no aparecía en NINGÚN directorio. Se añaden los ejes ``BRANCH`` (la sucursal
activa de la sesión) y ``COMPANY`` (toda la empresa), con códigos propios por
entidad (``CRM.<entidad>.ver.sucursal``/``.ver.compania``): no pueden
compartir ``CLIENTES.ver.compania`` porque los clientes son globales para
todos los roles con acceso y los prospectos de un cajero no.
``OWN`` incluye además lo que el usuario CREÓ y sigue sin responsable.

Same shape and fail-closed rules as
``backend/application/customers/data_scope.py::CustomerDataScopeResolver``;
kept as a separate resolver because the CRM permission catalog only defines
OWN/TEAM view axes for leads/opportunities/cases (no BRANCH/TERRITORY/
PORTFOLIO/COMPANY sub-permissions were specified for those three entities —
see ``CRMPermissions``). Company-wide CRM oversight is granted through
``CustomerPermissions.VIEW_COMPANY`` (one COMPANY axis for the whole
Clientes/CRM module) rather than duplicated per entity here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from backend.domain.crm.exceptions import CRMConfigurationError, CRMScopeError


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


@dataclass(frozen=True)
class CRMScopeContext:
    user_id: str
    team_member_ids: tuple[str, ...] = field(default_factory=tuple)
    #: Sucursales sobre las que actúa la sesión (la activa). Vacío → el eje
    #: BRANCH no puede resolverse y se cae al siguiente más estrecho.
    branch_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CRMDataScope:
    axis: str  # OWN | TEAM | BRANCH | COMPANY
    owner_user_id: str | None = None
    team_member_ids: tuple[str, ...] = field(default_factory=tuple)
    branch_ids: tuple[str, ...] = field(default_factory=tuple)

    def includes(self, *, responsible_user_id: str | None,
                 created_by_user_id: str | None = None,
                 branch_id: str | None = None) -> bool:
        """¿El registro cae dentro de este alcance?

        Un registro sin responsable pertenece a quien lo creó (si no, nadie
        con alcance OWN/TEAM podría volver a verlo después de darlo de alta).
        """
        if self.axis == "COMPANY":
            return True
        if self.axis == "BRANCH":
            return branch_id is not None and branch_id in self.branch_ids
        members = ((self.owner_user_id,) if self.axis == "OWN" else self.team_member_ids)
        if responsible_user_id:
            return responsible_user_id in members
        return bool(created_by_user_id) and created_by_user_id in members


class CRMDataScopeResolver:
    def __init__(self, checker: PermissionChecker | None) -> None:
        self._checker = checker

    def resolve_view_scope(
        self, context: CRMScopeContext, scope_permissions: tuple[tuple[str, str], ...]
    ) -> CRMDataScope:
        """``scope_permissions`` is one of CRMPermissions'
        ``LEAD_VIEW_SCOPE_PERMISSIONS`` / ``OPPORTUNITY_VIEW_SCOPE_PERMISSIONS``
        / ``CASE_VIEW_SCOPE_PERMISSIONS`` — narrowest → widest, same
        convention as ``CUSTOMER_VIEW_SCOPE_PERMISSIONS``."""
        if self._checker is None:
            raise CRMConfigurationError("CRMDataScopeResolver requiere un PermissionChecker")
        if not context.user_id:
            raise CRMScopeError("Operación sin usuario autenticado")

        for axis, permission in reversed(scope_permissions):
            if not self._checker.has_permission(context.user_id, permission):
                continue
            if axis == "COMPANY":
                return CRMDataScope(axis=axis)
            if axis == "BRANCH":
                branches = tuple(b for b in context.branch_ids if b)
                if not branches:
                    continue  # sin sucursal activa no hay alcance de sucursal
                return CRMDataScope(axis=axis, branch_ids=branches)
            if axis == "OWN":
                return CRMDataScope(axis=axis, owner_user_id=context.user_id)
            members = context.team_member_ids or (context.user_id,)
            return CRMDataScope(axis=axis, team_member_ids=tuple(members))

        raise CRMScopeError(
            f"El usuario {context.user_id} no tiene ningún permiso de lectura "
            "en este alcance (ver.propia/ver.equipo/ver.sucursal/ver.compania)")
