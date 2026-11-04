"""SDLC-ARQ-SHIFT-001: Caja, POS, devoluciones y cierre financiero ven el
MISMO turno activo del cajero.

Decisión aprobada (BACKLOG 2026-11-02): un turno SUSPENDED sigue siendo el
turno del cajero pero debe reanudarse para vender; uno CLOSING no sirve para
vender: hay que terminar el cierre y abrir un turno nuevo.
"""
from datetime import date
from decimal import Decimal
import importlib
import sqlite3
import unittest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS
from backend.application.cash_register.sales_integration import CashSalesIntegrationService
from backend.application.cash_register.shift_use_cases import (
    BeginCashShiftClosingUseCase, OpenCashShiftUseCase, ResumeCashShiftUseCase,
    SuspendCashShiftUseCase,
)
from backend.domain.cash_register.exceptions import CashInvalidStateError
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.infrastructure.db.repositories.organization.org_unit_repository import (
    SqliteOrgUnitRepository,
)
from backend.infrastructure.db.repositories.software_updates.station_update_repository import (
    SqliteActiveOperationsProbe,
)
from backend.infrastructure.desktop.cash_register_factory import build_cash_register_presenter
from backend.infrastructure.integrations.finance_close_sources import SqliteOperationalCloseSources
from backend.infrastructure.integrations.sales_cash_effects_client import SalesCashEffectsClient
from backend.shared.ids import new_uuid

_NOW = "2026-08-13T12:00:00+00:00"


class _Permissions:
    def has_permission(self, user_id, permission_code):
        return permission_code in ALL_CASH_PERMISSIONS


class _Scopes:
    def can_access_branch(self, *, user_id, branch_id):
        return True


class _Session:
    is_active = True

    def __init__(self, *, user_id: str, branch_id: str) -> None:
        self.user_id = user_id
        self.active_branch_id = branch_id

    def tiene_permiso(self, _permission: str) -> bool:
        return True


class _Root:
    pass


