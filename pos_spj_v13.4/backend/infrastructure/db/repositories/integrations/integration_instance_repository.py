"""SqliteIntegrationInstanceRepository — persists `IntegrationInstance`
(SET-19). Implements
`backend.domain.integrations.repository_ports.IntegrationInstanceRepositoryPort`.
"""

from __future__ import annotations

import json

from backend.domain.integrations.entities.integration_instance import IntegrationInstance
from backend.infrastructure.db.repositories.integrations.base import IntegrationsRepositoryBase

_COLS = "id, definition_id, name, config_json, credential_references_json, active, created_at, updated_at"


class SqliteIntegrationInstanceRepository(IntegrationsRepositoryBase):
    def save(self, instance: IntegrationInstance) -> None:
        self._execute(
            f"INSERT INTO integration_instances ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " name=excluded.name, config_json=excluded.config_json,"
            " credential_references_json=excluded.credential_references_json, active=excluded.active,"
            " updated_at=excluded.updated_at",
            self._params(instance),
        )

    def get(self, instance_id: str) -> IntegrationInstance | None:
        row = self._query_one(f"SELECT {_COLS} FROM integration_instances WHERE id=?", (instance_id,))
        return self._hydrate(row) if row else None

    def list_by_definition(self, definition_id: str) -> list[IntegrationInstance]:
        rows = self._query(
            f"SELECT {_COLS} FROM integration_instances WHERE definition_id=? ORDER BY name",
            (definition_id,),
        )
        return [self._hydrate(row) for row in rows]

    def list_active(self) -> list[IntegrationInstance]:
        rows = self._query(f"SELECT {_COLS} FROM integration_instances WHERE active=1 ORDER BY name")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(instance: IntegrationInstance) -> tuple:
        return (
            instance.id, instance.definition_id, instance.name, json.dumps(instance.config),
            json.dumps(instance.credential_references), int(instance.active), instance.created_at,
            instance.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> IntegrationInstance:
        return IntegrationInstance(
            id=row["id"], definition_id=row["definition_id"], name=row["name"],
            config=json.loads(row["config_json"] or "{}"),
            credential_references=json.loads(row["credential_references_json"] or "{}"),
            active=bool(row["active"]), created_at=row["created_at"], updated_at=row["updated_at"],
        )
