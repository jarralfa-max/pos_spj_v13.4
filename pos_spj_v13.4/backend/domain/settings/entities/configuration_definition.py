"""ConfigurationDefinition — SET-2 aggregate root (§9).

Owns a configuration key's *shape*: type, default, validation rule,
allowed scopes, and governance flags (approval/sensitivity/restart/
offline). It never carries a live value — that is `ConfigurationValue`'s
job. No key may be stored without first being registered here (§5: "No
debe almacenar parámetros arbitrarios sin definición previa").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.settings.enums import ScopeType, ValueType
from backend.domain.settings.exceptions import ConfigurationInvalidValueError
from backend.domain.settings.policies.configuration_validation_policy import validate_value
from backend.domain.settings.value_objects.configuration_key import ConfigurationKey
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class ConfigurationDefinition:
    id: str
    key: ConfigurationKey
    module: str
    label: str
    value_type: ValueType
    allowed_scopes: frozenset[ScopeType]
    section: str = ""
    description: str = ""
    default_value: object | None = None
    validation_schema: dict | None = None
    allowed_values: tuple[str, ...] | None = None
    default_scope: ScopeType | None = None
    inheritance_enabled: bool = True
    override_allowed: bool = True
    approval_required: bool = False
    sensitive: bool = False
    restart_required: bool = False
    offline_available: bool = True
    deprecated: bool = False
    replacement_key: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    # construction ------------------------------------------------------------
    @classmethod
    def create(
        cls, key: str, *, module: str, label: str, value_type: ValueType,
        allowed_scopes: frozenset[ScopeType] | set[ScopeType] | tuple[ScopeType, ...],
        section: str = "", description: str = "", default_value: object | None = None,
        validation_schema: dict | None = None, allowed_values: tuple[str, ...] | None = None,
        default_scope: ScopeType | None = None, inheritance_enabled: bool = True,
        override_allowed: bool = True, approval_required: bool = False,
        sensitive: bool = False, restart_required: bool = False,
        offline_available: bool = True,
    ) -> "ConfigurationDefinition":
        configuration_key = ConfigurationKey.create(key)
        if not module.strip() or not label.strip():
            raise ConfigurationInvalidValueError("module y label son obligatorios")

        scopes = frozenset(allowed_scopes)
        if not scopes:
            raise ConfigurationInvalidValueError(
                f"{configuration_key}: allowed_scopes no puede estar vacío"
            )
        if default_scope is not None and default_scope not in scopes:
            raise ConfigurationInvalidValueError(
                f"{configuration_key}: default_scope debe estar en allowed_scopes"
            )

        if value_type in (ValueType.ENUM, ValueType.MULTI_ENUM) and not allowed_values:
            raise ConfigurationInvalidValueError(
                f"{configuration_key}: {value_type.value} requiere allowed_values"
            )
        if allowed_values is not None:
            normalized_allowed = tuple(dict.fromkeys(str(item) for item in allowed_values))
            if not normalized_allowed:
                raise ConfigurationInvalidValueError(
                    f"{configuration_key}: allowed_values no puede estar vacío si se especifica"
                )
        else:
            normalized_allowed = None

        if default_value is not None:
            validate_value(value_type, default_value, allowed_values=normalized_allowed)

        return cls(
            id=new_uuid(), key=configuration_key, module=module.strip(), label=label.strip(),
            value_type=value_type, allowed_scopes=scopes, section=section.strip(),
            description=description.strip(), default_value=default_value,
            validation_schema=dict(validation_schema) if validation_schema else None,
            allowed_values=normalized_allowed, default_scope=default_scope,
            inheritance_enabled=inheritance_enabled, override_allowed=override_allowed,
            approval_required=approval_required, sensitive=sensitive,
            restart_required=restart_required, offline_available=offline_available,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    # behavior ------------------------------------------------------------------
    def allows_scope(self, scope_type: ScopeType) -> bool:
        return scope_type in self.allowed_scopes

    def deprecate(self, *, replacement_key: str | None = None) -> None:
        if self.deprecated:
            raise ConfigurationInvalidValueError(f"{self.key} ya está deprecada")
        self.deprecated = True
        self.replacement_key = replacement_key
        self._touch()
