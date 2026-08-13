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


if __name__ == "__main__":
    unittest.main()
