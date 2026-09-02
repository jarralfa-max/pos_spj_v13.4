"""SqliteConfigurationValueRepository — persists `ConfigurationValue`
(SET-3). Implements
`backend.domain.settings.repository_ports.ConfigurationValueRepositoryPort`.
Mirrors backend/infrastructure/db/repositories/crm/lead_repository.py.

`value_json` is typed per the *definition's* `value_type` — this
repository always joins `configuration_definitions` to know how to
(de)serialize it (`ConfigurationValue` itself does not carry its type).
"""

from __future__ import annotations

from datetime import datetime

from backend.domain.settings.entities.configuration_value import ConfigurationValue
from backend.domain.settings.enums import ConfigurationValueStatus, ScopeType, ValueType
from backend.domain.settings.exceptions import ConfigurationDefinitionNotFoundError
from backend.domain.settings.value_objects.configuration_scope import ConfigurationScope
from backend.domain.settings.value_objects.effective_period import EffectivePeriod
from backend.domain.settings.value_objects.version_number import VersionNumber
from backend.infrastructure.db.repositories.settings.base import SettingsRepositoryBase
from backend.infrastructure.db.repositories.settings.value_serialization import (
    deserialize_value,
    serialize_value,
)

_INSERT_COLS = (
    "id, definition_id, scope_type, scope_id, value_json, effective_from, effective_to,"
    " version, status, created_by_user_id, approved_by_user_id, activated_by_user_id,"
    " reason, previous_version_id, operation_id, created_at, updated_at"
)

_SELECT_COLS = (
    "cv.id, cv.definition_id, cv.scope_type, cv.scope_id, cv.value_json,"
    " cv.effective_from, cv.effective_to, cv.version, cv.status,"
    " cv.created_by_user_id, cv.approved_by_user_id, cv.activated_by_user_id,"
    " cv.reason, cv.previous_version_id, cv.operation_id, cv.created_at, cv.updated_at,"
    " cd.value_type AS definition_value_type"
)
_FROM = "FROM configuration_values cv JOIN configuration_definitions cd ON cd.id = cv.definition_id"


class SqliteConfigurationValueRepository(SettingsRepositoryBase):
    def save(self, value: ConfigurationValue, *, operation_id: str | None = None) -> None:
        value_type = self._value_type_for_definition(value.definition_id)
        self._execute(
            f"INSERT INTO configuration_values ({_INSERT_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " scope_type=excluded.scope_type, scope_id=excluded.scope_id,"
            " value_json=excluded.value_json, effective_from=excluded.effective_from,"
            " effective_to=excluded.effective_to, version=excluded.version,"
            " status=excluded.status, created_by_user_id=excluded.created_by_user_id,"
            " approved_by_user_id=excluded.approved_by_user_id,"
            " activated_by_user_id=excluded.activated_by_user_id, reason=excluded.reason,"
            " previous_version_id=excluded.previous_version_id,"
            " operation_id=excluded.operation_id, updated_at=excluded.updated_at",
            self._params(value, value_type, operation_id),
        )

    def get(self, value_id: str) -> ConfigurationValue | None:
        row = self._query_one(f"SELECT {_SELECT_COLS} {_FROM} WHERE cv.id=?", (value_id,))
        return self._hydrate(row) if row else None

    def list_candidates(
        self, definition_id: str, scopes: tuple[ConfigurationScope, ...],
    ) -> list[ConfigurationValue]:
        if not scopes:
            return []
        conditions = " OR ".join("(cv.scope_type=? AND cv.scope_id IS ?)" for _ in scopes)
        params: list = [definition_id]
        for scope in scopes:
            params.extend([scope.scope_type.value, scope.scope_id])
        rows = self._query(
            f"SELECT {_SELECT_COLS} {_FROM} WHERE cv.definition_id=? AND ({conditions})",
            tuple(params),
        )
        return [self._hydrate(row) for row in rows]

    def list_active_for_scope(self, scope: ConfigurationScope) -> list[ConfigurationValue]:
        rows = self._query(
            f"SELECT {_SELECT_COLS} {_FROM} WHERE cv.scope_type=? AND cv.scope_id IS ? AND cv.status='ACTIVE'",
            (scope.scope_type.value, scope.scope_id),
        )
        return [self._hydrate(row) for row in rows]

    def get_by_operation_id(self, operation_id: str) -> ConfigurationValue | None:
        row = self._query_one(f"SELECT {_SELECT_COLS} {_FROM} WHERE cv.operation_id=?", (operation_id,))
        return self._hydrate(row) if row else None

    # helpers -----------------------------------------------------------------
    def _value_type_for_definition(self, definition_id: str) -> ValueType:
        row = self._conn.execute(
            "SELECT value_type FROM configuration_definitions WHERE id=?", (definition_id,),
        ).fetchone()
        if row is None:
            raise ConfigurationDefinitionNotFoundError(
                f"No existe ConfigurationDefinition con id={definition_id!r}"
            )
        return ValueType(row[0])

    @staticmethod
    def _params(value: ConfigurationValue, value_type: ValueType, operation_id: str | None) -> tuple:
        period = value.effective_period
        return (
            value.id, value.definition_id, value.scope.scope_type.value, value.scope.scope_id,
            serialize_value(value_type, value.value),
            period.effective_from.isoformat(),
            period.effective_to.isoformat() if period.effective_to else None,
            value.version.value, value.status.value,
            value.created_by_user_id, value.approved_by_user_id, value.activated_by_user_id,
            value.reason, value.previous_version_id, operation_id,
            value.created_at, value.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> ConfigurationValue:
        value_type = ValueType(row["definition_value_type"])
        return ConfigurationValue(
            id=row["id"], definition_id=row["definition_id"],
            scope=ConfigurationScope(ScopeType(row["scope_type"]), row["scope_id"]),
            value=deserialize_value(value_type, row["value_json"]),
            effective_period=EffectivePeriod(
                datetime.fromisoformat(row["effective_from"]),
                datetime.fromisoformat(row["effective_to"]) if row["effective_to"] else None,
            ),
            version=VersionNumber(row["version"]),
            status=ConfigurationValueStatus(row["status"]),
            created_by_user_id=row["created_by_user_id"],
            approved_by_user_id=row["approved_by_user_id"],
            activated_by_user_id=row["activated_by_user_id"],
            reason=row["reason"], previous_version_id=row["previous_version_id"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
