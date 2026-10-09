"""ControlQueryService (§45-47, CRM-43) — bandejas de Control: candidatos a
duplicado (todos los estados abiertos), propuestas de fusión e importaciones.

Los servicios existentes leían por cliente o por UN estado; la bandeja de
duplicados necesita los detectados y los que están en revisión juntos, y la
de importaciones el historial completo con sus conteos.
"""

from __future__ import annotations

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork

_OPEN_DUPLICATES = ("DETECTED", "UNDER_REVIEW", "CONFIRMED_DUPLICATE")


class ControlQueryService:
    def __init__(self, connection, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._uow = CustomerUnitOfWork(connection)
        self._auth = authorization or CustomerAuthorizationPolicy()

    def duplicates(self, *, actor_user_id: str, include_closed: bool = False):
        self._auth.require(actor_user_id, CustomerPermissions.DUPLICATES_VIEW)
        statuses = _OPEN_DUPLICATES + (("DISMISSED", "MERGED") if include_closed else ())
        candidates = []
        for status in statuses:
            candidates.extend(self._uow.duplicate_candidates.list_by_status(status))
        return sorted(candidates, key=lambda c: c.created_at, reverse=True)

    def merges(self, *, actor_user_id: str):
        self._auth.require(actor_user_id, CustomerPermissions.DUPLICATES_VIEW)
        return self._uow.merge_records.list_recent()

    def import_batches(self, *, actor_user_id: str):
        self._auth.require(actor_user_id, CustomerPermissions.IMPORT)
        return self._uow.import_batches.list_recent()

    def quality_issues(self, *, actor_user_id: str, statuses=("OPEN", "ACKNOWLEDGED")):
        self._auth.require(actor_user_id, CustomerPermissions.DATA_QUALITY_VIEW)
        issues = []
        for status in statuses:
            issues.extend(self._uow.data_quality_issues.list_by_status(status))
        return sorted(issues, key=lambda i: i.created_at, reverse=True)
