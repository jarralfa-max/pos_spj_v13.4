from decimal import Decimal
import importlib
import sqlite3
import unittest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS
from backend.application.cash_register.shift_use_cases import OpenCashShiftUseCase
from backend.domain.cash_register.events import CashEvents
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


class CashRegisterFactoryAlertTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(self.db)
        importlib.import_module("migrations.standalone.176_cash_register_configuration_schema").run(self.db)
        self.branch = new_uuid()
        self.cashier = new_uuid()
        self.supervisor = new_uuid()
        self.register, self.drawer, self.terminal = new_uuid(), new_uuid(), new_uuid()
        self.now = "2026-08-03T00:00:00+00:00"
        self.db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                        (self.register, self.branch, "Caja", "ACTIVE", None, self.now, self.now))
        self.db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                        (self.drawer, self.branch, self.register, "Cajon", "ACTIVE", self.now, self.now))
        self.db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                        (self.terminal, self.branch, self.register, "POS", "ACTIVE", self.now, self.now))
        self.db.execute("INSERT INTO cash_movement_reasons VALUES(?,?,?,?,?,?,?,?)",
                        (new_uuid(), "EXCESS_CASH", "Exceso de efectivo", "SAFE_DROP", 0, 1, self.now, None))
        self.d50 = new_uuid()
        self.db.execute("INSERT INTO cash_denominations VALUES(?,?,?,?,?,?,?,?)",
                        (self.d50, "MXN", "50", "$50", 1, 1, self.now, None))
        for operation_type, approval, hard_cap in (
            ("SAFE_DROP", "300", "2000"),
            ("MANUAL_MOVEMENT", "500", "2000"),
        ):
            self.db.execute("INSERT INTO cash_operation_limits VALUES(?,?,?,?,?,?,?,?,?)",
                            (new_uuid(), operation_type, approval, hard_cap,
                             "SYSTEM", None, self.now, None, self.cashier))
        self.auth = CashAuthorizationPolicy(_Permissions(), _Scopes())
        self.shift_id = OpenCashShiftUseCase(
            self.auth,
            CashMonetaryLimitPolicy(approval_threshold=Decimal("1000"), hard_cap=Decimal("5000")),
        ).execute(
            self.db,
            branch_id=self.branch,
            register_id=self.register,
            drawer_id=self.drawer,
            terminal_id=self.terminal,
            cashier_user_id=self.cashier,
            opening_amount=Decimal("1000"),
            actor_user_id=self.cashier,
            operation_id=new_uuid(),
        ).entity_id
        self.session = _Session(user_id=self.cashier, branch_id=self.branch)
        self.root = _Root(self.db, self.session, self.shift_id)
        self.root.cash_authorization_policy = self.auth

    def tearDown(self):
        self.db.close()

    def _alert_rule(self, event_name: str) -> None:
        rule_id = new_uuid()
        self.db.execute("INSERT INTO cash_alert_rules VALUES(?,?,?,?,?,?,?,?,?)",
                        (rule_id, event_name, "WARNING", '["IN_APP"]',
                         "SYSTEM", None, 1, self.now, None))
        self.db.execute(
            "INSERT INTO cash_in_app_recipients VALUES(?,?,?,?,?)",
            (new_uuid(), rule_id, self.cashier, "Cajero", 1),
        )
        self.db.commit()

    def test_safe_drop_alert_jobs_are_prepared_post_commit_from_factory(self):
        self._alert_rule(CashEvents.SAFE_DROP_RECORDED)
        presenter = build_cash_register_presenter(self.root)

        result = presenter.register_cash_movement(
            movement_type="SAFE_DROP",
            amount=Decimal("350"),
            concept="Exceso de efectivo",
            reason_code="EXCESS_CASH",
            authorized_by=self.supervisor,
        )

        self.assertTrue(result.alert_required)
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM cash_notification_jobs").fetchone()[0],
            1,
        )
        job = self.db.execute(
            "SELECT channel,status FROM cash_notification_jobs"
        ).fetchone()
        self.assertEqual(job, ("IN_APP", "PENDING"))

    def test_handover_prepared_alert_jobs_are_prepared_post_commit_from_factory(self):
        self._alert_rule(CashEvents.HANDOVER_PREPARED)
        presenter = build_cash_register_presenter(self.root)
        drop = presenter.register_cash_movement(
            movement_type="SAFE_DROP",
            amount=Decimal("250"),
            concept="Exceso de efectivo",
            reason_code="EXCESS_CASH",
        )

        handover = presenter.prepare_cash_handover(
            safe_drop_entry_id=drop.entity_id,
            denominations={self.d50: 5},
        )

        self.assertEqual(handover.status, "PREPARED")
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM cash_notification_jobs").fetchone()[0],
            1,
        )


if __name__ == "__main__":
    unittest.main()
