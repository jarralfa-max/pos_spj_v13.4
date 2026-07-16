"""FASE 6 — sales integration: cash, credit, discounts, COGS, mixed settlements."""

import pytest

from backend.application.event_handlers.finance.sale_completed_handler import (
    SaleCompletedHandler,
)
from backend.application.event_handlers.finance.sale_reversed_handler import (
    SaleReversedHandler,
)
from backend.domain.finance.entities.commercial_obligation import CommercialObligation
from backend.domain.finance.enums import (
    CommercialInstrumentType,
    CommercialObligationStatus,
    JournalEntryStatus,
    PostingPurpose,
    RecognitionBasis,
    ReceivableStatus,
)
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import new_uuid


def _sale_payload(**overrides):
    payload = {
        "event_id": new_uuid(),
        "operation_id": new_uuid(),
        "sale_id": new_uuid(),
        "folio": "V-0001",
        "branch_id": new_uuid(),
        "occurred_at": "2026-07-16T12:00:00Z",
        "currency_code": "MXN",
        "gross_total": "500.00",
        "discount_total": "30.00",
        "net_total": "470.00",
        "tax_total": "64.83",
        "cogs_total": "200.00",
        "settlements": [{"type": "CASH", "amount": "470.00"}],
    }
    payload.update(overrides)
    return payload


class TestCashSale:
    def test_posts_revenue_and_cogs(self, bootstrapped_conn):
        handler = SaleCompletedHandler(bootstrapped_conn)
        payload = _sale_payload()
        handler.handle(payload)
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            revenue = uow.journal_entries.find_by_posting_reference(
                "sales", payload["sale_id"], PostingPurpose.SALE_REVENUE)
            cogs = uow.journal_entries.find_by_posting_reference(
                "sales", payload["sale_id"], PostingPurpose.SALE_COGS)
        assert revenue is not None and revenue.status is JournalEntryStatus.POSTED
        assert revenue.total_debits().to_string() == "500.00"  # 470 cash + 30 discount
        assert cogs is not None and cogs.total_debits().to_string() == "200.00"

    def test_event_is_idempotent(self, bootstrapped_conn):
        handler = SaleCompletedHandler(bootstrapped_conn)
        payload = _sale_payload()
        handler.handle(payload)
        handler.handle(payload)  # same event_id: no duplicate effects
        count = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM journal_entries").fetchone()[0]
        assert count == 2  # revenue + cogs only

    def test_settlement_mismatch_rejected(self, bootstrapped_conn):
        handler = SaleCompletedHandler(bootstrapped_conn)
        payload = _sale_payload(settlements=[{"type": "CASH", "amount": "400.00"}])
        with pytest.raises(FinanceDomainError, match="liquidaciones"):
            handler.handle(payload)

    def test_float_amount_rejected(self, bootstrapped_conn):
        handler = SaleCompletedHandler(bootstrapped_conn)
        payload = _sale_payload(gross_total=500.0)
        with pytest.raises(FinanceDomainError, match="float"):
            handler.handle(payload)


class TestCreditSale:
    def test_credit_sale_creates_receivable(self, bootstrapped_conn):
        handler = SaleCompletedHandler(bootstrapped_conn)
        customer = new_uuid()
        payload = _sale_payload(
            customer_id=customer,
            settlements=[{"type": "ON_CREDIT", "amount": "470.00"}],
        )
        handler.handle(payload)
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            receivables = uow.receivables.list_open_by_customer(customer)
        assert len(receivables) == 1
        assert receivables[0].outstanding_amount.to_string() == "470.00"

    def test_credit_sale_without_customer_fails(self, bootstrapped_conn):
        handler = SaleCompletedHandler(bootstrapped_conn)
        payload = _sale_payload(settlements=[{"type": "ON_CREDIT", "amount": "470.00"}])
        with pytest.raises(FinanceDomainError, match="customer_id"):
            handler.handle(payload)
        # atomicity: nothing persisted
        assert bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM journal_entries").fetchone()[0] == 0


