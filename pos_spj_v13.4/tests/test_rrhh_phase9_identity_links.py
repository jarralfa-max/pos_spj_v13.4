import importlib
import sqlite3

import pytest

from core.rrhh.application import EmployeeIdentityApplicationService
from core.rrhh.events import EMPLEADO_ACTUALIZADO, REPARTIDOR_ASIGNADO
from core.rrhh.infrastructure import SQLiteEmployeeIdentityRepository


class FakePublisher:
    def __init__(self):
        self.payloads = []

    def publish(self, payload):
        self.payloads.append(payload)


def _db(with_identity_columns=True):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    user_identity_column = ", personal_id INTEGER" if with_identity_columns else ""
    driver_identity_columns = ", personal_id INTEGER, source_module TEXT DEFAULT 'delivery'" if with_identity_columns else ""
    conn.executescript(
        f"""
        CREATE TABLE personal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            apellidos TEXT,
            puesto TEXT,
            salario REAL DEFAULT 0,
            fecha_ingreso TEXT,
            activo INTEGER DEFAULT 1,
            telefono TEXT,
            email TEXT,
            sucursal_id INTEGER DEFAULT 1
        );
        CREATE TABLE usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            usuario TEXT,
            password_hash TEXT,
            rol TEXT,
            sucursal_id INTEGER,
            activo INTEGER DEFAULT 1
            {user_identity_column}
        );
        CREATE TABLE drivers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            telefono TEXT,
            activo INTEGER DEFAULT 1,
            sucursal_id INTEGER
            {driver_identity_columns}
        );
        """
    )
    conn.execute(
        "INSERT INTO personal(nombre, apellidos, puesto, activo, sucursal_id) VALUES(?,?,?,?,?)",
        ("Rosa", "Perez", "Repartidor", 1, 2),
    )
    conn.execute(
        "INSERT INTO personal(nombre, apellidos, puesto, activo, sucursal_id) VALUES(?,?,?,?,?)",
        ("Luis", "Baja", "Cajero", 0, 1),
    )
    conn.execute(
        "INSERT INTO usuarios(nombre, usuario, password_hash, rol, sucursal_id) VALUES(?,?,?,?,?)",
        ("rosa", "rosa", "x", "ventas", 2),
    )
    conn.execute(
        "INSERT INTO drivers(nombre, telefono, activo, sucursal_id) VALUES(?,?,?,?)",
        ("Rosa Driver", "555", 1, 2),
    )
    conn.commit()
    return conn


def test_links_user_to_active_employee_and_publishes_employee_event_once():
    conn = _db()
    publisher = FakePublisher()
    service = EmployeeIdentityApplicationService(
        SQLiteEmployeeIdentityRepository(conn), event_publisher=publisher
    )

    assert service.link_user_to_employee(1, 1, operation_id="op-user-1") == 1
    assert conn.execute("SELECT personal_id FROM usuarios WHERE id=1").fetchone()[0] == 1
    assert len(publisher.payloads) == 1
    payload = publisher.payloads[0].to_dict()
    assert payload["event_type"] == EMPLEADO_ACTUALIZADO
    assert payload["operation_id"] == "op-user-1"
    assert payload["employee_id"] == 1
    assert payload["changes"] == {"usuario_id": 1, "identity_link": "usuario"}

    assert service.link_user_to_employee(1, 1, operation_id="op-user-1-repeat") == 1
    assert len(publisher.payloads) == 1


def test_links_driver_to_active_employee_and_publishes_driver_event_once():
    conn = _db()
    publisher = FakePublisher()
    service = EmployeeIdentityApplicationService(
        SQLiteEmployeeIdentityRepository(conn), event_publisher=publisher
    )

    assert service.link_driver_to_employee(1, 1, operation_id="op-driver-1") == 1
    row = conn.execute("SELECT personal_id, source_module FROM drivers WHERE id=1").fetchone()
    assert dict(row) == {"personal_id": 1, "source_module": "rrhh"}
    assert len(publisher.payloads) == 1
    payload = publisher.payloads[0].to_dict()
    assert payload["event_type"] == REPARTIDOR_ASIGNADO
    assert payload["operation_id"] == "op-driver-1"
    assert payload["driver_id"] == 1
    assert payload["employee_id"] == 1

    assert service.link_driver_to_employee(1, 1, operation_id="op-driver-1-repeat") == 1
    assert len(publisher.payloads) == 1


