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
             " approved_at, operation_id, created_at, updated_at")

    def save(self, request: LeaveRequest) -> None:
        self._execute(
            f"INSERT INTO leave_requests ({self._COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (request.id, request.employee_id, request.branch_id, request.leave_type.value,
             request.start_date.isoformat(), request.end_date.isoformat(),
             request.requested_days, request.reason, request.status.value,
             request.requested_by_user_id, request.approved_by_user_id,
             request.approved_at, request.operation_id, request.created_at,
             request.updated_at))

    def update(self, request: LeaveRequest) -> None:
        self._execute(
            "UPDATE leave_requests SET status=?, approved_by_user_id=?, approved_at=?,"
            " updated_at=? WHERE id=?",
            (request.status.value, request.approved_by_user_id, request.approved_at,
             request.updated_at, request.id))

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
            created_at=row["created_at"], updated_at=row["updated_at"])


class PayrollRepository(HRRepositoryBase):
    _RUN_COLS = ("id, period_start, period_end, branch_id, payment_frequency, status,"
                 " generated_by_user_id, authorized_by_user_id, authorized_at, paid_at,"
                 " payment_id, operation_id, created_at, updated_at")
    _LINE_COLS = ("id, payroll_run_id, employee_id, concept, amount, currency_code,"
                  " is_deduction, quantity, notes")

    def save(self, run: PayrollRun) -> None:
        self._execute(
            f"INSERT INTO payroll_runs ({self._RUN_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run.id, run.period_start.isoformat(), run.period_end.isoformat(),
             run.branch_id, run.payment_frequency.value if run.payment_frequency else None,
             run.status.value, run.generated_by_user_id, run.authorized_by_user_id,
             run.authorized_at, run.paid_at, run.payment_id, run.operation_id,
             run.created_at, run.updated_at))
        for line in run.lines:
            self._save_line(line)

    def update(self, run: PayrollRun) -> None:
        self._execute(
            "UPDATE payroll_runs SET status=?, authorized_by_user_id=?, authorized_at=?,"
            " paid_at=?, payment_id=?, updated_at=? WHERE id=?",
            (run.status.value, run.authorized_by_user_id, run.authorized_at, run.paid_at,
             run.payment_id, run.updated_at, run.id))

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
            updated_at=row["updated_at"])
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
             " operation_id, paid_at")

    def save(self, payment: PayrollPayment) -> None:
        self._execute(
            f"INSERT INTO payroll_payments ({self._COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (payment.id, payment.payroll_run_id, payment.gross_amount.to_string(),
             payment.deductions_amount.to_string(), payment.net_amount.to_string(),
             payment.net_amount.currency_code, payment.payment_method.value,
             payment.authorized_by_user_id, payment.paid_by_user_id, payment.operation_id,
             payment.paid_at))

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
            authorized_by_user_id=row["authorized_by_user_id"], paid_at=row["paid_at"])
