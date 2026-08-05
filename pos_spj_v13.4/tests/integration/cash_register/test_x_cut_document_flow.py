from decimal import Decimal
import importlib
import sqlite3
import unittest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.ledger_use_cases import RegisterCashMovementUseCase
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS, CashPermissions
from backend.application.cash_register.shift_use_cases import OpenCashShiftUseCase
from backend.application.cash_register.x_cut_query_service import XCutQueryService
from backend.application.cash_register.x_cut_use_cases import GenerateXCutUseCase, PrintXCutUseCase
from backend.domain.cash_register.enums import CashMovementType
from backend.domain.cash_register.exceptions import CashPermissionDeniedError
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.shared.ids import new_uuid


class _Permissions:
    def __init__(self, denied=()): self.denied = set(denied)
    def has_permission(self, user_id, permission_code):
        return permission_code in ALL_CASH_PERMISSIONS and permission_code not in self.denied


class _Scopes:
    def can_access_branch(self, *, user_id, branch_id): return True


class _Printer:
    def __init__(self, fail=False): self.documents, self.fail = [], fail
    def print_document(self, document):
        if self.fail: raise RuntimeError("printer offline")
        self.documents.append(document)


class XCutDocumentFlowTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
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
        self.db.commit()
        self.limit = CashMonetaryLimitPolicy(
            approval_threshold=Decimal("1000"), hard_cap=Decimal("5000"))
        self.shift_id = OpenCashShiftUseCase(self.auth, self.limit).execute(
            self.db, branch_id=self.branch, register_id=register,
            drawer_id=drawer, terminal_id=terminal,
            cashier_user_id=self.cashier, opening_amount=Decimal("500"),
            actor_user_id=self.cashier, operation_id=new_uuid()).entity_id
        movements = RegisterCashMovementUseCase(self.auth, self.limit)
        movements.execute(
            self.db, shift_id=self.shift_id, branch_id=self.branch,
            movement_type=CashMovementType.MANUAL_INCOME, amount=Decimal("100.25"),
            concept="Cambio adicional", actor_user_id=self.cashier,
            operation_id=new_uuid())
        movements.execute(
            self.db, shift_id=self.shift_id, branch_id=self.branch,
            movement_type=CashMovementType.MANUAL_WITHDRAWAL, amount=Decimal("25.10"),
            concept="Gasto autorizado", actor_user_id=self.cashier,
            operation_id=new_uuid())

    def tearDown(self): self.db.close()

    def _generate(self, operation_id=None):
        return GenerateXCutUseCase(self.auth).execute(
            self.db, shift_id=self.shift_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=operation_id or new_uuid())

    def test_document_is_immutable_snapshot_and_does_not_close_shift(self):
        operation_id = new_uuid()
        first = self._generate(operation_id)
        retry = self._generate(operation_id)
        self.assertTrue(retry.idempotent)
        row = self.db.execute(
            "SELECT cut_type,document_number,expected_cash,is_final,snapshot_json FROM cash_cuts WHERE id=?",
            (first.entity_id,)).fetchone()
        self.assertEqual(row[:4], ("X", first.document_number, "575.15", 0))
        self.assertIn('"movement_count":"3"', row[4])
        self.assertEqual(self.db.execute(
            "SELECT status FROM cash_shifts WHERE id=?", (self.shift_id,)).fetchone()[0], "OPEN")
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM cash_audit_log WHERE action='CASH_X_CUT_GENERATED'"
        ).fetchone()[0], 1)

    def test_visibility_redacts_sensitive_amounts_separately_from_view(self):
        cut = self._generate()
        visible = XCutQueryService(self.db, self.auth).get(
            cut_id=cut.entity_id, branch_id=self.branch,
            requester_user_id=self.cashier)
        self.assertEqual(visible.expected_cash, Decimal("575.15"))
        denied_sensitive = CashAuthorizationPolicy(
            _Permissions({CashPermissions.VIEW_SENSITIVE_AMOUNTS}), _Scopes())
        redacted = XCutQueryService(self.db, denied_sensitive).get(
            cut_id=cut.entity_id, branch_id=self.branch,
            requester_user_id=self.cashier)
        self.assertIsNone(redacted.expected_cash)
        self.assertIsNone(redacted.snapshot)
        denied_view = CashAuthorizationPolicy(
            _Permissions({CashPermissions.X_CUT_VIEW}), _Scopes())
        with self.assertRaises(CashPermissionDeniedError):
            XCutQueryService(self.db, denied_view).get(
                cut_id=cut.entity_id, branch_id=self.branch,
                requester_user_id=self.cashier)

    def test_print_uses_gateway_is_idempotent_and_audited(self):
        cut, printer = self._generate(), _Printer()
        operation_id = new_uuid()
        first = PrintXCutUseCase(self.auth, printer).execute(
            self.db, cut_id=cut.entity_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=operation_id)
        retry = PrintXCutUseCase(self.auth, printer).execute(
            self.db, cut_id=cut.entity_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=operation_id)
        self.assertEqual(first.document_number, cut.document_number)
        self.assertTrue(retry.idempotent)
        self.assertEqual(len(printer.documents), 1)
        self.assertFalse(printer.documents[0]["final"])
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM cash_audit_log WHERE action='CASH_X_CUT_PRINTED'"
        ).fetchone()[0], 1)

    def test_print_failure_does_not_claim_success_or_audit(self):
        cut = self._generate()
        with self.assertRaises(RuntimeError):
            PrintXCutUseCase(self.auth, _Printer(fail=True)).execute(
                self.db, cut_id=cut.entity_id, branch_id=self.branch,
                actor_user_id=self.cashier, operation_id=new_uuid())
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM cash_audit_log WHERE action='CASH_X_CUT_PRINTED'"
        ).fetchone()[0], 0)


if __name__ == "__main__": unittest.main()
