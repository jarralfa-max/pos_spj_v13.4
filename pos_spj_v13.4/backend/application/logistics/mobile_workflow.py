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
        rows.extend(("PURCHASE_REQUISITION", *row) for row in self._connection.execute(
            "SELECT d.id,d.document_number,NULL,'Proveedor por confirmar',"
            " (SELECT COUNT(*) FROM purchase_requisition_lines l WHERE l.requisition_id=d.id)"
            " FROM purchase_requisitions d WHERE d.branch_id=?"
            " AND d.status IN ('APPROVED','PARTIALLY_SOURCED')"
            " AND d.document_number LIKE ? ORDER BY d.created_at DESC LIMIT 50",
            (identity.branch_id, like)))
        return {"items": [{"type": row[0], "id": row[1], "documentNumber": row[2],
                            "supplierId": row[3], "supplierName": row[4],
                            "lineCount": row[5],
                            "typeLabel": "Orden de compra" if row[0] == "PURCHASE_ORDER"
                            else "Solicitud aprobada" if row[0] == "PURCHASE_REQUISITION"
                            else "Compra directa"} for row in rows]}


    def list_products(self, identity: MobileIdentity, document_id: str, query: str) -> dict:
        like = f"%{query.strip()}%"
        rows = self._connection.execute(
            "SELECT l.id,l.product_id,p.code,p.name,p.base_unit_id,p.catch_weight_enabled,"
            " p.lot_controlled,p.expiration_controlled FROM purchase_order_lines l"
            " JOIN products p ON p.id=l.product_id WHERE l.purchase_order_id=?"
            " AND (p.code LIKE ? OR p.name LIKE ?) UNION ALL"
            " SELECT l.id,l.product_id,p.code,p.name,p.base_unit_id,p.catch_weight_enabled,"
            " p.lot_controlled,p.expiration_controlled FROM direct_purchase_lines l"
            " JOIN products p ON p.id=l.product_id WHERE l.direct_purchase_id=?"
            " AND (p.code LIKE ? OR p.name LIKE ?) UNION ALL"
            " SELECT l.id,l.product_id,p.code,p.name,p.base_unit_id,p.catch_weight_enabled,"
            " p.lot_controlled,p.expiration_controlled FROM purchase_requisition_lines l"
            " JOIN products p ON p.id=l.product_id WHERE l.requisition_id=?"
            " AND (p.code LIKE ? OR p.name LIKE ?) LIMIT 50",
            (document_id, like, like, document_id, like, like,
             document_id, like, like)).fetchall()
        return {"items": [{"sourceLineId": row[0], "id": row[1], "code": row[2],
                            "name": row[3], "unitId": row[4],
                            "catchWeightEnabled": bool(row[5]),
                            "lotControlled": bool(row[6]),
                            "expirationControlled": bool(row[7])} for row in rows]}

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
        if command["documentType"] == "PURCHASE_REQUISITION" and not command.get("supplierId"):
            raise ValueError("La solicitud requiere una compra directa con proveedor confirmado")
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
        profile = self._product_for_source(source, command["sourceLineId"], command["productId"])
        if profile["lot_controlled"] and not command.get("lotNumber"):
            raise ValueError("El producto requiere lote")
        if profile["expiration_controlled"] and not command.get("expirationDate"):
            raise ValueError("El producto requiere caducidad")
        if profile["catch_weight_enabled"] and Decimal(command["netWeight"]) <= 0:
            raise ValueError("El producto de peso variable requiere peso neto")
        assignment = ShipmentContentAssignment.create(
            shipment_node_id=command["nodeId"],
            source_document_type=source.source_document_type,
            source_document_id=source.source_document_id,
            source_line_id=command["sourceLineId"], product_id=command["productId"],
            declared_quantity=command["quantity"], declared_net_weight=command["netWeight"],
            purchase_unit=profile["base_unit_id"], inventory_unit=profile["base_unit_id"],
            conversion_factor="1",
            unit_cost=command["unitCost"], currency_code="MXN", operation_id=operation_id,
            lot_number=command.get("lotNumber"),
            expiration_date=date.fromisoformat(command["expirationDate"])
            if command.get("expirationDate") else None,
            temperature=command.get("temperature"), assignment_id=command["id"])
        self._logistics.assign_content(actor_user_id=identity.user_id,
                                       shipment_id=shipment_id, assignment=assignment)
        return self._shipment_result(self._shipment(identity, shipment_id))

    def _product_for_source(self, source, source_line_id, product_id):
        table, foreign_key = {
            "PURCHASE_ORDER": ("purchase_order_lines", "purchase_order_id"),
            "DIRECT_PURCHASE": ("direct_purchase_lines", "direct_purchase_id"),
            "PURCHASE_REQUISITION": ("purchase_requisition_lines", "requisition_id"),
        }[source.source_document_type.value]
        row = self._connection.execute(
            f"SELECT p.base_unit_id,p.catch_weight_enabled,p.lot_controlled,p.expiration_controlled"
            f" FROM {table} l JOIN products p ON p.id=l.product_id"
            f" WHERE l.id=? AND l.{foreign_key}=? AND l.product_id=?",
            (source_line_id, source.source_document_id, product_id)).fetchone()
        if row is None:
            raise ValueError("El producto no pertenece al documento comercial")
        return {"base_unit_id": row[0], "catch_weight_enabled": bool(row[1]),
                "lot_controlled": bool(row[2]), "expiration_controlled": bool(row[3])}

    def attach_photo(self, identity: MobileIdentity, shipment_id: str, operation_id: str,
                     expected_version: int, command: dict) -> dict:
        self._check_version(identity, shipment_id, expected_version)
        existing = self._connection.execute(
            "SELECT id FROM logistics_shipment_photos WHERE operation_id=?",
            (operation_id,)).fetchone()
        if existing:
            return {"photoId": existing[0], "version": expected_version}
        shipment = self._shipment(identity, shipment_id)
        if not any(item.id == command["assignmentId"] for item in shipment.contents):
            raise ValueError("La fotografía no pertenece a una asignación del embarque")
        if command["contentType"] not in ("image/jpeg", "image/png", "image/webp"):
            raise ValueError("Tipo de fotografía no permitido")
        content = base64.b64decode(command["contentBase64"], validate=True)
        if len(content) > 8 * 1024 * 1024:
            raise ValueError("La fotografía excede 8 MB")
        photo_id = self._photos.save(
            content=content, file_name=command["fileName"],
            content_type=command["contentType"], actor_user_id=identity.user_id,
            operation_id=operation_id)
        with self._connection:
            self._connection.execute(
                "INSERT INTO logistics_shipment_photos"
                " (id,shipment_id,assignment_id,file_name,content_type,actor_user_id,operation_id,created_at)"
                " VALUES (?,?,?,?,?,?,?,datetime('now'))",
                (photo_id, shipment_id, command["assignmentId"], command["fileName"],
                 command["contentType"], identity.user_id, operation_id))
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

    def _shipment_result(self, shipment):
        containers = {node.container_id: self._repo.get_container(node.container_id)
                      for node in shipment.nodes}
        return {"shipmentId": shipment.id, "status": shipment.status.value,
                "version": shipment.version,
                "sources": [{"type": item.source_document_type.value,
                             "id": item.source_document_id} for item in shipment.sources],
                "nodes": [{"id": node.id, "containerId": node.container_id,
                           "containerCode": containers[node.container_id].container_code,
                           "typeName": self._repo.get_type(
                               containers[node.container_id].container_type_id).name,
                           "parentNodeId": node.parent_node_id, "status": node.status.value}
                          for node in shipment.nodes]}

    @staticmethod
    def _require(identity, permission):
        if permission not in identity.permissions:
            from fastapi import HTTPException
            raise HTTPException(403, f"Permiso requerido: {permission}")
