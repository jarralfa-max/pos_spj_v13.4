"""Read-only Logistics queries consumed by desktop Procurement references."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

class LogisticsShipmentQueryService:
    def __init__(self, connection, shipment_repository=None) -> None:
        self._connection = connection
        self._shipments = shipment_repository

    def related_to_destination(self, *, branch_id: str, warehouse_id: str,
                               limit: int = 100) -> list[dict]:
        try:
            cursor = self._connection.execute(
                "SELECT id,shipment_number,origin_type,status,started_at,dispatched_at"
                " FROM logistics_shipments WHERE destination_branch_id=?"
                " AND destination_warehouse_id=? ORDER BY started_at DESC LIMIT ?",
                (branch_id, warehouse_id, limit))
        except sqlite3.OperationalError:
            return []
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def loadable_documents(self, *, branch_id: str, warehouse_id: str,
                           search: str = "", limit: int = 100) -> list[dict]:
        """Commercial documents eligible for supplier-origin loading."""
        like = f"%{search.strip()}%"
        definitions = (
            ("purchase_orders", "purchase_order_lines", "purchase_order_id",
             "PURCHASE_ORDER", ("APPROVED", "SENT", "ACKNOWLEDGED", "PARTIALLY_LOADED")),
            ("direct_purchases", "direct_purchase_lines", "direct_purchase_id",
             "DIRECT_PURCHASE", ("DRAFT", "CONFIRMED")),
            ("purchase_requisitions", "purchase_requisition_lines", "requisition_id",
             "PURCHASE_REQUISITION", ("APPROVED", "PARTIALLY_SOURCED")),
        )
        result = []
        for table, lines, foreign_key, document_type, statuses in definitions:
            placeholders = ",".join("?" for _ in statuses)
            supplier_join = " JOIN proveedores p ON p.id=d.supplier_id" if table != "purchase_requisitions" else ""
            supplier_id = "d.supplier_id" if table != "purchase_requisitions" else "NULL"
            supplier_name = "p.nombre" if table != "purchase_requisitions" else "'Por confirmar'"
            try:
                cursor = self._connection.execute(
                    f"SELECT d.id,d.document_number,{supplier_id},{supplier_name},d.status,"
                    f" (SELECT COUNT(*) FROM {lines} l WHERE l.{foreign_key}=d.id),"
                    " (SELECT s.id FROM logistics_shipment_sources x"
                    " JOIN logistics_shipments s ON s.id=x.shipment_id"
                    " WHERE x.source_document_type=? AND x.source_document_id=d.id"
                    " AND s.status NOT IN ('CANCELLED','CLOSED') LIMIT 1)"
                    f" FROM {table} d{supplier_join} WHERE d.branch_id=?"
                    f" AND d.status IN ({placeholders}) AND (d.document_number LIKE ?"
                    f" OR {supplier_name} LIKE ?) ORDER BY d.created_at DESC LIMIT ?",
                    (document_type, branch_id, *statuses, like, like, limit))
            except sqlite3.OperationalError:
                continue
            result.extend({
                "document_type": document_type, "id": row[0], "document_number": row[1],
                "supplier_id": row[2], "supplier_name": row[3], "status": row[4],
                "line_count": row[5], "shipment_id": row[6],
                "destination_warehouse_id": warehouse_id,
            } for row in cursor.fetchall())
        return result[:limit]

    def workspace(self, shipment_id: str) -> dict | None:
        if self._shipments is None:
            raise RuntimeError("ShipmentRepository no configurado")
        shipment = self._shipments.get_shipment(shipment_id)
        if shipment is None:
            return None
        containers = {node.container_id: self._shipments.get_container(node.container_id)
                      for node in shipment.nodes}
        types = {container.container_type_id: self._shipments.get_type(container.container_type_id)
                 for container in containers.values() if container is not None}
        nodes = [{
            "id": node.id, "parent_id": node.parent_node_id, "depth": node.depth,
            "container_id": node.container_id,
            "container_code": containers[node.container_id].container_code,
            "type_name": types[containers[node.container_id].container_type_id].name,
            "status": node.status.value,
            "net_weight": str(shipment.aggregate_net_weight(node.id)),
        } for node in shipment.nodes]
        contents = [{
            "id": item.id, "node_id": item.shipment_node_id, "product_id": item.product_id,
            "source_line_id": item.source_line_id,
            "quantity": str(item.declared_quantity), "net_weight": str(item.declared_net_weight),
            "unit_cost": str(item.unit_cost), "lot_number": item.lot_number or "—",
        } for item in shipment.contents]
        differences = self._differences(shipment)
        roots = [node for node in nodes if node["parent_id"] is None]
        return {
            "id": shipment.id, "shipment_number": shipment.shipment_number,
            "status": shipment.status.value, "version": shipment.version,
            "supplier_id": shipment.origin_supplier_id,
            "destination_branch_id": shipment.destination_branch_id,
            "destination_warehouse_id": shipment.destination_warehouse_id,
            "nodes": nodes, "contents": contents, "differences": differences,
            "pending_authorizations": [item for item in differences if item["blocking"]],
            "root_count": len(roots), "container_count": len(nodes),
            "total_quantity": str(sum((Decimal(c["quantity"]) for c in contents), Decimal("0"))),
            "net_weight": str(sum((Decimal(c["net_weight"]) for c in contents), Decimal("0"))),
            "can_seal": bool(nodes) and not any(item["blocking"] for item in differences),
            "can_dispatch": bool(roots) and all(node["status"] == "SEALED" for node in roots),
            "dispatched_at": shipment.dispatched_at,
        }

    def _differences(self, shipment) -> list[dict]:
        result = []
        for source in shipment.sources:
            if source.source_document_type.value == "PURCHASE_REQUISITION":
                continue
            is_order = source.source_document_type.value == "PURCHASE_ORDER"
            table = "purchase_order_lines" if is_order else "direct_purchase_lines"
            foreign_key = "purchase_order_id" if is_order else "direct_purchase_id"
            quantity_column = "ordered_quantity" if is_order else "quantity"
            cost_column = "unit_price" if is_order else "unit_cost"
            try:
                expected = self._connection.execute(
                    f"SELECT id,product_id,{quantity_column},{cost_column} FROM {table} WHERE {foreign_key}=?",
                    (source.source_document_id,)).fetchall()
            except sqlite3.OperationalError:
                continue
            for line_id, product_id, quantity, cost in expected:
                assigned = [item for item in shipment.contents if item.source_line_id == line_id]
                loaded = sum((item.declared_quantity for item in assigned), Decimal("0"))
                expected_qty = Decimal(str(quantity))
                cost_variance = any(item.unit_cost != Decimal(str(cost)) for item in assigned)
                if loaded != expected_qty or cost_variance:
                    result.append({
                        "source_line_id": line_id, "product_id": product_id,
                        "expected": str(expected_qty), "loaded": str(loaded),
                        "variance": str(loaded - expected_qty),
                        "cost_variance": cost_variance,
                        "blocking": loaded > expected_qty or cost_variance,
                        "reason": "Exceso o costo distinto requiere autorización" if loaded > expected_qty or cost_variance else "Saldo pendiente de carga",
                    })
        try:
            authorized = {row[0] for row in self._connection.execute(
                "SELECT source_line_id FROM logistics_loading_authorizations WHERE shipment_id=?",
                (shipment.id,))}
        except sqlite3.OperationalError:
            authorized = set()
        for item in result:
            item["authorized"] = item["source_line_id"] in authorized
            if item["authorized"]:
                item["blocking"] = False
                item["reason"] = "Variación autorizada"
        return result
