"""BiDashboardService — orchestrates the executive BI dashboard payload.

Responsibilities:
  · resolve filters (dates, branch, etc.);
  · compute the 10 KPI cards (with documented formulas and period comparison);
  · assemble charts, highlights, alerts, insights and predictions;
  · gate sections by permission;
  · cache payloads per (filters) during the session.

No SQL here — all data comes from injected query services. UI/API consume the
returned DashboardPayload (Spanish user-facing strings, UUIDv7 identity).
"""
from __future__ import annotations

import time

from backend.application.dto.bi_dashboard_dto import (
    Alert, ChartData, DashboardFilters, DashboardPayload, HighlightCard,
    Insight, KpiCard, Prediction, make_kpi,
)

_BLUE, _GOLD, _GREEN = "#3b82f6", "#eab308", "#22c55e"

# Todas las secciones (pestañas) del módulo BI.
ALL_SECTIONS = (
    "resumen", "ventas", "inventario", "compras", "caja", "clientes",
    "proveedores", "finanzas", "merma", "reportes", "configuracion",
)
# Permiso requerido por sección (código canónico MODULE.action del catálogo).
# "resumen" siempre visible. El permission_checker normaliza (upper) al comparar.
_BI = "INTELIGENCIA_BI"
SECTION_PERMISSION = {
    "ventas": f"{_BI}.ver_ventas",
    "inventario": f"{_BI}.ver_inventario",
    "compras": f"{_BI}.ver_compras",
    "caja": f"{_BI}.ver_caja",
    "clientes": f"{_BI}.ver_clientes",
    "proveedores": f"{_BI}.ver_proveedores",
    "finanzas": f"{_BI}.ver_finanzas",
    "merma": f"{_BI}.ver_merma",
    "reportes": f"{_BI}.exportar",
    "configuracion": f"{_BI}.configurar",
}


