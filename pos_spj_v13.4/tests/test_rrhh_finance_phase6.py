import importlib
import sqlite3
from pathlib import Path

from core.events.handlers.finance_handler import PayrollFinanceHandler
from core.rrhh.events import NOMINA_GENERADA, NOMINA_PAGADA


class FakeJournalService:
    def __init__(self):
        self.entries = {}
        self.calls = []

    def post_entry(self, **kwargs):
        self.calls.append(kwargs)
        op_id = kwargs["operation_id"]
        if op_id in self.entries:
            return self.entries[op_id]
        self.entries[op_id] = len(self.entries) + 1
        return self.entries[op_id]


def _payload():
    return {
        "operation_id": "op-payroll-001",
        "employee_id": 1,
        "nombre": "Ana García",
        "period_start": "2026-04-01",
        "period_end": "2026-04-15",
        "total": 2000.0,
        "neto": 1820.0,
        "payroll_payment_id": 77,
        "metodo_pago": "efectivo",
        "sucursal_id": 1,
    }


def _finance_db():
    from backend.infrastructure.db.schema.finance_schema import create_finance_schema
    from backend.application.services.finance.finance_bootstrap import bootstrap_finance
    conn = sqlite3.connect(":memory:")
    create_finance_schema(conn)
    bootstrap_finance(conn)
    return conn


def test_phase6_payroll_finance_handler_consumes_generated_and_paid_idempotently():
    """FASE 20: PayrollFinanceHandler es puente al bounded context.
    NOMINA_GENERADA no devenga aparte (evita el doble efecto); NOMINA_PAGADA
    postea exactamente un asiento PAYROLL en el ledger nuevo, idempotente."""
    conn = _finance_db()
    handler = PayrollFinanceHandler(db_conn=conn)
    payload = _payload()

    handler.handle_generated(payload)
    handler.handle_generated(payload)
    handler.handle_paid(payload)
    handler.handle_paid(payload)

    entries = conn.execute(
        "SELECT COUNT(*) FROM journal_entries WHERE posting_purpose='PAYROLL'"
    ).fetchone()[0]
    assert entries == 1, "un solo asiento por pago de nómina (sin devengo paralelo)"
    total = conn.execute(
        "SELECT SUM(CAST(debit_amount AS NUMERIC)) FROM journal_lines"
    ).fetchone()[0]
    assert float(total) == 1820.0
    statuses = {row[0] for row in conn.execute("SELECT status FROM journal_entries")}
    assert statuses == {"POSTED"}


def test_phase6_rrhh_service_no_longer_registers_opex_directly():
    src = Path(__file__).resolve().parents[1] / "core" / "services" / "rrhh_service.py"
    text = src.read_text(encoding="utf-8")
    assert "registrar_gasto_opex(" not in text
    assert "PayrollPaidPayload" in text


def test_phase6_migration_adds_payroll_traceability_columns_idempotently():
    migration = importlib.import_module("migrations.standalone.093_rrhh_payroll_traceability")
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
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
        )
        """
    )

    migration.run(conn)
    migration.run(conn)

    columns = {row[1] for row in conn.execute("PRAGMA table_info(nomina_pagos)")}
    assert {"operation_id", "source_module", "source_id"}.issubset(columns)

    conn.execute(
        """
        INSERT INTO nomina_pagos
        (empleado_id, total, operation_id, source_module, source_id)
        VALUES (1, 100, 'op-1', 'rrhh', 1)
        """
    )
    try:
        conn.execute(
            """
            INSERT INTO nomina_pagos
            (empleado_id, total, operation_id, source_module, source_id)
            VALUES (1, 100, 'op-1', 'rrhh', 1)
            """
        )
        duplicate_failed = False
    except sqlite3.IntegrityError:
        duplicate_failed = True
    assert duplicate_failed is True
