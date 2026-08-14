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
        allocations = self.db.execute(
            """SELECT method_type,amount,affects_drawer,external_reference
            FROM payment_allocations ORDER BY created_at,method_type"""
        ).fetchall()
        self.assertEqual(len(allocations), 4)
        self.assertTrue(all(row[2] == 0 and row[3] for row in allocations))

    def test_commercial_instruments_require_validated_external_contract(self):
        for settlement_type in ("LOYALTY_POINTS", "COUPON", "VOUCHER", "STORE_CREDIT"):
            with self.assertRaises(CashInvalidStateError):
                self._complete([{"type": settlement_type, "amount": "25.00"}])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM payment_records").fetchone()[0], 0)
        self.assertEqual(self._balance(), Decimal("50"))

    def test_commercial_instrument_accepts_specific_validated_contract_fields(self):
        self._complete([
            {"type": "LOYALTY_POINTS", "amount": "10", "loyalty_contract_id": "LOY-OK"},
            {"type": "COUPON", "amount": "5", "coupon_id": "CUP-OK"},
            {"type": "VOUCHER", "amount": "7", "voucher_id": "VAL-OK"},
            {"type": "STORE_CREDIT", "amount": "9", "store_credit_id": "SALDO-OK"},
        ])
        references = {row[0] for row in self.db.execute(
            "SELECT external_reference FROM payment_allocations"
        ).fetchall()}
        self.assertEqual(references, {"LOY-OK", "CUP-OK", "VAL-OK", "SALDO-OK"})

    def test_mixed_cash_and_instruments_records_only_cash_component(self):
        self._complete([
            {"type": "CASH", "amount": "30.25"},
            {"type": "LOYALTY_POINTS", "amount": "10", "instrument_id": new_uuid()},
            {"type": "COUPON", "amount": "5", "instrument_id": new_uuid()},
            {"type": "VOUCHER", "amount": "20", "instrument_id": new_uuid()},
            {"type": "STORE_CREDIT", "amount": "15", "instrument_id": new_uuid()},
        ])
        self.assertEqual(self._balance(), Decimal("80.25"))

    def test_mixed_sale_persists_payment_record_allocations_and_only_cash_hits_drawer(self):
        loyalty_id = new_uuid()
        result = self._complete([
            {"type": "CASH", "amount": "400.00"},
            {"type": "BANK_CARD", "amount": "350.00", "terminal_reference": "T-123"},
            {"type": "BANK_TRANSFER", "amount": "150.00", "external_reference": "SPEI-9"},
            {"type": "LOYALTY_POINTS", "amount": "100.00", "instrument_id": loyalty_id},
        ])

        self.assertEqual(result.cash_amount, Decimal("400.00"))
        self.assertIsNotNone(result.payment_record_id)
        self.assertEqual(self._balance(), Decimal("450.00"))
        payment = self.db.execute(
            """SELECT sale_id,shift_id,branch_id,amount_to_settle,status
            FROM payment_records WHERE id=?""",
            (result.payment_record_id,),
        ).fetchone()
        self.assertEqual(
            payment,
            (self.db.execute(
                "SELECT reference_id FROM cash_ledger_entries WHERE id=?",
                (result.ledger_entry_id,),
            ).fetchone()[0], self.shift_id, self.branch, "1000.00", "CONFIRMED"),
        )
        allocations = self.db.execute(
            """SELECT method_type,amount,affects_drawer,external_reference
            FROM payment_allocations WHERE payment_record_id=?
            ORDER BY method_type,amount""",
            (result.payment_record_id,),
        ).fetchall()
        self.assertEqual(
            allocations,
            [
                ("BANK_CARD", "350.00", 0, "T-123"),
                ("BANK_TRANSFER", "150.00", 0, "SPEI-9"),
                ("CASH", "400.00", 1, None),
                ("LOYALTY_POINTS", "100.00", 0, loyalty_id),
            ],
        )

    def test_cash_change_reduces_settlement_and_physical_drawer_effect(self):
        event = create_domain_event(
            event_name=EventName.SALE_COMPLETED, operation_id=new_uuid(),
            entity_id=new_uuid(), branch_id=self.branch, user_id=self.cashier,
            source_module="sales",
            payload={"settlements": [{"type": "CASH", "amount": "120.00"}],
                     "change": "20.00"},
        )
        result = SaleCompletedCashHandler(self.db).handle(event)

        self.assertEqual(result.cash_amount, Decimal("100.00"))
        self.assertEqual(self._balance(), Decimal("150.00"))
        self.assertEqual(self.db.execute(
            "SELECT amount_to_settle FROM payment_records WHERE id=?",
            (result.payment_record_id,),
        ).fetchone()[0], "100.00")
        self.assertEqual(self.db.execute(
            "SELECT method_type,amount,affects_drawer FROM payment_allocations WHERE payment_record_id=?",
            (result.payment_record_id,),
        ).fetchone(), ("CASH", "100.00", 1))

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
                payment_lines=[{
                    "type": "LOYALTY_POINTS",
                    "amount": "10",
                    "instrument_id": new_uuid(),
                }])


if __name__ == "__main__": unittest.main()
