"""Shipment and custody entities for transfer dispatch."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid


ZERO = Decimal("0")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _decimal(value: Decimal | str | int | None) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError("Transfer shipment quantities, weights and temperatures must be Decimal")
    return Decimal(str(value))


@dataclass(frozen=True, slots=True)
class TransferShipmentLine:
    transfer_line_id: str
    quantity: Decimal | str | int
    weight: Decimal | str | int = ZERO
    id: str = field(default_factory=new_uuid)

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity", _decimal(self.quantity))
        object.__setattr__(self, "weight", _decimal(self.weight))
        if not self.transfer_line_id or self.quantity <= ZERO or self.weight < ZERO:
            raise ValueError("Shipment line requires transfer line, positive quantity and valid weight")


@dataclass(frozen=True, slots=True)
class TransferShipment:
    transfer_id: str
    shipment_number: str
    dispatched_by_user_id: str
    verified_by_user_id: str
    lines: tuple[TransferShipmentLine, ...]
    carrier_id: str | None = None
    vehicle_id: str | None = None
    driver_id: str | None = None
    seal_number: str | None = None
    temperature_at_dispatch: Decimal | str | int | None = None
    status: str = "DISPATCHED"
    id: str = field(default_factory=new_uuid)

    def __post_init__(self) -> None:
        if self.temperature_at_dispatch is not None:
            object.__setattr__(self, "temperature_at_dispatch", _decimal(self.temperature_at_dispatch))
        if not self.transfer_id or not self.shipment_number or not self.dispatched_by_user_id:
            raise ValueError("Transfer shipment requires transfer, shipment number and dispatcher")
        if not self.verified_by_user_id or self.verified_by_user_id == self.dispatched_by_user_id:
            raise ValueError("Transfer shipment requires an independent verifier")
        if not self.lines or len({line.transfer_line_id for line in self.lines}) != len(self.lines):
            raise ValueError("Transfer shipment requires unique shipment lines")


@dataclass(frozen=True, slots=True)
class TransferCustodyEvent:
    shipment_id: str
    event_type: str
    delivered_by_user_id: str
    received_by_user_id: str
    location_id: str | None
    vehicle_id: str | None = None
    seal_number: str | None = None
    evidence_reference: str | None = None
    notes: str | None = None
    temperature: Decimal | str | int | None = None
    id: str = field(default_factory=new_uuid)
    occurred_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.temperature is not None:
            object.__setattr__(self, "temperature", _decimal(self.temperature))
        if not self.shipment_id or not self.event_type:
            raise ValueError("Custody event requires shipment and event type")
        if not self.delivered_by_user_id or not self.received_by_user_id:
            raise ValueError("Custody event requires delivered-by and received-by users")
        if self.delivered_by_user_id == self.received_by_user_id:
            raise ValueError("Custody handover requires distinct parties")
