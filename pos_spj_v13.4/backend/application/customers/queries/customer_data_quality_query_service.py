"""CustomerDataQualityQueryService (§57) — read side for
CustomerDataQualityIssue. Reads only; never mutates. Flat
DATA_QUALITY_VIEW permission, same no-scope-suffix precedent as
CRM-6's CRMActivityQueryService.
"""

from __future__ import annotations

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.domain.customers.entities.customer_data_quality_issue import (
    CustomerDataQualityIssue,
)
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork


class CustomerDataQualityQueryService:
    def __init__(self, connection,
                authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._uow = CustomerUnitOfWork(connection)
        self._auth = authorization or CustomerAuthorizationPolicy()

    def list_open_for_customer(self, customer_id: str, *,
                               actor_user_id: str) -> list[CustomerDataQualityIssue]:
        self._auth.require(actor_user_id, CustomerPermissions.DATA_QUALITY_VIEW)
        return self._uow.data_quality_issues.list_open_for_customer(customer_id)

    def list_by_status(self, status: str, *,
                       actor_user_id: str) -> list[CustomerDataQualityIssue]:
        self._auth.require(actor_user_id, CustomerPermissions.DATA_QUALITY_VIEW)
        return self._uow.data_quality_issues.list_by_status(status)
