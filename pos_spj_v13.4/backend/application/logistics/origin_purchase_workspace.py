"""Desktop coordinator for an origin-purchase workspace.

Procurement supplies commercial context; all shipment mutations remain owned by
the canonical Logistics application service.
"""

from backend.domain.logistics.entities import LogisticsShipment
from backend.domain.logistics.enums import SourceDocumentType
from backend.shared.ids import new_uuid


class OriginPurchaseWorkspaceService:
    def __init__(self, logistics_service, queries, *, mobile_base_url="/mobile/logistics/"):
        self._logistics = logistics_service
        self._queries = queries
        self._mobile_base_url = mobile_base_url

    def documents(self, *, branch_id, warehouse_id, search=""):
        return self._queries.loadable_documents(
            branch_id=branch_id, warehouse_id=warehouse_id, search=search)

    def open(self, shipment_id):
        return self._queries.workspace(shipment_id)

    def create_shipment(self, *, actor_user_id, branch_id, warehouse_id, document):
        if document.get("shipment_id"):
            return self.open(document["shipment_id"])
        if document["document_type"] == "PURCHASE_REQUISITION" and not document.get("supplier_id"):
            raise ValueError("Confirma un proveedor mediante compra directa antes de crear el embarque")
        shipment_id = new_uuid()
        shipment = LogisticsShipment.create(
            shipment_id=shipment_id, shipment_number=f"SHIP-{shipment_id[:8].upper()}",
            origin_type="SUPPLIER", origin_location=document["supplier_name"],
            origin_supplier_id=document.get("supplier_id"), destination_branch_id=branch_id,
            destination_warehouse_id=warehouse_id, buyer_user_id=actor_user_id,
            operation_id=new_uuid())
        shipment.add_source(SourceDocumentType(document["document_type"]), document["id"])
        self._logistics.create_shipment(actor_user_id=actor_user_id, shipment=shipment)
        return self.open(shipment.id)

    def mobile_handoff(self, shipment_id):
        detail = self.open(shipment_id)
        if detail is None:
            raise LookupError("Embarque inexistente")
        return {"url": f"{self._mobile_base_url}?shipment={shipment_id}",
                "shipment_id": shipment_id, "requires_login": True}

    def seal_root(self, *, actor_user_id, shipment_id, node_id, seal_code):
        self._logistics.seal(actor_user_id=actor_user_id, shipment_id=shipment_id,
                             node_id=node_id, seal_code=seal_code, seal_type="DESKTOP_REVIEW",
                             operation_id=new_uuid())
        return self.open(shipment_id)

    def dispatch(self, *, actor_user_id, shipment_id):
        self._logistics.dispatch(actor_user_id=actor_user_id, shipment_id=shipment_id,
                                 operation_id=new_uuid())
        return self.open(shipment_id)

    def authorize_variance(self, *, actor_user_id, shipment_id, source_line_id, reason):
        self._logistics.authorize_loading_variance(
            actor_user_id=actor_user_id, shipment_id=shipment_id,
            source_line_id=source_line_id, reason=reason, operation_id=new_uuid())
        return self.open(shipment_id)
