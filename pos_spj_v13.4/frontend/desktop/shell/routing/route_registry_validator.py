"""RouteRegistryValidator — SHELL-9 §45.

Cross-registry checks a single `RouteRegistry` can't do on its own:

  - every route's `module_id` must exist in the `ModuleRegistry`
  - every route's `view_factory_id` must exist in the `ViewFactoryRegistry`
  - `route_id` must not be one of §45's explicit ambiguous legacy codes
    (`POS`, `CAJA`, `PRODUCCION`, `CONFIGURACION`, ...) and must carry its
    own identity via the dotted `module.action` form, not a bare word

Reuses `ValidationIssue`/`IssueSeverity` from SHELL-5's
`DependencyGraphValidator` rather than a second copy of the same
severity+code+message shape — same reasoning `ModuleHealthEvaluator`
reused SHELL-3's `HealthStatus` ordering instead of inventing its own.
"""
from __future__ import annotations

from backend.bootstrap.dependency_graph_validator import IssueSeverity, ValidationIssue
from frontend.desktop.shell.modules.module_registry import ModuleRegistry
from frontend.desktop.shell.routing.errors import RouteGraphInvalidError
from frontend.desktop.shell.routing.route_registry import RouteRegistry
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry

# §45's explicit examples of ambiguous, non-self-identifying codes.
_AMBIGUOUS_LEGACY_CODES = frozenset({
    "POS", "CAJA", "PRODUCCION", "CONFIGURACION",
    "TARJETAS", "FIDELIDAD", "ETIQUETAS", "HARDWARE", "PROVEEDORES",
    "TESORERIA", "SACRIFICIO", "DESPIECE", "DELIVERY", "VENTAS",
})


class RouteRegistryValidator:
    def validate(
        self, routes: RouteRegistry, modules: ModuleRegistry, view_factories: ViewFactoryRegistry,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for route in routes.all():
            issues.extend(self._check_module_exists(route, modules))
            issues.extend(self._check_view_factory_exists(route, view_factories))
            issues.extend(self._check_route_id_not_ambiguous(route))
        return issues

    def validate_or_raise(
        self, routes: RouteRegistry, modules: ModuleRegistry, view_factories: ViewFactoryRegistry,
    ) -> None:
        issues = self.validate(routes, modules, view_factories)
        errors = [i for i in issues if i.severity is IssueSeverity.ERROR]
        if errors:
            raise RouteGraphInvalidError(errors)

    @staticmethod
    def _check_module_exists(route, modules: ModuleRegistry) -> list[ValidationIssue]:
        if modules.is_registered(route.module_id):
            return []
        return [ValidationIssue(
            IssueSeverity.ERROR, "ROUTE_MODULE_NOT_FOUND",
            f"La ruta '{route.route_id}' declara module_id '{route.module_id}', "
            f"que no está registrado en el ModuleRegistry.",
        )]

    @staticmethod
    def _check_view_factory_exists(route, view_factories: ViewFactoryRegistry) -> list[ValidationIssue]:
        if view_factories.is_registered(route.view_factory_id):
            return []
        return [ValidationIssue(
            IssueSeverity.ERROR, "ROUTE_VIEW_FACTORY_NOT_FOUND",
            f"La ruta '{route.route_id}' declara view_factory_id '{route.view_factory_id}', "
            f"que no está registrado en el ViewFactoryRegistry.",
        )]

    @staticmethod
    def _check_route_id_not_ambiguous(route) -> list[ValidationIssue]:
        route_id = route.route_id
        if route_id.upper() in _AMBIGUOUS_LEGACY_CODES:
            return [ValidationIssue(
                IssueSeverity.ERROR, "AMBIGUOUS_ROUTE_ID",
                f"'{route_id}' es un código ambiguo (§45) — use la forma "
                f"'modulo.accion' (p. ej. 'sales.pos') como única identidad.",
            )]
        if "." not in route_id:
            return [ValidationIssue(
                IssueSeverity.ERROR, "AMBIGUOUS_ROUTE_ID",
                f"'{route_id}' no tiene forma 'modulo.accion' — un identificador "
                f"de una sola palabra puede colisionar con otro módulo.",
            )]
        return []
