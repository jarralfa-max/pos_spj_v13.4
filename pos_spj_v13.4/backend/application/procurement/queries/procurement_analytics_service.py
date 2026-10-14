"""Procurement analytics query service (PUR-12).

Produces KPI figures and color-free ChartDataDTOs from the procurement tables.
No colors/HTML/JS here — the theme/renderer owns presentation.

Auditoría Compras d9f2bca:
- C24: toda cifra recibe el MISMO alcance que las listas — sucursal, periodo
  (fecha local del documento) y moneda. Antes sumaba toda la empresa y todo el
  historial aunque la cabecera mostrara una sucursal y un periodo.
- C27: una tabla requerida ausente es un ERROR, no un cero: ``OperationalError``
  se propaga y la pantalla muestra su estado de error en vez de una cifra
  operativa aparentemente válida.
"""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class ProcurementAlertDTO:
    code: str
    message: str
    severity: str
    count: int


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
        return self._conn.execute(sql, params).fetchall()

    def _scalar(self, sql: str, params: tuple = (), default=0):
        rows = self._rows(sql, params)
        return rows[0][0] if rows and rows[0][0] is not None else default

    @staticmethod
    def _where(scope: dict, *, date_column: str = "created_at", branch_column="branch_id",
               currency: bool = False) -> tuple[str, tuple]:
        """Condiciones del alcance (C24). ``scope``: branch_id, start_date,
        end_date, currency_code — todas opcionales."""
        clauses: list[str] = []
        params: list = []
        if scope.get("branch_id") and branch_column:
            clauses.append(f"{branch_column}=?")
            params.append(scope["branch_id"])
        if scope.get("start_date"):
            clauses.append(f"date({date_column},'localtime')>=?")
            params.append(str(scope["start_date"])[:10])
        if scope.get("end_date"):
            clauses.append(f"date({date_column},'localtime')<=?")
            params.append(str(scope["end_date"])[:10])
        if currency:
            clauses.append("currency_code=?")
            params.append(scope.get("currency_code") or "MXN")
        return ("".join(f" AND {c}" for c in clauses), tuple(params))

    # KPIs --------------------------------------------------------------------
    def kpis(self, **scope) -> ProcurementKpisDTO:
        po_where, po_params = self._where(scope)
        spend_where, spend_params = self._where(scope, currency=True)
        committed = Decimal("0")
        for (total,) in self._rows(
                "SELECT total FROM purchase_orders WHERE status IN"
                " ('APPROVED','SENT','ACKNOWLEDGED','PARTIALLY_RECEIVED')" + spend_where,
                spend_params):
            committed += _dec(total)
        req_where, req_params = self._where(scope)
        rec_where, rec_params = self._where(scope)
        # Facturas: su sucursal es la de su documento de compra.
        inv_where, inv_params = self._where(
            scope, date_column="i.created_at",
            branch_column="COALESCE(po.branch_id, dp.branch_id)")
        direct_today = dict(scope, start_date=None, end_date=None)
        dp_where, dp_params = self._where(direct_today)
        return ProcurementKpisDTO(
            open_requisitions=int(self._scalar(
                "SELECT COUNT(*) FROM purchase_requisitions WHERE status IN"
                " ('DRAFT','PENDING_APPROVAL','APPROVED')" + req_where, req_params)),
            pending_order_approvals=int(self._scalar(
                "SELECT COUNT(*) FROM purchase_orders WHERE status='PENDING_APPROVAL'"
                + po_where, po_params)),
            orders_in_progress=int(self._scalar(
                "SELECT COUNT(*) FROM purchase_orders WHERE status IN"
                " ('SENT','ACKNOWLEDGED','PARTIALLY_RECEIVED')" + po_where, po_params)),
            receipts_completed=int(self._scalar(
                "SELECT COUNT(*) FROM goods_receipts WHERE status='COMPLETED'" + rec_where,
                rec_params)),
            invoices_with_differences=int(self._scalar(
                "SELECT COUNT(*) FROM supplier_invoices i"
                " LEFT JOIN purchase_orders po ON po.id = i.purchase_order_id"
                " LEFT JOIN direct_purchases dp ON dp.id = i.direct_purchase_id"
                " WHERE i.status='WITH_DIFFERENCES'" + inv_where, inv_params)),
            direct_purchases_today=int(self._scalar(
                # «Hoy» es el día LOCAL del negocio, no el de UTC.
                "SELECT COUNT(*) FROM direct_purchases"
                " WHERE date(created_at,'localtime')=date('now','localtime')" + dp_where,
                dp_params)),
            committed_spend=str(committed.quantize(Decimal("0.01"))))

    def alerts(self, **scope) -> tuple[ProcurementAlertDTO, ...]:
        """Return actionable operational alerts; presentation never derives counts."""
        po_where, po_params = self._where(scope)
        inv_where, inv_params = self._where(
            scope, date_column="i.created_at",
            branch_column="COALESCE(po.branch_id, dp.branch_id)")
        candidates = (
            ProcurementAlertDTO(
                "PENDING_APPROVAL", "Órdenes esperando autorización", "warning",
                int(self._scalar("SELECT COUNT(*) FROM purchase_orders"
                                 " WHERE status='PENDING_APPROVAL'" + po_where, po_params))),
            ProcurementAlertDTO(
                "INVOICE_DIFFERENCE", "Facturas bloqueadas por diferencias", "danger",
                int(self._scalar("SELECT COUNT(*) FROM supplier_invoices i"
                                 " LEFT JOIN purchase_orders po ON po.id = i.purchase_order_id"
                                 " LEFT JOIN direct_purchases dp ON dp.id = i.direct_purchase_id"
                                 " WHERE i.status IN ('WITH_DIFFERENCES','BLOCKED')"
                                 + inv_where, inv_params))),
            ProcurementAlertDTO(
                "OVERDUE_ORDER", "Órdenes enviadas sin recepción completa", "info",
                int(self._scalar("SELECT COUNT(*) FROM purchase_orders"
                                 " WHERE status IN ('SENT','ACKNOWLEDGED','PARTIALLY_RECEIVED')"
                                 + po_where, po_params))),
        )
        return tuple(alert for alert in candidates if alert.count)

    # charts ------------------------------------------------------------------
    def orders_by_status_chart(self, **scope) -> ChartDataDTO:
        where, params = self._where(scope)
        rows = self._rows(
            "SELECT status, COUNT(*) FROM purchase_orders WHERE 1=1" + where
            + " GROUP BY status ORDER BY status", params)
        if not rows:
            return ChartDataDTO.empty("po_status", ChartType.DONUT, "Órdenes por estado")
        categories = tuple(_status_es(r[0]) for r in rows)
        values = tuple(float(r[1]) for r in rows)
        return ChartDataDTO(
            chart_id="po_status", chart_type=ChartType.DONUT, title="Órdenes por estado",
            subtitle="Distribución de órdenes de compra", categories=categories,
            series=(series_from("Órdenes", values),),
            accessibility_summary="Conteo de órdenes de compra agrupadas por estado.")

    def spend_by_supplier_chart(self, *, top: int = 8, **scope) -> ChartDataDTO:
        where, params = self._where(scope, currency=True)
        totals: dict[str, Decimal] = {}
        for supplier_id, total in self._rows(
                "SELECT supplier_id, total FROM purchase_orders WHERE status IN"
                " ('APPROVED','SENT','ACKNOWLEDGED','PARTIALLY_RECEIVED','RECEIVED')" + where,
                params):
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
            currency_code=scope.get("currency_code") or "MXN",
            accessibility_summary="Gasto de compra acumulado por proveedor (top).")

    def receipts_vs_discrepancies_chart(self, **scope) -> ChartDataDTO:
        where, params = self._where(scope, date_column="g.created_at",
                                    branch_column="g.branch_id")
        completed = float(self._scalar(
            "SELECT COUNT(*) FROM goods_receipts g WHERE g.status='COMPLETED'" + where, params))
        with_disc = float(self._scalar(
            "SELECT COUNT(DISTINCT d.goods_receipt_id) FROM receipt_discrepancies d"
            " JOIN goods_receipts g ON g.id = d.goods_receipt_id WHERE 1=1" + where, params))
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

    def all_charts(self, **scope) -> list[ChartDataDTO]:
        return [self.orders_by_status_chart(**scope), self.spend_by_supplier_chart(**scope),
                self.receipts_vs_discrepancies_chart(**scope)]


#: Debe coincidir con `ORDER_STATUS_ES` de la UI (una prueba lo exige): la
#: gráfica y la lista nombran igual el mismo estado.
ORDER_STATUS_LABELS = {
    "DRAFT": "Borrador", "PENDING_APPROVAL": "Pendiente de aprobación",
    "APPROVED": "Aprobada", "SENT": "Enviada", "ACKNOWLEDGED": "Confirmada por proveedor",
    "PARTIALLY_RECEIVED": "Recibida parcialmente", "RECEIVED": "Recibida",
    "INVOICED": "Facturada", "CLOSED": "Cerrada", "CANCELLED": "Cancelada",
}


def _status_es(code: str) -> str:
    value = str(code or "")
    return ORDER_STATUS_LABELS.get(value) or (value.replace("_", " ").capitalize() or "—")