class TestMixedSettlements:
    def _recognize_gift_card(self, conn, amount="100.00"):
        instrument_id = new_uuid()
        with FinanceUnitOfWork(conn) as uow:
            obligation = CommercialObligation.recognize(
                CommercialInstrumentType.GIFT_CARD, "loyalty", instrument_id,
                RecognitionBasis.LIABILITY, Money.from_string(amount), new_uuid(),
            )
            uow.commercial_obligations.save(obligation)
        return instrument_id

    def test_mixed_cash_gift_card_credit(self, bootstrapped_conn):
        instrument_id = self._recognize_gift_card(bootstrapped_conn)
        handler = SaleCompletedHandler(bootstrapped_conn)
        payload = _sale_payload(
            customer_id=new_uuid(),
            settlements=[
                {"type": "CASH", "amount": "270.00"},
                {"type": "GIFT_CARD", "amount": "100.00", "instrument_id": instrument_id},
                {"type": "ON_CREDIT", "amount": "100.00"},
            ],
        )
        handler.handle(payload)
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            obligation = uow.commercial_obligations.find_by_instrument(
                CommercialInstrumentType.GIFT_CARD, instrument_id)
            entry = uow.journal_entries.find_by_posting_reference(
                "sales", payload["sale_id"], PostingPurpose.SALE_REVENUE)
        assert obligation.status is CommercialObligationStatus.REDEEMED
        assert obligation.outstanding_amount.is_zero()
        assert entry.is_balanced()

    def test_unrecognized_instrument_rejected(self, bootstrapped_conn):
        handler = SaleCompletedHandler(bootstrapped_conn)
        payload = _sale_payload(settlements=[
            {"type": "CASH", "amount": "370.00"},
            {"type": "GIFT_CARD", "amount": "100.00", "instrument_id": new_uuid()},
        ])
        with pytest.raises(FinanceDomainError, match="obligación reconocida"):
            handler.handle(payload)

    def test_gift_card_over_redemption_rejected(self, bootstrapped_conn):
        instrument_id = self._recognize_gift_card(bootstrapped_conn, amount="50.00")
        handler = SaleCompletedHandler(bootstrapped_conn)
        payload = _sale_payload(settlements=[
            {"type": "CASH", "amount": "370.00"},
            {"type": "GIFT_CARD", "amount": "100.00", "instrument_id": instrument_id},
        ])
        from backend.domain.finance.exceptions import ObligationAmountError
        with pytest.raises(ObligationAmountError):
            handler.handle(payload)


class TestSaleReversal:
    def test_reversal_mirrors_and_cancels_receivable(self, bootstrapped_conn):
        sale_handler = SaleCompletedHandler(bootstrapped_conn)
        customer = new_uuid()
        payload = _sale_payload(
            customer_id=customer,
            settlements=[{"type": "ON_CREDIT", "amount": "470.00"}],
        )
        sale_handler.handle(payload)

        reversal_handler = SaleReversedHandler(bootstrapped_conn)
        reversal_handler.handle({
            "event_id": new_uuid(), "operation_id": new_uuid(),
            "sale_id": payload["sale_id"], "reason": "devolución total",
            "occurred_at": "2026-07-17T10:00:00Z",
        })
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            original = uow.journal_entries.find_by_posting_reference(
                "sales", payload["sale_id"], PostingPurpose.SALE_REVENUE)
            receivables = uow.receivables.list_open_by_customer(customer)
        assert original.status is JournalEntryStatus.REVERSED
        assert receivables == []

    def test_reversal_is_idempotent(self, bootstrapped_conn):
        sale_handler = SaleCompletedHandler(bootstrapped_conn)
        payload = _sale_payload()
        sale_handler.handle(payload)
        reversal_handler = SaleReversedHandler(bootstrapped_conn)
        event = {
            "event_id": new_uuid(), "operation_id": new_uuid(),
            "sale_id": payload["sale_id"], "occurred_at": "2026-07-17T10:00:00Z",
        }
        reversal_handler.handle(event)
        reversal_handler.handle(event)  # repeated event
        # second distinct event for the same sale is also safe:
        reversal_handler.handle({**event, "event_id": new_uuid(), "operation_id": new_uuid()})
        entries = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM journal_entries").fetchone()[0]
        assert entries == 4  # revenue + cogs + 2 reversals, no more
