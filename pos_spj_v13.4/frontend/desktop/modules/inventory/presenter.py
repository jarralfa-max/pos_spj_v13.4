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
        return str(getattr(self._session, "branch_id", None) or "")

    def default_warehouse(self) -> str:
        return str(getattr(self._session, "warehouse_id", None) or "")

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

    def alerts(self, *, branch_id: str | None = None) -> TableViewModel:
        """Alertas recientes de inventario (fecha, severidad, evento, canal, estado,
        mensaje). Sólo lectura; delega en el alert query service."""
        if self._alert_factory is None:
            return alerts_table([])
        branch = branch_id or self.default_branch()
        rows = self._alert_factory(self._conn()).list_recent(branch_id=branch or None)
        return alerts_table(rows)

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
            return bool(result.success), result.message, dict(result.data)
        except Exception:
            logger.exception("InventoryPresenter.generate_suggestions failed")
            return False, "Error inesperado; revise el log.", {}
