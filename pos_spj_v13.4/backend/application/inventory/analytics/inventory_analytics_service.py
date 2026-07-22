"""InventoryAnalyticsService — read-only BI over the canonical inventory (§55).

Produces KPI DTOs, color-free ChartDataDTOs, a data-freshness signal and an
export dataset from the canonical projection/ledger. Decimal throughout in the
domain math; the only Decimal→float crossing is ``to_chart_number`` (the chart
display boundary, outside this bounded context). Never writes.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from backend.application.dto.charts.chart_data import (
    ChartDataDTO,
    ChartType,
    DataFreshnessDTO,
    FreshnessState,
    series_from,
)
from backend.application.dto.charts.chart_numbers import to_chart_number
from backend.domain.inventory.enums import InventoryStatus
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    to_decimal,
)


@dataclass(frozen=True, slots=True)
class InventoryKpiDTO:
    key: str
    title: str
    value: str            # display string; math is Decimal/int, never float
    unit: str | None = None
    variant: str = "neutral"
    tooltip: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InventoryAnalyticsService(InventoryRepositoryBase):
    # ── KPIs ─────────────────────────────────────────────────────────────────
    def kpis(self, *, branch_id: str) -> list[InventoryKpiDTO]:
        by_status = self._quantity_by_status(branch_id)
        available = by_status.get(InventoryStatus.AVAILABLE.value, Decimal("0"))
        reserved = Decimal("0")
        for r in self._query(
                "SELECT reserved_quantity FROM inventory_balances WHERE branch_id=?"
                " AND inventory_status='AVAILABLE'", (branch_id,)):
            reserved += to_decimal(r["reserved_quantity"])
        quarantined = by_status.get(InventoryStatus.QUARANTINED.value, Decimal("0"))
        open_suggestions = self._scalar(
            "SELECT COUNT(*) FROM inventory_replenishment_suggestion"
            " WHERE branch_id=? AND status='OPEN'", (branch_id,), default=0)
        critical = self._scalar(
            "SELECT COUNT(*) FROM inventory_replenishment_suggestion"
            " WHERE branch_id=? AND status='OPEN' AND urgency IN ('CRITICAL','STOCKOUT')",
            (branch_id,), default=0)
        return [
            InventoryKpiDTO(key="available", title="Disponible", value=str(available),
                            variant="info", tooltip="Existencia disponible (on-hand − reservado)."),
            InventoryKpiDTO(key="reserved", title="Reservado",
                            value=str(reserved), variant="neutral"),
            InventoryKpiDTO(key="quarantined", title="En cuarentena",
                            value=str(quarantined),
                            variant="warning" if quarantined > 0 else "neutral"),
            InventoryKpiDTO(key="open_suggestions", title="Reposición abierta",
                            value=str(open_suggestions), variant="info"),
            InventoryKpiDTO(key="critical", title="Reposición crítica",
                            value=str(critical),
                            variant="danger" if critical else "success"),
        ]

    # ── charts ─────────────────────────────────────────────────────────────
    def stock_by_status_chart(self, *, branch_id: str) -> ChartDataDTO:
        data = self._quantity_by_status(branch_id)
        if not data:
            return ChartDataDTO.empty("inv_stock_status", ChartType.DONUT,
                                      "Existencia por estado")
        categories = tuple(data.keys())
        series = series_from("Cantidad", [to_chart_number(v) for v in data.values()])
        return ChartDataDTO(
            chart_id="inv_stock_status", chart_type=ChartType.DONUT,
            title="Existencia por estado", subtitle="Distribución del inventario",
            categories=categories, series=(series,), generated_at=_now(),
            freshness_state=FreshnessState.LIVE)

    def stock_by_warehouse_chart(self, *, branch_id: str) -> ChartDataDTO:
        rows = self._query(
            "SELECT warehouse_id, COALESCE(SUM(CAST(quantity AS REAL)),0) AS q"
            " FROM inventory_balances WHERE branch_id=? AND inventory_status='AVAILABLE'"
            " GROUP BY warehouse_id ORDER BY q DESC", (branch_id,))
        if not rows:
            return ChartDataDTO.empty("inv_stock_wh", ChartType.BAR,
                                      "Disponible por almacén")
        categories = tuple(str(r["warehouse_id"]) for r in rows)
        series = series_from("Disponible", [to_chart_number(r["q"]) for r in rows])
        return ChartDataDTO(
            chart_id="inv_stock_wh", chart_type=ChartType.BAR,
            title="Disponible por almacén", subtitle=None, categories=categories,
            series=(series,), generated_at=_now(), freshness_state=FreshnessState.LIVE)

    def movements_by_type_chart(self, *, branch_id: str) -> ChartDataDTO:
        rows = self._query(
            "SELECT movement_type, COUNT(*) AS n FROM inventory_ledger"
            " WHERE branch_id=? GROUP BY movement_type ORDER BY n DESC", (branch_id,))
        if not rows:
            return ChartDataDTO.empty("inv_moves", ChartType.HORIZONTAL_BAR,
                                      "Movimientos por tipo")
        categories = tuple(str(r["movement_type"]) for r in rows)
        series = series_from("Movimientos", [to_chart_number(r["n"]) for r in rows])
        return ChartDataDTO(
            chart_id="inv_moves", chart_type=ChartType.HORIZONTAL_BAR,
            title="Movimientos por tipo", subtitle=None, categories=categories,
            series=(series,), generated_at=_now(), freshness_state=FreshnessState.LIVE)

    def waste_by_type_chart(self, *, branch_id: str) -> ChartDataDTO:
        rows = self._query(
            "SELECT waste_type, COALESCE(SUM(CAST(quantity AS REAL)),0) AS q"
            " FROM inventory_waste_event WHERE branch_id=? GROUP BY waste_type"
            " ORDER BY q DESC", (branch_id,))
        if not rows:
            return ChartDataDTO.empty("inv_waste", ChartType.BAR, "Merma por tipo")
        categories = tuple(str(r["waste_type"]) for r in rows)
        series = series_from("Merma", [to_chart_number(r["q"]) for r in rows],
                             semantic="danger")
        return ChartDataDTO(
            chart_id="inv_waste", chart_type=ChartType.BAR, title="Merma por tipo",
            subtitle=None, categories=categories, series=(series,), generated_at=_now(),
            freshness_state=FreshnessState.LIVE)

    # ── freshness ────────────────────────────────────────────────────────────
    def freshness(self, *, branch_id: str) -> DataFreshnessDTO:
        last = self._scalar(
            "SELECT MAX(occurred_at) FROM inventory_ledger WHERE branch_id=?",
            (branch_id,))
        now = _now()
        if last is None:
            return DataFreshnessDTO(generated_at=now, state=FreshnessState.UNKNOWN)
        last_dt = datetime.fromisoformat(last)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        delay = int((now - last_dt).total_seconds())
        state = (FreshnessState.LIVE if delay < 300
                 else FreshnessState.FRESH if delay < 3600
                 else FreshnessState.DELAYED if delay < 86400
                 else FreshnessState.STALE)
        return DataFreshnessDTO(generated_at=now, last_source_event_at=last_dt,
                                state=state, delay_seconds=delay)

    # ── export ───────────────────────────────────────────────────────────────
    def export_availability_rows(self, *, branch_id: str) -> list[dict]:
        return self._query(
            "SELECT product_id, warehouse_id, inventory_status, quantity, weight,"
            " reserved_quantity FROM inventory_balances WHERE branch_id=?"
            " ORDER BY product_id, warehouse_id, inventory_status", (branch_id,))

    def export_availability_csv(self, *, branch_id: str) -> str:
        rows = self.export_availability_rows(branch_id=branch_id)
        buffer = io.StringIO()
        fieldnames = ["product_id", "warehouse_id", "inventory_status", "quantity",
                      "weight", "reserved_quantity"]
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
        return buffer.getvalue()

    # ── internals ────────────────────────────────────────────────────────────
    def _quantity_by_status(self, branch_id: str) -> dict[str, Decimal]:
        rows = self._query(
            "SELECT inventory_status, quantity FROM inventory_balances WHERE branch_id=?",
            (branch_id,))
        out: dict[str, Decimal] = {}
        for r in rows:
            status = r["inventory_status"]
            out[status] = out.get(status, Decimal("0")) + to_decimal(r["quantity"])
        return {k: v for k, v in out.items() if v != 0}
