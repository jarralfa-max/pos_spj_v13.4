from decimal import Decimal
import importlib
import sqlite3
import unittest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.ledger_query_service import CashLedgerQueryService
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS
from backend.application.cash_register.sales_integration import CashSalesIntegrationService
from backend.application.cash_register.shift_use_cases import OpenCashShiftUseCase
from backend.application.event_handlers.cash_register.sales_cash_handlers import SaleCompletedCashHandler
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


class CashCommercialInstrumentTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(self.db)
        self.branch, self.cashier = new_uuid(), new_uuid()
        register, drawer, terminal = new_uuid(), new_uuid(), new_uuid()
        now = "2026-08-03T00:00:00+00:00"
        self.db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                        (register, self.branch, "Caja", "ACTIVE", None, now, now))
        self.db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                        (drawer, self.branch, register, "Cajón", "ACTIVE", now, now))
        self.db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                        (terminal, self.branch, register, "POS", "ACTIVE", now, now))
        self.db.commit()
        auth = CashAuthorizationPolicy(_Permissions(), _Scopes())
        limit = CashMonetaryLimitPolicy(
            approval_threshold=Decimal("1000"), hard_cap=Decimal("5000"))
        self.shift_id = OpenCashShiftUseCase(auth, limit).execute(
            self.db, branch_id=self.branch, register_id=register,
            drawer_id=drawer, terminal_id=terminal,
            cashier_user_id=self.cashier, opening_amount=Decimal("50"),
            actor_user_id=self.cashier, operation_id=new_uuid()).entity_id

    def tearDown(self): self.db.close()

    def _complete(self, settlements):
        event = create_domain_event(
            event_name=EventName.SALE_COMPLETED, operation_id=new_uuid(),
            entity_id=new_uuid(), branch_id=self.branch, user_id=self.cashier,
            source_module="sales", payload={"settlements": settlements})
        return SaleCompletedCashHandler(self.db).handle(event)

    def _balance(self):
        return CashLedgerQueryService(CashLedgerRepository(self.db)).projection(
            self.shift_id).balance

    def test_points_coupon_voucher_and_store_credit_never_enter_drawer(self):
        for settlement_type in ("LOYALTY_POINTS", "COUPON", "VOUCHER", "STORE_CREDIT"):
            result = self._complete([{
                "type": settlement_type, "amount": "25.00",
                "instrument_id": new_uuid(),
            }])
            self.assertIsNone(result.ledger_entry_id)
        self.assertEqual(self._balance(), Decimal("50"))
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM cash_ledger_entries WHERE movement_type='CASH_SALE'"
        ).fetchone()[0], 0)

    def test_mixed_cash_and_instruments_records_only_cash_component(self):
        self._complete([
            {"type": "CASH", "amount": "30.25"},
            {"type": "LOYALTY_POINTS", "amount": "10", "instrument_id": new_uuid()},
            {"type": "COUPON", "amount": "5", "instrument_id": new_uuid()},
            {"type": "VOUCHER", "amount": "20", "instrument_id": new_uuid()},
            {"type": "STORE_CREDIT", "amount": "15", "instrument_id": new_uuid()},
        ])
        self.assertEqual(self._balance(), Decimal("80.25"))

    def test_gift_card_is_reserved_and_cannot_silently_operate(self):
        with self.assertRaises(CashInvalidStateError):
            self._complete([{
                "type": "GIFT_CARD", "amount": "25", "instrument_id": new_uuid(),
            }])
        self.assertEqual(self._balance(), Decimal("50"))

    def test_non_cash_sale_still_requires_open_shift(self):
        self.db.execute("UPDATE cash_shifts SET status='SUSPENDED' WHERE id=?", (self.shift_id,))
        self.db.commit()
        with self.assertRaises(CashInvalidStateError):
            CashSalesIntegrationService().record_completed_sale(
                self.db, sale_id=new_uuid(), branch_id=self.branch,
                cashier_user_id=self.cashier, operation_id=new_uuid(),
                payment_lines={"LOYALTY_POINTS": "10"})


if __name__ == "__main__": unittest.main()
