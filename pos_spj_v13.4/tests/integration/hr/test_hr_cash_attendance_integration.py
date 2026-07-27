from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from backend.application.commands.cash_register_commands import CloseCashShiftCommand, OpenCashShiftCommand
from backend.application.event_handlers.hr.cash_shift_closed_attendance_handler import CashShiftClosedAttendanceHandler
from backend.application.event_handlers.hr.cash_shift_opened_attendance_handler import CashShiftOpenedAttendanceHandler
from backend.application.services.cash_register_application_service import CashRegisterApplicationService
from backend.application.use_cases.close_cash_shift_use_case import CloseCashShiftUseCase
from backend.application.use_cases.hr.register_attendance_punch_use_case import RegisterAttendancePunchUseCase
from backend.application.use_cases.hr.register_manual_attendance_use_case import RegisterManualAttendanceUseCase
from backend.application.use_cases.open_cash_shift_use_case import OpenCashShiftUseCase
from backend.application.commands.attendance_commands import RegisterManualAttendanceCommand
from backend.domain.hr.entities import Department, Employee, Position
from backend.domain.hr.enums import ContractType, PaymentFrequency, PunchType
from backend.domain.hr.exceptions import UserEmployeeLinkRequiredError
from backend.infrastructure.db.repositories.attendance_repository import SQLiteAttendanceRepository
from backend.infrastructure.db.repositories.department_repository import SQLiteDepartmentRepository
from backend.infrastructure.db.repositories.employee_repository import SQLiteEmployeeRepository
from backend.infrastructure.db.repositories.position_repository import SQLitePositionRepository
from backend.infrastructure.db.schema.hr_schema import create_hr_schema
from core.services.enterprise.finance_service import FinanceService


BRANCH_ID = "01900000-0000-7000-8000-000000000001"
USER_ID = "01900000-0000-7000-8000-00000000c501"


def _setup() -> tuple[sqlite3.Connection, Employee, list[tuple[str, dict]]]:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_hr_schema(conn)
    conn.executescript(
        """
        CREATE TABLE turnos_caja (
            id TEXT PRIMARY KEY, sucursal_id TEXT, usuario TEXT, cajero TEXT,
            fondo_inicial REAL DEFAULT 0, total_ventas REAL DEFAULT 0,
            efectivo_esperado REAL DEFAULT 0, efectivo_contado REAL DEFAULT 0,
            diferencia REAL DEFAULT 0, estado TEXT DEFAULT 'abierto',
            fecha_apertura DATETIME DEFAULT (datetime('now')), fecha_cierre DATETIME
        );
        CREATE TABLE movimientos_caja (
            id TEXT PRIMARY KEY, turno_id TEXT, sucursal_id TEXT, tipo TEXT,
            monto REAL, concepto TEXT, usuario TEXT, fecha DATETIME
        );
        CREATE TABLE ventas (
            id TEXT PRIMARY KEY, sucursal_id TEXT, usuario TEXT, total REAL,
            estado TEXT DEFAULT 'completada', forma_pago TEXT DEFAULT 'Efectivo',
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE cierres_caja (
            id TEXT PRIMARY KEY, tipo TEXT, sucursal_id TEXT, usuario TEXT, turno TEXT,
            fecha_apertura TEXT, total_ventas REAL, num_ventas INTEGER,
            total_efectivo REAL, total_tarjeta REAL, total_transferencia REAL,
            total_otros REAL, total_anulaciones REAL, num_anulaciones INTEGER,
            efectivo_contado REAL, fondo_inicial REAL, diferencia REAL,
            comentarios TEXT, estado TEXT, turno_id TEXT
        );
        CREATE TABLE usuarios (
            id TEXT PRIMARY KEY, nombre TEXT, usuario TEXT, password_hash TEXT,
            rol TEXT, sucursal_id TEXT, employee_id TEXT, activo INTEGER
        );
        """
    )
    department = Department(name="Operaciones", branch_id=BRANCH_ID)
    position = Position(name="Cajera", department_id=department.id)
    employee = Employee(
        employee_code="EMP-CAJA",
        first_name="Elena",
        last_name="Caja",
        branch_id=BRANCH_ID,
        department_id=department.id,
        position_id=position.id,
        contract_type=ContractType.FULL_TIME,
        payment_frequency=PaymentFrequency.WEEKLY,
        base_salary=Decimal("1500"),
        daily_salary=Decimal("300"),
        hire_date=date(2026, 6, 1),
    )
    SQLiteDepartmentRepository(conn).save(department)
    SQLitePositionRepository(conn).save(position)
    SQLiteEmployeeRepository(conn).save(employee)
    conn.execute(
        "INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id, employee_id, activo) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
        (USER_ID, "Elena Caja", "elena", "hash", "cajero", BRANCH_ID, employee.id),
    )
    events: list[tuple[str, dict]] = []
    return conn, employee, events


