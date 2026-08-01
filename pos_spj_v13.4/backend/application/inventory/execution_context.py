"""InventoryExecutionContext — the trusted actor/scope carried into every command.

§5.3: commands and queries must not trust branch/warehouse/location ids sent by the
UI. Instead they receive an ``InventoryExecutionContext`` resolved from the live
session, and validate every target against it via ``InventoryScopePolicy``. The
resolver fails closed (§5.4): no session → AUTHENTICATION_REQUIRED, no active branch
→ BRANCH_CONFIGURATION_REQUIRED — never a fabricated ``"desktop"``/``"1"``/``"MAIN"``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.inventory.exceptions import (
    BranchConfigurationRequiredError,
    InventoryAuthenticationRequiredError,
    WarehouseConfigurationRequiredError,
)
from backend.domain.inventory.policies.scope_policy import InventoryScopePolicy

_SCOPE = InventoryScopePolicy()


@dataclass(frozen=True)
class InventoryExecutionContext:
    """Authenticated actor + resolved scope. Immutable, never built from UI ids."""

    actor_user_id: str
    active_branch_id: str
    assigned_branch_ids: frozenset[str] = field(default_factory=frozenset)
    allowed_warehouse_ids: frozenset[str] = field(default_factory=frozenset)
    permissions: frozenset[str] = field(default_factory=frozenset)
    device_id: str | None = None

    def enforce_branch(self, target_branch_id: str) -> None:
        """Raise BranchScopeError if the actor may not operate on that branch."""
        _SCOPE.enforce_branch_access(
            user_permissions=self.permissions,
            user_branch_id=self.active_branch_id,
            assigned_branch_ids=self.assigned_branch_ids,
            target_branch_id=str(target_branch_id or ""),
        )

    def enforce_warehouse(self, target_warehouse_id: str, *,
                          has_all_warehouses: bool = False) -> None:
        """Raise WarehouseScopeError if the warehouse is outside the actor's reach."""
        target = str(target_warehouse_id or "")
        if not target:
            raise WarehouseConfigurationRequiredError(
                "La operación requiere un almacén válido")
        _SCOPE.enforce_warehouse_access(
            allowed_warehouse_ids=self.allowed_warehouse_ids,
            target_warehouse_id=target,
            has_all_warehouses=has_all_warehouses,
        )


def _as_id_set(value) -> frozenset[str]:
    if not value:
        return frozenset()
    return frozenset(str(v).strip() for v in value if str(v or "").strip())


def resolve_inventory_execution_context(
    session, *, require_branch: bool = True,
) -> InventoryExecutionContext:
    """Build a trusted context from the live session. Fails closed (§5.4).

    Reads identity/scope from the session attributes (``user_id``/``usuario``,
    ``active_branch_id``/``branch_id``/``sucursal_id``, assigned branches, allowed
    warehouses, permissions). No session or no user → AUTHENTICATION_REQUIRED; no
    active branch (when required) → BRANCH_CONFIGURATION_REQUIRED. Never fabricates.
    """
    if session is None:
        raise InventoryAuthenticationRequiredError("Sesión no autenticada")
    user_id = str(getattr(session, "user_id", None)
                  or getattr(session, "usuario", None) or "").strip()
    if not user_id:
        raise InventoryAuthenticationRequiredError("Sesión sin usuario autenticado")
    branch_id = str(getattr(session, "active_branch_id", None)
                    or getattr(session, "branch_id", None)
                    or getattr(session, "sucursal_id", None) or "").strip()
    if require_branch and not branch_id:
        raise BranchConfigurationRequiredError("Sesión sin sucursal activa")

    assigned = _as_id_set(getattr(session, "assigned_branch_ids", None)
                          or getattr(session, "sucursales_asignadas", None))
    warehouses = _as_id_set(getattr(session, "allowed_warehouse_ids", None)
                            or getattr(session, "almacenes_permitidos", None))
    permissions = _as_id_set(getattr(session, "permissions", None)
                             or getattr(session, "permisos", None))
    device_id = getattr(session, "device_id", None)
    return InventoryExecutionContext(
        actor_user_id=user_id,
        active_branch_id=branch_id,
        assigned_branch_ids=assigned,
        allowed_warehouse_ids=warehouses,
        permissions=permissions,
        device_id=str(device_id).strip() if device_id else None,
    )
