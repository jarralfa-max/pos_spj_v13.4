"""TreasuryService — domain rules for treasury accounts and transfers."""

from __future__ import annotations

from backend.domain.finance.entities.treasury_account import TreasuryAccount
from backend.domain.finance.enums import SettlementType, TreasuryAccountType
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.value_objects.money import Money

#: Settlement types that move real money into a treasury account.
CASH_LIKE_SETTLEMENTS = frozenset({
    SettlementType.CASH,
    SettlementType.CARD,
    SettlementType.BANK_TRANSFER,
    SettlementType.PAYMENT_PROCESSOR,
})

#: Settlement types that must never be recorded as treasury inflows.
NON_CASH_SETTLEMENTS = frozenset({
    SettlementType.ON_CREDIT,
    SettlementType.LOYALTY_POINTS,
    SettlementType.COUPON,
    SettlementType.VOUCHER,
    SettlementType.GIFT_CARD,
    SettlementType.STORE_CREDIT,
    SettlementType.PROMOTIONAL_BALANCE,
})


class TreasuryService:
    def validate_transfer(self, source: TreasuryAccount, target: TreasuryAccount,
                          amount: Money) -> None:
        if source.id == target.id:
            raise FinanceDomainError("Treasury transfer requires two different accounts")
        if not source.active or not target.active:
            raise FinanceDomainError("Both treasury accounts must be active")
        if not amount.is_positive():
            raise FinanceDomainError("Transfer amount must be positive")
        if source.currency_code != amount.currency_code or target.currency_code != amount.currency_code:
            raise FinanceDomainError("Transfer currency must match both treasury accounts")

    @staticmethod
    def is_cash_settlement(settlement_type: SettlementType) -> bool:
        return settlement_type in CASH_LIKE_SETTLEMENTS

    @staticmethod
    def assert_not_promotional_cash(account: TreasuryAccount) -> None:
        """An internal promotional wallet must never behave as a cash account."""
        if account.account_type is TreasuryAccountType.DIGITAL_WALLET:
            raise FinanceDomainError(
                "A promotional/internal wallet is not cash; classify its effect via "
                "a commercial obligation posting profile"
            )
