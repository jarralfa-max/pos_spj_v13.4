"""Work shift, leave and payroll repositories."""

from __future__ import annotations

from datetime import date, time

from backend.domain.hr.entities import (
    LeaveRequest,
    PayrollLine,
    PayrollPayment,
    PayrollRun,
    ShiftAssignment,
    WorkShift,
)
from backend.domain.hr.enums import (
    LeaveStatus,
    LeaveType,
    PaymentFrequency,
    PaymentMethod,
    PayrollConcept,
    PayrollRunStatus,
)
from backend.domain.hr.value_objects import Money
from backend.infrastructure.db.repositories.hr.base import HRRepositoryBase


class WorkShiftRepository(HRRepositoryBase):
    _COLS = ("id, name, start_time, end_time, crosses_midnight, break_minutes,"
             " late_tolerance_minutes, branch_id, active, created_at")
    _ASSIGN_COLS = ("id, employee_id, work_shift_id, effective_from, effective_to,"
                    " weekdays, branch_id, created_at")

    def save(self, shift: WorkShift) -> None:
        self._execute(
            f"INSERT INTO work_shifts ({self._COLS}) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (shift.id, shift.name, shift.start_time.isoformat(), shift.end_time.isoformat(),
             int(shift.crosses_midnight), shift.break_minutes,
             shift.late_tolerance_minutes, shift.branch_id, int(shift.active),
             shift.created_at))

    def get(self, shift_id: str) -> WorkShift | None:
        row = self._query_one(f"SELECT {self._COLS} FROM work_shifts WHERE id=?", (shift_id,))
        return self._to_shift(row) if row else None

    def list_active(self, *, branch_id: str | None = None) -> list[WorkShift]:
        if branch_id:
            rows = self._query(
                f"SELECT {self._COLS} FROM work_shifts WHERE active=1"
                " AND (branch_id=? OR branch_id IS NULL) ORDER BY name", (branch_id,))
        else:
            rows = self._query(
                f"SELECT {self._COLS} FROM work_shifts WHERE active=1 ORDER BY name")
        return [self._to_shift(r) for r in rows]

    def save_assignment(self, assignment: ShiftAssignment) -> None:
        self._execute(
            f"INSERT INTO shift_assignments ({self._ASSIGN_COLS})"
            " VALUES (?,?,?,?,?,?,?,?)",
            (assignment.id, assignment.employee_id, assignment.work_shift_id,
             assignment.effective_from.isoformat(),
             assignment.effective_to.isoformat() if assignment.effective_to else None,
             ",".join(str(d) for d in assignment.weekdays), assignment.branch_id,
             assignment.created_at))

    def list_assignments(self, employee_id: str) -> list[ShiftAssignment]:
        rows = self._query(
            f"SELECT {self._ASSIGN_COLS} FROM shift_assignments WHERE employee_id=?"
            " ORDER BY effective_from", (employee_id,))
        return [ShiftAssignment(
            id=r["id"], employee_id=r["employee_id"], work_shift_id=r["work_shift_id"],
            effective_from=date.fromisoformat(r["effective_from"]),
            weekdays=tuple(int(d) for d in r["weekdays"].split(",") if d != ""),
            branch_id=r["branch_id"],
            effective_to=date.fromisoformat(r["effective_to"]) if r["effective_to"] else None,
            created_at=r["created_at"]) for r in rows]

    def find_assignment_for(self, employee_id: str, on_date: date) -> ShiftAssignment | None:
        row = self._query_one(
            f"SELECT {self._ASSIGN_COLS} FROM shift_assignments"
            " WHERE employee_id=? AND effective_from<=?"
            " AND (effective_to IS NULL OR effective_to>=?)"
            " ORDER BY effective_from DESC LIMIT 1",
            (employee_id, on_date.isoformat(), on_date.isoformat()))
        if row is None:
            return None
        weekday = on_date.weekday()
        weekdays = tuple(int(d) for d in row["weekdays"].split(",") if d != "")
        if weekday not in weekdays:
            return None
        return ShiftAssignment(
            id=row["id"], employee_id=row["employee_id"], work_shift_id=row["work_shift_id"],
            effective_from=date.fromisoformat(row["effective_from"]), weekdays=weekdays,
            branch_id=row["branch_id"],
            effective_to=date.fromisoformat(row["effective_to"]) if row["effective_to"] else None,
            created_at=row["created_at"])

    @staticmethod
    def _to_shift(row: dict) -> WorkShift:
        return WorkShift(
            id=row["id"], name=row["name"],
            start_time=time.fromisoformat(row["start_time"]),
            end_time=time.fromisoformat(row["end_time"]),
            crosses_midnight=bool(row["crosses_midnight"]),
            break_minutes=row["break_minutes"],
            late_tolerance_minutes=row["late_tolerance_minutes"],
            branch_id=row["branch_id"], active=bool(row["active"]),
            created_at=row["created_at"])


