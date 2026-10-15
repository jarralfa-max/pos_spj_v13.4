"""Leave policy — overlap and balance validation."""

from __future__ import annotations

from datetime import date

from backend.domain.hr.entities import LeaveRequest
from backend.domain.hr.enums import LeaveStatus, LeaveType
from backend.domain.hr.exceptions import (
    InsufficientLeaveBalanceError,
    InvalidLeaveDatesError,
    LeaveOverlapError,
)


class LeavePolicy:
    #: Leave types that consume the paid vacation balance.
    BALANCE_TYPES = frozenset({LeaveType.VACATION})

    def enforce_dates(self, start_date: date, end_date: date) -> None:
        if end_date < start_date:
            raise InvalidLeaveDatesError("La fecha final no puede ser anterior a la inicial")

    def enforce_no_overlap(self, new_start: date, new_end: date,
                           existing: list[LeaveRequest]) -> None:
        for request in existing:
            if request.status in (LeaveStatus.APPROVED, LeaveStatus.PENDING) \
                    and request.overlaps(new_start, new_end):
                raise LeaveOverlapError(
                    f"La solicitud se solapa con otra del {request.start_date} "
                    f"al {request.end_date}"
                )

    def enforce_balance(self, leave_type: LeaveType, requested_days: int,
                        available_days: int) -> None:
        if leave_type in self.BALANCE_TYPES and requested_days > available_days:
            raise InsufficientLeaveBalanceError(
                f"Saldo insuficiente: disponibles {available_days}, solicitados {requested_days}"
            )


# ── Saldo vacacional por ciclo (auditoría RRHH cebf67a HR-18) ───────────────
# Antes: una cuota FIJA de 12 días menos TODA la historia — tras 12 días en
# 2025, en 2026 no quedaba nada. Ahora el saldo es POR CICLO de aniversario, con
# derecho según antigüedad, y se explica por las solicitudes del ciclo.

from dataclasses import dataclass  # noqa: E402


def vacation_entitlement(years_of_service: int) -> int:
    """Días por año de servicio. Regla declarada por defecto: la tabla de la
    LFT vigente desde 2023 (12 el 1.er año, +2 por año hasta 20 el 5.º; luego
    +2 por cada 5 años). Es parametrizable (``annual_vacation_days``) y no
    constituye una certificación legal."""
    year = max(1, int(years_of_service))
    if year <= 5:
        return 12 + 2 * (year - 1)
    return 20 + 2 * ((year - 6) // 5 + 1)


def _anniversary(hire_date: date, year: int) -> date:
    try:
        return hire_date.replace(year=year)
    except ValueError:              # 29 de febrero en año no bisiesto
        return hire_date.replace(year=year, day=28)


def vacation_cycle(hire_date: date, on_date: date) -> tuple[date, date, int]:
    """Ciclo de aniversario que contiene ``on_date``: (inicio, fin, año n.º)."""
    year = on_date.year
    start = _anniversary(hire_date, year)
    if start > on_date:
        start = _anniversary(hire_date, year - 1)
    end = _anniversary(hire_date, start.year + 1)
    from datetime import timedelta
    return start, end - timedelta(days=1), max(1, start.year - hire_date.year + 1)


@dataclass(frozen=True, slots=True)
class VacationBalance:
    cycle_start: date
    cycle_end: date
    service_year: int
    entitled: int
    used: int          # aprobadas en el ciclo
    reserved: int      # pendientes en el ciclo (apartan saldo)

    @property
    def available(self) -> int:
        return self.entitled - self.used - self.reserved


def vacation_balance(hire_date: date, on_date: date, requests,
                     *, annual_days: int | None = None) -> VacationBalance:
    """Saldo del ciclo que contiene ``on_date``. Cuenta sólo vacaciones de ESE
    ciclo (por fecha de inicio); cancelar/rechazar libera su reserva."""
    start, end, service_year = vacation_cycle(hire_date, on_date)
    entitled = annual_days if annual_days is not None else vacation_entitlement(service_year)
    used = reserved = 0
    for request in requests:
        if request.leave_type is not LeaveType.VACATION:
            continue
        if not (start <= request.start_date <= end):
            continue
        if request.status is LeaveStatus.APPROVED:
            used += request.requested_days
        elif request.status is LeaveStatus.PENDING:
            reserved += request.requested_days
    return VacationBalance(start, end, service_year, entitled, used, reserved)
