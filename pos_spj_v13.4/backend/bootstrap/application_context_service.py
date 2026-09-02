"""ApplicationContextService — SHELL-6 §20.

The only sanctioned way to change the active branch: request → validate
permission → validate no open operations → resolve the new branch →
rebuild the context → emit events. Nothing else mutates
`container.sucursal_id`/`container.sucursal_nombre` directly (§20's
explicit prohibition) — a caller that wants a different branch calls
`change_branch()` and gets back a brand-new, immutable `ApplicationContext`.

Steps 5-8 of §20's flow ("invalidar cachés", "actualizar queries",
"reconstruir navegación", "notificar vistas") are the *consumers'*
responsibility, not this service's: they happen by subscribing to the
`APPLICATION_CONTEXT_CHANGED`/`NAVIGATION_CONTEXT_REBUILT` events this
service emits, once a query layer (SHELL-9) and navigation layer (SHELL-12)
exist to actually subscribe. This service's contract ends at "return a
valid new context, having emitted the canonical events."

Dependencies are injected as plain callables (ports), not concrete
repositories — matching every other SHELL-1/2 service in this codebase —
so this is fully unit-testable without a database, and the real
`PermissionQueryService`/`FeatureFlagService`/branch-lookup wiring happens
once this gets connected to the live app.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.bootstrap.application_context import ApplicationContext, FeatureContext
from backend.bootstrap.application_context_errors import (
    BranchNotFoundError,
    ContextSwitchNotAllowedError,
)
from backend.bootstrap.application_context_events import (
    APPLICATION_CONTEXT_CHANGED,
    APPLICATION_CONTEXT_CHANGING,
    NAVIGATION_CONTEXT_REBUILT,
)
from backend.bootstrap.permission_evaluator import PermissionEvaluator

PERMISSION_APPLICATION_CONTEXT_SWITCH = "APPLICATION_CONTEXT_SWITCH"

AuditSink = Callable[[str, dict], None]


@dataclass(frozen=True)
class BranchLookupResult:
    id: str
    name: str


BranchResolver = Callable[[str], Optional[BranchLookupResult]]
PermissionsLoader = Callable[[str, str], frozenset]
FeatureFlagsLoader = Callable[[str], dict]
OpenOperationsChecker = Callable[[], bool]


class ApplicationContextService:
    def __init__(
        self,
        *,
        branch_resolver: BranchResolver,
        permissions_loader: PermissionsLoader,
        feature_flags_loader: FeatureFlagsLoader,
        open_operations_checker: Optional[OpenOperationsChecker] = None,
        audit_sink: Optional[AuditSink] = None,
    ) -> None:
        self._resolve_branch = branch_resolver
        self._load_permissions = permissions_loader
        self._load_feature_flags = feature_flags_loader
        self._has_open_operations = open_operations_checker or (lambda: False)
        self._audit = audit_sink or (lambda event, payload: None)

    def change_branch(
        self, context: ApplicationContext, *, new_branch_id: str, now: datetime | None = None,
    ) -> ApplicationContext:
        now = now or datetime.now(timezone.utc)
        self._audit(APPLICATION_CONTEXT_CHANGING, {
            "user_id": context.user_id, "from_branch_id": context.branch_id, "to_branch_id": new_branch_id,
        })

        evaluator = PermissionEvaluator(context)
        if not evaluator.has_permission(PERMISSION_APPLICATION_CONTEXT_SWITCH):
            raise ContextSwitchNotAllowedError(
                "No tiene permiso para cambiar de sucursal (APPLICATION_CONTEXT_SWITCH)."
            )

        if self._has_open_operations():
            raise ContextSwitchNotAllowedError(
                "No se puede cambiar de sucursal: hay operaciones abiertas sin guardar."
            )

        branch = self._resolve_branch(new_branch_id)
        if branch is None:
            raise BranchNotFoundError(f"La sucursal '{new_branch_id}' no existe o no está activa.")

        new_permissions = self._load_permissions(context.user_id, branch.id)
        new_feature_context = FeatureContext.from_flags_dict(self._load_feature_flags(branch.id))
        new_context = context.with_branch(
            branch_id=branch.id, branch_name=branch.name,
            permissions=frozenset(new_permissions), feature_context=new_feature_context,
        )

        self._audit(APPLICATION_CONTEXT_CHANGED, {"user_id": context.user_id, "branch_id": new_context.branch_id})
        self._audit(NAVIGATION_CONTEXT_REBUILT, {"user_id": context.user_id, "branch_id": new_context.branch_id})
        return new_context
