"""HR bounded context — born-clean UUIDv7 schema (single source of truth).

Rules:
- Every id is ``TEXT NOT NULL PRIMARY KEY`` holding a lowercase UUIDv7.
- Money columns are ``TEXT`` decimal strings (PostgreSQL: NUMERIC); no REAL.
- Attendance punches are immutable (no UPDATE path in the repositories).
- Idempotency is structural: UNIQUE(operation_id) where an operation must not
  repeat, plus UNIQUE(source, source_reference_id, punch_type) for cash-driven
  punches.
- No AUTOINCREMENT, no integer row-id identity, no legacy compatibility, no
  data rescue.

Only a migration in ``migrations/`` may execute this DDL.
"""

from __future__ import annotations

HR_TABLES: tuple[str, ...] = (
    "hr_device_events",
    "hr_employee_credentials",
    "hr_time_clock_devices",
    "leave_balance_movements",
    "payroll_loan_applications",
    "employee_loans",
    "payroll_inputs",
    "hr_inbox",
    "payroll_payment_allocations",
    "payroll_coverage",
    "employee_salary_history",
    "hr_outbox",
    "hr_processed_events",
    "hr_audit_log",
    "payroll_payments",
    "payroll_lines",
    "payroll_runs",
    "leave_requests",
    "shift_assignments",
    "work_shifts",
    "attendance_adjustments",
    "attendance_punches",
    "attendance_workdays",
    "employees",
    "hr_positions",
    "hr_departments",
)

#: Legacy HR tables orphaned by the born-clean cutover (no live writer after
#: the HR refactor). ``personal`` stays until drivers/commissions are refactored.
LEGACY_HR_TABLES: tuple[str, ...] = (
    "asistencias",
    "nomina_records",
    "evaluaciones_personal",
    "turno_roles",
    "turno_asignaciones",
    "turno_notificaciones_log",
)

