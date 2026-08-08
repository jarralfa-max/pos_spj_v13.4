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
from frontend.desktop.modules.inventory.view_models import (
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
                 create_location_uc=None, set_location_status_uc=None,
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
        self._create_location_uc = create_location_uc
        self._set_location_status_uc = set_location_status_uc
        self._session = session_context
        self._dispatch = event_dispatcher

    # session -----------------------------------------------------------------
    # §5.4 fail-closed: la identidad y el ámbito NO se fabrican ("desktop"/"MAIN",
    # ni warehouse_id = branch_id). Sin sesión válida quedan vacíos: las lecturas
    # devuelven vacío y las mutaciones se niegan aguas abajo (la política real exige
    # usuario y el checker deniega sin identidad).
    def _actor(self) -> str:
        return str(getattr(self._session, "user_id", None) or "")

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
        return availability_table(rows)

    def stock(self, *, branch_id: str | None = None) -> TableViewModel:
        """Existencias físicas por producto/almacén/bucket (cantidad ≠ 0). Sólo
        lectura; delega en el stock query service."""
        if self._stock_factory is None:
            return stock_table([])
        branch = branch_id or self.default_branch()
        rows = self._stock_factory(self._conn()).list_on_hand(branch_id=branch or None)
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
        return weight_table(rows)

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

    def expiring(self, *, branch_id: str | None = None) -> TableViewModel:
        """Lotes disponibles en riesgo de caducidad (vencido/crítico/próximo),
        próximos a vencer primero. Sólo lectura; delega en el expiry query service
        (clasifica, no emite eventos ni mueve stock)."""
        if self._expiry_factory is None:
            return expiry_table([])
        branch = branch_id or self.default_branch()
        rows = self._expiry_factory(self._conn()).list_at_risk(branch_id=branch or None)
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
        return replenishment_table(svc.list_open_suggestions(branch_id=branch))

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

    def location_tree(self, *, warehouse_id: str) -> TableViewModel:
        svc = self._warehouse_factory(self._conn())
        return locations_table(svc.location_hierarchy(warehouse_id=warehouse_id))

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
                         branch_id: str | None = None) -> tuple[bool, str, dict]:
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
                warehouse_type=type_enum, actor_user_id=self._actor())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.create_warehouse failed")
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

    def create_location(self, *, warehouse_id: str, code: str, name: str,
                        level: int = 0,
                        parent_location_id: str | None = None) -> tuple[bool, str, dict]:
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
                actor_user_id=self._actor())
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, self._result_data(result)
        except Exception:
            logger.exception("InventoryPresenter.create_location failed")
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
