"""SqliteConfigurationDefinitionRepository — persists
`ConfigurationDefinition` (SET-3). Implements
`backend.domain.settings.repository_ports.ConfigurationDefinitionRepositoryPort`.
Mirrors backend/infrastructure/db/repositories/crm/lead_repository.py.
"""

from __future__ import annotations

import json

from backend.domain.settings.entities.configuration_definition import ConfigurationDefinition
from backend.domain.settings.enums import ScopeType, ValueType
from backend.domain.settings.value_objects.configuration_key import ConfigurationKey
from backend.infrastructure.db.repositories.settings.base import SettingsRepositoryBase
from backend.infrastructure.db.repositories.settings.value_serialization import (
    deserialize_value,
    serialize_value,
)

_COLS = (
    "id, key, module, section, label, description, value_type, default_value_json,"
    " validation_schema_json, allowed_values_json, allowed_scopes_json, default_scope,"
    " inheritance_enabled, override_allowed, approval_required, sensitive,"
    " restart_required, offline_available, deprecated, replacement_key, created_at, updated_at"
)


class SqliteConfigurationDefinitionRepository(SettingsRepositoryBase):
    def save(self, definition: ConfigurationDefinition) -> None:
        self._execute(
            f"INSERT INTO configuration_definitions ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " key=excluded.key, module=excluded.module, section=excluded.section,"
            " label=excluded.label, description=excluded.description,"
            " value_type=excluded.value_type, default_value_json=excluded.default_value_json,"
            " validation_schema_json=excluded.validation_schema_json,"
            " allowed_values_json=excluded.allowed_values_json,"
            " allowed_scopes_json=excluded.allowed_scopes_json,"
            " default_scope=excluded.default_scope,"
            " inheritance_enabled=excluded.inheritance_enabled,"
            " override_allowed=excluded.override_allowed,"
            " approval_required=excluded.approval_required, sensitive=excluded.sensitive,"
            " restart_required=excluded.restart_required,"
            " offline_available=excluded.offline_available, deprecated=excluded.deprecated,"
            " replacement_key=excluded.replacement_key, updated_at=excluded.updated_at",
            self._params(definition),
        )

    def get(self, definition_id: str) -> ConfigurationDefinition | None:
        row = self._query_one(f"SELECT {_COLS} FROM configuration_definitions WHERE id=?", (definition_id,))
        return self._hydrate(row) if row else None

    def get_by_key(self, key: str) -> ConfigurationDefinition | None:
        row = self._query_one(f"SELECT {_COLS} FROM configuration_definitions WHERE key=?", (key,))
        return self._hydrate(row) if row else None

    def list_by_module(self, module: str) -> list[ConfigurationDefinition]:
        rows = self._query(
            f"SELECT {_COLS} FROM configuration_definitions WHERE module=? ORDER BY key", (module,),
        )
        return [self._hydrate(row) for row in rows]

    def list_all(self) -> list[ConfigurationDefinition]:
        rows = self._query(f"SELECT {_COLS} FROM configuration_definitions ORDER BY module, key")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(definition: ConfigurationDefinition) -> tuple:
        return (
            definition.id, str(definition.key), definition.module, definition.section,
            definition.label, definition.description, definition.value_type.value,
            (serialize_value(definition.value_type, definition.default_value)
             if definition.default_value is not None else None),
            json.dumps(definition.validation_schema) if definition.validation_schema is not None else None,
            json.dumps(list(definition.allowed_values)) if definition.allowed_values is not None else None,
            json.dumps(sorted(scope.value for scope in definition.allowed_scopes)),
            definition.default_scope.value if definition.default_scope is not None else None,
            int(definition.inheritance_enabled), int(definition.override_allowed),
            int(definition.approval_required), int(definition.sensitive),
            int(definition.restart_required), int(definition.offline_available),
            int(definition.deprecated), definition.replacement_key,
            definition.created_at, definition.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> ConfigurationDefinition:
        value_type = ValueType(row["value_type"])
        return ConfigurationDefinition(
            id=row["id"], key=ConfigurationKey(row["key"]), module=row["module"],
            section=row["section"] or "", label=row["label"], description=row["description"] or "",
            value_type=value_type,
            default_value=(deserialize_value(value_type, row["default_value_json"])
                            if row["default_value_json"] is not None else None),
            validation_schema=(json.loads(row["validation_schema_json"])
                               if row["validation_schema_json"] is not None else None),
            allowed_values=(tuple(json.loads(row["allowed_values_json"]))
                            if row["allowed_values_json"] is not None else None),
            allowed_scopes=frozenset(ScopeType(item) for item in json.loads(row["allowed_scopes_json"])),
            default_scope=ScopeType(row["default_scope"]) if row["default_scope"] else None,
            inheritance_enabled=bool(row["inheritance_enabled"]),
            override_allowed=bool(row["override_allowed"]),
            approval_required=bool(row["approval_required"]), sensitive=bool(row["sensitive"]),
            restart_required=bool(row["restart_required"]),
            offline_available=bool(row["offline_available"]), deprecated=bool(row["deprecated"]),
            replacement_key=row["replacement_key"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
