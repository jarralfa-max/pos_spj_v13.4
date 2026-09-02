"""SqliteIntegrationHealthCheckRepository — persists `IntegrationHealthCheck`
(SET-19). Implements
`backend.domain.integrations.repository_ports.IntegrationHealthCheckRepositoryPort`.
Append-only — no ``get``/update, matching the entity's own "record, don't
mutate" shape.
"""

from __future__ import annotations

from backend.domain.integrations.entities.integration_health_check import IntegrationHealthCheck
from backend.infrastructure.db.repositories.integrations.base import IntegrationsRepositoryBase

_COLS = "id, instance_id, success, message, checked_at"


class SqliteIntegrationHealthCheckRepository(IntegrationsRepositoryBase):
    def save(self, check: IntegrationHealthCheck) -> None:
        self._execute(
            f"INSERT INTO integration_health_checks ({_COLS}) VALUES (?,?,?,?,?)",
            self._params(check),
        )

    def list_for_instance(self, instance_id: str, *, limit: int = 20) -> list[IntegrationHealthCheck]:
        rows = self._query(
            f"SELECT {_COLS} FROM integration_health_checks WHERE instance_id=?"
            " ORDER BY checked_at DESC LIMIT ?",
            (instance_id, limit),
        )
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(check: IntegrationHealthCheck) -> tuple:
        return (check.id, check.instance_id, int(check.success), check.message, check.checked_at)

    @staticmethod
    def _hydrate(row: dict) -> IntegrationHealthCheck:
        return IntegrationHealthCheck(
            id=row["id"], instance_id=row["instance_id"], success=bool(row["success"]),
            message=row["message"] or "", checked_at=row["checked_at"],
        )
