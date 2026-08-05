from decimal import Decimal
import importlib
import sqlite3
import unittest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.blind_count_use_cases import (
    CaptureBlindCountDenominationUseCase, ConfirmBlindCountUseCase, StartBlindCountUseCase,
)
from backend.application.cash_register.difference_query_service import CashDifferenceQueryService
from backend.application.cash_register.difference_use_cases import (
    ExplainCashDifferenceUseCase, ResolveCashDifferenceUseCase,
    ReviewCashDifferenceUseCase,
)
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS
from backend.application.cash_register.shift_use_cases import (
    BeginCashShiftClosingUseCase, OpenCashShiftUseCase,
)
from backend.application.cash_register.z_cut_use_cases import GenerateZCutUseCase
from backend.domain.cash_register.exceptions import CashSegregationOfDutiesError
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.shared.ids import new_uuid


class _Permissions:
    def has_permission(self, user_id, permission_code): return permission_code in ALL_CASH_PERMISSIONS


class _Scopes:
    def can_access_branch(self, *, user_id, branch_id): return True


class CashDifferenceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(self.db)
        importlib.import_module("migrations.standalone.176_cash_register_configuration_schema").run(self.db)
        self.auth = CashAuthorizationPolicy(_Permissions(), _Scopes())
        self.branch, self.cashier = new_uuid(), new_uuid()
        self.supervisor, self.reviewer, self.resolver = new_uuid(), new_uuid(), new_uuid()
        register, drawer, terminal = new_uuid(), new_uuid(), new_uuid()
        now = "2026-08-03T00:00:00+00:00"
        self.db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                        (register, self.branch, "Caja", "ACTIVE", None, now, now))
        self.db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                        (drawer, self.branch, register, "Cajón", "ACTIVE", now, now))
        self.db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                        (terminal, self.branch, register, "POS", "ACTIVE", now, now))
        denomination_id = new_uuid()
        self.db.execute("INSERT INTO cash_denominations VALUES(?,?,?,?,?,?,?,?)",
                        (denomination_id, "MXN", "100", "$100", 1, 1, now, None))
        self.db.execute(
            """INSERT INTO cash_difference_policies
            (id,tolerance_amount,critical_threshold,recurrence_window_days,
             recurrence_threshold,channels_json,scope_type,scope_id,active,effective_from,effective_to)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (new_uuid(), "10", "100", 30, 3, '["IN_APP","WHATSAPP"]',
             "BRANCH", self.branch, 1, now, None))
        self.db.commit()
        limit = CashMonetaryLimitPolicy(
            approval_threshold=Decimal("1000"), hard_cap=Decimal("5000"))
        shift_id = OpenCashShiftUseCase(self.auth, limit).execute(
            self.db, branch_id=self.branch, register_id=register,
            drawer_id=drawer, terminal_id=terminal,
            cashier_user_id=self.cashier, opening_amount=Decimal("500"),
            actor_user_id=self.cashier, operation_id=new_uuid()).entity_id
        count_id = StartBlindCountUseCase(self.auth).execute(
            self.db, shift_id=shift_id, branch_id=self.branch,
            counter_user_id=self.cashier, operation_id=new_uuid()).entity_id
        CaptureBlindCountDenominationUseCase(self.auth).execute(
            self.db, count_id=count_id, branch_id=self.branch,
            denomination_id=denomination_id, quantity=4,
            actor_user_id=self.cashier, operation_id=new_uuid())
        ConfirmBlindCountUseCase(self.auth).execute(
            self.db, count_id=count_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=new_uuid())
        BeginCashShiftClosingUseCase(self.auth).execute(
            self.db, shift_id=shift_id, branch_id=self.branch,
            actor_user_id=self.supervisor, operation_id=new_uuid())
        self.difference_id = GenerateZCutUseCase(self.auth).execute(
            self.db, shift_id=shift_id, branch_id=self.branch,
            actor_user_id=self.supervisor, operation_id=new_uuid()).difference_id

    def tearDown(self): self.db.close()

    def test_detection_classification_tolerance_recurrence_alert_and_whatsapp(self):
        dto = CashDifferenceQueryService(self.db, self.auth).get(
            difference_id=self.difference_id, branch_id=self.branch,
            requester_user_id=self.supervisor)
        self.assertEqual(dto.classification, "SHORTAGE")
        self.assertEqual(dto.severity, "CRITICAL")
        self.assertEqual(dto.amount, Decimal("-100"))
        self.assertEqual(dto.tolerance_amount, Decimal("10"))
        self.assertEqual(dto.recurrence_count, 1)
        payload = self.db.execute(
            "SELECT payload_json FROM cash_domain_events WHERE event_name='CASH_DIFFERENCE_DETECTED'"
        ).fetchone()[0]
        self.assertIn('"whatsapp_required":true', payload)
        self.assertIn('"WHATSAPP"', payload)

    def test_explain_review_resolve_are_segregated_audited_and_idempotent(self):
        explain_operation = new_uuid()
        ExplainCashDifferenceUseCase(self.auth).execute(
            self.db, difference_id=self.difference_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=explain_operation,
            explanation="Error al entregar cambio")
        explain_retry = ExplainCashDifferenceUseCase(self.auth).execute(
            self.db, difference_id=self.difference_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=explain_operation,
            explanation="Error al entregar cambio")
        self.assertTrue(explain_retry.idempotent)
        with self.assertRaises(CashSegregationOfDutiesError):
            ReviewCashDifferenceUseCase(self.auth).execute(
                self.db, difference_id=self.difference_id, branch_id=self.branch,
                actor_user_id=self.cashier, operation_id=new_uuid())
        ReviewCashDifferenceUseCase(self.auth).execute(
            self.db, difference_id=self.difference_id, branch_id=self.branch,
            actor_user_id=self.reviewer, operation_id=new_uuid())
        with self.assertRaises(CashSegregationOfDutiesError):
            ResolveCashDifferenceUseCase(self.auth).execute(
                self.db, difference_id=self.difference_id, branch_id=self.branch,
                actor_user_id=self.reviewer, operation_id=new_uuid(), resolution="No")
        ResolveCashDifferenceUseCase(self.auth).execute(
            self.db, difference_id=self.difference_id, branch_id=self.branch,
            actor_user_id=self.resolver, operation_id=new_uuid(),
            resolution="Capacitación y reposición documentada")
        row = self.db.execute(
            "SELECT status,explained_by,reviewed_by,resolved_by FROM cash_differences WHERE id=?",
            (self.difference_id,)).fetchone()
        self.assertEqual(row, ("RESOLVED", self.cashier, self.reviewer, self.resolver))
        names = {item[0] for item in self.db.execute(
            "SELECT event_name FROM cash_domain_events WHERE entity_id=?", (self.difference_id,))}
        self.assertTrue({"CASH_DIFFERENCE_DETECTED", "CASH_DIFFERENCE_EXPLAINED",
                         "CASH_DIFFERENCE_REVIEWED", "CASH_DIFFERENCE_RESOLVED"} <= names)


if __name__ == "__main__": unittest.main()
