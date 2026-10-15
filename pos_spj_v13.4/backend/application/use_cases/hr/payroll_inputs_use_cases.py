"""Conceptos capturados y préstamos a empleados (pendientes de la auditoría RR. HH.).

* Bonos, comisiones y ajustes: se CAPTURAN con motivo y fecha, los APRUEBA otra
  persona (segregación por identidad) y la corrida ordinaria que cubre esa fecha
  los toma; cancelarla los devuelve a aprobados. La comisión automática desde
  Ventas no existe aún: hoy la fuente canónica es esta captura aprobada.
* Préstamo/anticipo: entregarlo mueve dinero, así que publica
  ``EMPLOYEE_LOAN_GRANTED`` (Finanzas: Dr 1145 / Cr Caja o Bancos). Cada nómina
  descuenta el abono pactado sin dejar el neto negativo; al liquidarse queda PAID.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from backend.application.use_cases.hr.hr_result import HRResult
from backend.domain.hr.enums import CAPTURABLE_PERCEPTIONS, PaymentMethod, PayrollConcept
from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy, HRPermission
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.ids import new_uuid

EMPLOYEE_LOAN_GRANTED = "EMPLOYEE_LOAN_GRANTED"


def _amount(raw) -> Decimal | None:
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, AttributeError):
        return None
    return value if value.is_finite() else None


class CapturePayrollInputUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, employee_id: str, concept: str,
                amount: str, applies_on: date, reason: str, operation_id: str,
                source_module: str = "hr", source_reference: str | None = None) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.PAYROLL_INPUT_CAPTURE)
        value = _amount(amount)
        try:
            concept_enum = PayrollConcept(concept)
        except ValueError:
            concept_enum = None
        if concept_enum not in CAPTURABLE_PERCEPTIONS:
            return HRResult.fail("Concepto no permitido (bono, comisión o ajuste)", "VALIDATION")
        if value is None or value <= 0:
            return HRResult.fail("El importe debe ser mayor que cero", "VALIDATION")
        if not str(reason or "").strip():
            return HRResult.fail("El concepto requiere motivo", "VALIDATION")
        with HRUnitOfWork(connection) as uow:
            if uow.payroll_inputs.find_by_operation_id(operation_id):
                return HRResult.ok("Concepto ya capturado", operation_id=operation_id)
            employee = uow.employees.get(employee_id)
            if employee is None:
                return HRResult.fail("El empleado no existe", "NOT_FOUND")
            self._auth.require_branch(actor_user_id, employee.branch_id)
            if not employee.is_employed_on(applies_on):
                return HRResult.fail("La fecha está fuera de la vigencia del empleado",
                                     "VALIDATION")
            input_id = new_uuid()
            uow.payroll_inputs.save({
                "id": input_id, "employee_id": employee_id, "branch_id": employee.branch_id,
                "concept": concept_enum.value, "amount": format(value.quantize(Decimal("0.01")), "f"),
                "currency_code": employee.daily_salary.currency_code,
                "applies_on": applies_on.isoformat(), "reason": reason.strip(),
                "source_module": source_module, "source_reference": source_reference,
                "status": "PENDING", "captured_by_user_id": actor_user_id,
                "approved_by_user_id": None, "approved_at": None, "payroll_run_id": None,
                "operation_id": operation_id,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
            uow.audit.record(action="PAYROLL_INPUT_CAPTURED", actor_user_id=actor_user_id,
                             entity_type="employee", entity_id=employee_id,
                             detail=f"{concept_enum.value} {value} {applies_on}",
                             operation_id=operation_id)
        return HRResult.ok("Concepto capturado; requiere aprobación", entity_id=input_id)


class ResolvePayrollInputUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, input_id: str, approve: bool,
                reason: str = "") -> HRResult:
        self._auth.require(actor_user_id, HRPermission.PAYROLL_INPUT_APPROVE)
        with HRUnitOfWork(connection) as uow:
            row = uow.payroll_inputs.get(input_id)
            if row is None:
                return HRResult.fail("El concepto no existe", "NOT_FOUND")
            self._auth.require_branch(actor_user_id, row["branch_id"])
            if row["status"] != "PENDING":
                return HRResult.fail(f"El concepto ya está {row['status']}", "INVALID_STATE")
            if approve and row["captured_by_user_id"] == actor_user_id:
                return HRResult.fail(
                    "Separación de funciones: quien captura el concepto no lo aprueba",
                    "SEGREGATION")
            uow.payroll_inputs.set_status(input_id, "APPROVED" if approve else "REJECTED",
                                          approved_by=actor_user_id)
            uow.audit.record(action="PAYROLL_INPUT_" + ("APPROVED" if approve else "REJECTED"),
                             actor_user_id=actor_user_id, entity_type="employee",
                             entity_id=row["employee_id"], detail=reason or row["concept"])
        return HRResult.ok("Concepto aprobado" if approve else "Concepto rechazado",
                           entity_id=input_id)


class GrantEmployeeLoanUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, employee_id: str, kind: str,
                principal: str, installment: str, payment_method: str, reason: str,
                operation_id: str, granted_on: date | None = None,
                payment_reference: str | None = None) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.LOAN_GRANT)
        principal_value, installment_value = _amount(principal), _amount(installment)
        if kind not in ("LOAN", "ADVANCE"):
            return HRResult.fail("Tipo inválido (préstamo o anticipo)", "VALIDATION")
        if principal_value is None or principal_value <= 0:
            return HRResult.fail("El importe debe ser mayor que cero", "VALIDATION")
        if installment_value is None or installment_value <= 0 \
                or installment_value > principal_value:
            return HRResult.fail("El abono debe ser mayor que cero y no exceder el importe",
                                 "VALIDATION")
        try:
            method = PaymentMethod(payment_method)
        except ValueError:
            return HRResult.fail("Seleccione cómo se entrega el dinero", "VALIDATION")
        reference = str(payment_reference or "").strip() or None
        if method is not PaymentMethod.CASH and not reference:
            return HRResult.fail("La transferencia o el cheque requieren su referencia",
                                 "VALIDATION")
        if not str(reason or "").strip():
            return HRResult.fail("El préstamo requiere motivo", "VALIDATION")
        granted_on = granted_on or date.today()
        with HRUnitOfWork(connection) as uow:
            existing = uow.loans.find_by_operation_id(operation_id)
            if existing is not None:
                return HRResult.ok("Préstamo ya registrado", entity_id=existing["id"])
            employee = uow.employees.get(employee_id)
            if employee is None or not employee.active:
                return HRResult.fail("El empleado no existe o está dado de baja", "NOT_FOUND")
            self._auth.require_branch(actor_user_id, employee.branch_id)
            loan_id = new_uuid()
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            currency = employee.daily_salary.currency_code
            uow.loans.save({
                "id": loan_id, "employee_id": employee_id, "branch_id": employee.branch_id,
                "kind": kind, "principal": format(principal_value.quantize(Decimal("0.01")), "f"),
                "installment": format(installment_value.quantize(Decimal("0.01")), "f"),
                "currency_code": currency, "granted_on": granted_on.isoformat(),
                "payment_method": method.value, "payment_reference": reference,
                "status": "ACTIVE", "reason": reason.strip(), "granted_by_user_id": actor_user_id,
                "operation_id": operation_id, "created_at": now})
            event_id = new_uuid()
            uow.outbox.enqueue(event_id, EMPLOYEE_LOAN_GRANTED, json.dumps({
                "event_id": event_id, "event_name": EMPLOYEE_LOAN_GRANTED,
                "operation_id": operation_id, "occurred_at": now, "currency_code": currency,
                "loan_id": loan_id, "kind": kind, "employee_id": employee_id,
                "employee_code": employee.employee_code, "branch_id": employee.branch_id,
                "amount": format(principal_value.quantize(Decimal("0.01")), "f"),
                "payment_method": method.value, "payment_reference": reference,
            }), operation_id)
            uow.audit.record(action="EMPLOYEE_LOAN_GRANTED", actor_user_id=actor_user_id,
                             entity_type="employee", entity_id=employee_id,
                             detail=f"{kind} {principal_value} abono {installment_value}",
                             operation_id=operation_id)
        return HRResult.ok("Préstamo registrado; se descontará en cada nómina",
                           entity_id=loan_id)
