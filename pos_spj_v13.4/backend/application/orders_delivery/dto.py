"""Read-side DTOs for the Pedidos/Delivery application layer — flat, frozen
projections a caller (UI/API) can use without touching domain entities
directly. Mirrors backend/application/sales/dto.py's `SaleDTO`/`SaleLineDTO`
shape exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from backend.domain.orders_delivery.delivery_job import DeliveryJob
from backend.domain.orders_delivery.entities import CustomerOrder, CustomerOrderLine


@dataclass(frozen=True, slots=True)
class CustomerOrderLineDTO:
    id: str
    product_id: str
    variant_id: str | None
    requested_quantity: Decimal | None
    requested_weight: Decimal | None
    unit_price_snapshot: Decimal
    requested_subtotal: Decimal
    catch_weight_enabled: bool
    status: str
    product_snapshot: Mapping[str, Any]

    @classmethod
    def from_entity(cls, line: CustomerOrderLine) -> "CustomerOrderLineDTO":
        return cls(
            id=line.id, product_id=line.product_id, variant_id=line.variant_id,
            requested_quantity=line.requested_quantity.value if line.requested_quantity else None,
            requested_weight=line.requested_weight.value if line.requested_weight else None,
            unit_price_snapshot=line.unit_price_snapshot,
            requested_subtotal=line.requested_subtotal,
            catch_weight_enabled=line.catch_weight_enabled,
            status=line.status.value, product_snapshot=dict(line.product_snapshot),
        )


@dataclass(frozen=True, slots=True)
class CustomerOrderDTO:
    id: str
    order_number: str | None
    branch_id: str
    channel: str
    order_type: str
    fulfillment_type: str
    status: str
    payment_status: str
    fulfillment_status: str
    customer_approval_status: str
    sale_id: str | None
    grand_total: Decimal
    lines: tuple[CustomerOrderLineDTO, ...]

    @classmethod
    def from_entity(cls, order: CustomerOrder) -> "CustomerOrderDTO":
        return cls(
            id=order.id, order_number=order.order_number, branch_id=order.branch_id,
            channel=order.channel.value, order_type=order.order_type.value,
            fulfillment_type=order.fulfillment_type.value, status=order.status.value,
            payment_status=order.payment_status.value,
            fulfillment_status=order.fulfillment_status.value,
            customer_approval_status=order.customer_approval_status.value,
            sale_id=order.sale_id,
            grand_total=order.totals.grand_total,
            lines=tuple(CustomerOrderLineDTO.from_entity(line) for line in order.lines),
        )


@dataclass(frozen=True, slots=True)
class DeliveryJobDTO:
    id: str
    order_id: str
    branch_id: str
    delivery_number: str | None
    status: str
    assigned_driver_id: str | None
    delivery_fee: Decimal
    cash_to_collect: Decimal

    @classmethod
    def from_entity(cls, job: DeliveryJob) -> "DeliveryJobDTO":
        return cls(
            id=job.id, order_id=job.order_id, branch_id=job.branch_id,
            delivery_number=job.delivery_number, status=job.status.value,
            assigned_driver_id=job.assigned_driver_id, delivery_fee=job.delivery_fee,
            cash_to_collect=job.cash_to_collect,
        )
