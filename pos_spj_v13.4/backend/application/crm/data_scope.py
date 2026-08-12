"""CRMDataScopeResolver — OWN/TEAM scope for leads, opportunities and cases
(CRM-2, master prompt §60, §64-67).

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


@dataclass(frozen=True)
class CRMDataScope:
    axis: str  # OWN | TEAM
    owner_user_id: str | None = None
    team_member_ids: tuple[str, ...] = field(default_factory=tuple)


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
            if self._checker.has_permission(context.user_id, permission):
                if axis == "OWN":
                    return CRMDataScope(axis=axis, owner_user_id=context.user_id)
                members = context.team_member_ids or (context.user_id,)
                return CRMDataScope(axis=axis, team_member_ids=tuple(members))

        raise CRMScopeError(
            f"El usuario {context.user_id} no tiene ningún permiso de lectura "
            "en este alcance (ver.propia/ver.equipo)")
