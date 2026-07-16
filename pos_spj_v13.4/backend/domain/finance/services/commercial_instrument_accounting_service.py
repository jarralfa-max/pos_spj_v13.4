"""CommercialInstrumentAccountingService — recognition rules per instrument type.

Builds declarative line specs from posting profiles. It never hardcodes account
ids and never owns the operational instrument.
"""

from __future__ import annotations

from backend.domain.finance.entities.commercial_obligation import CommercialObligation
from backend.domain.finance.entities.posting_profile import PostingProfile
from backend.domain.finance.enums import (
    CommercialInstrumentType,
    RecognitionBasis,
)
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.policies.commercial_instrument_posting_policy import (
    CommercialInstrumentPostingPolicy,
)
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money


class CommercialInstrumentAccountingService:
    def __init__(self) -> None:
        self._policy = CommercialInstrumentPostingPolicy()

    # ── recognition (issuance) ────────────────────────────────────────────
    def recognition_lines(
        self,
        obligation: CommercialObligation,
        profile: PostingProfile,
        *,
        settlement_amount: Money | None = None,
    ) -> list[LineSpec]:
        """Lines for the issuance of an instrument, according to its nature.

        - LIABILITY basis: Dr expense/contra-revenue (or cash for sold instruments),
          Cr instrument liability.
        - THIRD_PARTY_RECEIVABLE: Dr third-party receivable, Cr liability.
        - PROMOTIONAL_EXPENSE: Dr promotional expense, Cr promotional balance account.
        - NO_INITIAL_RECOGNITION: no lines at issuance.
        """
        amount = obligation.recognized_amount
        basis = obligation.recognition_basis
        if basis is RecognitionBasis.NO_INITIAL_RECOGNITION or amount.is_zero():
            return []

        if self._policy.is_sold_instrument(obligation.instrument_type):
            cash_amount = settlement_amount if settlement_amount is not None else amount
            liability_role = ("gift_card_liability_account_id"
                              if obligation.instrument_type is CommercialInstrumentType.GIFT_CARD
                              and profile.has_account("gift_card_liability_account_id")
                              else "liability_account_id")
            return [
                LineSpec(profile.account_for("cash_account_id"), debit=cash_amount,
                         description="Venta de instrumento prepago"),
                LineSpec(profile.account_for(liability_role), credit=cash_amount,
                         description="Obligación por instrumento prepago"),
            ]

        if basis is RecognitionBasis.LIABILITY:
            debit_role = ("contra_revenue_account_id"
                          if profile.has_account("contra_revenue_account_id")
                          else "expense_account_id")
            return [
                LineSpec(profile.account_for(debit_role), debit=amount,
                         description="Reconocimiento de instrumento comercial"),
                LineSpec(profile.account_for("liability_account_id"), credit=amount,
                         description="Obligación por instrumento pendiente"),
            ]

        if basis is RecognitionBasis.THIRD_PARTY_RECEIVABLE:
            return [
                LineSpec(profile.account_for("third_party_receivable_account_id"), debit=amount,
                         description="CxC a entidad financiadora"),
                LineSpec(profile.account_for("liability_account_id"), credit=amount,
                         description="Obligación por instrumento financiado"),
            ]

        if basis is RecognitionBasis.PROMOTIONAL_EXPENSE:
            return [
                LineSpec(profile.account_for("expense_account_id"), debit=amount,
                         description="Gasto promocional"),
                LineSpec(profile.account_for("promotional_balance_account_id"), credit=amount,
                         description="Saldo promocional no reembolsable"),
            ]

        raise FinanceDomainError(f"Unsupported recognition basis: {basis}")

    # ── redemption ────────────────────────────────────────────────────────
    def redemption_lines(
        self,
        obligation: CommercialObligation,
        profile: PostingProfile,
        redeemed_amount: Money,
        *,
        actual_cost: Money | None = None,
    ) -> list[LineSpec]:
        """Lines for a redemption.

        With prior liability: Dr liability, Cr revenue (or clearing). If the actual
        reward cost differs from the estimate, the difference hits breakage income
        or expense.
        Without prior recognition (promotional coupon): Dr contra-revenue,
        Cr clearing/revenue at redemption time.
        """
        basis = obligation.recognition_basis
        lines: list[LineSpec] = []

        if basis is RecognitionBasis.NO_INITIAL_RECOGNITION:
            credit_role = ("clearing_account_id" if profile.has_account("clearing_account_id")
                           else "revenue_account_id")
            lines.append(LineSpec(profile.account_for("contra_revenue_account_id"),
                                  debit=redeemed_amount, description="Canje de cupón promocional"))
            lines.append(LineSpec(profile.account_for(credit_role),
                                  credit=redeemed_amount, description="Aplicación de canje"))
            return lines

        liability_role = ("gift_card_liability_account_id"
                          if obligation.instrument_type is CommercialInstrumentType.GIFT_CARD
                          and profile.has_account("gift_card_liability_account_id")
                          else "liability_account_id")
        credit_role = ("revenue_account_id" if profile.has_account("revenue_account_id")
                       else "clearing_account_id")
        lines.append(LineSpec(profile.account_for(liability_role), debit=redeemed_amount,
                              description="Cancelación de obligación por canje"))
        lines.append(LineSpec(profile.account_for(credit_role), credit=redeemed_amount,
                              description="Reconocimiento por canje"))

        if actual_cost is not None and actual_cost.amount != redeemed_amount.amount:
            difference = actual_cost.subtract(redeemed_amount)
            if difference.is_positive():
                lines.append(LineSpec(profile.account_for("expense_account_id"),
                                      debit=difference,
                                      description="Costo real mayor a estimación"))
                lines.append(LineSpec(profile.account_for(credit_role),
                                      credit=difference,
                                      description="Ajuste por costo real"))
            else:
                gain = difference.abs()
                lines.append(LineSpec(profile.account_for(credit_role),
                                      debit=gain, description="Ajuste por costo real menor"))
                lines.append(LineSpec(profile.account_for("breakage_income_account_id"),
                                      credit=gain,
                                      description="Ingreso por diferencia de estimación"))
        return lines

    # ── expiration (breakage) ─────────────────────────────────────────────
    def expiration_lines(self, obligation: CommercialObligation, profile: PostingProfile,
                         released_amount: Money) -> list[LineSpec]:
        """Expiration releases the obligation into breakage income — never silently."""
        if released_amount.is_zero():
            return []
        if obligation.recognition_basis is RecognitionBasis.NO_INITIAL_RECOGNITION:
            return []
        liability_role = ("gift_card_liability_account_id"
                          if obligation.instrument_type is CommercialInstrumentType.GIFT_CARD
                          and profile.has_account("gift_card_liability_account_id")
                          else "liability_account_id")
        if obligation.recognition_basis is RecognitionBasis.PROMOTIONAL_EXPENSE:
            liability_role = "promotional_balance_account_id"
        return [
            LineSpec(profile.account_for(liability_role), debit=released_amount,
                     description="Liberación de obligación por vencimiento"),
            LineSpec(profile.account_for("breakage_income_account_id"), credit=released_amount,
                     description="Ingreso por expiración (breakage)"),
        ]
