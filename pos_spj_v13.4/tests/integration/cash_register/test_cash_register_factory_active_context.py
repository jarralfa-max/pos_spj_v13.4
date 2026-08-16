import importlib
import sqlite3
import unittest

from backend.infrastructure.desktop.cash_register_factory import build_cash_register_presenter
from backend.shared.ids import new_uuid


class _Session:
    is_active = True

    def __init__(self, *, user_id: str, branch_id: str) -> None:
        self.user_id = user_id
        self.active_branch_id = branch_id

    def tiene_permiso(self, _permission: str) -> bool:
        return True


class _Root:
    pass


class CashRegisterFactoryActiveContextTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys=ON")
        importlib.import_module("migrations.standalone.176_cash_register_configuration_schema").run(self.db)
        importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(self.db)

    def tearDown(self):
        self.db.close()

    def test_presenter_resolves_active_register_drawer_and_terminal_from_branch(self):
        branch_id, user_id = new_uuid(), new_uuid()
        register_id, drawer_id, terminal_id = new_uuid(), new_uuid(), new_uuid()
        now = "2026-08-13T12:00:00+00:00"
        self.db.execute(
            "INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
            (register_id, branch_id, "Caja principal", "ACTIVE", None, now, now),
        )
        self.db.execute(
            "INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
            (drawer_id, branch_id, register_id, "Cajon principal", "ACTIVE", now, now),
        )
        self.db.execute(
            "INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
            (terminal_id, branch_id, register_id, "Terminal principal", "ACTIVE", now, now),
        )
        root = _Root()
        root.db = self.db
        root.session = _Session(user_id=user_id, branch_id=branch_id)

        presenter = build_cash_register_presenter(root)

        self.assertEqual(presenter.active_register_id(), register_id)
        self.assertEqual(presenter.active_drawer_id(), drawer_id)
        self.assertEqual(presenter.active_terminal_id(), terminal_id)

    def test_presenter_uses_active_terminal_as_sync_device_when_session_lacks_one(self):
        branch_id, user_id = new_uuid(), new_uuid()
        register_id, drawer_id, terminal_id = new_uuid(), new_uuid(), new_uuid()
        now = "2026-08-13T12:00:00+00:00"
        self.db.execute(
            "INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
            (register_id, branch_id, "Caja principal", "ACTIVE", None, now, now),
        )
        self.db.execute(
            "INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
            (drawer_id, branch_id, register_id, "Cajon principal", "ACTIVE", now, now),
        )
        self.db.execute(
            "INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
            (terminal_id, branch_id, register_id, "Terminal principal", "ACTIVE", now, now),
        )
        root = _Root()
        root.db = self.db
        root.session = _Session(user_id=user_id, branch_id=branch_id)

        presenter = build_cash_register_presenter(root)

        self.assertEqual(presenter.active_sync_device_id(), terminal_id)
        state = presenter.cash_sync_state()
        self.assertEqual(state["id"], terminal_id)
        self.assertEqual(
            self.db.execute(
                "SELECT branch_id FROM cash_sync_devices WHERE id=?",
                (terminal_id,),
            ).fetchone()[0],
            branch_id,
        )

    def test_presenter_recovers_active_shift_from_persistence_after_restart(self):
        branch_id, user_id = new_uuid(), new_uuid()
        register_id, drawer_id, terminal_id, shift_id = (
            new_uuid(), new_uuid(), new_uuid(), new_uuid()
        )
        now = "2026-08-13T12:00:00+00:00"
        self.db.execute(
            "INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
            (register_id, branch_id, "Caja principal", "ACTIVE", None, now, now),
        )
        self.db.execute(
            "INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
            (drawer_id, branch_id, register_id, "Cajon principal", "ACTIVE", now, now),
        )
        self.db.execute(
            "INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
            (terminal_id, branch_id, register_id, "Terminal principal", "ACTIVE", now, now),
        )
        self.db.execute(
            """INSERT INTO cash_shifts
            (id,branch_id,register_id,drawer_id,terminal_id,cashier_user_id,
             opening_amount,opening_operation_id,status,opened_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                shift_id, branch_id, register_id, drawer_id, terminal_id,
                user_id, "250.00", new_uuid(), "OPEN", now,
            ),
        )
        self.db.commit()
        root = _Root()
        root.db = self.db
        root.session = _Session(user_id=user_id, branch_id=branch_id)

        presenter = build_cash_register_presenter(root)

        self.assertEqual(presenter.active_shift_id(), shift_id)
        self.assertEqual(presenter.optional_active_shift_id(), shift_id)
        self.assertEqual(presenter.active_register_id(), register_id)
        self.assertEqual(presenter.active_drawer_id(), drawer_id)
        self.assertEqual(presenter.active_terminal_id(), terminal_id)


if __name__ == "__main__":
    unittest.main()
