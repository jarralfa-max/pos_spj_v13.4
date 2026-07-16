"""FASE 7.7 (caja) — CashRegister application layer.

The use cases (OpenCashShift / RegisterCashMovement / GenerateZCut) delegate to
CashRegisterApplicationService, which orchestrates the existing FinanceService
turno logic and emits the canonical CASH_* events. Identity is UUIDv7
(turno_id from abrir_turno) and operation_id != entity_id (rule 41).
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import date
from decimal import Decimal

import pytest

from core.services.enterprise.finance_service import FinanceService
from backend.domain.hr.entities import Department, Employee, Position
from backend.domain.hr.enums import ContractType, PaymentFrequency
from backend.infrastructure.db.repositories.department_repository import SQLiteDepartmentRepository
from backend.infrastructure.db.repositories.employee_repository import SQLiteEmployeeRepository
from backend.infrastructure.db.repositories.position_repository import SQLitePositionRepository
from backend.infrastructure.db.schema.hr_schema import create_hr_schema
from backend.application.services.cash_register_application_service import (
    CashRegisterApplicationService,
)
from backend.application.use_cases.open_cash_shift_use_case import OpenCashShiftUseCase
from backend.application.use_cases.register_cash_movement_use_case import (
    RegisterCashMovementUseCase,
)
from backend.application.use_cases.generate_z_cut_use_case import GenerateZCutUseCase
from backend.application.commands.cash_register_commands import (
    OpenCashShiftCommand,
    RegisterCashMovementCommand,
    GenerateZCutCommand,
)


@pytest.fixture
def ctx():
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
            id INTEGER PRIMARY KEY, sucursal_id TEXT, usuario TEXT, total REAL,
            estado TEXT DEFAULT 'completada', forma_pago TEXT DEFAULT 'Efectivo',
            fecha DATETIME DEFAULT (datetime('now'))
        );
<<<<<<< HEAD
        CREATE TABLE cierres_caja (
            id TEXT PRIMARY KEY, tipo TEXT, sucursal_id TEXT, usuario TEXT,
            turno TEXT, turno_id TEXT, fecha_apertura DATETIME,
            fecha_cierre DATETIME, total_ventas REAL, num_ventas INTEGER,
            total_efectivo REAL, total_tarjeta REAL, total_transferencia REAL,
            total_otros REAL, total_anulaciones REAL, num_anulaciones INTEGER,
            efectivo_contado REAL, fondo_inicial REAL, diferencia REAL,
            comentarios TEXT, estado TEXT
=======
        CREATE TABLE usuarios (
            id TEXT PRIMARY KEY, nombre TEXT, usuario TEXT, password_hash TEXT,
            rol TEXT, sucursal_id TEXT, employee_id TEXT, activo INTEGER
>>>>>>> 5f7df5247ec66f7297adb53c0d2e32ee56e33c23
        );
        """
    )
    branch = str(uuid.uuid4())
    department = Department(name="Operaciones", branch_id=branch)
    position = Position(name="Caja", department_id=department.id)
    employee = Employee(
        employee_code="EMP-CASH", first_name="Ana", last_name="Caja",
        branch_id=branch, department_id=department.id, position_id=position.id,
        contract_type=ContractType.FULL_TIME, payment_frequency=PaymentFrequency.WEEKLY,
        base_salary=Decimal("1000"), daily_salary=Decimal("200"), hire_date=date(2026, 1, 1),
    )
    SQLiteDepartmentRepository(conn).save(department)
    SQLitePositionRepository(conn).save(position)
    SQLiteEmployeeRepository(conn).save(employee)
    user_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id, employee_id, activo) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
        (user_id, "Ana Caja", "ana", "hash", "cajero", branch, employee.id),
    )
    conn.commit()
    events = []
    svc = CashRegisterApplicationService(
        FinanceService(conn), publisher=lambda evt, payload: events.append((evt, payload))
    )
    return svc, events, branch, user_id, employee.id


def _cmd(cls, branch, user_id, employee_id, **kw):
    payload = {"operation_id": str(uuid.uuid4()), "branch_id": branch, "user_id": user_id, "user_name": "ana", **kw}
    if cls is OpenCashShiftCommand:
        payload["employee_id"] = employee_id
    return cls(**payload)


def test_open_shift_returns_uuid_and_emits_event(ctx):
    svc, events, branch, user_id, employee_id = ctx
    uc = OpenCashShiftUseCase(handler=svc.open_shift)
    res = uc.execute(_cmd(OpenCashShiftCommand, branch, user_id, employee_id, opening_amount=500.0))
    assert res.success and uuid.UUID(res.entity_id)        # turno_id is UUIDv7
    assert res.entity_id != res.operation_id               # rule 41
    assert any(e[0] == "CASH_SHIFT_OPENED" for e in events)


def test_register_movement_emits_event(ctx):
    svc, events, branch, user_id, employee_id = ctx
    OpenCashShiftUseCase(handler=svc.open_shift).execute(
        _cmd(OpenCashShiftCommand, branch, user_id, employee_id, opening_amount=500.0)
    )
    uc = RegisterCashMovementUseCase(handler=svc.register_movement)
    res = uc.execute(_cmd(RegisterCashMovementCommand, branch, user_id, employee_id,
                          movement_type="RETIRO", amount=100.0, concept="pago proveedor"))
    assert res.success
    assert any(e[0] == "CASH_MOVEMENT_RECORDED" for e in events)
    row = svc._fin.db.execute("SELECT turno_id FROM movimientos_caja").fetchone()
    assert uuid.UUID(row["turno_id"])  # FK is the shift UUID


def test_z_cut_emits_cut_and_difference_when_unbalanced(ctx):
    svc, events, branch, user_id, employee_id = ctx
    OpenCashShiftUseCase(handler=svc.open_shift).execute(
        _cmd(OpenCashShiftCommand, branch, user_id, employee_id, opening_amount=100.0)
    )
    uc = GenerateZCutUseCase(handler=svc.generate_z_cut)
    # counted 50 vs expected 100 (fondo) -> difference -50
    res = uc.execute(_cmd(GenerateZCutCommand, branch, user_id, employee_id, payload={"efectivo_fisico": 50.0}))
    assert res.success
    kinds = {e[0] for e in events}
    assert "CASH_Z_CUT_GENERATED" in kinds
    assert "CASH_DIFFERENCE_DETECTED" in kinds


def test_z_cut_no_difference_event_when_balanced(ctx):
    svc, events, branch, user_id, employee_id = ctx
    OpenCashShiftUseCase(handler=svc.open_shift).execute(
        _cmd(OpenCashShiftCommand, branch, user_id, employee_id, opening_amount=100.0)
    )
    GenerateZCutUseCase(handler=svc.generate_z_cut).execute(
        _cmd(GenerateZCutCommand, branch, user_id, employee_id, payload={"efectivo_fisico": 100.0})
    )
    kinds = {e[0] for e in events}
    assert "CASH_Z_CUT_GENERATED" in kinds
    assert "CASH_DIFFERENCE_DETECTED" not in kinds
