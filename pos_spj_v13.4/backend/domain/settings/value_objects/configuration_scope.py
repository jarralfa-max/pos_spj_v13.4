"""ConfigurationScope — the (scope_type, scope_id) a `ConfigurationValue`
applies to. See master prompt §6-7.

GLOBAL never carries a `scope_id`. Every other scope requires one:
UUIDv7 for entity-referencing scopes (branch, workstation, device, user,
role, product, ...), or a non-empty logical code for `CODE_BASED_SCOPES`
(module, channel, process — these name a concept, not a row).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.settings.enums import CODE_BASED_SCOPES, ScopeType
from backend.domain.settings.exceptions import ConfigurationScopeNotAllowedError
from backend.shared.ids import validate_uuidv7


@dataclass(frozen=True, slots=True)
class ConfigurationScope:
    scope_type: ScopeType
    scope_id: str | None

    @classmethod
    def create(cls, scope_type: ScopeType, scope_id: str | None) -> "ConfigurationScope":
        if scope_type is ScopeType.GLOBAL:
            if scope_id is not None:
                raise ConfigurationScopeNotAllowedError("El ámbito GLOBAL no admite scope_id")
            return cls(scope_type, None)

        normalized = str(scope_id or "").strip()
        if not normalized:
            raise ConfigurationScopeNotAllowedError(
                f"El ámbito {scope_type.value} requiere un scope_id"
            )
        if scope_type in CODE_BASED_SCOPES:
            return cls(scope_type, normalized)

        validate_uuidv7(normalized)
        return cls(scope_type, normalized)

    @classmethod
    def global_scope(cls) -> "ConfigurationScope":
        return cls(ScopeType.GLOBAL, None)

    def matches(self, other: "ConfigurationScope") -> bool:
        return self.scope_type is other.scope_type and self.scope_id == other.scope_id
