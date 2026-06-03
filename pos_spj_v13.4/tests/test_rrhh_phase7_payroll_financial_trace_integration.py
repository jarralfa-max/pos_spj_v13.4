import importlib
import sqlite3
from unittest.mock import MagicMock

from core.events.handlers.finance_handler import PayrollFinanceHandler
from core.services.finance.journal_entry_service import JournalEntryService
from core.services.rrhh_service import RRHHService
from core.use_cases.nomina import GestionarNominaUC, SolicitudNomina
from core.rrhh.events import NOMINA_GENERADA, NOMINA_PAGADA


class ImmediatePayrollBus:
    def __init__(self, handler):
        self.events = []
        self.handler = handler

    def publish(self, event_type, payload, async_=False):
        self.events.append((event_type, payload, async_))
        if event_type == NOMINA_GENERADA:
            self.handler.handle_generated(payload)
        elif event_type == NOMINA_PAGADA:
            self.handler.handle_paid(payload)


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
            telefono TEXT,
            activo INTEGER DEFAULT 1
        );
        CREATE TABLE asistencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            personal_id INTEGER NOT NULL,
            fecha DATE NOT NULL,
            horas_trabajadas REAL,
            estado TEXT DEFAULT 'PRESENTE'
        );
        CREATE TABLE nomina_pagos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado_id INTEGER,
            periodo_inicio TEXT,
            periodo_fin TEXT,
            salario_base REAL,
            total REAL,
            metodo_pago TEXT,
            estado TEXT,
            usuario TEXT
        );
        CREATE TABLE journal_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id TEXT UNIQUE NOT NULL,
            event_type TEXT,
            source_module TEXT,
            source_id INTEGER,
            source_folio TEXT,
            debit_account TEXT,
            credit_account TEXT,
            amount REAL,
            branch_id INTEGER DEFAULT 1,
            user TEXT DEFAULT 'sistema',
            metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    migration = importlib.import_module("migrations.standalone.093_rrhh_payroll_traceability")
    migration.run(conn)
    conn.execute(
        "INSERT INTO personal (nombre, apellidos, salario, telefono) VALUES (?,?,?,?)",
        ("Ana", "García", 400.0, "555"),
    )
    for day in range(1, 6):
        conn.execute(
            "INSERT INTO asistencias (personal_id, fecha, horas_trabajadas, estado) VALUES (?,?,?,?)",
            (1, f"2026-04-0{day}", 8.0, "PRESENTE"),
        )
    conn.commit()
    return conn


def _uc(conn):
    rrhh = RRHHService(
        conn,
        treasury_service=MagicMock(),
        whatsapp_service=None,
        template_engine=None,
    )
    journal = JournalEntryService(conn)
    handler = PayrollFinanceHandler(journal_service=journal)
    bus = ImmediatePayrollBus(handler)
    uc = GestionarNominaUC(
        rrhh_service=rrhh,
        finance_service=MagicMock(),
        event_bus=bus,
    )
    return uc, bus


def test_phase7_payroll_payment_flows_to_financial_trace_sqlite():
    conn = _db()
    uc, bus = _uc(conn)

    result = uc.ejecutar(
        SolicitudNomina(
            empleado_id=1,
            fecha_inicio="2026-04-01",
            fecha_fin="2026-04-05",
            metodo_pago="transferencia",
            operation_id="op-payroll-sqlite-001",
        ),
        sucursal_id=1,
        admin_user="admin",
    )

    assert result.ok is True
    assert result.payroll_payment_id == 1
    assert [event[0] for event in bus.events] == [NOMINA_GENERADA, NOMINA_PAGADA]

    payment = conn.execute(
        "SELECT total, operation_id, source_module, source_id FROM nomina_pagos WHERE id=?",
        (result.payroll_payment_id,),
    ).fetchone()
    assert payment["operation_id"] == "op-payroll-sqlite-001"
    assert payment["source_module"] == "rrhh"
    assert payment["source_id"] == 1

    entries = conn.execute(
        "SELECT operation_id, event_type, debit_account, credit_account, amount, source_id "
        "FROM journal_entries ORDER BY id"
    ).fetchall()
    assert [row["operation_id"] for row in entries] == [
        "op-payroll-sqlite-001-GEN",
        "op-payroll-sqlite-001-PAID",
    ]
    assert entries[0]["event_type"] == NOMINA_GENERADA
    assert entries[0]["debit_account"] == "6101"
    assert entries[0]["credit_account"] == "2101"
    assert entries[1]["event_type"] == NOMINA_PAGADA
    assert entries[1]["debit_account"] == "2101"
    assert entries[1]["credit_account"] == "1101"
    assert entries[1]["amount"] == result.neto_deducido
    assert entries[1]["source_id"] == result.payroll_payment_id


def test_phase7_payroll_payment_is_idempotent_and_does_not_double_pay():
    conn = _db()
    uc, _bus = _uc(conn)
    solicitud = SolicitudNomina(
        empleado_id=1,
        fecha_inicio="2026-04-01",
        fecha_fin="2026-04-05",
        metodo_pago="efectivo",
        operation_id="op-payroll-no-double",
    )

    first = uc.ejecutar(solicitud, sucursal_id=1, admin_user="admin")
    second = uc.ejecutar(solicitud, sucursal_id=1, admin_user="admin")

    assert first.ok is True
    assert second.ok is True
    assert first.payroll_payment_id == second.payroll_payment_id == 1
    assert conn.execute("SELECT COUNT(*) FROM nomina_pagos").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0] == 2
    assert conn.execute(
        "SELECT COUNT(*) FROM journal_entries WHERE operation_id IN (?, ?)",
        ("op-payroll-no-double-GEN", "op-payroll-no-double-PAID"),
    ).fetchone()[0] == 2
