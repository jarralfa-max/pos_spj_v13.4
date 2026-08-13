from decimal import Decimal
import importlib
import sqlite3
import unittest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS
from backend.application.cash_register.sales_integration import CashSalesIntegrationService
from backend.application.cash_register.shift_use_cases import OpenCashShiftUseCase
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.infrastructure.desktop.cash_register_factory import build_cash_register_presenter
from backend.shared.ids import new_uuid


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

    def tiene_permiso(self, permission_code: str) -> bool:
        return permission_code in ALL_CASH_PERMISSIONS


class _Root:
    def __init__(self, db, session, shift_id):
        self.db = db
        self.session = session
        self.active_cash_shift_id = shift_id


class CashRefundFactoryWiringTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(self.db)
        importlib.import_module("migrations.standalone.176_cash_register_configuration_schema").run(self.db)
        self.branch = new_uuid()
        self.cashier = new_uuid()
        self.supervisor = new_uuid()
        register, drawer, terminal = new_uuid(), new_uuid(), new_uuid()
        now = "2026-08-03T00:00:00+00:00"
        self.db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                        (register, self.branch, "Caja", "ACTIVE", None, now, now))
        self.db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                        (drawer, self.branch, register, "Cajon", "ACTIVE", now, now))
        self.db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                        (terminal, self.branch, register, "POS", "ACTIVE", now, now))
        self.db.execute("INSERT INTO cash_operation_limits VALUES(?,?,?,?,?,?,?,?,?)",
                        (new_uuid(), "REFUND", "500", "2000", "SYSTEM", None, now, None, self.cashier))
        self.auth = CashAuthorizationPolicy(_Permissions(), _Scopes())
        self.shift_id = OpenCashShiftUseCase(
            self.auth,
            CashMonetaryLimitPolicy(approval_threshold=Decimal("1000"), hard_cap=Decimal("5000")),
        ).execute(
            self.db,
            branch_id=self.branch,
            register_id=register,
            drawer_id=drawer,
            terminal_id=terminal,
            cashier_user_id=self.cashier,
            opening_amount=Decimal("1000"),
            actor_user_id=self.cashier,
            operation_id=new_uuid(),
        ).entity_id
        self.root = _Root(self.db, _Session(user_id=self.cashier, branch_id=self.branch), self.shift_id)
        self.root.cash_authorization_policy = self.auth

    def tearDown(self):
        self.db.close()

    def test_non_cash_refund_emits_event_without_physical_outflow(self):
        presenter = build_cash_register_presenter(self.root)
        refund_id = new_uuid()
        sale_id = new_uuid()

        result = presenter.execute_cash_refund(
            refund_id=refund_id,
            sale_id=sale_id,
            authorized_by=self.supervisor,
            original_payment_lines={"CARD": Decimal("100")},
            refund_lines={"CARD": Decimal("100")},
            reason="Devolucion autorizada",
        )

        self.assertIsNone(result.ledger_entry_id)
        self.assertEqual(result.cash_amount, Decimal("0"))
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM cash_ledger_entries WHERE movement_type='CASH_REFUND'").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM cash_domain_events WHERE event_name='CASH_REFUND_PROCESSED'").fetchone()[0],
            1,
        )

    def test_cash_refund_creates_physical_outflow_ledger_entry(self):
        sale_id = new_uuid()
        CashSalesIntegrationService().record_completed_sale(
            self.db,
            sale_id=sale_id,
            branch_id=self.branch,
            cashier_user_id=self.cashier,
            operation_id=new_uuid(),
            payment_lines={"CASH": Decimal("200")},
        )
        presenter = build_cash_register_presenter(self.root)

        result = presenter.execute_cash_refund(
            refund_id=new_uuid(),
            sale_id=sale_id,
            authorized_by=self.supervisor,
            original_payment_lines={"CASH": Decimal("200")},
            refund_lines={"CASH": Decimal("50")},
            reason="Devolucion parcial autorizada",
        )

        self.assertIsNotNone(result.ledger_entry_id)
        row = self.db.execute(
            "SELECT movement_type,direction,amount,related_sale_id FROM cash_ledger_entries WHERE id=?",
            (result.ledger_entry_id,),
        ).fetchone()
        self.assertEqual(row, ("CASH_REFUND", "OUTFLOW", "50", sale_id))


if __name__ == "__main__":
    unittest.main()
