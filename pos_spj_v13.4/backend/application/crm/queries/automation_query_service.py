"""AutomationQueryService (§56, CRM-43) — reglas de automatización y sus
ejecuciones, para la pantalla de Configuración (no existía lectura)."""

from __future__ import annotations

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


class AutomationQueryService:
    def __init__(self, connection, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._uow = CRMUnitOfWork(connection)
        self._auth = authorization or CRMAuthorizationPolicy()

    def rules(self, *, actor_user_id: str):
        self._auth.require(actor_user_id, CRMPermissions.AUTOMATION_RULES_VIEW)
        return self._uow.automation_rules.list_all()

    def executions(self, *, actor_user_id: str, limit: int = 100):
        self._auth.require(actor_user_id, CRMPermissions.AUTOMATION_EXECUTIONS_VIEW)
        return self._uow.automation_executions.list_recent(limit=limit)
