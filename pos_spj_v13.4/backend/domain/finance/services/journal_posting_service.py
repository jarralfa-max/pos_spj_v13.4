"""JournalPostingService — the only domain path to build, post and reverse entries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.domain.finance.entities.fiscal_period import FiscalPeriod
from backend.domain.finance.entities.journal_entry import JournalEntry, JournalLine
from backend.domain.finance.enums import LineRole
from backend.domain.finance.exceptions import (
    ExchangeRateNotFoundError,
    FinanceConfigurationError,
    UnbalancedJournalEntryError,
)
from backend.domain.finance.policies.balanced_entry_policy import BalancedEntryPolicy
from backend.domain.finance.policies.posting_period_policy import PostingPeriodPolicy
from backend.domain.finance.policies.reversal_policy import ReversalPolicy
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference


@dataclass(frozen=True, slots=True)
class LineSpec:
    """Declarative journal line: exactly one of debit/credit must be positive."""

    account_id: str
    debit: Money | None = None
    credit: Money | None = None
    description: str = ""
    cost_center_id: str | None = None
    profit_center_id: str | None = None
    branch_id: str | None = None
    project_id: str | None = None
    department_id: str | None = None
    customer_id: str | None = None
    supplier_id: str | None = None
    employee_id: str | None = None
    product_id: str | None = None
    source_reference: str = ""

    def line_kwargs(self) -> dict:
        return dict(cost_center_id=self.cost_center_id, profit_center_id=self.profit_center_id,
                    branch_id=self.branch_id, project_id=self.project_id,
                    department_id=self.department_id, customer_id=self.customer_id,
                    supplier_id=self.supplier_id, employee_id=self.employee_id,
                    product_id=self.product_id, source_reference=self.source_reference)


def _line_kwargs(line: JournalLine) -> dict:
    return dict(cost_center_id=line.cost_center_id, profit_center_id=line.profit_center_id,
                branch_id=line.branch_id, project_id=line.project_id,
                department_id=line.department_id, customer_id=line.customer_id,
                supplier_id=line.supplier_id, employee_id=line.employee_id,
                product_id=line.product_id, source_reference=line.source_reference,
                exchange_rate=line.exchange_rate)


class JournalPostingService:
    def __init__(self) -> None:
        self._balanced = BalancedEntryPolicy()
        self._period_policy = PostingPeriodPolicy()
        self._reversal_policy = ReversalPolicy()

    def build_entry(
        self,
        journal_id: str,
        entry_number: str,
        entry_date: date,
        fiscal_period: FiscalPeriod,
        description: str,
        posting_reference: PostingReference,
        line_specs: list[LineSpec],
        *,
        currency_code: str = "MXN",
        base_currency_code: str | None = None,
        exchange_rate: Decimal | None = None,
        rounding_account_id: str | None = None,
        branch_id: str | None = None,
        created_by: str | None = None,
        reversal_of_entry_id: str | None = None,
        source_document_type: str | None = None,
        validate: bool = True,
    ) -> JournalEntry:
        """Create the entry (VALIDATED unless ``validate=False``). Not yet posted.

        Moneda extranjera (§24): cada línea se convierte a la moneda base con
        el tipo de cambio de la operación. Si al redondear las conversiones los
        débitos y créditos base difieren (centavos), la diferencia va a una
        línea VISIBLE en ``rounding_account_id``; nunca se oculta en otra línea.
        """
        base_currency_code = (base_currency_code or currency_code).upper()
        currency_code = currency_code.upper()
        rate = self._rate(currency_code, base_currency_code, exchange_rate)
        entry = JournalEntry.create(
            journal_id=journal_id,
            entry_number=entry_number,
            entry_date=entry_date,
            fiscal_period_id=fiscal_period.id,
            description=description,
            posting_reference=posting_reference,
            currency_code=currency_code,
            base_currency_code=base_currency_code,
            branch_id=branch_id,
            created_by=created_by,
            reversal_of_entry_id=reversal_of_entry_id,
            source_document_type=source_document_type,
        )
        for spec in line_specs:
            kwargs = spec.line_kwargs()
            kwargs["exchange_rate"] = rate
            if spec.debit is not None and spec.debit.is_positive():
                entry.add_debit(spec.account_id, spec.debit, spec.description,
                                base_amount=self._to_base(spec.debit, rate, base_currency_code),
                                **kwargs)
            if spec.credit is not None and spec.credit.is_positive():
                entry.add_credit(spec.account_id, spec.credit, spec.description,
                                 base_amount=self._to_base(spec.credit, rate, base_currency_code),
                                 **kwargs)
        self._add_rounding(entry, rounding_account_id)
        if validate:
            self._balanced.enforce(entry)
            entry.validate(created_by)
        return entry

    def post(self, entry: JournalEntry, fiscal_period: FiscalPeriod, *,
             posted_by: str | None = None, allow_soft_closed: bool = False) -> None:
        """VALIDATED → POSTED under period control. POSTED entries are immutable."""
        self._period_policy.enforce(fiscal_period, entry.posting_date,
                                    allow_soft_closed=allow_soft_closed)
        entry.mark_posted(posted_by)

    def build_reversal(
        self,
        original: JournalEntry,
        reversal_entry_number: str,
        reversal_date: date,
        fiscal_period: FiscalPeriod,
        reason: str,
        posting_reference: PostingReference,
        *,
        created_by: str | None = None,
    ) -> JournalEntry:
        """Build the mirror entry of a POSTED original. The original is never edited."""
        self._reversal_policy.enforce(original, reason=reason)
        reversal = JournalEntry.create(
            journal_id=original.journal_id,
            entry_number=reversal_entry_number,
            entry_date=reversal_date,
            fiscal_period_id=fiscal_period.id,
            description=f"REVERSO de {original.entry_number}: {reason}",
            posting_reference=posting_reference,
            currency_code=original.currency_code,
            base_currency_code=original.base_currency_code,
            branch_id=original.branch_id,
            created_by=created_by,
            reversal_of_entry_id=original.id,
            source_document_type=original.source_document_type,
        )
        for line in original.lines:
            if line.line_role is LineRole.ROUNDING:
                amount = line.base_debit if line.base_debit.is_positive() else line.base_credit
                reversal.add_rounding(line.account_id, amount,
                                      debit=line.base_credit.is_positive())
                continue
            kwargs = _line_kwargs(line)
            if line.debit.is_positive():
                reversal.add_credit(line.account_id, line.debit, line.description,
                                    base_amount=line.base_debit, **kwargs)
            else:
                reversal.add_debit(line.account_id, line.credit, line.description,
                                   base_amount=line.base_credit, **kwargs)
        self._balanced.enforce(reversal)
        reversal.validate(created_by)
        return reversal

    def post_reversal(self, original: JournalEntry, reversal: JournalEntry,
                      fiscal_period: FiscalPeriod, *, posted_by: str | None = None) -> None:
        """Post the reversal and mark the original as REVERSED, atomically in domain terms."""
        self.post(reversal, fiscal_period, posted_by=posted_by)
        original.mark_reversed(reversal.id)

    # ── conversión ────────────────────────────────────────────────────────
    @staticmethod
    def _rate(currency_code: str, base_currency_code: str,
              exchange_rate: Decimal | None) -> Decimal:
        if currency_code == base_currency_code:
            if exchange_rate is not None and Decimal(str(exchange_rate)) != Decimal("1"):
                raise FinanceConfigurationError(
                    "Una operación en moneda base no lleva tipo de cambio distinto de 1")
            return Decimal("1")
        if exchange_rate is None:
            raise ExchangeRateNotFoundError(
                f"La operación en {currency_code} requiere tipo de cambio a {base_currency_code}")
        rate = Decimal(str(exchange_rate))
        if rate <= 0:
            raise ExchangeRateNotFoundError("El tipo de cambio debe ser mayor que cero")
        return rate

    @staticmethod
    def _to_base(amount: Money, rate: Decimal, base_currency_code: str) -> Money:
        if amount.currency_code == base_currency_code and rate == Decimal("1"):
            return amount
        return Money(amount.amount * rate, base_currency_code, amount.decimal_places,
                     amount.rounding_mode)

    @staticmethod
    def _add_rounding(entry: JournalEntry, rounding_account_id: str | None) -> None:
        normal = [line for line in entry.lines if line.line_role is LineRole.NORMAL]
        if not normal:
            return
        difference = entry.base_total_debits().amount - entry.base_total_credits().amount
        if difference == 0:
            return
        if entry.total_debits().amount != entry.total_credits().amount:
            return  # desbalance real: lo rechaza la política, no se "redondea"
        tolerance = Decimal("0.01") * len(normal)
        if abs(difference) > tolerance:
            raise UnbalancedJournalEntryError(
                f"La conversión dejó una diferencia de {difference} que excede el redondeo")
        if not rounding_account_id:
            raise FinanceConfigurationError(
                "Falta la cuenta de diferencias de redondeo en la configuración de Finanzas")
        entry.add_rounding(rounding_account_id,
                           Money(abs(difference), entry.base_currency_code),
                           debit=difference < 0)
