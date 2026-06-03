import importlib
import sqlite3
from pathlib import Path

from core.services.driver_service import DriverService

ROOT = Path(__file__).resolve().parents[1]
RRHH_UI = ROOT / "modulos" / "rrhh.py"
DELIVERY_UI = ROOT / "modulos" / "delivery.py"


def test_phase8_rrhh_ui_removed_dead_attendance_and_schema_creation():
    src = RRHH_UI.read_text(encoding="utf-8")
    assert "_registrar_asistencia_ORIG" not in src
    assert "CREATE TABLE" not in src
    assert "ALTER TABLE" not in src
    assert "self.attendance_service.register_check_in_out" in src


def test_phase8_delivery_ui_no_longer_mutates_schema_and_uses_driver_service():
    src = DELIVERY_UI.read_text(encoding="utf-8")
    assert "CREATE TABLE" not in src
    assert "ALTER TABLE" not in src
    assert "GestorDriversDialog(self.conexion, self, driver_service=self.driver_service)" in src
    assert "self.driver_service.create_driver" in src
    assert "self.driver_service.update_driver" in src
    assert "self.driver_service.deactivate_driver" in src
    assert "DELETE FROM drivers" not in src


def test_phase8_rrhh_cleanup_migration_creates_ui_removed_tables_idempotently():
    migration = importlib.import_module("migrations.standalone.094_rrhh_delivery_cleanup_schema")
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE drivers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            telefono TEXT,
            activo INTEGER DEFAULT 1,
            sucursal_id INTEGER DEFAULT 1
        )
        """
    )

    migration.run(conn)
    migration.run(conn)

    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"puestos", "vacaciones_personal", "drivers"}.issubset(tables)
    driver_cols = {row[1] for row in conn.execute("PRAGMA table_info(drivers)")}
    assert {"personal_id", "source_module"}.issubset(driver_cols)


def test_phase8_driver_service_is_single_write_path_for_driver_people():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    service = DriverService(conn)

    driver_id = service.create_driver(
        {"nombre": "Rosa Repartidora", "telefono": "+525551112222", "sucursal_id": 2}
    )
    service.update_driver(
        driver_id,
        {"nombre": "Rosa R.", "telefono": "+525551112222", "sucursal_id": 2, "activo": 1},
    )
    rows = service.list_drivers()
    assert len(rows) == 1
    assert rows[0]["id"] == driver_id
    assert rows[0]["nombre"] == "Rosa R."
    assert rows[0]["sucursal_id"] == 2

    service.deactivate_driver(driver_id)
    assert service.list_active_drivers(branch_id=2) == []
