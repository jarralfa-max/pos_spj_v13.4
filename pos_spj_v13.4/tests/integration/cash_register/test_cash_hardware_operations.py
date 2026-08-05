import importlib
import sqlite3
import unittest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.hardware import CashHardwareError
from backend.application.cash_register.hardware_use_cases import (
    OpenCashDrawerUseCase, PrintCashDocumentUseCase,
)
from backend.shared.ids import new_uuid


class Allow:
    def has_permission(self, user_id, permission_code): return True
    def can_access_branch(self, *, user_id, branch_id): return True


class Drawer:
    def __init__(self): self.opened = []
    def open_drawer(self, drawer_id): self.opened.append(drawer_id)


class BrokenPrinter:
    def print_job(self, printer_id, job):
        raise OSError("vendor detail must not leak")


class CashHardwareOperationsTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module(
            "migrations.standalone.175_cash_register_bounded_context_schema"
        ).run(self.db)
        self.branch, self.actor = new_uuid(), new_uuid()
        self.register, self.drawer = new_uuid(), new_uuid()
        now = "2026-08-04T12:00:00+00:00"
        self.db.execute(
            "INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
            (self.register, self.branch, "Caja 1", "ACTIVE", None, now, now),
        )
        self.db.execute(
            "INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
            (self.drawer, self.branch, self.register, "Cajón 1", "ACTIVE", now, now),
        )
        self.db.commit()
        checker = Allow()
        self.authorization = CashAuthorizationPolicy(checker, checker)

    def tearDown(self): self.db.close()

    def test_open_without_sale_is_audited_with_reason(self):
        gateway = Drawer()
        operation = new_uuid()
        OpenCashDrawerUseCase(self.authorization, gateway).execute(
            self.db, drawer_id=self.drawer, branch_id=self.branch,
            actor_user_id=self.actor, operation_id=operation,
            reason="Conteo supervisor",
        )
        self.assertEqual(gateway.opened, [self.drawer])
        audit = self.db.execute(
            "SELECT action,reason FROM cash_audit_log WHERE operation_id=?", (operation,)
        ).fetchone()
        self.assertEqual(audit, ("CASH_DRAWER_OPENED", "Conteo supervisor"))
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM cash_outbox WHERE operation_id=?", (operation,)
        ).fetchone()[0], 1)

    def test_driver_failure_is_committed_as_alert_before_raising(self):
        operation, printer, document = new_uuid(), new_uuid(), new_uuid()
        with self.assertRaises(CashHardwareError) as caught:
            PrintCashDocumentUseCase(self.authorization, BrokenPrinter()).execute(
                self.db, printer_id=printer, document_id=document, content=b"ticket",
                branch_id=self.branch, actor_user_id=self.actor, operation_id=operation,
            )
        self.assertEqual(caught.exception.code, "DRIVER_FAILURE")
        event = self.db.execute(
            "SELECT event_name,payload_json FROM cash_domain_events WHERE operation_id=?",
            (operation,),
        ).fetchone()
        self.assertEqual(event[0], "CASH_HARDWARE_OPERATION_FAILED")
        self.assertIn('"alert_required":true', event[1])
        self.assertNotIn("vendor detail", event[1])


if __name__ == "__main__": unittest.main()
