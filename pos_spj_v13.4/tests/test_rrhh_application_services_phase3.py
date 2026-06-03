import sqlite3
from datetime import datetime, date

import pytest

from core.rrhh.application import (
    AttendanceApplicationService,
    EmployeeApplicationService,
    LeaveApplicationService,
    ShiftApplicationService,
)
from core.rrhh.domain import (
    AttendanceHoursPolicy,
    EmployeeEligibilityPolicy,
    PayrollPeriodPolicy,
    RestDayPolicy,
)
from core.rrhh.infrastructure import (
    SQLiteAttendanceRepository,
    SQLiteEmployeeRepository,
    SQLiteLeaveRepository,
    SQLiteShiftRepository,
)


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
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
        CREATE TABLE asistencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            personal_id INTEGER NOT NULL,
            fecha DATE NOT NULL,
            hora_entrada TEXT,
            hora_salida TEXT,
            horas_trabajadas REAL,
            estado TEXT DEFAULT 'PRESENTE',
            observaciones TEXT
        );
        CREATE TABLE vacaciones_personal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            personal_id INTEGER NOT NULL,
            tipo TEXT DEFAULT 'vacaciones',
            fecha_inicio DATE NOT NULL,
            fecha_fin DATE NOT NULL,
            dias INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'aprobado',
            notas TEXT,
            fecha_registro DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE turno_roles(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            hora_inicio TEXT DEFAULT '08:00',
            hora_fin TEXT DEFAULT '16:00',
            descripcion TEXT,
            color TEXT DEFAULT '#3498db',
            activo INTEGER DEFAULT 1
        );
        CREATE TABLE turno_asignaciones(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            personal_id INTEGER NOT NULL,
            turno_rol_id INTEGER NOT NULL,
            fecha_inicio DATE NOT NULL,
            fecha_fin DATE,
            dia_descanso TEXT DEFAULT 'Domingo',
            rotacion_dias INTEGER DEFAULT 7,
            notif_semana INTEGER DEFAULT 1,
            notif_dia INTEGER DEFAULT 1,
            activo INTEGER DEFAULT 1,
            notas TEXT
        );
        """
    )
    return conn


def test_employee_application_service_wraps_legacy_employee_repository():
    conn = _db()
    service = EmployeeApplicationService(SQLiteEmployeeRepository(conn))

    employee_id = service.save_employee(
        {
            "nombre": "Ana",
            "apellidos": "Lopez",
            "puesto": "Cajero",
            "salario": 500,
            "fecha_ingreso": "2026-01-01",
            "telefono": "+5215555555555",
        }
    )
    service.save_employee({"nombre": "Ana Maria", "apellidos": "Lopez"}, employee_id)

    employee = service.get_employee(employee_id)
    assert employee.nombre_completo == "Ana Maria Lopez"
    assert service.list_employee_lookup()[0].id == employee_id

    assert service.is_payroll_eligible(employee_id) is True
    assert service.list_payroll_eligible_employees()[0].id == employee_id

    service.deactivate_employee(employee_id)
    assert service.list_active_employees() == []
    assert service.is_payroll_eligible(employee_id) is False


def test_attendance_application_service_preserves_check_in_out_behavior():
    conn = _db()
    employee_id = EmployeeApplicationService(SQLiteEmployeeRepository(conn)).save_employee({"nombre": "Luis"})
    service = AttendanceApplicationService(SQLiteAttendanceRepository(conn))

    check_in = service.register_check_in_out(employee_id, "2026-06-02", "08:00")
    assert check_in.ok is True
    assert check_in.action == "check_in"
    assert check_in.message == "✅ Entrada registrada: 08:00"

    check_out = service.register_check_in_out(employee_id, "2026-06-02", "16:30")
    assert check_out.ok is True
    assert check_out.action == "check_out"
    assert check_out.hours == 8.5
    assert check_out.message == "✅ Salida registrada: 16:30 (8.5h)"

    complete = service.register_check_in_out(employee_id, "2026-06-02", "17:00")
    assert complete.ok is False
    assert complete.action == "complete"


def test_leave_application_service_creates_rows_and_exposes_overlap_query():
    conn = _db()
    employee_id = EmployeeApplicationService(SQLiteEmployeeRepository(conn)).save_employee({"nombre": "Marta"})
    service = LeaveApplicationService(SQLiteLeaveRepository(conn))

    leave_id = service.create_leave(
        employee_id=employee_id,
        leave_type="vacaciones",
        date_from="2026-06-10",
        date_to="2026-06-15",
        days=6,
        status="aprobado",
    )

    assert service.list_leave_table_rows()[0][0] == leave_id
    assert [item.id for item in service.find_overlaps(employee_id, "2026-06-14", "2026-06-20")] == [leave_id]

    with pytest.raises(ValueError, match="se solapa"):
        service.create_leave(
            employee_id=employee_id,
            leave_type="permiso",
            date_from="2026-06-14",
            date_to="2026-06-16",
            days=3,
            status="pendiente",
        )


def test_shift_application_service_wraps_roles_and_assignments():
    conn = _db()
    employee_id = EmployeeApplicationService(SQLiteEmployeeRepository(conn)).save_employee({"nombre": "Rosa"})
    service = ShiftApplicationService(SQLiteShiftRepository(conn))

    role_id = service.save_role({"nombre": "Mañana", "hora_inicio": "07:00", "hora_fin": "15:00"})
    assignment_id = service.save_assignment(
        {
            "personal_id": employee_id,
            "turno_rol_id": role_id,
            "fecha_inicio": "2026-06-01",
            "fecha_fin": "2026-09-01",
        }
    )

    assert service.list_roles()[0].id == role_id
    assert service.list_assignments()[0].id == assignment_id

    service.deactivate_assignment(assignment_id)
    service.deactivate_role(role_id)
    assert service.list_assignments() == []
    assert service.list_roles() == []


def test_phase4_domain_policies_are_framework_free_and_deterministic():
    assert AttendanceHoursPolicy().rounded_worked_hours("08:00", "16:30") == 8.5

    start, end = PayrollPeriodPolicy(period_days=7).current_period_strings(
        datetime(2026, 6, 3, 12, 0)
    )
    assert (start, end) == ("2026-05-27", "2026-06-03")

    assert EmployeeEligibilityPolicy().is_active(type("Emp", (), {"activo": True})()) is True
    assert EmployeeEligibilityPolicy().is_active(type("Emp", (), {"activo": False})()) is False

    rest_policy = RestDayPolicy(max_consecutive_days=6, min_coverage=1)
    assert rest_policy.requires_rest(6) is True
    assert rest_policy.requires_rest(5) is False
    assert rest_policy.default_rest_date(date(2026, 6, 3)).isoformat() == "2026-06-04"
    assert rest_policy.can_schedule_rest(resting_count=1, total_employees=3) is True
    assert rest_policy.has_minimum_coverage(active_count=2, resting_today=1) is True


class _FakeEventPublisher:
    def __init__(self):
        self.events = []

    def publish(self, payload, *, async_=False):
        self.events.append((payload.event_type, payload.to_dict(), async_))


def test_phase5_employee_service_publishes_validated_canonical_events():
    from core.rrhh.events import EMPLEADO_CREADO, EMPLEADO_DESACTIVADO

    conn = _db()
    publisher = _FakeEventPublisher()
    service = EmployeeApplicationService(
        SQLiteEmployeeRepository(conn), event_publisher=publisher
    )

    employee_id = service.save_employee(
        {"nombre": "Eva", "puesto": "Cajero"}, operation_id="op-emp-create"
    )
    service.deactivate_employee(employee_id, reason="renuncia", operation_id="op-emp-off")

    assert publisher.events[0][0] == EMPLEADO_CREADO
    assert publisher.events[0][1]["operation_id"] == "op-emp-create"
    assert publisher.events[0][1]["employee_id"] == employee_id
    assert publisher.events[1][0] == EMPLEADO_DESACTIVADO
    assert publisher.events[1][1]["operation_id"] == "op-emp-off"
    assert publisher.events[1][1]["reason"] == "renuncia"


def test_phase5_attendance_service_publishes_event_from_application_layer():
    from core.rrhh.events import ASISTENCIA_REGISTRADA

    conn = _db()
    employee_id = EmployeeApplicationService(SQLiteEmployeeRepository(conn)).save_employee({"nombre": "Luis"})
    publisher = _FakeEventPublisher()
    service = AttendanceApplicationService(
        SQLiteAttendanceRepository(conn), event_publisher=publisher
    )

    service.register_check_in_out(employee_id, "2026-06-02", "08:00", operation_id="op-in")
    service.register_check_in_out(employee_id, "2026-06-02", "16:00", operation_id="op-out")

    assert [event[0] for event in publisher.events] == [ASISTENCIA_REGISTRADA, ASISTENCIA_REGISTRADA]
    assert publisher.events[0][1]["operation_id"] == "op-in"
    assert publisher.events[0][1]["tipo"] == "check_in"
    assert publisher.events[1][1]["operation_id"] == "op-out"
    assert publisher.events[1][1]["tipo"] == "check_out"
    assert publisher.events[1][1]["hours"] == 8.0


def test_phase5_leave_service_publishes_status_specific_events_and_requires_operation_id():
    from core.rrhh.events import LeaveEventPayload, PERMISO_APROBADO, VACACIONES_APROBADAS

    conn = _db()
    employee_id = EmployeeApplicationService(SQLiteEmployeeRepository(conn)).save_employee({"nombre": "Marta"})
    publisher = _FakeEventPublisher()
    service = LeaveApplicationService(SQLiteLeaveRepository(conn), event_publisher=publisher)

    service.create_leave(
        employee_id=employee_id,
        leave_type="vacaciones",
        date_from="2026-06-10",
        date_to="2026-06-15",
        days=6,
        status="aprobado",
        operation_id="op-vac",
    )
    service.create_leave(
        employee_id=employee_id,
        leave_type="permiso",
        date_from="2026-06-20",
        date_to="2026-06-20",
        days=1,
        status="aprobado",
        operation_id="op-perm",
    )

    assert publisher.events[0][0] == VACACIONES_APROBADAS
    assert publisher.events[0][1]["operation_id"] == "op-vac"
    assert publisher.events[1][0] == PERMISO_APROBADO
    assert publisher.events[1][1]["operation_id"] == "op-perm"
    with pytest.raises(ValueError, match="operation_id"):
        LeaveEventPayload(
            operation_id="",
            request_id=1,
            employee_id=employee_id,
            tipo="vacaciones",
            date_start="2026-07-01",
            date_end="2026-07-02",
            days=2,
            status="pendiente",
        )
