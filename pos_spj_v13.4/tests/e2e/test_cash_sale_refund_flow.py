from decimal import Decimal
import importlib
import sqlite3
import unittest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.ledger_query_service import CashLedgerQueryService
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS
from backend.application.cash_register.refund_integration import CashRefundIntegrationService
from backend.application.cash_register.sales_integration import CashSalesIntegrationService
from backend.application.cash_register.shift_use_cases import OpenCashShiftUseCase
from backend.application.event_handlers.cash_register.sales_cash_handlers import SaleRefundedCashHandler
from backend.domain.cash_register.exceptions import (
    CashInvalidStateError, CashSegregationOfDutiesError,
)
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.infrastructure.db.repositories.cash_register.repositories import CashLedgerRepository
from backend.shared.events.event_contracts import create_domain_event
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


class _Permissions:
    def has_permission(self, user_id, permission_code): return permission_code in ALL_CASH_PERMISSIONS


class _Scopes:
    def can_access_branch(self, *, user_id, branch_id): return True


class CashSaleRefundFlowTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(self.db)
        self.auth = CashAuthorizationPolicy(_Permissions(), _Scopes())
        self.limit = CashMonetaryLimitPolicy(
            approval_threshold=Decimal("1000"), hard_cap=Decimal("5000"))
        self.branch, self.cashier, self.authorizer = new_uuid(), new_uuid(), new_uuid()
        register, drawer, terminal = new_uuid(), new_uuid(), new_uuid()
        now = "2026-08-04T00:00:00+00:00"
        self.db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                        (register, self.branch, "Caja", "ACTIVE", None, now, now))
        self.db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                        (drawer, self.branch, register, "Cajón", "ACTIVE", now, now))
        self.db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                        (terminal, self.branch, register, "POS", "ACTIVE", now, now))
        self.db.commit()
        self.shift_id = OpenCashShiftUseCase(self.auth, self.limit).execute(
            self.db, branch_id=self.branch, register_id=register,
            drawer_id=drawer, terminal_id=terminal,
            cashier_user_id=self.cashier, opening_amount=Decimal("50"),
            actor_user_id=self.cashier, operation_id=new_uuid()).entity_id
        self.sale_id = new_uuid()
        CashSalesIntegrationService().record_completed_sale(
            self.db, sale_id=self.sale_id, branch_id=self.branch,
            cashier_user_id=self.cashier, operation_id=new_uuid(),
            payment_lines={"CASH": "100", "CARD": "100"})
        self.service = CashRefundIntegrationService(self.auth, self.limit)

    def tearDown(self): self.db.close()

    def _event(self, *, refund_id=None, operation_id=None,
               original=None, refunded=None, authorized_by=None):
        return create_domain_event(
            event_name=EventName.SALE_REFUNDED,
            operation_id=operation_id or new_uuid(), entity_id=self.sale_id,
            branch_id=self.branch, user_id=self.cashier, source_module="sales",
            payload={
                "refund_id": refund_id or new_uuid(),
                "authorized_by": authorized_by or self.authorizer,
                "reason": "Devolución parcial",
                "original_settlements": original or {"CASH": "100", "CARD": "100"},
                "refund_settlements": refunded or {"CASH": "40", "CARD": "10"},
            })

    def _handle(self, event):
        return SaleRefundedCashHandler(self.db, self.service).handle(event)

    def _balance(self):
        return CashLedgerQueryService(CashLedgerRepository(self.db)).projection(
            self.shift_id).balance

    def test_mixed_refund_uses_original_method_and_only_cash_leaves_drawer(self):
        refund_id = new_uuid()
        result = self._handle(self._event(refund_id=refund_id))
        self.assertEqual(result.cash_amount, Decimal("40"))
        row = self.db.execute(
            """SELECT movement_type,direction,amount,reference_id,related_sale_id
            FROM cash_ledger_entries WHERE id=?""", (result.ledger_entry_id,)).fetchone()
        self.assertEqual(row, ("CASH_REFUND", "OUTFLOW", "40", refund_id, self.sale_id))
        execution = self.db.execute(
            """SELECT refund_id,sale_id,method,amount,ledger_entry_id
            FROM cash_refund_executions WHERE refund_id=?""",
            (refund_id,),
        ).fetchone()
        self.assertEqual(execution, (refund_id, self.sale_id, "CASH", "40", result.ledger_entry_id))
        self.assertEqual(self._balance(), Decimal("110"))

    def test_refund_event_retry_is_idempotent(self):
        event = self._event()
        first, retry = self._handle(event), self._handle(event)
        self.assertEqual(first.ledger_entry_id, retry.ledger_entry_id)
        self.assertTrue(retry.idempotent)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM cash_ledger_entries WHERE movement_type='CASH_REFUND'"
        ).fetchone()[0], 1)

    def test_authorization_original_method_and_cumulative_cash_are_enforced(self):
        with self.assertRaises(CashSegregationOfDutiesError):
            self._handle(self._event(authorized_by=self.cashier))
        with self.assertRaises(CashInvalidStateError):
            self._handle(self._event(refunded={"CASH": "101"}))
        self._handle(self._event(refunded={"CASH": "60"}))
        with self.assertRaises(CashInvalidStateError):
            self._handle(self._event(refunded={"CASH": "50"}))

    def test_non_cash_refund_has_no_drawer_entry_and_signals_loyalty_finance(self):
        loyalty_contract = new_uuid()
        event = self._event(
            original=[
                {"type": "LOYALTY_POINTS", "amount": "30", "instrument_id": loyalty_contract},
                {"type": "CARD", "amount": "70"},
            ],
            refunded=[
                {"type": "LOYALTY_POINTS", "amount": "20", "instrument_id": loyalty_contract},
                {"type": "CARD", "amount": "10"},
            ])
        result = self._handle(event)
        self.assertIsNone(result.ledger_entry_id)
        self.assertEqual(self._balance(), Decimal("150"))
        execution = self.db.execute(
            "SELECT method,amount,ledger_entry_id FROM cash_refund_executions WHERE refund_id=?",
            (event.payload["refund_id"],),
        ).fetchone()
        self.assertEqual(execution, ("ORIGINAL_PAYMENT_METHOD", "30", None))
        payload = self.db.execute(
            "SELECT payload_json FROM cash_domain_events WHERE operation_id=?",
            (event.operation_id,)).fetchone()[0]
        self.assertIn('"finance_event":"SALE_REFUNDED"', payload)
        self.assertIn('"loyalty_reversal_required":true', payload)

    def test_commercial_refund_requires_validated_external_contract(self):
        with self.assertRaises(CashInvalidStateError):
            self._handle(self._event(
                original={"LOYALTY_POINTS": "30"},
                refunded={"LOYALTY_POINTS": "10"},
            ))
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM cash_refund_executions"
        ).fetchone()[0], 0)


if __name__ == "__main__": unittest.main()
