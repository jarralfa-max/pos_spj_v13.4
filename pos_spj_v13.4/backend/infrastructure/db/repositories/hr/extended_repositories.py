"""Repositorios de los pendientes de la auditoría RR. HH. (2026-10-14):
checador, conceptos capturados, préstamos y libro de vacaciones.
Los repositorios nunca confirman; la UoW es la dueña de la transacción."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.domain.hr.time_clock import (
    CredentialType,
    EmployeeCredential,
    TimeClockDevice,
    TimeClockKind,
)
from backend.infrastructure.db.repositories.hr.base import HRRepositoryBase
from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TimeClockRepository(HRRepositoryBase):
    # ── aparatos ────────────────────────────────────────────────────────────
    def save_device(self, device: TimeClockDevice) -> None:
        self._execute(
            "INSERT INTO hr_time_clock_devices (id, branch_id, code, name, kind, driver,"
            " connection_json, active, sync_cursor, last_synced_at, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (device.id, device.branch_id, device.code, device.name, device.kind.value,
             device.driver, json.dumps(device.connection), int(device.active),
             device.sync_cursor, device.last_synced_at, device.created_at))

    def update_sync(self, device_id: str, *, cursor: str | None) -> None:
        self._execute("UPDATE hr_time_clock_devices SET sync_cursor=?, last_synced_at=?"
                      " WHERE id=?", (cursor, _now(), device_id))

    def set_active(self, device_id: str, active: bool) -> None:
        self._execute("UPDATE hr_time_clock_devices SET active=? WHERE id=?",
                      (int(active), device_id))

    def get_device(self, device_id: str) -> TimeClockDevice | None:
        row = self._query_one("SELECT * FROM hr_time_clock_devices WHERE id=?", (device_id,))
        return self._device(row) if row else None

    def get_device_by_code(self, code: str) -> TimeClockDevice | None:
        row = self._query_one("SELECT * FROM hr_time_clock_devices WHERE code=?",
                              (str(code or "").strip().upper(),))
        return self._device(row) if row else None

    def list_devices(self, *, branch_id: str | None = None) -> list[TimeClockDevice]:
        if branch_id:
            rows = self._query("SELECT * FROM hr_time_clock_devices WHERE branch_id=?"
                               " ORDER BY code", (branch_id,))
        else:
            rows = self._query("SELECT * FROM hr_time_clock_devices ORDER BY code")
        return [self._device(r) for r in rows]

    @staticmethod
    def _device(row: dict) -> TimeClockDevice:
        return TimeClockDevice(
            id=row["id"], branch_id=row["branch_id"], code=row["code"], name=row["name"],
            kind=TimeClockKind(row["kind"]), driver=row["driver"],
            connection=json.loads(row["connection_json"] or "{}"),
            active=bool(row["active"]), sync_cursor=row["sync_cursor"],
            last_synced_at=row["last_synced_at"], created_at=row["created_at"])

    # ── credenciales ────────────────────────────────────────────────────────
    def save_credential(self, credential: EmployeeCredential) -> None:
        self._execute(
            "INSERT INTO hr_employee_credentials (id, employee_id, credential_type, lookup_key,"
            " device_scope, label, active, enrolled_by_user_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (credential.id, credential.employee_id, credential.credential_type.value,
             credential.lookup_key, credential.device_id or "", credential.label,
             int(credential.active), credential.enrolled_by_user_id, credential.created_at))

    def revoke_credential(self, credential_id: str) -> None:
        self._execute("UPDATE hr_employee_credentials SET active=0, revoked_at=? WHERE id=?",
                      (_now(), credential_id))

    def find_employee_for(self, credential_type: CredentialType, lookup_key: str,
                          device_id: str | None) -> str | None:
        """Credencial del aparato concreto primero; luego la válida en todos."""
        row = self._query_one(
            "SELECT employee_id FROM hr_employee_credentials WHERE active=1"
            " AND credential_type=? AND lookup_key=? AND device_scope IN (?, '')"
            " ORDER BY CASE device_scope WHEN '' THEN 1 ELSE 0 END LIMIT 1",
            (credential_type.value, lookup_key, device_id or ""))
        return row["employee_id"] if row else None

    def credentials_for(self, employee_id: str) -> list[dict]:
        return self._query(
            "SELECT c.id, c.credential_type, c.label, c.device_scope, c.active, c.created_at,"
            " d.code AS device_code FROM hr_employee_credentials c"
            " LEFT JOIN hr_time_clock_devices d ON d.id=c.device_scope"
            " WHERE c.employee_id=? ORDER BY c.created_at DESC", (employee_id,))

    def get_credential(self, credential_id: str) -> dict | None:
        return self._query_one("SELECT * FROM hr_employee_credentials WHERE id=?",
                               (credential_id,))

    # ── eventos del aparato ─────────────────────────────────────────────────
    def find_event(self, device_id: str, device_event_id: str) -> dict | None:
        return self._query_one(
            "SELECT * FROM hr_device_events WHERE device_id=? AND device_event_id=?",
            (device_id, device_event_id))

    def save_event(self, *, device_id: str, device_event_id: str, credential_type: str,
                   lookup_key: str, occurred_at: str, kind: str, verify_method: str,
                   status: str, employee_id: str | None, punch_id: str | None,
                   error: str | None) -> str:
        event_id = new_uuid()
        self._execute(
            "INSERT INTO hr_device_events (id, device_id, device_event_id, credential_type,"
            " lookup_key, occurred_at, kind, verify_method, status, employee_id, punch_id,"
            " error, received_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, device_id, device_event_id, credential_type, lookup_key, occurred_at,
             kind, verify_method, status, employee_id, punch_id, error, _now()))
        return event_id

    def resolve_event(self, event_id: str, *, status: str, employee_id: str | None,
                      punch_id: str | None, error: str | None) -> None:
        self._execute("UPDATE hr_device_events SET status=?, employee_id=?, punch_id=?, error=?"
                      " WHERE id=?", (status, employee_id, punch_id, error, event_id))

    def unmatched_events(self, *, lookup_key: str | None = None) -> list[dict]:
        if lookup_key:
            return self._query("SELECT * FROM hr_device_events WHERE status='UNMATCHED'"
                               " AND lookup_key=? ORDER BY occurred_at", (lookup_key,))
        return self._query("SELECT * FROM hr_device_events WHERE status='UNMATCHED'"
                           " ORDER BY occurred_at")


class PayrollInputRepository(HRRepositoryBase):
    _COLS = ("id, employee_id, branch_id, concept, amount, currency_code, applies_on, reason,"
             " source_module, source_reference, status, captured_by_user_id,"
             " approved_by_user_id, approved_at, payroll_run_id, operation_id, created_at")

    def save(self, row: dict) -> None:
        self._execute(
            f"INSERT INTO payroll_inputs ({self._COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            tuple(row.get(c.strip()) for c in self._COLS.split(",")))

    def get(self, input_id: str) -> dict | None:
        return self._query_one(f"SELECT {self._COLS} FROM payroll_inputs WHERE id=?",
                               (input_id,))

    def find_by_operation_id(self, operation_id: str) -> dict | None:
        return self._query_one(f"SELECT {self._COLS} FROM payroll_inputs WHERE operation_id=?",
                               (operation_id,))

    def set_status(self, input_id: str, status: str, *, approved_by: str | None = None,
                   payroll_run_id: str | None = None) -> None:
        self._execute(
            "UPDATE payroll_inputs SET status=?, approved_by_user_id=COALESCE(?, approved_by_user_id),"
            " approved_at=CASE WHEN ? IS NOT NULL THEN ? ELSE approved_at END, payroll_run_id=?"
            " WHERE id=?", (status, approved_by, approved_by, _now(), payroll_run_id, input_id))

    def approved_for(self, employee_id: str, start: date, end: date) -> list[dict]:
        return self._query(
            f"SELECT {self._COLS} FROM payroll_inputs WHERE employee_id=? AND status='APPROVED'"
            " AND applies_on BETWEEN ? AND ? ORDER BY applies_on", (employee_id,
                                                                    start.isoformat(),
                                                                    end.isoformat()))

    def release_run(self, payroll_run_id: str) -> None:
        self._execute("UPDATE payroll_inputs SET status='APPROVED', payroll_run_id=NULL"
                      " WHERE payroll_run_id=? AND status='APPLIED'", (payroll_run_id,))

    def list(self, *, branch_id: str | None = None, status: str | None = None) -> list[dict]:
        conditions, params = ["1=1"], []
        if branch_id:
            conditions.append("i.branch_id=?")
            params.append(branch_id)
        if status:
            conditions.append("i.status=?")
            params.append(status)
        return self._query(
            "SELECT i.id, i.employee_id, e.first_name || ' ' || e.last_name AS employee_name,"
            " i.concept, i.amount, i.applies_on, i.reason, i.status, i.captured_by_user_id"
            " FROM payroll_inputs i JOIN employees e ON e.id=i.employee_id"
            f" WHERE {' AND '.join(conditions)} ORDER BY i.applies_on DESC", tuple(params))


class EmployeeLoanRepository(HRRepositoryBase):
    _COLS = ("id, employee_id, branch_id, kind, principal, installment, currency_code,"
             " granted_on, payment_method, payment_reference, status, reason,"
             " granted_by_user_id, operation_id, created_at")

    def save(self, row: dict) -> None:
        self._execute(
            f"INSERT INTO employee_loans ({self._COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            tuple(row.get(c.strip()) for c in self._COLS.split(",")))

    def get(self, loan_id: str) -> dict | None:
        return self._query_one(f"SELECT {self._COLS} FROM employee_loans WHERE id=?", (loan_id,))

    def find_by_operation_id(self, operation_id: str) -> dict | None:
        return self._query_one(f"SELECT {self._COLS} FROM employee_loans WHERE operation_id=?",
                               (operation_id,))

    def active_for(self, employee_id: str, *, as_of: date) -> list[dict]:
        return self._query(
            f"SELECT {self._COLS} FROM employee_loans WHERE employee_id=? AND status='ACTIVE'"
            " AND granted_on<=? ORDER BY granted_on", (employee_id, as_of.isoformat()))

    def applied_total(self, loan_id: str) -> Decimal:
        """Abonos en corridas VIVAS (no canceladas): lo pagado o reservado."""
        total = Decimal("0")
        for row in self._query(
                "SELECT a.amount FROM payroll_loan_applications a JOIN payroll_runs r"
                " ON r.id=a.payroll_run_id WHERE a.loan_id=? AND r.status<>'CANCELLED'",
                (loan_id,)):
            total += Decimal(str(row["amount"]))
        return total

    def apply(self, loan_id: str, payroll_run_id: str, amount: Decimal) -> None:
        self._execute("INSERT INTO payroll_loan_applications (id, loan_id, payroll_run_id, amount)"
                      " VALUES (?,?,?,?)", (new_uuid(), loan_id, payroll_run_id,
                                            format(amount.quantize(Decimal("0.01")), "f")))

    def release_run(self, payroll_run_id: str) -> None:
        self._execute("DELETE FROM payroll_loan_applications WHERE payroll_run_id=?",
                      (payroll_run_id,))

    def set_status(self, loan_id: str, status: str) -> None:
        self._execute("UPDATE employee_loans SET status=? WHERE id=?", (status, loan_id))

    def list(self, *, branch_id: str | None = None) -> list[dict]:
        clause, params = ("WHERE l.branch_id=?", (branch_id,)) if branch_id else ("", ())
        return self._query(
            "SELECT l.id, l.employee_id, e.first_name || ' ' || e.last_name AS employee_name,"
            " l.kind, l.principal, l.installment, l.granted_on, l.status FROM employee_loans l"
            f" JOIN employees e ON e.id=l.employee_id {clause} ORDER BY l.granted_on DESC", params)


class LeaveLedgerRepository(HRRepositoryBase):
    def add(self, *, employee_id: str, cycle_start: date, kind: str, days: int,
            source_type: str | None = None, source_id: str | None = None, reason: str = "",
            created_by_user_id: str | None = None, leave_type: str = "VACATION") -> bool:
        """Agrega un movimiento. Abono y vencimiento son UNO por ciclo: repetirlos
        no hace nada (devuelve False)."""
        cursor = self._conn.execute(
            "INSERT OR IGNORE INTO leave_balance_movements (id, employee_id, leave_type,"
            " cycle_start, kind, days, source_type, source_id, reason, created_by_user_id,"
            " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (new_uuid(), employee_id, leave_type, cycle_start.isoformat(), kind, int(days),
             source_type, source_id, reason, created_by_user_id, _now()))
        return bool(cursor.rowcount)

    def movements(self, employee_id: str, leave_type: str = "VACATION") -> list[dict]:
        return self._query(
            "SELECT cycle_start, kind, days, source_type, source_id, reason, created_at"
            " FROM leave_balance_movements WHERE employee_id=? AND leave_type=?"
            " ORDER BY cycle_start, created_at", (employee_id, leave_type))

    def by_source(self, source_type: str, source_id: str) -> list[dict]:
        return self._query(
            "SELECT cycle_start, kind, days FROM leave_balance_movements"
            " WHERE source_type=? AND source_id=? ORDER BY created_at", (source_type, source_id))
