"""FASES 9, 13, 14 — nómina, corte de caja, inventario/merma/producción."""

import pytest

from backend.application.event_handlers.finance.cash_shift_closed_handler import (
    CashShiftClosedHandler,
)
from backend.application.event_handlers.finance.inventory_adjustment_handler import (
    InventoryAdjustmentHandler,
    ProductionCompletedHandler,
)
from backend.application.event_handlers.finance.waste_registered_handler import (
    WasteRegisteredHandler,
)
from backend.application.event_handlers.finance.payroll_paid_handler import PayrollPaidHandler
from backend.domain.finance.enums import PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import new_uuid

OCCURRED = "2026-07-16T20:00:00Z"


class TestPayroll:
    def _payload(self, **overrides):
        payload = {
            "event_id": new_uuid(), "operation_id": new_uuid(),
            "payroll_run_id": new_uuid(), "occurred_at": OCCURRED,
            "gross_salaries": "80000.00", "social_security": "12000.00",
            "net_paid": "76000.00", "currency_code": "MXN",
        }
        payload.update(overrides)
        return payload

    def test_single_entry_per_payroll(self, bootstrapped_conn):
        handler = PayrollPaidHandler(bootstrapped_conn)
        payload = self._payload()
        handler.handle(payload)
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            entry = uow.journal_entries.find_by_posting_reference(
                "hr", payload["payroll_run_id"], PostingPurpose.PAYROLL)
        assert entry is not None and entry.is_balanced()
        assert entry.total_debits().to_string() == "92000.00"

    def test_double_processing_blocked(self, bootstrapped_conn):
        handler = PayrollPaidHandler(bootstrapped_conn)
        payload = self._payload()
        handler.handle(payload)
        handler.handle(payload)  # same event
        # distinct retry event, same payroll run:
        handler.handle(self._payload(payroll_run_id=payload["payroll_run_id"]))
        count = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM journal_entries WHERE posting_purpose='PAYROLL'"
        ).fetchone()[0]
        assert count == 1

    def test_net_exceeding_gross_rejected(self, bootstrapped_conn):
        handler = PayrollPaidHandler(bootstrapped_conn)
        with pytest.raises(FinanceDomainError):
            handler.handle(self._payload(net_paid="95000.00"))


class TestCashShift:
    def test_shift_close_with_shortage(self, bootstrapped_conn):
        handler = CashShiftClosedHandler(bootstrapped_conn)
        shift_id = new_uuid()
        handler.handle({
            "event_id": new_uuid(), "operation_id": new_uuid(),
            "shift_id": shift_id, "occurred_at": OCCURRED,
            "expected_cash": "5000.00", "counted_cash": "4950.00",
        })
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            entry = uow.journal_entries.find_by_posting_reference(
                "cash", shift_id, PostingPurpose.CASH_SHIFT_CLOSE)
        assert entry.is_balanced()
        difference_events = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM finance_outbox WHERE event_name='CASH_DIFFERENCE_DETECTED'"
        ).fetchone()[0]
        assert difference_events == 1

    def test_shift_close_with_overage(self, bootstrapped_conn):
        handler = CashShiftClosedHandler(bootstrapped_conn)
        shift_id = new_uuid()
        handler.handle({
            "event_id": new_uuid(), "operation_id": new_uuid(),
            "shift_id": shift_id, "occurred_at": OCCURRED,
            "expected_cash": "5000.00", "counted_cash": "5020.00",
        })
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            entry = uow.journal_entries.find_by_posting_reference(
                "cash", shift_id, PostingPurpose.CASH_SHIFT_CLOSE)
        assert entry.is_balanced()
        assert entry.total_debits().to_string() == "5020.00"


class TestInventoryEvents:
    def test_waste_posts_cost(self, bootstrapped_conn):
        handler = WasteRegisteredHandler(bootstrapped_conn)
        waste_id = new_uuid()
        handler.handle({
            "event_id": new_uuid(), "operation_id": new_uuid(),
            "waste_id": waste_id, "occurred_at": OCCURRED, "amount": "350.00",
        })
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            entry = uow.journal_entries.find_by_posting_reference(
                "inventory", waste_id, PostingPurpose.WASTE)
        assert entry.is_balanced()
        assert entry.total_debits().to_string() == "350.00"

    def test_adjustment_directions(self, bootstrapped_conn):
        handler = InventoryAdjustmentHandler(bootstrapped_conn)
        for direction in ("INCREASE", "DECREASE"):
            adjustment_id = new_uuid()
            handler.handle({
                "event_id": new_uuid(), "operation_id": new_uuid(),
                "adjustment_id": adjustment_id, "occurred_at": OCCURRED,
                "amount": "120.00", "direction": direction,
            })
            with FinanceUnitOfWork(bootstrapped_conn) as uow:
                entry = uow.journal_entries.find_by_posting_reference(
                    "inventory", adjustment_id, PostingPurpose.INVENTORY_ADJUSTMENT)
            assert entry.is_balanced()

    def test_production_with_yield_loss(self, bootstrapped_conn):
        handler = ProductionCompletedHandler(bootstrapped_conn)
        production_id = new_uuid()
        handler.handle({
            "event_id": new_uuid(), "operation_id": new_uuid(),
            "production_id": production_id, "occurred_at": OCCURRED,
            "input_cost": "1000.00", "output_value": "930.00",
        })
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            entry = uow.journal_entries.find_by_posting_reference(
                "production", production_id, PostingPurpose.PRODUCTION)
        assert entry.is_balanced()
        assert entry.total_credits().to_string() == "1000.00"

    def test_production_cannot_create_profit(self, bootstrapped_conn):
        handler = ProductionCompletedHandler(bootstrapped_conn)
        with pytest.raises(FinanceDomainError):
            handler.handle({
                "event_id": new_uuid(), "operation_id": new_uuid(),
                "production_id": new_uuid(), "occurred_at": OCCURRED,
                "input_cost": "1000.00", "output_value": "1100.00",
            })
