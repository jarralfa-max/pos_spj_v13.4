"""PayrollCalculator — builds payroll lines for employees over a period.

Pure computation: given an employee's payable days (or the legacy aggregate
counters) and manual concepts, it produces the ``PayrollLine`` list. No SQL,
no repositories.

Auditoría RRHH cebf67a:

* HR-07 — una POLÍTICA declarada por modalidad, no dos fórmulas elegidas por
  si hay o no asistencia. Sueldo fijo (todo contrato salvo ``HOURLY``): cobra
  los días de vigencia del periodo × su tarifa diaria y se descuentan sólo las
  ausencias SIN goce y las faltas contra un turno asignado. Por horas: cobra los
  minutos trabajados más los días de ausencia CON goce. Registrar una jornada
  completa ya no cambia el sueldo de 7 días a 1.
* HR-08 — los permisos/vacaciones aprobados entran como días pagables con su
  tipo (``PayableDayKind``).
* HR-09 — cada día lleva la tarifa VIGENTE ese día (historial salarial).
* HR-12 — la tarifa por minuto se conserva con precisión Decimal y cada línea
  se redondea UNA sola vez: 300/480×60×1.5 = 56.25 (antes 55.80).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from backend.domain.hr.entities import Employee, PayrollLine
from backend.domain.hr.enums import DEDUCTION_CONCEPTS, ContractType, PayrollConcept
from backend.domain.hr.value_objects import Money

#: Jornada de referencia para la tarifa por minuto (regla versionable).
MINUTES_PER_WORKDAY = 480


class PayableDayKind(str, Enum):
    WORKED = "WORKED"                # jornada terminada (completa o ajustada)
    PENDING = "PENDING"              # jornada abierta/incidencia: espera resolución
    REST = "REST"                    # sin turno asignado ese día o descanso
    VACATION = "VACATION"            # vacaciones aprobadas (con goce)
    PAID_LEAVE = "PAID_LEAVE"        # permiso con goce / justificación / incapacidad pagada
    UNPAID_LEAVE = "UNPAID_LEAVE"    # permiso sin goce aprobado
    ABSENCE = "ABSENCE"              # falta: turno asignado, sin jornada ni permiso
    FUTURE = "FUTURE"                # día del periodo aún no transcurrido


PAID_ABSENCE_KINDS = frozenset({PayableDayKind.VACATION, PayableDayKind.PAID_LEAVE})
DEDUCTED_KINDS = frozenset({PayableDayKind.UNPAID_LEAVE, PayableDayKind.ABSENCE})


@dataclass(frozen=True, slots=True)
class PayableDay:
    day: date
    daily_rate: Decimal
    kind: PayableDayKind
    worked_minutes: int = 0
    overtime_minutes: int = 0
    late_minutes: int = 0


@dataclass(frozen=True, slots=True)
class EmployeePayrollInput:
    employee: Employee
    worked_days: int = 0
    overtime_minutes: int = 0
    late_minutes: int = 0
    absence_days: int = 0
    extra_concepts: tuple[tuple[PayrollConcept, Money], ...] = ()
    #: Días pagables del periodo (sólo los de vigencia del vínculo). Cuando se
    #: dan, mandan sobre los contadores agregados de arriba.
    days: tuple[PayableDay, ...] = ()


class PayrollCalculator:
    def __init__(self, *, overtime_multiplier: str = "1.5",
                 minutes_per_workday: int = MINUTES_PER_WORKDAY) -> None:
        self._overtime_multiplier = Decimal(overtime_multiplier)
        self._minutes_per_day = Decimal(minutes_per_workday)

    def build_lines(self, payroll_run_id: str, item: EmployeePayrollInput) -> list[PayrollLine]:
        if item.days:
            lines = self._lines_from_days(payroll_run_id, item)
        else:
            lines = self._lines_from_counters(payroll_run_id, item)
        for concept, amount in item.extra_concepts:
            lines.append(PayrollLine.create(
                payroll_run_id, item.employee.id, concept, amount,
                is_deduction=concept in DEDUCTION_CONCEPTS))
        return lines

    # ── días pagables (ruta canónica) ────────────────────────────────────────
    def _lines_from_days(self, run_id: str, item: EmployeePayrollInput) -> list[PayrollLine]:
        employee = item.employee
        currency = employee.daily_salary.currency_code
        days = item.days
        hourly = employee.contract_type is ContractType.HOURLY
        lines: list[PayrollLine] = []

        def money(value: Decimal) -> Money:
            return Money(value, currency)

        if hourly:
            worked = [d for d in days if d.kind in (PayableDayKind.WORKED, PayableDayKind.PENDING)]
            base = sum((d.daily_rate * Decimal(d.worked_minutes) / self._minutes_per_day
                        for d in worked), Decimal("0"))
            minutes = sum(d.worked_minutes for d in worked)
            lines.append(PayrollLine.create(
                run_id, employee.id, PayrollConcept.BASE_SALARY, money(base),
                is_deduction=False, quantity=str(minutes),
                notes=f"{minutes} min trabajados (por horas)"))
            for kind, concept in ((PayableDayKind.VACATION, PayrollConcept.VACATION),
                                  (PayableDayKind.PAID_LEAVE, PayrollConcept.PAID_LEAVE)):
                paid = [d for d in days if d.kind is kind]
                if paid:
                    lines.append(PayrollLine.create(
                        run_id, employee.id, concept,
                        money(sum((d.daily_rate for d in paid), Decimal("0"))),
                        is_deduction=False, quantity=str(len(paid)),
                        notes=f"{len(paid)} día(s) con goce"))
        else:
            # Sueldo fijo: todos los días de vigencia del periodo (descansos
            # incluidos); sólo lo SIN goce y las faltas se descuentan.
            base = sum((d.daily_rate for d in days), Decimal("0"))
            lines.append(PayrollLine.create(
                run_id, employee.id, PayrollConcept.BASE_SALARY, money(base),
                is_deduction=False, quantity=str(len(days)),
                notes=f"{len(days)} día(s) de vigencia en el periodo"))
            deducted = [d for d in days if d.kind in DEDUCTED_KINDS]
            if deducted:
                lines.append(PayrollLine.create(
                    run_id, employee.id, PayrollConcept.ABSENCE_DEDUCTION,
                    money(sum((d.daily_rate for d in deducted), Decimal("0"))),
                    is_deduction=True, quantity=str(len(deducted)),
                    notes=", ".join(f"{d.day.isoformat()} {d.kind.value}" for d in deducted)))

        overtime = sum((d.daily_rate / self._minutes_per_day * Decimal(d.overtime_minutes)
                        for d in days), Decimal("0")) * self._overtime_multiplier
        overtime_minutes = sum(d.overtime_minutes for d in days)
        if overtime_minutes > 0:
            lines.append(PayrollLine.create(
                run_id, employee.id, PayrollConcept.OVERTIME, money(overtime),
                is_deduction=False, quantity=str(overtime_minutes),
                notes=f"×{self._overtime_multiplier}"))
        late_minutes = sum(d.late_minutes for d in days)
        if late_minutes > 0:
            late = sum((d.daily_rate / self._minutes_per_day * Decimal(d.late_minutes)
                        for d in days), Decimal("0"))
            lines.append(PayrollLine.create(
                run_id, employee.id, PayrollConcept.LATE_DEDUCTION, money(late),
                is_deduction=True, quantity=str(late_minutes)))
        return lines

    # ── contadores agregados (compatibilidad) ───────────────────────────────
    def _lines_from_counters(self, run_id: str, item: EmployeePayrollInput) -> list[PayrollLine]:
        employee = item.employee
        rate = employee.daily_salary.amount
        currency = employee.daily_salary.currency_code
        lines = [PayrollLine.create(
            run_id, employee.id, PayrollConcept.BASE_SALARY,
            Money(rate * Decimal(item.worked_days), currency),
            is_deduction=False, quantity=str(item.worked_days))]
        if item.overtime_minutes > 0:
            overtime = (rate / self._minutes_per_day * Decimal(item.overtime_minutes)
                        * self._overtime_multiplier)
            lines.append(PayrollLine.create(
                run_id, employee.id, PayrollConcept.OVERTIME, Money(overtime, currency),
                is_deduction=False, quantity=str(item.overtime_minutes)))
        if item.absence_days > 0:
            lines.append(PayrollLine.create(
                run_id, employee.id, PayrollConcept.ABSENCE_DEDUCTION,
                Money(rate * Decimal(item.absence_days), currency),
                is_deduction=True, quantity=str(item.absence_days)))
        if item.late_minutes > 0:
            late = rate / self._minutes_per_day * Decimal(item.late_minutes)
            lines.append(PayrollLine.create(
                run_id, employee.id, PayrollConcept.LATE_DEDUCTION, Money(late, currency),
                is_deduction=True, quantity=str(item.late_minutes)))
        return lines
