"""LoyaltyMemberProfileQueryService (LOY-25) — read-only assembly of a
member's account, memberships, points balance and recent ledger for the
Fidelidad desktop UI's "Perfil de miembro" page.

Mirrors ``backend.application.customers.queries.customer_360_query_service``'s
role for the Fidelidad module: a pure read path over already-built LOY-2..9
repositories, never a new business calculation — "la UI no calcula KPIs"
(§90) applies here too: this service returns the balance/lists, the page
only renders them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from backend.domain.loyalty.entities.loyalty_account import LoyaltyAccount
from backend.domain.loyalty.entities.loyalty_membership import LoyaltyMembership
from backend.domain.loyalty.entities.loyalty_transaction import LoyaltyTransaction
from backend.domain.loyalty.entities.reward import Reward
from backend.domain.loyalty.policies.balance_policy import LoyaltyBalancePolicy
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork


@dataclass(frozen=True)
class LoyaltyMemberProfileView:
    found: bool
    account: LoyaltyAccount | None = None
    balance: Decimal = Decimal("0")
    memberships: tuple[LoyaltyMembership, ...] = field(default_factory=tuple)
    recent_transactions: tuple[LoyaltyTransaction, ...] = field(default_factory=tuple)
    available_rewards: tuple[Reward, ...] = field(default_factory=tuple)


class LoyaltyMemberProfileQueryService:
    def __init__(self, connection) -> None:
        self._connection = connection

    def get_profile(self, customer_id: str, *, recent_limit: int = 20) -> LoyaltyMemberProfileView:
        with LoyaltyUnitOfWork(self._connection, owns_transaction=False) as uow:
            account = uow.accounts.get_by_customer_id(customer_id)
            if account is None:
                return LoyaltyMemberProfileView(found=False)
            ledger = uow.transactions.list_for_account(account.id)
            balance = LoyaltyBalancePolicy.balance(ledger)
            memberships = tuple(uow.memberships.list_for_account(account.id))
            rewards: list[Reward] = []
            for membership in memberships:
                rewards.extend(uow.rewards.list_active_for_program(membership.program_id))
            recent = tuple(sorted(ledger, key=lambda t: t.created_at, reverse=True)[:recent_limit])
            return LoyaltyMemberProfileView(
                found=True, account=account, balance=balance, memberships=memberships,
                recent_transactions=recent, available_rewards=tuple(rewards))
