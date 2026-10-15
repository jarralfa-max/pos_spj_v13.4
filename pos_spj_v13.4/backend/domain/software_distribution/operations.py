"""When an update may stop the application: active operations and the
station's maintenance window.

An update never interrupts a sale being captured, a payment awaiting
confirmation or a cash cut in progress — not even a mandatory one. A
mandatory release only shortens the deferral by informing a deadline.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
import re


@dataclass(frozen=True)
class ActiveOperationsSnapshot:
    """Counts read from the operational database right before stopping."""

    sales_in_capture: int = 0
    payments_pending: int = 0
    cash_cuts_in_progress: int = 0
    pending_outbox_messages: int = 0


@dataclass(frozen=True)
class DeferralDecision:
    blocked: bool
    reasons: tuple[str, ...]
    warnings: tuple[str, ...] = ()


class UpdateDeferralPolicy:
    """Blocking reasons stop the update; warnings are shown but do not."""

    def decide(self, snapshot: ActiveOperationsSnapshot) -> DeferralDecision:
        reasons: list[str] = []
        if snapshot.sales_in_capture:
            reasons.append(f"{snapshot.sales_in_capture} venta(s) en captura.")
        if snapshot.payments_pending:
            reasons.append(f"{snapshot.payments_pending} cobro(s) pendiente(s) de confirmar.")
        if snapshot.cash_cuts_in_progress:
            reasons.append(f"{snapshot.cash_cuts_in_progress} corte(s) de caja en curso.")
        warnings: list[str] = []
        if snapshot.pending_outbox_messages:
            warnings.append(
                f"{snapshot.pending_outbox_messages} mensaje(s) por sincronizar; se enviarán "
                "al volver a abrir la aplicación.")
        return DeferralDecision(blocked=bool(reasons), reasons=tuple(reasons),
                                warnings=tuple(warnings))


_WINDOW = re.compile(r"^\s*([01]\d|2[0-3]):([0-5]\d)\s*-\s*([01]\d|2[0-3]):([0-5]\d)\s*$")


class InvalidMaintenanceWindowError(ValueError):
    pass


@dataclass(frozen=True)
class MaintenanceWindow:
    """Daily local-time window. `start > end` crosses midnight (22:00-06:00)."""

    start: time
    end: time

    @classmethod
    def parse(cls, text: str) -> "MaintenanceWindow":
        match = _WINDOW.match(text or "")
        if match is None:
            raise InvalidMaintenanceWindowError(
                f"Ventana inválida: {text!r} (formato HH:MM-HH:MM).")
        start = time(int(match.group(1)), int(match.group(2)))
        end = time(int(match.group(3)), int(match.group(4)))
        if start == end:
            raise InvalidMaintenanceWindowError("La ventana no puede empezar y terminar igual.")
        return cls(start=start, end=end)

    def contains(self, moment: datetime) -> bool:
        current = moment.time().replace(second=0, microsecond=0)
        if self.start < self.end:
            return self.start <= current < self.end
        return current >= self.start or current < self.end

    def __str__(self) -> str:
        return f"{self.start:%H:%M}-{self.end:%H:%M}"
