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
            # Sólo la compra rápida CONFIRMADA con «Recolección en proveedor»
            # (§11): una de recepción inmediata ya entró al almacén y un
            # borrador todavía no es un compromiso con el proveedor.
            ("direct_purchases", "direct_purchase_lines", "direct_purchase_id",
             "DIRECT_PURCHASE", ("CONFIRMED",)),
            ("purchase_requisitions", "purchase_requisition_lines", "requisition_id",
             "PURCHASE_REQUISITION", ("APPROVED", "PARTIALLY_SOURCED")),
        )
        result = []
        for table, lines, foreign_key, document_type, statuses in definitions:
            placeholders = ",".join("?" for _ in statuses)
            supplier_join = " JOIN (SELECT id, legal_name FROM supplier_master) p ON p.id=d.supplier_id" if table != "purchase_requisitions" else ""
            supplier_id = "d.supplier_id" if table != "purchase_requisitions" else "NULL"
            # El almacén destino es el DEL DOCUMENTO; la sesión real no trae almacén.
            warehouse = "d.warehouse_id" if table != "purchase_requisitions" else "NULL"
            supplier_name = "p.legal_name" if table != "purchase_requisitions" else "'Por confirmar'"
            try:
                cursor = self._connection.execute(
                    f"SELECT d.id,d.document_number,{supplier_id},{supplier_name},d.status,"
                    f" (SELECT COUNT(*) FROM {lines} l WHERE l.{foreign_key}=d.id),"
                    " (SELECT s.id FROM logistics_shipment_sources x"
                    " JOIN logistics_shipments s ON s.id=x.shipment_id"
                    " WHERE x.source_document_type=? AND x.source_document_id=d.id"
                    " AND s.status NOT IN ('CANCELLED','CLOSED') LIMIT 1),"
                    f" {warehouse}"
                    f" FROM {table} d{supplier_join} WHERE d.branch_id=?"
                    + (" AND d.fulfillment_mode='SUPPLIER_PICKUP'"
                       if table == "direct_purchases" else "") +
                    f" AND d.status IN ({placeholders}) AND (d.document_number LIKE ?"
                    f" OR {supplier_name} LIKE ?) ORDER BY d.created_at DESC LIMIT ?",
                    (document_type, branch_id, *statuses, like, like, limit))
            except sqlite3.OperationalError:
                continue
            result.extend({
                "document_type": document_type, "id": row[0], "document_number": row[1],
                "supplier_id": row[2], "supplier_name": row[3], "status": row[4],
                "line_count": row[5], "shipment_id": row[6],
                "destination_warehouse_id": row[7] or warehouse_id,
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
        # Nombres, nunca ids, para la pantalla.
        from backend.application.procurement.queries.product_names import (
            product_labels,
        )
        names = product_labels(self._connection,
                              [c["product_id"] for c in contents]
                              + [d["product_id"] for d in differences])
        for item in contents + differences:
            item["product_name"] = names.get(str(item["product_id"]), "Producto")
        roots = [node for node in nodes if node["parent_id"] is None]
        return {
            "id": shipment.id, "shipment_number": shipment.shipment_number,
            "status": shipment.status.value, "version": shipment.version,
            "origin_location": shipment.origin_location,
            "origin_supplier_address_id": shipment.origin_supplier_address_id,
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
            "arrived_at": shipment.arrived_at, "closed_at": shipment.closed_at,
            # §28: qué sigue después del despacho.
            "can_load": shipment.status.value in ("DRAFT", "LOADING"),
            "can_mark_transit": shipment.status.value == "DISPATCHED",
            "can_arrive": shipment.status.value in ("DISPATCHED", "IN_TRANSIT"),
            "can_count": shipment.status.value in ("ARRIVED", "RECEIVING"),
            "can_receive": shipment.status.value == "RECEIVING",
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


#: Estado del contenedor → por qué no se puede cargar (vacío = se puede).
_NOT_LOADABLE = {
    "ASSIGNED": "Asignado a un embarque", "LOADING": "En carga en un embarque",
    "SEALED": "Sellado en un embarque", "IN_TRANSIT": "En tránsito",
    "AT_DESTINATION": "En destino, falta cerrar el embarque",
    "IN_INSPECTION": "En inspección", "DAMAGED": "Dañado", "LOST": "Perdido",
    "QUARANTINED": "En cuarentena", "CLEANING": "En limpieza",
    "MAINTENANCE": "En mantenimiento", "RELEASED": "Devuelto / liberado",
    "RETIRED": "Dado de baja",
}
CONTAINER_STATUS_LABELS = {"AVAILABLE": "Disponible", **_NOT_LOADABLE}


class LogisticsContainerQueryService:
    """Catálogo de contenedores (Logística → Contenedores): lista con el motivo
    por el que uno no puede cargarse y su historial (custodia + auditoría)."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def containers(self, *, search: str = "", status: str | None = None,
                   limit: int = 500) -> list[dict]:
        like = f"%{search.strip().upper()}%"
        sql = (
            "SELECT c.id, c.container_code, t.name, c.status, c.owner_type, c.tare_weight,"
            " c.capacity_weight, c.serial_number, c.current_location_id, c.condition,"
            " (SELECT s.shipment_number FROM logistics_shipment_nodes n"
            "  JOIN logistics_shipments s ON s.id=n.shipment_id WHERE n.container_id=c.id"
            "  AND n.detached_at IS NULL AND s.status NOT IN ('CANCELLED','CLOSED','RECEIVED')"
            "  LIMIT 1)"
            " FROM logistics_physical_containers c"
            " LEFT JOIN logistics_container_types t ON t.id=c.container_type_id"
            " WHERE (UPPER(c.container_code) LIKE ? OR UPPER(COALESCE(t.name,'')) LIKE ?)")
        params: list = [like, like]
        if status:
            sql += " AND c.status=?"
            params.append(status)
        sql += " ORDER BY c.container_code LIMIT ?"
        params.append(limit)
        try:
            filas = self._connection.execute(sql, tuple(params)).fetchall()
        except sqlite3.OperationalError:
            return []
        resultado = []
        for (cid, code, type_name, estado, owner, tare, capacity, serial, location,
             condition, shipment_number) in filas:
            motivo = ""
            if shipment_number:
                motivo = f"En el embarque {shipment_number}"
            elif estado != "AVAILABLE":
                motivo = _NOT_LOADABLE.get(estado, estado)
            resultado.append({
                "id": cid, "code": code, "type_name": type_name or "", "status": estado,
                "status_label": CONTAINER_STATUS_LABELS.get(estado, estado),
                "owner_type": owner, "tare_weight": tare, "capacity_weight": capacity,
                "serial_number": serial or "", "location_id": location or "",
                "condition": condition, "shipment_number": shipment_number or "",
                "loadable": not motivo, "not_loadable_reason": motivo})
        return resultado

    def label_rows(self, container_ids) -> list[dict]:
        """Lo legible de la etiqueta, en el orden pedido."""
        ids = [str(i) for i in container_ids if i]
        if not ids:
            return []
        marcas = ",".join("?" * len(ids))
        filas = self._connection.execute(
            "SELECT c.id, c.container_code, t.name, t.category, c.tare_weight,"
            " c.capacity_weight, c.qr_version FROM logistics_physical_containers c"
            " LEFT JOIN logistics_container_types t ON t.id=c.container_type_id"
            f" WHERE c.id IN ({marcas})", tuple(ids)).fetchall()
        por_id = {str(f[0]): {"id": str(f[0]), "code": f[1], "type_name": f[2] or "",
                              "category": f[3] or "", "tare_weight": str(f[4] or "0"),
                              "capacity_weight": str(f[5]) if f[5] else None,
                              "qr_version": int(f[6] or 1)} for f in filas}
        return [por_id[i] for i in ids if i in por_id]

    def printed_codes(self, container_ids) -> list[str]:
        """Contenedores cuya etiqueta YA se imprimió (otra impresión es
        reimpresión y exige motivo)."""
        ids = [str(i) for i in container_ids if i]
        if not ids:
            return []
        marcas = ",".join("?" * len(ids))
        try:
            filas = self._connection.execute(
                "SELECT DISTINCT c.container_code FROM logistics_print_jobs j"
                " JOIN logistics_container_labels l ON l.id=j.label_id"
                " JOIN logistics_physical_containers c ON c.id=l.container_id"
                f" WHERE j.status='COMPLETED' AND c.id IN ({marcas})"
                " ORDER BY c.container_code", tuple(ids)).fetchall()
        except sqlite3.OperationalError:
            return []
        return [str(f[0]) for f in filas]

    def owner_name(self) -> str:
        try:
            fila = self._connection.execute(
                "SELECT commercial_name, legal_name FROM company_profiles WHERE active=1"
                " LIMIT 1").fetchone()
        except sqlite3.OperationalError:
            return ""
        return str((fila[0] or fila[1] or "") if fila else "").strip()

    def history(self, container_id: str, *, limit: int = 200) -> list[dict]:
        eventos = []
        for consulta, origen in (
                ("SELECT occurred_at, action, reason, actor_user_id FROM logistics_custody_events"
                 " WHERE container_id=?", "Custodia"),
                ("SELECT occurred_at, action, reason, actor_user_id FROM logistics_audit_log"
                 " WHERE entity_id=?", "Cambio")):
            try:
                eventos += [{"at": r[0], "action": r[1], "reason": r[2] or "", "actor": r[3],
                             "source": origen}
                            for r in self._connection.execute(consulta, (container_id,))]
            except sqlite3.OperationalError:
                continue
        nombres = self._user_names({e["actor"] for e in eventos})
        for e in eventos:
            e["actor_name"] = nombres.get(e["actor"], "")
        return sorted(eventos, key=lambda e: e["at"] or "", reverse=True)[:limit]

    def _user_names(self, ids) -> dict:
        ids = sorted(i for i in ids if i)
        if not ids:
            return {}
        try:
            filas = self._connection.execute(
                "SELECT id, COALESCE(NULLIF(trim(nombre),''), usuario) FROM usuarios"
                f" WHERE id IN ({','.join('?' for _ in ids)})", tuple(ids)).fetchall()
        except sqlite3.OperationalError:
            return {}
        return {str(r[0]): str(r[1] or "") for r in filas}

    def shipments(self, *, search: str = "", limit: int = 200) -> list[dict]:
        like = f"%{search.strip()}%"
        try:
            filas = self._connection.execute(
                "SELECT s.id, s.shipment_number, s.status, s.origin_location,"
                " s.dispatched_at, s.arrived_at, s.closed_at,"
                " (SELECT COUNT(*) FROM logistics_shipment_nodes n WHERE n.shipment_id=s.id"
                "  AND n.detached_at IS NULL)"
                " FROM logistics_shipments s WHERE s.shipment_number LIKE ?"
                " OR s.origin_location LIKE ? ORDER BY COALESCE(s.dispatched_at, '') DESC,"
                " s.rowid DESC LIMIT ?", (like, like, limit)).fetchall()
        except sqlite3.OperationalError:
            return []
        return [{"id": r[0], "number": r[1], "status": r[2], "origin": r[3] or "",
                 "dispatched_at": (r[4] or "")[:16].replace("T", " "),
                 "arrived_at": (r[5] or "")[:16].replace("T", " "),
                 "closed_at": (r[6] or "")[:16].replace("T", " "), "containers": r[7]}
                for r in filas]

