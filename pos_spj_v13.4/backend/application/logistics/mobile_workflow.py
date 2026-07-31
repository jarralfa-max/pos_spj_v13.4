"""Cross-context orchestrator for mobile origin loading; never a source of truth."""

from __future__ import annotations

import base64
from datetime import date
from decimal import Decimal
from typing import Protocol

from backend.api.mobile_session import MobileIdentity
from backend.domain.logistics.entities import LogisticsShipment, ShipmentContentAssignment
from backend.domain.logistics.enums import SourceDocumentType
from backend.domain.logistics.qr_identity import PermanentContainerQrService
from backend.infrastructure.db.repositories.logistics_repository import LogisticsRepository


class PhotoGateway(Protocol):
    def save(self, *, content: bytes, file_name: str, content_type: str,
             actor_user_id: str, operation_id: str) -> str: ...


class MobileOriginPurchaseWorkflow:
    def __init__(self, connection, logistics_service, qr_service: PermanentContainerQrService,
                 photo_gateway: PhotoGateway) -> None:
        self._connection = connection
        self._logistics = logistics_service
        self._repo = LogisticsRepository(connection)
        self._qr = qr_service
        self._photos = photo_gateway

    def list_documents(self, identity: MobileIdentity, query: str) -> dict:
        self._require(identity, "logistics.shipment.create")
        like = f"%{query.strip()}%"
        rows = []
        for table, doc_type, number, statuses in (
            ("purchase_orders", "PURCHASE_ORDER", "document_number",
             ("APPROVED", "SENT", "ACKNOWLEDGED", "PARTIALLY_LOADED")),
            ("direct_purchases", "DIRECT_PURCHASE", "document_number",
             ("DRAFT", "CONFIRMED")),
        ):
            placeholders = ",".join("?" for _ in statuses)
            rows.extend((doc_type, *row) for row in self._connection.execute(
                f"SELECT d.id,d.{number},d.supplier_id,p.nombre,"
                f" (SELECT COUNT(*) FROM {table[:-1]}_lines l WHERE l.{table[:-1]}_id=d.id)"
                f" FROM {table} d JOIN proveedores p ON p.id=d.supplier_id"
                f" WHERE d.branch_id=? AND d.status IN ({placeholders})"
                f" AND (d.{number} LIKE ? OR p.nombre LIKE ?) ORDER BY d.created_at DESC LIMIT 50",
                (identity.branch_id, *statuses, like, like)))
        return {"items": [{"type": row[0], "id": row[1], "documentNumber": row[2],
                            "supplierId": row[3], "supplierName": row[4],
                            "lineCount": row[5],
                            "typeLabel": "Orden de compra" if row[0] == "PURCHASE_ORDER"
                            else "Compra directa"} for row in rows]}

    def list_products(self, identity: MobileIdentity, document_id: str, query: str) -> dict:
        like = f"%{query.strip()}%"
        rows = self._connection.execute(
            "SELECT l.id,l.product_id,p.codigo,p.nombre FROM purchase_order_lines l"
            " JOIN products p ON p.id=l.product_id WHERE l.purchase_order_id=?"
            " AND (p.codigo LIKE ? OR p.nombre LIKE ?) UNION ALL"
            " SELECT l.id,l.product_id,p.codigo,p.nombre FROM direct_purchase_lines l"
            " JOIN products p ON p.id=l.product_id WHERE l.direct_purchase_id=?"
            " AND (p.codigo LIKE ? OR p.nombre LIKE ?) LIMIT 50",
            (document_id, like, like, document_id, like, like)).fetchall()
        return {"items": [{"sourceLineId": row[0], "id": row[1], "code": row[2],
                            "name": row[3]} for row in rows]}

    def resolve_container(self, identity: MobileIdentity, token: str) -> dict:
        self._require(identity, "logistics.container.scan")
        container_id, _ = self._qr.resolve(token)
        container = self._repo.get_container(container_id)
        if container is None or not self._qr.validate(token, container):
            raise ValueError("QR revocado o contenedor inexistente")
        ctype = self._repo.get_type(container.container_type_id)
        return {"containerId": container.id, "containerCode": container.container_code,
                "typeName": ctype.name, "status": container.status.value,
                "qrVersion": container.qr_version}

    def get_shipment(self, identity: MobileIdentity, shipment_id: str) -> dict:
        shipment = self._shipment(identity, shipment_id)
        return self._shipment_result(shipment)

    def create_shipment(self, identity: MobileIdentity, operation_id: str,
                        expected_version: int, command: dict) -> dict:
        self._require(identity, "logistics.shipment.create")
        if expected_version != 0:
            raise ValueError("La versión inicial debe ser cero")
        shipment = LogisticsShipment.create(
            shipment_id=command["shipmentId"], shipment_number=f"SHIP-{command['shipmentId']}",
            origin_type="SUPPLIER", origin_location="Proveedor",
            origin_supplier_id=command.get("supplierId"),
            destination_branch_id=identity.branch_id,
            destination_warehouse_id=identity.warehouse_id,
            buyer_user_id=identity.user_id, operation_id=operation_id)
        shipment.add_source(SourceDocumentType(command["documentType"]), command["documentId"])
        return self._shipment_result(
            self._logistics.create_shipment(actor_user_id=identity.user_id, shipment=shipment))

    def attach_node(self, identity: MobileIdentity, shipment_id: str, operation_id: str,
                    expected_version: int, command: dict) -> dict:
        self._check_version(identity, shipment_id, expected_version)
        self._logistics.attach_container(
            actor_user_id=identity.user_id, shipment_id=shipment_id,
            container_id=self._qr.resolve(command["containerToken"])[0],
            operation_id=operation_id, parent_node_id=command.get("parentNodeId"),
            node_id=command["nodeId"])
        return self._shipment_result(self._shipment(identity, shipment_id))

    def assign_content(self, identity: MobileIdentity, shipment_id: str, operation_id: str,
                       expected_version: int, command: dict) -> dict:
        self._check_version(identity, shipment_id, expected_version)
        source = self._shipment(identity, shipment_id).sources[0]
        assignment = ShipmentContentAssignment.create(
            shipment_node_id=command["nodeId"],
            source_document_type=source.source_document_type,
            source_document_id=source.source_document_id,
            source_line_id=command["sourceLineId"], product_id=command["productId"],
            declared_quantity=command["quantity"], declared_net_weight=command["netWeight"],
            purchase_unit="PZA", inventory_unit="PZA", conversion_factor="1",
            unit_cost=command["unitCost"], currency_code="MXN", operation_id=operation_id,
            lot_number=command.get("lotNumber"),
            expiration_date=date.fromisoformat(command["expirationDate"])
            if command.get("expirationDate") else None,
            temperature=command.get("temperature"))
        self._logistics.assign_content(actor_user_id=identity.user_id,
                                       shipment_id=shipment_id, assignment=assignment)
        return self._shipment_result(self._shipment(identity, shipment_id))

    def attach_photo(self, identity: MobileIdentity, shipment_id: str, operation_id: str,
                     expected_version: int, command: dict) -> dict:
        self._check_version(identity, shipment_id, expected_version)
        if command["contentType"] not in ("image/jpeg", "image/png", "image/webp"):
            raise ValueError("Tipo de fotografía no permitido")
        content = base64.b64decode(command["contentBase64"], validate=True)
        if len(content) > 8 * 1024 * 1024:
            raise ValueError("La fotografía excede 8 MB")
        photo_id = self._photos.save(
            content=content, file_name=command["fileName"],
            content_type=command["contentType"], actor_user_id=identity.user_id,
            operation_id=operation_id)
        return {"photoId": photo_id, "version": expected_version}

    def seal_node(self, identity: MobileIdentity, shipment_id: str, node_id: str,
                  operation_id: str, expected_version: int, command: dict) -> dict:
        self._check_version(identity, shipment_id, expected_version)
        self._logistics.seal(
            actor_user_id=identity.user_id, shipment_id=shipment_id, node_id=node_id,
            seal_code=command["sealCode"], seal_type=command["sealType"],
            operation_id=operation_id)
        return self._shipment_result(self._shipment(identity, shipment_id))

    def dispatch(self, identity: MobileIdentity, shipment_id: str, operation_id: str,
                 expected_version: int) -> dict:
        self._check_version(identity, shipment_id, expected_version)
        result = self._logistics.dispatch(
            actor_user_id=identity.user_id, shipment_id=shipment_id,
            operation_id=operation_id)
        return self._shipment_result(result)

    def _check_version(self, identity, shipment_id, expected):
        shipment = self._shipment(identity, shipment_id)
        if shipment.version != expected:
            from fastapi import HTTPException
            raise HTTPException(412, {"message": "Conflicto de versión",
                                      "serverVersion": shipment.version})

    def _shipment(self, identity, shipment_id):
        shipment = self._repo.get_shipment(shipment_id)
        if shipment is None or shipment.destination_branch_id != identity.branch_id or \
                shipment.destination_warehouse_id != identity.warehouse_id:
            raise LookupError("Embarque inexistente en la sesión activa")
        return shipment

    @staticmethod
    def _shipment_result(shipment):
        return {"shipmentId": shipment.id, "status": shipment.status.value,
                "version": shipment.version,
                "nodes": [{"id": node.id, "containerId": node.container_id,
                           "parentNodeId": node.parent_node_id, "status": node.status.value}
                          for node in shipment.nodes]}

    @staticmethod
    def _require(identity, permission):
        if permission not in identity.permissions:
            from fastapi import HTTPException
            raise HTTPException(403, f"Permiso requerido: {permission}")
