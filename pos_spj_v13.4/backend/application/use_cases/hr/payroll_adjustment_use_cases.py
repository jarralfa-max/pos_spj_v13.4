"""Corrección de nómina ya pagada (pendientes de la auditoría RR. HH., 2026-10-14).

* ``GenerateComplementaryPayrollRunUseCase`` — recalcula el periodo de una corrida
  PAGADA con lo que hoy se sabe (ajustes de asistencia aprobados, permisos,
  historial salarial) y paga SÓLO la diferencia a favor del empleado, con motivo y
  referencia a la original. No reclama días (la original ya los cubre). Lo pagado
  de más no se descuenta solo: se informa para resolverlo (anticipo o ajuste).
* ``ReversePayrollPaymentUseCase`` — un pago registrado por error: la corrida queda
  cancelada con traza, se liberan días, conceptos y abonos de préstamo, y Finanzas
  revierte el asiento (o, si nunca se contabilizó, el evento se anula en la cola).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.application.use_cases.hr.hr_result import HRResult
from backend.application.use_cases.hr.payroll_use_cases import GeneratePayrollRunUseCase
from backend.domain.hr.entities import PayrollLine, PayrollRun
from backend.domain.hr.enums import PayrollConcept, PayrollRunStatus
from backend.domain.hr.exceptions import HRDomainError
from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy, HRPermission
from backend.domain.hr.services.payroll_calculator import EmployeePayrollInput, PayrollCalculator
from backend.domain.hr.value_objects import Money
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid

#: Conceptos que salen del cálculo de días/horas (lo que una complementaria corrige).
CALCULATED_CONCEPTS = frozenset({
    PayrollConcept.BASE_SALARY, PayrollConcept.OVERTIME, PayrollConcept.VACATION,
    PayrollConcept.PAID_LEAVE, PayrollConcept.ABSENCE_DEDUCTION,
    PayrollConcept.LATE_DEDUCTION,
})
PAYROLL_PAYMENT_REVERSED = "PAYROLL_PAYMENT_REVERSED"


def _signed(line: PayrollLine) -> Decimal:
    return -line.amount.amount if line.is_deduction else line.amount.amount


class GenerateComplementaryPayrollRunUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None,
                 *, calculator: PayrollCalculator | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()
        self._calculator = calculator or PayrollCalculator()

    def execute(self, connection, *, actor_user_id: str, original_run_id: str, reason: str,
                operation_id: str, employee_ids: list[str] | None = None,
                today: date | None = None) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.PAYROLL_COMPLEMENTARY)
        if not str(reason or "").strip():
            return HRResult.fail("La corrida complementaria requiere motivo", "VALIDATION",
                                 operation_id=operation_id)
        today = today or date.today()
        with HRUnitOfWork(connection) as uow:
            existing = uow.payroll.find_by_operation_id(operation_id)
            if existing is not None:
                return HRResult.ok("Corrida complementaria ya generada", entity_id=existing.id,
                                   operation_id=operation_id)
            original = uow.payroll.get(original_run_id)
            if original is None:
                return HRResult.fail("La corrida original no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            self._auth.require_branch(actor_user_id, original.branch_id)
            if original.status is not PayrollRunStatus.PAID or original.run_type != "ORDINARY":
                return HRResult.fail("Sólo se complementa una corrida ordinaria PAGADA",
                                     "PAYROLL_STATE", operation_id=operation_id)
            related = [original, *uow.payroll.list_related(original.id)]
            targets = [e for e in original.employee_ids()
                       if not employee_ids or e in set(employee_ids)]
            ids = list(targets)
            workdays = {(w.employee_id, w.work_date): w for w in
                        uow.attendance.list_workdays_between(
                            original.period_start, original.period_end, employee_ids=ids)}
            leaves: dict[str, list] = {}
            for leave in uow.leaves.list_approved_between(
                    original.period_start, original.period_end, employee_ids=ids):
                leaves.setdefault(leave.employee_id, []).append(leave)

            run = PayrollRun.create(original.period_start, original.period_end, operation_id,
                                    branch_id=original.branch_id,
                                    generated_by_user_id=actor_user_id)
            run.run_type = "COMPLEMENTARY"
            run.original_run_id = original.id
            run.adjustment_reason = reason.strip()
            overpaid: list[str] = []
            for employee_id in targets:
                employee = uow.employees.get(employee_id)
                if employee is None:
                    continue
                days = GeneratePayrollRunUseCase._payable_days(
                    uow, employee, original.period_start, original.period_end, workdays,
                    leaves.get(employee_id, []), today)
                should = self._calculator.build_lines(
                    run.id, EmployeePayrollInput(employee=employee, days=tuple(days)))
                should_net = sum((_signed(line) for line in should
                                  if line.concept in CALCULATED_CONCEPTS), Decimal("0"))
                paid_net = Decimal("0")
                for previous in related:
                    for line in previous.lines:
                        if line.employee_id != employee_id:
                            continue
                        if previous.run_type == "COMPLEMENTARY" or \
                                line.concept in CALCULATED_CONCEPTS:
                            paid_net += _signed(line)
                delta = should_net - paid_net
                if delta > 0:
                    run.add_line(PayrollLine.create(
                        run.id, employee_id, PayrollConcept.ADJUSTMENT,
                        Money(delta, employee.daily_salary.currency_code), is_deduction=False,
                        notes=f"Diferencia de la corrida {original.id[:8]}: {reason.strip()}"))
                elif delta < 0:
                    overpaid.append(f"{employee.employee_code} {format(-delta, 'f')}")
            if not run.lines:
                message = "No hay diferencias a favor que pagar"
                if overpaid:
                    message += ("; pagado de más (resuélvalo con un anticipo o ajuste): "
                                + ", ".join(overpaid))
                return HRResult.fail(message, "NO_DIFFERENCE", operation_id=operation_id)
            run.mark_calculated()
            uow.payroll.save(run)
            uow.audit.record(action="PAYROLL_COMPLEMENTARY_GENERATED",
                             actor_user_id=actor_user_id, entity_type="payroll_run",
                             entity_id=run.id, detail=f"original={original.id} {reason.strip()}",
                             operation_id=operation_id)
            uow.outbox.enqueue(new_uuid(), EventName.PAYROLL_RUN_GENERATED.value, json.dumps({
                "payroll_run_id": run.id, "run_type": run.run_type,
                "original_run_id": original.id}), operation_id)
        message = "Corrida complementaria generada"
        if overpaid:
            message += "; pagado de más: " + ", ".join(overpaid)
        return HRResult.ok(message, entity_id=run.id, operation_id=operation_id,
                           net=run.net_amount().to_string(), overpaid=overpaid)


class ReversePayrollPaymentUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, payroll_run_id: str, reason: str,
                operation_id: str) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.PAYROLL_REVERSE_PAYMENT)
        with HRUnitOfWork(connection) as uow:
            run = uow.payroll.get(payroll_run_id)
            if run is None:
                return HRResult.fail("La corrida no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            self._auth.require_branch(actor_user_id, run.branch_id)
            if uow.payroll.list_related(run.id):
                return HRResult.fail(
                    "La corrida tiene complementarias vivas: revierta o cancele primero esas",
                    "HAS_COMPLEMENTARY", operation_id=operation_id)
            try:
                run.reverse_payment(actor_user_id, reason=reason)
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "PAYROLL_STATE", operation_id=operation_id)
            uow.payroll.update(run)
            if run.payment_id:
                uow.payroll_payments.mark_reversed(run.payment_id, run.reversed_at)
            uow.payroll.release_coverage(run.id)
            uow.payroll_inputs.release_run(run.id)
            reopened = uow.connection.execute(
                "SELECT DISTINCT loan_id FROM payroll_loan_applications WHERE payroll_run_id=?",
                (run.id,)).fetchall()
            uow.loans.release_run(run.id)
            for (loan_id,) in reopened:
                uow.loans.set_status(loan_id, "ACTIVE")
            pending = uow.outbox.find_pending("PAYROLL_PAID", run.id)
            if pending is not None:
                # Nunca llegó a contabilidad: se anula en la cola, no hay asiento que revertir.
                uow.outbox.void(pending["id"], f"pago revertido: {reason.strip()}")
                accounting = "el pago no se había contabilizado; se anuló en la cola"
            else:
                event_id = new_uuid()
                uow.outbox.enqueue(event_id, PAYROLL_PAYMENT_REVERSED, json.dumps({
                    "event_id": event_id, "event_name": PAYROLL_PAYMENT_REVERSED,
                    "operation_id": operation_id,
                    "occurred_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "currency_code": run.net_amount().currency_code,
                    "payroll_run_id": run.id, "branch_id": run.branch_id,
                    "reason": reason.strip(), "reversed_by_user_id": actor_user_id,
                }), operation_id)
                accounting = "Finanzas revierte el asiento"
            uow.audit.record(action="PAYROLL_PAYMENT_REVERSED", actor_user_id=actor_user_id,
                             entity_type="payroll_run", entity_id=run.id, detail=reason.strip(),
                             operation_id=operation_id)
        return HRResult.ok(f"Pago revertido; {accounting}. El periodo puede volver a generarse.",
                           entity_id=payroll_run_id, operation_id=operation_id)
