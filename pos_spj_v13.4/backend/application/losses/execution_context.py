"""Trusted immutable actor and organizational scope for Losses commands."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.application.losses.permissions import LossPermissions
from backend.domain.losses.exceptions import LossConfigurationError, LossScopeError


@dataclass(frozen=True)
class LossExecutionContext:
    actor_user_id: str
    active_branch_id: str
    assigned_branch_ids: frozenset[str] = field(default_factory=frozenset)
    allowed_warehouse_ids: frozenset[str] = field(default_factory=frozenset)
    permissions: frozenset[str] = field(default_factory=frozenset)
    device_id: str | None = None

    def __post_init__(self) -> None:
        if not str(self.actor_user_id or "").strip():
            raise LossConfigurationError("Losses requiere un usuario autenticado")
        if not str(self.active_branch_id or "").strip():
            raise LossConfigurationError("Losses requiere una sucursal activa")

    @property
    def has_global_scope(self) -> bool:
        return LossPermissions.VIEW_ALL_BRANCHES in self.permissions

    def enforce_branch(self, target_branch_id: str) -> None:
        target = str(target_branch_id or "").strip()
        if not target:
            raise LossScopeError("La operación requiere una sucursal válida")
        allowed = {self.active_branch_id, *self.assigned_branch_ids}
        if not self.has_global_scope and target not in allowed:
            raise LossScopeError(f"Sucursal fuera del alcance del actor: {target}")

    def enforce_warehouse(self, target_warehouse_id: str) -> None:
        target = str(target_warehouse_id or "").strip()
        if not target:
            raise LossScopeError("La operación requiere un almacén válido")
        if not self.has_global_scope and target not in self.allowed_warehouse_ids:
            raise LossScopeError(f"Almacén fuera del alcance del actor: {target}")
