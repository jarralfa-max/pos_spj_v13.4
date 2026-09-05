"""InventoryForecast (§28, BI-13) — demand forecast + current stock position
projected forward into projected_stock / days_of_supply / stockout &
overstock probability / reorder_date.

`InventoryPosition` is the seam to the Inventory bounded context (§10: BI
consumes canonical query services, never owns their data) — it is a plain
snapshot the caller supplies, not something this package fetches itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class InventoryPosition:
    product_id: str
    branch_id: str
    current_stock: Decimal
    reserved: Decimal
    incoming_stock: Decimal
    incoming_arrival_date: date | None
    supplier_lead_time_days: int

    def __post_init__(self) -> None:
        if not self.product_id or not self.branch_id:
            raise ValueError("InventoryPosition requires product_id and branch_id")
        for name in ("current_stock", "reserved", "incoming_stock"):
            if getattr(self, name) < 0:
                raise ValueError(f"InventoryPosition.{name} must be >= 0")
        if self.supplier_lead_time_days < 0:
            raise ValueError("InventoryPosition.supplier_lead_time_days must be >= 0")
        if self.incoming_stock > 0 and self.incoming_arrival_date is None:
            raise ValueError("incoming_arrival_date is required when incoming_stock > 0")

    def available_stock(self) -> Decimal:
        return self.current_stock - self.reserved


@dataclass(frozen=True, slots=True)
class InventoryForecastPoint:
    date: date
    projected_stock: Decimal
    days_of_supply: Decimal | None
    stockout_probability: Decimal
    overstock_probability: Decimal

    def __post_init__(self) -> None:
        for name in ("stockout_probability", "overstock_probability"):
            value = getattr(self, name)
            if not (Decimal("0") <= value <= Decimal("1")):
                raise ValueError(f"InventoryForecastPoint.{name} must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class InventoryForecast:
    product_id: str
    branch_id: str
    safety_stock: Decimal
    reorder_point: Decimal
    reorder_date: date | None
    points: tuple[InventoryForecastPoint, ...]

    def __post_init__(self) -> None:
        if not self.product_id or not self.branch_id:
            raise ValueError("InventoryForecast requires product_id and branch_id")
        if self.safety_stock < 0 or self.reorder_point < 0:
            raise ValueError("InventoryForecast.safety_stock/reorder_point must be >= 0")
        if not self.points:
            raise ValueError("InventoryForecast.points must not be empty")
        dates = [p.date for p in self.points]
        if dates != sorted(dates):
            raise ValueError("InventoryForecast.points must be sorted by date")
