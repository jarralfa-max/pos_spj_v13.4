from decimal import Decimal
import importlib
import sqlite3
import unittest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.movement_use_cases import (
    DeliverTreasuryHandoverUseCase, DisputeTreasuryHandoverUseCase,
    PrepareTreasuryHandoverUseCase, ReceiveTreasuryHandoverUseCase,
    RegisterSafeDropUseCase,
)
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS
from backend.application.cash_register.shift_use_cases import OpenCashShiftUseCase
from backend.domain.cash_register.exceptions import CashInvalidStateError
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.shared.ids import new_uuid


class _Permissions:
    def has_permission(self, user_id, permission_code): return permission_code in ALL_CASH_PERMISSIONS


class _Scopes:
    def can_access_branch(self, *, user_id, branch_id): return True


class CashValueHandoverFlowTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(self.db)
        importlib.import_module("migrations.standalone.176_cash_register_configuration_schema").run(self.db)
        self.auth = CashAuthorizationPolicy(_Permissions(), _Scopes())
        self.branch, self.cashier, self.treasurer = new_uuid(), new_uuid(), new_uuid()
        register, drawer, terminal = new_uuid(), new_uuid(), new_uuid()
        now = "2026-08-04T00:00:00+00:00"
        self.db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                        (register, self.branch, "Caja", "ACTIVE", None, now, now))
        self.db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                        (drawer, self.branch, register, "Cajón", "ACTIVE", now, now))
        self.db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                        (terminal, self.branch, register, "POS", "ACTIVE", now, now))
        self.db.execute("INSERT INTO cash_movement_reasons VALUES(?,?,?,?,?,?,?,?)",
                        (new_uuid(), "EXCESS", "Exceso", "SAFE_DROP", 0, 1, now, None))
        self.d100, self.d50 = new_uuid(), new_uuid()
        self.db.execute("INSERT INTO cash_denominations VALUES(?,?,?,?,?,?,?,?)",
                        (self.d100, "MXN", "100", "$100", 1, 1, now, None))
        self.db.execute("INSERT INTO cash_denominations VALUES(?,?,?,?,?,?,?,?)",
                        (self.d50, "MXN", "50", "$50", 2, 1, now, None))
        self.db.commit()
        limit = CashMonetaryLimitPolicy(
            approval_threshold=Decimal("1000"), hard_cap=Decimal("5000"))
        self.shift_id = OpenCashShiftUseCase(self.auth, limit).execute(
            self.db, branch_id=self.branch, register_id=register,
            drawer_id=drawer, terminal_id=terminal,
            cashier_user_id=self.cashier, opening_amount=Decimal("1000"),
            actor_user_id=self.cashier, operation_id=new_uuid()).entity_id
        self.drop_id = RegisterSafeDropUseCase(
            self.auth, limit, alert_threshold=Decimal("1000")).execute(
                self.db, shift_id=self.shift_id, branch_id=self.branch,
                amount=Decimal("250"), reason_code="EXCESS",
                actor_user_id=self.cashier, operation_id=new_uuid()).entity_id

    def tearDown(self): self.db.close()

    def _prepare(self, denominations=None):
        return PrepareTreasuryHandoverUseCase(self.auth).execute(
            self.db, safe_drop_entry_id=self.drop_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=new_uuid(),
            denominations=denominations or {self.d100: 2, self.d50: 1})

    def _deliver(self, handover_id, operation_id=None):
        return DeliverTreasuryHandoverUseCase(self.auth).execute(
            self.db, handover_id=handover_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=operation_id or new_uuid(),
            denominations={self.d100: 2, self.d50: 1})

    def test_preparation_persists_denominations_and_requires_exact_total(self):
        with self.assertRaises(CashInvalidStateError):
            self._prepare({self.d100: 2})
        prepared = self._prepare()
        rows = self.db.execute(
            "SELECT denomination,quantity,subtotal FROM cash_handover_denominations WHERE handover_id=? ORDER BY CAST(denomination AS NUMERIC) DESC",
            (prepared.entity_id,)).fetchall()
        self.assertEqual(rows, [("100", 2, "200"), ("50", 1, "50")])

    def test_double_confirmation_and_treasury_reception_are_idempotent(self):
        prepared = self._prepare()
        delivery_operation = new_uuid()
        self._deliver(prepared.entity_id, delivery_operation)
        delivery_retry = self._deliver(prepared.entity_id, delivery_operation)
        self.assertTrue(delivery_retry.idempotent)
        reception_operation = new_uuid()
        received = ReceiveTreasuryHandoverUseCase(self.auth).execute(
            self.db, handover_id=prepared.entity_id, branch_id=self.branch,
            actor_user_id=self.treasurer, operation_id=reception_operation,
            denominations={self.d100: 2, self.d50: 1})
        retry = ReceiveTreasuryHandoverUseCase(self.auth).execute(
            self.db, handover_id=prepared.entity_id, branch_id=self.branch,
            actor_user_id=self.treasurer, operation_id=reception_operation,
            denominations={self.d100: 2, self.d50: 1})
        self.assertEqual(received.status, "RECEIVED")
        self.assertTrue(retry.idempotent)
        confirmations = self.db.execute(
            "SELECT confirmation_type,confirmed_by,total_amount FROM cash_handover_confirmations WHERE handover_id=? ORDER BY confirmation_type",
            (prepared.entity_id,)).fetchall()
        self.assertEqual(confirmations, [
            ("DELIVERY", self.cashier, "250"), ("RECEPTION", self.treasurer, "250")])
        payload = self.db.execute(
            "SELECT payload_json FROM cash_domain_events WHERE event_name='CASH_HANDOVER_RECEIVED'"
        ).fetchone()[0]
        self.assertIn('"treasury_transfer_required":true', payload)

    def test_reception_difference_opens_dispute_and_blocks_treasury_transfer(self):
        prepared = self._prepare()
        self._deliver(prepared.entity_id)
        disputed = ReceiveTreasuryHandoverUseCase(self.auth).execute(
            self.db, handover_id=prepared.entity_id, branch_id=self.branch,
            actor_user_id=self.treasurer, operation_id=new_uuid(),
            denominations={self.d100: 1, self.d50: 2})
        self.assertEqual(disputed.status, "DISPUTED")
        row = self.db.execute(
            "SELECT status,disputed_by,dispute_reason FROM cash_handovers WHERE id=?",
            (prepared.entity_id,)).fetchone()
        self.assertEqual(row[0:2], ("DISPUTED", self.treasurer))
        self.assertTrue(row[2])
        payload = self.db.execute(
            "SELECT payload_json FROM cash_domain_events WHERE event_name='CASH_HANDOVER_DISPUTED'"
        ).fetchone()[0]
        self.assertIn('"treasury_transfer_required":false', payload)
        self.assertIn('"received_amount":"200"', payload)

    def test_manual_dispute_requires_reason_and_is_audited(self):
        prepared = self._prepare()
        self._deliver(prepared.entity_id)
        with self.assertRaises(CashInvalidStateError):
            DisputeTreasuryHandoverUseCase(self.auth).execute(
                self.db, handover_id=prepared.entity_id, branch_id=self.branch,
                actor_user_id=self.treasurer, operation_id=new_uuid(), reason="")
        result = DisputeTreasuryHandoverUseCase(self.auth).execute(
            self.db, handover_id=prepared.entity_id, branch_id=self.branch,
            actor_user_id=self.treasurer, operation_id=new_uuid(),
            reason="Sello del sobre alterado")
        self.assertEqual(result.status, "DISPUTED")
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM cash_audit_log WHERE action='CASH_HANDOVER_DISPUTED'"
        ).fetchone()[0], 1)


if __name__ == "__main__": unittest.main()
