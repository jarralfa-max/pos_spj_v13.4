"""ProcurementImmediatePaymentBridgeHandler — SUPPLIER_PAYMENT_SCHEDULED
(procurement bounded context, contado/immediate-payment direct purchases).

`ConfirmDirectPurchaseUseCase` correctly emits `PURCHASE_PAYMENT_REQUESTED`
for an immediate-payment purchase and deliberately never books a CxP for it
(only a credit purchase does, via the supplier-invoice matching flow — see
`ProcurementPayableBridgeHandler`) — but until this handler, nothing ever
subscribed the derived `SUPPLIER_PAYMENT_SCHEDULED` event either. A contado
purchase therefore left NO financial trace at all: no journal entry, no
record that money moved. This closes that gap by posting the recognition +
settlement as a single balanced entry (Debit Inventario/Gasto/Activo per
`purchase_nature`, Credit the resolved treasury account) — there is no
payable to settle, so this never touches `Payable`/`CreatePayableUseCase`.

Resolving WHICH treasury account to credit is the one genuinely new design
decision this handler makes, and it is deliberately conservative:
procurement's `payment_source` (`PaymentSource` enum: PETTY_CASH,
TREASURY_ACCOUNT, BANK_TRANSFER, AUTHORIZED_CARD, MERCADO_PAGO,
OTHER_CONFIGURED_SOURCE) and Finance's `TreasuryAccountType` (BANK,
CASH_REGISTER, PETTY_CASH, GENERAL_CASH, PAYMENT_PROCESSOR, DIGITAL_WALLET,
CLEARING_ACCOUNT) are different enums with no existing mapping anywhere in
the codebase. Only the three unambiguous correspondences are mapped
(PETTY_CASH->PETTY_CASH, BANK_TRANSFER->BANK, MERCADO_PAGO->PAYMENT_PROCESSOR)
— the rest (TREASURY_ACCOUNT is generic, AUTHORIZED_CARD could mean either a
processor or a bank account, OTHER_CONFIGURED_SOURCE is explicitly
unspecified) are left unmapped on purpose. If resolution then finds zero or
more than one active matching account (branch-scoped when the purchase
carries a `branch_id`, else global), this handler logs and does nothing
rather than guess — a missing journal entry is a visible, fixable gap; a
journal entry posted against the wrong treasury account is a silent,
expensive one. `POS_CASH`/`POS_OPERATIVE_CASH`/`CAJA_POS` never reach this
handler at all — `downstream_translators.py::on_payment_requested` already
rejects those sources before publishing.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.enums import JournalType, PostingPurpose, TreasuryAccountType
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork

logger = logging.getLogger("spj.finance.procurement_immediate_payment_bridge")

#: Only the correspondences with one obviously-correct answer. See module
#: docstring — deliberately not exhaustive.
_UNAMBIGUOUS_SOURCE_TO_ACCOUNT_TYPE = {
    "PETTY_CASH": TreasuryAccountType.PETTY_CASH,
    "BANK_TRANSFER": TreasuryAccountType.BANK,
    "MERCADO_PAGO": TreasuryAccountType.PAYMENT_PROCESSOR,
}

#: Mirrors `ProcurementPayableBridgeHandler`'s own mapping/fallback exactly —
#: one shared convention for "which account recognizes this purchase_nature."
_NATURE_ACCOUNT_ROLE = {
    "INVENTORY": "inventory_account_id",
    "EXPENSE": "expense_account_id",
    "ASSET": "asset_account_id",
    "SERVICE": "expense_account_id",
}


class ProcurementImmediatePaymentBridgeHandler:
    event_name = "SUPPLIER_PAYMENT_SCHEDULED"

    def __init__(self, connection) -> None:
        self._connection = connection
        self._engine = PostingEngine()

    def handle(self, payload: dict) -> None:
        if str(payload.get("source_module") or "") != "procurement":
            return  # SUPPLIER_PAYMENT_SCHEDULED may originate elsewhere later
        document_id = str(payload.get("document_id") or "").strip()
        operation_id = str(payload.get("operation_id") or "").strip()
        amount = payload.get("amount")
        if not document_id or not operation_id or not amount:
            raise ValueError(
                "SUPPLIER_PAYMENT_SCHEDULED (procurement) requiere document_id, "
                "operation_id y amount")
        nature_subtotals: dict = payload.get("nature_subtotals") or {}
        if not nature_subtotals:
            # payload predates the breakdown, or every line was captured
            # before this fix — never guess an account, just skip.
            return

        currency_code = str(payload.get("currency_code") or "MXN")
        branch_id = payload.get("branch_id") or None

        treasury_account = self._resolve_treasury_account(
            payment_source=str(payload.get("payment_source") or ""), branch_id=branch_id)
        if treasury_account is None:
            return  # already logged inside _resolve_treasury_account

        issue_date = _issue_date(payload)
        with FinanceUnitOfWork(self._connection) as uow:
            existing = uow.journal_entries.find_by_posting_reference(
                "procurement", document_id, PostingPurpose.SUPPLIER_PAYMENT)
            if existing is not None:
                return  # idempotent: already posted for this document

            profile = uow.posting_profiles.find_effective("PURCHASE", issue_date)
            if profile is None:
                raise ValueError(
                    f"No hay perfil contable PURCHASE vigente en {issue_date.isoformat()}")

            lines: list[LineSpec] = []
            debited = Decimal("0")
            for nature, subtotal in nature_subtotals.items():
                money = Money.from_string(str(subtotal), currency_code)
                if not money.is_positive():
                    continue
                role = _NATURE_ACCOUNT_ROLE.get(nature, "expense_account_id")
                lines.append(LineSpec(profile.account_for(role), debit=money,
                                      description=f"Compra de contado {document_id} ({nature})"))
                debited += money.amount
            tax_total = Money.from_string(str(payload.get("tax_total") or "0"), currency_code)
            if tax_total.is_positive():
                lines.append(LineSpec(profile.account_for("tax_account_id"), debit=tax_total,
                                      description=f"IVA acreditable {document_id}"))
                debited += tax_total.amount
            if not lines:
                return

            total = Money.from_string(str(amount), currency_code)
            if debited != total.amount:
                raise ValueError(
                    f"Pago de contado {document_id}: subtotales por naturaleza + impuesto "
                    f"({debited}) != monto total ({total.amount})")
            lines.append(LineSpec(treasury_account.ledger_account_id, credit=total,
                                  description=f"Pago de contado a proveedor {document_id}"))

            self._engine.post(
                uow, JournalType.PURCHASES, issue_date,
                f"Compra de contado {document_id}",
                PostingReference("procurement", document_id, PostingPurpose.SUPPLIER_PAYMENT,
                                 operation_id),
                lines, currency_code=currency_code, branch_id=branch_id,
            )

    def _resolve_treasury_account(self, *, payment_source: str, branch_id: str | None):
        account_type = _UNAMBIGUOUS_SOURCE_TO_ACCOUNT_TYPE.get(payment_source)
        if account_type is None:
            logger.warning(
                "procurement immediate payment: payment_source=%r has no unambiguous "
                "TreasuryAccountType mapping — skipping, refusing to guess",
                payment_source)
            return None
        with FinanceUnitOfWork(self._connection) as uow:
            candidates = [a for a in uow.treasury.list_active() if a.account_type == account_type]
        if branch_id:
            branch_scoped = [a for a in candidates if a.branch_id == branch_id]
            if branch_scoped:
                candidates = branch_scoped
            else:
                candidates = [a for a in candidates if a.branch_id is None]
        if len(candidates) != 1:
            logger.warning(
                "procurement immediate payment: %d active %s treasury account(s) found "
                "(branch_id=%r) — expected exactly 1, skipping",
                len(candidates), account_type.value, branch_id)
            return None
        return candidates[0]


def _issue_date(payload: dict) -> date:
    timestamp = str(payload.get("timestamp") or "")
    if timestamp:
        try:
            return date.fromisoformat(timestamp[:10])
        except ValueError:
            pass
    return date.today()
