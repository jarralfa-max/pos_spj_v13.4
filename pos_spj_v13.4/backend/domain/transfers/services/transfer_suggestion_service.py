"""Decimal-only DOS/CV redistribution analytics, independent from UI and SQL."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..entities.transfer_suggestion import TransferSuggestion
from ..value_objects.transfer_node import TransferNode


ZERO = Decimal("0")
HUNDRED = Decimal("100")


def _decimal(value: Decimal | str | int) -> Decimal:
    if isinstance(value, (bool, float)):
        raise TypeError("Suggestion analytics must use Decimal")
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True, slots=True)
class TransferSuggestionSettings:
    minimum_days_of_supply: Decimal
    target_days_multiplier: Decimal
    target_days_floor: Decimal
    coefficient_of_variation_threshold: Decimal
    minimum_suggested_quantity: Decimal
    minimum_urgency_score: Decimal
    maximum_origin_stock_fraction: Decimal
    forecast_weight: Decimal
    zero_demand_days_of_supply: Decimal
    historical_window_days: int
    maximum_suggestions: int

    def __post_init__(self) -> None:
        decimal_fields = (
            "minimum_days_of_supply", "target_days_multiplier", "target_days_floor",
            "coefficient_of_variation_threshold", "minimum_suggested_quantity",
            "minimum_urgency_score", "maximum_origin_stock_fraction", "forecast_weight",
            "zero_demand_days_of_supply",
        )
        for name in decimal_fields:
            object.__setattr__(self, name, _decimal(getattr(self, name)))
        if any(getattr(self, name) < ZERO for name in decimal_fields):
            raise ValueError("Suggestion settings cannot be negative")
        if self.maximum_origin_stock_fraction > 1 or self.forecast_weight > 1:
            raise ValueError("Suggestion fractions must be between zero and one")
        if (self.target_days_floor <= ZERO or self.zero_demand_days_of_supply <= ZERO
                or self.minimum_suggested_quantity <= ZERO):
            raise ValueError("Suggestion DOS floors and minimum quantity must be positive")
        if self.minimum_urgency_score > HUNDRED:
            raise ValueError("Suggestion urgency threshold cannot exceed one hundred")
        if self.maximum_suggestions < 1 or self.historical_window_days < 1:
            raise ValueError("Suggestion limits and windows must be positive")


@dataclass(frozen=True, slots=True)
class TransferSupplySignal:
    product_id: str
    unit_id: str
    node: TransferNode
    available_quantity: Decimal
    reserved_quantity: Decimal
    minimum_stock: Decimal
    maximum_stock: Decimal
    safety_stock: Decimal
    inbound_in_transit: Decimal
    inbound_open_orders: Decimal
    outbound_open_transfers: Decimal
    historical_daily_demand: Decimal
    forecast_daily_demand: Decimal
    expiring_quantity: Decimal = ZERO

    def __post_init__(self) -> None:
        for name in (
            "available_quantity", "reserved_quantity", "minimum_stock", "maximum_stock",
            "safety_stock", "inbound_in_transit", "outbound_open_transfers",
            "inbound_open_orders",
            "historical_daily_demand", "forecast_daily_demand", "expiring_quantity",
        ):
            object.__setattr__(self, name, _decimal(getattr(self, name)))
        if any(getattr(self, name) < ZERO for name in (
            "available_quantity", "reserved_quantity", "minimum_stock", "maximum_stock",
            "safety_stock", "inbound_in_transit", "outbound_open_transfers",
            "inbound_open_orders",
            "historical_daily_demand", "forecast_daily_demand", "expiring_quantity",
        )):
            raise ValueError("Supply signals cannot be negative")
        if self.maximum_stock > ZERO and self.maximum_stock < self.minimum_stock:
            raise ValueError("Maximum stock cannot be lower than minimum stock")

    def net_available(self) -> Decimal:
        return max(ZERO, self.available_quantity - self.reserved_quantity
                   + self.inbound_in_transit + self.inbound_open_orders
                   - self.outbound_open_transfers)

    def daily_demand(self, forecast_weight: Decimal) -> Decimal:
        return (self.historical_daily_demand * (Decimal("1") - forecast_weight)
                + self.forecast_daily_demand * forecast_weight)


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def coefficient_of_variation(values: list[Decimal]) -> Decimal:
    if len(values) < 2:
        return ZERO
    mean = sum(values, ZERO) / Decimal(len(values))
    if mean == ZERO:
        return ZERO
    variance = sum(((value - mean) ** 2 for value in values), ZERO) / Decimal(len(values))
    return variance.sqrt() / mean


class TransferSuggestionService:
    def generate(self, *, signals: tuple[TransferSupplySignal, ...],
                 settings: TransferSuggestionSettings, operation_id: str,
                 source_channel: str, source_reference_id: str | None = None
                 ) -> tuple[TransferSuggestion, ...]:
        grouped: dict[tuple[str, str], list[TransferSupplySignal]] = {}
        for signal in signals:
            grouped.setdefault((signal.product_id, signal.unit_id), []).append(signal)
        suggestions: list[TransferSuggestion] = []
        for (product_id, unit_id), product_signals in grouped.items():
            calculated: list[tuple[TransferSupplySignal, Decimal, Decimal]] = []
            for signal in product_signals:
                demand = signal.daily_demand(settings.forecast_weight)
                dos = (signal.net_available() / demand if demand > ZERO
                       else settings.zero_demand_days_of_supply)
                calculated.append((signal, dos, demand))
            if len(calculated) < 2:
                continue
            dos_values = [item[1] for item in calculated]
            variation = coefficient_of_variation(dos_values)
            if variation < settings.coefficient_of_variation_threshold:
                continue
            median = _median(dos_values)
            target = max(settings.target_days_floor,
                         median * settings.target_days_multiplier)
            origins = sorted(
                (item for item in calculated
                 if (item[1] > target or (item[0].maximum_stock > ZERO
                                          and item[0].net_available() > item[0].maximum_stock))
                 and item[0].net_available() > item[0].minimum_stock + item[0].safety_stock),
                key=lambda item: (item[0].expiring_quantity, item[1]), reverse=True,
            )
            destinations = sorted(
                (item for item in calculated
                 if item[1] < settings.minimum_days_of_supply
                 or item[0].net_available() < item[0].minimum_stock + item[0].safety_stock),
                key=lambda item: item[1],
            )
            for destination, destination_dos, destination_demand in destinations:
                for origin, origin_dos, origin_demand in origins:
                    if origin.node.identity() == destination.node.identity():
                        continue
                    protected = max(ZERO, origin.net_available()
                                    - origin.minimum_stock - origin.safety_stock)
                    excess = (max(ZERO, (origin_dos - target) * origin_demand)
                              if origin_demand > ZERO else protected)
                    deficit = max(ZERO, (target - destination_dos) * destination_demand)
                    origin_cap = origin.net_available() * settings.maximum_origin_stock_fraction
                    destination_capacity = (max(ZERO, destination.maximum_stock
                                                - destination.net_available())
                                            if destination.maximum_stock > ZERO else deficit)
                    quantity = min(excess, deficit, protected, origin_cap, destination_capacity)
                    score = (HUNDRED if destination_dos <= ZERO else
                             min(HUNDRED, HUNDRED * max(
                                 ZERO, Decimal("1") - destination_dos / target)))
                    if (quantity < settings.minimum_suggested_quantity
                            or score < settings.minimum_urgency_score):
                        continue
                    suggestions.append(TransferSuggestion(
                        product_id=product_id, unit_id=unit_id,
                        origin_node=origin.node, destination_node=destination.node,
                        suggested_quantity=quantity,
                        origin_days_of_supply=origin_dos,
                        destination_days_of_supply=destination_dos,
                        target_days_of_supply=target,
                        coefficient_of_variation=variation, urgency_score=score,
                        operation_id=operation_id, source_channel=source_channel,
                        source_reference_id=source_reference_id,
                    ))
        suggestions.sort(key=lambda item: item.urgency_score, reverse=True)
        return tuple(suggestions[:settings.maximum_suggestions])