class BiDashboardService:
    def __init__(self, query_service, permission_checker=None, cache_ttl: int = 60,
                 settings=None):
        """query_service: BiDashboardQueryService.
        permission_checker: callable(permission_key) -> bool (optional).
        settings: BiSettingsService (optional); defaults used if None.
        """
        self._q = query_service
        self._can = permission_checker or (lambda perm: True)
        self._ttl = cache_ttl
        self._cache: dict = {}
        self._cache_ts: dict = {}
        if settings is None:
            from backend.application.services.bi_settings_service import BiSettingsService
            settings = BiSettingsService()
        self._settings = settings

    # ── Público ───────────────────────────────────────────────────────────────

    def build_dashboard(self, filters: DashboardFilters | None = None) -> DashboardPayload:
        f = (filters or DashboardFilters()).resolved()
        key = str(f.to_dict())
        now = time.monotonic()
        if key in self._cache and now - self._cache_ts.get(key, 0) < self._ttl:
            return self._cache[key]

        cur = self._q.core_metrics(f)
        prev = self._q.previous_metrics(f)
        charts_raw = self._q.chart_bundle(f)

        payload = DashboardPayload(
            filters=f.to_dict(),
            kpis=[k.to_dict() for k in self._kpis(cur, prev)],
            charts={c.key: c.to_dict() for c in self._charts(charts_raw)},
            highlights={h.key: h.to_dict() for h in self._highlights(charts_raw)},
            alerts=[a.to_dict() for a in self._alerts(cur, prev, charts_raw)],
            predictions={p.key: p.to_dict() for p in self._predictions(f)},
            insights=[i.to_dict() for i in self._insights(cur, charts_raw)],
            allowed_sections=self._allowed_sections(),
        )
        self._cache[key] = payload
        self._cache_ts[key] = now
        return payload

    def invalidate_cache(self) -> None:
        self._cache.clear()
        self._cache_ts.clear()

    def filter_options(self) -> dict:
        """Catálogos para los filtros globales de la UI."""
        return self._q.filter_options()

    def section_data(self, section: str, filters: DashboardFilters | None = None) -> dict:
        """Datos de una pestaña detallada (mini-KPIs + charts + tablas).

        Estructura estable: {section, title, kpis[], charts[], tables[]}.
        """
        f = (filters or DashboardFilters()).resolved()
        builder = getattr(self, f"_section_{section}", None)
        if builder is None:
            return {"section": section, "title": section.title(),
                    "kpis": [], "charts": [], "tables": []}
        return builder(f)

    # ── Secciones detalladas (FASE 8) ─────────────────────────────────────────

    @staticmethod
    def _mini(title, value, unit="$"):
        return {"title": title, "value": round(float(value or 0), 2), "unit": unit}

    @staticmethod
    def _bars(title, pairs, color=_BLUE, unit="$"):
        return {"kind": "bar", "title": title, "unit": unit,
                "labels": [p[0] for p in pairs],
                "series": [{"name": title, "color": color,
                            "values": [p[1] for p in pairs]}]}

    def _section_ventas(self, f) -> dict:
        s = self._q.sales
        t = s.sales_totals(f)
        return {
            "section": "ventas", "title": "Ventas",
            "kpis": [self._mini("Ventas netas", t["ventas_netas"]),
                     self._mini("Órdenes", t["ordenes"], ""),
                     self._mini("Ticket promedio", t["ticket_promedio"])],
            "charts": [self._bars("Ventas por sucursal", s.by_branch(f)),
                       {"kind": "donut", "title": "Métodos de pago", "unit": "$",
                        "labels": [m for m, _ in s.payment_methods(f)],
                        "series": [{"name": "Total", "color": _BLUE,
                                    "values": [v for _, v in s.payment_methods(f)]}]},
                       {"kind": "line", "title": "Horas pico", "unit": "$",
                        "labels": [h for h, _ in s.peak_hours(f)],
                        "series": [{"name": "Ingresos", "color": _GREEN,
                                    "values": [v for _, v in s.peak_hours(f)]}]}],
            "tables": [
                {"title": "Top productos", "columns": ["Producto", "Ingresos $"],
                 "rows": [[n, f"${v:,.2f}"] for n, v in s.top_products(f)]},
                {"title": "Top clientes", "columns": ["Cliente", "Visitas", "Total $"],
                 "rows": [[c["nombre"], c["visitas"], f"${c['total']:,.2f}"]
                          for c in s.top_customers(f)]}],
        }

    def _section_inventario(self, f) -> dict:
        inv = self._q.inventory
        cogs = self._q.sales.cost_of_goods(f)
        val = inv.inventory_valued(f)
        return {
            "section": "inventario", "title": "Inventario",
            "kpis": [self._mini("Inventario valorizado", val),
                     self._mini("Rotación", (cogs / val) if val else 0, "x"),
                     self._mini("Merma", inv.waste_value(f))],
            "charts": [self._bars("Merma por categoría", inv.waste_by_category(f),
                                  color=_GOLD)],
            "tables": [
                {"title": "Stock crítico", "columns": ["Producto", "Existencia", "Mínimo", "Unidad"],
                 "rows": [[c["nombre"], c["existencia"], c["stock_minimo"], c["unidad"]]
                          for c in inv.critical_stock(f)]}],
        }

    def _section_finanzas(self, f) -> dict:
        m = self._q.core_metrics(f)
        prof = self._q.sales.profitability_by_category(f)
        return {
            "section": "finanzas", "title": "Finanzas",
            "kpis": [self._mini("Ventas netas", m["ventas_netas"]),
                     self._mini("Utilidad neta", m["utilidad_neta"]),
                     self._mini("Margen", m["margen_pct"], "%"),
                     self._mini("Gastos", m["gastos"]),
                     self._mini("CxC", m["cxc"]),
                     self._mini("CxP", m["cxp"])],
            "charts": [self._bars("Rentabilidad por categoría (margen $)",
                                  [(c, mg) for c, mg, _ in prof], color=_GOLD)],
            "tables": [],
        }

    def _section_merma(self, f) -> dict:
        inv = self._q.inventory
        val = inv.waste_value(f)
        ventas = self._q.sales.sales_totals(f)["ventas_netas"]
        return {
            "section": "merma", "title": "Merma",
            "kpis": [self._mini("Valor de merma", val),
                     self._mini("Merma %", (val / ventas * 100) if ventas else 0, "%")],
            "charts": [self._bars("Merma por categoría", inv.waste_by_category(f),
                                  color=_GOLD)],
            "tables": [],
        }

    def _section_caja(self, f) -> dict:
        cash = self._q.cash
        t = cash.cash_totals(f)
        daily = cash.daily_behavior(f)
        return {
            "section": "caja", "title": "Caja",
            "kpis": [self._mini("Ingresos directos", t["ingresos"]),
                     self._mini("Egresos directos", t["egresos"]),
                     self._mini("Saldo", t["saldo"]),
                     self._mini("Cortes", t["num_cortes"], "")],
            "charts": [{"kind": "line", "title": "Comportamiento diario de caja",
                        "unit": "$", "labels": [d for d, _, _ in daily],
                        "series": [{"name": "Ingresos", "color": _GREEN,
                                    "values": [i for _, i, _ in daily]},
                                   {"name": "Egresos", "color": "#ef4444",
                                    "values": [e for _, _, e in daily]}]}],
            "tables": [
                {"title": "Cortes recientes",
                 "columns": ["Fecha", "Ventas $", "Efectivo $", "Diferencia $"],
                 "rows": [[c["fecha"], f"${c['total_ventas']:,.2f}",
                           f"${c['efectivo']:,.2f}", f"${c['diferencia']:,.2f}"]
                          for c in cash.recent_cortes(f)]}],
        }

    def _section_compras(self, f) -> dict:
        fin = self._q.finance
        return {
            "section": "compras", "title": "Compras",
            "kpis": [self._mini("Compras del periodo", fin.purchases_total(f)),
                     self._mini("CxP", fin.accounts_payable_total(f))],
            "charts": [self._bars("Top proveedores",
                                  [(s["nombre"], s["total"]) for s in fin.top_suppliers(f)])],
            "tables": [
                {"title": "Proveedores", "columns": ["Proveedor", "Comprado $"],
                 "rows": [[s["nombre"], f"${s['total']:,.2f}"] for s in fin.top_suppliers(f)]}],
        }

    def _section_clientes(self, f) -> dict:
        s = self._q.sales
        return {
            "section": "clientes", "title": "Clientes",
            "kpis": [self._mini("CxC", self._q.finance.accounts_receivable_total(f))],
            "charts": [self._bars("Top clientes",
                                  [(c["nombre"], c["total"]) for c in s.top_customers(f)])],
            "tables": [
                {"title": "Top clientes", "columns": ["Cliente", "Visitas", "Total $"],
                 "rows": [[c["nombre"], c["visitas"], f"${c['total']:,.2f}"]
                          for c in s.top_customers(f)]}],
        }

    def _section_proveedores(self, f) -> dict:
        fin = self._q.finance
        return {
            "section": "proveedores", "title": "Proveedores",
            "kpis": [self._mini("CxP", fin.accounts_payable_total(f)),
                     self._mini("Compras del periodo", fin.purchases_total(f))],
            "charts": [self._bars("Top proveedores",
                                  [(s["nombre"], s["total"]) for s in fin.top_suppliers(f)])],
            "tables": [
                {"title": "Proveedores", "columns": ["Proveedor", "Comprado $"],
                 "rows": [[s["nombre"], f"${s['total']:,.2f}"] for s in fin.top_suppliers(f)]}],
        }

    # ── KPIs (FASE 4) ─────────────────────────────────────────────────────────

    def _kpis(self, c: dict, p: dict) -> list[KpiCard]:
        return [
            make_kpi("ventas_netas", "Ventas netas", c["ventas_netas"], p["ventas_netas"],
                     unit="$", tooltip="Total vendido (completadas) del periodo.",
                     drilldown="ventas", formula="SUM(ventas.total) estado='completada'"),
            make_kpi("utilidad_neta", "Utilidad neta", c["utilidad_neta"], p["utilidad_neta"],
                     unit="$", tooltip="Ventas netas − costo de ventas − gastos.",
                     drilldown="finanzas", formula="ventas_netas - costo_ventas - gastos"),
            make_kpi("margen", "Margen %", c["margen_pct"], p["margen_pct"], unit="%",
                     is_percent=True, tooltip="Utilidad neta / ventas netas × 100.",
                     drilldown="finanzas", formula="utilidad_neta / ventas_netas * 100"),
            make_kpi("ticket_promedio", "Ticket promedio", c["ticket_promedio"],
                     p["ticket_promedio"], unit="$",
                     tooltip="Ventas netas / número de órdenes.",
                     drilldown="ventas", formula="ventas_netas / ordenes"),
            make_kpi("ordenes", "Órdenes", c["ordenes"], p["ordenes"], unit="",
                     tooltip="Número de ventas completadas.", drilldown="ventas",
                     formula="COUNT(ventas) estado='completada'"),
            make_kpi("inventario_valorizado", "Inventario valorizado",
                     c["inventario_valorizado"], p["inventario_valorizado"], unit="$",
                     tooltip="Σ existencia_sucursal × costo del producto.",
                     drilldown="inventario", formula="SUM(inventory_stock.quantity * costo)"),
            make_kpi("cxc", "CxC (Clientes)", c["cxc"], p["cxc"], unit="$",
                     higher_is_better=False, tooltip="Saldo pendiente de clientes.",
                     drilldown="clientes", formula="SUM(accounts_receivable.balance>0)"),
            make_kpi("cxp", "CxP (Proveedores)", c["cxp"], p["cxp"], unit="$",
                     higher_is_better=False, tooltip="Saldo pendiente a proveedores.",
                     drilldown="proveedores", formula="SUM(accounts_payable.balance>0)"),
            make_kpi("merma", "Merma %", c["merma_pct"], p["merma_pct"], unit="%",
                     is_percent=True, higher_is_better=False,
                     tooltip="Valor de merma / ventas netas × 100.",
                     drilldown="merma", formula="merma_valor / ventas_netas * 100"),
            make_kpi("rotacion", "Rotación inventario", c["rotacion"], p["rotacion"],
                     unit="x", tooltip="Costo de ventas / inventario valorizado.",
                     drilldown="inventario", formula="costo_ventas / inventario_valorizado"),
        ]

    # ── Charts (FASE 5) ───────────────────────────────────────────────────────

    def _charts(self, r: dict) -> list[ChartData]:
        m = r["monthly"]
        prof = r["profitability"]
        return [
            ChartData("sales_trend", "line", "Evolución de ventas y utilidad",
                      labels=m["labels"], series=[
                          {"name": "Ventas", "color": _BLUE, "values": m["ventas"]},
                          {"name": "Utilidad", "color": _GOLD, "values": m["utilidad"]}]),
            ChartData("branch_sales", "bar", "Ventas por sucursal",
                      labels=[n for n, _ in r["by_branch"]],
                      series=[{"name": "Ventas", "color": _BLUE,
                               "values": [v for _, v in r["by_branch"]]}]),
            ChartData("top_products", "hbar", "Top productos",
                      labels=[n for n, _ in r["top_products"]],
                      series=[{"name": "Ingresos", "color": _BLUE,
                               "values": [v for _, v in r["top_products"]]}]),
            ChartData("categories", "bar", "Categorías",
                      labels=[n for n, _ in r["by_category"]],
                      series=[{"name": "Ventas", "color": _BLUE,
                               "values": [v for _, v in r["by_category"]]}]),
            ChartData("payment_methods", "donut", "Métodos de pago",
                      labels=[n for n, _ in r["payment_methods"]],
                      series=[{"name": "Total", "color": _BLUE,
                               "values": [v for _, v in r["payment_methods"]]}]),
            ChartData("peak_hours", "line", "Horas pico de venta",
                      labels=[h for h, _ in r["peak_hours"]],
                      series=[{"name": "Ingresos", "color": _GREEN,
                               "values": [v for _, v in r["peak_hours"]]}]),
            ChartData("forecast", "line", "Forecast de demanda",
                      labels=r["forecast"]["labels"], unit="$", series=[
                          {"name": "Real", "color": _BLUE, "values": r["forecast"]["real"]},
                          {"name": "Pronóstico", "color": _GOLD,
                           "values": r["forecast"]["pronostico"]}]),
            ChartData("profitability", "bar", "Rentabilidad por línea (margen $)",
                      labels=[c for c, _, _ in prof],
                      series=[{"name": "Margen", "color": _GOLD,
                               "values": [mg for _, mg, _ in prof]}]),
        ]

    # ── Highlights (FASE 5) ───────────────────────────────────────────────────

    def _highlights(self, r: dict) -> list[HighlightCard]:
        out = []
        tp = r["top_products"]
        if tp:
            total = sum(v for _, v in tp) or 1.0
            out.append(HighlightCard("top_product", "Producto top", tp[0][0], tp[0][1],
                                     round(tp[0][1] / total * 100, 1)))
        bc = r["by_category"]
        if bc:
            total = sum(v for _, v in bc) or 1.0
            out.append(HighlightCard("top_category", "Categoría top", bc[0][0], bc[0][1],
                                     round(bc[0][1] / total * 100, 1)))
        bb = r["by_branch"]
        if bb:
            total = sum(v for _, v in bb) or 1.0
            out.append(HighlightCard("top_branch", "Sucursal top", bb[0][0], bb[0][1],
                                     round(bb[0][1] / total * 100, 1)))
        return out

    # ── Alertas (FASE 6) ──────────────────────────────────────────────────────

    def _alerts(self, c: dict, p: dict, r: dict) -> list[Alert]:
        alerts: list[Alert] = []
        st = self._settings
        merma_thr = st.get("threshold_merma_pct")
        margen_thr = st.get("threshold_margen_bajo_pct")
        caida_thr = st.get("threshold_caida_ventas_pct")
        cxc_thr = st.get("threshold_cxc_aumento_pct")
        compras_thr = st.get("threshold_compras_aumento_pct")
        meta = st.get("meta_ventas_periodo")

        if c["merma_pct"] > merma_thr:
            alerts.append(Alert("critical", "merma_alta", "Merma alta",
                                 f"La merma es {c['merma_pct']:.1f}% de las ventas "
                                 f"(${c['merma_valor']:,.2f}, umbral {merma_thr:.0f}%). "
                                 "Revisar cadena de frío y porciones.", c["merma_pct"]))
        if p["ventas_netas"] > 0 and \
                c["ventas_netas"] < p["ventas_netas"] * (1 - caida_thr / 100):
            caida = (1 - c["ventas_netas"] / p["ventas_netas"]) * 100
            alerts.append(Alert("warning", "caida_ventas", "Caída de ventas",
                                 f"Las ventas bajaron {caida:.1f}% vs el periodo anterior.", caida))
        if p["cxc"] > 0 and c["cxc"] > p["cxc"] * (1 + cxc_thr / 100):
            alerts.append(Alert("warning", "cxc_alta", "Aumento de CxC",
                                 f"Las cuentas por cobrar subieron a ${c['cxc']:,.2f}.", c["cxc"]))
        if c["ventas_netas"] > 0 and c["margen_pct"] < margen_thr:
            alerts.append(Alert("warning", "margen_bajo", "Utilidad baja pese a ventas",
                                 f"El margen es {c['margen_pct']:.1f}% pese a ${c['ventas_netas']:,.2f} "
                                 "en ventas. Revisar costos y gastos.", c["margen_pct"]))
        if p["compras"] > 0 and c["compras"] > p["compras"] * (1 + compras_thr / 100) and \
                c["ventas_netas"] <= p["ventas_netas"] * 1.05:
            alerts.append(Alert("warning", "compras_sin_venta", "Compras sin correlación de ventas",
                                 "Las compras crecieron sin un aumento equivalente de ventas.",
                                 c["compras"]))
        if meta > 0 and c["ventas_netas"] < meta:
            falta = meta - c["ventas_netas"]
            alerts.append(Alert("info", "meta_ventas", "Meta de ventas no alcanzada",
                                 f"Ventas ${c['ventas_netas']:,.2f} de la meta ${meta:,.2f} "
                                 f"(faltan ${falta:,.2f}).", c["ventas_netas"]))
        return alerts

    # ── Insights (FASE 6) ─────────────────────────────────────────────────────

    def _insights(self, c: dict, r: dict) -> list[Insight]:
        ins: list[Insight] = []
        if r["by_branch"]:
            n, v = r["by_branch"][0]
            ins.append(Insight("sucursal_top", f"Mayor venta en sucursal {n}",
                               f"Lidera con ${v:,.2f} en el periodo."))
        if r["by_category"]:
            n, v = r["by_category"][0]
            ins.append(Insight("categoria_oportunidad", f"Oportunidad en categoría {n}",
                               f"Categoría líder con ${v:,.2f}; ampliar surtido y promos."))
        if r["top_products"]:
            n, v = r["top_products"][0]
            ins.append(Insight("producto_top", f"Producto estrella: {n}",
                               f"Genera ${v:,.2f} en ventas del periodo."))
        pm = r["payment_methods"]
        if pm:
            total = sum(v for _, v in pm) or 1.0
            n, v = pm[0]
            ins.append(Insight("metodo_pago", f"Método de pago dominante: {n}",
                               f"Representa {v/total*100:.0f}% de la facturación."))
        if c["margen_pct"] > 0:
            ins.append(Insight("rentabilidad",
                               f"Margen del periodo: {c['margen_pct']:.1f}%",
                               f"Utilidad neta estimada ${c['utilidad_neta']:,.2f}."))
        return ins

    # ── Predicciones (FASE 5/6) ───────────────────────────────────────────────

    def _predictions(self, f) -> list[Prediction]:
        window = self._settings.get("forecast_window_days")
        nw = self._q.forecast.next_week_prediction(f, window_days=window)
        return [Prediction("next_week", "Predicción próxima semana", nw["value"],
                           unit="$", detail=f"~${nw['avg_dia']:,.2f}/día "
                                             f"({nw['muestras']} días de histórico).")]

    # ── Permisos (FASE 12) ────────────────────────────────────────────────────

    def _allowed_sections(self) -> list[str]:
        out = ["resumen"]
        for sec in ALL_SECTIONS:
            if sec == "resumen":
                continue
            perm = SECTION_PERMISSION.get(sec)
            if perm is None or self._can(perm):
                out.append(sec)
        return out
