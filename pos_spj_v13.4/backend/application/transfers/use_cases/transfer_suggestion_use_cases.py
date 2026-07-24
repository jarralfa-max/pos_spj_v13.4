"""TRF-16 configured suggestion generation and Forecast event integration."""
from __future__ import annotations

from typing import Protocol

from backend.shared.ids import new_uuid
from backend.domain.transfers.events import TransferEvents, event_payload
from backend.domain.transfers.exceptions import DuplicateOperationError
from backend.domain.transfers.repository_ports import TransferSuggestionRepository
from backend.domain.transfers.services.transfer_suggestion_service import (
    TransferSuggestionService,
    TransferSuggestionSettings,
    TransferSupplySignal,
)
from ..authorization import TransferAuthorizationPolicy
from ..commands.transfer_request_commands import GenerateTransferSuggestionsCommand
from ..dto.suggestion_dto import TransferSuggestionDTO
from ..permissions import TransferPermissions
from .transfer_request_use_cases import TransferEventSink


class TransferSuggestionSupplyQueryService(Protocol):
    def list_supply_signals(self, *, product_ids: tuple[str, ...],
                            node_ids: tuple[str, ...],
                            historical_window_days: int) -> tuple[TransferSupplySignal, ...]: ...


class TransferSuggestionSettingsQueryService(Protocol):
    def get_settings(self, *, branch_id: str | None,
                     transfer_type: str) -> TransferSuggestionSettings: ...


def _dto(suggestion) -> TransferSuggestionDTO:
    return TransferSuggestionDTO(
        suggestion_id=suggestion.id, product_id=suggestion.product_id,
        unit_id=suggestion.unit_id, origin_node=suggestion.origin_node.identity(),
        destination_node=suggestion.destination_node.identity(),
        suggested_quantity=suggestion.suggested_quantity,
        origin_days_of_supply=suggestion.origin_days_of_supply,
        destination_days_of_supply=suggestion.destination_days_of_supply,
        target_days_of_supply=suggestion.target_days_of_supply,
        coefficient_of_variation=suggestion.coefficient_of_variation,
        urgency_score=suggestion.urgency_score, status=suggestion.status,
        source_channel=suggestion.source_channel,
    )


class GenerateTransferSuggestionsUseCase:
    def __init__(self, repository: TransferSuggestionRepository,
                 supply_query: TransferSuggestionSupplyQueryService,
                 settings_query: TransferSuggestionSettingsQueryService,
                 authorization: TransferAuthorizationPolicy,
                 service: TransferSuggestionService,
                 event_sink: TransferEventSink | None = None) -> None:
        self._repository = repository
        self._supply_query = supply_query
        self._settings_query = settings_query
        self._authorization = authorization
        self._service = service
        self._events = event_sink

    def execute(self, command: GenerateTransferSuggestionsCommand) -> tuple[TransferSuggestionDTO, ...]:
        if self._repository.operation_exists(command.operation_id):
            raise DuplicateOperationError("Suggestion generation operation already exists")
        self._authorization.require(user_id=command.requested_by_user_id,
                                    permission_code=TransferPermissions.REQUEST_VIEW)
        settings = self._settings_query.get_settings(
            branch_id=command.configuration_branch_id,
            transfer_type=command.transfer_type.value,
        )
        signals = self._supply_query.list_supply_signals(
            product_ids=command.product_ids, node_ids=command.node_ids,
            historical_window_days=settings.historical_window_days)
        suggestions = self._service.generate(
            signals=signals, settings=settings, operation_id=command.operation_id,
            source_channel=command.source_channel,
            source_reference_id=command.source_reference_id,
        )
        self._repository.record_generation(
            generation_id=new_uuid(), operation_id=command.operation_id,
            source_channel=command.source_channel,
            source_reference_id=command.source_reference_id,
            actor_id=command.requested_by_user_id,
        )
        self._repository.save_all(suggestions)
        if self._events is not None:
            for suggestion in suggestions:
                self._events.collect(event_payload(
                    TransferEvents.SUGGESTION_CREATED,
                    operation_id=command.operation_id, entity_id=suggestion.id,
                    user_id=command.requested_by_user_id,
                    product_id=suggestion.product_id,
                    origin_node=suggestion.origin_node.identity(),
                    destination_node=suggestion.destination_node.identity(),
                ))
        return tuple(_dto(item) for item in suggestions)


class ForecastTransferSuggestionRequestedHandler:
    """Maps Forecast's canonical request event to the shared generation use case."""
    EVENT_NAME = "TRANSFER_SUGGESTION_REQUESTED"

    def __init__(self, use_case: GenerateTransferSuggestionsUseCase) -> None:
        self._use_case = use_case

    def handle(self, event: dict[str, object]) -> tuple[TransferSuggestionDTO, ...]:
        if event.get("event_name") != self.EVENT_NAME:
            raise ValueError("Unsupported Forecast event")
        return self._use_case.execute(GenerateTransferSuggestionsCommand(
            requested_by_user_id=str(event["user_id"]),
            operation_id=str(event["operation_id"]), source_channel="FORECAST",
            source_reference_id=str(event["entity_id"]),
            product_ids=tuple(str(value) for value in event.get("product_ids", ())),
            node_ids=tuple(str(value) for value in event.get("node_ids", ())),
            configuration_branch_id=(str(event["branch_id"]) if event.get("branch_id") else None),
        ))
