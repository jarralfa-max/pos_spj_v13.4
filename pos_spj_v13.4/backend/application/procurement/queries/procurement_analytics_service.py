"""Procurement analytics query service (PUR-12).

Produces KPI figures and color-free ChartDataDTOs from the procurement tables.
No colors/HTML/JS here — the theme/renderer owns presentation. Tolerates missing
tables (returns zeros / empty charts) so the dashboard degrades gracefully.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.application.dto.charts.chart_data import (
    ChartDataDTO,
    ChartType,
    series_from,
)


@dataclass(frozen=True)
class ProcurementKpisDTO:
    open_requisitions: int
    pending_order_approvals: int
    orders_in_progress: int
    receipts_completed: int
    invoices_with_differences: int
    direct_purchases_today: int
    committed_spend: str


def _dec(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


class ProcurementAnalyticsService:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    # helpers -----------------------------------------------------------------
    def _rows(self, sql: str, params: tuple = ()) -> list[tuple]:
        try:
            return self._conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []

    def _scalar(self, sql: str, params: tuple = (), default=0):
        rows = self._rows(sql, params)
        return rows[0][0] if rows and rows[0][0] is not None else default

    # KPIs --------------------------------------------------------------------
    def kpis(self) -> ProcurementKpisDTO:
        committed = Decimal("0")
        for (total,) in self._rows(
                "SELECT total FROM purchase_orders WHERE status IN"
                " ('APPROVED','SENT','ACKNOWLEDGED','PARTIALLY_RECEIVED')"):
            committed += _dec(total)
        return ProcurementKpisDTO(
            open_requisitions=int(self._scalar(
                "SELECT COUNT(*) FROM purchase_requisitions WHERE status IN"
                " ('DRAFT','PENDING_APPROVAL','APPROVED')")),
            pending_order_approvals=int(self._scalar(
                "SELECT COUNT(*) FROM purchase_orders WHERE status='PENDING_APPROVAL'")),
            orders_in_progress=int(self._scalar(
                "SELECT COUNT(*) FROM purchase_orders WHERE status IN"
                " ('SENT','ACKNOWLEDGED','PARTIALLY_RECEIVED')")),
            receipts_completed=int(self._scalar(
                "SELECT COUNT(*) FROM goods_receipts WHERE status='COMPLETED'")),
            invoices_with_differences=int(self._scalar(
                "SELECT COUNT(*) FROM supplier_invoices WHERE status='WITH_DIFFERENCES'")),
            direct_purchases_today=int(self._scalar(
                "SELECT COUNT(*) FROM direct_purchases WHERE substr(created_at,1,10)=?",
                (datetime.now(timezone.utc).date().isoformat(),))),
            committed_spend=str(committed.quantize(Decimal("0.01"))))

    # charts ------------------------------------------------------------------
    def orders_by_status_chart(self) -> ChartDataDTO:
        rows = self._rows(
            "SELECT status, COUNT(*) FROM purchase_orders GROUP BY status ORDER BY status")
        if not rows:
            return ChartDataDTO.empty("po_status", ChartType.DONUT, "Órdenes por estado")
        categories = tuple(_status_es(r[0]) for r in rows)
        values = tuple(float(r[1]) for r in rows)
        return ChartDataDTO(
            chart_id="po_status", chart_type=ChartType.DONUT, title="Órdenes por estado",
            subtitle="Distribución de órdenes de compra", categories=categories,
            series=(series_from("Órdenes", values),),
            accessibility_summary="Conteo de órdenes de compra agrupadas por estado.")

    def spend_by_supplier_chart(self, *, top: int = 8) -> ChartDataDTO:
        totals: dict[str, Decimal] = {}
        for supplier_id, total in self._rows(
                "SELECT supplier_id, total FROM purchase_orders WHERE status IN"
                " ('APPROVED','SENT','ACKNOWLEDGED','PARTIALLY_RECEIVED','RECEIVED')"):
            totals[supplier_id] = totals.get(supplier_id, Decimal("0")) + _dec(total)
        if not totals:
            return ChartDataDTO.empty("spend_supplier", ChartType.HORIZONTAL_BAR,
                                      "Gasto por proveedor")
        ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:top]
        categories = tuple((sid or "—")[:8] for sid, _ in ranked)
        values = tuple(float(v) for _, v in ranked)
        return ChartDataDTO(
            chart_id="spend_supplier", chart_type=ChartType.HORIZONTAL_BAR,
            title="Gasto por proveedor", subtitle="Órdenes comprometidas/recibidas",
            categories=categories, series=(series_from("Gasto", values),),
            currency_code="MXN",
            accessibility_summary="Gasto de compra acumulado por proveedor (top).")

    def receipts_vs_discrepancies_chart(self) -> ChartDataDTO:
        completed = float(self._scalar(
            "SELECT COUNT(*) FROM goods_receipts WHERE status='COMPLETED'"))
        with_disc = float(self._scalar(
            "SELECT COUNT(DISTINCT goods_receipt_id) FROM receipt_discrepancies"))
        if completed == 0 and with_disc == 0:
            return ChartDataDTO.empty("receipts_disc", ChartType.BAR,
                                      "Recepciones y discrepancias")
        return ChartDataDTO(
            chart_id="receipts_disc", chart_type=ChartType.BAR,
            title="Recepciones y discrepancias", subtitle="Calidad de la recepción",
            categories=("Completadas", "Con discrepancia"),
            series=(series_from("Recepciones", (completed, with_disc)),),
            accessibility_summary="Recepciones completadas frente a las que tuvieron"
            " alguna discrepancia registrada.")

    def all_charts(self) -> list[ChartDataDTO]:
        return [self.orders_by_status_chart(), self.spend_by_supplier_chart(),
                self.receipts_vs_discrepancies_chart()]


def _status_es(code: str) -> str:
    return {
        "DRAFT": "Borrador", "PENDING_APPROVAL": "Pendiente", "APPROVED": "Aprobada",
        "SENT": "Enviada", "ACKNOWLEDGED": "Confirmada",
        "PARTIALLY_RECEIVED": "Recibida parcial", "RECEIVED": "Recibida",
        "INVOICED": "Facturada", "CLOSED": "Cerrada", "CANCELLED": "Cancelada",
    }.get(str(code or ""), str(code or "—"))
