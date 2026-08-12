"""CustomerDataScopeResolver — turns a granted permission into a data filter
(CRM-2, master prompt §60).

No formal scope resolver exists anywhere in this codebase yet (see
docs/architecture/CRM_0_CUSTOMER_MASTER_AUDIT.md §9): CAJA/INVENTARIO/COMPRAS
only went as far as defining ``ver.sucursal_propia``-style permission codes —
nothing turns them into an actual query filter. This is the first one, built
for the Customer Master's six-axis scope (OWN/TEAM/BRANCH/TERRITORY/
PORTFOLIO/COMPANY) so a future ``CustomerDirectoryQueryService`` (CRM-3+) has
something concrete to call instead of improvising per query.

The resolver does no I/O itself — it takes an already-assembled
``CustomerScopeContext`` (who is the branch/territory/portfolio/team for this
request) and a ``PermissionChecker`` (same Protocol as
``InventoryAuthorizationPolicy``), and returns the *widest* scope the user's
grants allow. Fail closed: no matching permission → ``CustomerScopeError``;
a granted axis whose context value is missing (e.g. BRANCH granted but no
active branch) → ``CustomerConfigurationError``, never a silent unrestricted
fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from backend.application.customers.permissions import CUSTOMER_VIEW_SCOPE_PERMISSIONS
from backend.domain.customers.exceptions import (
    CustomerConfigurationError,
    CustomerScopeError,
)


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


@dataclass(frozen=True)
class CustomerScopeContext:
    """Values already known about the requesting session — the resolver
    does not look any of these up."""

    user_id: str
    branch_id: str | None = None
    territory_id: str | None = None
    portfolio_id: str | None = None
    team_member_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CustomerDataScope:
    """What a CustomerDirectoryQueryService (or similar) should filter by."""

    axis: str  # OWN | TEAM | BRANCH | TERRITORY | PORTFOLIO | COMPANY
    owner_user_id: str | None = None
    team_member_ids: tuple[str, ...] = field(default_factory=tuple)
    branch_id: str | None = None
    territory_id: str | None = None
    portfolio_id: str | None = None


class CustomerDataScopeResolver:
    def __init__(self, checker: PermissionChecker | None) -> None:
        self._checker = checker

    def resolve_view_scope(self, context: CustomerScopeContext) -> CustomerDataScope:
        if self._checker is None:
            raise CustomerConfigurationError(
                "CustomerDataScopeResolver requiere un PermissionChecker")
        if not context.user_id:
            raise CustomerScopeError("Operación sin usuario autenticado")

        # Widest → narrowest: the first granted axis wins.
        for axis, permission in reversed(CUSTOMER_VIEW_SCOPE_PERMISSIONS):
            if self._checker.has_permission(context.user_id, permission):
                return self._build_scope(axis, context)

        raise CustomerScopeError(
            f"El usuario {context.user_id} no tiene ningún permiso de lectura "
            "de clientes (ver.propia/equipo/sucursal/territorio/cartera/compania)")

    def _build_scope(self, axis: str, context: CustomerScopeContext) -> CustomerDataScope:
        if axis == "OWN":
            return CustomerDataScope(axis=axis, owner_user_id=context.user_id)
        if axis == "TEAM":
            members = context.team_member_ids or (context.user_id,)
            return CustomerDataScope(axis=axis, team_member_ids=tuple(members))
        if axis == "BRANCH":
            if not context.branch_id:
                raise CustomerConfigurationError(
                    "Alcance BRANCH otorgado pero la sesión no tiene sucursal activa")
            return CustomerDataScope(axis=axis, branch_id=context.branch_id)
        if axis == "TERRITORY":
            if not context.territory_id:
                raise CustomerConfigurationError(
                    "Alcance TERRITORY otorgado pero no hay territorio en contexto")
            return CustomerDataScope(axis=axis, territory_id=context.territory_id)
        if axis == "PORTFOLIO":
            if not context.portfolio_id:
                raise CustomerConfigurationError(
                    "Alcance PORTFOLIO otorgado pero no hay cartera en contexto")
            return CustomerDataScope(axis=axis, portfolio_id=context.portfolio_id)
        # COMPANY: no filter — sees everything.
        return CustomerDataScope(axis=axis)
