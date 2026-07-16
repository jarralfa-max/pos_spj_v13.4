"""HR bounded context — born-clean UUIDv7 schema (single source of truth).

Rules:
- Every id is ``TEXT PRIMARY KEY`` holding a lowercase UUIDv7.
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
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    branch_id TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE (code)
);

CREATE TABLE IF NOT EXISTS hr_positions (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    department_id TEXT REFERENCES hr_departments(id),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE (code)
);

CREATE TABLE IF NOT EXISTS employees (
    id TEXT PRIMARY KEY,
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
    id TEXT PRIMARY KEY,
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
    id TEXT PRIMARY KEY,
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
    id TEXT PRIMARY KEY,
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
    id TEXT PRIMARY KEY,
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
    id TEXT PRIMARY KEY,
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
    id TEXT PRIMARY KEY,
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
    id TEXT PRIMARY KEY,
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
    id TEXT PRIMARY KEY,
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
    id TEXT PRIMARY KEY,
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
    id TEXT PRIMARY KEY,
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
    event_id TEXT PRIMARY KEY,
    event_name TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    processed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hr_outbox (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    event_name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','DISPATCHED')),
    created_at TEXT NOT NULL,
    dispatched_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_hr_outbox_status ON hr_outbox (status);
"""


def create_hr_schema(conn) -> None:
    """Create the complete HR schema. Idempotent (IF NOT EXISTS)."""
    conn.executescript(_DDL)


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
