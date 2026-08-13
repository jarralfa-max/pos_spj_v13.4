"""CustomerPrivacyRequestQueryService — read side for privacy requests.
Reads only; never mutates. Flat permission (``PRIVACY_REQUEST_VIEW``) —
same precedent as CustomerConsentQueryService.
"""

from __future__ import annotations

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.domain.customer_privacy.entities.customer_privacy_request import (
    CustomerPrivacyRequest,
)
from backend.domain.customer_privacy.exceptions import PrivacyRequestNotFoundError
from backend.infrastructure.db.repositories.customer_privacy.unit_of_work import (
    CustomerPrivacyUnitOfWork,
)


class CustomerPrivacyRequestQueryService:
    def __init__(self, connection, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._uow = CustomerPrivacyUnitOfWork(connection)
        self._auth = authorization or CustomerAuthorizationPolicy()

    def get(self, request_id: str, *, actor_user_id: str) -> CustomerPrivacyRequest:
        self._auth.require(actor_user_id, CustomerPermissions.PRIVACY_REQUEST_VIEW)
        request = self._uow.requests.get(request_id)
        if request is None:
            raise PrivacyRequestNotFoundError(f"Solicitud {request_id!r} no existe")
        return request

    def list_for_customer(self, customer_id: str, *,
                           actor_user_id: str) -> list[CustomerPrivacyRequest]:
        self._auth.require(actor_user_id, CustomerPermissions.PRIVACY_REQUEST_VIEW)
        return self._uow.requests.list_for_customer(customer_id)

    def list_by_status(self, status: str, *, actor_user_id: str, limit: int = 200,
                        offset: int = 0) -> list[CustomerPrivacyRequest]:
        self._auth.require(actor_user_id, CustomerPermissions.PRIVACY_REQUEST_VIEW)
        return self._uow.requests.list_by_status(status, limit=limit, offset=offset)
