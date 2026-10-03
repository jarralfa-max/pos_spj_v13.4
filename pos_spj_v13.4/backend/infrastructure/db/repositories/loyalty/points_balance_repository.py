"""Saldo de puntos de un cliente, derivado del ÚNICO libro: `loyalty_transactions`.

Hasta LOY-29 (2026-10-02) este repositorio sumaba además `loyalty_ledger`, el
libro legacy, para no dejar en cero a quien acumuló antes de la
reconstrucción. Se midió la base real: `loyalty_ledger` tenía CERO filas y
cero escritores, así que la doble lectura no protegía ningún saldo y sí
mantenía viva una segunda fuente de verdad (§11/§73: "Un ledger de puntos").
La migración 291 retira la tabla.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.loyalty.policies.balance_policy import LoyaltyBalancePolicy
from backend.infrastructure.db.repositories.loyalty.base import LoyaltyRepositoryBase


class LoyaltyPointsBalanceRepository(LoyaltyRepositoryBase):
    def balance_for_customer(self, customer_id: str) -> int:
        """Puntos disponibles, en entero.

        Los puntos son unidades enteras: el cliente tiene 150 puntos, no
        150.4. Se trunca hacia abajo para no regalar un punto que no existe.
        """
        saldo = self._canonical_balance(customer_id)
        return max(0, int(saldo))

    def _canonical_balance(self, customer_id: str) -> Decimal:
        """Saldo derivado del ledger (nunca de un campo).

        Sin cuenta de fidelidad el saldo es cero: un cliente que nunca compró
        identificado no tiene puntos, y eso no es un error que deba propagarse.
        """
        row = self._query_one(
            "SELECT id FROM loyalty_accounts WHERE customer_id=?", (customer_id,))
        if row is None:
            return Decimal("0")

        from backend.infrastructure.db.repositories.loyalty.transaction_repository import (
            LoyaltyTransactionRepository,
        )

        transacciones = LoyaltyTransactionRepository(self._conn).list_for_account(row["id"])
        return LoyaltyBalancePolicy.balance(transacciones)
