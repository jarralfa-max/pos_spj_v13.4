from decimal import Decimal
import importlib
import sqlite3
import unittest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.movement_use_cases import (
    DeliverTreasuryHandoverUseCase, PrepareTreasuryHandoverUseCase,
    ReceiveTreasuryHandoverUseCase, RegisterSafeDropUseCase,
)
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS
from backend.application.cash_register.shift_use_cases import OpenCashShiftUseCase
from backend.domain.cash_register.exceptions import (
    CashAuthorizationRequiredError, CashInvalidStateError,
    CashSegregationOfDutiesError,
)
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.shared.ids import new_uuid


class _Permissions:
    def has_permission(self, user_id, permission_code): return permission_code in ALL_CASH_PERMISSIONS


class _Scopes:
    def can_access_branch(self, *, user_id, branch_id): return True


class CashSafeDropHandoverTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(self.db)
        importlib.import_module("migrations.standalone.176_cash_register_configuration_schema").run(self.db)
        self.auth = CashAuthorizationPolicy(_Permissions(), _Scopes())
        self.limit = CashMonetaryLimitPolicy(
            approval_threshold=Decimal("500"), hard_cap=Decimal("2000"))
        self.branch, self.cashier, self.supervisor, self.treasurer = (
            new_uuid(), new_uuid(), new_uuid(), new_uuid())
        register, drawer, terminal = new_uuid(), new_uuid(), new_uuid()
        now = "2026-08-03T00:00:00+00:00"
        self.db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                        (register, self.branch, "Caja", "ACTIVE", None, now, now))
        self.db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                        (drawer, self.branch, register, "Cajón", "ACTIVE", now, now))
        self.db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                        (terminal, self.branch, register, "POS", "ACTIVE", now, now))
        self.db.execute(
            "INSERT INTO cash_movement_reasons VALUES(?,?,?,?,?,?,?,?)",
            (new_uuid(), "EXCESS_CASH", "Exceso de efectivo", "SAFE_DROP", 0, 1, now, None))
        self.db.execute(
            "INSERT INTO cash_movement_reasons VALUES(?,?,?,?,?,?,?,?)",
            (new_uuid(), "SECURITY", "Retiro por seguridad", "SAFE_DROP", 1, 1, now, None))
        self.d50 = new_uuid()
        self.db.execute("INSERT INTO cash_denominations VALUES(?,?,?,?,?,?,?,?)",
                        (self.d50, "MXN", "50", "$50", 1, 1, now, None))
        self.db.commit()
        opening_limit = CashMonetaryLimitPolicy(
            approval_threshold=Decimal("1000"), hard_cap=Decimal("5000"))
        self.shift_id = OpenCashShiftUseCase(self.auth, opening_limit).execute(
            self.db, branch_id=self.branch, register_id=register,
            drawer_id=drawer, terminal_id=terminal,
            cashier_user_id=self.cashier, opening_amount=Decimal("1000"),
            actor_user_id=self.cashier, operation_id=new_uuid()).entity_id
        self.safe_drop = RegisterSafeDropUseCase(
            self.auth, self.limit, alert_threshold=Decimal("300"))

    def tearDown(self): self.db.close()

    def _drop(self, amount=Decimal("200"), **overrides):
        params = dict(
            shift_id=self.shift_id, branch_id=self.branch, amount=amount,
            reason_code="EXCESS_CASH", actor_user_id=self.cashier,
            operation_id=new_uuid())
        params.update(overrides)
        return self.safe_drop.execute(self.db, **params)

    def _denoms(self, amount): return {self.d50: int(Decimal(amount) / Decimal("50"))}

    def test_catalog_safe_drop_and_alert_are_atomic_and_idempotent(self):
        operation_id = new_uuid()
        first = self._drop(Decimal("350"), operation_id=operation_id)
        second = self._drop(Decimal("350"), operation_id=operation_id)
        self.assertTrue(first.alert_required)
        self.assertTrue(second.idempotent)
        row = self.db.execute(
            "SELECT movement_type,direction,amount,concept FROM cash_ledger_entries WHERE id=?",
            (first.entity_id,)).fetchone()
        self.assertEqual(row, ("SAFE_DROP", "OUTFLOW", "350", "Exceso de efectivo"))
        event = self.db.execute(
            "SELECT event_name,payload_json FROM cash_domain_events WHERE operation_id=?",
            (operation_id,)).fetchone()
        self.assertEqual(event[0], "CASH_SAFE_DROP_RECORDED")
        self.assertIn('"alert_required":true', event[1])
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM cash_outbox WHERE operation_id=?", (operation_id,)).fetchone()[0], 1)

    def test_catalog_authorization_limits_and_available_cash_are_enforced(self):
        with self.assertRaises(CashInvalidStateError):
            self._drop(reason_code="UNKNOWN")
        with self.assertRaises(CashAuthorizationRequiredError):
            self._drop(Decimal("100"), reason_code="SECURITY")
        with self.assertRaises(CashSegregationOfDutiesError):
            self._drop(Decimal("100"), reason_code="SECURITY", authorized_by=self.cashier)
        self._drop(Decimal("600"), authorized_by=self.supervisor)
        with self.assertRaises(CashInvalidStateError):
            self._drop(Decimal("401"))

    def test_safe_drop_handover_to_treasury_preserves_custody_and_emits_event(self):
        drop = self._drop(Decimal("250"))
        prepared = PrepareTreasuryHandoverUseCase(self.auth).execute(
            self.db, safe_drop_entry_id=drop.entity_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=new_uuid(),
            denominations=self._denoms(250))
        DeliverTreasuryHandoverUseCase(self.auth).execute(
            self.db, handover_id=prepared.entity_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=new_uuid(),
            denominations=self._denoms(250))
        with self.assertRaises(CashSegregationOfDutiesError):
            ReceiveTreasuryHandoverUseCase(self.auth).execute(
                self.db, handover_id=prepared.entity_id, branch_id=self.branch,
                actor_user_id=self.cashier, operation_id=new_uuid(),
                denominations=self._denoms(250))
        received = ReceiveTreasuryHandoverUseCase(self.auth).execute(
            self.db, handover_id=prepared.entity_id, branch_id=self.branch,
            actor_user_id=self.treasurer, operation_id=new_uuid(),
            denominations=self._denoms(250))
        self.assertEqual(received.status, "RECEIVED")
        row = self.db.execute(
            "SELECT amount,source_entry_id,delivered_by,received_by,status FROM cash_handovers WHERE id=?",
            (prepared.entity_id,)).fetchone()
        self.assertEqual(row, ("250", drop.entity_id, self.cashier, self.treasurer, "RECEIVED"))
        payload = self.db.execute(
            "SELECT payload_json FROM cash_domain_events WHERE event_name='CASH_HANDOVER_RECEIVED'"
        ).fetchone()[0]
        self.assertIn('"treasury_transfer_required":true', payload)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM cash_ledger_entries WHERE movement_type='HANDOVER'"
        ).fetchone()[0], 0, "custody transfer must not subtract cash twice")

    def test_one_safe_drop_cannot_prepare_two_handovers(self):
        drop = self._drop()
        PrepareTreasuryHandoverUseCase(self.auth).execute(
            self.db, safe_drop_entry_id=drop.entity_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=new_uuid(),
            denominations=self._denoms(200))
        with self.assertRaises(sqlite3.IntegrityError):
            PrepareTreasuryHandoverUseCase(self.auth).execute(
                self.db, safe_drop_entry_id=drop.entity_id, branch_id=self.branch,
                actor_user_id=self.cashier, operation_id=new_uuid(),
                denominations=self._denoms(200))


if __name__ == "__main__": unittest.main()