class _ShiftHarness(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys=ON")
        for name in ("176_cash_register_configuration_schema",
                     "175_cash_register_bounded_context_schema",
                     "350_replication_engine"):
            importlib.import_module(f"migrations.standalone.{name}").run(self.db)
        # Outbox mínimos que lee el cierre financiero (sólo cuenta pendientes).
        for table in ("sales_outbox", "procurement_outbox", "hr_outbox", "costing_outbox"):
            self.db.execute(
                f"CREATE TABLE IF NOT EXISTS {table}"
                " (status TEXT, event_name TEXT, created_at TEXT)")
        self.branch, self.cashier = new_uuid(), new_uuid()
        self.register, self.drawer, self.terminal = new_uuid(), new_uuid(), new_uuid()
        self.db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                        (self.register, self.branch, "Caja", "ACTIVE", None, _NOW, _NOW))
        self.db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                        (self.drawer, self.branch, self.register, "Cajón", "ACTIVE", _NOW, _NOW))
        self.db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                        (self.terminal, self.branch, self.register, "POS", "ACTIVE", _NOW, _NOW))
        self.db.commit()
        self.auth = CashAuthorizationPolicy(_Permissions(), _Scopes())
        self.limit = CashMonetaryLimitPolicy(
            approval_threshold=Decimal("1000"), hard_cap=Decimal("5000"))

    def tearDown(self):
        self.db.close()

    # ── ayudas ─────────────────────────────────────────────────────────
    def _open(self) -> str:
        return OpenCashShiftUseCase(self.auth, self.limit).execute(
            self.db, branch_id=self.branch, register_id=self.register,
            drawer_id=self.drawer, terminal_id=self.terminal,
            cashier_user_id=self.cashier, opening_amount=Decimal("100"),
            actor_user_id=self.cashier, operation_id=new_uuid()).entity_id

    def _transition(self, use_case, shift_id: str, reason: str = "") -> None:
        use_case(self.auth).execute(
            self.db, shift_id=shift_id, branch_id=self.branch,
            actor_user_id=self.cashier, operation_id=new_uuid(), reason=reason)

    def _caja_shift_id(self, root=None):
        if root is None:
            root = _Root()
            root.db = self.db
            root.session = _Session(user_id=self.cashier, branch_id=self.branch)
        return build_cash_register_presenter(root).optional_active_shift_id()

    def _pos_shift_id(self):
        return SalesCashEffectsClient().require_open_shift(
            self.db, branch_id=self.branch, cashier_user_id=self.cashier)

    def _finance_open_count(self) -> int:
        return SqliteOperationalCloseSources(self.db).status(
            period_start=date(2000, 1, 1), period_end=date(2999, 12, 31)).open_cash_shifts

    def _cash_sale(self, amount: str = "50"):
        return CashSalesIntegrationService().record_completed_sale(
            self.db, sale_id=new_uuid(), branch_id=self.branch,
            cashier_user_id=self.cashier, operation_id=new_uuid(),
            payment_lines={"CASH": amount}, amount_to_settle=amount)

    def _ledger_sales(self) -> list[tuple[str, str]]:
        return self.db.execute(
            "SELECT shift_id, amount FROM cash_ledger_entries WHERE movement_type='CASH_SALE'"
        ).fetchall()

    def _insert_shift(self, *, status: str, opened_at: str, devices=None,
                      cashier=None) -> str:
        """Turno sembrado directo (estados que ningún caso de uso escribe)."""
        register, drawer, terminal = devices or (self.register, self.drawer, self.terminal)
        shift_id = new_uuid()
        self.db.execute(
            """INSERT INTO cash_shifts
            (id,branch_id,register_id,drawer_id,terminal_id,cashier_user_id,
             opening_amount,opening_operation_id,status,opened_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (shift_id, self.branch, register, drawer, terminal,
             cashier or self.cashier, "0", new_uuid(), status, opened_at))
        self.db.commit()
        return shift_id

    def _set_status(self, shift_id: str, status: str) -> None:
        self.db.execute("UPDATE cash_shifts SET status=? WHERE id=?", (status, shift_id))
        self.db.commit()

    def _extra_devices(self) -> tuple[str, str, str]:
        register, drawer, terminal = new_uuid(), new_uuid(), new_uuid()
        tag = register[-6:]
        self.db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                        (register, self.branch, f"Caja {tag}", "ACTIVE", None, _NOW, _NOW))
        self.db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                        (drawer, self.branch, register, f"Cajón {tag}", "ACTIVE", _NOW, _NOW))
        self.db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                        (terminal, self.branch, register, f"POS {tag}", "ACTIVE", _NOW, _NOW))
        return register, drawer, terminal


class ActiveShiftCoherenceTests(_ShiftHarness):
    # ── OPEN ───────────────────────────────────────────────────────────
    def test_open_shift_is_the_same_for_caja_pos_and_finance(self):
        shift_id = self._open()
        self.assertEqual(self._caja_shift_id(), shift_id)
        self.assertEqual(self._pos_shift_id(), shift_id)
        self.assertEqual(self._finance_open_count(), 1)
        result = self._cash_sale()
        self.assertEqual(result.shift_id, shift_id)
        self.assertEqual(self._ledger_sales(), [(shift_id, "50")])

    # ── SUSPENDED ──────────────────────────────────────────────────────
    def test_suspended_shift_is_still_the_cashiers_shift_but_cannot_sell(self):
        shift_id = self._open()
        self._transition(SuspendCashShiftUseCase, shift_id, reason="Pausa")
        self.assertEqual(self._caja_shift_id(), shift_id)
        self.assertEqual(self._finance_open_count(), 1)
        with self.assertRaises(CashInvalidStateError):
            self._pos_shift_id()
        with self.assertRaises(CashInvalidStateError):
            self._cash_sale()
        self.assertEqual(self._ledger_sales(), [])
        with self.assertRaisesRegex(CashInvalidStateError, "cajero ya tiene un turno activo"):
            self._open()
        self._transition(ResumeCashShiftUseCase, shift_id)
        self.assertEqual(self._pos_shift_id(), shift_id)
        self.assertEqual(self._cash_sale().shift_id, shift_id)

    # ── CLOSING ────────────────────────────────────────────────────────
    def test_closing_shift_is_shown_by_caja_and_counted_but_cannot_sell(self):
        shift_id = self._open()
        self._transition(BeginCashShiftClosingUseCase, shift_id)
        self.assertEqual(self._caja_shift_id(), shift_id)
        self.assertEqual(self._finance_open_count(), 1)
        with self.assertRaises(CashInvalidStateError):
            self._pos_shift_id()
        with self.assertRaises(CashInvalidStateError):
            self._cash_sale()
        with self.assertRaisesRegex(CashInvalidStateError, "cajero ya tiene un turno activo"):
            self._open()

    def test_closed_shift_is_returned_by_nobody_and_a_new_one_can_be_opened(self):
        shift_id = self._open()
        self._set_status(shift_id, "FORCE_CLOSED")
        self.assertIsNone(self._caja_shift_id())
        with self.assertRaises(CashInvalidStateError):
            self._pos_shift_id()
        self.assertEqual(self._finance_open_count(), 0)
        self.assertNotEqual(self._open(), shift_id)

    # ── sin turno ──────────────────────────────────────────────────────
    def test_no_shift_everyone_agrees(self):
        self.assertIsNone(self._caja_shift_id())
        with self.assertRaises(CashInvalidStateError):
            self._pos_shift_id()
        self.assertEqual(self._finance_open_count(), 0)

    # ── recuentos de otros contextos ───────────────────────────────────
    def test_other_contexts_count_only_non_final_shifts(self):
        self._insert_shift(status="OPEN", opened_at=_NOW)
        self._insert_shift(status="CLOSING", opened_at=_NOW, devices=self._extra_devices(),
                           cashier=new_uuid())
        self._insert_shift(status="FORCE_CLOSED", opened_at=_NOW,
                           devices=self._extra_devices(), cashier=new_uuid())
        self.assertEqual(self._finance_open_count(), 2)
        self.assertEqual(SqliteOrgUnitRepository(self.db).open_cash_shifts(self.branch), 2)
        self.assertEqual(SqliteActiveOperationsProbe(self.db).snapshot().cash_cuts_in_progress, 1)


class ActiveShiftDivergenceTests(_ShiftHarness):
    """Divergencias del intent. Paso 1 del plan: fallan HOY
    (`expectedFailure`); el paso que corrige cada una quita su marca."""

    def _pos_problem(self):
        from frontend.desktop.modules.sales_pos.composition import _cash_shift_problem
        return _cash_shift_problem(self.db)(branch_id=self.branch, cashier_user_id=self.cashier)

    def test_pos_tells_the_cashier_to_resume_a_suspended_shift(self):
        shift_id = self._open()
        self._transition(SuspendCashShiftUseCase, shift_id, reason="Pausa")
        self.assertIn("suspendido", self._pos_problem())
        with self.assertRaises(CashInvalidStateError) as caught:
            self._pos_shift_id()
        self.assertEqual(caught.exception.shift_id, shift_id)

    def test_pos_tells_the_cashier_to_finish_closing_and_open_a_new_shift(self):
        shift_id = self._open()
        self._transition(BeginCashShiftClosingUseCase, shift_id)
        self.assertIn("cierre", self._pos_problem())
        with self.assertRaises(CashInvalidStateError) as caught:
            self._pos_shift_id()
        self.assertEqual(caught.exception.shift_id, shift_id)

    @unittest.expectedFailure
    def test_composition_root_holds_no_active_shift_cache(self):
        root = _Root()
        root.db = self.db
        root.session = _Session(user_id=self.cashier, branch_id=self.branch)
        presenter = build_cash_register_presenter(root)
        shift_id = presenter.open_cash_shift(opening_amount=Decimal("0")).entity_id
        self.assertEqual(presenter.optional_active_shift_id(), shift_id)
        self.assertFalse(hasattr(root, "active_cash_shift_id"))
        self._set_status(shift_id, "FORCE_CLOSED")
        self.assertIsNone(presenter.optional_active_shift_id())

    @unittest.expectedFailure
    def test_cancelled_shift_is_final_for_organization(self):
        self._insert_shift(status="CANCELLED", opened_at=_NOW)
        self.assertEqual(SqliteOrgUnitRepository(self.db).open_cash_shifts(self.branch), 0)


if __name__ == "__main__":
    unittest.main()
