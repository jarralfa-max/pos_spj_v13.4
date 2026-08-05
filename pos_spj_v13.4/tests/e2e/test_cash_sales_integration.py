from decimal import Decimal
import importlib
import sqlite3
import unittest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.ledger_query_service import CashLedgerQueryService
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS
from backend.application.cash_register.sales_integration import CashSalesIntegrationService
from backend.application.cash_register.shift_use_cases import OpenCashShiftUseCase
from backend.application.event_handlers.cash_register.sales_cash_handlers import (
    SaleCancelledCashHandler, SaleCompletedCashHandler,
)
from backend.domain.cash_register.exceptions import CashInvalidStateError
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.infrastructure.db.repositories.cash_register.repositories import CashLedgerRepository
from backend.shared.events.event_contracts import create_domain_event
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


class _Permissions:
    def has_permission(self, user_id, permission_code): return permission_code in ALL_CASH_PERMISSIONS


class _Scopes:
    def can_access_branch(self, *, user_id, branch_id): return True


class CashSalesE2ETests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(self.db)
        self.branch, self.cashier = new_uuid(), new_uuid()
        self.register, self.drawer, self.terminal = new_uuid(), new_uuid(), new_uuid()
        now = "2026-08-03T00:00:00+00:00"
        self.db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                        (self.register, self.branch, "Caja", "ACTIVE", None, now, now))
        self.db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                        (self.drawer, self.branch, self.register, "Cajón", "ACTIVE", now, now))
        self.db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                        (self.terminal, self.branch, self.register, "POS", "ACTIVE", now, now))
        self.db.commit()
        auth = CashAuthorizationPolicy(_Permissions(), _Scopes())
        limit = CashMonetaryLimitPolicy(
            approval_threshold=Decimal("1000"), hard_cap=Decimal("5000"))
        self.shift_id = OpenCashShiftUseCase(auth, limit).execute(
            self.db, branch_id=self.branch, register_id=self.register,
            drawer_id=self.drawer, terminal_id=self.terminal,
            cashier_user_id=self.cashier, opening_amount=Decimal("100"),
            actor_user_id=self.cashier, operation_id=new_uuid()).entity_id

    def tearDown(self): self.db.close()

    def _event(self, *, sale_id=None, operation_id=None, lines=None, change="0"):
        return create_domain_event(
            event_name=EventName.SALE_COMPLETED,
            operation_id=operation_id or new_uuid(), entity_id=sale_id or new_uuid(),
            branch_id=self.branch, user_id=self.cashier, source_module="sales",
            payload={"payment_breakdown": lines or {}, "change": change})

    def _balance(self):
        return CashLedgerQueryService(CashLedgerRepository(self.db)).projection(
            self.shift_id).balance

    def test_cash_and_mixed_payments_record_only_net_cash(self):
        SaleCompletedCashHandler(self.db).handle(
            self._event(lines={"efectivo": "120"}, change="20"))
        SaleCompletedCashHandler(self.db).handle(
            self._event(lines={"efectivo": "40.25", "tarjeta": "59.75"}))
        self.assertEqual(self._balance(), Decimal("240.25"))
        rows = self.db.execute(
            "SELECT amount FROM cash_ledger_entries WHERE movement_type='CASH_SALE' ORDER BY recorded_at,id"
        ).fetchall()
        self.assertEqual(rows, [("100",), ("40.25",)])

    def test_card_sale_requires_shift_but_does_not_change_cash(self):
        SaleCompletedCashHandler(self.db).handle(
            self._event(lines={"tarjeta": "250"}))
        self.assertEqual(self._balance(), Decimal("100"))
        self.db.execute("UPDATE cash_shifts SET status='SUSPENDED' WHERE id=?", (self.shift_id,))
        self.db.commit()
        with self.assertRaises(CashInvalidStateError):
            SaleCompletedCashHandler(self.db).handle(
                self._event(lines={"tarjeta": "10"}))

    def test_sale_event_retry_is_idempotent(self):
        event = self._event(lines={"efectivo": "25"})
        first = SaleCompletedCashHandler(self.db).handle(event)
        second = SaleCompletedCashHandler(self.db).handle(event)
        self.assertEqual(first.ledger_entry_id, second.ledger_entry_id)
        self.assertTrue(second.idempotent)
        self.assertEqual(self._balance(), Decimal("125"))

    def test_cancellation_and_refund_compensate_without_editing_original(self):
        sale_id = new_uuid()
        SaleCompletedCashHandler(self.db).handle(
            self._event(sale_id=sale_id, lines={"cash": "75"}))
        original = self.db.execute(
            "SELECT * FROM cash_ledger_entries WHERE reference_id=? AND movement_type='CASH_SALE'",
            (sale_id,)).fetchone()
        cancellation = create_domain_event(
            event_name=EventName.SALE_CANCELLED, operation_id=new_uuid(),
            entity_id=sale_id, branch_id=self.branch, user_id=self.cashier,
            source_module="sales", payload={"reason": "Ticket cancelado"})
        result = SaleCancelledCashHandler(self.db).handle(cancellation)
        self.assertEqual(self.db.execute(
            "SELECT * FROM cash_ledger_entries WHERE reference_id=? AND movement_type='CASH_SALE'",
            (sale_id,)).fetchone(), original)
        self.assertEqual(self.db.execute(
            "SELECT direction,amount FROM cash_ledger_entries WHERE id=?",
            (result.entity_id,)).fetchone(), ("OUTFLOW", "75"))
        self.assertEqual(self._balance(), Decimal("100"))
        retry = SaleCancelledCashHandler(self.db).handle(cancellation)
        self.assertTrue(retry.idempotent)

    def test_preflight_rejects_sale_without_open_shift(self):
        self.db.execute("UPDATE cash_shifts SET status='SUSPENDED' WHERE id=?", (self.shift_id,))
        self.db.commit()
        with self.assertRaises(CashInvalidStateError):
            CashSalesIntegrationService().require_open_shift(
                self.db, branch_id=self.branch, cashier_user_id=self.cashier)


if __name__ == "__main__": unittest.main()
