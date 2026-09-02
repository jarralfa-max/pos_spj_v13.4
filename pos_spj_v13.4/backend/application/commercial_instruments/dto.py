"""Read-side DTOs for the Commercial Instruments application layer. Mirrors
backend/application/loyalty/dto.py's style."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.commercial_instruments.entities.coupon_definition import CouponDefinition
from backend.domain.commercial_instruments.entities.coupon_instance import CouponInstance
from backend.domain.commercial_instruments.entities.voucher_instance import VoucherInstance
from backend.domain.commercial_instruments.entities.voucher_transaction import VoucherTransaction


@dataclass(frozen=True, slots=True)
class CouponDefinitionDTO:
    id: str
    code: str
    name: str
    coupon_type: str
    benefit_type: str
    benefit_value: Decimal
    active: bool

    @classmethod
    def from_entity(cls, definition: CouponDefinition) -> "CouponDefinitionDTO":
        return cls(
            id=definition.id, code=definition.code, name=definition.name,
            coupon_type=definition.coupon_type.value, benefit_type=definition.benefit_type.value,
            benefit_value=definition.benefit_value, active=definition.active,
        )


@dataclass(frozen=True, slots=True)
class CouponInstanceDTO:
    id: str
    definition_id: str
    code: str
    status: str
    customer_id: str | None
    sale_id: str | None

    @classmethod
    def from_entity(cls, instance: CouponInstance) -> "CouponInstanceDTO":
        return cls(
            id=instance.id, definition_id=instance.definition_id, code=instance.code,
            status=instance.status.value, customer_id=instance.customer_id,
            sale_id=instance.sale_id,
        )


@dataclass(frozen=True, slots=True)
class VoucherInstanceDTO:
    id: str
    definition_id: str
    code: str
    status: str
    balance: Decimal
    customer_id: str | None

    @classmethod
    def from_entity(cls, instance: VoucherInstance, balance: Decimal) -> "VoucherInstanceDTO":
        return cls(
            id=instance.id, definition_id=instance.definition_id, code=instance.code,
            status=instance.status.value, balance=balance, customer_id=instance.customer_id,
        )


@dataclass(frozen=True, slots=True)
class VoucherTransactionDTO:
    id: str
    voucher_instance_id: str
    transaction_type: str
    amount: Decimal
    status: str
    operation_id: str

    @classmethod
    def from_entity(cls, transaction: VoucherTransaction) -> "VoucherTransactionDTO":
        return cls(
            id=transaction.id, voucher_instance_id=transaction.voucher_instance_id,
            transaction_type=transaction.transaction_type.value, amount=transaction.amount,
            status=transaction.status.value, operation_id=transaction.operation_id,
        )