def _cash_service(conn: sqlite3.Connection, events: list[tuple[str, dict]]) -> CashRegisterApplicationService:
    attendance_uc = RegisterAttendancePunchUseCase(
        SQLiteAttendanceRepository(conn),
        employee_repository=SQLiteEmployeeRepository(conn),
    )
    opened = CashShiftOpenedAttendanceHandler(attendance_uc)
    closed = CashShiftClosedAttendanceHandler(attendance_uc)

    def publish(event_name: str, payload: dict) -> None:
        events.append((event_name, payload))
        if event_name == "CASH_SHIFT_OPENED":
            opened.handle(payload)
        if event_name == "CASH_SHIFT_CLOSED":
            closed.handle(payload)

    return CashRegisterApplicationService(
        FinanceService(conn),
        publisher=publish,
        permission_checker=lambda _user_id, permission: permission in {"caja.abrir", "caja.cerrar"},
    )


def _open_command(employee: Employee, operation_id: str) -> OpenCashShiftCommand:
    return OpenCashShiftCommand(
        operation_id=operation_id,
        branch_id=BRANCH_ID,
        user_id=USER_ID,
        employee_id=employee.id,
        opening_amount=100.0,
    )


def test_cash_open_registers_attendance_entry() -> None:
    conn, employee, events = _setup()
    service = _cash_service(conn, events)
    result = OpenCashShiftUseCase(handler=service.open_shift).execute(_open_command(employee, "01900000-0000-7000-8000-00000000f501"))

    punches = SQLiteAttendanceRepository(conn).list_punches_for_workday(employee_id=employee.id, branch_id=BRANCH_ID, work_date=date.today())
    assert result.success
    assert [p.punch_type.value for p in punches] == ["ENTRY"]
    assert events[-1][0] == "CASH_SHIFT_OPENED"
    assert events[-1][1]["user_id"] == USER_ID
    assert events[-1][1]["employee_id"] == employee.id


def test_cash_close_registers_attendance_exit() -> None:
    conn, employee, events = _setup()
    service = _cash_service(conn, events)
    open_result = OpenCashShiftUseCase(handler=service.open_shift).execute(_open_command(employee, "01900000-0000-7000-8000-00000000f502"))
    close_result = CloseCashShiftUseCase(handler=service.close_shift).execute(
        CloseCashShiftCommand(
            operation_id="01900000-0000-7000-8000-00000000f503",
            branch_id=BRANCH_ID,
            user_id=USER_ID,
            employee_id=employee.id,
            shift_id=open_result.entity_id,
            counted_cash=100.0,
        )
    )

    punches = SQLiteAttendanceRepository(conn).list_punches_for_workday(employee_id=employee.id, branch_id=BRANCH_ID, work_date=date.today())
    assert close_result.success
    assert [p.punch_type.value for p in punches] == ["ENTRY", "EXIT"]
    assert "CASH_SHIFT_CLOSED" in {event for event, _ in events}


