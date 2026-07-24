from decimal import Decimal

import pytest

from backend.application.transfers.authorization import TransferAuthorizationPolicy
from backend.application.transfers.commands.transfer_request_commands import GenerateTransferSuggestionsCommand
from backend.application.transfers.permissions import TransferPermissions
from backend.application.transfers.use_cases.transfer_suggestion_use_cases import (
    ForecastTransferSuggestionRequestedHandler,
    GenerateTransferSuggestionsUseCase,
)
from backend.domain.transfers.enums import TransferNodeType
from backend.domain.transfers.exceptions import DuplicateOperationError
from backend.domain.transfers.services.transfer_suggestion_service import (
    TransferSuggestionService,
    TransferSuggestionSettings,
    TransferSupplySignal,
    coefficient_of_variation,
)
from backend.domain.transfers.value_objects.transfer_node import TransferNode


def _settings(*, forecast_weight="0"):
    return TransferSuggestionSettings(
        minimum_days_of_supply="3", target_days_multiplier="1",
        target_days_floor="5", coefficient_of_variation_threshold="0.40",
        minimum_suggested_quantity="1", minimum_urgency_score="10",
        maximum_origin_stock_fraction="0.80", forecast_weight=forecast_weight,
        zero_demand_days_of_supply="365", historical_window_days=30,
        maximum_suggestions=10,
    )


def _signal(branch, stock, historical, forecast):
    return TransferSupplySignal(
        product_id="product", unit_id="unit",
        node=TransferNode(TransferNodeType.WAREHOUSE, branch, f"{branch}-warehouse"),
        available_quantity=stock, reserved_quantity="0", minimum_stock="0",
        maximum_stock="200", safety_stock="0", inbound_in_transit="0",
        inbound_open_orders="0", outbound_open_transfers="0",
        historical_daily_demand=historical,
        forecast_daily_demand=forecast,
    )


class Repository:
    def __init__(self): self.items, self.operations, self.generations = [], set(), []
    def save_all(self, suggestions): self.items.extend(suggestions)
    def operation_exists(self, operation_id): return operation_id in self.operations
    def record_generation(self, **values):
        self.operations.add(values["operation_id"]); self.generations.append(values)


class SupplyQuery:
    def __init__(self, signals): self.signals, self.calls = signals, []
    def list_supply_signals(self, **filters): self.calls.append(filters); return self.signals


class SettingsQuery:
    def __init__(self, settings): self.settings, self.calls = settings, []
    def get_settings(self, **scope): self.calls.append(scope); return self.settings


class Permissions:
    def has_permission(self, user_id, permission_code):
        return user_id == "planner" and permission_code == TransferPermissions.REQUEST_VIEW


class Events:
    def __init__(self): self.items = []
    def collect(self, event): self.items.append(event)


def test_decimal_dos_and_cv_generate_configured_redistribution_without_execution():
    service = TransferSuggestionService()
    suggestions = service.generate(
        signals=(_signal("origin", "100", "10", "10"),
                 _signal("destination", "10", "10", "10")),
        settings=_settings(), operation_id="suggest-operation",
        source_channel="MANUAL",
    )
    assert len(suggestions) == 1
    suggestion = suggestions[0]
    assert suggestion.origin_days_of_supply == Decimal("10")
    assert suggestion.destination_days_of_supply == Decimal("1")
    assert suggestion.target_days_of_supply == Decimal("5.5")
    assert suggestion.suggested_quantity == Decimal("45")
    assert suggestion.coefficient_of_variation == Decimal("0.8181818181818181818181818182")
    assert suggestion.status == "PROPOSED"
    assert coefficient_of_variation([Decimal("5"), Decimal("5")]) == Decimal("0")


def test_balanced_dos_or_cv_below_configuration_produces_no_suggestion():
    suggestions = TransferSuggestionService().generate(
        signals=(_signal("a", "50", "10", "10"), _signal("b", "50", "10", "10")),
        settings=_settings(), operation_id="balanced", source_channel="MANUAL")
    assert suggestions == ()
    with pytest.raises(TypeError):
        TransferSuggestionSettings(
            minimum_days_of_supply=3.0, target_days_multiplier="1", target_days_floor="5",
            coefficient_of_variation_threshold="0.4", minimum_suggested_quantity="1",
            minimum_urgency_score="10", maximum_origin_stock_fraction="0.8",
            forecast_weight="0", zero_demand_days_of_supply="365",
            historical_window_days=30, maximum_suggestions=10)


def test_forecast_event_uses_configuration_query_persists_proposals_and_is_idempotent():
    repository, events = Repository(), Events()
    supply = SupplyQuery((_signal("origin", "100", "10", "10"),
                          _signal("destination", "10", "1", "10")))
    settings = SettingsQuery(_settings(forecast_weight="1"))
    use_case = GenerateTransferSuggestionsUseCase(
        repository, supply, settings, TransferAuthorizationPolicy(Permissions()),
        TransferSuggestionService(), events)
    result = ForecastTransferSuggestionRequestedHandler(use_case).handle({
        "event_name": "TRANSFER_SUGGESTION_REQUESTED", "user_id": "planner",
        "operation_id": "forecast-operation", "entity_id": "forecast-run",
        "branch_id": "destination", "product_ids": ["product"],
        "node_ids": ["origin", "destination"],
    })
    assert len(result) == 1
    assert result[0].source_channel == "FORECAST"
    assert repository.items[0].source_reference_id == "forecast-run"
    assert settings.calls == [{"branch_id": "destination",
                               "transfer_type": "REPLENISHMENT_TRANSFER"}]
    assert supply.calls[0]["product_ids"] == ("product",)
    assert supply.calls[0]["historical_window_days"] == 30
    assert events.items[0]["event_name"] == "TRANSFER_SUGGESTION_CREATED"
    with pytest.raises(DuplicateOperationError):
        ForecastTransferSuggestionRequestedHandler(use_case).handle({
            "event_name": "TRANSFER_SUGGESTION_REQUESTED", "user_id": "planner",
            "operation_id": "forecast-operation", "entity_id": "forecast-run",
        })


def test_zero_demand_origin_is_a_finite_configured_surplus_candidate():
    result = TransferSuggestionService().generate(
        signals=(_signal("no-demand-origin", "100", "0", "0"),
                 _signal("destination", "5", "10", "10")),
        settings=_settings(), operation_id="zero-demand", source_channel="MANUAL")
    assert len(result) == 1
    assert result[0].origin_days_of_supply == Decimal("365")
    assert result[0].suggested_quantity > 0
