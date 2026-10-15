"""Payroll use cases — the single canonical sequence.

GeneratePayrollRun → AuthorizePayrollRun → PayPayrollRun (→ CancelPayrollRun).

Separation is mandatory: generation, authorization and payment are distinct
operations, never a single button. Payment is idempotent and publishes exactly
one PAYROLL_PAID event, which the finance bridge consumes to post the ledger —
no duplicated financial movement, no double pay, no editing a paid run.

Auditoría RRHH cebf67a:
- HR-01/02: permiso ``RRHH.nomina.*`` y alcance sobre la sucursal de la corrida.
- HR-07/08/09: la corrida se arma con DÍAS PAGABLES por empleado — vigencia del
  vínculo (alta/baja), tarifa vigente ese día, ausencias aprobadas por tipo y
  faltas contra turno asignado — con una sola política por modalidad.
- HR-10: un día de un empleado lo cubre una sola corrida ordinaria viva
  (``payroll_coverage``); la misma clave con otro contenido es un conflicto.
- HR-11/27: neto individual no negativo; autorizar congela el importe.
- HR-04/29: el pago exige método (y referencia si no es efectivo), guarda el
  reparto por empleado y publica un sobre con el MISMO ``event_id`` del outbox.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone

from backend.application.use_cases.hr.hr_result import HRResult
from decimal import Decimal

from backend.domain.hr.entities import PayrollLine, PayrollPayment, PayrollRun
from backend.domain.hr.enums import (
    LeaveType,
    PaymentMethod,
    PayrollConcept,
    PayrollRunStatus,
)
from backend.domain.hr.services.withholding import NoWithholdingProvider
from backend.domain.hr.value_objects import Money
from backend.domain.hr.exceptions import HRDomainError
from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy, HRPermission
from backend.domain.hr.policies.payroll_policy import PayrollPolicy
from backend.domain.hr.services.attendance_calculator import (
    FINISHED_STATUSES,
    PENDING_STATUSES,
)
from backend.domain.hr.services.payroll_calculator import (
    EmployeePayrollInput,
    PayableDay,
    PayableDayKind,
    PayrollCalculator,
)
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid

#: Cómo paga la nómina cada tipo de ausencia APROBADA (regla declarada; revisable).
#: La incapacidad la cubre el IMSS, no el patrón: se descuenta del sueldo fijo.
LEAVE_PAY_POLICY: dict[LeaveType, PayableDayKind] = {
    LeaveType.VACATION: PayableDayKind.VACATION,
    LeaveType.PAID_LEAVE: PayableDayKind.PAID_LEAVE,
    LeaveType.ABSENCE_JUSTIFICATION: PayableDayKind.PAID_LEAVE,
    LeaveType.UNPAID_LEAVE: PayableDayKind.UNPAID_LEAVE,
    LeaveType.SICK_LEAVE: PayableDayKind.UNPAID_LEAVE,
}

#: Métodos que necesitan referencia del movimiento (folio SPEI, número de cheque).
_REFERENCED_METHODS = frozenset({PaymentMethod.BANK_TRANSFER, PaymentMethod.CHECK})


def _fingerprint(period_start: date, period_end: date, branch_id: str | None,
                 run_type: str) -> str:
    raw = f"{period_start.isoformat()}|{period_end.isoformat()}|{branch_id or ''}|{run_type}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _days(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


class _CoverageOverlap(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class GeneratePayrollRunUseCase:
    """Builds a multi-employee run from salaries + attendance for the period."""

    def __init__(self, authorization: AuthorizationPolicy | None = None,
                 *, calculator: PayrollCalculator | None = None,
                 withholding_provider=None) -> None:
        self._auth = authorization or AuthorizationPolicy()
        self._calculator = calculator or PayrollCalculator()
        self._withholdings = withholding_provider or NoWithholdingProvider()

    def execute(self, connection, *, actor_user_id: str, period_start: date,
                period_end: date, operation_id: str, branch_id: str | None = None,
                today: date | None = None) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.PAYROLL_GENERATE)
        self._auth.require_branch(actor_user_id, branch_id)
        if period_end < period_start:
            return HRResult.fail("El fin del periodo no puede ser anterior al inicio",
                                 "VALIDATION", operation_id=operation_id)
        fingerprint = _fingerprint(period_start, period_end, branch_id, "ORDINARY")
        today = today or date.today()
        try:
            with HRUnitOfWork(connection) as uow:
                existing = uow.payroll.find_by_operation_id(operation_id)
                if existing is not None:
                    if existing.request_fingerprint and existing.request_fingerprint != fingerprint:
                        return HRResult.fail(
                            "La clave de la operación ya se usó con otro periodo o sucursal",
                            "IDEMPOTENCY_CONFLICT", operation_id=operation_id)
                    return HRResult.ok("Corrida ya generada", entity_id=existing.id,
                                       operation_id=operation_id)
                employees = uow.employees.list_employed_between(
                    period_start, period_end, branch_id=branch_id)
                if not employees:
                    return HRResult.fail("No hay empleados vigentes en el periodo",
                                         "NO_EMPLOYEES", operation_id=operation_id)
                run = PayrollRun.create(period_start, period_end, operation_id,
                                        branch_id=branch_id,
                                        generated_by_user_id=actor_user_id)
                run.request_fingerprint = fingerprint
                ids = [e.id for e in employees]
                workdays = {(w.employee_id, w.work_date): w for w in
                            uow.attendance.list_workdays_between(
                                period_start, period_end, employee_ids=ids)}
                leaves: dict[str, list] = {}
                for leave in uow.leaves.list_approved_between(
                        period_start, period_end, employee_ids=ids):
                    leaves.setdefault(leave.employee_id, []).append(leave)

                pending = 0
                applied_inputs: list[str] = []
                loan_applications: list[tuple[str, Decimal]] = []
                for employee in employees:
                    days = self._payable_days(uow, employee, period_start, period_end,
                                              workdays, leaves.get(employee.id, []), today)
                    pending += sum(1 for d in days if d.kind is PayableDayKind.PENDING)
                    item = EmployeePayrollInput(employee=employee, days=tuple(days))
                    lines = self._calculator.build_lines(run.id, item)
                    lines += self._captured_perceptions(uow, run, employee, period_start,
                                                        period_end, applied_inputs)
                    for concept, amount, note in self._withholdings.withholdings(
                            employee, list(lines), period_start=period_start,
                            period_end=period_end):
                        lines.append(PayrollLine.create(run.id, employee.id, concept, amount,
                                                        is_deduction=True, notes=note))
                    lines += self._loan_installments(uow, run, employee, period_end, lines,
                                                     loan_applications)
                    for line in lines:
                        run.add_line(line)
                run.mark_calculated()
                uow.payroll.save(run)
                for input_id in applied_inputs:
                    uow.payroll_inputs.set_status(input_id, "APPLIED", payroll_run_id=run.id)
                for loan_id, amount in loan_applications:
                    uow.loans.apply(loan_id, run.id, amount)
                for employee in employees:
                    covered = [day for day in _days(period_start, period_end)
                               if employee.is_employed_on(day)]
                    try:
                        uow.payroll.claim_coverage(run.id, employee.id, covered)
                    except sqlite3.IntegrityError:
                        conflict = uow.payroll.coverage_conflict(
                            employee.id, period_start, period_end) or {}
                        raise _CoverageOverlap(
                            f"{employee.employee_code} ya está en la corrida "
                            f"{str(conflict.get('payroll_run_id', ''))[:8]} "
                            f"({conflict.get('first_day', '')} a {conflict.get('last_day', '')}); "
                            "cancélela o genere un periodo sin solape") from None
                uow.audit.record(action="PAYROLL_RUN_GENERATED", actor_user_id=actor_user_id,
                                 entity_type="payroll_run", entity_id=run.id,
                                 detail=f"{period_start}..{period_end}",
                                 operation_id=operation_id)
                uow.outbox.enqueue(new_uuid(), EventName.PAYROLL_RUN_GENERATED.value,
                                   json.dumps({"payroll_run_id": run.id,
                                               "employees": len(employees)}), operation_id)
        except _CoverageOverlap as overlap:
            return HRResult.fail(overlap.message, "PAYROLL_OVERLAP", operation_id=operation_id)
        message = "Corrida generada"
        if pending:
            message += (f"; {pending} jornada(s) pendiente(s) de resolver antes de autorizar")
        return HRResult.ok(message, entity_id=run.id, operation_id=operation_id,
                           net=run.net_amount().to_string(), pending_attendance=pending)

    @staticmethod
    def _captured_perceptions(uow, run, employee, start, end, applied: list) -> list:
        """Bonos, comisiones y ajustes APROBADOS cuya fecha cae en el periodo."""
        lines = []
        for row in uow.payroll_inputs.approved_for(employee.id, start, end):
            lines.append(PayrollLine.create(
                run.id, employee.id, PayrollConcept(row["concept"]),
                Money.from_string(row["amount"], row["currency_code"] or "MXN"),
                is_deduction=False, notes=row["reason"]))
            applied.append(row["id"])
        return lines

    @staticmethod
    def _loan_installments(uow, run, employee, period_end, lines, applications: list) -> list:
        """Abono de cada préstamo/anticipo vigente: el pactado, sin pasar del
        saldo y SIN dejar el neto del empleado negativo (lo que no alcance queda
        para la siguiente nómina)."""
        net = Decimal("0")
        for line in lines:
            net += -line.amount.amount if line.is_deduction else line.amount.amount
        extra = []
        for loan in uow.loans.active_for(employee.id, as_of=period_end):
            remaining = Decimal(loan["principal"]) - uow.loans.applied_total(loan["id"])
            amount = min(Decimal(loan["installment"]), remaining, max(net, Decimal("0")))
            if amount <= 0:
                continue
            concept = (PayrollConcept.ADVANCE_DEDUCTION if loan["kind"] == "ADVANCE"
                       else PayrollConcept.LOAN_DEDUCTION)
            extra.append(PayrollLine.create(
                run.id, employee.id, concept, Money(amount, loan["currency_code"] or "MXN"),
                is_deduction=True,
                notes=f"Saldo antes del abono {format(remaining, 'f')} — {loan['reason']}"))
            applications.append((loan["id"], amount))
            net -= amount
        return extra

    @staticmethod
    def _payable_days(uow, employee, start: date, end: date, workdays, leaves,
                      today: date) -> list[PayableDay]:
        days: list[PayableDay] = []
        for day in _days(start, end):
            if not employee.is_employed_on(day):
                continue
            rate = uow.salary_history.daily_rate_on(employee, day)
            workday = workdays.get((employee.id, day))
            leave = next((lv for lv in leaves if lv.covers(day)), None)
            if workday is not None and workday.status in FINISHED_STATUSES:
                days.append(PayableDay(day, rate, PayableDayKind.WORKED,
                                       worked_minutes=workday.worked_minutes,
                                       overtime_minutes=workday.overtime_minutes,
                                       late_minutes=workday.late_minutes))
            elif leave is not None:
                days.append(PayableDay(day, rate, LEAVE_PAY_POLICY.get(
                    leave.leave_type, PayableDayKind.PAID_LEAVE)))
            elif workday is not None and workday.status in PENDING_STATUSES:
                days.append(PayableDay(day, rate, PayableDayKind.PENDING,
                                       worked_minutes=workday.worked_minutes))
            elif day > today:
                days.append(PayableDay(day, rate, PayableDayKind.FUTURE))
            elif uow.shifts.find_assignment_for(employee.id, day) is not None:
                days.append(PayableDay(day, rate, PayableDayKind.ABSENCE))
            else:
                days.append(PayableDay(day, rate, PayableDayKind.REST))
        return days


def _pending_attendance(uow, run: PayrollRun) -> tuple[int, int]:
    ids = set(run.employee_ids())
    open_days = sum(1 for w in uow.attendance.list_workdays_between(
        run.period_start, run.period_end, employee_ids=ids) if w.status in PENDING_STATUSES)
    adjustments = uow.adjustments.count_pending_between(run.period_start, run.period_end, ids)
    return open_days, adjustments


class AuthorizePayrollRunUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()
        self._policy = PayrollPolicy()

    def execute(self, connection, *, actor_user_id: str, payroll_run_id: str,
                operation_id: str) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.PAYROLL_AUTHORIZE)
        with HRUnitOfWork(connection) as uow:
            run = uow.payroll.get(payroll_run_id)
            if run is None:
                return HRResult.fail("La corrida no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            self._auth.require_branch(actor_user_id, run.branch_id)
            open_days, adjustments = _pending_attendance(uow, run)
            if open_days or adjustments:
                return HRResult.fail(
                    f"Hay asistencia sin resolver en el periodo ({open_days} jornada(s) "
                    f"abierta(s) o con incidencia, {adjustments} ajuste(s) pendiente(s)); "
                    "resuélvala y vuelva a generar la corrida", "PENDING_ATTENDANCE",
                    operation_id=operation_id)
            try:
                self._policy.enforce_can_authorize(run, actor_user_id)
                run.authorize(actor_user_id)
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.payroll.update(run)
            uow.audit.record(action="PAYROLL_RUN_AUTHORIZED", actor_user_id=actor_user_id,
                             entity_type="payroll_run", entity_id=run.id,
                             detail=run.authorized_net_amount or "",
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
                paid_at: datetime | None = None,
                payment_reference: str | None = None) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.PAYROLL_PAY)
        try:
            method = PaymentMethod(str(payment_method or "").strip())
        except ValueError:
            return HRResult.fail("Seleccione el método de pago", "VALIDATION",
                                 operation_id=operation_id)
        reference = str(payment_reference or "").strip() or None
        if method in _REFERENCED_METHODS and not reference:
            return HRResult.fail("La transferencia o el cheque requieren su referencia",
                                 "VALIDATION", operation_id=operation_id)
        paid_at = paid_at or datetime.now(timezone.utc)
        with HRUnitOfWork(connection) as uow:
            run = uow.payroll.get(payroll_run_id)
            if run is None:
                return HRResult.fail("La corrida no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            self._auth.require_branch(actor_user_id, run.branch_id)
            # Idempotency: a run already paid returns its existing payment.
            existing_payment = uow.payroll_payments.find_by_run(payroll_run_id)
            if existing_payment is not None:
                return HRResult.ok("La corrida ya fue pagada", entity_id=existing_payment.id,
                                   operation_id=operation_id)
            try:
                self._policy.enforce_can_pay(run)
                payment = PayrollPayment(
                    id=new_uuid(), payroll_run_id=run.id, net_amount=run.net_amount(),
                    gross_amount=run.gross_amount(),
                    deductions_amount=run.deductions_amount(),
                    payment_method=method, operation_id=operation_id,
                    paid_by_user_id=actor_user_id,
                    authorized_by_user_id=run.authorized_by_user_id or "",
                    employee_ids=run.employee_ids(), paid_at=paid_at.isoformat(),
                    payment_reference=reference)
                run.mark_paid(payment.id)
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "PAYROLL_STATE", operation_id=operation_id)
            uow.payroll_payments.save(payment)
            loan_deductions = Money.zero(payment.net_amount.currency_code)
            for line in run.lines:
                if line.concept in (PayrollConcept.LOAN_DEDUCTION,
                                    PayrollConcept.ADVANCE_DEDUCTION):
                    loan_deductions = loan_deductions.add(line.amount)
            allocations = run.employee_nets()
            for employee_id, net in allocations.items():
                uow.payroll_payments.save_allocation(
                    payment_id=payment.id, run_id=run.id, employee_id=employee_id,
                    net_amount=net)
            uow.payroll.update(run)
            uow.audit.record(action="PAYROLL_PAID", actor_user_id=actor_user_id,
                             entity_type="payroll_run", entity_id=run.id,
                             detail=f"{payment.net_amount.to_string()} {method.value}"
                                    + (f" ref {reference}" if reference else ""),
                             operation_id=operation_id)
            # Canonical PAYROLL_PAID for the finance bounded context (one ledger
            # entry). HR-04: el sobre lleva el MISMO event_id que su fila de outbox.
            event_id = new_uuid()
            uow.outbox.enqueue(event_id, EventName.PAYROLL_PAID.value, json.dumps({
                "event_id": event_id,
                "event_name": EventName.PAYROLL_PAID.value,
                "operation_id": operation_id,
                "occurred_at": payment.paid_at,
                "currency_code": payment.net_amount.currency_code,
                "payroll_payment_id": payment.id,
                "payroll_run_id": run.id,
                "branch_id": run.branch_id,
                "period_start": run.period_start.isoformat(),
                "period_end": run.period_end.isoformat(),
                "employee_ids": list(payment.employee_ids),
                "allocations": [{"employee_id": e, "net_amount": n.to_string()}
                                for e, n in allocations.items()],
                "gross_amount": payment.gross_amount.to_string(),
                "deductions_amount": payment.deductions_amount.to_string(),
                "net_amount": payment.net_amount.to_string(),
                "gross_salaries": payment.gross_amount.to_string(),
                "social_security": "0.00",
                "net_paid": payment.net_amount.to_string(),
                "loan_deductions": loan_deductions.to_string(),
                "run_type": run.run_type,
                "original_run_id": run.original_run_id,
                "payment_method": payment.payment_method.value,
                "payment_reference": reference,
                "paid_at": payment.paid_at,
                "authorized_by_user_id": payment.authorized_by_user_id,
                "paid_by_user_id": payment.paid_by_user_id,
            }), operation_id)
            _settle_finished_loans(uow, run.id)
        return HRResult.ok("Nómina pagada", entity_id=payment.id, operation_id=operation_id,
                           net=payment.net_amount.to_string())


class CancelPayrollRunUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, payroll_run_id: str,
                operation_id: str) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.PAYROLL_CANCEL)
        with HRUnitOfWork(connection) as uow:
            run = uow.payroll.get(payroll_run_id)
            if run is None:
                return HRResult.fail("La corrida no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            self._auth.require_branch(actor_user_id, run.branch_id)
            try:
                run.cancel()
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "PAYROLL_STATE", operation_id=operation_id)
            uow.payroll.update(run)
            # HR-10: cancelar libera los días para regenerar el periodo; los
            # conceptos y abonos de préstamo vuelven a quedar disponibles.
            uow.payroll.release_coverage(run.id)
            uow.payroll_inputs.release_run(run.id)
            uow.loans.release_run(run.id)
            uow.audit.record(action="PAYROLL_CANCELLED", actor_user_id=actor_user_id,
                             entity_type="payroll_run", entity_id=run.id, detail="",
                             operation_id=operation_id)
            uow.outbox.enqueue(new_uuid(), EventName.PAYROLL_CANCELLED.value,
                               json.dumps({"payroll_run_id": run.id}), operation_id)
        return HRResult.ok("Corrida cancelada", entity_id=payroll_run_id,
                           operation_id=operation_id)


#: Estados en los que una corrida ya no se modifica.
CLOSED_RUN_STATUSES = frozenset({PayrollRunStatus.AUTHORIZED, PayrollRunStatus.PAID})


def _settle_finished_loans(uow, payroll_run_id: str) -> None:
    rows = uow.connection.execute(
        "SELECT DISTINCT loan_id FROM payroll_loan_applications WHERE payroll_run_id=?",
        (payroll_run_id,)).fetchall()
    for (loan_id,) in rows:
        loan = uow.loans.get(loan_id)
        if loan and Decimal(loan["principal"]) - uow.loans.applied_total(loan_id) <= 0:
            uow.loans.set_status(loan_id, "PAID")
