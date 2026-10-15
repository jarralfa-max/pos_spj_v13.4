"""Libro de saldo de vacaciones (pendiente de la auditoría RR. HH. HR-18).

El saldo es la SUMA de movimientos (``leave_balance_movements``), cada uno con su
ciclo de aniversario:

* ``ACCRUAL`` — al empezar cada ciclo se abonan los días que corresponden por
  antigüedad (``vacation_entitlement``). Uno por ciclo.
* ``RESERVATION`` / ``RELEASE`` — una solicitud pendiente aparta días; rechazarla
  o cancelarla los libera (sólo los suyos).
* ``CONSUMPTION`` — al aprobarse, la reserva se convierte en consumo.
* ``EXPIRATION`` — lo no disfrutado de un ciclo vence ``carry_over_months``
  después de que el ciclo termina (regla declarada; por omisión 6 meses, la
  ventana de la LFT para disfrutarlas). Uno por ciclo.
* ``ADJUSTMENT`` — corrección manual con motivo y permiso.

Se consume del ciclo VIGENTE más antiguo primero (FIFO). Abonos y vencimientos se
registran de forma perezosa e idempotente al consultar o mover el saldo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from backend.domain.hr.exceptions import HRDomainError, InsufficientLeaveBalanceError
from backend.domain.hr.policies.leave_policy import (
    _anniversary,
    vacation_cycle,
    vacation_entitlement,
)

DEFAULT_CARRY_OVER_MONTHS = 6


def _add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    for candidate in (31, 30, 29, 28):
        try:
            return date(year, month, min(day.day, candidate))
        except ValueError:
            continue
    raise ValueError(day)


@dataclass(frozen=True, slots=True)
class CycleBalance:
    cycle_start: date
    cycle_end: date
    expires_on: date
    remaining: int


@dataclass(frozen=True, slots=True)
class LedgerBalance:
    available: int
    reserved: int
    cycles: tuple[CycleBalance, ...]
    movements: tuple[dict, ...]


class LeaveBalanceService:
    def __init__(self, *, annual_days: int | None = None,
                 carry_over_months: int = DEFAULT_CARRY_OVER_MONTHS) -> None:
        self._annual_days = annual_days
        self._carry_over = carry_over_months

    # ── ciclos ──────────────────────────────────────────────────────────────
    def _cycles_until(self, hire_date: date, on_date: date):
        start, end, year = vacation_cycle(hire_date, hire_date)
        while start <= on_date:
            yield start, end, year
            start = _anniversary(hire_date, start.year + 1)
            end = _anniversary(hire_date, start.year + 1) - timedelta(days=1)
            year += 1

    def _expires_on(self, cycle_end: date) -> date:
        return _add_months(cycle_end, self._carry_over)

    def _remaining_by_cycle(self, uow, employee_id: str) -> dict[date, int]:
        remaining: dict[date, int] = {}
        for row in uow.leave_ledger.movements(employee_id):
            cycle = date.fromisoformat(row["cycle_start"])
            remaining[cycle] = remaining.get(cycle, 0) + int(row["days"])
        return remaining

    def ensure(self, uow, employee, on_date: date) -> None:
        """Abonos de los ciclos iniciados y vencimientos de los ya vencidos."""
        for start, end, year in self._cycles_until(employee.hire_date, on_date):
            entitled = self._annual_days if self._annual_days is not None \
                else vacation_entitlement(year)
            uow.leave_ledger.add(employee_id=employee.id, cycle_start=start, kind="ACCRUAL",
                                 days=entitled, reason=f"Abono año {year} de servicio")
            if self._expires_on(end) < on_date:
                left = self._remaining_by_cycle(uow, employee.id).get(start, 0)
                if left > 0:
                    uow.leave_ledger.add(employee_id=employee.id, cycle_start=start,
                                         kind="EXPIRATION", days=-left,
                                         reason=f"Vencen días del ciclo {start}")

    def balance(self, uow, employee, on_date: date) -> LedgerBalance:
        self.ensure(uow, employee, on_date)
        remaining = self._remaining_by_cycle(uow, employee.id)
        cycles = []
        for start, end, _year in self._cycles_until(employee.hire_date, on_date):
            expires = self._expires_on(end)
            if expires >= on_date:
                cycles.append(CycleBalance(start, end, expires, remaining.get(start, 0)))
        movements = tuple(uow.leave_ledger.movements(employee.id))
        return LedgerBalance(sum(max(0, c.remaining) for c in cycles),
                             self._reserved(movements), tuple(cycles), movements)

    @staticmethod
    def _reserved(movements) -> int:
        """Días apartados por solicitudes que aún no se aprueban ni se liberan."""
        per_request: dict[str, dict[str, int]] = {}
        for m in movements:
            if not m["source_id"]:
                continue
            bucket = per_request.setdefault(m["source_id"], {})
            key = f"{m['kind']}:{m['source_type']}"
            bucket[key] = bucket.get(key, 0) + int(m["days"])
        reserved = 0
        for bucket in per_request.values():
            if bucket.get("CONSUMPTION:leave") or bucket.get("RELEASE:leave_release"):
                continue
            reserved += -bucket.get("RESERVATION:leave", 0)
        return max(0, reserved)

    # ── movimientos de una solicitud ────────────────────────────────────────
    def reserve(self, uow, employee, request, *, actor_user_id: str | None) -> None:
        balance = self.balance(uow, employee, request.start_date)
        if request.requested_days > balance.available:
            raise InsufficientLeaveBalanceError(
                f"Saldo insuficiente: disponibles {balance.available}, "
                f"solicitados {request.requested_days}")
        pending = request.requested_days
        for cycle in balance.cycles:                       # FIFO: el ciclo más antiguo
            take = min(pending, max(0, cycle.remaining))
            if take:
                uow.leave_ledger.add(employee_id=employee.id, cycle_start=cycle.cycle_start,
                                     kind="RESERVATION", days=-take, source_type="leave",
                                     source_id=request.id, reason="Solicitud pendiente",
                                     created_by_user_id=actor_user_id)
                pending -= take
            if not pending:
                break

    def consume(self, uow, request, *, actor_user_id: str | None) -> None:
        for row in uow.leave_ledger.by_source("leave", request.id):
            if row["kind"] != "RESERVATION":
                continue
            cycle = date.fromisoformat(row["cycle_start"])
            days = -int(row["days"])
            uow.leave_ledger.add(employee_id=request.employee_id, cycle_start=cycle,
                                 kind="RELEASE", days=days, source_type="leave_reservation",
                                 source_id=request.id, reason="Reserva aprobada",
                                 created_by_user_id=actor_user_id)
            uow.leave_ledger.add(employee_id=request.employee_id, cycle_start=cycle,
                                 kind="CONSUMPTION", days=-days, source_type="leave",
                                 source_id=request.id, reason="Vacaciones aprobadas",
                                 created_by_user_id=actor_user_id)

    def release(self, uow, request, *, actor_user_id: str | None, reason: str) -> None:
        """Devuelve al saldo lo que esta solicitud tenga apartado o consumido."""
        net: dict[date, int] = {}
        for row in uow.leave_ledger.by_source("leave", request.id):
            cycle = date.fromisoformat(row["cycle_start"])
            net[cycle] = net.get(cycle, 0) + int(row["days"])
        for row in uow.leave_ledger.by_source("leave_reservation", request.id):
            cycle = date.fromisoformat(row["cycle_start"])
            net[cycle] = net.get(cycle, 0) + int(row["days"])
        for cycle, days in net.items():
            if days < 0:
                uow.leave_ledger.add(employee_id=request.employee_id, cycle_start=cycle,
                                     kind="RELEASE", days=-days, source_type="leave_release",
                                     source_id=request.id, reason=reason,
                                     created_by_user_id=actor_user_id)

    def adjust(self, uow, employee, *, days: int, on_date: date, reason: str,
               actor_user_id: str) -> None:
        if not days:
            raise HRDomainError("El ajuste debe ser distinto de cero")
        if not str(reason or "").strip():
            raise HRDomainError("El ajuste de saldo requiere motivo")
        start, _end, _year = vacation_cycle(employee.hire_date, on_date)
        self.ensure(uow, employee, on_date)
        uow.leave_ledger.add(employee_id=employee.id, cycle_start=start, kind="ADJUSTMENT",
                             days=int(days), source_type="manual", source_id=None,
                             reason=reason.strip(), created_by_user_id=actor_user_id)
