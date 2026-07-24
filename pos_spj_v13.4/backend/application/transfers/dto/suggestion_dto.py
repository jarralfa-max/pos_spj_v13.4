"""Read-only transfer suggestion results for UI and integrations."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TransferSuggestionDTO:
    suggestion_id: str
    product_id: str
    unit_id: str
    origin_node: tuple[object, str | None, str | None, str | None]
    destination_node: tuple[object, str | None, str | None, str | None]
    suggested_quantity: Decimal
    origin_days_of_supply: Decimal
    destination_days_of_supply: Decimal
    target_days_of_supply: Decimal
    coefficient_of_variation: Decimal
    urgency_score: Decimal
    status: str
    source_channel: str
