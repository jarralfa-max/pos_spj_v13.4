"""Desktop coordinator for an origin-purchase workspace.

Procurement supplies commercial context; all shipment mutations remain owned by
the canonical Logistics application service.

FASE 8-10 (2026-09-29):
* El ORIGEN es una bodega/punto de recolección del proveedor (Supplier Master,
  id + foto del domicilio), nunca su nombre.
* Desde escritorio se opera todo lo que antes sólo prometía la "sesión móvil":
  registrar/buscar/escanear contenedores, armar padre/hijo, cargar líneas de
  compra con cantidad, peso, lote, caducidad y temperatura (lo que exija el
  perfil del producto), sellar y despachar. Las unidades salen de la LÍNEA de la
  compra (y ésta de Productos), no del catálogo "a ojo".
* Llegada: tránsito → llegada → conteo/pesaje por contenido → recepción de la
  compra (GoodsReceipt) → inventario, y el embarque se cierra.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation

from backend.domain.logistics.entities import (
    ContainerType, LogisticsShipment, PhysicalContainer, ShipmentContentAssignment,
)
from backend.domain.logistics.enums import ContainerCategory, ContainerOwnerType, SourceDocumentType
from backend.shared.ids import new_uuid

CONTAINER_CATEGORY_ES = {
    "MASTER_CONTAINER": "Contenedor maestro", "TRAILER_CONTAINER": "Caja de tráiler",
    "PALLET": "Tarima", "CAGE": "Jaula", "CRATE": "Huacal", "PLASTIC_BOX": "Caja de plástico",
    "CARDBOARD_BOX": "Caja de cartón", "TOTE": "Contenedor apilable", "COOLER": "Hielera",
    "TRAY": "Charola", "BAG": "Bolsa", "BIN": "Contenedor a granel",
}


def _dec(value, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else default))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Número inválido: {value!r}") from exc


class OriginPurchaseWorkspaceService:
    def __init__(self, logistics_service, queries, *, mobile_base_url="/mobile/logistics/",
                 connection=None, supplier_origins=None, product_catalog=None,
                 receive_order=None, receive_direct=None) -> None:
        self._logistics = logistics_service
        self._queries = queries
        self._mobile_base_url = mobile_base_url
        self._conn = connection if connection is not None else getattr(queries, "_connection", None)
        if supplier_origins is None and self._conn is not None:
            from backend.application.suppliers.queries.supplier_origin_query_service import (
                SupplierOriginQueryService,
            )
            supplier_origins = SupplierOriginQueryService(self._conn)
        if product_catalog is None and self._conn is not None:
            from backend.application.procurement.adapters.product_catalog_adapter import (
                ProcurementProductCatalogAdapter,
            )
            product_catalog = ProcurementProductCatalogAdapter(self._conn)
        self._origins = supplier_origins
        self._catalog = product_catalog
        # Recepción de la OC al llegar (FASE 10): callable(actor, order_id, lines,
        # shipment_id) -> (ok, mensaje, datos). Lo inyecta la composición de Compras.
        self._receive_order = receive_order
        #: Recepción de una compra rápida con recolección (mismo contrato).
        self._receive_direct = receive_direct

    # ── documentos y creación del embarque ────────────────────────────────────
    def documents(self, *, branch_id, warehouse_id, search=""):
        documents = self._queries.loadable_documents(
            branch_id=branch_id, warehouse_id=warehouse_id, search=search)
        for document in documents:
            origin = self._order_origin(document)
            document["origin_supplier_address_id"] = origin[0] if origin else None
            document["origin_display"] = origin[1] if origin else ""
        return documents

    def _order_origin(self, document) -> tuple[str, str] | None:
        """Bodega de origen que eligió el DOCUMENTO (orden o compra rápida)."""
        table = {"PURCHASE_ORDER": "purchase_orders",
                 "DIRECT_PURCHASE": "direct_purchases"}.get(document["document_type"])
        if self._conn is None or table is None:
            return None
        try:
            row = self._conn.execute(
                f"SELECT origin_supplier_address_id, origin_address_snapshot FROM {table}"
                " WHERE id=?", (document["id"],)).fetchone()
        except sqlite3.OperationalError:
            return None
        if not row or not row[0]:
            return None
        from backend.application.suppliers.queries.supplier_origin_query_service import (
            origin_display,
        )
        try:
            snapshot = json.loads(row[1]) if row[1] else {}
        except ValueError:
            snapshot = {}
        return row[0], origin_display(snapshot)

    def supplier_origin_options(self, supplier_id) -> list[tuple[str, str]]:
        if self._origins is None or not supplier_id:
            return []
        return [(o["id"], o["display"]) for o in self._origins.origin_locations(supplier_id)]

    def open(self, shipment_id):
        return self._queries.workspace(shipment_id)

    def create_shipment(self, *, actor_user_id, branch_id, warehouse_id, document,
                        origin_address_id=None):
        if document.get("shipment_id"):
            return self.open(document["shipment_id"])
        if document["document_type"] == "PURCHASE_REQUISITION" and not document.get("supplier_id"):
            raise ValueError("Confirma un proveedor mediante compra directa antes de crear el embarque")
        supplier_id = document.get("supplier_id")
        address_id = origin_address_id or document.get("origin_supplier_address_id")
        if not address_id:
            options = self.supplier_origin_options(supplier_id)
            if len(options) == 1:
                address_id = options[0][0]
            elif not options:
                raise ValueError("El proveedor no tiene bodegas ni puntos de recolección. "
                                 "Regístralos en Proveedores → Domicilios.")
            else:
                raise ValueError("Elige la bodega o punto de recolección de origen.")
        origin = self._origins.origin_location(supplier_id, address_id) if self._origins else None
        if origin is None:
            raise ValueError("La bodega o punto de recolección no pertenece al proveedor")
        shipment_id = new_uuid()
        shipment = LogisticsShipment.create(
            shipment_id=shipment_id, shipment_number=f"EMB-{shipment_id[-8:].upper()}",
            origin_type="SUPPLIER", origin_location=origin["display"],
            origin_supplier_id=supplier_id, destination_branch_id=branch_id,
            destination_warehouse_id=warehouse_id, buyer_user_id=actor_user_id,
            operation_id=new_uuid(), origin_supplier_address_id=origin["id"],
            origin_address_snapshot=json.dumps(origin["snapshot"], ensure_ascii=False))
        shipment.add_source(SourceDocumentType(document["document_type"]), document["id"])
        self._logistics.create_shipment(actor_user_id=actor_user_id, shipment=shipment)
        return self.open(shipment.id)

    def mobile_handoff(self, shipment_id):
        detail = self.open(shipment_id)
        if detail is None:
            raise LookupError("Embarque inexistente")
        return {"url": f"{self._mobile_base_url}?shipment={shipment_id}",
                "shipment_id": shipment_id, "requires_login": True}

    # ── contenedores (bounded context Logística; nada paralelo en Compras) ─────
    def container_types(self) -> list[tuple[str, str]]:
        rows = self._conn.execute(
            "SELECT id, name, category FROM logistics_container_types WHERE active=1"
            " ORDER BY name").fetchall()
        return [(r[0], f"{r[1]} ({CONTAINER_CATEGORY_ES.get(r[2], r[2])})") for r in rows]

    def register_container_type(self, *, actor_user_id, code, name, category,
                                allows_children=False, maximum_net_weight=None,
                                seal_required=False, tare_weight="0") -> str:
        item = ContainerType.create(
            code=code, name=name, category=ContainerCategory(category),
            allows_children=bool(allows_children),
            maximum_children=None, maximum_depth_below=2 if allows_children else 0,
            default_tare_weight=str(tare_weight or "0"),
            maximum_net_weight=str(maximum_net_weight) if maximum_net_weight else None,
            seal_required=bool(seal_required))
        return self._logistics.register_type(actor_user_id=actor_user_id, item=item)

    def register_container(self, *, actor_user_id, code, container_type_id,
                           tare_weight=None) -> dict:
        ctype = self._logistics.get_type(container_type_id)
        if ctype is None:
            raise ValueError("Elige el tipo de contenedor")
        if self._find_by_code(code) is not None:
            raise ValueError(f"Ya existe un contenedor con el código {code.strip().upper()}")
        container = PhysicalContainer.create(
            container_code=code, container_type_id=container_type_id,
            owner_type=ContainerOwnerType.COMPANY,
            tare_weight=str(tare_weight) if tare_weight not in (None, "") else
            str(ctype.default_tare_weight))
        return self._logistics.register_container(
            actor_user_id=actor_user_id, container=container, operation_id=new_uuid())

    def _find_by_code(self, code: str):
        row = self._conn.execute(
            "SELECT id FROM logistics_physical_containers WHERE container_code=?",
            ((code or "").strip().upper(),)).fetchone()
        return row[0] if row else None

    def find_container(self, reference: str) -> dict:
        """Por código impreso o por el QR escaneado (URL/token firmado)."""
        reference = (reference or "").strip()
        if not reference:
            raise ValueError("Captura o escanea el código del contenedor")
        container_id = self._find_by_code(reference)
        if container_id is None and "." in reference:
            try:
                container_id = self._logistics.resolve_qr(reference)
            except Exception as exc:
                raise ValueError("QR de contenedor inválido") from exc
        container = self._logistics.get_container(container_id) if container_id else None
        if container is None:
            raise ValueError(f"No existe el contenedor {reference}")
        ctype = self._logistics.get_type(container.container_type_id)
        return {"id": container.id, "code": container.container_code,
                "type_name": ctype.name if ctype else "—", "status": container.status.value}

    def attach_container(self, *, actor_user_id, shipment_id, reference,
                         parent_node_id=None):
        container = self.find_container(reference)
        self._logistics.attach_container(
            actor_user_id=actor_user_id, shipment_id=shipment_id,
            container_id=container["id"], operation_id=new_uuid(),
            parent_node_id=parent_node_id or None)
        return self.open(shipment_id)

    # ── carga de líneas de compra ─────────────────────────────────────────────
    def loading_lines(self, shipment_id) -> list[dict]:
        """Líneas de los documentos del embarque con lo esperado, lo cargado, lo
        pendiente y lo que su producto exige capturar."""
        shipment = self._logistics.get_shipment(shipment_id)
        if shipment is None:
            raise LookupError("Embarque inexistente")
        loaded: dict[str, Decimal] = {}
        for content in shipment.contents:
            loaded[content.source_line_id] = loaded.get(
                content.source_line_id, Decimal("0")) + content.declared_quantity
        from backend.application.procurement.queries.product_names import (
            product_labels,
        )
        result = []
        for source in shipment.sources:
            for line in self._source_lines(source):
                result.append(line)
        names = product_labels(self._conn, (ln["product_id"] for ln in result))
        for line in result:
            line["product_name"] = names.get(line["product_id"], "Producto")
            line["loaded"] = loaded.get(line["source_line_id"], Decimal("0"))
            line["pending"] = max(Decimal("0"), line["expected"] - line["loaded"])
            profile = self._catalog.purchase_profile(line["product_id"]) if self._catalog else None
            line["lot_required"] = bool(getattr(profile, "lot_controlled", False))
            line["expiration_required"] = bool(getattr(profile, "expiration_controlled", False))
            line["weight_required"] = bool(getattr(profile, "catch_weight", False)) or \
                getattr(profile, "base_unit_dimension", "") == "WEIGHT"
            line["temperature_required"] = bool(getattr(profile, "temperature_tracked", False))
        return result

    def _source_lines(self, source) -> list[dict]:
        kind = source.source_document_type.value
        if kind == "PURCHASE_ORDER":
            sql = ("SELECT id, product_id, ordered_quantity, unit_price, purchase_unit,"
                   " inventory_unit, conversion_factor, currency_code FROM purchase_order_lines"
                   " WHERE purchase_order_id=?")
        elif kind == "DIRECT_PURCHASE":
            sql = ("SELECT id, product_id, quantity, unit_cost, purchase_unit, inventory_unit,"
                   " conversion_factor, currency_code FROM direct_purchase_lines"
                   " WHERE direct_purchase_id=?")
        else:
            return []
        try:
            rows = self._conn.execute(sql, (source.source_document_id,)).fetchall()
        except sqlite3.OperationalError:
            return []
        return [{"source_line_id": r[0], "source_document_type": kind,
                 "source_document_id": source.source_document_id, "product_id": r[1],
                 "expected": _dec(r[2]), "unit_cost": _dec(r[3]),
                 "purchase_unit": r[4] or "", "inventory_unit": r[5] or "",
                 "conversion_factor": _dec(r[6], "1"), "currency_code": r[7] or "MXN"}
                for r in rows]

    def assign_line(self, *, actor_user_id, shipment_id, node_id, source_line_id,
                    quantity, net_weight="0", lot_number=None, expiration_date=None,
                    temperature=None):
        line = next((ln for ln in self.loading_lines(shipment_id)
                     if ln["source_line_id"] == source_line_id), None)
        if line is None:
            raise ValueError("La línea no pertenece a los documentos del embarque")
        quantity, weight = _dec(quantity), _dec(net_weight)
        if quantity <= 0:
            raise ValueError("La cantidad cargada debe ser mayor a cero")
        name = line["product_name"]
        if line["weight_required"] and weight <= 0:
            raise ValueError(f"{name} requiere el peso neto")
        if line["lot_required"] and not (lot_number or "").strip():
            raise ValueError(f"{name} requiere lote")
        if line["expiration_required"] and not expiration_date:
            raise ValueError(f"{name} requiere caducidad")
        if line["temperature_required"] and temperature in (None, ""):
            raise ValueError(f"{name} requiere temperatura")
        expiration = (expiration_date if isinstance(expiration_date, date) or not expiration_date
                      else date.fromisoformat(str(expiration_date)))
        assignment = ShipmentContentAssignment.create(
            shipment_node_id=node_id,
            source_document_type=SourceDocumentType(line["source_document_type"]),
            source_document_id=line["source_document_id"], source_line_id=source_line_id,
            product_id=line["product_id"], declared_quantity=str(quantity),
            declared_net_weight=str(weight), purchase_unit=line["purchase_unit"],
            inventory_unit=line["inventory_unit"],
            conversion_factor=str(line["conversion_factor"]),
            unit_cost=str(line["unit_cost"]), currency_code=line["currency_code"],
            operation_id=new_uuid(), lot_number=(lot_number or "").strip() or None,
            expiration_date=expiration,
            temperature=str(temperature) if temperature not in (None, "") else None)
        self._logistics.assign_content(actor_user_id=actor_user_id, shipment_id=shipment_id,
                                       assignment=assignment)
        return self.open(shipment_id)

    # ── sellado y despacho ─────────────────────────────────────────────────────
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

    # ── llegada → recepción → inventario (§28) ────────────────────────────────
    def mark_in_transit(self, *, actor_user_id, shipment_id):
        self._logistics.mark_in_transit(actor_user_id=actor_user_id, shipment_id=shipment_id,
                                        operation_id=new_uuid())
        return self.open(shipment_id)

    def register_arrival(self, *, actor_user_id, shipment_id):
        self._logistics.register_arrival(actor_user_id=actor_user_id, shipment_id=shipment_id,
                                         operation_id=new_uuid())
        return self.open(shipment_id)

    def arrival_lines(self, shipment_id) -> list[dict]:
        """Cada contenido cargado con lo declarado en origen, lo contado al llegar
        (si ya se contó) y lo que su producto exige capturar."""
        shipment = self._logistics.get_shipment(shipment_id)
        if shipment is None:
            raise LookupError("Embarque inexistente")
        counts = self._logistics.arrival_counts(shipment_id)
        requirements = {ln["source_line_id"]: ln for ln in self.loading_lines(shipment_id)}
        codes = {node.id: self._logistics.get_container(node.container_id).container_code
                 for node in shipment.nodes if not node.detached_at}
        result = []
        for content in shipment.contents:
            need = requirements.get(content.source_line_id, {})
            count = counts.get(content.id)
            result.append({
                "content_id": content.id, "container_code": codes.get(content.shipment_node_id, "—"),
                "product_id": content.product_id,
                "product_name": need.get("product_name", "Producto"),
                "purchase_unit": content.purchase_unit,
                "declared_quantity": content.declared_quantity,
                "declared_net_weight": content.declared_net_weight,
                "lot_number": content.lot_number or "",
                "expiration_date": content.expiration_date.isoformat()
                if content.expiration_date else "",
                "counted": count is not None,
                "received_quantity": count["received_quantity"] if count else None,
                "accepted_quantity": count["accepted_quantity"] if count else None,
                "received_net_weight": count["received_net_weight"] if count else None,
                "lot_required": need.get("lot_required", False),
                "expiration_required": need.get("expiration_required", False),
                "weight_required": need.get("weight_required", False),
                "temperature_required": need.get("temperature_required", False),
            })
        return result

    def record_count(self, *, actor_user_id, shipment_id, content_id, received_quantity,
                     accepted_quantity, received_net_weight="0", piece_count=None,
                     lot_number=None, expiration_date=None, temperature=None, notes=""):
        line = next((ln for ln in self.arrival_lines(shipment_id)
                     if ln["content_id"] == content_id), None)
        if line is None:
            raise ValueError("El contenido no pertenece al embarque")
        accepted = _dec(accepted_quantity)
        name = line["product_name"]
        # Lo que se ACEPTA debe traer lo que el producto exige; si todo se
        # rechaza no hay nada que rastrear en inventario.
        if accepted > 0:
            if line["weight_required"] and _dec(received_net_weight) <= 0:
                raise ValueError(f"{name} requiere el peso real recibido")
            if line["lot_required"] and not (lot_number or line["lot_number"]):
                raise ValueError(f"{name} requiere lote")
            if line["expiration_required"] and not (expiration_date or line["expiration_date"]):
                raise ValueError(f"{name} requiere caducidad")
            if line["temperature_required"] and temperature in (None, ""):
                raise ValueError(f"{name} requiere temperatura")
        self._logistics.record_count(
            actor_user_id=actor_user_id, shipment_id=shipment_id, content_id=content_id,
            received_quantity=str(_dec(received_quantity)), accepted_quantity=str(accepted),
            received_net_weight=str(_dec(received_net_weight)), piece_count=piece_count,
            lot_number=lot_number or line["lot_number"] or None,
            expiration_date=expiration_date or line["expiration_date"] or None,
            temperature=temperature, notes=notes, operation_id=new_uuid())
        return self.open(shipment_id)

    def receive_and_close(self, *, actor_user_id, shipment_id) -> dict:
        """Todo contado → una recepción (GoodsReceipt) por orden de compra del
        embarque, vinculada a él → inventario (por el flujo canónico de Compras) →
        embarque cerrado. Reintentar no duplica recepciones (operación
        determinística por embarque y orden)."""
        import uuid
        if self._receive_order is None:
            raise ValueError("La recepción de compras no está disponible en este equipo")
        shipment = self._logistics.get_shipment(shipment_id)
        if shipment is None:
            raise LookupError("Embarque inexistente")
        lines = self.arrival_lines(shipment_id)
        pending = [ln["product_name"] for ln in lines if not ln["counted"]]
        if pending:
            raise ValueError("Falta contar: " + ", ".join(pending))
        counts = self._logistics.arrival_counts(shipment_id)
        by_order: dict[tuple[str, str], list[dict]] = {}
        for content in shipment.contents:
            kind = content.source_document_type.value
            if kind not in ("PURCHASE_ORDER", "DIRECT_PURCHASE"):
                raise ValueError("Sólo se reciben órdenes de compra y compras directas.")
            if kind == "DIRECT_PURCHASE" and self._receive_direct is None:
                raise ValueError("La recepción de compras directas no está disponible "
                                 "en este equipo")
            count = counts[content.id]
            by_order.setdefault((kind, content.source_document_id), []).append({
                "product_id": content.product_id,
                "purchase_order_line_id": content.source_line_id,
                "received_quantity": count["received_quantity"],
                "accepted_quantity": count["accepted_quantity"],
                "net_weight": count["received_net_weight"]
                if _dec(count["received_net_weight"]) > 0 else None,
                "piece_count": count["piece_count"],
                "lot": count["lot_number"], "expiration": count["expiration_date"],
                "temperature": count["temperature"],
            })
        receipts = []
        for (kind, order_id), receipt_lines in by_order.items():
            operation_id = str(uuid.uuid5(uuid.NAMESPACE_URL,
                                          f"spj:arrival:{shipment_id}:{order_id}"))
            receive = self._receive_order if kind == "PURCHASE_ORDER" else self._receive_direct
            ok, message, data = receive(
                actor_user_id=actor_user_id, order_id=order_id, lines=receipt_lines,
                shipment_id=shipment_id, operation_id=operation_id)
            if not ok:
                raise ValueError(message)
            receipts.append(data.get("document_number") or data.get("entity_id"))
        self._logistics.close_shipment(actor_user_id=actor_user_id, shipment_id=shipment_id,
                                       operation_id=new_uuid())
        detail = self.open(shipment_id) or {}
        detail["receipts"] = receipts
        return detail
