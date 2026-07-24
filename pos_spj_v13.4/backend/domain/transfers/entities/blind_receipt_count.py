"""Blind receipt count that hides expected values until immutable confirmation."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid
from ..exceptions import TransferInvalidStatusError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _decimal(value: Decimal | str | int) -> Decimal:
    if isinstance(value, (bool, float)):
        raise TypeError("Blind receipt values must use Decimal, string, or integer")
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True, slots=True)
class BlindReceiptObservedLine:
    transfer_line_id: str
    observed_quantity: Decimal
    observed_weight: Decimal = Decimal("0")
    accepted: bool = True
    lot_id: str | None = None
    observed_pieces: Decimal = Decimal("0")
    temperature: Decimal | None = None
    expires_on: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_quantity", _decimal(self.observed_quantity))
        object.__setattr__(self, "observed_weight", _decimal(self.observed_weight))
        object.__setattr__(self, "observed_pieces", _decimal(self.observed_pieces))
        if self.temperature is not None:
            object.__setattr__(self, "temperature", _decimal(self.temperature))
        if (self.observed_quantity < 0 or self.observed_weight < 0
                or self.observed_pieces < 0):
            raise ValueError("Blind receipt observations cannot be negative")
        if self.observed_pieces != self.observed_pieces.to_integral_value():
            raise ValueError("Blind receipt pieces must be a whole Decimal value")


@dataclass(slots=True)
class BlindReceiptCount:
    transfer_id: str
    shipment_id: str
    receiver_user_id: str
    start_operation_id: str
    id: str = field(default_factory=new_uuid)
    status: str = "CAPTURING"
    lines: tuple[BlindReceiptObservedLine, ...] = ()
    receipt_id: str | None = None
    created_at: str = field(default_factory=_now)
    confirmed_at: str | None = None

    def capture(self, lines: tuple[BlindReceiptObservedLine, ...]) -> None:
        if self.status != "CAPTURING":
            raise TransferInvalidStatusError("Confirmed blind count cannot be edited")
        if not lines or len({line.transfer_line_id for line in lines}) != len(lines):
            raise ValueError("Blind count requires unique observed lines")
        self.lines = lines

    def confirm(self, receipt_id: str) -> None:
        if self.status != "CAPTURING" or not self.lines:
            raise TransferInvalidStatusError("Blind count must be captured before confirmation")
        if not receipt_id:
            raise ValueError("Confirmed blind count requires receipt identity")
        self.receipt_id = receipt_id
        self.status = "CONFIRMED"
        self.confirmed_at = _now()
