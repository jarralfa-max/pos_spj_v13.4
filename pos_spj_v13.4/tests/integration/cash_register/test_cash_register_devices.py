import importlib
import sqlite3
import unittest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.device_use_cases import (
    AssignCashDeviceUseCase, CreateCashDeviceUseCase,
    DiagnoseCashHardwareUseCase, SetCashDeviceStatusUseCase,
)
from backend.application.cash_register.device_query_service import CashDeviceQueryService
from backend.application.cash_register.hardware import StubCashHardwareGateway
from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS
from backend.infrastructure.db.repositories.cash_register.repositories import CashDeviceRepository
from backend.shared.ids import new_uuid


class _Permissions:
    def has_permission(self, user_id, permission_code): return permission_code in ALL_CASH_PERMISSIONS
class _Scopes:
    def can_access_branch(self, *, user_id, branch_id): return True


class _DeviceRows:
    def __init__(self, rows):
        self._rows = rows

    def list_devices(self, kind: str):
        return list(self._rows)


class CashRegisterDeviceTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(self.db)
        self.auth = CashAuthorizationPolicy(_Permissions(), _Scopes())
        self.branch, self.actor = new_uuid(), new_uuid()

    def tearDown(self): self.db.close()

    def test_create_activate_block_and_assign_devices_are_audited_and_outboxed(self):
        create = CreateCashDeviceUseCase(self.auth)
        register = create.execute(self.db, kind="register", branch_id=self.branch,
                                  name="Caja principal", actor_user_id=self.actor,
                                  operation_id=new_uuid())
        second = create.execute(self.db, kind="register", branch_id=self.branch,
                                name="Caja secundaria", actor_user_id=self.actor,
                                operation_id=new_uuid())
        drawer = create.execute(self.db, kind="drawer", branch_id=self.branch,
                                register_id=register.entity_id, name="Cajón A",
                                actor_user_id=self.actor, operation_id=new_uuid())
        terminal = create.execute(self.db, kind="terminal", branch_id=self.branch,
                                  register_id=register.entity_id, name="POS A",
                                  actor_user_id=self.actor, operation_id=new_uuid())
        SetCashDeviceStatusUseCase(self.auth).execute(
            self.db, kind="register", device_id=register.entity_id,
            branch_id=self.branch, activate=False, actor_user_id=self.actor,
            operation_id=new_uuid(), reason="Mantenimiento")
        SetCashDeviceStatusUseCase(self.auth).execute(
            self.db, kind="register", device_id=register.entity_id,
            branch_id=self.branch, activate=True, actor_user_id=self.actor,
            operation_id=new_uuid())
        AssignCashDeviceUseCase(self.auth).execute(
            self.db, kind="drawer", device_id=drawer.entity_id,
            register_id=second.entity_id, branch_id=self.branch,
            actor_user_id=self.actor, operation_id=new_uuid())
        self.assertEqual(self.db.execute("SELECT status FROM cash_registers WHERE id=?", (register.entity_id,)).fetchone()[0], "ACTIVE")
        self.assertEqual(self.db.execute("SELECT register_id FROM cash_drawers WHERE id=?", (drawer.entity_id,)).fetchone()[0], second.entity_id)
        events = self.db.execute("SELECT COUNT(*) FROM cash_domain_events").fetchone()[0]
        self.assertEqual(events, self.db.execute("SELECT COUNT(*) FROM cash_outbox").fetchone()[0])
        self.assertEqual(events, self.db.execute("SELECT COUNT(*) FROM cash_audit_log").fetchone()[0])

    def test_hardware_is_accessed_only_through_gateway(self):
        gateway = StubCashHardwareGateway(connected=False)
        result = DiagnoseCashHardwareUseCase(self.auth, gateway).execute(
            self.db, device_id=new_uuid(), branch_id=self.branch,
            actor_user_id=self.actor, operation_id=new_uuid())
        self.assertFalse(result.connected)
        self.assertEqual(result.message, "Sin conexión")
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM cash_domain_events WHERE event_name='CASH_HARDWARE_DIAGNOSED'"
        ).fetchone()[0], 1)

    def test_born_clean_schema_rejects_non_uuid_device_identity(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                """INSERT INTO cash_registers
                (id,branch_id,name,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?)""",
                ("kkkk", self.branch, "Caja contaminada", "ACTIVE", "2026-08-13", "2026-08-13"),
            )

    def test_device_query_marks_contaminated_identity_before_ui_actions(self):
        rows = CashDeviceQueryService(_DeviceRows([{
            "id": "kkkk",
            "name": "Caja contaminada",
            "branch_name": self.branch,
            "assignment": "",
            "status": "ACTIVE",
            "hardware_status": "No verificado",
        }])).list_devices("register")

        self.assertEqual(rows[0].id, "kkkk")
        self.assertEqual(rows[0].hardware_status, "Identidad inválida")

    def test_device_query_translates_branch_id_to_branch_name_when_catalog_exists(self):
        self.db.execute(
            """CREATE TABLE sucursales (
            id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL
            )"""
        )
        self.db.execute(
            "INSERT INTO sucursales(id,nombre) VALUES(?,?)",
            (self.branch, "Sucursal Centro"),
        )
        device = CreateCashDeviceUseCase(self.auth).execute(
            self.db, kind="register", branch_id=self.branch,
            name="Caja mostrador", actor_user_id=self.actor,
            operation_id=new_uuid(),
        )

        rows = CashDeviceQueryService(CashDeviceRepository(self.db)).list_devices("register")

        self.assertEqual(rows[0].id, device.entity_id)
        self.assertEqual(rows[0].branch_name, "Sucursal Centro")

    def test_device_commands_reject_non_uuid_identity_before_repository_mutation(self):
        with self.assertRaises(ValueError):
            SetCashDeviceStatusUseCase(self.auth).execute(
                self.db, kind="register", device_id="kkkk",
                branch_id=self.branch, activate=False,
                actor_user_id=self.actor, operation_id=new_uuid(),
                reason="Mantenimiento",
            )


if __name__ == "__main__": unittest.main()