def test_repeated_cash_open_does_not_duplicate_entry() -> None:
    conn, employee, events = _setup()
    service = _cash_service(conn, events)
    OpenCashShiftUseCase(handler=service.open_shift).execute(_open_command(employee, "01900000-0000-7000-8000-00000000f504"))
    repeated = OpenCashShiftUseCase(handler=service.open_shift).execute(_open_command(employee, "01900000-0000-7000-8000-00000000f505"))

    punches = SQLiteAttendanceRepository(conn).list_punches_for_workday(employee_id=employee.id, branch_id=BRANCH_ID, work_date=date.today())
    assert repeated.success
    assert len(punches) == 1


def test_cash_close_without_entry_creates_missing_entry_incident() -> None:
    conn, employee, events = _setup()
    service = _cash_service(conn, events)
    open_result = OpenCashShiftUseCase(handler=service.open_shift).execute(_open_command(employee, "01900000-0000-7000-8000-00000000f506"))
    conn.execute("DELETE FROM attendance_punches")
    CloseCashShiftUseCase(handler=service.close_shift).execute(
        CloseCashShiftCommand(
            operation_id="01900000-0000-7000-8000-00000000f507",
            branch_id=BRANCH_ID,
            user_id=USER_ID,
            employee_id=employee.id,
            shift_id=open_result.entity_id,
            counted_cash=100.0,
        )
    )

    incidents = SQLiteAttendanceRepository(conn).list_incidents(employee_id=employee.id, branch_id=BRANCH_ID, work_date=date.today())
    assert [incident.incident_type.value for incident in incidents] == ["MISSING_ENTRY"]


def test_manual_entry_before_cash_open_is_not_duplicated() -> None:
    conn, employee, events = _setup()
    attendance = SQLiteAttendanceRepository(conn)
    RegisterManualAttendanceUseCase(
        attendance,
        employee_repository=SQLiteEmployeeRepository(conn),
        permission_checker=lambda _user_id, _permission: True,
    ).execute(
        RegisterManualAttendanceCommand(
            operation_id="01900000-0000-7000-8000-00000000f508",
            branch_id=BRANCH_ID,
            user_id=USER_ID,
            employee_id=employee.id,
            punch_type=PunchType.ENTRY,
            occurred_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            reason="Entrada manual previa",
        )
    )
    service = _cash_service(conn, events)
    OpenCashShiftUseCase(handler=service.open_shift).execute(_open_command(employee, "01900000-0000-7000-8000-00000000f509"))

    punches = attendance.list_punches_for_workday(employee_id=employee.id, branch_id=BRANCH_ID, work_date=date.today())
    assert len(punches) == 1


def test_multiple_cash_shifts_same_day_do_not_create_multiple_workdays() -> None:
    conn, employee, events = _setup()
    service = _cash_service(conn, events)
    for suffix in ("10", "11"):
        opened = OpenCashShiftUseCase(handler=service.open_shift).execute(_open_command(employee, f"01900000-0000-7000-8000-00000000f5{suffix}"))
        CloseCashShiftUseCase(handler=service.close_shift).execute(
            CloseCashShiftCommand(
                operation_id=f"01900000-0000-7000-8000-00000000f6{suffix}",
                branch_id=BRANCH_ID,
                user_id=USER_ID,
                employee_id=employee.id,
                shift_id=opened.entity_id,
                counted_cash=100.0,
            )
        )

    count = conn.execute("SELECT COUNT(*) FROM attendance_workdays WHERE employee_id=? AND branch_id=?", (employee.id, BRANCH_ID)).fetchone()[0]
    assert count == 1


def test_cash_open_blocks_user_without_employee_link() -> None:
    conn, employee, events = _setup()
    conn.execute("UPDATE usuarios SET employee_id = NULL WHERE id = ?", (USER_ID,))
    service = _cash_service(conn, events)

    with pytest.raises(UserEmployeeLinkRequiredError):
        OpenCashShiftUseCase(handler=service.open_shift).execute(_open_command(employee, "01900000-0000-7000-8000-00000000f512"))
