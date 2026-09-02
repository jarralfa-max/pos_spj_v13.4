"""VoucherDefinition — a category of voucher (master prompt §22). Unlike
`CouponDefinition`, carries no fixed benefit value — a refund/compensation
voucher's face value varies per instance (each one is issued for the actual
amount owed), set on `VoucherInstance` issuance instead."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.commercial_instruments.enums import VoucherType
from backend.domain.commercial_instruments.exceptions import InvalidVoucherDefinitionError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class VoucherDefinition:
    id: str
    code: str
    name: str
    voucher_type: VoucherType
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.code or not self.code.strip():
            raise InvalidVoucherDefinitionError("code es obligatorio")
        if not self.name or not self.name.strip():
            raise InvalidVoucherDefinitionError("name es obligatorio")

    @classmethod
    def create(cls, code: str, name: str, voucher_type: VoucherType) -> "VoucherDefinition":
        return cls(id=new_uuid(), code=code.strip(), name=name.strip(),
                   voucher_type=voucher_type)

    def deactivate(self) -> None:
        self.active = False
        self.updated_at = _utcnow()

    def activate(self) -> None:
        self.active = True
        self.updated_at = _utcnow()
