"""SLAInstance — the SLA clock attached to one CustomerServiceCase
(§30-32: "first_response_due_at, resolution_due_at, first_response_at,
resolved_at, breach_status, escalation_level").

``breach_status`` is split between stored and derived, same reasoning as
CRMWorkItemStatus.OVERDUE (CRM-6): PAUSED and COMPLETED are explicit,
event-driven states (the case entered WAITING_CUSTOMER; a resolution was
recorded) so they ARE persisted fields (``paused``, ``resolved_at``).
ON_TIME/AT_RISK/BREACHED depend purely on wall-clock time passing without
action, so they are never persisted — ``effective_breach_status()``
computes them from ``resolution_due_at`` vs. "now", the same way
``CRMActivity.effective_status()`` derives OVERDUE.

Auditoría CRM F11 (2026-10-09): pausar ya descuenta la espera. ``pause``
guarda cuándo empezó; ``resume`` recorre los vencimientos pendientes lo que duró
la pausa y lo acumula en ``paused_seconds`` (antes el vencimiento quedaba fijo y
al reanudar el caso aparecía vencido por tiempo que fue del cliente). Varias
pausas se suman. Resolver estando en pausa cierra primero la pausa.

El RESULTADO del SLA se guarda aparte del estado del caso:
``first_response_outcome``/``resolution_outcome`` = ``MET`` (a tiempo) o
``MISSED`` (tarde). «Resuelto» ya no se lee como «cumplido» (antes una resolución
tardía devolvía COMPLETED sin rastro del incumplimiento).

Calendario: el reloj es de 24 horas. Horario hábil y días festivos requieren
calendarios por política, que el sistema todavía no modela.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from backend.domain.customer_service.enums import SLABreachStatus
from backend.domain.customer_service.exceptions import InvalidSLAInstanceError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _shift(value: str, delta: timedelta) -> str:
    return (_parse(value) + delta).isoformat(timespec="seconds")


def _outcome(moment: str, due: str) -> str:
    return "MET" if _parse(moment) <= _parse(due) else "MISSED"


@dataclass(slots=True)
class SLAInstance:
    id: str
    case_id: str
    policy_id: str
    first_response_due_at: str
    resolution_due_at: str
    at_risk_threshold_pct: int = 80
    first_response_at: str | None = None
    resolved_at: str | None = None
    paused: bool = False
    escalation_level: int = 0
    created_at: str = field(default_factory=_utcnow)
    paused_at: str | None = None
    paused_seconds: int = 0
    first_response_outcome: str | None = None
    resolution_outcome: str | None = None

    @classmethod
    def create(
        cls, case_id: str, policy_id: str, first_response_minutes: int, resolution_minutes: int,
        *, at_risk_threshold_pct: int = 80, reference_time: str | None = None,
    ) -> "SLAInstance":
        if not case_id:
            raise InvalidSLAInstanceError("SLAInstance requiere case_id")
        if not policy_id:
            raise InvalidSLAInstanceError("SLAInstance requiere policy_id")
        created = reference_time or _utcnow()
        base = _parse(created)
        return cls(
            id=new_uuid(), case_id=case_id, policy_id=policy_id,
            first_response_due_at=(base + timedelta(minutes=first_response_minutes)).isoformat(
                timespec="seconds"),
            resolution_due_at=(base + timedelta(minutes=resolution_minutes)).isoformat(
                timespec="seconds"),
            at_risk_threshold_pct=at_risk_threshold_pct, created_at=created,
        )

    def record_first_response(self, *, at: str | None = None) -> None:
        if self.first_response_at is not None:
            raise InvalidSLAInstanceError("Ya se registró la primera respuesta")
        moment = at or _utcnow()
        if self.paused:
            self.resume(at=moment)
        self.first_response_at = moment
        self.first_response_outcome = _outcome(moment, self.first_response_due_at)

    def record_resolution(self, *, at: str | None = None) -> None:
        if self.resolved_at is not None:
            raise InvalidSLAInstanceError("Ya se registró la resolución")
        moment = at or _utcnow()
        if self.paused:
            self.resume(at=moment)
        self.resolved_at = moment
        self.resolution_outcome = _outcome(moment, self.resolution_due_at)
        if self.first_response_at is None and self.first_response_outcome is None:
            # Se resolvió sin registrar primera respuesta: la resolución la cubre.
            self.first_response_outcome = _outcome(moment, self.first_response_due_at)

    def pause(self, *, at: str | None = None) -> None:
        if self.paused or self.resolved_at is not None:
            return
        self.paused = True
        self.paused_at = at or _utcnow()

    def resume(self, *, at: str | None = None) -> None:
        if not self.paused:
            return
        if self.paused_at:
            waited = max(0.0, (_parse(at or _utcnow()) - _parse(self.paused_at)).total_seconds())
            shift = timedelta(seconds=waited)
            if self.first_response_at is None:
                self.first_response_due_at = _shift(self.first_response_due_at, shift)
            self.resolution_due_at = _shift(self.resolution_due_at, shift)
            self.paused_seconds += int(waited)
        self.paused = False
        self.paused_at = None

    def result_status(self, *, as_of: str | None = None) -> str:
        """Lo que se muestra/cuenta: ``MET``/``MISSED`` si ya terminó, si no el
        estado vivo (ON_TIME, AT_RISK, BREACHED, PAUSED)."""
        if self.resolved_at is not None:
            return self.resolution_outcome or "MET"
        return self.effective_breach_status(as_of=as_of).value

    def first_response_result(self, *, as_of: str | None = None) -> str:
        if self.first_response_outcome is not None:
            return self.first_response_outcome
        return self.first_response_status(as_of=as_of).value

    def bump_escalation(self) -> int:
        self.escalation_level += 1
        return self.escalation_level

    def first_response_status(self, *, as_of: str | None = None) -> SLABreachStatus:
        """CRM-43 (§31, §86 «SLA respuesta»): el estado del plazo de PRIMERA
        respuesta, independiente del de resolución."""
        if self.first_response_at is not None or self.resolved_at is not None:
            return SLABreachStatus.COMPLETED
        if self.paused:
            return SLABreachStatus.PAUSED
        now = as_of or _utcnow()
        if _parse(now) > _parse(self.first_response_due_at):
            return SLABreachStatus.BREACHED
        total = ((_parse(self.first_response_due_at) - _parse(self.created_at)).total_seconds()
                 - self.paused_seconds)
        elapsed = (_parse(now) - _parse(self.created_at)).total_seconds() - self.paused_seconds
        if total > 0 and (elapsed / total * 100) >= self.at_risk_threshold_pct:
            return SLABreachStatus.AT_RISK
        return SLABreachStatus.ON_TIME

    def effective_breach_status(self, *, as_of: str | None = None) -> SLABreachStatus:
        if self.resolved_at is not None:
            return SLABreachStatus.COMPLETED
        if self.paused:
            return SLABreachStatus.PAUSED
        now = as_of or _utcnow()
        if _parse(now) > _parse(self.resolution_due_at):
            return SLABreachStatus.BREACHED
        total = ((_parse(self.resolution_due_at) - _parse(self.created_at)).total_seconds()
                 - self.paused_seconds)
        elapsed = (_parse(now) - _parse(self.created_at)).total_seconds() - self.paused_seconds
        if total > 0 and (elapsed / total * 100) >= self.at_risk_threshold_pct:
            return SLABreachStatus.AT_RISK
        return SLABreachStatus.ON_TIME
