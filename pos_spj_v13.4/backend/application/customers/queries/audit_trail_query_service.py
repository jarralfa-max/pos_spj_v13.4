"""AuditTrailQueryService (§76, CRM-43) — la bitácora de Clientes y CRM.

Requiere ``CLIENTES.auditoria.ver``. El historial de exportaciones (§48) es
la misma bitácora filtrada por acción.
"""

from __future__ import annotations

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.infrastructure.db.repositories.customers.audit_trail_repository import (
    AuditTrailRepository,
)


class AuditTrailQueryService:
    def __init__(self, connection, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._repo = AuditTrailRepository(connection)
        self._auth = authorization or CustomerAuthorizationPolicy()

    def recent(self, *, actor_user_id: str, module: str | None = None,
               action: str | None = None, limit: int = 500) -> list[dict]:
        self._auth.require(actor_user_id, CustomerPermissions.AUDIT_VIEW)
        return self._repo.recent(limit=limit, module=module, action=action)

    def exports(self, *, actor_user_id: str, limit: int = 200) -> list[dict]:
        """Exportaciones: las ve quien puede exportar (no sólo auditoría)."""
        if not (self._auth.has_permission(actor_user_id, CustomerPermissions.AUDIT_VIEW)
                or self._auth.has_permission(actor_user_id, CustomerPermissions.EXPORT)):
            self._auth.require(actor_user_id, CustomerPermissions.AUDIT_VIEW)
        return self._repo.recent(limit=limit, action="CUSTOMER_DATA_EXPORTED")
