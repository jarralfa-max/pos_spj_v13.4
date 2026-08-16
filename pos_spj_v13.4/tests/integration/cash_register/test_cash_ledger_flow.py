from decimal import Decimal
import importlib
import sqlite3
import unittest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.ledger_query_service import CashLedgerQueryService
from backend.application.cash_register.ledger_use_cases import (
    RegisterCashMovementUseCase, ReverseCashMovementUseCase,
)
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS
from backend.application.cash_register.shift_use_cases import OpenCashShiftUseCase
from backend.domain.cash_register.enums import CashMovementType
from backend.domain.cash_register.exceptions import (
    CashAuthorizationRequiredError, CashDuplicateOperationError, CashInvalidStateError,
    CashSegregationOfDutiesError,
)
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.infrastructure.db.repositories.cash_register.repositories import CashLedgerRepository
from backend.shared.ids import new_uuid


class _Permissions:
    def has_permission(self, user_id, permission_code): return permission_code in ALL_CASH_PERMISSIONS


class _Scopes:
    def can_access_branch(self, *, user_id, branch_id): return True


class CashLedgerFlowTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(self.db)
        self.auth = CashAuthorizationPolicy(_Permissions(), _Scopes())
        self.limit = CashMonetaryLimitPolicy(
            approval_threshold=Decimal("1000"), hard_cap=Decimal("5000"))
        self.branch, self.cashier, self.supervisor = new_uuid(), new_uuid(), new_uuid()
        self.register, self.drawer, self.terminal = new_uuid(), new_uuid(), new_uuid()
        now = "2026-08-03T00:00:00+00:00"
        self.db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                        (self.register, self.branch, "Caja", "ACTIVE", None, now, now))
        self.db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                        (self.drawer, self.branch, self.register, "Cajón", "ACTIVE", now, now))
        self.db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                        (self.terminal, self.branch, self.register, "POS", "ACTIVE", now, now))
        self.db.commit()
        self.shift_id = OpenCashShiftUseCase(self.auth, self.limit).execute(
            self.db, branch_id=self.branch, register_id=self.register,
            drawer_id=self.drawer, terminal_id=self.terminal,
            cashier_user_id=self.cashier, opening_amount=Decimal("500"),
            actor_user_id=self.cashier, operation_id=new_uuid()).entity_id
        self.command = RegisterCashMovementUseCase(self.auth, self.limit)

    def tearDown(self): self.db.close()

    def _record(self, kind, amount, *, operation_id=None, authorized_by=None):
        return self.command.execute(
            self.db, shift_id=self.shift_id, branch_id=self.branch,
            movement_type=kind, amount=amount, concept="Operación de prueba",
            actor_user_id=self.cashier, operation_id=operation_id or new_uuid(),
            authorized_by=authorized_by)

    def test_movements_and_projection_reconstruct_exact_decimal_balance(self):
        self._record(CashMovementType.MANUAL_INCOME, Decimal("100.10"))
        self._record(CashMovementType.MANUAL_WITHDRAWAL, Decimal("25.05"))
        self._record(CashMovementType.SAFE_DROP, Decimal("50"))
        projection = CashLedgerQueryService(CashLedgerRepository(self.db)).projection(self.shift_id)
        self.assertEqual(projection.balance, Decimal("525.05"))
        self.assertEqual(projection.inflows, Decimal("600.10"))
        self.assertEqual(projection.outflows, Decimal("75.05"))
        self.assertEqual(projection.movement_count, 4)
        self.assertEqual(projection.rows[0].reference_id, self.shift_id)
        self.assertIsNone(projection.rows[-1].related_sale_id)

    def test_manual_outflows_cannot_exceed_reconstructed_cash(self):
        with self.assertRaises(CashInvalidStateError):
            self._record(CashMovementType.MANUAL_WITHDRAWAL, Decimal("500.01"))
        with self.assertRaises(CashInvalidStateError):
            self._record(CashMovementType.SAFE_DROP, Decimal("500.01"))

        self._record(CashMovementType.MANUAL_INCOME, Decimal("25"))
        self._record(CashMovementType.MANUAL_WITHDRAWAL, Decimal("525"))

        projection = CashLedgerQueryService(CashLedgerRepository(self.db)).projection(self.shift_id)
        self.assertEqual(projection.balance, Decimal("0"))

    def test_explicit_idempotency_does_not_duplicate_side_effects(self):
        operation_id = new_uuid()
        first = self._record(CashMovementType.MANUAL_INCOME, Decimal("10"), operation_id=operation_id)
        second = self._record(CashMovementType.MANUAL_INCOME, Decimal("10"), operation_id=operation_id)
        self.assertEqual(first.entity_id, second.entity_id)
        self.assertTrue(second.idempotent)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM cash_ledger_entries WHERE operation_id=?", (operation_id,)).fetchone()[0], 1)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM cash_outbox WHERE operation_id=?", (operation_id,)).fetchone()[0], 1)

    def test_reversal_is_compensating_and_original_is_immutable(self):
        original = self._record(CashMovementType.MANUAL_WITHDRAWAL, Decimal("40"))
        before = self.db.execute("SELECT * FROM cash_ledger_entries WHERE id=?", (original.entity_id,)).fetchone()
        reversal = ReverseCashMovementUseCase(self.auth).execute(
            self.db, entry_id=original.entity_id, branch_id=self.branch,
            actor_user_id=self.cashier, authorized_by=self.supervisor,
            operation_id=new_uuid(), reason="Captura incorrecta")
        after = self.db.execute("SELECT * FROM cash_ledger_entries WHERE id=?", (original.entity_id,)).fetchone()
        self.assertEqual(before, after)
        row = self.db.execute(
            "SELECT movement_type,direction,amount,reversal_of_id FROM cash_ledger_entries WHERE id=?",
            (reversal.entity_id,)).fetchone()
        self.assertEqual(row, ("REVERSAL", "INFLOW", "40", original.entity_id))
        self.assertEqual(CashLedgerQueryService(CashLedgerRepository(self.db)).projection(
            self.shift_id).balance, Decimal("500"))
        with self.assertRaises(CashDuplicateOperationError):
            ReverseCashMovementUseCase(self.auth).execute(
                self.db, entry_id=original.entity_id, branch_id=self.branch,
                actor_user_id=self.cashier, authorized_by=self.supervisor,
                operation_id=new_uuid(), reason="Otra vez")

    def test_limits_segregation_decimal_and_open_shift_are_enforced(self):
        with self.assertRaises(TypeError):
            self._record(CashMovementType.MANUAL_INCOME, 10.0)
        with self.assertRaises(CashAuthorizationRequiredError):
            self._record(CashMovementType.MANUAL_INCOME, Decimal("1000.01"))
        self._record(CashMovementType.MANUAL_INCOME, Decimal("1000.01"),
                     authorized_by=self.supervisor)
        original = self._record(CashMovementType.MANUAL_INCOME, Decimal("1"))
        with self.assertRaises(CashSegregationOfDutiesError):
            ReverseCashMovementUseCase(self.auth).execute(
                self.db, entry_id=original.entity_id, branch_id=self.branch,
                actor_user_id=self.cashier, authorized_by=self.cashier,
                operation_id=new_uuid(), reason="No permitido")
        self.db.execute("UPDATE cash_shifts SET status='SUSPENDED' WHERE id=?", (self.shift_id,))
        self.db.commit()
        with self.assertRaises(CashInvalidStateError):
            self._record(CashMovementType.MANUAL_INCOME, Decimal("1"))


if __name__ == "__main__": unittest.main()
