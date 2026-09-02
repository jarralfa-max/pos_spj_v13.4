"""DependencyGraphValidator — SHELL-5 §17.

Runs entirely over `ServiceRegistration.dependencies` declarations — never
invokes a single factory. That's what lets §17's promise ("el grafo debe
validarse antes del login") hold: the whole graph can be checked before
anything expensive (a DB connection, a UI widget) gets constructed.

Duplicate *registrations* (the same key registered twice) are caught
eagerly by `ServiceRegistry.register()` itself, not here — by the time a
`ServiceRegistry` exists to validate, that particular mistake already
raised. What this validator adds on top:

  - missing dependencies (a declared, required dependency nothing registered)
  - cycles
  - lifetime incompatibility (captive dependencies, §15)
  - duplicate canonical-role claims (§14 "dos implementaciones canónicas")
  - deprecated/legacy registrations (§14 "servicios legacy") — WARNING, not
    an ERROR; a legacy shim mid-migration is allowed to exist, just flagged
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.bootstrap.service_errors import DependencyGraphInvalidError
from backend.bootstrap.service_lifetime import is_lifetime_compatible
from backend.bootstrap.service_registry import ServiceRegistry


class IssueSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True)
class ValidationIssue:
    severity: IssueSeverity
    code: str
    message: str


class DependencyGraphValidator:
    def validate(self, registry: ServiceRegistry) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        issues += self._check_missing_dependencies(registry)
        issues += self._check_cycles(registry)
        issues += self._check_lifetime_compatibility(registry)
        issues += self._check_duplicate_canonical_roles(registry)
        issues += self._check_deprecated(registry)
        return issues

    def validate_or_raise(self, registry: ServiceRegistry) -> None:
        issues = self.validate(registry)
        errors = [i for i in issues if i.severity is IssueSeverity.ERROR]
        if errors:
            raise DependencyGraphInvalidError(errors)

    # ── individual checks ────────────────────────────────────────────────────

    def _check_missing_dependencies(self, registry: ServiceRegistry) -> list[ValidationIssue]:
        issues = []
        for reg in registry.registrations():
            for dep in reg.dependencies:
                if dep.optional:
                    continue
                if not registry.is_registered(dep.key):
                    issues.append(ValidationIssue(
                        IssueSeverity.ERROR, "MISSING_DEPENDENCY",
                        f"'{reg.key}' depende de '{dep.key}', que no está registrado.",
                    ))
        return issues

    def _check_cycles(self, registry: ServiceRegistry) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {reg.key: WHITE for reg in registry.registrations()}
        reported: set[frozenset] = set()

        def edges(key):
            reg = registry.get(key)
            if reg is None:
                return
            for dep in reg.dependencies:
                if registry.is_registered(dep.key):
                    yield dep.key

        def visit(key, path):
            color[key] = GRAY
            path.append(key)
            for neighbor in edges(key):
                if color.get(neighbor, WHITE) == GRAY:
                    cycle = path[path.index(neighbor):] + [neighbor]
                    fingerprint = frozenset(cycle)
                    if fingerprint not in reported:
                        reported.add(fingerprint)
                        issues.append(ValidationIssue(
                            IssueSeverity.ERROR, "DEPENDENCY_CYCLE",
                            "Ciclo de dependencias: " + " → ".join(str(k) for k in cycle),
                        ))
                elif color.get(neighbor, WHITE) == WHITE:
                    visit(neighbor, path)
            path.pop()
            color[key] = BLACK

        for reg in registry.registrations():
            if color[reg.key] == WHITE:
                visit(reg.key, [])
        return issues

    def _check_lifetime_compatibility(self, registry: ServiceRegistry) -> list[ValidationIssue]:
        issues = []
        for reg in registry.registrations():
            for dep in reg.dependencies:
                dep_reg = registry.get(dep.key)
                if dep_reg is None:
                    continue  # already reported as a missing dependency
                if not is_lifetime_compatible(dependent=reg.lifetime, dependency=dep_reg.lifetime):
                    issues.append(ValidationIssue(
                        IssueSeverity.ERROR, "LIFETIME_INCOMPATIBLE",
                        f"'{reg.key}' ({reg.lifetime.value}) depende de '{dep.key}' "
                        f"({dep_reg.lifetime.value}) — dependencia cautiva: un servicio "
                        f"de vida más larga no puede depender de uno de vida más corta.",
                    ))
        return issues

    def _check_duplicate_canonical_roles(self, registry: ServiceRegistry) -> list[ValidationIssue]:
        issues = []
        by_role: dict[str, list] = {}
        for reg in registry.registrations():
            if reg.canonical_for:
                by_role.setdefault(reg.canonical_for, []).append(reg.key)
        for role, keys in by_role.items():
            if len(keys) > 1:
                issues.append(ValidationIssue(
                    IssueSeverity.ERROR, "DUPLICATE_CANONICAL_IMPLEMENTATION",
                    f"El rol '{role}' tiene {len(keys)} implementaciones canónicas "
                    f"registradas: {', '.join(str(k) for k in keys)}.",
                ))
        return issues

    def _check_deprecated(self, registry: ServiceRegistry) -> list[ValidationIssue]:
        return [
            ValidationIssue(
                IssueSeverity.WARNING, "DEPRECATED_SERVICE",
                f"'{reg.key}' está marcado como legacy/deprecated.",
            )
            for reg in registry.registrations() if reg.deprecated
        ]
