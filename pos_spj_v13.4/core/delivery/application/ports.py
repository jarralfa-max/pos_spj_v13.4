from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol


class EventPublisher(Protocol):
    def __call__(self, event: str, payload: dict[str, Any]) -> None: ...


class StatusNotifier(Protocol):
    def notify_status(self, *, phone: str, folio: str, status: str) -> bool: ...
    def sync_status(self, whatsapp_order_id: str, status: str) -> bool: ...


class DeliveryNotifierPort(Protocol):
    def notify_status(self, *, phone: str, folio: str, status: str) -> bool: ...

    def notify_adjustment_required(self, **kwargs: Any) -> bool: ...

    def notify_weight_adjustment(self, **kwargs: Any) -> bool: ...

    def notify_out_for_delivery(self, *, phone: str, folio: str, driver_name: str = "", eta: str = "") -> bool: ...

    def notify_delivered(self, *, phone: str, folio: str) -> bool: ...

    def notify_from_event(self, payload: dict[str, Any]) -> bool: ...


class GeocodingPort(Protocol):
    def geocode(self, address: str) -> dict[str, Any] | None: ...


class InventoryReservationPort(Protocol):
    def reserve_for_order(
        self, *, order_id: int, items: list[dict[str, Any]], branch_id: int, operation_id: str
    ) -> dict[str, int]: ...

    def release_for_order(self, *, order_id: int, operation_id: str, reason: str = "") -> dict[str, int]: ...

    def commit_for_order(
        self, *, order_id: int, items: list[dict[str, Any]], branch_id: int, operation_id: str
    ) -> dict[str, int]: ...


NoopPublisher: Callable[[str, dict[str, Any]], None] = lambda _event, _payload: None
