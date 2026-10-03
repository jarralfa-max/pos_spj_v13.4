"""Resumen de fidelidad de UN cliente, para quien no es Fidelidad (§52).

Clientes (Cliente 360) muestra "inscrito / puntos / nivel" y antes lo leía de
`loyalty_snapshots`: una tabla legacy que NADIE escribe desde la
reconstrucción. El efecto era silencioso: todo cliente aparecía "no inscrito"
con 0 puntos aunque tuviera saldo en el libro canónico.

Ahora Fidelidad expone su propio resumen y Clientes lo consume sin tocar
ninguna tabla de Fidelidad (guardia `test_customers_crm_does_not_own_loyalty`).

* El saldo se deriva del libro (`loyalty_transactions`), nunca de un campo.
* "Inscrito" = tiene cuenta de fidelidad. La cuenta la abre la primera compra
  cobrada (SALES-23), sin necesidad de una membresía a un programa.
* El nivel y el programa salen de la membresía ACTIVA más reciente; sin
  membresía no hay nivel (no se fabrica "Bronce").
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.loyalty.enums import MembershipStatus
from backend.domain.loyalty.policies.balance_policy import LoyaltyBalancePolicy
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork


@dataclass(frozen=True)
class LoyaltyCustomerSnapshot:
    customer_id: str
    enrolled: bool
    available_points: int
    account_status: str | None = None
    program_name: str | None = None
    tier_name: str | None = None


class LoyaltyCustomerSummaryQueryService:
    def __init__(self, connection) -> None:
        self._connection = connection

    def summary_for(self, customer_id: str) -> LoyaltyCustomerSnapshot:
        customer_id = str(customer_id or "").strip()
        if not customer_id:
            return LoyaltyCustomerSnapshot(customer_id="", enrolled=False, available_points=0)
        with LoyaltyUnitOfWork(self._connection, owns_transaction=False) as uow:
            account = uow.accounts.get_by_customer_id(customer_id)
            if account is None:
                return LoyaltyCustomerSnapshot(
                    customer_id=customer_id, enrolled=False, available_points=0)
            balance = LoyaltyBalancePolicy.balance(uow.transactions.list_for_account(account.id))
            activas = sorted(
                (m for m in uow.memberships.list_for_account(account.id)
                 if m.status is MembershipStatus.ACTIVE),
                key=lambda m: m.enrolled_at, reverse=True)
            program_name = tier_name = None
            if activas:
                program = uow.programs.get(activas[0].program_id)
                program_name = program.name if program else None
                if activas[0].current_tier_id:
                    tier = uow.tiers.get(activas[0].current_tier_id)
                    tier_name = tier.name if tier else None
            return LoyaltyCustomerSnapshot(
                customer_id=customer_id, enrolled=True,
                available_points=max(0, int(balance)),
                account_status=account.status.value,
                program_name=program_name, tier_name=tier_name)


__all__ = ["LoyaltyCustomerSnapshot", "LoyaltyCustomerSummaryQueryService"]
