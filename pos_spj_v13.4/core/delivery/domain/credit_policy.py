"""Delivery credit policy — single source of truth for when a delivery order
requires a customer-credit check, and for how much.

A delivery extends credit to the customer when it leaves the store with an
outstanding balance owed on account (e.g. "Anticipo + saldo" or an explicit
"crédito" method). Immediate-payment methods (cash/card on delivery, prepaid,
transfer, "ya pagado", "sin cobro") do NOT consume credit.

Backend in English; the matched payment-method strings come from the Spanish UI.
"""
from __future__ import annotations

from decimal import Decimal

# Tokens (lowercase) that indicate a balance owed on account → credit required.
_CREDIT_TOKENS = ("saldo", "credito", "crédito")


def requires_credit_check(pago_metodo: str | None) -> bool:
    """Return True if *pago_metodo* leaves a balance owed on the customer's account."""
    text = (pago_metodo or "").strip().lower()
    if not text:
        return False
    return any(token in text for token in _CREDIT_TOKENS)


def credit_amount(total: Decimal, anticipo: Decimal = Decimal("0")) -> Decimal:
    """Balance that will be carried on the customer's account.

    Uses Decimal exclusively. The credit amount is the order total minus any
    advance already paid, floored at zero.
    """
    total_d = Decimal(str(total or 0))
    anticipo_d = Decimal(str(anticipo or 0))
    return max(total_d - anticipo_d, Decimal("0"))
