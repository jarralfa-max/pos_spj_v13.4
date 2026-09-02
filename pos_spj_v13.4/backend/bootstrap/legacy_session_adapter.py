"""LegacySessionAdapter — SHELL-16½ (new-shell live-wiring prerequisite).

Every SHELL-16 module's composition function (`create_sales_pos_view`,
`create_transfers_view`, `CashRegisterModuleActivator`'s stand-in, etc.)
was extracted from code that read `container.session` — a real
`core/session_context.py::SessionContext` instance — as its
`session_context` argument. Their tests all built a small fake exposing
the same subset of that real interface (`.user_id`, `.active_branch_id`,
`.tiene_permiso(code)`, `.is_active`). Wiring those same modules into the
NEW shell means handing them something built from the new
`ApplicationContext` (SHELL-6) instead — an immutable dataclass with a
completely different shape (`permissions: frozenset[str]`, no mutation
methods, no `.sucursal_id`/`.tiene_permiso`).

This adapter is the bridge: a read-only view over one `ApplicationContext`
that answers every `SessionContext` query the migrated modules actually
use, computed the same way `SessionContext`/`PermissionEvaluator` already
do — not reimplemented, since two independent implementations of "does
this permission wildcard match" is exactly the kind of drift CLAUDE.md's
audit-trail rule exists to prevent. `tiene_permiso()` delegates to
`PermissionEvaluator` (SHELL-6) directly.

Deliberately narrower than the full legacy interface where the new
context has no equivalent concept yet: `active_warehouse_id`/
`active_warehouse_name`/`sucursales_disponibles` return empty defaults —
confirmed (by reading every SHELL-16 module's composition function)
that none of the 9 already-migrated modules read these; `inventory`
treats `warehouse_id` as synonymous with `branch_id` rather than reading
a separate warehouse session attribute. If a future module needs one of
these for real, that is new information this adapter does not have yet,
not a bug in the mapping below — extend it then, don't guess now.

Not itself a `SessionContext` (no `set_user`/`set_sucursal`/`clear()` —
`ApplicationContext` is immutable and already built by the time this
adapter wraps it; there is nothing to mutate through it).
"""
from __future__ import annotations

from backend.bootstrap.application_context import ApplicationContext
from backend.bootstrap.permission_evaluator import PermissionEvaluator


class LegacySessionAdapter:
    def __init__(self, context: ApplicationContext) -> None:
        self._context = context
        self._evaluator = PermissionEvaluator(context)

    @property
    def user_id(self) -> str:
        return self._context.user_id

    @property
    def usuario(self) -> str:
        return self._context.user_name

    @property
    def nombre_completo(self) -> str:
        return self._context.user_name

    @property
    def rol(self) -> str:
        return self._context.roles[0] if self._context.roles else ""

    @property
    def sucursal_id(self) -> str:
        return self._context.branch_id

    @property
    def sucursal_nombre(self) -> str:
        return self._context.branch_name

    @property
    def active_branch_id(self) -> str:
        return self._context.branch_id

    @property
    def active_warehouse_id(self) -> str:
        return ""

    @property
    def active_warehouse_name(self) -> str:
        return ""

    @property
    def permisos(self):
        return frozenset(self._context.permissions)

    @property
    def is_active(self) -> bool:
        # An ApplicationContext only exists after a successful login — unlike
        # the legacy singleton, there is no "constructed but not yet
        # authenticated" state for this adapter to represent.
        return True

    @property
    def es_admin(self) -> bool:
        return self._context.is_admin()

    @property
    def es_gerente(self) -> bool:
        return any(
            role.lower() in ("admin", "superadmin", "gerente", "gerente_rh")
            for role in self._context.roles
        )

    @property
    def sucursales_disponibles(self) -> list:
        return []

    @property
    def is_branch_resolved(self) -> bool:
        return bool(self._context.branch_id)

    def tiene_permiso(self, codigo_permiso: str) -> bool:
        return self._evaluator.has_permission(codigo_permiso)

    def requiere_permiso(self, codigo_permiso: str, accion: str = "") -> bool:
        if self.tiene_permiso(codigo_permiso):
            return True
        raise PermissionError(f"No tiene permiso para: {accion or codigo_permiso}")

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "usuario": self.usuario,
            "nombre": self.nombre_completo,
            "rol": self.rol,
            "sucursal_id": self.sucursal_id,
            "sucursal_nombre": self.sucursal_nombre,
            "active_branch_id": self.active_branch_id,
            "is_active": self.is_active,
            "n_permisos": len(self.permisos),
        }

    def __repr__(self) -> str:
        return (
            f"LegacySessionAdapter(user={self.usuario!r}, rol={self.rol!r}, "
            f"sucursal={self.sucursal_nombre!r}[{self.active_branch_id}], "
            f"permisos={len(self.permisos)})"
        )
