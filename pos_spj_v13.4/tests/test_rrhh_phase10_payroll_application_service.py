import sqlite3

from core.rrhh.application import PayrollApplicationService, PayrollPaymentCommand
from core.rrhh.events import NOMINA_GENERADA, NOMINA_PAGADA
from core.rrhh.infrastructure import SQLiteEmployeeRepository, SQLitePayrollRepository


class FakePublisher:
    def __init__(self):
        self.payloads = []

    def publish(self, payload):
        self.payloads.append(payload.to_dict())


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE personal (
            id TEXT PRIMARY KEY,
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
        CREATE TABLE nomina_pagos (
            id TEXT PRIMARY KEY,
            empleado_id TEXT,
            periodo_inicio TEXT,
            periodo_fin TEXT,
            salario_base REAL DEFAULT 0,
            bonos REAL DEFAULT 0,
            deducciones REAL DEFAULT 0,
            total REAL,
            metodo_pago TEXT,
            estado TEXT,
            usuario TEXT,
            fecha DATETIME DEFAULT (datetime('now')),
            operation_id TEXT UNIQUE,
            source_module TEXT,
            source_id INTEGER
        );
        """
    )
    conn.execute(
        """
        INSERT INTO personal(id, nombre, apellidos, puesto, salario, activo, sucursal_id)
        VALUES(?,?,?,?,?,?,?)
        """,
        ("1", "Ana", "Nomina", "Cajero", 1200, 1, 1),
    )
    conn.execute(
        """
        INSERT INTO personal(id, nombre, apellidos, puesto, salario, activo, sucursal_id)
        VALUES(?,?,?,?,?,?,?)
        """,
        ("2", "Luis", "Inactivo", "Auxiliar", 1000, 0, 1),
    )
    conn.commit()
    return conn


def _service(conn, publisher=None):
    return PayrollApplicationService(
        SQLitePayrollRepository(conn),
        SQLiteEmployeeRepository(conn),
        event_publisher=publisher or FakePublisher(),
    )


def test_payroll_application_service_creates_traceable_payment_and_events():
    conn = _db()
    publisher = FakePublisher()
    service = _service(conn, publisher)

    result = service.pay_payroll(
        PayrollPaymentCommand(
            employee_id=1,
            period_start="2026-05-01",
            period_end="2026-05-07",
            salario_base=1200,
            bonos=100,
            deducciones=50,
            total=1250,
            neto=1250,
            metodo_pago="transferencia",
            sucursal_id=1,
            usuario="admin",
            operation_id="op-payroll-10",
            source_id=77,
        )
    )

    assert result.ok is True
    assert result.created is True
    assert result.payroll_payment_id  # UUIDv7
    row = conn.execute(
        """
        SELECT empleado_id, total, operation_id, source_module, source_id
        FROM nomina_pagos WHERE id=?
        """,
        (result.payroll_payment_id,),
    ).fetchone()
    assert dict(row) == {
        "empleado_id": "1",
        "total": 1250.0,
        "operation_id": "op-payroll-10",
        "source_module": "rrhh",
        "source_id": 77,
    }
    assert [p["event_type"] for p in publisher.payloads] == [NOMINA_GENERADA, NOMINA_PAGADA]
    assert all(p["operation_id"] == "op-payroll-10" for p in publisher.payloads)
    assert publisher.payloads[1]["payroll_payment_id"] == result.payroll_payment_id


def test_payroll_application_service_is_idempotent_by_operation_id():
    conn = _db()
    publisher = FakePublisher()
    service = _service(conn, publisher)
    command = PayrollPaymentCommand(
        employee_id=1,
        period_start="2026-05-01",
        period_end="2026-05-07",
        total=900,
        sucursal_id=1,
        operation_id="op-payroll-idempotent",
    )

    first = service.pay_payroll(command)
    second = service.pay_payroll(command)

    assert first.ok is True
    assert second.ok is True
    assert first.payroll_payment_id == second.payroll_payment_id
    assert first.created is True
    assert second.created is False
    assert conn.execute("SELECT COUNT(*) FROM nomina_pagos").fetchone()[0] == 1
    assert [p["event_type"] for p in publisher.payloads] == [NOMINA_GENERADA, NOMINA_PAGADA]


def test_payroll_application_service_rejects_inactive_employee_without_payment():
    conn = _db()
    publisher = FakePublisher()
    service = _service(conn, publisher)

    result = service.pay_payroll(
        PayrollPaymentCommand(
            employee_id=2,
            period_start="2026-05-01",
            period_end="2026-05-07",
            total=900,
            sucursal_id=1,
            operation_id="op-payroll-inactive",
        )
    )

    assert result.ok is False
    assert "Empleado no elegible" in result.error
    assert conn.execute("SELECT COUNT(*) FROM nomina_pagos").fetchone()[0] == 0
    assert publisher.payloads == []
