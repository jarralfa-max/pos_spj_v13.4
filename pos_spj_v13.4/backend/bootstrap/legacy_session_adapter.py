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

import dataclasses
import logging

from backend.bootstrap.application_context import ApplicationContext
from backend.bootstrap.permission_evaluator import PermissionEvaluator
from backend.shared.ids import is_uuidv7

logger = logging.getLogger("spj.session")


class LegacySessionAdapter:
    def __init__(self, context: ApplicationContext, *, grant_refresher=None) -> None:
        self._context = context
        self._evaluator = PermissionEvaluator(context)
        # Auditoría de permisos 968e0bc (PER-08): sin refrescador, los permisos
        # son los del inicio de sesión (pruebas, autoprueba de la interfaz).
        self._refresher = grant_refresher
        self._revoked = False

    def _refresh_permissions(self) -> None:
        """Si cambió alguna concesión, recarga los permisos y los roles de ESTA
        sesión (usuario y sucursal siguen igual). Los roles también: `is_admin()`
        los mira, y antes un administrador degradado seguía saltándose todas
        las comprobaciones hasta cerrar sesión (auditoría enterprise, Fase 2)."""
        if self._refresher is None or not self._refresher.changed():
            return
        try:
            nuevos = self._refresher.load(self._context.user_id, self._context.branch_id)
        except Exception:  # noqa: BLE001 - si no se pudo recargar, se conserva lo anterior
            logger.exception("No se pudieron recargar los permisos de la sesión.")
            return
        if nuevos is None:
            # La cuenta se desactivó con la sesión abierta: no se concede nada
            # más, ni por rol de acceso total.
            self._revoked = True
            logger.warning("Sesión revocada: la cuenta %s ya no está activa.",
                           self._context.user_name)
            return
        roles = self._context.roles
        cargar_roles = getattr(self._refresher, "load_roles", None)
        if callable(cargar_roles):
            try:
                roles = tuple(cargar_roles(self._context.user_id, self._context.branch_id))
            except Exception:  # noqa: BLE001 - igual que los permisos: se conserva lo anterior
                logger.exception("No se pudieron recargar los roles de la sesión.")
        if nuevos == self._context.permissions and roles == self._context.roles:
            return
        self._context = dataclasses.replace(self._context, permissions=frozenset(nuevos),
                                            roles=roles)
        self._evaluator = PermissionEvaluator(self._context)
        logger.info("Permisos de la sesión recargados: %s (%d códigos).",
                    self._context.user_name, len(nuevos))

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
    def company_id(self) -> str:
        return self._context.company_id

    @property
    def workstation_id(self) -> str | None:
        """Only a registered UUID identifies a configuration scope; a host name does not."""
        value = self._context.workstation_id
        return value if is_uuidv7(value) else None

    @property
    def active_warehouse_id(self) -> str:
        return ""

    @property
    def active_warehouse_name(self) -> str:
        return ""

    @property
    def permisos(self):
        self._refresh_permissions()
        return frozenset(self._context.permissions)

    @property
    def is_active(self) -> bool:
        # An ApplicationContext only exists after a successful login — unlike
        # the legacy singleton, there is no "constructed but not yet
        # authenticated" state for this adapter to represent. It stops being
        # active if the account is deactivated while the session is open
        # (auditoría de permisos 968e0bc, PER-08).
        self._refresh_permissions()
        return not self._revoked

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
    def assigned_branch_ids(self) -> frozenset:
        """Sucursales asignadas, el nombre que LEEN los contextos de ejecución.

        `resolve_inventory_execution_context` (y sus equivalentes de Mermas y
        Cárnico) buscan este atributo en la sesión. Antes no existía en ningún
        objeto de sesión, así que siempre resolvían el conjunto vacío y el nivel
        "sucursales asignadas" del alcance no podía conceder nada a nadie.
        """
        return frozenset(self._context.assigned_branch_ids)

    @property
    def sucursales_asignadas(self) -> frozenset:
        """Alias en español: los contextos aceptan cualquiera de los dos
        nombres, y el resto de esta clase expone el vocabulario en español."""
        return self.assigned_branch_ids

    @property
    def sucursales_disponibles(self) -> list:
        # Distinto de `assigned_branch_ids`: esto pretendía ser la lista para un
        # SELECTOR de sucursal (id + nombre), no el conjunto de alcance. Sigue
        # vacío porque ninguna pantalla lo consume; quien necesite ofrecer
        # sucursales debe pasar por `BranchScopeQueryService`, que las acota al
        # usuario antes de consultar.
        return []

    @property
    def is_branch_resolved(self) -> bool:
        return bool(self._context.branch_id)

    def tiene_permiso(self, codigo_permiso: str) -> bool:
        self._refresh_permissions()
        if self._revoked:
            return False
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
