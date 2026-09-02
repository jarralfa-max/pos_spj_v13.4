"""SqliteIntegrationDefinitionRepository — persists `IntegrationDefinition`
(SET-19). Implements
`backend.domain.integrations.repository_ports.IntegrationDefinitionRepositoryPort`.
"""

from __future__ import annotations

import json

from backend.domain.integrations.entities.integration_definition import IntegrationDefinition
from backend.domain.integrations.enums import IntegrationCategory
from backend.infrastructure.db.repositories.integrations.base import IntegrationsRepositoryBase

_COLS = "id, code, name, category, required_credential_names_json, active, created_at, updated_at"


class SqliteIntegrationDefinitionRepository(IntegrationsRepositoryBase):
    def save(self, definition: IntegrationDefinition) -> None:
        self._execute(
            f"INSERT INTO integration_definitions ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " name=excluded.name, required_credential_names_json=excluded.required_credential_names_json,"
            " active=excluded.active, updated_at=excluded.updated_at",
            self._params(definition),
        )

    def get(self, definition_id: str) -> IntegrationDefinition | None:
        row = self._query_one(f"SELECT {_COLS} FROM integration_definitions WHERE id=?", (definition_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> IntegrationDefinition | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM integration_definitions WHERE code=?", (code.strip().upper(),),
        )
        return self._hydrate(row) if row else None

    def list_active(self) -> list[IntegrationDefinition]:
        rows = self._query(f"SELECT {_COLS} FROM integration_definitions WHERE active=1 ORDER BY name")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(definition: IntegrationDefinition) -> tuple:
        return (
            definition.id, definition.code, definition.name, definition.category.value,
            json.dumps(list(definition.required_credential_names)), int(definition.active),
            definition.created_at, definition.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> IntegrationDefinition:
        return IntegrationDefinition(
            id=row["id"], code=row["code"], name=row["name"], category=IntegrationCategory(row["category"]),
            required_credential_names=tuple(json.loads(row["required_credential_names_json"] or "[]")),
            active=bool(row["active"]), created_at=row["created_at"], updated_at=row["updated_at"],
        )
