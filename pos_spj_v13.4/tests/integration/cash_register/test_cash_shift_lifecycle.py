from decimal import Decimal
import importlib
import sqlite3
import unittest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS
from backend.application.cash_register.shift_query_service import CashShiftQueryService
from backend.application.cash_register.shift_use_cases import (
    BeginCashShiftClosingUseCase, OpenCashShiftUseCase,
    ResumeCashShiftUseCase, SuspendCashShiftUseCase,
)
from backend.domain.cash_register.exceptions import (
    CashAuthorizationRequiredError, CashInvalidStateError, CashLimitExceededError,
)
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.shared.ids import new_uuid


class _Permissions:
    def has_permission(self, user_id, permission_code): return permission_code in ALL_CASH_PERMISSIONS
class _Scopes:
    def can_access_branch(self, *, user_id, branch_id): return True


class CashShiftLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(self.db)
        self.auth = CashAuthorizationPolicy(_Permissions(), _Scopes())
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
        self.limit = CashMonetaryLimitPolicy(
            approval_threshold=Decimal("1000"), hard_cap=Decimal("5000"))

    def tearDown(self): self.db.close()

    def _open(self, amount=Decimal("500")):
        return OpenCashShiftUseCase(self.auth, self.limit).execute(
            self.db, branch_id=self.branch, register_id=self.register,
            drawer_id=self.drawer, terminal_id=self.terminal,
            cashier_user_id=self.cashier, opening_amount=amount,
            actor_user_id=self.cashier, operation_id=new_uuid())

    def test_opening_assigns_devices_and_cashier_and_records_fund_atomically(self):
        result = self._open()
        row = self.db.execute("SELECT register_id,drawer_id,terminal_id,cashier_user_id,status FROM cash_shifts WHERE id=?", (result.entity_id,)).fetchone()
        self.assertEqual(row, (self.register, self.drawer, self.terminal, self.cashier, "OPEN"))
        movement = self.db.execute("SELECT movement_type,amount FROM cash_ledger_entries WHERE shift_id=?", (result.entity_id,)).fetchone()
        self.assertEqual(movement, ("OPENING_FLOAT", "500"))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cash_audit_log").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cash_outbox").fetchone()[0], 1)

    def test_blocked_device_and_unapproved_or_excessive_fund_are_rejected(self):
        self.db.execute("UPDATE cash_drawers SET status='BLOCKED' WHERE id=?", (self.drawer,))
        self.db.commit()
        with self.assertRaises(CashInvalidStateError): self._open()
        self.db.execute("UPDATE cash_drawers SET status='ACTIVE' WHERE id=?", (self.drawer,))
        self.db.commit()
        with self.assertRaises(CashAuthorizationRequiredError): self._open(Decimal("1000.01"))
        with self.assertRaises(CashLimitExceededError): self._open(Decimal("5000.01"))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cash_shifts").fetchone()[0], 0)

    def test_second_active_assignment_is_rejected_without_partial_writes(self):
        self._open()
        with self.assertRaisesRegex(CashInvalidStateError, "cajero ya tiene un turno activo"):
            self._open()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cash_shifts").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cash_ledger_entries").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cash_outbox").fetchone()[0], 1)

    def test_suspend_resume_and_preliminary_close_are_audited_state_transitions(self):
        shift = self._open()
        SuspendCashShiftUseCase(self.auth).execute(
            self.db, shift_id=shift.entity_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=new_uuid(), reason="Pausa")
        self.assertEqual(self.db.execute("SELECT status FROM cash_shifts WHERE id=?", (shift.entity_id,)).fetchone()[0], "SUSPENDED")
        ResumeCashShiftUseCase(self.auth).execute(
            self.db, shift_id=shift.entity_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=new_uuid())
        BeginCashShiftClosingUseCase(self.auth).execute(
            self.db, shift_id=shift.entity_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=new_uuid())
        row = self.db.execute("SELECT status,z_cut_id,closed_at FROM cash_shifts WHERE id=?", (shift.entity_id,)).fetchone()
        self.assertEqual(row, ("CLOSING", None, None))
        names = {r[0] for r in self.db.execute("SELECT event_name FROM cash_domain_events")}
        self.assertTrue({"CASH_SHIFT_OPENED", "CASH_SHIFT_SUSPENDED", "CASH_SHIFT_RESUMED", "CASH_SHIFT_CLOSING_STARTED"} <= names)

    def test_shift_query_service_lists_recent_shifts_for_ui_without_sql_in_frontend(self):
        shift = self._open()
        listing = CashShiftQueryService(self.db, self.auth).list_recent(
            branch_id=self.branch,
            requester_user_id=self.cashier,
        )
        self.assertEqual(listing.active_count, 1)
        self.assertEqual(len(listing.rows), 1)
        row = listing.rows[0]
        self.assertEqual(row.id, shift.entity_id)
        self.assertEqual(row.register_name, "Caja")
        self.assertEqual(row.drawer_name, "Cajón")
        self.assertEqual(row.terminal_name, "POS")
        self.assertEqual(row.status, "OPEN")
        self.assertEqual(row.opening_amount, Decimal("500"))
        self.assertEqual(row.expected_cash, Decimal("500"))


if __name__ == "__main__": unittest.main()
