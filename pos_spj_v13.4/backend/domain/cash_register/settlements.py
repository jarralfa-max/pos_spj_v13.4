"""CASH-10 settlement classification; only physical cash affects the drawer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.domain.cash_register.exceptions import CashInvalidStateError


class CashSettlementClass(str, Enum):
    PHYSICAL_CASH = "PHYSICAL_CASH"
    ELECTRONIC = "ELECTRONIC"
    CREDIT = "CREDIT"
    COMMERCIAL_INSTRUMENT = "COMMERCIAL_INSTRUMENT"
    FUTURE_INSTRUMENT = "FUTURE_INSTRUMENT"


@dataclass(frozen=True, slots=True)
class CashSettlementDefinition:
    canonical_type: str
    classification: CashSettlementClass
    affects_drawer: bool
    operational: bool = True


_DEFINITIONS = {
    "CASH": CashSettlementDefinition("CASH", CashSettlementClass.PHYSICAL_CASH, True),
    "BANK_CARD": CashSettlementDefinition("BANK_CARD", CashSettlementClass.ELECTRONIC, False),
    "BANK_TRANSFER": CashSettlementDefinition("BANK_TRANSFER", CashSettlementClass.ELECTRONIC, False),
    "PAYMENT_LINK": CashSettlementDefinition("PAYMENT_LINK", CashSettlementClass.ELECTRONIC, False),
    "PAYMENT_PROCESSOR": CashSettlementDefinition("PAYMENT_PROCESSOR", CashSettlementClass.ELECTRONIC, False),
    "CUSTOMER_CREDIT": CashSettlementDefinition("CUSTOMER_CREDIT", CashSettlementClass.CREDIT, False),
    "LOYALTY_POINTS": CashSettlementDefinition("LOYALTY_POINTS", CashSettlementClass.COMMERCIAL_INSTRUMENT, False),
    "COUPON": CashSettlementDefinition("COUPON", CashSettlementClass.COMMERCIAL_INSTRUMENT, False),
    "VOUCHER": CashSettlementDefinition("VOUCHER", CashSettlementClass.COMMERCIAL_INSTRUMENT, False),
    "REFUND_VOUCHER": CashSettlementDefinition("REFUND_VOUCHER", CashSettlementClass.COMMERCIAL_INSTRUMENT, False),
    "PROMOTIONAL_VOUCHER": CashSettlementDefinition("PROMOTIONAL_VOUCHER", CashSettlementClass.COMMERCIAL_INSTRUMENT, False),
    "STORE_CREDIT": CashSettlementDefinition("STORE_CREDIT", CashSettlementClass.COMMERCIAL_INSTRUMENT, False),
    "PROMOTIONAL_BALANCE": CashSettlementDefinition("PROMOTIONAL_BALANCE", CashSettlementClass.COMMERCIAL_INSTRUMENT, False),
    "GIFT_CARD": CashSettlementDefinition("GIFT_CARD", CashSettlementClass.FUTURE_INSTRUMENT, False, False),
}

_ALIASES = {
    "EFECTIVO": "CASH", "CASH": "CASH",
    "TARJETA": "BANK_CARD", "CARD": "BANK_CARD", "BANK_CARD": "BANK_CARD",
    "TRANSFERENCIA": "BANK_TRANSFER", "TRANSFER": "BANK_TRANSFER", "BANK_TRANSFER": "BANK_TRANSFER",
    "PAYMENT_LINK": "PAYMENT_LINK", "LINK_PAGO": "PAYMENT_LINK",
    "MERCADO PAGO": "PAYMENT_PROCESSOR", "MERCADO_PAGO": "PAYMENT_PROCESSOR", "PAYMENT_PROCESSOR": "PAYMENT_PROCESSOR",
    "CREDITO": "CUSTOMER_CREDIT", "CRÉDITO": "CUSTOMER_CREDIT", "ON_CREDIT": "CUSTOMER_CREDIT", "CUSTOMER_CREDIT": "CUSTOMER_CREDIT",
    "PUNTOS": "LOYALTY_POINTS", "LOYALTY_POINTS": "LOYALTY_POINTS",
    "CUPON": "COUPON", "CUPÓN": "COUPON", "COUPON": "COUPON",
    "VALE": "VOUCHER", "VOUCHER": "VOUCHER",
    "REFUND_VOUCHER": "REFUND_VOUCHER", "VALE_REEMBOLSO": "REFUND_VOUCHER",
    "PROMOTIONAL_VOUCHER": "PROMOTIONAL_VOUCHER", "VALE_PROMOCIONAL": "PROMOTIONAL_VOUCHER",
    "SALDO_A_FAVOR": "STORE_CREDIT", "SALDO A FAVOR": "STORE_CREDIT", "STORE_CREDIT": "STORE_CREDIT",
    "SALDO_PROMOCIONAL": "PROMOTIONAL_BALANCE", "PROMOTIONAL_BALANCE": "PROMOTIONAL_BALANCE",
    "GIFT_CARD": "GIFT_CARD", "GIFT CARD": "GIFT_CARD", "TARJETA_DE_REGALO": "GIFT_CARD",
}


def classify_settlement(raw_type: str, *, allow_future: bool = False) -> CashSettlementDefinition:
    key = str(raw_type or "").strip().upper()
    canonical = _ALIASES.get(key)
    if canonical is None:
        raise CashInvalidStateError(f"Medio de pago no clasificado: {raw_type}")
    definition = _DEFINITIONS[canonical]
    if not definition.operational and not allow_future:
        raise CashInvalidStateError(
            f"El medio {definition.canonical_type} está reservado para una fase futura")
    return definition
