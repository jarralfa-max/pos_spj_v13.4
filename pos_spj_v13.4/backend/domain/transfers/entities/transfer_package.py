"""Transfer package entity: seals, tare, labels, and catch-weight packing."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from backend.shared.ids import new_uuid


ZERO = Decimal("0")


def _decimal(value: Decimal | str | int) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError("Transfer package weights and temperatures must be Decimal")
    return Decimal(str(value))


@dataclass(frozen=True, slots=True)
class TransferPackage:
    transfer_id: str
    package_number: str
    package_type: str
    weight: Decimal | str | int
    tare: Decimal | str | int
    line_ids: tuple[str, ...]
    seal_number: str | None = None
    temperature: Decimal | str | int | None = None
    label_id: str | None = None
    status: str = "READY"
    id: str = field(default_factory=new_uuid)

    def __post_init__(self) -> None:
        object.__setattr__(self, "weight", _decimal(self.weight))
        object.__setattr__(self, "tare", _decimal(self.tare))
        if self.temperature is not None:
            object.__setattr__(self, "temperature", _decimal(self.temperature))
        if not self.transfer_id or not self.package_number or not self.package_type:
            raise ValueError("Transfer package requires transfer, package number, and type")
        if self.weight <= ZERO or self.tare < ZERO or self.tare > self.weight:
            raise ValueError("Transfer package requires positive gross weight and valid tare")
        if not self.line_ids or len(set(self.line_ids)) != len(self.line_ids):
            raise ValueError("Transfer package requires unique packed transfer line IDs")

    @property
    def net_weight(self) -> Decimal:
        return self.weight - self.tare
