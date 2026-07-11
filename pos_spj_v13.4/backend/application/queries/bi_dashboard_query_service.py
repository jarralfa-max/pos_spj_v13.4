"""Aggregator BI query service.

Composes the sales/inventory/finance/forecast query services and returns a raw
metric bundle (current + previous period) that the BiDashboardService turns into
the structured dashboard payload. SQL stays in the underlying query services.
"""
from __future__ import annotations

from dataclasses import replace

from backend.application.queries.bi_sales_query_service import BiSalesQueryService
from backend.application.queries.bi_inventory_query_service import BiInventoryQueryService
from backend.application.queries.bi_finance_query_service import BiFinanceQueryService
from backend.application.queries.bi_forecast_query_service import BiForecastQueryService


class BiDashboardQueryService:
    def __init__(self, conn):
        self.sales = BiSalesQueryService(conn)
        self.inventory = BiInventoryQueryService(conn)
        self.finance = BiFinanceQueryService(conn)
        self.forecast = BiForecastQueryService(conn)

    def core_metrics(self, f) -> dict:
        """Métricas escalares base para KPIs (un solo periodo)."""
        totals = self.sales.sales_totals(f)
        cogs = self.sales.cost_of_goods(f)
        expenses = self.finance.expenses(f)
        inv_val = self.inventory.inventory_valued(f)
        waste = self.inventory.waste_value(f)
        ventas = totals["ventas_netas"]
        utilidad = ventas - cogs - expenses
        return {
            "ventas_netas": ventas,
            "ordenes": totals["ordenes"],
            "ticket_promedio": totals["ticket_promedio"],
            "costo_ventas": cogs,
            "gastos": expenses,
            "utilidad_neta": utilidad,
            "margen_pct": (utilidad / ventas * 100) if ventas else 0.0,
            "inventario_valorizado": inv_val,
            "cxc": self.finance.accounts_receivable_total(f),
            "cxp": self.finance.accounts_payable_total(f),
            "merma_valor": waste,
            "merma_pct": (waste / ventas * 100) if ventas else 0.0,
            # Rotación = COGS del periodo / inventario valorizado
            "rotacion": (cogs / inv_val) if inv_val else 0.0,
            "compras": self.finance.purchases_total(f),
        }

    def previous_metrics(self, f) -> dict:
        pf, pt = f.previous_period()
        prev = replace(f, preset="custom", date_from=pf, date_to=pt)
        return self.core_metrics(prev)

    def filter_options(self) -> dict:
        """Catálogos para poblar los filtros globales (sin SQL en la UI)."""
        def _q(sql):
            try:
                return self.sales._conn.execute(sql).fetchall()
            except Exception:
                return []
        branches = [{"id": str(r[0]), "nombre": r[1]} for r in _q(
            "SELECT id, nombre FROM sucursales WHERE COALESCE(activa,1)=1 ORDER BY nombre")]
        categories = [r[0] for r in _q(
            "SELECT DISTINCT categoria FROM productos "
            "WHERE COALESCE(categoria,'')<>'' ORDER BY categoria")]
        payments = [r[0] for r in _q(
            "SELECT DISTINCT forma_pago FROM ventas "
            "WHERE COALESCE(forma_pago,'')<>'' ORDER BY forma_pago")]
        return {"branches": branches, "categories": categories,
                "payment_methods": payments}

    def chart_bundle(self, f) -> dict:
        """Series para los charts del dashboard."""
        return {
            "monthly": self.sales.monthly_evolution(),
            "by_branch": self.sales.by_branch(f),
            "top_products": self.sales.top_products(f, limit=10),
            "by_category": self.sales.by_category(f),
            "payment_methods": self.sales.payment_methods(f),
            "peak_hours": self.sales.peak_hours(f),
            "profitability": self.sales.profitability_by_category(f),
            "forecast": self.forecast.forecast_series(f),
        }
