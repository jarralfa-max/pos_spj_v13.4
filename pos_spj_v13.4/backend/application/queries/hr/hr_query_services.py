"""Read-only query services for the HR bounded context (UI + BI feed).

No mutations, no commit. Return display-ready dict rows with paging/filters.

Auditoría RRHH cebf67a:
- HR-02: TODA lectura acepta la sucursal (``branch_id``); el presentador la
  pasa siempre con la sucursal de la sesión.
- HR-24: el tablero distingue en turno / jornada terminada / falta contra turno
  asignado / ausencia autorizada, y todos sus indicadores usan el mismo alcance.
- HR-25: los importes se suman en Decimal desde sus cadenas (antes SUM NUMERIC
  y ``float``: 0.30−0.10 daba 0.19999999999999998).
- HR-28: búsqueda y conteo para paginar el padrón.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any


def _decimal_sum(values) -> Decimal:
    total = Decimal("0")
    for value in values:
        total += Decimal(str(value or "0"))
    return total


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


class _HRQueryBase:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = self._conn.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _scalar(self, sql: str, params: tuple = (), default: Any = 0) -> Any:
        row = self._conn.execute(sql, params).fetchone()
        return row[0] if row and row[0] is not None else default

    def _has_table(self, name: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone() is not None


class EmployeeQueryService(_HRQueryBase):
    def _filters(self, *, branch_id, active_only, search):
        conditions, params = ["1=1"], []
        if active_only:
            conditions.append("e.active=1")
        if branch_id:
            conditions.append("e.branch_id=?")
            params.append(branch_id)
        if search:
            conditions.append("(e.first_name LIKE ? OR e.last_name LIKE ? OR e.employee_code LIKE ?"
                              " OR (e.first_name || ' ' || e.last_name) LIKE ?)")
            like = f"%{search.strip()}%"
            params.extend([like, like, like, like])
        return " AND ".join(conditions), params

    def list_employees(self, *, branch_id: str | None = None, active_only: bool = True,
                       search: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
        where, params = self._filters(branch_id=branch_id, active_only=active_only,
                                      search=search)
        params.extend([limit, offset])
        return self._query(
            "SELECT e.id, e.employee_code, e.first_name, e.last_name, e.branch_id,"
            " e.employment_status, e.hire_date, e.active,"
            " d.name AS department_name, p.name AS position_name"
            " FROM employees e"
            " LEFT JOIN hr_departments d ON d.id=e.department_id"
            " LEFT JOIN hr_positions p ON p.id=e.position_id"
            f" WHERE {where}"
            " ORDER BY e.last_name, e.first_name LIMIT ? OFFSET ?", tuple(params))

    def count_employees(self, *, branch_id: str | None = None, active_only: bool = True,
                        search: str | None = None) -> int:
        where, params = self._filters(branch_id=branch_id, active_only=active_only,
                                      search=search)
        return int(self._scalar(f"SELECT COUNT(*) FROM employees e WHERE {where}",
                                tuple(params)))

    def get_employee(self, employee_id: str, *, branch_id: str | None = None) -> dict | None:
        sql = ("SELECT e.*, d.name AS department_name, p.name AS position_name"
               " FROM employees e"
               " LEFT JOIN hr_departments d ON d.id=e.department_id"
               " LEFT JOIN hr_positions p ON p.id=e.position_id WHERE e.id=?")
        params: tuple = (employee_id,)
        if branch_id:
            sql += " AND e.branch_id=?"
            params = (employee_id, branch_id)
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def salary_history(self, employee_id: str) -> list[dict]:
        if not self._has_table("employee_salary_history"):
            return []
        return self._query(
            "SELECT effective_from, daily_salary, base_salary, reason FROM"
            " employee_salary_history WHERE employee_id=? ORDER BY effective_from DESC",
            (employee_id,))

    def linkable_users(self) -> list[dict]:
        """Usuarios activos sin empleado vinculado (para vincular, HR-30)."""
        if not self._has_table("usuarios"):
            return []
        columns = {r[1] for r in self._conn.execute("PRAGMA table_info(usuarios)")}
        active = " AND COALESCE(activo,1)=1" if "activo" in columns else ""
        return self._query(
            "SELECT id, usuario FROM usuarios WHERE (personal_id IS NULL OR personal_id='')"
            f"{active} ORDER BY usuario")

    def linked_user(self, employee_id: str) -> dict | None:
        if not self._has_table("usuarios"):
            return None
        rows = self._query("SELECT id, usuario FROM usuarios WHERE personal_id=? LIMIT 1",
                           (employee_id,))
        return rows[0] if rows else None

    def catalogs(self) -> dict:
        return {
            "departments": self._query(
                "SELECT id, code, name FROM hr_departments WHERE active=1 ORDER BY name"),
            "positions": self._query(
                "SELECT id, code, name, department_id FROM hr_positions WHERE active=1"
                " ORDER BY name"),
        }

    def org_units(self) -> list[dict]:
        """Unidades organizacionales activas (para asignar departamentos)."""
        if not self._query("SELECT 1 AS x FROM sqlite_master WHERE type='table'"
                           " AND name='org_units'"):
            return []
        return self._query("SELECT id, code, name FROM org_units WHERE status='ACTIVE'"
                           " ORDER BY name")


class AttendanceQueryService(_HRQueryBase):
    def list_workdays(self, *, work_date: str | None = None, branch_id: str | None = None,
                      date_from: str | None = None, date_to: str | None = None,
                      limit: int = 200) -> list[dict]:
        conditions, params = ["1=1"], []
        if work_date:
            conditions.append("w.work_date=?")
            params.append(work_date)
        if date_from:
            conditions.append("w.work_date>=?")
            params.append(date_from)
        if date_to:
            conditions.append("w.work_date<=?")
            params.append(date_to)
        if branch_id:
            conditions.append("w.branch_id=?")
            params.append(branch_id)
        params.append(limit)
        return self._query(
            "SELECT w.id, w.employee_id, e.first_name || ' ' || e.last_name AS employee_name,"
            " w.branch_id, w.work_date, w.first_entry_at, w.last_exit_at, w.worked_minutes,"
            " w.late_minutes, w.overtime_minutes, w.status, w.incident_type"
            " FROM attendance_workdays w JOIN employees e ON e.id=w.employee_id"
            f" WHERE {' AND '.join(conditions)}"
            " ORDER BY w.work_date DESC, employee_name LIMIT ?", tuple(params))

    def workday_punches(self, workday_id: str) -> list[dict]:
        return self._query(
            "SELECT punch_type, occurred_at, timezone_name, source, registered_by_user_id,"
            " notes FROM attendance_punches WHERE workday_id=? ORDER BY occurred_at",
            (workday_id,))

    def get_workday(self, workday_id: str, *, branch_id: str | None = None) -> dict | None:
        sql = ("SELECT w.id, w.employee_id, e.first_name || ' ' || e.last_name AS employee_name,"
               " w.branch_id, w.work_date, w.first_entry_at, w.last_exit_at, w.status"
               " FROM attendance_workdays w JOIN employees e ON e.id=w.employee_id"
               " WHERE w.id=?")
        params: tuple = (workday_id,)
        if branch_id:
            sql += " AND w.branch_id=?"
            params = (workday_id, branch_id)
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def pending_adjustments(self, *, branch_id: str | None = None) -> list[dict]:
        clause = " AND w.branch_id=?" if branch_id else ""
        params: tuple = (branch_id,) if branch_id else ()
        return self._query(
            "SELECT a.id, a.employee_id, e.first_name || ' ' || e.last_name AS employee_name,"
            " w.work_date, a.field_name, a.previous_value, a.requested_value, a.reason,"
            " a.status, a.requested_by_user_id"
            " FROM attendance_adjustments a JOIN employees e ON e.id=a.employee_id"
            " JOIN attendance_workdays w ON w.id=a.workday_id"
            f" WHERE a.status='PENDING'{clause} ORDER BY a.created_at", params)

    def pending_cash_events(self) -> list[dict]:
        """HR-06: aperturas/cierres de caja retenidos (usuario sin empleado)."""
        if not self._has_table("hr_inbox"):
            return []
        return self._query(
            "SELECT event_id, event_name, user_id, attempts, last_error, created_at"
            " FROM hr_inbox WHERE status='PENDING' ORDER BY created_at")


class LeaveQueryService(_HRQueryBase):
    def list_requests(self, *, status: str | None = None, employee_id: str | None = None,
                      branch_id: str | None = None) -> list[dict]:
        conditions, params = ["1=1"], []
        if status:
            conditions.append("l.status=?")
            params.append(status)
        if employee_id:
            conditions.append("l.employee_id=?")
            params.append(employee_id)
        if branch_id:
            conditions.append("l.branch_id=?")
            params.append(branch_id)
        return self._query(
            "SELECT l.id, l.employee_id, e.first_name || ' ' || e.last_name AS employee_name,"
            " l.leave_type, l.start_date, l.end_date, l.requested_days, l.status, l.reason,"
            " l.requested_by_user_id, l.approved_by_user_id, l.cancel_reason"
            " FROM leave_requests l JOIN employees e ON e.id=l.employee_id"
            f" WHERE {' AND '.join(conditions)} ORDER BY l.start_date DESC", tuple(params))


class PayrollQueryService(_HRQueryBase):
    def list_runs(self, *, status: str | None = None,
                  branch_id: str | None = None) -> list[dict]:
        conditions, params = ["1=1"], []
        if status:
            conditions.append("status=?")
            params.append(status)
        if branch_id:
            conditions.append("branch_id=?")
            params.append(branch_id)
        return self._query(
            "SELECT id, period_start, period_end, branch_id, status, generated_by_user_id,"
            " authorized_by_user_id, authorized_net_amount, paid_at FROM payroll_runs"
            f" WHERE {' AND '.join(conditions)} ORDER BY period_start DESC LIMIT 200",
            tuple(params))

    def get_run(self, payroll_run_id: str) -> dict | None:
        rows = self._query(
            "SELECT id, period_start, period_end, branch_id, status, generated_by_user_id,"
            " authorized_by_user_id, authorized_net_amount, paid_at, payment_id"
            " FROM payroll_runs WHERE id=?", (payroll_run_id,))
        return rows[0] if rows else None

    def run_lines(self, payroll_run_id: str) -> list[dict]:
        return self._query(
            "SELECT pl.employee_id, e.employee_code,"
            " e.first_name || ' ' || e.last_name AS employee_name,"
            " pl.concept, pl.amount, pl.is_deduction, pl.quantity, pl.notes"
            " FROM payroll_lines pl JOIN employees e ON e.id=pl.employee_id"
            " WHERE pl.payroll_run_id=? ORDER BY employee_name, pl.concept",
            (payroll_run_id,))

    def run_totals(self, payroll_run_id: str) -> dict:
        lines = self._query(
            "SELECT amount, is_deduction FROM payroll_lines WHERE payroll_run_id=?",
            (payroll_run_id,))
        gross = _decimal_sum(r["amount"] for r in lines if not r["is_deduction"])
        deductions = _decimal_sum(r["amount"] for r in lines if r["is_deduction"])
        return {"gross": _money(gross), "deductions": _money(deductions),
                "net": _money(gross - deductions)}

    def totals_by_run(self, run_ids) -> dict[str, dict]:
        """Totales de varias corridas en una sola lectura (sin N+1)."""
        wanted = list(run_ids)
        if not wanted:
            return {}
        marks = ",".join("?" for _ in wanted)
        rows = self._query(
            f"SELECT payroll_run_id, amount, is_deduction FROM payroll_lines"
            f" WHERE payroll_run_id IN ({marks})", tuple(wanted))
        grouped: dict[str, list] = defaultdict(list)
        for row in rows:
            grouped[row["payroll_run_id"]].append(row)
        result = {}
        for run_id in wanted:
            lines = grouped.get(run_id, [])
            gross = _decimal_sum(r["amount"] for r in lines if not r["is_deduction"])
            deductions = _decimal_sum(r["amount"] for r in lines if r["is_deduction"])
            result[run_id] = {"gross": _money(gross), "deductions": _money(deductions),
                              "net": _money(gross - deductions)}
        return result

    def employee_summary(self, payroll_run_id: str) -> list[dict]:
        """HR-29: percepciones, deducciones y neto POR EMPLEADO (para revisar
        antes de autorizar)."""
        per_employee: dict[str, dict] = {}
        for line in self.run_lines(payroll_run_id):
            row = per_employee.setdefault(line["employee_id"], {
                "employee_id": line["employee_id"], "employee_code": line["employee_code"],
                "employee_name": line["employee_name"], "gross": Decimal("0"),
                "deductions": Decimal("0"), "concepts": []})
            amount = Decimal(str(line["amount"]))
            if line["is_deduction"]:
                row["deductions"] += amount
            else:
                row["gross"] += amount
            row["concepts"].append(line)
        result = []
        for row in per_employee.values():
            net = row["gross"] - row["deductions"]
            result.append({**row, "gross": _money(row["gross"]),
                           "deductions": _money(row["deductions"]), "net": _money(net),
                           "negative": net < 0})
        return sorted(result, key=lambda r: r["employee_name"])

    def payment(self, payroll_run_id: str) -> dict | None:
        rows = self._query(
            "SELECT id, net_amount, payment_method, payment_reference, paid_at,"
            " paid_by_user_id FROM payroll_payments WHERE payroll_run_id=?",
            (payroll_run_id,)) if self._has_payment_reference() else self._query(
            "SELECT id, net_amount, payment_method, paid_at, paid_by_user_id"
            " FROM payroll_payments WHERE payroll_run_id=?", (payroll_run_id,))
        return rows[0] if rows else None

    def accounting_status(self, payroll_run_id: str) -> str:
        """¿Llegó la nómina pagada a contabilidad? (visible, no supuesto)."""
        rows = self._query(
            "SELECT status, attempts, last_error, payload_json FROM hr_outbox"
            " WHERE event_name='PAYROLL_PAID'") if "attempts" in self._outbox_columns() else []
        for row in rows:
            if payroll_run_id in str(row["payload_json"]):
                if row["status"] == "DISPATCHED":
                    return "Contabilizada"
                if row.get("last_error"):
                    return f"Pendiente de contabilizar: {row['last_error']}"
                return "Pendiente de contabilizar"
        return ""

    def _outbox_columns(self) -> set:
        return {r[1] for r in self._conn.execute("PRAGMA table_info(hr_outbox)")}

    def _has_payment_reference(self) -> bool:
        return "payment_reference" in {
            r[1] for r in self._conn.execute("PRAGMA table_info(payroll_payments)")}


class ShiftQueryService(_HRQueryBase):
    def list_active(self, *, branch_id: str | None = None) -> list[dict]:
        if branch_id:
            return self._query(
                "SELECT id, name, start_time, end_time, break_minutes,"
                " late_tolerance_minutes FROM work_shifts WHERE active=1"
                " AND (branch_id=? OR branch_id IS NULL) ORDER BY name", (branch_id,))
        return self._query(
            "SELECT id, name, start_time, end_time, break_minutes,"
            " late_tolerance_minutes FROM work_shifts WHERE active=1 ORDER BY name")

    def assignments_for_employee(self, employee_id: str) -> list[dict]:
        return self._query(
            "SELECT a.id, a.work_shift_id, s.name AS shift_name, a.effective_from,"
            " a.effective_to, a.weekdays FROM shift_assignments a"
            " JOIN work_shifts s ON s.id=a.work_shift_id WHERE a.employee_id=?"
            " ORDER BY a.effective_from DESC", (employee_id,))


class HRDashboardQueryService(_HRQueryBase):
    def overview(self, *, work_date: str, branch_id: str | None = None) -> dict:
        """HR-24: todos los indicadores con EL MISMO alcance de sucursal; una
        entrada abierta es "en turno" (no ausencia) y la falta sólo cuenta
        contra un turno asignado ese día sin permiso aprobado."""
        branch_clause = " AND branch_id=?" if branch_id else ""
        branch_params: tuple = (branch_id,) if branch_id else ()
        day = date.fromisoformat(work_date)

        employees = self._query(
            "SELECT id FROM employees WHERE active=1" + branch_clause
            + " AND hire_date<=? AND (termination_date IS NULL OR termination_date>=?)",
            (*branch_params, work_date, work_date))
        active_ids = {r["id"] for r in employees}
        workdays = self._query(
            "SELECT employee_id, status, late_minutes, overtime_minutes FROM"
            " attendance_workdays WHERE work_date=?" + branch_clause,
            (work_date, *branch_params))
        by_employee = {w["employee_id"]: w for w in workdays}
        on_shift = sum(1 for w in workdays if w["status"] == "OPEN")
        finished = sum(1 for w in workdays if w["status"] in ("COMPLETE", "ADJUSTED"))
        late = sum(1 for w in workdays if (w["late_minutes"] or 0) > 0)
        overtime = sum(int(w["overtime_minutes"] or 0) for w in workdays)

        on_leave = {r["employee_id"] for r in self._query(
            "SELECT employee_id FROM leave_requests WHERE status='APPROVED'"
            " AND start_date<=? AND end_date>=?" + branch_clause,
            (work_date, work_date, *branch_params))}
        weekday = str(day.weekday())
        scheduled = set()
        for row in self._query(
                "SELECT employee_id, weekdays FROM shift_assignments WHERE effective_from<=?"
                " AND (effective_to IS NULL OR effective_to>=?)", (work_date, work_date)):
            if weekday in str(row["weekdays"]).split(","):
                scheduled.add(row["employee_id"])
        absences = sum(1 for employee_id in active_ids & scheduled
                       if employee_id not in by_employee and employee_id not in on_leave)

        incidents = self._scalar(
            "SELECT COUNT(*) FROM attendance_workdays WHERE status='INCIDENT'" + branch_clause,
            branch_params)
        pending_leaves = self._scalar(
            "SELECT COUNT(*) FROM leave_requests WHERE status='PENDING'" + branch_clause,
            branch_params)
        return {
            "active_employees": len(active_ids),
            "on_shift_now": on_shift,
            "present_today": on_shift + finished,
            "finished_today": finished,
            "absences_today": absences,
            "authorized_absences_today": len(active_ids & on_leave),
            "late_today": late,
            "pending_requests": pending_leaves,
            "overtime_minutes": overtime,
            "pending_incidents": incidents,
        }


class HROperationsQueryService(_HRQueryBase):
    """Lecturas de checador, conceptos capturados y préstamos (2026-10-14)."""

    def devices(self, *, branch_id: str | None = None) -> list[dict]:
        if not self._has_table("hr_time_clock_devices"):
            return []
        clause, params = (" WHERE d.branch_id=?", (branch_id,)) if branch_id else ("", ())
        return self._query(
            "SELECT d.id, d.code, d.name, d.kind, d.driver, d.active, d.last_synced_at,"
            " (SELECT COUNT(*) FROM hr_device_events e WHERE e.device_id=d.id"
            "  AND e.status='UNMATCHED') AS unmatched"
            f" FROM hr_time_clock_devices d{clause} ORDER BY d.code", params)

    def credentials(self, employee_id: str) -> list[dict]:
        if not self._has_table("hr_employee_credentials"):
            return []
        return self._query(
            "SELECT c.id, c.credential_type, c.label, c.active, c.created_at,"
            " COALESCE(d.code, 'Todos') AS device_code FROM hr_employee_credentials c"
            " LEFT JOIN hr_time_clock_devices d ON d.id=c.device_scope"
            " WHERE c.employee_id=? ORDER BY c.active DESC, c.created_at DESC", (employee_id,))

    def payroll_inputs(self, *, branch_id: str | None = None) -> list[dict]:
        if not self._has_table("payroll_inputs"):
            return []
        clause, params = (" WHERE i.branch_id=?", (branch_id,)) if branch_id else ("", ())
        return self._query(
            "SELECT i.id, e.employee_code, e.first_name || ' ' || e.last_name AS employee_name,"
            " i.concept, i.amount, i.applies_on, i.reason, i.status FROM payroll_inputs i"
            f" JOIN employees e ON e.id=i.employee_id{clause} ORDER BY i.applies_on DESC LIMIT 300",
            params)

    def loans(self, *, branch_id: str | None = None) -> list[dict]:
        if not self._has_table("employee_loans"):
            return []
        clause, params = (" WHERE l.branch_id=?", (branch_id,)) if branch_id else ("", ())
        rows = self._query(
            "SELECT l.id, e.employee_code, e.first_name || ' ' || e.last_name AS employee_name,"
            " l.kind, l.principal, l.installment, l.granted_on, l.status FROM employee_loans l"
            f" JOIN employees e ON e.id=l.employee_id{clause} ORDER BY l.granted_on DESC", params)
        for row in rows:
            applied = _decimal_sum(r["amount"] for r in self._query(
                "SELECT a.amount FROM payroll_loan_applications a JOIN payroll_runs r"
                " ON r.id=a.payroll_run_id WHERE a.loan_id=? AND r.status<>'CANCELLED'",
                (row["id"],)))
            row["balance"] = _money(Decimal(str(row["principal"])) - applied)
        return rows
