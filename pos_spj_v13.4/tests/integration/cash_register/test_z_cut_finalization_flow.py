from decimal import Decimal
import importlib
import sqlite3
import unittest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.blind_count_use_cases import (
    CaptureBlindCountDenominationUseCase, ConfirmBlindCountUseCase, StartBlindCountUseCase,
)
from backend.application.cash_register.movement_use_cases import RegisterSafeDropUseCase
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS
from backend.application.cash_register.shift_use_cases import (
    BeginCashShiftClosingUseCase, OpenCashShiftUseCase,
)
from backend.application.cash_register.z_cut_query_service import CashZCutQueryService
from backend.application.cash_register.z_cut_use_cases import (
    GenerateZCutUseCase, NotifyZCutUseCase, PrintZCutUseCase,
)
from backend.domain.cash_register.exceptions import CashInvalidStateError
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.shared.ids import new_uuid


class _Permissions:
    def has_permission(self, user_id, permission_code): return permission_code in ALL_CASH_PERMISSIONS


class _LimitedPermissions:
    def __init__(self, grants):
        self._grants = set(grants)

    def has_permission(self, user_id, permission_code):
        return permission_code in self._grants


class _Scopes:
    def can_access_branch(self, *, user_id, branch_id): return True


class _Printer:
    def __init__(self): self.calls = []
    def print_document(self, document): self.calls.append(document)


class _Notifier:
    def __init__(self): self.calls = []
    def notify(self, document): self.calls.append(document)


class ZCutFinalizationFlowTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(self.db)
        importlib.import_module("migrations.standalone.176_cash_register_configuration_schema").run(self.db)
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
        self.d100 = new_uuid()
        self.db.execute("INSERT INTO cash_denominations VALUES(?,?,?,?,?,?,?,?)",
                        (self.d100, "MXN", "100", "$100", 1, 1, now, None))
        self.db.execute("INSERT INTO cash_movement_reasons VALUES(?,?,?,?,?,?,?,?)",
                        (new_uuid(), "EXCESS", "Exceso", "SAFE_DROP", 0, 1, now, None))
        self.db.execute(
            """INSERT INTO cash_difference_policies
            (id,tolerance_amount,critical_threshold,recurrence_window_days,
             recurrence_threshold,channels_json,scope_type,scope_id,active,effective_from,effective_to)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (new_uuid(), "10", "100", 30, 3, '["IN_APP","WHATSAPP"]',
             "BRANCH", self.branch, 1, now, None))
        self.db.commit()
        self.limit = CashMonetaryLimitPolicy(
            approval_threshold=Decimal("1000"), hard_cap=Decimal("5000"))
        self.shift_id = OpenCashShiftUseCase(self.auth, self.limit).execute(
            self.db, branch_id=self.branch, register_id=register,
            drawer_id=drawer, terminal_id=terminal,
            cashier_user_id=self.cashier, opening_amount=Decimal("500"),
            actor_user_id=self.cashier, operation_id=new_uuid()).entity_id

    def tearDown(self): self.db.close()

    def _confirmed_count(self, quantity=5):
        count = StartBlindCountUseCase(self.auth).execute(
            self.db, shift_id=self.shift_id, branch_id=self.branch,
            counter_user_id=self.cashier, operation_id=new_uuid())
        CaptureBlindCountDenominationUseCase(self.auth).execute(
            self.db, count_id=count.entity_id, branch_id=self.branch,
            denomination_id=self.d100, quantity=quantity,
            actor_user_id=self.cashier, operation_id=new_uuid())
        ConfirmBlindCountUseCase(self.auth).execute(
            self.db, count_id=count.entity_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=new_uuid())
        return count.entity_id

    def _begin_closing(self):
        BeginCashShiftClosingUseCase(self.auth).execute(
            self.db, shift_id=self.shift_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=new_uuid())

    def _generate(self, operation_id=None):
        return GenerateZCutUseCase(self.auth).execute(
            self.db, shift_id=self.shift_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=operation_id or new_uuid())

    def test_consolidates_expected_count_closure_publication_and_idempotency(self):
        count_id = self._confirmed_count(5)
        self._begin_closing()
        operation_id = new_uuid()
        result = self._generate(operation_id)
        retry = self._generate(operation_id)
        self.assertTrue(retry.idempotent)
        row = self.db.execute(
            "SELECT expected_cash,counted_cash,difference,is_final,blind_count_id,snapshot_json FROM cash_cuts WHERE id=?",
            (result.entity_id,)).fetchone()
        self.assertEqual(row[:5], ("500", "500", "0", 1, count_id))
        self.assertIn('"denominations_json"', row[5])
        shift = self.db.execute(
            "SELECT status,z_cut_id,closed_at FROM cash_shifts WHERE id=?", (self.shift_id,)).fetchone()
        self.assertEqual(shift[0:2], ("CLOSED", result.entity_id))
        self.assertIsNotNone(shift[2])
        self.assertIsNone(result.difference_id)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM cash_outbox WHERE operation_id=?", (operation_id,)).fetchone()[0], 1)

    def test_creates_difference_in_same_transaction(self):
        self._confirmed_count(4)
        self._begin_closing()
        result = self._generate()
        self.assertIsNotNone(result.difference_id)
        row = self.db.execute(
            "SELECT expected_amount,counted_amount,amount,status FROM cash_differences WHERE id=?",
            (result.difference_id,)).fetchone()
        self.assertEqual(row, ("500", "400", "-100", "DETECTED"))

    def test_rejects_missing_preliminary_close_count_and_pending_safe_drop(self):
        self._confirmed_count(5)
        with self.assertRaises(CashInvalidStateError): self._generate()
        self._begin_closing()
        # A safe drop without RECEIVED custody handover remains pending.
        self.db.execute("UPDATE cash_shifts SET status='OPEN' WHERE id=?", (self.shift_id,))
        self.db.commit()
        RegisterSafeDropUseCase(
            self.auth, self.limit, alert_threshold=Decimal("1000")).execute(
                self.db, shift_id=self.shift_id, branch_id=self.branch,
                amount=Decimal("100"), reason_code="EXCESS",
                actor_user_id=self.cashier, operation_id=new_uuid())
        self._begin_closing()
        with self.assertRaises(CashInvalidStateError): self._generate()

    def test_event_failure_rolls_back_cut_difference_and_shift_close(self):
        self._confirmed_count(4)
        self._begin_closing()
        self.db.execute("""CREATE TRIGGER reject_z_event BEFORE INSERT ON cash_domain_events
            WHEN NEW.event_name='CASH_Z_CUT_GENERATED' BEGIN SELECT RAISE(ABORT,'event failure'); END""")
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError): self._generate()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cash_cuts WHERE cut_type='Z'").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cash_differences").fetchone()[0], 0)
        self.assertEqual(self.db.execute(
            "SELECT status FROM cash_shifts WHERE id=?", (self.shift_id,)).fetchone()[0], "CLOSING")

    def test_print_and_notification_are_separate_idempotent_post_commit_effects(self):
        self._confirmed_count(5)
        self._begin_closing()
        cut = self._generate()
        printer, notifier = _Printer(), _Notifier()
        print_operation, notify_operation = new_uuid(), new_uuid()
        PrintZCutUseCase(self.auth, printer).execute(
            self.db, cut_id=cut.entity_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=print_operation)
        print_retry = PrintZCutUseCase(self.auth, printer).execute(
            self.db, cut_id=cut.entity_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=print_operation)
        NotifyZCutUseCase(self.auth, notifier).execute(
            self.db, cut_id=cut.entity_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=notify_operation)
        notify_retry = NotifyZCutUseCase(self.auth, notifier).execute(
            self.db, cut_id=cut.entity_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=notify_operation)
        self.assertTrue(print_retry.idempotent)
        self.assertTrue(notify_retry.idempotent)
        self.assertEqual(len(printer.calls), 1)
        self.assertEqual(len(notifier.calls), 1)
        self.assertTrue(printer.calls[0]["final"])
        names = {row[0] for row in self.db.execute(
            "SELECT event_name FROM cash_domain_events WHERE entity_id=?", (cut.entity_id,))}
        self.assertTrue({"CASH_Z_CUT_GENERATED", "CASH_Z_CUT_PRINTED",
                         "CASH_Z_CUT_NOTIFICATION_SENT"} <= names)

    def test_z_cut_projection_redacts_sensitive_amounts_without_permission(self):
        self._confirmed_count(5)
        self._begin_closing()
        cut = self._generate()
        view_only_auth = CashAuthorizationPolicy(
            _LimitedPermissions({"CAJA.corte_z.ver"}),
            _Scopes(),
        )
        hidden = CashZCutQueryService(self.db, view_only_auth).get(
            cut_id=cut.entity_id,
            branch_id=self.branch,
            requester_user_id=self.cashier,
        )
        self.assertIsNone(hidden.expected_cash)
        self.assertIsNone(hidden.counted_cash)
        self.assertIsNone(hidden.difference)
        self.assertIsNone(hidden.snapshot)
        self.assertFalse(hidden.sensitive_amounts_visible)

        sensitive_auth = CashAuthorizationPolicy(
            _LimitedPermissions({"CAJA.corte_z.ver", "CAJA.ver.importes_sensibles"}),
            _Scopes(),
        )
        visible = CashZCutQueryService(self.db, sensitive_auth).get(
            cut_id=cut.entity_id,
            branch_id=self.branch,
            requester_user_id=self.cashier,
        )
        self.assertEqual(visible.expected_cash, Decimal("500"))
        self.assertEqual(visible.counted_cash, Decimal("500"))
        self.assertEqual(visible.difference, Decimal("0"))
        self.assertIn("denominations_json", visible.snapshot)


if __name__ == "__main__": unittest.main()
