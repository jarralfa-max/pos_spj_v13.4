"""DTOs for transfer packages."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TransferPackageDTO:
    package_id: str
    transfer_id: str
    package_number: str
    package_type: str
    gross_weight: Decimal
    tare: Decimal
    net_weight: Decimal
    seal_number: str | None
    temperature: Decimal | None
    label_id: str | None
    line_ids: tuple[str, ...]
    status: str