def test_rejects_inactive_employee_identity_links_without_writing():
    conn = _db()
    publisher = FakePublisher()
    service = EmployeeIdentityApplicationService(
        SQLiteEmployeeIdentityRepository(conn), event_publisher=publisher
    )

    with pytest.raises(ValueError, match="Empleado inactivo"):
        service.link_user_to_employee(1, 2, operation_id="op-inactive-user")
    with pytest.raises(ValueError, match="Empleado inactivo"):
        service.link_driver_to_employee(1, 2, operation_id="op-inactive-driver")

    assert conn.execute("SELECT personal_id FROM usuarios WHERE id=1").fetchone()[0] is None
    assert conn.execute("SELECT personal_id FROM drivers WHERE id=1").fetchone()[0] is None
    assert publisher.payloads == []


def test_rejects_reassigning_identity_to_different_employee():
    conn = _db()
    conn.execute(
        "INSERT INTO personal(nombre, apellidos, puesto, activo, sucursal_id) VALUES(?,?,?,?,?)",
        ("Mario", "Activo", "Auxiliar", 1, 1),
    )
    conn.commit()
    service = EmployeeIdentityApplicationService(SQLiteEmployeeIdentityRepository(conn))

    service.link_user_to_employee(1, 1, operation_id="op-user-original")
    service.link_driver_to_employee(1, 1, operation_id="op-driver-original")

    with pytest.raises(ValueError, match="usuario 1 ya está vinculado"):
        service.link_user_to_employee(1, 3, operation_id="op-user-conflict")
    with pytest.raises(ValueError, match="repartidor 1 ya está vinculado"):
        service.link_driver_to_employee(1, 3, operation_id="op-driver-conflict")


def test_rejects_duplicate_user_or_driver_for_same_employee():
    conn = _db()
    conn.execute(
        "INSERT INTO usuarios(nombre, usuario, password_hash, rol, sucursal_id) VALUES(?,?,?,?,?)",
        ("rosa2", "rosa2", "x", "ventas", 2),
    )
    conn.execute(
        "INSERT INTO drivers(nombre, telefono, activo, sucursal_id) VALUES(?,?,?,?)",
        ("Rosa Driver 2", "556", 1, 2),
    )
    conn.commit()
    service = EmployeeIdentityApplicationService(SQLiteEmployeeIdentityRepository(conn))

    service.link_user_to_employee(1, 1, operation_id="op-user-original")
    service.link_driver_to_employee(1, 1, operation_id="op-driver-original")

    with pytest.raises(ValueError, match="empleado 1 ya está vinculado al usuario 1"):
        service.link_user_to_employee(2, 1, operation_id="op-user-duplicate")
    with pytest.raises(ValueError, match="empleado 1 ya está vinculado al repartidor 1"):
        service.link_driver_to_employee(2, 1, operation_id="op-driver-duplicate")


def test_migration_095_adds_nullable_identity_links_idempotently():
    conn = _db(with_identity_columns=False)
    migration = importlib.import_module("migrations.standalone.095_rrhh_identity_links")

    migration.run(conn)
    migration.run(conn)

    user_columns = {row[1] for row in conn.execute("PRAGMA table_info(usuarios)")}
    driver_columns = {row[1] for row in conn.execute("PRAGMA table_info(drivers)")}
    indexes = {row[1] for row in conn.execute("PRAGMA index_list(usuarios)")}
    driver_indexes = {row[1] for row in conn.execute("PRAGMA index_list(drivers)")}

    assert "personal_id" in user_columns
    assert {"personal_id", "source_module"}.issubset(driver_columns)
    assert "idx_usuarios_personal_id" in indexes
    assert "idx_drivers_personal_id" in driver_indexes
