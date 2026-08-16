import importlib
import sqlite3
import unittest

from backend.application.cash_register.overview_query_service import CashOverviewQueryService
from backend.application.cash_register.permissions import CashPermissions
from backend.shared.ids import new_uuid


class AllowAuth:
    def __init__(self):
        self.calls = []
    def require(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["permission_code"] != CashPermissions.ACCESS:
            raise AssertionError(kwargs)


class CashOverviewQueryServiceTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module("migrations.standalone.176_cash_register_configuration_schema").run(self.db)
        importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(self.db)
        self.branch = new_uuid()
        self.user = new_uuid()
        self.register = new_uuid()
        self.drawer = new_uuid()
        self.terminal = new_uuid()
        self.shift = new_uuid()
        now = "2026-08-01T10:00:00+00:00"
        self.db.execute(
            "INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
            (self.register, self.branch, "Caja 1", "ACTIVE", None, now, now),
        )
        self.db.execute(
            "INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
            (self.drawer, self.branch, self.register, "Cajon 1", "ACTIVE", now, now),
        )
        self.db.execute(
            "INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
            (self.terminal, self.branch, self.register, "Terminal 1", "BLOCKED", now, now),
        )
        self.db.execute(
            """INSERT INTO cash_shifts
            (id,branch_id,register_id,drawer_id,terminal_id,cashier_user_id,
             opening_amount,opening_operation_id,status,opened_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (self.shift, self.branch, self.register, self.drawer, self.terminal,
             self.user, "100.00", new_uuid(), "OPEN", now),
        )
        self.db.execute(
            """INSERT INTO cash_ledger_entries
            (id,shift_id,branch_id,movement_type,direction,amount,operation_id,
             recorded_by,concept,recorded_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (new_uuid(), self.shift, self.branch, "OPENING_FLOAT", "INFLOW",
             "100.00", new_uuid(), self.user, "Apertura", now),
        )
        self.db.execute(
            """INSERT INTO cash_handovers
            (id,shift_id,branch_id,amount,prepared_by,operation_id,source_entry_id,status,prepared_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (new_uuid(), self.shift, self.branch, "50.00", self.user, new_uuid(),
             self._safe_drop(), "PREPARED", now),
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _safe_drop(self):
        entry_id = new_uuid()
        self.db.execute(
            """INSERT INTO cash_ledger_entries
            (id,shift_id,branch_id,movement_type,direction,amount,operation_id,
             recorded_by,concept,recorded_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (entry_id, self.shift, self.branch, "SAFE_DROP", "OUTFLOW",
             "50.00", new_uuid(), self.user, "Retiro", "2026-08-01T10:05:00+00:00"),
        )
        return entry_id

    def test_dashboard_returns_operational_kpis_and_alert_lists(self):
        auth = AllowAuth()
        dto = CashOverviewQueryService(self.db, auth).dashboard(
            branch_id=self.branch,
            requester_user_id=self.user,
        )

        values = {kpi.key: kpi.numeric_value for kpi in dto.kpis}
        self.assertEqual(values["active_shifts"], 1)
        self.assertEqual(str(values["expected_cash"]), "50")
        self.assertEqual(values["safe_drops"], 1)
        self.assertEqual(values["terminals"], 1)
        self.assertEqual(len(dto.active_shifts), 1)
        self.assertEqual(dto.active_shifts[0].detail, "Fondo inicial $100.00")
        self.assertNotIn(self.user[:8], dto.active_shifts[0].detail)
        self.assertEqual(len(dto.pending_handovers), 1)
        self.assertEqual(dto.pending_handovers[0].detail, "Monto preparado $50.00")
        self.assertEqual(len(dto.terminal_alerts), 1)
        self.assertIn("entregas de valores pendientes", dto.next_action)
        self.assertEqual(auth.calls[0]["permission_code"], CashPermissions.ACCESS)


if __name__ == "__main__":
    unittest.main()
