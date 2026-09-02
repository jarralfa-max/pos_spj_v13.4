"""SqliteWebhookEndpointRepository — persists `WebhookEndpoint` (SET-19).
Implements
`backend.domain.integrations.repository_ports.WebhookEndpointRepositoryPort`.
"""

from __future__ import annotations

from backend.domain.integrations.entities.webhook_endpoint import WebhookEndpoint
from backend.domain.integrations.enums import WebhookSignatureScheme
from backend.infrastructure.db.repositories.integrations.base import IntegrationsRepositoryBase

_COLS = (
    "id, instance_id, code, path, signature_scheme, signing_secret_reference, active,"
    " last_received_at, created_at, updated_at"
)


class SqliteWebhookEndpointRepository(IntegrationsRepositoryBase):
    def save(self, endpoint: WebhookEndpoint) -> None:
        self._execute(
            f"INSERT INTO webhook_endpoints ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " active=excluded.active, last_received_at=excluded.last_received_at,"
            " updated_at=excluded.updated_at",
            self._params(endpoint),
        )

    def get(self, endpoint_id: str) -> WebhookEndpoint | None:
        row = self._query_one(f"SELECT {_COLS} FROM webhook_endpoints WHERE id=?", (endpoint_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> WebhookEndpoint | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM webhook_endpoints WHERE code=?", (code.strip().upper(),),
        )
        return self._hydrate(row) if row else None

    def list_by_instance(self, instance_id: str) -> list[WebhookEndpoint]:
        rows = self._query(
            f"SELECT {_COLS} FROM webhook_endpoints WHERE instance_id=? ORDER BY code", (instance_id,),
        )
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(endpoint: WebhookEndpoint) -> tuple:
        return (
            endpoint.id, endpoint.instance_id, endpoint.code, endpoint.path,
            endpoint.signature_scheme.value, endpoint.signing_secret_reference, int(endpoint.active),
            endpoint.last_received_at, endpoint.created_at, endpoint.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> WebhookEndpoint:
        return WebhookEndpoint(
            id=row["id"], instance_id=row["instance_id"], code=row["code"], path=row["path"],
            signature_scheme=WebhookSignatureScheme(row["signature_scheme"]),
            signing_secret_reference=row["signing_secret_reference"], active=bool(row["active"]),
            last_received_at=row["last_received_at"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
