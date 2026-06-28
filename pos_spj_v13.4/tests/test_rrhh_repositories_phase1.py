import sqlite3

from core.rrhh.infrastructure import (
    SQLiteAttendanceRepository,
    SQLiteEmployeeRepository,
    SQLiteLeaveRepository,
    SQLitePayrollRepository,
    SQLiteShiftRepository,
)


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
        CREATE TABLE asistencias (
            id TEXT PRIMARY KEY,
            personal_id TEXT NOT NULL,
            fecha DATE NOT NULL,
            hora_entrada TEXT,
            hora_salida TEXT,
            horas_trabajadas REAL,
            estado TEXT DEFAULT 'PRESENTE',
            observaciones TEXT
        );
        CREATE TABLE vacaciones_personal (
            id TEXT PRIMARY KEY,
            personal_id TEXT NOT NULL,
            tipo TEXT DEFAULT 'vacaciones',
            fecha_inicio DATE NOT NULL,
            fecha_fin DATE NOT NULL,
            dias INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'aprobado',
            notas TEXT,
            fecha_registro DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE nomina_pagos (
            id TEXT PRIMARY KEY,
            empleado_id TEXT NOT NULL,
            periodo_inicio DATE NOT NULL,
            periodo_fin DATE NOT NULL,
            salario_base REAL NOT NULL DEFAULT 0,
            bonos REAL DEFAULT 0,
            deducciones REAL DEFAULT 0,
            total REAL NOT NULL DEFAULT 0,
            metodo_pago TEXT DEFAULT 'efectivo',
            estado TEXT DEFAULT 'pagado',
            usuario TEXT,
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE turno_roles(
            id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL UNIQUE,
            hora_inicio TEXT DEFAULT '08:00',
            hora_fin TEXT DEFAULT '16:00',
            descripcion TEXT,
            color TEXT DEFAULT '#3498db',
            activo INTEGER DEFAULT 1
        );
        CREATE TABLE turno_asignaciones(
            id TEXT PRIMARY KEY,
            personal_id TEXT NOT NULL,
            turno_rol_id TEXT NOT NULL,
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


def test_employee_repository_matches_legacy_active_employee_behavior():
    conn = _db()
    repo = SQLiteEmployeeRepository(conn)

    emp_id = repo.create(
        {
            "nombre": "Ana",
            "apellidos": "Lopez",
            "puesto": "Cajero",
            "salario": 500,
            "fecha_ingreso": "2026-01-01",
            "telefono": "+5215555555555",
        }
    )
    conn.execute("INSERT INTO personal(nombre, activo) VALUES('Inactivo', 0)")
    conn.commit()

    active = repo.list_active()
    assert [e.id for e in active] == [emp_id]
    assert active[0].nombre_completo == "Ana Lopez"
    assert repo.list_active(search="cajero")[0].id == emp_id

    repo.deactivate(emp_id)
    assert repo.list_active() == []


def test_attendance_repository_keeps_check_in_and_check_out_sql_shape():
    conn = _db()
    emp_id = SQLiteEmployeeRepository(conn).create({"nombre": "Luis"})
    repo = SQLiteAttendanceRepository(conn)

    attendance_id = repo.register_check_in(emp_id, "2026-06-02", "08:00")
    row = repo.get_for_date(emp_id, "2026-06-02")
    assert row.id == attendance_id
    assert row.estado == "PRESENTE"
    assert row.hora_entrada == "08:00"

    repo.register_check_out(attendance_id, "16:30", 8.5)
    row = repo.get_for_date(emp_id, "2026-06-02")
    assert row.hora_salida == "16:30"
    assert row.horas_trabajadas == 8.5
    assert repo.list_between_for_table("2026-06-01", "2026-06-03") == [
        ("Luis ", "2026-06-02", "08:00", "16:30", 8.5, "PRESENTE")
    ]


def test_leave_repository_can_find_legacy_date_overlaps_without_writing_schema():
    conn = _db()
    emp_id = SQLiteEmployeeRepository(conn).create({"nombre": "Marta"})
    repo = SQLiteLeaveRepository(conn)

    leave_id = repo.create(
        {
            "personal_id": emp_id,
            "tipo": "vacaciones",
            "fecha_inicio": "2026-06-10",
            "fecha_fin": "2026-06-15",
            "dias": 6,
            "estado": "aprobado",
        }
    )

    table_rows = repo.list_recent_for_table()
    assert table_rows[0][:7] == (
        leave_id,
        "Marta ",
        "vacaciones",
        "2026-06-10",
        "2026-06-15",
        6,
        "aprobado",
    )

    overlaps = repo.find_overlaps(emp_id, "2026-06-14", "2026-06-20")
    assert [item.id for item in overlaps] == [leave_id]
    assert repo.find_overlaps(emp_id, "2026-06-16", "2026-06-20") == []


def test_payroll_repository_creates_and_sums_paid_payments_only():
    conn = _db()
    emp_id = SQLiteEmployeeRepository(conn).create({"nombre": "Pedro"})
    repo = SQLitePayrollRepository(conn)

    payment_id = repo.create_payment(
        {
            "empleado_id": emp_id,
            "periodo_inicio": "2026-05-25",
            "periodo_fin": "2026-06-01",
            "salario_base": 1000,
            "bonos": 50,
            "deducciones": 25,
            "total": 1025,
            "metodo_pago": "Transferencia",
            "estado": "pagado",
            "usuario": "admin",
        }
    )
    repo.create_payment(
        {
            "empleado_id": emp_id,
            "periodo_inicio": "2026-05-25",
            "periodo_fin": "2026-06-01",
            "salario_base": 1000,
            "total": 1000,
            "estado": "cancelado",
        }
    )

    payment = repo.get_payment(payment_id)
    assert payment.total == 1025
    assert payment.metodo_pago == "Transferencia"
    assert repo.get_latest_payment_for_employee(emp_id).id == payment_id
    payment_date = conn.execute(
        "SELECT date(fecha) FROM nomina_pagos WHERE id=?", (payment_id,)
    ).fetchone()[0]
    assert repo.sum_paid_between(payment_date, payment_date) == 1025


def test_shift_repository_covers_roles_and_assignments_without_ui_dependency():
    conn = _db()
    emp_id = SQLiteEmployeeRepository(conn).create({"nombre": "Rosa"})
    repo = SQLiteShiftRepository(conn)

    role_id = repo.create_role(
        {
            "nombre": "Mañana",
            "hora_inicio": "07:00",
            "hora_fin": "15:00",
            "descripcion": "Apertura",
            "color": "#00aa00",
        }
    )
    assignment_id = repo.create_assignment(
        {
            "personal_id": emp_id,
            "turno_rol_id": role_id,
            "fecha_inicio": "2026-06-01",
            "fecha_fin": "2026-09-01",
            "dia_descanso": "Domingo",
        }
    )

    assert repo.list_roles()[0].nombre == "Mañana"
    assert repo.list_assignments()[0].id == assignment_id

    repo.deactivate_role(role_id)
    repo.deactivate_assignment(assignment_id)
    assert repo.list_roles() == []
    assert repo.list_assignments() == []
