"""Runtime subscriptions owned by Logistics."""

from backend.domain.logistics.entities import LogisticsShipment
from backend.domain.logistics.enums import SourceDocumentType


def wire_logistics(bus, service) -> dict:
    """Wire durable cross-context commands to Logistics application services."""
    def create_requested(payload: dict) -> None:
        shipment = LogisticsShipment.create(
            shipment_number=payload["shipment_number"],
            origin_type=payload["origin_type"],
            origin_location=payload["origin_location"],
            destination_branch_id=payload["destination_branch_id"],
            destination_warehouse_id=payload["destination_warehouse_id"],
            buyer_user_id=payload["actor_user_id"],
            operation_id=payload["operation_id"],
            origin_supplier_id=payload.get("origin_supplier_id"),
            vehicle_id=payload.get("vehicle_id"))
        for source in payload.get("sources", []):
            shipment.add_source(
                SourceDocumentType(source["source_document_type"]),
                source["source_document_id"])
        service.create_shipment(actor_user_id=payload["actor_user_id"], shipment=shipment)

    bus.subscribe("LOGISTICS_SHIPMENT_CREATE_REQUESTED", create_requested,
                  priority=80, label="logistics_shipment_create")
    return {"subscribed": ["LOGISTICS_SHIPMENT_CREATE_REQUESTED"], "count": 1}
