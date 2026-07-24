"""Outbound Quality/Loss/Cost contracts without leaking their internals into Transfers."""
from typing import Protocol

from backend.domain.transfers.events import TransferEvents


class TransferLossCaseGateway(Protocol):
    def request_loss_case(self, payload: dict[str, object]) -> None: ...


class TransferEconomicImpactGateway(Protocol):
    def record_transfer_impact(self, event_name: str,
                               payload: dict[str, object]) -> None: ...


class TransferLossCaseRequestedHandler:
    def __init__(self, gateway: TransferLossCaseGateway) -> None:
        self._gateway = gateway

    def handle(self, event: dict[str, object]) -> None:
        if (event.get("event_name") != TransferEvents.DIFFERENCE_RESOLVED
                or event.get("resolution_type") != "CREATE_LOSS_CASE"):
            raise ValueError("Event does not request a transfer loss case")
        self._gateway.request_loss_case({
            "event_name": "LOSS_CASE_REQUESTED",
            "transfer_id": event["entity_id"],
            "difference_id": event["difference_id"],
            "resolution_id": event["resolution_id"],
            "operation_id": event["operation_id"],
            "requested_by_user_id": event["user_id"],
        })


class TransferEconomicImpactHandler:
    SUPPORTED_EVENTS = frozenset({
        TransferEvents.DISPATCHED,
        TransferEvents.RECEIVED,
        TransferEvents.DIFFERENCE_CONFIRMED,
        TransferEvents.LOSS_CONFIRMED,
        TransferEvents.RETURN_COMPLETED,
    })

    def __init__(self, gateway: TransferEconomicImpactGateway) -> None:
        self._gateway = gateway

    def handle(self, event: dict[str, object]) -> None:
        event_name = str(event.get("event_name", ""))
        if event_name not in self.SUPPORTED_EVENTS:
            raise ValueError("Unsupported transfer economic event")
        self._gateway.record_transfer_impact(event_name, event)
