"""CustomerProfileQueryService — read side of the Customer Master aggregate
(§57's ``CustomerProfileQueryService``/``CustomerDirectoryQueryService``,
first cut). Reads only; never mutates.

Every read goes through ``CustomerDataScopeResolver`` (CRM-2) — there is no
"read everything" fallback. ``get_profile`` additionally checks the fetched
customer falls inside the caller's resolved scope, so a user cannot bypass
directory filtering by guessing a customer_id (§60).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.application.customers.data_scope import (
    CustomerDataScope,
    CustomerDataScopeResolver,
    CustomerScopeContext,
)
from backend.domain.customers.entities.customer import Customer
from backend.domain.customers.entities.customer_account import CustomerAccount
from backend.domain.customers.entities.customer_address import CustomerAddress
from backend.domain.customers.entities.customer_contact import CustomerContactPerson
from backend.domain.customers.entities.customer_tax_profile import CustomerTaxProfile
from backend.domain.customers.exceptions import CustomerNotFoundError, CustomerScopeError
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork


@dataclass(frozen=True)
class CustomerProfile:
    customer: Customer
    accounts: list[CustomerAccount] = field(default_factory=list)
    contacts: list[CustomerContactPerson] = field(default_factory=list)
    addresses: list[CustomerAddress] = field(default_factory=list)
    tax_profile: CustomerTaxProfile | None = None


class CustomerProfileQueryService:
    def __init__(self, connection, scope_resolver: CustomerDataScopeResolver) -> None:
        self._uow = CustomerUnitOfWork(connection)
        self._scope_resolver = scope_resolver

    def get_profile(self, customer_id: str, context: CustomerScopeContext) -> CustomerProfile:
        scope = self._scope_resolver.resolve_view_scope(context)
        customer = self._uow.customers.get(customer_id)
        if customer is None:
            raise CustomerNotFoundError(f"Cliente {customer_id!r} no existe")
        if not self._in_scope(customer, scope):
            raise CustomerScopeError(
                f"El cliente {customer_id!r} está fuera del alcance ({scope.axis}) del usuario")
        return CustomerProfile(
            customer=customer,
            accounts=self._uow.accounts.list_for_customer(customer_id),
            contacts=self._uow.contacts.list_for_customer(customer_id),
            addresses=self._uow.addresses.list_for_customer(customer_id),
            tax_profile=self._uow.tax_profiles.get_for_customer(customer_id),
        )

    def list_directory(
        self, context: CustomerScopeContext, *, limit: int = 200, offset: int = 0,
    ) -> list[Customer]:
        scope = self._scope_resolver.resolve_view_scope(context)
        if scope.axis == "COMPANY":
            return self._uow.customers.list_active(limit=limit, offset=offset)
        if scope.axis in ("OWN", "TEAM"):
            owner_ids = (scope.owner_user_id,) if scope.axis == "OWN" else scope.team_member_ids
            return self._uow.customers.list_owned_by(owner_ids, limit=limit, offset=offset)
        if scope.axis == "BRANCH":
            return self._uow.customers.list_by_branch(scope.branch_id, limit=limit, offset=offset)
        if scope.axis == "TERRITORY":
            return self._uow.customers.list_by_territory(
                scope.territory_id, limit=limit, offset=offset)
        # PORTFOLIO: no customers.portfolio_id column yet (portfolios are a
        # CRM-relationship concept per §69, modeled in CRM-10) — until then a
        # PORTFOLIO grant sees nothing rather than silently widening to ALL.
        return []

    @staticmethod
    def _in_scope(customer: Customer, scope: CustomerDataScope) -> bool:
        if scope.axis == "COMPANY":
            return True
        if scope.axis == "OWN":
            return customer.account_owner_user_id == scope.owner_user_id
        if scope.axis == "TEAM":
            return customer.account_owner_user_id in scope.team_member_ids
        if scope.axis == "BRANCH":
            return customer.origin_branch_id == scope.branch_id
        if scope.axis == "TERRITORY":
            return customer.territory_id == scope.territory_id
        # PORTFOLIO: see list_directory's note — no membership signal yet.
        return False
