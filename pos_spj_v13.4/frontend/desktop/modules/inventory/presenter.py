"""InventoryPresenter — bridge between the enterprise inventory UI and backend.

Wires the read/query services (availability, replenishment) and use cases
(generate suggestions) into display-ready view models and ``(ok, message, data)``
tuples. Never touches SQL/connections directly — it calls a ``connection_provider``
and the injected backend services. Presentation-only pages depend on this, so all
orchestration/formatting stays out of Qt.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid
from frontend.desktop.modules.inventory.capability_resolver import (
    resolve_inventory_capabilities,
)
from frontend.desktop.modules.inventory.view_models import (
    InventoryCapabilities,
    KpiViewModel,
    TableViewModel,
    adjustments_table,
    alert_severity_variant,
    alerts_table,
    audit_table,
    availability_breakdown_table,
    availability_table,
    cold_chain_table,
    counts_table,
    expiry_table,
    locations_table,
    lots_table,
    movement_lines_table,
    movements_table,
    quarantine_table,
    replenishment_table,
    reservations_table,
    settings_table,
    stock_table,
    traceability_table,
    transfers_table,
    urgency_variant,
    warehouses_table,
    weight_table,
    zones_table,
)

logger = logging.getLogger("spj.inventory.presenter")


class InventoryPresenter:
    def __init__(self, *, connection_provider, availability_service_factory,
                 replenishment_query_factory, generate_suggestions_uc=None,
                 warehouse_query_factory=None, analytics_factory=None,
                 lot_query_factory=None, movement_query_factory=None,
                 expiry_query_factory=None, traceability_query_factory=None,
                 stock_query_factory=None, quarantine_query_factory=None,
                 reservation_query_factory=None, cold_chain_query_factory=None,
                 audit_query_factory=None, transfer_query_factory=None,
                 weight_query_factory=None, receipt_query_factory=None,
                 count_query_factory=None, adjustment_query_factory=None,
                 alert_query_factory=None, settings_query_factory=None,
                 release_quarantine_uc=None, dispose_quarantine_uc=None,
                 open_quarantine_uc=None, product_query_factory=None,
                 create_adjustment_uc=None, approve_adjustment_uc=None,
                 post_adjustment_uc=None, reverse_adjustment_uc=None,
                 create_count_uc=None, record_count_uc=None,
                 confirm_count_uc=None, approve_count_uc=None,
                 create_adjustment_from_count_uc=None,
                 create_warehouse_uc=None, set_warehouse_status_uc=None,
                 update_warehouse_uc=None, deactivate_warehouse_uc=None,
                 create_zone_uc=None,
                 create_location_uc=None, set_location_status_uc=None,
                 update_location_uc=None, deactivate_location_uc=None,
                 reverse_movement_uc=None,
                 register_lot_uc=None, update_lot_uc=None,
                 set_lot_quality_status_uc=None, label_print_service_factory=None,
                 generate_expiry_alerts_uc=None, expire_inventory_uc=None,
                 record_catch_weight_uc=None, scale_gateway_factory=None,
                 record_temperature_reading_uc=None,
                 resolve_temperature_excursion_uc=None,
                 create_reservation_uc=None, allocate_reservation_uc=None,
                 release_reservation_uc=None, inspect_receipt_uc=None,
                 session_context=None, event_dispatcher=None) -> None:
        self._conn = connection_provider
        self._availability_factory = availability_service_factory
        self._replenishment_factory = replenishment_query_factory
        self._generate_uc = generate_suggestions_uc
        self._warehouse_factory = warehouse_query_factory
        self._analytics_factory = analytics_factory
        self._lot_factory = lot_query_factory
        self._movement_factory = movement_query_factory
        self._expiry_factory = expiry_query_factory
        self._traceability_factory = traceability_query_factory
        self._stock_factory = stock_query_factory
        self._quarantine_factory = quarantine_query_factory
        self._reservation_factory = reservation_query_factory
        self._cold_chain_factory = cold_chain_query_factory
        self._audit_factory = audit_query_factory
        self._transfer_factory = transfer_query_factory
        self._weight_factory = weight_query_factory
        self._receipt_factory = receipt_query_factory
        self._count_factory = count_query_factory
        self._adjustment_factory = adjustment_query_factory
        self._alert_factory = alert_query_factory
        self._settings_factory = settings_query_factory
        self._release_quarantine_uc = release_quarantine_uc
        self._dispose_quarantine_uc = dispose_quarantine_uc
        self._open_quarantine_uc = open_quarantine_uc
        self._product_factory = product_query_factory
        self._create_adjustment_uc = create_adjustment_uc
        self._approve_adjustment_uc = approve_adjustment_uc
        self._post_adjustment_uc = post_adjustment_uc
        self._reverse_adjustment_uc = reverse_adjustment_uc
        self._create_count_uc = create_count_uc
        self._record_count_uc = record_count_uc
        self._confirm_count_uc = confirm_count_uc
        self._approve_count_uc = approve_count_uc
        self._create_adjustment_from_count_uc = create_adjustment_from_count_uc
        self._create_warehouse_uc = create_warehouse_uc
        self._set_warehouse_status_uc = set_warehouse_status_uc
        self._update_warehouse_uc = update_warehouse_uc
        self._deactivate_warehouse_uc = deactivate_warehouse_uc
        self._create_zone_uc = create_zone_uc
        self._create_location_uc = create_location_uc
        self._set_location_status_uc = set_location_status_uc
        self._update_location_uc = update_location_uc
        self._deactivate_location_uc = deactivate_location_uc
        self._reverse_movement_uc = reverse_movement_uc
        self._register_lot_uc = register_lot_uc
        self._update_lot_uc = update_lot_uc
        self._set_lot_quality_status_uc = set_lot_quality_status_uc
        self._label_print_service_factory = label_print_service_factory
        self._generate_expiry_alerts_uc = generate_expiry_alerts_uc
        self._expire_inventory_uc = expire_inventory_uc
        self._record_catch_weight_uc = record_catch_weight_uc
        self._scale_gateway_factory = scale_gateway_factory
        self._record_temperature_reading_uc = record_temperature_reading_uc
        self._resolve_temperature_excursion_uc = resolve_temperature_excursion_uc
        self._create_reservation_uc = create_reservation_uc
        self._allocate_reservation_uc = allocate_reservation_uc
        self._release_reservation_uc = release_reservation_uc
        self._inspect_receipt_uc = inspect_receipt_uc
        self._session = session_context
        self._dispatch = event_dispatcher

    # session -----------------------------------------------------------------
    # §5.4 fail-closed: la identidad y el ámbito NO se fabrican ("desktop"/"MAIN",
    # ni warehouse_id = branch_id). Sin sesión válida quedan vacíos: las lecturas
    # devuelven vacío y las mutaciones se niegan aguas abajo (la política real exige
    # usuario y el checker deniega sin identidad).
    def _actor(self) -> str:
        return str(getattr(self._session, "user_id", None) or "")

    def capabilities(self) -> InventoryCapabilities:
        """Resolved display capabilities for the current session (§15/§17).
        Pages use this to show/enable actions; the backend re-validates every
        one independently regardless of what the UI shows."""
        check = getattr(self._session, "tiene_permiso", None)
        return resolve_inventory_capabilities(check if callable(check) else lambda _c: False)

    def default_branch(self) -> str:
        session = self._session
        return str(getattr(session, "active_branch_id", None)
                   or getattr(session, "branch_id", None) or "")

    def default_warehouse(self) -> str:
        session = self._session
        return str(getattr(session, "active_warehouse_id", None)
                   or getattr(session, "warehouse_id", None) or "")

    def product_options(self, query: str):
        """Canonical product search for pickers (§P0-D): name, code or barcode
        over the live ``products`` catalog — never a raw UUID typed by hand."""
        from frontend.desktop.components.search_selector import SearchOption
        if self._product_factory is None:
            return []
        try:
            results = self._product_factory(self._conn()).search_products(query)
        except Exception:
            logger.exception("InventoryPresenter.product_options failed")
            return []
        return [SearchOption(id=r.id, label=r.label, subtitle=r.subtitle)
                for r in results]

    def resolve_barcode(self, barcode: str):
        """Resolución exacta de código de barras (§P0-D item 2): a diferencia
        de ``product_options`` (búsqueda difusa, para escribir/filtrar), esto
        es lo que un escáner necesita — una coincidencia exacta y
        determinista, o nada. Nunca ambigua."""
        from frontend.desktop.components.search_selector import SearchOption
        if self._product_factory is None:
            return None
        code = str(barcode or "").strip()
        if not code:
            return None
        try:
            result = self._product_factory(self._conn()).resolve_barcode(code)
        except Exception:
            logger.exception("InventoryPresenter.resolve_barcode failed")
            return None
        if result is None:
            return None
        return SearchOption(id=result.id, label=result.label, subtitle=result.subtitle)

    def _product_names(self, product_ids) -> dict:
        """Resolución en lote de id→nombre (§P0-D item 3): nunca mostrar un
        UUID crudo en una tabla cuando el nombre está a una consulta de
        distancia. Falla cerrado a un dict vacío — los llamadores deben usar
        ``.get(pid, pid)`` para no perder la fila si el nombre no resuelve."""
        if self._product_factory is None:
            return {}
        ids = [str(pid) for pid in (product_ids or []) if pid]
        if not ids:
            return {}
        try:
            return self._product_factory(self._conn()).get_names(ids)
        except Exception:
            logger.exception("InventoryPresenter._product_names failed")
            return {}

    def location_options(self, *, warehouse_id: str | None = None):
        """Ubicaciones reales (activas) del almacén, para selects acotados
        (§P0-04 corolario): una lista chica por almacén no amerita
        EntitySearchInput — pero tampoco debe quedar ausente, forzando a la
        acción a asumir el almacén completo como ubicación implícita."""
        from frontend.desktop.components.search_selector import SearchOption
        if self._warehouse_factory is None:
            return []
        warehouse = warehouse_id or self.default_warehouse()
        if not warehouse:
            return []
        try:
            rows = self._warehouse_factory(self._conn()).list_locations(
                warehouse_id=warehouse)
        except Exception:
            logger.exception("InventoryPresenter.location_options failed")
            return []
        return [SearchOption(id=r.get("id"), label=f"{r.get('code')} — {r.get('name')}",
                             subtitle=str(r.get("status") or ""))
                for r in rows if str(r.get("status") or "ACTIVE") == "ACTIVE"]

    def warehouse_options(self, *, branch_id: str | None = None):
        """Almacenes de la sucursal, para selects acotados (p.ej. el picker de
        la página de Ubicaciones, que no tiene forma de elegir almacén hoy)."""
        from frontend.desktop.components.search_selector import SearchOption
        if self._warehouse_factory is None:
            return []
        branch = branch_id or self.default_branch()
        if not branch:
            return []
        try:
            rows = self._warehouse_factory(self._conn()).list_warehouses(branch_id=branch)
        except Exception:
            logger.exception("InventoryPresenter.warehouse_options failed")
            return []
        return [SearchOption(id=r.get("id"), label=f"{r.get('code')} — {r.get('name')}",
                             subtitle=str(r.get("status") or ""))
                for r in rows]

    # reads -------------------------------------------------------------------
    def availability(self, *, product_ids: list[str], branch_id: str | None = None,
                     warehouse_id: str | None = None) -> TableViewModel:
        branch = branch_id or self.default_branch()
        svc = self._availability_factory(self._conn())
        rows = []
        for pid in product_ids:
            dto = svc.get_availability(product_id=pid, branch_id=branch,
                                       warehouse_id=warehouse_id)
            rows.append({"product_id": dto.product_id, "on_hand": dto.on_hand,
                         "reserved": dto.reserved, "available": dto.available})
        names = self._product_names([r["product_id"] for r in rows])
        for r in rows:
            r["product_name"] = names.get(r["product_id"], r["product_id"])
        return availability_table(rows)

    def stock(self, *, branch_id: str | None = None) -> TableViewModel:
        """Existencias físicas por producto/almacén/bucket (cantidad ≠ 0). Sólo
        lectura; delega en el stock query service."""
        if self._stock_factory is None:
            return stock_table([])
        branch = branch_id or self.default_branch()
        rows = self._stock_factory(self._conn()).list_on_hand(branch_id=branch or None)
        names = self._product_names([r.get("product_id") for r in rows])
        for r in rows:
            r["product_name"] = names.get(r.get("product_id"), r.get("product_id"))
        return stock_table(rows)

    def reservations(self, *, product_id: str,
                     branch_id: str | None = None) -> TableViewModel:
        """Reservas activas de un producto (origen, documento, almacén, cantidad,
        estado). Sólo lectura; delega en el reservation query service."""
        pid = str(product_id or "").strip()
        if not pid or self._reservation_factory is None:
            return reservations_table([])
        branch = branch_id or self.default_branch()
        rows = self._reservation_factory(self._conn()).list_active_for_product(
            product_id=pid, branch_id=branch or None)
        return reservations_table(rows)

    def audit(self, *, branch_id: str | None = None) -> TableViewModel:
        """Bitácora de auditoría reciente (fecha, entidad, acción, usuario,
        autorizó). Sólo lectura; delega en el audit query service."""
        if self._audit_factory is None:
            return audit_table([])
        branch = branch_id or self.default_branch()
        rows = self._audit_factory(self._conn()).list_recent(branch_id=branch or None)
        return audit_table(rows)

    def settings(self) -> TableViewModel:
        """Parámetros del módulo: reglas de notificación (evento, ámbito, canal,
        severidad mínima, throttle, activa). Sólo lectura; delega en el settings
        query service."""
        if self._settings_factory is None:
            return settings_table([])
        rows = self._settings_factory(self._conn()).list_notification_rules()
        return settings_table(rows)

    def alerts(self, *, branch_id: str | None = None,
               severity: str | None = None) -> TableViewModel:
        """Alertas recientes de inventario (fecha, severidad, evento, canal, estado,
        mensaje), opcionalmente filtradas por severidad. Sólo lectura; delega en el
        alert query service."""
        if self._alert_factory is None:
            return alerts_table([])
        branch = branch_id or self.default_branch()
        rows = self._alert_factory(self._conn()).list_recent(
            branch_id=branch or None, severity=severity or None)
        return alerts_table(rows)

    def alert_kpis(self, *, branch_id: str | None = None) -> list[KpiViewModel]:
        """Resumen de alertas por severidad (total, críticas, advertencias,
        informativas) para la KPIBar de la página de Alertas."""
        if self._alert_factory is None:
            return []
        branch = branch_id or self.default_branch()
        rows = self._alert_factory(self._conn()).list_recent(branch_id=branch or None)
        counts: dict[str, int] = {}
        for r in rows:
            key = str(r.get("severity") or "")
            counts[key] = counts.get(key, 0) + 1
        return [
            KpiViewModel(key="total", title="Alertas", value=str(len(rows)),
                         variant="info"),
            KpiViewModel(key="critical", title="Críticas",
                         value=str(counts.get("CRITICAL", 0)),
                         variant=alert_severity_variant("CRITICAL")),
            KpiViewModel(key="warning", title="Advertencias",
                         value=str(counts.get("WARNING", 0)),
                         variant=alert_severity_variant("WARNING")),
            KpiViewModel(key="info", title="Informativas",
                         value=str(counts.get("INFO", 0)),
                         variant=alert_severity_variant("INFO")),
        ]

    def adjustments(self, *, branch_id: str | None = None) -> TableViewModel:
        """Ajustes recientes (folio, motivo, almacén, estado, creado). Sólo
        lectura; delega en el adjustment query service."""
        if self._adjustment_factory is None:
            return adjustments_table([])
        branch = branch_id or self.default_branch()
        rows = self._adjustment_factory(self._conn()).list_recent(
            branch_id=branch or None)
        return adjustments_table(rows)

    def counts(self, *, branch_id: str | None = None) -> TableViewModel:
        """Conteos recientes (folio, tipo, almacén, modalidad, estado, creado).
        Sólo lectura; delega en el count query service."""
        if self._count_factory is None:
            return counts_table([])
        branch = branch_id or self.default_branch()
        rows = self._count_factory(self._conn()).list_recent(branch_id=branch or None)
        return counts_table(rows)

    def receipts(self, *, branch_id: str | None = None) -> TableViewModel:
        """Recepciones recientes hacia el inventario (compra, transferencia,
        producción): fecha, tipo, módulo, documento, estado. Sólo lectura; delega
        en el receipt query service (subconjunto entrante del ledger)."""
        if self._receipt_factory is None:
            return movements_table([])
        branch = branch_id or self.default_branch()
        rows = self._receipt_factory(self._conn()).list_recent(
            branch_id=branch or None)
        return movements_table(rows)

    def catch_weight(self, *, branch_id: str | None = None) -> TableViewModel:
        """Existencias de peso variable (catch-weight): balances con peso ≠ 0
        (producto, almacén, bucket, piezas, peso, peso reservado). Sólo lectura;
        delega en el weight query service."""
        if self._weight_factory is None:
            return weight_table([])
        branch = branch_id or self.default_branch()
        rows = self._weight_factory(self._conn()).list_catch_weight(
            branch_id=branch or None)
        names = self._product_names([r.get("product_id") for r in rows])
        for r in rows:
            r["product_name"] = names.get(r.get("product_id"), r.get("product_id"))
        return weight_table(rows)

    def weight_history(self, *, branch_id: str | None = None) -> TableViewModel:
        """Historial de capturas de peso (§28 "Ver historial"): los ajustes con
        motivo ``WEIGHT_VARIANCE`` — cada captura de báscula/manual se aplica al
        inventario como un ajuste, así que su historial es ese mismo filtro.
        Sólo lectura; delega en el adjustment query service."""
        if self._adjustment_factory is None:
            return adjustments_table([])
        branch = branch_id or self.default_branch()
        rows = self._adjustment_factory(self._conn()).list_recent(
            branch_id=branch or None, reason="WEIGHT_VARIANCE")
        return adjustments_table(rows)

    def read_scale(self) -> dict | None:
        """Lee una lectura pendiente de la báscula cableada (§18/§28 "Leer
        báscula"): vista previa antes de confirmar la captura. Sin gateway
        cableado o sin lectura encolada (driver de hardware pendiente) devuelve
        None — la UI debe ofrecer la captura manual, no fallar."""
        if self._scale_gateway_factory is None:
            return None
        from backend.domain.inventory.exceptions import InvalidCatchWeightError
        try:
            gateway = self._scale_gateway_factory()
            reading = gateway.read()
        except InvalidCatchWeightError:
            return None
        except Exception:
            logger.exception("InventoryPresenter.read_scale failed")
            return None
        return {"gross": reading.gross, "tare": reading.tare, "net": reading.net,
                "unit": reading.unit, "stable": reading.stable,
                "source": reading.source.value}

    def transfers(self, *, branch_id: str | None = None) -> TableViewModel:
        """Transferencias físicas recientes que tocan la sucursal (folio, tipo,
        origen, destino, estado, actualizado). Sólo lectura; ventana al contexto de
        Transferencias — la gestión completa vive en su módulo dedicado."""
        if self._transfer_factory is None:
            return transfers_table([])
        branch = branch_id or self.default_branch()
        rows = self._transfer_factory(self._conn()).list_recent(
            branch_id=branch or None)
        return transfers_table(rows)

    def cold_chain_excursions(self, *, warehouse_id: str | None = None) -> TableViewModel:
        """Excursiones de temperatura abiertas (almacén, lote, temperatura, rango,
        estado, acción). Sólo lectura; delega en el cold chain query service."""
        if self._cold_chain_factory is None:
            return cold_chain_table([])
        rows = self._cold_chain_factory(self._conn()).list_open_excursions(
            warehouse_id=warehouse_id or None)
        return cold_chain_table(rows)

    def quarantines(self, *, branch_id: str | None = None) -> TableViewModel:
        """Cuarentenas abiertas (producto, lote, motivo, cantidad, estado). Sólo
        lectura; delega en el quarantine query service."""
        if self._quarantine_factory is None:
            return quarantine_table([])
        branch = branch_id or self.default_branch()
        rows = self._quarantine_factory(self._conn()).list_open(branch_id=branch or None)
        names = self._product_names([r.get("product_id") for r in rows])
        for r in rows:
            r["product_name"] = names.get(r.get("product_id"), r.get("product_id"))
        return quarantine_table(rows)

    def availability_breakdown(self, *, product_id: str, branch_id: str | None = None,
                               warehouse_id: str | None = None) -> TableViewModel:
        """Desglose de disponibilidad de UN producto por bucket físico (§9.3): total
        en mano, disponible, reservado y cada bucket que explica un faltante. Sólo
        lectura; delega en el availability query service (.explain())."""
        pid = str(product_id or "").strip()
        if not pid:
            return availability_breakdown_table({})
        branch = branch_id or self.default_branch()
        dto = self._availability_factory(self._conn()).get_availability(
            product_id=pid, branch_id=branch, warehouse_id=warehouse_id)
        return availability_breakdown_table(dto.explain())

    def lots(self, *, product_id: str, branch_id: str | None = None) -> TableViewModel:
        """Lotes de un producto (código, origen, calidad, caducidad) por FEFO.
        Sólo lectura; delega en el lot query service."""
        pid = str(product_id or "").strip()
        if not pid or self._lot_factory is None:
            return lots_table([])
        branch = branch_id or self.default_branch()
        rows = self._lot_factory(self._conn()).list_for_product(
            product_id=pid, branch_id=branch or None)
        return lots_table(rows)

    def lot_detail(self, *, lot_id: str) -> dict | None:
        """Fila cruda de un lote (§26 detalle) — para la vista de detalle, no
        la fila ya formateada de la lista."""
        lid = str(lot_id or "").strip()
        if not lid or self._lot_factory is None:
            return None
        return self._lot_factory(self._conn()).get_lot(lot_id=lid)

    def lot_stock(self, *, lot_id: str) -> TableViewModel:
        """Existencias del lote (§26 "Ver stock"). Sólo lectura; delega en el
        stock query service (mismo mapper que la página de Existencias)."""
        lid = str(lot_id or "").strip()
        if not lid or self._stock_factory is None:
            return stock_table([])
        rows = self._stock_factory(self._conn()).list_on_hand(lot_id=lid)
        names = self._product_names([r.get("product_id") for r in rows])
        for r in rows:
            r["product_name"] = names.get(r.get("product_id"), r.get("product_id"))
        return stock_table(rows)

    def lot_movements(self, *, lot_id: str) -> TableViewModel:
        """Movimientos del ledger que tocan el lote (§26 "Ver movimientos").
        Sólo lectura; delega en el movement query service."""
        lid = str(lot_id or "").strip()
        if not lid or self._movement_factory is None:
            return movements_table([])
        rows = self._movement_factory(self._conn()).list_for_lot(lot_id=lid)
        return movements_table(rows)

    def movements(self, *, branch_id: str | None = None,
                  limit: int = 100) -> TableViewModel:
        """Movimientos recientes del ledger (fecha, tipo, módulo, documento, estado),
        más recientes primero. Sólo lectura; delega en el movement query service."""
        if self._movement_factory is None:
            return movements_table([])
        branch = branch_id or self.default_branch()
        rows = self._movement_factory(self._conn()).list_recent(
            branch_id=branch or None, limit=limit)
        return movements_table(rows)

    def movement_detail(self, *, movement_id: str) -> dict | None:
        """Encabezado crudo del movimiento (§6 detalle) — para la vista de
        detalle, no la fila ya formateada de la lista."""
        mid = str(movement_id or "").strip()
        if not mid or self._movement_factory is None:
            return None
        return self._movement_factory(self._conn()).get_movement(movement_id=mid)

    def _location_labels(self, location_ids) -> dict:
        """id→"código — nombre" para las ubicaciones citadas en un puñado de
        líneas de movimiento (§P0-D: nunca un UUID crudo). El número de
        ubicaciones distintas por movimiento es chico, así que resolver una
        por una aquí es más simple que agregar una consulta masiva nueva."""
        if self._warehouse_factory is None:
            return {}
        svc = self._warehouse_factory(self._conn())
        labels = {}
        for lid in {str(i) for i in location_ids if i}:
            row = svc.get_location(location_id=lid)
            if row is not None:
                labels[lid] = f"{row.get('code')} — {row.get('name')}"
        return labels

    def movement_lines(self, *, movement_id: str) -> TableViewModel:
        """Líneas del movimiento (§6 detalle/líneas). Sólo lectura; delega en
        el movement query service."""
        mid = str(movement_id or "").strip()
        if not mid or self._movement_factory is None:
            return movement_lines_table([])
        rows = self._movement_factory(self._conn()).get_lines(movement_id=mid)
        names = self._product_names([r.get("product_id") for r in rows])
        locations = self._location_labels(
            [r.get("from_location_id") for r in rows]
            + [r.get("to_location_id") for r in rows])
        return movement_lines_table(rows, product_names=names, location_labels=locations)

    def movement_source_document(self, *, movement_id: str) -> TableViewModel:
        """Otros movimientos del ledger que comparten el mismo documento
        origen (§6 documento origen) — p.ej. todos los efectos de inventario
        de una misma recepción de compra. Sólo lectura."""
        mid = str(movement_id or "").strip()
        if not mid or self._movement_factory is None:
            return movements_table([])
        svc = self._movement_factory(self._conn())
        header = svc.get_movement(movement_id=mid)
        if header is None:
            return movements_table([])
        doc_type = header.get("source_document_type")
        doc_id = header.get("source_document_id")
        if not doc_type or not doc_id:
            return movements_table([])
        rows = svc.list_for_document(
            source_document_type=doc_type, source_document_id=doc_id)
        return movements_table(rows)

    def movement_audit(self, *, movement_id: str) -> TableViewModel:
        """Bitácora de auditoría de este movimiento (§6 auditoría): quién lo
        posteó, quién lo reversó y cuándo. Sólo lectura; delega en el audit
        query service (ya escrito por post_movement/ReverseInventoryMovementUseCase)."""
        mid = str(movement_id or "").strip()
        if not mid or self._audit_factory is None:
            return audit_table([])
        rows = self._audit_factory(self._conn()).list_recent(entity_id=mid)
        return audit_table(rows)

    def reverse_movement(self, *, movement_id: str,
                         reason: str) -> tuple[bool, str, dict]:
        """Reversa un movimiento posteado (§6 reverso): movimiento inverso,
        irreversible, ligado por ``reversal_of_id``."""
        if self._reverse_movement_uc is None:
            return False, "Reverso de movimientos no disponible.", {}
        mid = str(movement_id or "").strip()
        if not mid:
            return False, "Selecciona un movimiento.", {}
        reason_v = str(reason or "").strip()
        if not reason_v:
            return False, "Captura un motivo.", {}
        try:
            result = self._reverse_movement_uc.execute(
                self._conn(), movement_id=mid, operation_id=new_uuid(),
                actor_user_id=self._actor(), reason=reason_v)
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.reverse_movement failed")
            return False, "Error inesperado; revise el log.", {}

    def register_lot(self, *, product_id: str, lot_code: str, origin_type: str,
                     supplier_lot_code: str = "", production_lot_code: str = "",
                     origin_document_id: str = "", production_date: str = "",
                     expiration_date: str = "", branch_id: str | None = None
                     ) -> tuple[bool, str, dict]:
        """Alta de lote (§26 "Registrar lote")."""
        if self._register_lot_uc is None:
            return False, "Registro de lotes no disponible.", {}
        pid = str(product_id or "").strip()
        code = str(lot_code or "").strip()
        if not pid or not code:
            return False, "Selecciona un producto y captura el código de lote.", {}
        try:
            from backend.domain.inventory.enums import LotOrigin
            origin_enum = LotOrigin(str(origin_type))
        except ValueError:
            return False, "Origen de lote inválido.", {}
        try:
            result = self._register_lot_uc.execute(
                self._conn(), product_id=pid, lot_code=code, origin_type=origin_enum,
                operation_id=new_uuid(), actor_user_id=self._actor(),
                supplier_lot_code=str(supplier_lot_code or "").strip() or None,
                production_lot_code=str(production_lot_code or "").strip() or None,
                origin_document_id=str(origin_document_id or "").strip() or None,
                production_date=str(production_date or "").strip() or None,
                expiration_date=str(expiration_date or "").strip() or None,
                branch_id=branch_id or self.default_branch() or None)
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.register_lot failed")
            return False, "Error inesperado; revise el log.", {}

    def update_lot(self, *, lot_id: str, supplier_lot_code: str | None = ...,
                   production_lot_code: str | None = ..., origin_document_id: str | None = ...,
                   production_date: str | None = ..., expiration_date: str | None = ...
                   ) -> tuple[bool, str, dict]:
        """Edita los datos permitidos de un lote (§26 "Editar datos permitidos")."""
        if self._update_lot_uc is None:
            return False, "Edición de lotes no disponible.", {}
        lid = str(lot_id or "").strip()
        if not lid:
            return False, "Selecciona un lote.", {}
        fields: dict = {}
        for name, value in (
            ("supplier_lot_code", supplier_lot_code),
            ("production_lot_code", production_lot_code),
            ("origin_document_id", origin_document_id),
            ("production_date", production_date),
            ("expiration_date", expiration_date),
        ):
            if value is not ...:
                fields[name] = str(value).strip() or None if value is not None else None
        try:
            result = self._update_lot_uc.execute(
                self._conn(), lot_id=lid, operation_id=new_uuid(),
                actor_user_id=self._actor(), **fields)
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.update_lot failed")
            return False, "Error inesperado; revise el log.", {}

    def set_lot_quality_status(self, *, lot_id: str, new_status: str,
                               reason: str = "") -> tuple[bool, str, dict]:
        """Libera, bloquea o envía a cuarentena un lote (§26/§31) — un único
        flujo auditado, con el estado destino como único diferenciador."""
        if self._set_lot_quality_status_uc is None:
            return False, "Cambio de estado de calidad no disponible.", {}
        lid = str(lot_id or "").strip()
        if not lid:
            return False, "Selecciona un lote.", {}
        try:
            from backend.domain.inventory.enums import LotQualityStatus
            status_enum = LotQualityStatus(str(new_status))
        except ValueError:
            return False, "Estado de calidad inválido.", {}
        try:
            result = self._set_lot_quality_status_uc.execute(
                self._conn(), lot_id=lid, new_status=status_enum, operation_id=new_uuid(),
                actor_user_id=self._actor(), reason=str(reason or "").strip())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.set_lot_quality_status failed")
            return False, "Error inesperado; revise el log.", {}

    def print_lot_label(self, *, lot_id: str,
                        is_reprint: bool = False) -> tuple[bool, str, dict]:
        """Imprime (o reimprime) la etiqueta de un lote (§26)."""
        if self._label_print_service_factory is None:
            return False, "Impresión de etiquetas no disponible.", {}
        lid = str(lot_id or "").strip()
        if not lid or self._lot_factory is None:
            return False, "Selecciona un lote.", {}
        lot = self._lot_factory(self._conn()).get_lot(lot_id=lid)
        if lot is None:
            return False, "Lote no encontrado.", {}
        names = self._product_names([lot.get("product_id")])
        product_name = names.get(lot.get("product_id"), lot.get("product_id"))
        try:
            from backend.domain.inventory.enums import LabelType
            from backend.domain.inventory.value_objects.label_document import (
                LabelDocument,
            )
            document = LabelDocument(
                label_type=LabelType.LOT, title=str(lot.get("lot_code") or ""),
                lines=(str(product_name), f"Caducidad: {lot.get('expiration_date') or '—'}"),
                barcode=str(lot.get("lot_code") or ""), entity_ref=lid)
            service = self._label_print_service_factory(self._conn())
            result = service.print_label(
                document, actor_user_id=self._actor(), is_reprint=is_reprint,
                branch_id=lot.get("branch_id"))
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.print_lot_label failed")
            return False, "Error inesperado; revise el log.", {}

    def record_temperature_reading(self, *, sensor_id: str, warehouse_id: str | None = None,
                                   temperature, reading_point: str, min_temp, max_temp,
                                   warning_margin=0, location_id: str | None = None,
                                   lot_id: str | None = None,
                                   auto_block: bool = False) -> tuple[bool, str, dict]:
        """Registra una lectura de temperatura (§21 "Registrar lectura"): clasifica
        contra el rango, y si excede (WARNING/OUT_OF_RANGE) registra la excursión y,
        con bloqueo automático + lote, pone el lote en cuarentena."""
        if self._record_temperature_reading_uc is None:
            return False, "Registro de temperatura no disponible.", {}
        sensor = str(sensor_id or "").strip()
        if not sensor:
            return False, "Captura el identificador del sensor.", {}
        warehouse = warehouse_id or self.default_warehouse()
        if not warehouse:
            return False, "Selecciona un almacén.", {}
        try:
            from backend.domain.inventory.enums import TemperaturePoint
            point_enum = TemperaturePoint(str(reading_point))
        except ValueError:
            return False, "Punto de lectura inválido.", {}
        try:
            result = self._record_temperature_reading_uc.execute(
                self._conn(), sensor_id=sensor, warehouse_id=warehouse,
                temperature=temperature, reading_point=point_enum, min_temp=min_temp,
                max_temp=max_temp, warning_margin=warning_margin, location_id=location_id,
                lot_id=lot_id or None, auto_block=auto_block, operation_id=new_uuid(),
                actor_user_id=self._actor())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.record_temperature_reading failed")
            return False, "Error inesperado; revise el log.", {}

    def resolve_temperature_excursion(self, *, excursion_id: str, resolution: str,
                                      resolution_note: str = "") -> tuple[bool, str, dict]:
        """Resuelve una excursión abierta (§21 "Resolver excursión"): libera o
        rechaza el lote si quedó bloqueado por auto-bloqueo, y cierra la excursión."""
        if self._resolve_temperature_excursion_uc is None:
            return False, "Resolución de excursiones no disponible.", {}
        eid = str(excursion_id or "").strip()
        if not eid:
            return False, "Selecciona una excursión.", {}
        if resolution not in ("RELEASE", "REJECT"):
            return False, "Acción de resolución inválida.", {}
        try:
            result = self._resolve_temperature_excursion_uc.execute(
                self._conn(), excursion_id=eid, resolution=resolution,
                resolution_note=str(resolution_note or "").strip(),
                operation_id=new_uuid(), actor_user_id=self._actor())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.resolve_temperature_excursion failed")
            return False, "Error inesperado; revise el log.", {}

    def create_reservation(self, *, product_id: str, source: str, source_document_id: str,
                           quantity, weight=0, branch_id: str | None = None,
                           warehouse_id: str | None = None, expires_at=None,
                           location_id: str | None = None) -> tuple[bool, str, dict]:
        """Crea una reserva (§22): reduce el disponible a prometer sin mover stock
        físico. La asignación a lotes concretos es un paso aparte
        (``allocate_reservation``)."""
        if self._create_reservation_uc is None:
            return False, "Creación de reservas no disponible.", {}
        pid = str(product_id or "").strip()
        if not pid:
            return False, "Selecciona un producto.", {}
        try:
            from backend.domain.inventory.enums import ReservationSource
            source_enum = ReservationSource(str(source))
        except ValueError:
            return False, "Origen de reserva inválido.", {}
        if not quantity:
            return False, "Captura una cantidad mayor a cero.", {}
        branch = branch_id or self.default_branch()
        warehouse = warehouse_id or self.default_warehouse()
        try:
            result = self._create_reservation_uc.execute(
                self._conn(), product_id=pid, branch_id=branch, warehouse_id=warehouse,
                source=source_enum,
                source_document_id=str(source_document_id or "").strip(),
                quantity=quantity, weight=weight, expires_at=expires_at or None,
                location_id=location_id, operation_id=new_uuid(),
                actor_user_id=self._actor())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.create_reservation failed")
            return False, "Error inesperado; revise el log.", {}

    def allocate_reservation(self, *, reservation_id: str) -> tuple[bool, str, dict]:
        """Asigna una reserva confirmada a lotes concretos por FEFO (§22)."""
        if self._allocate_reservation_uc is None:
            return False, "Asignación de reservas no disponible.", {}
        rid = str(reservation_id or "").strip()
        if not rid:
            return False, "Selecciona una reserva.", {}
        try:
            result = self._allocate_reservation_uc.execute(
                self._conn(), reservation_id=rid, operation_id=new_uuid(),
                actor_user_id=self._actor())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.allocate_reservation failed")
            return False, "Error inesperado; revise el log.", {}

    def release_reservation(self, *, reservation_id: str,
                            reason: str = "") -> tuple[bool, str, dict]:
        """Libera una reserva activa (§22): el disponible a prometer vuelve a subir."""
        if self._release_reservation_uc is None:
            return False, "Liberación de reservas no disponible.", {}
        rid = str(reservation_id or "").strip()
        if not rid:
            return False, "Selecciona una reserva.", {}
        try:
            result = self._release_reservation_uc.execute(
                self._conn(), reservation_id=rid, reason=str(reason or "").strip(),
                operation_id=new_uuid(), actor_user_id=self._actor())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.release_reservation failed")
            return False, "Error inesperado; revise el log.", {}

    def inspect_stock(self, *, balance_id: str, passed: bool,
                      reason: str = "") -> tuple[bool, str, dict]:
        """Aprueba (→ AVAILABLE) o rechaza (→ QUALITY_BLOCKED) una existencia
        retenida para inspección (§34/P0-E)."""
        if self._inspect_receipt_uc is None:
            return False, "Inspección de existencias no disponible.", {}
        bid = str(balance_id or "").strip()
        if not bid:
            return False, "Selecciona una existencia.", {}
        try:
            result = self._inspect_receipt_uc.execute(
                self._conn(), balance_id=bid, passed=bool(passed),
                operation_id=new_uuid(), actor_user_id=self._actor(),
                reason=str(reason or "").strip())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.inspect_stock failed")
            return False, "Error inesperado; revise el log.", {}

    def generate_expiry_alerts(self) -> tuple[bool, str, dict]:
        """Genera alertas de caducidad (§27) para los lotes disponibles en
        riesgo — no mueve stock, sólo evalúa y encola alertas."""
        if self._generate_expiry_alerts_uc is None:
            return False, "Generación de alertas no disponible.", {}
        try:
            result = self._generate_expiry_alerts_uc.execute(
                self._conn(), operation_id=new_uuid(), actor_user_id=self._actor())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.generate_expiry_alerts failed")
            return False, "Error inesperado; revise el log.", {}

    def process_expired_lots(self) -> tuple[bool, str, dict]:
        """Procesa lotes vencidos (§27 "Procesar vencidos"): mueve su existencia
        disponible al bucket EXPIRED (no los da de baja — eso es una merma aparte)."""
        if self._expire_inventory_uc is None:
            return False, "Procesamiento de vencidos no disponible.", {}
        try:
            result = self._expire_inventory_uc.execute(
                self._conn(), operation_id=new_uuid(), actor_user_id=self._actor())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.process_expired_lots failed")
            return False, "Error inesperado; revise el log.", {}

    def expiring(self, *, branch_id: str | None = None) -> TableViewModel:
        """Lotes disponibles en riesgo de caducidad (vencido/crítico/próximo),
        próximos a vencer primero. Sólo lectura; delega en el expiry query service
        (clasifica, no emite eventos ni mueve stock)."""
        if self._expiry_factory is None:
            return expiry_table([])
        branch = branch_id or self.default_branch()
        rows = self._expiry_factory(self._conn()).list_at_risk(branch_id=branch or None)
        names = self._product_names([r.get("product_id") for r in rows])
        for r in rows:
            r["product_name"] = names.get(r.get("product_id"), r.get("product_id"))
        return expiry_table(rows)

    def traceability(self, *, lot_id: str) -> TableViewModel:
        """Rastreo ascendente de un lote (eventos que lo originaron): fecha,
        movimiento, dirección, módulo y documento. Sólo lectura; delega en el
        traceability query service."""
        lid = str(lot_id or "").strip()
        if not lid or self._traceability_factory is None:
            return traceability_table(())
        trace = self._traceability_factory(self._conn()).trace_upstream(lid)
        return traceability_table(trace.events)

    def open_suggestions(self, *, branch_id: str | None = None) -> TableViewModel:
        branch = branch_id or self.default_branch()
        svc = self._replenishment_factory(self._conn())
        rows = svc.list_open_suggestions(branch_id=branch)
        names = self._product_names([r.get("product_id") for r in rows])
        for r in rows:
            r["product_name"] = names.get(r.get("product_id"), r.get("product_id"))
        return replenishment_table(rows)

    def replenishment_kpis(self, *, branch_id: str | None = None) -> list[KpiViewModel]:
        branch = branch_id or self.default_branch()
        rows = self._replenishment_factory(self._conn()).list_open_suggestions(
            branch_id=branch)
        by_urgency: dict[str, int] = {}
        for r in rows:
            key = str(r.get("urgency") or "OK")
            by_urgency[key] = by_urgency.get(key, 0) + 1
        return [
            KpiViewModel(key="open", title="Sugerencias abiertas", value=str(len(rows)),
                         variant="info"),
            KpiViewModel(key="critical", title="Críticas",
                         value=str(by_urgency.get("CRITICAL", 0) + by_urgency.get("STOCKOUT", 0)),
                         variant=urgency_variant("CRITICAL")),
            KpiViewModel(key="reorder", title="Por reordenar",
                         value=str(by_urgency.get("REORDER", 0)),
                         variant=urgency_variant("REORDER")),
        ]

    def warehouses(self, *, branch_id: str | None = None) -> TableViewModel:
        branch = branch_id or self.default_branch()
        svc = self._warehouse_factory(self._conn())
        return warehouses_table(svc.list_warehouses(branch_id=branch))

    def warehouse_detail(self, *, warehouse_id: str) -> dict | None:
        """Fila cruda de un almacén (§24 edición) — para prellenar el diálogo de
        edición con los valores reales, no las cadenas ya formateadas para tabla."""
        wid = str(warehouse_id or "").strip()
        if not wid:
            return None
        svc = self._warehouse_factory(self._conn())
        return svc.get_warehouse(warehouse_id=wid)

    def location_detail(self, *, location_id: str) -> dict | None:
        """Fila cruda de una ubicación (§24 edición), mismo motivo que
        ``warehouse_detail``."""
        lid = str(location_id or "").strip()
        if not lid:
            return None
        svc = self._warehouse_factory(self._conn())
        return svc.get_location(location_id=lid)

    def location_tree(self, *, warehouse_id: str) -> TableViewModel:
        svc = self._warehouse_factory(self._conn())
        return locations_table(svc.location_hierarchy(warehouse_id=warehouse_id))

    def zones(self, *, warehouse_id: str) -> TableViewModel:
        """Zonas del almacén (§24 "Zonas"). Sólo lectura; delega en el
        warehouse query service (``list_zones`` ya existía sin UI)."""
        wid = str(warehouse_id or "").strip()
        if not wid:
            return zones_table([])
        svc = self._warehouse_factory(self._conn())
        return zones_table(svc.list_zones(warehouse_id=wid))

    # analytics (INV-24) -------------------------------------------------------
    def inventory_kpis(self, *, branch_id: str | None = None) -> list[KpiViewModel]:
        branch = branch_id or self.default_branch()
        dtos = self._analytics_factory(self._conn()).kpis(branch_id=branch)
        return [KpiViewModel(key=d.key, title=d.title, value=d.value, variant=d.variant,
                             subtitle=d.unit, tooltip=d.tooltip) for d in dtos]

    def analytics_charts(self, *, branch_id: str | None = None) -> list:
        branch = branch_id or self.default_branch()
        svc = self._analytics_factory(self._conn())
        return [
            svc.stock_by_status_chart(branch_id=branch),
            svc.stock_by_warehouse_chart(branch_id=branch),
            svc.movements_by_type_chart(branch_id=branch),
            svc.waste_by_type_chart(branch_id=branch),
        ]

    def freshness(self, *, branch_id: str | None = None):
        branch = branch_id or self.default_branch()
        return self._analytics_factory(self._conn()).freshness(branch_id=branch)

    def export_availability_csv(self, *, branch_id: str | None = None) -> str:
        branch = branch_id or self.default_branch()
        return self._analytics_factory(self._conn()).export_availability_csv(
            branch_id=branch)

    # commands ----------------------------------------------------------------
    def generate_suggestions(self, *, branch_id: str | None = None) -> tuple[bool, str, dict]:
        if self._generate_uc is None:
            return False, "Generación de sugerencias no disponible.", {}
        branch = branch_id or self.default_branch()
        try:
            result = self._generate_uc.execute(
                self._conn(), operation_id=new_uuid(), actor_user_id=self._actor(),
                branch_id=branch)
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.generate_suggestions failed")
            return False, "Error inesperado; revise el log.", {}

    @staticmethod
    def _result_data(result) -> dict:
        """Normaliza InventoryResult a un dict de UI: entity_id + data (§18,
        "resultados normalizados: success, message, error_code, entity_id, data")."""
        data = dict(result.data)
        if result.entity_id is not None:
            data.setdefault("entity_id", result.entity_id)
        return data

    def release_quarantine(self, *, quarantine_id: str) -> tuple[bool, str, dict]:
        """Libera una cuarentena abierta (§31): el stock vuelve a AVAILABLE.
        Denegado aguas abajo si el actor es quien la abrió (segregación) o no
        tiene el permiso — nunca se resuelve en la UI."""
        if self._release_quarantine_uc is None:
            return False, "Liberación de cuarentena no disponible.", {}
        qid = str(quarantine_id or "").strip()
        if not qid:
            return False, "Selecciona una cuarentena.", {}
        try:
            result = self._release_quarantine_uc.execute(
                self._conn(), quarantine_id=qid, operation_id=new_uuid(),
                actor_user_id=self._actor())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.release_quarantine failed")
            return False, "Error inesperado; revise el log.", {}

    def dispose_quarantine(self, *, quarantine_id: str,
                           reason: str = "") -> tuple[bool, str, dict]:
        """Dispone (da de baja) el stock de una cuarentena abierta (§31):
        movimiento de salida definitivo, irreversible."""
        if self._dispose_quarantine_uc is None:
            return False, "Disposición de cuarentena no disponible.", {}
        qid = str(quarantine_id or "").strip()
        if not qid:
            return False, "Selecciona una cuarentena.", {}
        try:
            result = self._dispose_quarantine_uc.execute(
                self._conn(), quarantine_id=qid, operation_id=new_uuid(),
                actor_user_id=self._actor(), reason=str(reason or "").strip())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.dispose_quarantine failed")
            return False, "Error inesperado; revise el log.", {}

    def open_quarantine(self, *, product_id: str, reason: str, quantity,
                        branch_id: str | None = None,
                        warehouse_id: str | None = None,
                        location_id: str | None = None,
                        reason_note: str = "") -> tuple[bool, str, dict]:
        """Pone stock en cuarentena (§31): AVAILABLE → QUARANTINED. El producto
        se resuelve por búsqueda canónica (§P0-D), nunca por UUID escrito a
        mano. Con ``location_id`` real (§P0-04 corolario) encuentra el saldo
        donde vive de verdad; sin él, el use case cae al almacén completo
        como ubicación implícita — sólo funciona si el stock vive ahí."""
        if self._open_quarantine_uc is None:
            return False, "Apertura de cuarentena no disponible.", {}
        pid = str(product_id or "").strip()
        if not pid:
            return False, "Selecciona un producto.", {}
        try:
            from backend.domain.inventory.enums import QuarantineReason
            reason_enum = QuarantineReason(str(reason))
        except ValueError:
            return False, "Motivo de cuarentena inválido.", {}
        branch = branch_id or self.default_branch()
        warehouse = warehouse_id or self.default_warehouse()
        loc = str(location_id or "").strip() or None
        try:
            result = self._open_quarantine_uc.execute(
                self._conn(), product_id=pid, branch_id=branch, warehouse_id=warehouse,
                reason=reason_enum, quantity=quantity, operation_id=new_uuid(),
                actor_user_id=self._actor(), location_id=loc,
                reason_note=str(reason_note or "").strip())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.open_quarantine failed")
            return False, "Error inesperado; revise el log.", {}

    def create_adjustment(self, *, product_id: str, reason: str, quantity_delta,
                          weight_delta=0, reason_note: str = "",
                          branch_id: str | None = None,
                          warehouse_id: str | None = None) -> tuple[bool, str, dict]:
        """Crea un ajuste de una sola línea (§29): cantidad con signo — positivo
        entrada, negativo salida. Queda en borrador o pendiente de aprobación
        según el límite configurado; el use case decide, no la UI."""
        if self._create_adjustment_uc is None:
            return False, "Creación de ajustes no disponible.", {}
        pid = str(product_id or "").strip()
        if not pid:
            return False, "Selecciona un producto.", {}
        try:
            from backend.domain.inventory.enums import AdjustmentReason
            reason_enum = AdjustmentReason(str(reason))
        except ValueError:
            return False, "Motivo de ajuste inválido.", {}
        if not quantity_delta and not weight_delta:
            return False, "Captura una cantidad o peso distinto de cero.", {}
        branch = branch_id or self.default_branch()
        warehouse = warehouse_id or self.default_warehouse()
        folio = f"AJ-{new_uuid()[:8].upper()}"
        try:
            result = self._create_adjustment_uc.execute(
                self._conn(), folio=folio, branch_id=branch, warehouse_id=warehouse,
                reason=reason_enum, operation_id=new_uuid(), actor_user_id=self._actor(),
                reason_note=str(reason_note or "").strip(),
                lines=[{"product_id": pid, "quantity_delta": quantity_delta,
                       "weight_delta": weight_delta}])
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            data = self._result_data(result)
            message = result.message
            if result.success and data.get("requires_approval"):
                message = f"{message} (folio {folio}) — requiere aprobación"
            elif result.success:
                message = f"{message} (folio {folio})"
            return bool(result.success), message, data
        except Exception:
            logger.exception("InventoryPresenter.create_adjustment failed")
            return False, "Error inesperado; revise el log.", {}

    def record_catch_weight(self, *, product_id: str, use_scale: bool,
                            pieces_delta=0, gross=None, tare=0, unit: str = "KG",
                            authorizer_user_id: str | None = None,
                            reason_note: str = "", location_id: str | None = None,
                            branch_id: str | None = None,
                            warehouse_id: str | None = None) -> tuple[bool, str, dict]:
        """Captura una lectura de peso (báscula o manual autorizada) y la aplica
        como un ajuste de inventario (§28/§29 "Capturar peso", "Corregir
        lectura", "Reconciliar piezas/peso") — ver ``RecordCatchWeightUseCase``
        para el porqué de reusar el mecanismo de ajustes en vez de uno nuevo."""
        if self._record_catch_weight_uc is None:
            return False, "Captura de peso no disponible.", {}
        pid = str(product_id or "").strip()
        if not pid:
            return False, "Selecciona un producto.", {}
        branch = branch_id or self.default_branch()
        warehouse = warehouse_id or self.default_warehouse()
        gateway = None
        if use_scale:
            if self._scale_gateway_factory is None:
                return False, "No hay báscula configurada.", {}
            gateway = self._scale_gateway_factory()
        try:
            result = self._record_catch_weight_uc.execute(
                self._conn(), product_id=pid, branch_id=branch, warehouse_id=warehouse,
                location_id=location_id, pieces_delta=pieces_delta, gateway=gateway,
                gross=gross, tare=tare, unit=unit,
                authorizer_user_id=str(authorizer_user_id or "").strip() or None,
                reason_note=str(reason_note or "").strip(),
                operation_id=new_uuid(), actor_user_id=self._actor())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.record_catch_weight failed")
            return False, "Error inesperado; revise el log.", {}

    def approve_adjustment(self, *, adjustment_id: str) -> tuple[bool, str, dict]:
        """Aprueba un ajuste pendiente (§29): quien lo creó no puede aprobarlo
        (segregación de funciones, resuelta aguas abajo, nunca en la UI)."""
        if self._approve_adjustment_uc is None:
            return False, "Aprobación de ajustes no disponible.", {}
        aid = str(adjustment_id or "").strip()
        if not aid:
            return False, "Selecciona un ajuste.", {}
        try:
            result = self._approve_adjustment_uc.execute(
                self._conn(), adjustment_id=aid, operation_id=new_uuid(),
                actor_user_id=self._actor())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.approve_adjustment failed")
            return False, "Error inesperado; revise el log.", {}

    def post_adjustment(self, *, adjustment_id: str) -> tuple[bool, str, dict]:
        """Postea un ajuste aprobado (§29): mueve el ledger. Un ajuste pendiente
        de aprobación es rechazado por el use case, no simulado aquí."""
        if self._post_adjustment_uc is None:
            return False, "Posteo de ajustes no disponible.", {}
        aid = str(adjustment_id or "").strip()
        if not aid:
            return False, "Selecciona un ajuste.", {}
        try:
            result = self._post_adjustment_uc.execute(
                self._conn(), adjustment_id=aid, operation_id=new_uuid(),
                actor_user_id=self._actor())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.post_adjustment failed")
            return False, "Error inesperado; revise el log.", {}

    def reverse_adjustment(self, *, adjustment_id: str,
                           reason: str = "") -> tuple[bool, str, dict]:
        """Reversa un ajuste posteado (§29): movimiento inverso, irreversible."""
        if self._reverse_adjustment_uc is None:
            return False, "Reverso de ajustes no disponible.", {}
        aid = str(adjustment_id or "").strip()
        if not aid:
            return False, "Selecciona un ajuste.", {}
        try:
            result = self._reverse_adjustment_uc.execute(
                self._conn(), adjustment_id=aid, operation_id=new_uuid(),
                actor_user_id=self._actor(), reason=str(reason or "").strip())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.reverse_adjustment failed")
            return False, "Error inesperado; revise el log.", {}

    def create_count(self, *, product_id: str, count_type: str = "CYCLE_COUNT",
                     blind: bool = True, branch_id: str | None = None,
                     warehouse_id: str | None = None) -> tuple[bool, str, dict]:
        """Inicia un conteo de una sola línea (§27): el producto se resuelve
        vía product_options, nunca un UUID tecleado a mano."""
        if self._create_count_uc is None:
            return False, "Creación de conteos no disponible.", {}
        pid = str(product_id or "").strip()
        if not pid:
            return False, "Selecciona un producto.", {}
        try:
            from backend.domain.inventory.enums import CountType
            type_enum = CountType(str(count_type))
        except ValueError:
            return False, "Tipo de conteo inválido.", {}
        branch = branch_id or self.default_branch()
        warehouse = warehouse_id or self.default_warehouse()
        folio = f"CT-{new_uuid()[:8].upper()}"
        try:
            result = self._create_count_uc.execute(
                self._conn(), folio=folio, count_type=type_enum, branch_id=branch,
                warehouse_id=warehouse, scope_lines=[{"product_id": pid}],
                operation_id=new_uuid(), actor_user_id=self._actor(), blind=blind)
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            data = self._result_data(result)
            message = result.message
            if result.success:
                message = f"{message} (folio {folio})"
            return bool(result.success), message, data
        except Exception:
            logger.exception("InventoryPresenter.create_count failed")
            return False, "Error inesperado; revise el log.", {}

    def record_count(self, *, count_id: str, counted_quantity,
                     counted_weight=0) -> tuple[bool, str, dict]:
        """Captura la cantidad contada de la única línea del conteo (§27) — el
        id de línea nunca lo ve la UI, se resuelve vía CountQueryService."""
        if self._record_count_uc is None:
            return False, "Captura de conteos no disponible.", {}
        cid = str(count_id or "").strip()
        if not cid:
            return False, "Selecciona un conteo.", {}
        if counted_quantity is None:
            return False, "Captura una cantidad contada.", {}
        if self._count_factory is None:
            return False, "Captura de conteos no disponible.", {}
        try:
            lines = self._count_factory(self._conn()).list_lines(count_id=cid)
        except Exception:
            logger.exception("InventoryPresenter.record_count failed to resolve line")
            return False, "Error inesperado; revise el log.", {}
        if not lines:
            return False, "El conteo no tiene líneas.", {}
        try:
            result = self._record_count_uc.execute(
                self._conn(), count_id=cid, line_id=lines[0]["id"],
                counted_quantity=counted_quantity, counted_weight=counted_weight,
                operation_id=new_uuid(), actor_user_id=self._actor())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.record_count failed")
            return False, "Error inesperado; revise el log.", {}

    def confirm_count(self, *, count_id: str) -> tuple[bool, str, dict]:
        """Confirma el conteo (§27): calcula varianza y bloquea la captura."""
        if self._confirm_count_uc is None:
            return False, "Confirmación de conteos no disponible.", {}
        cid = str(count_id or "").strip()
        if not cid:
            return False, "Selecciona un conteo.", {}
        try:
            result = self._confirm_count_uc.execute(
                self._conn(), count_id=cid, operation_id=new_uuid(),
                actor_user_id=self._actor())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.confirm_count failed")
            return False, "Error inesperado; revise el log.", {}

    def approve_count(self, *, count_id: str) -> tuple[bool, str, dict]:
        """Aprueba el conteo (§27): segregación real (contador != aprobador
        cuando hay varianza), aplicada por el use case, no por la UI."""
        if self._approve_count_uc is None:
            return False, "Aprobación de conteos no disponible.", {}
        cid = str(count_id or "").strip()
        if not cid:
            return False, "Selecciona un conteo.", {}
        try:
            result = self._approve_count_uc.execute(
                self._conn(), count_id=cid, operation_id=new_uuid(),
                actor_user_id=self._actor())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.approve_count failed")
            return False, "Error inesperado; revise el log.", {}

    def generate_adjustment_from_count(self, *, count_id: str) -> tuple[bool, str, dict]:
        """Cierra el ciclo (§27→§29): convierte las varianzas de un conteo
        aprobado en un ajuste real, listo para postear."""
        if self._create_adjustment_from_count_uc is None:
            return False, "Generar ajuste desde conteo no disponible.", {}
        cid = str(count_id or "").strip()
        if not cid:
            return False, "Selecciona un conteo.", {}
        folio = f"AJ-{new_uuid()[:8].upper()}"
        try:
            result = self._create_adjustment_from_count_uc.execute(
                self._conn(), count_id=cid, folio=folio, operation_id=new_uuid(),
                actor_user_id=self._actor())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            data = self._result_data(result)
            message = result.message
            if result.success and result.entity_id:
                message = f"{message} (folio {folio})"
            return bool(result.success), message, data
        except Exception:
            logger.exception("InventoryPresenter.generate_adjustment_from_count failed")
            return False, "Error inesperado; revise el log.", {}

    def create_warehouse(self, *, code: str, name: str, warehouse_type: str,
                         branch_id: str | None = None,
                         temperature_profile: str | None = None,
                         capacity=None, capacity_uom: str | None = None
                         ) -> tuple[bool, str, dict]:
        """Alta de almacén (§12): la página de Almacenes no tenía forma de
        crear uno — la única vía era el script de provisión (P0-E)."""
        if self._create_warehouse_uc is None:
            return False, "Creación de almacenes no disponible.", {}
        code_v = str(code or "").strip()
        name_v = str(name or "").strip()
        if not code_v or not name_v:
            return False, "Captura código y nombre.", {}
        try:
            from backend.domain.inventory.enums import WarehouseType
            type_enum = WarehouseType(str(warehouse_type))
        except ValueError:
            return False, "Tipo de almacén inválido.", {}
        branch = branch_id or self.default_branch()
        try:
            result = self._create_warehouse_uc.execute(
                self._conn(), code=code_v, name=name_v, branch_id=branch,
                warehouse_type=type_enum, actor_user_id=self._actor(),
                temperature_profile=str(temperature_profile or "").strip() or None,
                capacity=capacity, capacity_uom=str(capacity_uom or "").strip() or None)
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.create_warehouse failed")
            return False, "Error inesperado; revise el log.", {}

    def update_warehouse(self, *, warehouse_id: str, name: str | None = None,
                         warehouse_type: str | None = None,
                         temperature_profile: str | None = ...,
                         capacity=..., capacity_uom: str | None = ...
                         ) -> tuple[bool, str, dict]:
        """Edita un almacén existente (§24 "Editar almacén")."""
        if self._update_warehouse_uc is None:
            return False, "Edición de almacenes no disponible.", {}
        wid = str(warehouse_id or "").strip()
        if not wid:
            return False, "Selecciona un almacén.", {}
        fields: dict = {}
        if name is not None:
            fields["name"] = name
        if warehouse_type is not None:
            try:
                from backend.domain.inventory.enums import WarehouseType
                fields["warehouse_type"] = WarehouseType(str(warehouse_type))
            except ValueError:
                return False, "Tipo de almacén inválido.", {}
        if temperature_profile is not ...:
            fields["temperature_profile"] = (str(temperature_profile).strip() or None
                                             if temperature_profile is not None else None)
        if capacity is not ...:
            fields["capacity"] = capacity
        if capacity_uom is not ...:
            fields["capacity_uom"] = (str(capacity_uom).strip() or None
                                      if capacity_uom is not None else None)
        try:
            result = self._update_warehouse_uc.execute(
                self._conn(), warehouse_id=wid, actor_user_id=self._actor(), **fields)
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.update_warehouse failed")
            return False, "Error inesperado; revise el log.", {}

    def set_warehouse_status(self, *, warehouse_id: str, activate: bool,
                             reason: str = "") -> tuple[bool, str, dict]:
        if self._set_warehouse_status_uc is None:
            return False, "Cambio de estado de almacén no disponible.", {}
        wid = str(warehouse_id or "").strip()
        if not wid:
            return False, "Selecciona un almacén.", {}
        try:
            result = self._set_warehouse_status_uc.execute(
                self._conn(), warehouse_id=wid, activate=bool(activate),
                actor_user_id=self._actor(), reason=str(reason or "").strip())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.set_warehouse_status failed")
            return False, "Error inesperado; revise el log.", {}

    def deactivate_warehouse(self, *, warehouse_id: str,
                             reason: str = "") -> tuple[bool, str, dict]:
        """Retira un almacén de servicio (§24 "Desactivar almacén")."""
        if self._deactivate_warehouse_uc is None:
            return False, "Desactivación de almacenes no disponible.", {}
        wid = str(warehouse_id or "").strip()
        if not wid:
            return False, "Selecciona un almacén.", {}
        try:
            result = self._deactivate_warehouse_uc.execute(
                self._conn(), warehouse_id=wid, actor_user_id=self._actor(),
                reason=str(reason or "").strip())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.deactivate_warehouse failed")
            return False, "Error inesperado; revise el log.", {}

    def create_zone(self, *, warehouse_id: str, code: str, name: str,
                    zone_type: str) -> tuple[bool, str, dict]:
        """Alta de zona (§24 "Zonas") — el backend ya existía (`CreateZoneUseCase`)
        sin ningún camino de UI hasta ahora."""
        if self._create_zone_uc is None:
            return False, "Creación de zonas no disponible.", {}
        wid = str(warehouse_id or "").strip()
        if not wid:
            return False, "Selecciona un almacén.", {}
        code_v = str(code or "").strip()
        name_v = str(name or "").strip()
        if not code_v or not name_v:
            return False, "Captura código y nombre.", {}
        try:
            from backend.domain.inventory.enums import WarehouseZoneType
            type_enum = WarehouseZoneType(str(zone_type))
        except ValueError:
            return False, "Tipo de zona inválido.", {}
        try:
            result = self._create_zone_uc.execute(
                self._conn(), warehouse_id=wid, code=code_v, name=name_v,
                zone_type=type_enum, actor_user_id=self._actor())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.create_zone failed")
            return False, "Error inesperado; revise el log.", {}

    def create_location(self, *, warehouse_id: str, code: str, name: str,
                        level: int = 0,
                        parent_location_id: str | None = None,
                        capacity=None) -> tuple[bool, str, dict]:
        """Alta de ubicación (§12), opcionalmente como sub-ubicación de otra
        (jerarquía pasillo → rack → nivel → posición)."""
        if self._create_location_uc is None:
            return False, "Creación de ubicaciones no disponible.", {}
        wid = str(warehouse_id or "").strip()
        if not wid:
            return False, "Selecciona un almacén.", {}
        code_v = str(code or "").strip()
        name_v = str(name or "").strip()
        if not code_v or not name_v:
            return False, "Captura código y nombre.", {}
        try:
            result = self._create_location_uc.execute(
                self._conn(), warehouse_id=wid, code=code_v, name=name_v,
                level=int(level or 0),
                parent_location_id=str(parent_location_id or "").strip() or None,
                capacity=capacity, actor_user_id=self._actor())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.create_location failed")
            return False, "Error inesperado; revise el log.", {}

    def update_location(self, *, location_id: str, name: str | None = None,
                        capacity=...) -> tuple[bool, str, dict]:
        """Edita una ubicación existente (§24 "Editar ubicación")."""
        if self._update_location_uc is None:
            return False, "Edición de ubicaciones no disponible.", {}
        lid = str(location_id or "").strip()
        if not lid:
            return False, "Selecciona una ubicación.", {}
        fields: dict = {}
        if name is not None:
            fields["name"] = name
        if capacity is not ...:
            fields["capacity"] = capacity
        try:
            result = self._update_location_uc.execute(
                self._conn(), location_id=lid, actor_user_id=self._actor(), **fields)
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.update_location failed")
            return False, "Error inesperado; revise el log.", {}

    def set_location_status(self, *, location_id: str, activate: bool,
                            reason: str = "") -> tuple[bool, str, dict]:
        if self._set_location_status_uc is None:
            return False, "Cambio de estado de ubicación no disponible.", {}
        lid = str(location_id or "").strip()
        if not lid:
            return False, "Selecciona una ubicación.", {}
        try:
            result = self._set_location_status_uc.execute(
                self._conn(), location_id=lid, activate=bool(activate),
                actor_user_id=self._actor(), reason=str(reason or "").strip())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.set_location_status failed")
            return False, "Error inesperado; revise el log.", {}

    def deactivate_location(self, *, location_id: str,
                            reason: str = "") -> tuple[bool, str, dict]:
        """Retira una ubicación de servicio (§24 "Desactivar ubicación")."""
        if self._deactivate_location_uc is None:
            return False, "Desactivación de ubicaciones no disponible.", {}
        lid = str(location_id or "").strip()
        if not lid:
            return False, "Selecciona una ubicación.", {}
        try:
            result = self._deactivate_location_uc.execute(
                self._conn(), location_id=lid, actor_user_id=self._actor(),
                reason=str(reason or "").strip())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.deactivate_location failed")
            return False, "Error inesperado; revise el log.", {}
