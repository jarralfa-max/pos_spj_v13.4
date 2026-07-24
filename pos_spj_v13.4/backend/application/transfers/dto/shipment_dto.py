"""DTOs for transfer shipments and dispatch."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TransferShipmentLineDTO:
    transfer_line_id: str
    quantity: Decimal
    weight: Decimal


@dataclass(frozen=True, slots=True)
class TransferShipmentDTO:
    shipment_id: str
    transfer_id: str
    shipment_number: str
    status: str
    transfer_status: str
    seal_number: str | None
    vehicle_id: str | None
    custody_event_id: str
    lines: tuple[TransferShipmentLineDTO, ...]
