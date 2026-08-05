from decimal import Decimal
import importlib
import sqlite3
import unittest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.blind_count_query_service import BlindCountQueryService
from backend.application.cash_register.blind_count_use_cases import (
    CaptureBlindCountDenominationUseCase, ConfirmBlindCountUseCase,
    StartBlindCountUseCase,
)
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS, CashPermissions
from backend.application.cash_register.shift_use_cases import OpenCashShiftUseCase
from backend.domain.cash_register.exceptions import CashInvalidStateError, CashPermissionDeniedError
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.shared.ids import new_uuid


class _Permissions:
    def __init__(self, denied=()): self.denied = set(denied)
    def has_permission(self, user_id, permission_code):
        return permission_code in ALL_CASH_PERMISSIONS and permission_code not in self.denied


class _Scopes:
    def can_access_branch(self, *, user_id, branch_id): return True


class BlindCashCountFlowTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module("migrations.standalone.176_cash_register_configuration_schema").run(self.db)
        importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(self.db)
        self.auth = CashAuthorizationPolicy(_Permissions(), _Scopes())
        self.branch, self.cashier = new_uuid(), new_uuid()
        register, drawer, terminal = new_uuid(), new_uuid(), new_uuid()
        now = "2026-08-03T00:00:00+00:00"
        self.db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                        (register, self.branch, "Caja", "ACTIVE", None, now, now))
        self.db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                        (drawer, self.branch, register, "Cajón", "ACTIVE", now, now))
        self.db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                        (terminal, self.branch, register, "POS", "ACTIVE", now, now))
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
            cashier_user_id=self.cashier, opening_amount=Decimal("500"),
            actor_user_id=self.cashier, operation_id=new_uuid()).entity_id
        self.count_id = StartBlindCountUseCase(self.auth).execute(
            self.db, shift_id=self.shift_id, branch_id=self.branch,
            counter_user_id=self.cashier, operation_id=new_uuid()).entity_id

    def tearDown(self): self.db.close()

    def _capture(self, denomination_id, quantity, operation_id=None):
        return CaptureBlindCountDenominationUseCase(self.auth).execute(
            self.db, count_id=self.count_id, branch_id=self.branch,
            denomination_id=denomination_id, quantity=quantity,
            actor_user_id=self.cashier, operation_id=operation_id or new_uuid())

    def test_session_hides_expected_and_uses_catalog_denominations(self):
        dto = BlindCountQueryService(self.db, self.auth).get(
            count_id=self.count_id, branch_id=self.branch,
            requester_user_id=self.cashier)
        self.assertIsNone(dto.expected_cash)
        self.assertIsNone(dto.difference)
        self.assertEqual([line.denomination_id for line in dto.lines], [self.d100, self.d50])
        self.assertNotIn("expected", self.db.execute(
            "SELECT payload_json FROM cash_domain_events WHERE event_name='CASH_BLIND_COUNT_STARTED'"
        ).fetchone()[0].replace("expected_cash_hidden", ""))

    def test_capture_recalculates_with_decimal_and_is_idempotent(self):
        operation_id = new_uuid()
        first = self._capture(self.d100, 3, operation_id)
        second = self._capture(self.d100, 3, operation_id)
        self._capture(self.d50, 4)
        self.assertEqual(first.total_counted, Decimal("300"))
        self.assertTrue(second.idempotent)
        row = self.db.execute(
            "SELECT total_counted FROM cash_counts WHERE id=?", (self.count_id,)).fetchone()
        self.assertEqual(row[0], "500")
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM cash_count_denominations WHERE count_id=?", (self.count_id,)
        ).fetchone()[0], 2)

    def test_confirm_locks_capture_then_authorized_reveal_calculates_difference(self):
        self._capture(self.d100, 4)
        self._capture(self.d50, 1)
        operation_id = new_uuid()
        first = ConfirmBlindCountUseCase(self.auth).execute(
            self.db, count_id=self.count_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=operation_id)
        retry = ConfirmBlindCountUseCase(self.auth).execute(
            self.db, count_id=self.count_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=operation_id)
        self.assertEqual(first.status, "CONFIRMED")
        self.assertTrue(retry.idempotent)
        with self.assertRaises(CashInvalidStateError): self._capture(self.d50, 2)
        hidden = BlindCountQueryService(self.db, self.auth).get(
            count_id=self.count_id, branch_id=self.branch,
            requester_user_id=self.cashier)
        self.assertTrue(hidden.locked)
        self.assertIsNone(hidden.expected_cash)
        revealed = BlindCountQueryService(self.db, self.auth).get(
            count_id=self.count_id, branch_id=self.branch,
            requester_user_id=self.cashier, reveal_expected=True)
        self.assertEqual(revealed.expected_cash, Decimal("500"))
        self.assertEqual(revealed.difference, Decimal("-50"))

    def test_expected_cannot_be_revealed_early_or_without_permission(self):
        query = BlindCountQueryService(self.db, self.auth)
        with self.assertRaises(CashInvalidStateError):
            query.get(count_id=self.count_id, branch_id=self.branch,
                      requester_user_id=self.cashier, reveal_expected=True)
        self._capture(self.d100, 5)
        ConfirmBlindCountUseCase(self.auth).execute(
            self.db, count_id=self.count_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=new_uuid())
        denied = CashAuthorizationPolicy(
            _Permissions({CashPermissions.BLIND_COUNT_REVEAL_EXPECTED}), _Scopes())
        with self.assertRaises(CashPermissionDeniedError):
            BlindCountQueryService(self.db, denied).get(
                count_id=self.count_id, branch_id=self.branch,
                requester_user_id=self.cashier, reveal_expected=True)

    def test_only_one_open_session_per_shift(self):
        with self.assertRaises(CashInvalidStateError):
            StartBlindCountUseCase(self.auth).execute(
                self.db, shift_id=self.shift_id, branch_id=self.branch,
                counter_user_id=self.cashier, operation_id=new_uuid())


if __name__ == "__main__": unittest.main()