_DDL = """
CREATE TABLE IF NOT EXISTS hr_departments (
    id TEXT NOT NULL PRIMARY KEY,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    branch_id TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE (code)
);

CREATE TABLE IF NOT EXISTS hr_positions (
    id TEXT NOT NULL PRIMARY KEY,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    department_id TEXT REFERENCES hr_departments(id),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE (code)
);

CREATE TABLE IF NOT EXISTS employees (
    id TEXT NOT NULL PRIMARY KEY,
    employee_code TEXT NOT NULL UNIQUE,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    phone_e164 TEXT,
    email TEXT,
    branch_id TEXT NOT NULL,
    department_id TEXT REFERENCES hr_departments(id),
    position_id TEXT REFERENCES hr_positions(id),
    supervisor_employee_id TEXT REFERENCES employees(id),
    employment_status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (employment_status IN ('ACTIVE','ON_LEAVE','SUSPENDED','TERMINATED')),
    contract_type TEXT NOT NULL
        CHECK (contract_type IN ('PERMANENT','FIXED_TERM','TEMPORARY','INTERNSHIP','HOURLY')),
    payment_frequency TEXT NOT NULL
        CHECK (payment_frequency IN ('WEEKLY','BIWEEKLY','SEMIMONTHLY','MONTHLY')),
    base_salary TEXT NOT NULL DEFAULT '0.00',
    daily_salary TEXT NOT NULL DEFAULT '0.00',
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    hire_date TEXT NOT NULL,
    termination_date TEXT,
    termination_reason TEXT,
    bank_account_reference TEXT,
    tax_identifier TEXT,
    emergency_contact_name TEXT,
    emergency_contact_phone TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_employees_branch ON employees (branch_id, active);

CREATE TABLE IF NOT EXISTS attendance_workdays (
    id TEXT NOT NULL PRIMARY KEY,
    employee_id TEXT NOT NULL REFERENCES employees(id),
    branch_id TEXT NOT NULL,
    work_date TEXT NOT NULL,
    scheduled_shift_id TEXT,
    first_entry_at TEXT,
    last_exit_at TEXT,
    worked_minutes INTEGER NOT NULL DEFAULT 0,
    late_minutes INTEGER NOT NULL DEFAULT 0,
    overtime_minutes INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN','COMPLETE','INCIDENT','ADJUSTED')),
    incident_type TEXT,
    calculation_version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (employee_id, work_date)
);

CREATE TABLE IF NOT EXISTS attendance_punches (
    id TEXT NOT NULL PRIMARY KEY,
    employee_id TEXT NOT NULL REFERENCES employees(id),
    branch_id TEXT NOT NULL,
    workday_id TEXT REFERENCES attendance_workdays(id),
    punch_type TEXT NOT NULL CHECK (punch_type IN ('ENTRY','EXIT')),
    occurred_at TEXT NOT NULL,
    timezone_name TEXT NOT NULL DEFAULT 'America/Mexico_City',
    source TEXT NOT NULL CHECK (source IN (
        'CASH_REGISTER','MANUAL','TIME_CLOCK','MOBILE','SYSTEM',
        'FINGERPRINT','FACE_RECOGNITION','QR','RFID')),
    source_reference_id TEXT,
    device_id TEXT,
    registered_by_user_id TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    notes TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_punches_workday ON attendance_punches (workday_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_punches_source_ref
    ON attendance_punches (source, source_reference_id, punch_type)
    WHERE source_reference_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS attendance_adjustments (
    id TEXT NOT NULL PRIMARY KEY,
    employee_id TEXT NOT NULL REFERENCES employees(id),
    workday_id TEXT NOT NULL REFERENCES attendance_workdays(id),
    original_punch_id TEXT REFERENCES attendance_punches(id),
    field_name TEXT NOT NULL,
    previous_value TEXT,
    requested_value TEXT NOT NULL,
    reason TEXT NOT NULL,
    requested_by_user_id TEXT NOT NULL,
    approved_by_user_id TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','APPROVED','REJECTED')),
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    approved_at TEXT
);

CREATE TABLE IF NOT EXISTS work_shifts (
    id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    crosses_midnight INTEGER NOT NULL DEFAULT 0,
    break_minutes INTEGER NOT NULL DEFAULT 0,
    late_tolerance_minutes INTEGER NOT NULL DEFAULT 0,
    branch_id TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shift_assignments (
    id TEXT NOT NULL PRIMARY KEY,
    employee_id TEXT NOT NULL REFERENCES employees(id),
    work_shift_id TEXT NOT NULL REFERENCES work_shifts(id),
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    weekdays TEXT NOT NULL,
    branch_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shift_assignments_employee
    ON shift_assignments (employee_id, effective_from);

CREATE TABLE IF NOT EXISTS leave_requests (
    id TEXT NOT NULL PRIMARY KEY,
    employee_id TEXT NOT NULL REFERENCES employees(id),
    branch_id TEXT NOT NULL,
    leave_type TEXT NOT NULL CHECK (leave_type IN (
        'VACATION','PAID_LEAVE','UNPAID_LEAVE','SICK_LEAVE','ABSENCE_JUSTIFICATION')),
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    requested_days INTEGER NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('DRAFT','PENDING','APPROVED','REJECTED','CANCELLED')),
    requested_by_user_id TEXT NOT NULL,
    approved_by_user_id TEXT,
    approved_at TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leave_employee ON leave_requests (employee_id, status);

CREATE TABLE IF NOT EXISTS payroll_runs (
    id TEXT NOT NULL PRIMARY KEY,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    branch_id TEXT,
    payment_frequency TEXT,
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN (
        'DRAFT','CALCULATED','UNDER_REVIEW','AUTHORIZED','PAID','CANCELLED')),
    generated_by_user_id TEXT,
    authorized_by_user_id TEXT,
    authorized_at TEXT,
    paid_at TEXT,
    payment_id TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payroll_lines (
    id TEXT NOT NULL PRIMARY KEY,
    payroll_run_id TEXT NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,
    employee_id TEXT NOT NULL REFERENCES employees(id),
    concept TEXT NOT NULL,
    amount TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    is_deduction INTEGER NOT NULL DEFAULT 0,
    quantity TEXT NOT NULL DEFAULT '1',
    notes TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_payroll_lines_run ON payroll_lines (payroll_run_id);

CREATE TABLE IF NOT EXISTS payroll_payments (
    id TEXT NOT NULL PRIMARY KEY,
    payroll_run_id TEXT NOT NULL UNIQUE REFERENCES payroll_runs(id),
    gross_amount TEXT NOT NULL,
    deductions_amount TEXT NOT NULL,
    net_amount TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    payment_method TEXT NOT NULL CHECK (payment_method IN ('CASH','BANK_TRANSFER','CHECK')),
    authorized_by_user_id TEXT NOT NULL,
    paid_by_user_id TEXT NOT NULL,
    operation_id TEXT NOT NULL UNIQUE,
    paid_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hr_audit_log (
    id TEXT NOT NULL PRIMARY KEY,
    action TEXT NOT NULL,
    actor_user_id TEXT,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    detail TEXT NOT NULL DEFAULT '',
    operation_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hr_audit_entity ON hr_audit_log (entity_type, entity_id);

CREATE TABLE IF NOT EXISTS hr_processed_events (
    event_id TEXT NOT NULL PRIMARY KEY,
    event_name TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    processed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hr_outbox (
    id TEXT NOT NULL PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    event_name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','DISPATCHED')),
    created_at TEXT NOT NULL,
    dispatched_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_hr_outbox_status ON hr_outbox (status);

-- Auditoría RRHH cebf67a (migración 335) ---------------------------------
-- HR-09/HR-23: el salario tiene vigencia; recalcular julio usa la tasa de julio.
CREATE TABLE IF NOT EXISTS employee_salary_history (
    id TEXT NOT NULL PRIMARY KEY,
    employee_id TEXT NOT NULL REFERENCES employees(id),
    daily_salary TEXT NOT NULL,
    base_salary TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    effective_from TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    changed_by_user_id TEXT,
    operation_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (employee_id, effective_from)
);

-- HR-10: un día de un empleado lo cubre UNA sola corrida ordinaria viva. La
-- restricción UNIQUE lo hace estructural (dos operadores, reintentos, concurrencia).
CREATE TABLE IF NOT EXISTS payroll_coverage (
    id TEXT NOT NULL PRIMARY KEY,
    employee_id TEXT NOT NULL REFERENCES employees(id),
    coverage_date TEXT NOT NULL,
    payroll_run_id TEXT NOT NULL REFERENCES payroll_runs(id),
    UNIQUE (employee_id, coverage_date)
);
CREATE INDEX IF NOT EXISTS idx_payroll_coverage_run ON payroll_coverage (payroll_run_id);

-- HR-11: cuánto se entrega a cada persona; la suma es el pago y el asiento.
CREATE TABLE IF NOT EXISTS payroll_payment_allocations (
    id TEXT NOT NULL PRIMARY KEY,
    payroll_payment_id TEXT NOT NULL REFERENCES payroll_payments(id),
    payroll_run_id TEXT NOT NULL REFERENCES payroll_runs(id),
    employee_id TEXT NOT NULL REFERENCES employees(id),
    net_amount TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    UNIQUE (payroll_payment_id, employee_id)
);

-- HR-06: eventos de Caja que RR. HH. no pudo aplicar todavía (usuario sin
-- empleado vinculado). No se pierden: se reprocesan al vincular.
CREATE TABLE IF NOT EXISTS hr_inbox (
    event_id TEXT NOT NULL PRIMARY KEY,
    event_name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    user_id TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','PROCESSED','DISCARDED')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    processed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_hr_inbox_status ON hr_inbox (status, user_id);

-- Pendientes de la auditoría RRHH (migración 337) --------------------------
-- Percepciones/deducciones capturadas y aprobadas (bonos, comisiones, ajustes):
-- la corrida ordinaria que cubre ``applies_on`` las toma; cancelarla las libera.
CREATE TABLE IF NOT EXISTS payroll_inputs (
    id TEXT NOT NULL PRIMARY KEY,
    employee_id TEXT NOT NULL REFERENCES employees(id),
    branch_id TEXT NOT NULL,
    concept TEXT NOT NULL,
    amount TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    applies_on TEXT NOT NULL,
    reason TEXT NOT NULL,
    source_module TEXT NOT NULL DEFAULT 'hr',
    source_reference TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','APPROVED','APPLIED','REJECTED','CANCELLED')),
    captured_by_user_id TEXT NOT NULL,
    approved_by_user_id TEXT,
    approved_at TEXT,
    payroll_run_id TEXT REFERENCES payroll_runs(id),
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_payroll_inputs_employee ON payroll_inputs (employee_id, status);

-- Préstamos y anticipos a empleados: se descuentan por abono en cada nómina
-- hasta liquidarse. El saldo NO se guarda: es principal − abonos de corridas vivas.
CREATE TABLE IF NOT EXISTS employee_loans (
    id TEXT NOT NULL PRIMARY KEY,
    employee_id TEXT NOT NULL REFERENCES employees(id),
    branch_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('LOAN','ADVANCE')),
    principal TEXT NOT NULL,
    installment TEXT NOT NULL,
    currency_code TEXT NOT NULL DEFAULT 'MXN',
    granted_on TEXT NOT NULL,
    payment_method TEXT NOT NULL CHECK (payment_method IN ('CASH','BANK_TRANSFER','CHECK')),
    payment_reference TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','PAID','CANCELLED')),
    reason TEXT NOT NULL,
    granted_by_user_id TEXT NOT NULL,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payroll_loan_applications (
    id TEXT NOT NULL PRIMARY KEY,
    loan_id TEXT NOT NULL REFERENCES employee_loans(id),
    payroll_run_id TEXT NOT NULL REFERENCES payroll_runs(id),
    amount TEXT NOT NULL,
    UNIQUE (loan_id, payroll_run_id)
);

-- Saldo de vacaciones como LIBRO de movimientos (abono por ciclo, reserva,
-- consumo, liberación, vencimiento, ajuste). Cada saldo se explica por filas.
CREATE TABLE IF NOT EXISTS leave_balance_movements (
    id TEXT NOT NULL PRIMARY KEY,
    employee_id TEXT NOT NULL REFERENCES employees(id),
    leave_type TEXT NOT NULL DEFAULT 'VACATION',
    cycle_start TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('ACCRUAL','RESERVATION','RELEASE','CONSUMPTION',
                                       'EXPIRATION','ADJUSTMENT')),
    days INTEGER NOT NULL,
    source_type TEXT,
    source_id TEXT,
    reason TEXT NOT NULL DEFAULT '',
    created_by_user_id TEXT,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_leave_ledger_cycle_once
    ON leave_balance_movements (employee_id, leave_type, cycle_start, kind)
    WHERE kind IN ('ACCRUAL','EXPIRATION');
CREATE INDEX IF NOT EXISTS idx_leave_ledger_employee
    ON leave_balance_movements (employee_id, leave_type, cycle_start);

-- Checador: aparatos, credenciales (referencia del aparato; nunca la plantilla
-- biométrica; el PIN sólo como hash) y eventos crudos como evidencia.
CREATE TABLE IF NOT EXISTS hr_time_clock_devices (
    id TEXT NOT NULL PRIMARY KEY,
    branch_id TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    driver TEXT NOT NULL DEFAULT 'keyboard',
    connection_json TEXT NOT NULL DEFAULT '{}',
    active INTEGER NOT NULL DEFAULT 1,
    sync_cursor TEXT,
    last_synced_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hr_employee_credentials (
    id TEXT NOT NULL PRIMARY KEY,
    employee_id TEXT NOT NULL REFERENCES employees(id),
    credential_type TEXT NOT NULL CHECK (credential_type IN ('DEVICE_USER','CARD','QR','PIN')),
    lookup_key TEXT NOT NULL,
    device_scope TEXT NOT NULL DEFAULT '',
    label TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    enrolled_by_user_id TEXT,
    created_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_hr_credentials_active
    ON hr_employee_credentials (credential_type, lookup_key, device_scope) WHERE active=1;
CREATE TABLE IF NOT EXISTS hr_device_events (
    id TEXT NOT NULL PRIMARY KEY,
    device_id TEXT NOT NULL REFERENCES hr_time_clock_devices(id),
    device_event_id TEXT NOT NULL,
    credential_type TEXT NOT NULL,
    lookup_key TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    verify_method TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN ('APPLIED','DUPLICATE','UNMATCHED','REJECTED')),
    employee_id TEXT,
    punch_id TEXT,
    error TEXT,
    received_at TEXT NOT NULL,
    UNIQUE (device_id, device_event_id)
);
CREATE INDEX IF NOT EXISTS idx_hr_device_events_status ON hr_device_events (status);
"""


