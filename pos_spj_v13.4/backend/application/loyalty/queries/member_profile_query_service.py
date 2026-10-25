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
    #: program_id → nombre, para no mostrar identificadores en pantalla (LOY-29).
    program_names: dict = field(default_factory=dict)


class LoyaltyMemberProfileQueryService:
    """Auditoría 968e0bc FID-06: devolvía saldo y movimientos de cualquier
    cliente sin saber quién preguntaba. Ahora exige actor y `puntos.ver`.
    El programa es de TODA la empresa (decisión del usuario: los puntos y las
    piezas valen en las cinco sucursales), así que no se filtra por sucursal."""

    def __init__(self, connection, *, authorization=None) -> None:
        self._connection = connection
        self._auth = authorization

    def get_profile(self, customer_id: str, *, actor_user_id: str = "",
                    recent_limit: int = 20) -> LoyaltyMemberProfileView:
        from backend.application.loyalty.permissions import LoyaltyPermissions
        from backend.domain.loyalty.exceptions import LoyaltyPermissionDeniedError

        if self._auth is None:
            raise LoyaltyPermissionDeniedError("Consulta de puntos sin autorización configurada")
        self._auth.require(actor_user_id, LoyaltyPermissions.POINTS_VIEW)
        with LoyaltyUnitOfWork(self._connection, owns_transaction=False) as uow:
            account = uow.accounts.get_by_customer_id(customer_id)
            if account is None:
                return LoyaltyMemberProfileView(found=False)
            ledger = uow.transactions.list_for_account(account.id)
            balance = LoyaltyBalancePolicy.balance(ledger)
            memberships = tuple(uow.memberships.list_for_account(account.id))
            rewards: list[Reward] = []
            program_names: dict[str, str] = {}
            for membership in memberships:
                rewards.extend(uow.rewards.list_active_for_program(membership.program_id))
                program = uow.programs.get(membership.program_id)
                program_names[membership.program_id] = program.name if program else ""
            recent = tuple(sorted(ledger, key=lambda t: t.created_at, reverse=True)[:recent_limit])
            return LoyaltyMemberProfileView(
                found=True, account=account, balance=balance, memberships=memberships,
                recent_transactions=recent, available_rewards=tuple(rewards),
                program_names=program_names)
