from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from core.delivery.domain.policies import DeliveryTotalPolicy


class DeliveryTotalRepositoryPort(Protocol):
    def get_order_total(self, order_id: int) -> float: ...

    def list_item_subtotals_for_order(self, order_id: int) -> list[float]: ...

    def update_order_total(
        self,
        order_id: int,
        total: float,
        *,
        mark_weight_adjusted: bool = True,
        commit: bool = True,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class DeliveryTotalResult:
    order_id: int
    old_total: float
    new_total: float
    changed: bool


class DeliveryTotalService:
    """Canonical application service for delivery order totals.

    `delivery_items.subtotal` is the operational source used to recalculate
    `delivery_orders.total`. Commercial sale totals remain a projection owned by
    `SaleDeliveryProjectionService`; this service never writes `ventas`.
    """

    def __init__(self, repository: DeliveryTotalRepositoryPort) -> None:
        self.repository = repository

    def recalculate_order_total_details(
        self,
        order_id: int,
        *,
        mark_weight_adjusted: bool = True,
        commit: bool = True,
    ) -> DeliveryTotalResult:
        old_total = self.repository.get_order_total(order_id)
        subtotals = self.repository.list_item_subtotals_for_order(order_id)
        new_total = DeliveryTotalPolicy.calculate_total(subtotals)
        self.repository.update_order_total(
            order_id,
            new_total,
            mark_weight_adjusted=mark_weight_adjusted,
            commit=commit,
        )
        return DeliveryTotalResult(
            order_id=order_id,
            old_total=old_total,
            new_total=new_total,
            changed=old_total != new_total,
        )

    def recalculate_order_total(
        self,
        order_id: int,
        *,
        mark_weight_adjusted: bool = True,
        commit: bool = True,
    ) -> float:
        return self.recalculate_order_total_details(
            order_id,
            mark_weight_adjusted=mark_weight_adjusted,
            commit=commit,
        ).new_total
