"""ScheduledOrderPolicy (master prompt §19). Validates the shape of a
schedule (window ordering, activation lead time) and decides whether
activation is due — pure, no I/O: the caller supplies `now` explicitly
rather than this policy reading the clock itself.
"""

from __future__ import annotations

from datetime import datetime

from backend.domain.orders_delivery.enums import ScheduleStatus
from backend.domain.orders_delivery.exceptions import (
    InvalidOrderScheduleError,
    OrderActivationNotDueError,
)


class ScheduledOrderPolicy:
    @staticmethod
    def ensure_valid_window(*, window_start: str, window_end: str) -> None:
        if not window_start or not window_end:
            raise InvalidOrderScheduleError(
                "La programación requiere ventana de inicio y fin")
        if window_end <= window_start:
            raise InvalidOrderScheduleError(
                "La ventana de entrega debe terminar después de iniciar")

    @staticmethod
    def ensure_can_activate(*, status: ScheduleStatus, activation_at: str, now: datetime) -> None:
        if status not in (ScheduleStatus.SCHEDULED, ScheduleStatus.ACTIVATION_PENDING):
            raise InvalidOrderScheduleError(
                f"No se puede activar una programación en estado {status.value}")
        if not activation_at:
            raise InvalidOrderScheduleError("La programación no tiene fecha de activación")
        if datetime.fromisoformat(activation_at) > now:
            raise OrderActivationNotDueError(
                f"La activación es hasta {activation_at}, todavía no corresponde")

    @staticmethod
    def ensure_can_reschedule(status: ScheduleStatus) -> None:
        if status in (ScheduleStatus.ACTIVATED, ScheduleStatus.CANCELLED):
            raise InvalidOrderScheduleError(
                f"No se puede reprogramar una programación en estado {status.value}")

    @staticmethod
    def ensure_can_cancel(status: ScheduleStatus) -> None:
        if status in (ScheduleStatus.ACTIVATED, ScheduleStatus.CANCELLED):
            raise InvalidOrderScheduleError(
                f"No se puede cancelar una programación en estado {status.value}")
