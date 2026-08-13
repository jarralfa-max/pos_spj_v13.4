"""CustomerDuplicateQueryService (§57) — read side for
CustomerDuplicateCandidate/CustomerMergeRecord. Reads only; never mutates.
Flat DUPLICATES_VIEW permission — this entity family has no ``ver.propia``/
``ver.equipo`` scope-suffixed pair in the catalog, same no-scope-suffix
precedent as CRM-6's CRMActivityQueryService.
"""

from __future__ import annotations

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.domain.customers.entities.customer_duplicate_candidate import (
    CustomerDuplicateCandidate,
)
from backend.domain.customers.entities.customer_merge_record import CustomerMergeRecord
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork


class CustomerDuplicateQueryService:
    def __init__(self, connection,
                authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._uow = CustomerUnitOfWork(connection)
        self._auth = authorization or CustomerAuthorizationPolicy()

    def list_by_status(self, status: str, *,
                       actor_user_id: str) -> list[CustomerDuplicateCandidate]:
        self._auth.require(actor_user_id, CustomerPermissions.DUPLICATES_VIEW)
        return self._uow.duplicate_candidates.list_by_status(status)

    def list_for_customer(self, customer_id: str, *,
                          actor_user_id: str) -> list[CustomerDuplicateCandidate]:
        self._auth.require(actor_user_id, CustomerPermissions.DUPLICATES_VIEW)
        return self._uow.duplicate_candidates.list_for_customer(customer_id)

    def list_merge_history(self, customer_id: str, *,
                           actor_user_id: str) -> list[CustomerMergeRecord]:
        self._auth.require(actor_user_id, CustomerPermissions.DUPLICATES_VIEW)
        return self._uow.merge_records.list_for_customer(customer_id)
