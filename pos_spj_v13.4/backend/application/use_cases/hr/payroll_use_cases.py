"""Payroll use cases — the single canonical sequence.

GeneratePayrollRun → AuthorizePayrollRun → PayPayrollRun (→ CancelPayrollRun).

Separation is mandatory: generation, authorization and payment are distinct
operations, never a single button. Payment is idempotent and publishes exactly
one PAYROLL_PAID event, which the finance bridge consumes to post the ledger —
no duplicated financial movement, no double pay, no editing a paid run.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from backend.application.use_cases.hr.hr_result import HRResult
from backend.domain.hr.entities import PayrollPayment, PayrollRun
from backend.domain.hr.enums import PaymentMethod, PayrollRunStatus
from backend.domain.hr.exceptions import HRDomainError
from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy
from backend.domain.hr.policies.payroll_policy import PayrollPolicy
from backend.domain.hr.services.attendance_calculator import AttendanceCalculator
from backend.domain.hr.services.payroll_calculator import (
    EmployeePayrollInput,
    PayrollCalculator,
)
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


class GeneratePayrollRunUseCase:
    """Builds a multi-employee run from salaries + attendance for the period."""

    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()
        self._calculator = PayrollCalculator()
        self._attendance = AttendanceCalculator()

    def execute(self, connection, *, actor_user_id: str, period_start: date,
                period_end: date, operation_id: str, branch_id: str | None = None) -> HRResult:
        self._auth.require(actor_user_id, "hr.payroll.generate")
        with HRUnitOfWork(connection) as uow:
            existing = uow.payroll.find_by_operation_id(operation_id)
            if existing is not None:
                return HRResult.ok("Corrida ya generada", entity_id=existing.id,
                                   operation_id=operation_id)
            run = PayrollRun.create(period_start, period_end, operation_id,
                                    branch_id=branch_id,
                                    generated_by_user_id=actor_user_id)
            employees = uow.employees.list_active(branch_id=branch_id)
            if not employees:
                return HRResult.fail("No hay empleados activos para la corrida",
                                     "NO_EMPLOYEES", operation_id=operation_id)
            for employee in employees:
                workdays = [
                    w for w in uow.attendance.list_workdays()
                    if w.employee_id == employee.id
                    and period_start <= w.work_date <= period_end
                ]
                summary = self._attendance.summarize(workdays)
                worked_days = summary.present_days or self._period_days(period_start, period_end)
                item = EmployeePayrollInput(
                    employee=employee, worked_days=worked_days,
                    overtime_minutes=summary.overtime_minutes,
                    late_minutes=summary.late_minutes)
                for line in self._calculator.build_lines(run.id, item):
                    run.add_line(line)
            run.mark_calculated()
            uow.payroll.save(run)
            uow.audit.record(action="PAYROLL_RUN_GENERATED", actor_user_id=actor_user_id,
                             entity_type="payroll_run", entity_id=run.id,
                             detail=f"{period_start}..{period_end}",
                             operation_id=operation_id)
            uow.outbox.enqueue(new_uuid(), EventName.PAYROLL_RUN_GENERATED.value,
                               json.dumps({"payroll_run_id": run.id,
                                           "employees": len(employees)}), operation_id)
        return HRResult.ok("Corrida generada", entity_id=run.id, operation_id=operation_id,
                           net=run.net_amount().to_string())

    @staticmethod
    def _period_days(start: date, end: date) -> int:
        return (end - start).days + 1


class AuthorizePayrollRunUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()
        self._policy = PayrollPolicy()

    def execute(self, connection, *, actor_user_id: str, payroll_run_id: str,
                operation_id: str) -> HRResult:
        self._auth.require(actor_user_id, "hr.payroll.authorize")
        with HRUnitOfWork(connection) as uow:
            run = uow.payroll.get(payroll_run_id)
            if run is None:
                return HRResult.fail("La corrida no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            try:
                self._policy.enforce_can_authorize(run, actor_user_id)
                run.authorize(actor_user_id)
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.payroll.update(run)
            uow.audit.record(action="PAYROLL_RUN_AUTHORIZED", actor_user_id=actor_user_id,
                             entity_type="payroll_run", entity_id=run.id, detail="",
                             operation_id=operation_id)
            uow.outbox.enqueue(new_uuid(), EventName.PAYROLL_RUN_AUTHORIZED.value,
                               json.dumps({"payroll_run_id": run.id}), operation_id)
        return HRResult.ok("Corrida autorizada", entity_id=payroll_run_id,
                           operation_id=operation_id)


class PayPayrollRunUseCase:
    """Idempotent payment. Publishes one PAYROLL_PAID for finance to post."""

    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()
        self._policy = PayrollPolicy()

    def execute(self, connection, *, actor_user_id: str, payroll_run_id: str,
                payment_method: str, operation_id: str,
                paid_at: datetime | None = None) -> HRResult:
        self._auth.require(actor_user_id, "hr.payroll.pay")
        paid_at = paid_at or datetime.now(timezone.utc)
        with HRUnitOfWork(connection) as uow:
            run = uow.payroll.get(payroll_run_id)
            if run is None:
                return HRResult.fail("La corrida no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            # Idempotency: a run already paid returns its existing payment.
            existing_payment = uow.payroll_payments.find_by_run(payroll_run_id)
            if existing_payment is not None:
                return HRResult.ok("La corrida ya fue pagada", entity_id=existing_payment.id,
                                   operation_id=operation_id)
            try:
                self._policy.enforce_can_pay(run)
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "PAYROLL_STATE", operation_id=operation_id)

            payment = PayrollPayment(
                id=new_uuid(), payroll_run_id=run.id, net_amount=run.net_amount(),
                gross_amount=run.gross_amount(), deductions_amount=run.deductions_amount(),
                payment_method=PaymentMethod(payment_method), operation_id=operation_id,
                paid_by_user_id=actor_user_id,
                authorized_by_user_id=run.authorized_by_user_id or "",
                employee_ids=run.employee_ids(), paid_at=paid_at.isoformat())
            uow.payroll_payments.save(payment)
            run.mark_paid(payment.id)
            uow.payroll.update(run)
            uow.audit.record(action="PAYROLL_PAID", actor_user_id=actor_user_id,
                             entity_type="payroll_run", entity_id=run.id,
                             detail=payment.net_amount.to_string(), operation_id=operation_id)
            # Canonical PAYROLL_PAID for the finance bounded context (one ledger entry).
            uow.outbox.enqueue(new_uuid(), EventName.PAYROLL_PAID.value, json.dumps({
                "event_id": new_uuid(),
                "operation_id": operation_id,
                "payroll_payment_id": payment.id,
                "payroll_run_id": run.id,
                "branch_id": run.branch_id,
                "employee_ids": list(payment.employee_ids),
                "gross_amount": payment.gross_amount.to_string(),
                "deductions_amount": payment.deductions_amount.to_string(),
                "net_amount": payment.net_amount.to_string(),
                "gross_salaries": payment.gross_amount.to_string(),
                "social_security": "0.00",
                "net_paid": payment.net_amount.to_string(),
                "payment_method": payment.payment_method.value,
                "paid_at": payment.paid_at,
                "authorized_by_user_id": payment.authorized_by_user_id,
                "paid_by_user_id": payment.paid_by_user_id,
            }), operation_id)
        return HRResult.ok("Nómina pagada", entity_id=payment.id, operation_id=operation_id,
                           net=payment.net_amount.to_string())


class CancelPayrollRunUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, payroll_run_id: str,
                operation_id: str) -> HRResult:
        self._auth.require(actor_user_id, "hr.payroll.cancel")
        with HRUnitOfWork(connection) as uow:
            run = uow.payroll.get(payroll_run_id)
            if run is None:
                return HRResult.fail("La corrida no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            try:
                run.cancel()
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "PAYROLL_STATE", operation_id=operation_id)
            uow.payroll.update(run)
            uow.audit.record(action="PAYROLL_CANCELLED", actor_user_id=actor_user_id,
                             entity_type="payroll_run", entity_id=run.id, detail="",
                             operation_id=operation_id)
            uow.outbox.enqueue(new_uuid(), EventName.PAYROLL_CANCELLED.value,
                               json.dumps({"payroll_run_id": run.id}), operation_id)
        return HRResult.ok("Corrida cancelada", entity_id=payroll_run_id,
                           operation_id=operation_id)
