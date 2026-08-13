"""CustomerOwnershipQueryService (§57) — read side for CustomerOwnership.
Reads only; never mutates. Flat CUSTOMER_OWNER_VIEW permission, same
no-scope-suffix precedent as CRMActivityQueryService (this entity family has
no ``ver.propia``/``ver.equipo`` pair in CRM-2's catalog either).
"""

from __future__ import annotations

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.domain.crm.entities.customer_ownership import CustomerOwnership
from backend.domain.crm.enums import OwnershipType
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


class CustomerOwnershipQueryService:
    def __init__(self, connection, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._uow = CRMUnitOfWork(connection)
        self._auth = authorization or CRMAuthorizationPolicy()

    def get_current(self, customer_id: str, ownership_type: str, *,
                    actor_user_id: str) -> CustomerOwnership | None:
        self._auth.require(actor_user_id, CRMPermissions.CUSTOMER_OWNER_VIEW)
        return self._uow.ownerships.get_latest(customer_id, ownership_type)

    def get_current_by_type(self, customer_id: str, *,
                            actor_user_id: str) -> dict[str, CustomerOwnership]:
        """Current owner for every OwnershipType that has ever been captured
        for this customer, keyed by type."""
        self._auth.require(actor_user_id, CRMPermissions.CUSTOMER_OWNER_VIEW)
        current: dict[str, CustomerOwnership] = {}
        for ownership_type in OwnershipType:
            latest = self._uow.ownerships.get_latest(customer_id, ownership_type.value)
            if latest is not None:
                current[ownership_type.value] = latest
        return current

    def list_history(self, customer_id: str, *, actor_user_id: str) -> list[CustomerOwnership]:
        self._auth.require(actor_user_id, CRMPermissions.CUSTOMER_OWNER_VIEW)
        return self._uow.ownerships.list_for_customer(customer_id)