class LeaveRepository(HRRepositoryBase):
    _COLS = ("id, employee_id, branch_id, leave_type, start_date, end_date,"
             " requested_days, reason, status, requested_by_user_id, approved_by_user_id,"
             " approved_at, operation_id, created_at, updated_at,"
             " cancelled_by_user_id, cancelled_at, cancel_reason")

    def save(self, request: LeaveRequest) -> None:
        self._execute(
            f"INSERT INTO leave_requests ({self._COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (request.id, request.employee_id, request.branch_id, request.leave_type.value,
             request.start_date.isoformat(), request.end_date.isoformat(),
             request.requested_days, request.reason, request.status.value,
             request.requested_by_user_id, request.approved_by_user_id,
             request.approved_at, request.operation_id, request.created_at,
             request.updated_at, request.cancelled_by_user_id, request.cancelled_at,
             request.cancel_reason))

    def update(self, request: LeaveRequest) -> None:
        self._execute(
            "UPDATE leave_requests SET status=?, approved_by_user_id=?, approved_at=?,"
            " updated_at=?, cancelled_by_user_id=?, cancelled_at=?, cancel_reason=?"
            " WHERE id=?",
            (request.status.value, request.approved_by_user_id, request.approved_at,
             request.updated_at, request.cancelled_by_user_id, request.cancelled_at,
             request.cancel_reason, request.id))

    def list_approved_between(self, start: date, end: date, *,
                              employee_ids=None) -> list[LeaveRequest]:
        """HR-08: ausencias APROBADAS que tocan el periodo (alimentan la nómina)."""
        rows = self._query(
            f"SELECT {self._COLS} FROM leave_requests WHERE status='APPROVED'"
            " AND start_date<=? AND end_date>=?", (end.isoformat(), start.isoformat()))
        wanted = set(employee_ids) if employee_ids is not None else None
        return [self._to_entity(r) for r in rows
                if wanted is None or r["employee_id"] in wanted]

    def get(self, leave_id: str) -> LeaveRequest | None:
        row = self._query_one(f"SELECT {self._COLS} FROM leave_requests WHERE id=?", (leave_id,))
        return self._to_entity(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> LeaveRequest | None:
        row = self._query_one(
            f"SELECT {self._COLS} FROM leave_requests WHERE operation_id=?", (operation_id,))
        return self._to_entity(row) if row else None

    def list_by_employee(self, employee_id: str) -> list[LeaveRequest]:
        rows = self._query(
            f"SELECT {self._COLS} FROM leave_requests WHERE employee_id=?"
            " ORDER BY start_date DESC", (employee_id,))
        return [self._to_entity(r) for r in rows]

    def list_pending(self) -> list[LeaveRequest]:
        rows = self._query(
            f"SELECT {self._COLS} FROM leave_requests WHERE status='PENDING'"
            " ORDER BY start_date")
        return [self._to_entity(r) for r in rows]

    @staticmethod
    def _to_entity(row: dict) -> LeaveRequest:
        return LeaveRequest(
            id=row["id"], employee_id=row["employee_id"], branch_id=row["branch_id"],
            leave_type=LeaveType(row["leave_type"]),
            start_date=date.fromisoformat(row["start_date"]),
            end_date=date.fromisoformat(row["end_date"]),
            requested_days=row["requested_days"], reason=row["reason"],
            requested_by_user_id=row["requested_by_user_id"],
            operation_id=row["operation_id"], status=LeaveStatus(row["status"]),
            approved_by_user_id=row["approved_by_user_id"], approved_at=row["approved_at"],
            created_at=row["created_at"], updated_at=row["updated_at"],
            cancelled_by_user_id=row.get("cancelled_by_user_id"),
            cancelled_at=row.get("cancelled_at"), cancel_reason=row.get("cancel_reason"))


class PayrollRepository(HRRepositoryBase):
    _RUN_COLS = ("id, period_start, period_end, branch_id, payment_frequency, status,"
                 " generated_by_user_id, authorized_by_user_id, authorized_at, paid_at,"
                 " payment_id, operation_id, created_at, updated_at, run_type,"
                 " request_fingerprint, authorized_net_amount, original_run_id,"
                 " adjustment_reason, reversed_at, reversed_by_user_id, reversal_reason")
    _LINE_COLS = ("id, payroll_run_id, employee_id, concept, amount, currency_code,"
                  " is_deduction, quantity, notes")

    def save(self, run: PayrollRun) -> None:
        self._execute(
            f"INSERT INTO payroll_runs ({self._RUN_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run.id, run.period_start.isoformat(), run.period_end.isoformat(),
             run.branch_id, run.payment_frequency.value if run.payment_frequency else None,
             run.status.value, run.generated_by_user_id, run.authorized_by_user_id,
             run.authorized_at, run.paid_at, run.payment_id, run.operation_id,
             run.created_at, run.updated_at, run.run_type, run.request_fingerprint,
             run.authorized_net_amount, run.original_run_id, run.adjustment_reason,
             run.reversed_at, run.reversed_by_user_id, run.reversal_reason))
        for line in run.lines:
            self._save_line(line)

    def update(self, run: PayrollRun) -> None:
        self._execute(
            "UPDATE payroll_runs SET status=?, authorized_by_user_id=?, authorized_at=?,"
            " paid_at=?, payment_id=?, updated_at=?, authorized_net_amount=?,"
            " reversed_at=?, reversed_by_user_id=?, reversal_reason=? WHERE id=?",
            (run.status.value, run.authorized_by_user_id, run.authorized_at, run.paid_at,
             run.payment_id, run.updated_at, run.authorized_net_amount, run.reversed_at,
             run.reversed_by_user_id, run.reversal_reason, run.id))

    def save_extra_lines(self, run: PayrollRun, lines) -> None:
        for line in lines:
            self._save_line(line)

    def list_related(self, original_run_id: str) -> list[PayrollRun]:
        """Corridas complementarias vivas de una corrida original."""
        rows = self._query(
            f"SELECT {self._RUN_COLS} FROM payroll_runs WHERE original_run_id=?"
            " AND status<>'CANCELLED' ORDER BY created_at", (original_run_id,))
        return [self._hydrate(r) for r in rows]

    # ── cobertura (HR-10) ────────────────────────────────────────────────────
    def claim_coverage(self, run_id: str, employee_id: str, days) -> None:
        """Reserva cada día del empleado para esta corrida. La llave primaria
        UNIQUE(employee_id, coverage_date) hace IMPOSIBLE una segunda corrida
        ordinaria solapada: lanza ``sqlite3.IntegrityError``."""
        from backend.shared.ids import new_uuid
        for day in days:
            self._execute(
                "INSERT INTO payroll_coverage (id, employee_id, coverage_date, payroll_run_id)"
                " VALUES (?,?,?,?)", (new_uuid(), employee_id, day.isoformat(), run_id))

    def coverage_conflict(self, employee_id: str, start: date, end: date) -> dict | None:
        return self._query_one(
            "SELECT c.payroll_run_id, MIN(c.coverage_date) AS first_day,"
            " MAX(c.coverage_date) AS last_day, r.status FROM payroll_coverage c"
            " JOIN payroll_runs r ON r.id=c.payroll_run_id WHERE c.employee_id=?"
            " AND c.coverage_date BETWEEN ? AND ? GROUP BY c.payroll_run_id, r.status",
            (employee_id, start.isoformat(), end.isoformat()))

    def release_coverage(self, run_id: str) -> None:
        self._execute("DELETE FROM payroll_coverage WHERE payroll_run_id=?", (run_id,))

    def _save_line(self, line: PayrollLine) -> None:
        self._execute(
            f"INSERT INTO payroll_lines ({self._LINE_COLS}) VALUES (?,?,?,?,?,?,?,?,?)",
            (line.id, line.payroll_run_id, line.employee_id, line.concept.value,
             line.amount.to_string(), line.amount.currency_code, int(line.is_deduction),
             line.quantity, line.notes))

    def get(self, run_id: str) -> PayrollRun | None:
        row = self._query_one(f"SELECT {self._RUN_COLS} FROM payroll_runs WHERE id=?", (run_id,))
        return self._hydrate(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> PayrollRun | None:
        row = self._query_one(
            f"SELECT {self._RUN_COLS} FROM payroll_runs WHERE operation_id=?", (operation_id,))
        return self._hydrate(row) if row else None

    def list_runs(self, *, status: str | None = None) -> list[PayrollRun]:
        if status:
            rows = self._query(
                f"SELECT {self._RUN_COLS} FROM payroll_runs WHERE status=?"
                " ORDER BY period_start DESC", (status,))
        else:
            rows = self._query(
                f"SELECT {self._RUN_COLS} FROM payroll_runs ORDER BY period_start DESC LIMIT 200")
        return [self._hydrate(r) for r in rows]

    def _hydrate(self, row: dict) -> PayrollRun:
        run = PayrollRun(
            id=row["id"], period_start=date.fromisoformat(row["period_start"]),
            period_end=date.fromisoformat(row["period_end"]), branch_id=row["branch_id"],
            operation_id=row["operation_id"], status=PayrollRunStatus(row["status"]),
            payment_frequency=PaymentFrequency(row["payment_frequency"]) if row["payment_frequency"] else None,
            generated_by_user_id=row["generated_by_user_id"],
            authorized_by_user_id=row["authorized_by_user_id"],
            authorized_at=row["authorized_at"], paid_at=row["paid_at"],
            payment_id=row["payment_id"], created_at=row["created_at"],
            updated_at=row["updated_at"], run_type=row.get("run_type") or "ORDINARY",
            request_fingerprint=row.get("request_fingerprint"),
            authorized_net_amount=row.get("authorized_net_amount"),
            original_run_id=row.get("original_run_id"),
            adjustment_reason=row.get("adjustment_reason"),
            reversed_at=row.get("reversed_at"),
            reversed_by_user_id=row.get("reversed_by_user_id"),
            reversal_reason=row.get("reversal_reason"))
        for line_row in self._query(
                f"SELECT {self._LINE_COLS} FROM payroll_lines WHERE payroll_run_id=?",
                (row["id"],)):
            run.lines.append(PayrollLine(
                id=line_row["id"], payroll_run_id=line_row["payroll_run_id"],
                employee_id=line_row["employee_id"],
                concept=PayrollConcept(line_row["concept"]),
                amount=Money.from_string(line_row["amount"], line_row["currency_code"]),
                is_deduction=bool(line_row["is_deduction"]), quantity=line_row["quantity"],
                notes=line_row["notes"]))
        return run


class PayrollPaymentRepository(HRRepositoryBase):
    _COLS = ("id, payroll_run_id, gross_amount, deductions_amount, net_amount,"
             " currency_code, payment_method, authorized_by_user_id, paid_by_user_id,"
             " operation_id, paid_at, payment_reference")

    def save(self, payment: PayrollPayment) -> None:
        self._execute(
            f"INSERT INTO payroll_payments ({self._COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (payment.id, payment.payroll_run_id, payment.gross_amount.to_string(),
             payment.deductions_amount.to_string(), payment.net_amount.to_string(),
             payment.net_amount.currency_code, payment.payment_method.value,
             payment.authorized_by_user_id, payment.paid_by_user_id, payment.operation_id,
             payment.paid_at, payment.payment_reference))

    def save_allocation(self, *, payment_id: str, run_id: str, employee_id: str,
                        net_amount) -> None:
        """HR-11: cuánto recibe cada empleado; la suma es el pago y el asiento."""
        from backend.shared.ids import new_uuid
        self._execute(
            "INSERT INTO payroll_payment_allocations (id, payroll_payment_id, payroll_run_id,"
            " employee_id, net_amount, currency_code) VALUES (?,?,?,?,?,?)",
            (new_uuid(), payment_id, run_id, employee_id, net_amount.to_string(),
             net_amount.currency_code))

    def mark_reversed(self, payment_id: str, reversed_at: str) -> None:
        self._execute("UPDATE payroll_payments SET reversed_at=? WHERE id=?",
                      (reversed_at, payment_id))

    def allocations(self, payment_id: str) -> list[dict]:
        return self._query(
            "SELECT employee_id, net_amount, currency_code FROM payroll_payment_allocations"
            " WHERE payroll_payment_id=? ORDER BY employee_id", (payment_id,))

    def get(self, payment_id: str) -> PayrollPayment | None:
        row = self._query_one(f"SELECT {self._COLS} FROM payroll_payments WHERE id=?", (payment_id,))
        return self._to_entity(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> PayrollPayment | None:
        row = self._query_one(
            f"SELECT {self._COLS} FROM payroll_payments WHERE operation_id=?", (operation_id,))
        return self._to_entity(row) if row else None

    def find_by_run(self, payroll_run_id: str) -> PayrollPayment | None:
        row = self._query_one(
            f"SELECT {self._COLS} FROM payroll_payments WHERE payroll_run_id=?", (payroll_run_id,))
        return self._to_entity(row) if row else None

    @staticmethod
    def _to_entity(row: dict) -> PayrollPayment:
        currency = row["currency_code"]
        return PayrollPayment(
            id=row["id"], payroll_run_id=row["payroll_run_id"],
            gross_amount=Money.from_string(row["gross_amount"], currency),
            deductions_amount=Money.from_string(row["deductions_amount"], currency),
            net_amount=Money.from_string(row["net_amount"], currency),
            payment_method=PaymentMethod(row["payment_method"]),
            operation_id=row["operation_id"],
            paid_by_user_id=row["paid_by_user_id"],
            authorized_by_user_id=row["authorized_by_user_id"], paid_at=row["paid_at"],
            payment_reference=row.get("payment_reference"))