#: Auditoría de Finanzas F21 (2026-10-10): la entrega de PAYROLL_PAID a
#: Finanzas deja intentos y último error visibles en vez de fallar en silencio.
_UPGRADE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("hr_outbox", "attempts", "INTEGER NOT NULL DEFAULT 0"),
    ("hr_outbox", "last_error", "TEXT"),
    # Auditoría RRHH cebf67a (migración 335):
    # HR-10 tipo de corrida y huella de la solicitud (misma clave, otro contenido).
    ("payroll_runs", "run_type", "TEXT NOT NULL DEFAULT 'ORDINARY'"),
    ("payroll_runs", "request_fingerprint", "TEXT"),
    # HR-27 importe autorizado: pagar exige exactamente esa versión.
    ("payroll_runs", "authorized_net_amount", "TEXT"),
    # HR-29 referencia del pago (transferencia/cheque) y quién la capturó.
    ("payroll_payments", "payment_reference", "TEXT"),
    # HR-19 cancelación de una ausencia: quién, cuándo y por qué.
    ("leave_requests", "cancelled_by_user_id", "TEXT"),
    ("leave_requests", "cancelled_at", "TEXT"),
    ("leave_requests", "cancel_reason", "TEXT"),
    # Pendientes (migración 337): corrida complementaria y reverso de un pago.
    ("payroll_runs", "original_run_id", "TEXT"),
    ("payroll_runs", "adjustment_reason", "TEXT"),
    ("payroll_runs", "reversed_at", "TEXT"),
    ("payroll_runs", "reversed_by_user_id", "TEXT"),
    ("payroll_runs", "reversal_reason", "TEXT"),
    ("payroll_payments", "reversed_at", "TEXT"),
)


def upgrade_hr_schema(conn) -> list[str]:
    """Columnas agregadas después del esquema base. Idempotente."""
    added: list[str] = []
    for table, column, ddl in _UPGRADE_COLUMNS:
        existing = {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if existing and column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            added.append(f"{table}.{column}")
    return added


def create_hr_schema(conn) -> None:
    """Create the complete HR schema. Idempotent (IF NOT EXISTS)."""
    conn.executescript(_DDL)
    upgrade_hr_schema(conn)


def drop_legacy_hr_tables(conn) -> list[str]:
    """Drop legacy HR tables with no live writer after the refactor."""
    dropped: list[str] = []
    for table in LEGACY_HR_TABLES:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if row is not None:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
            dropped.append(table)
    return dropped
