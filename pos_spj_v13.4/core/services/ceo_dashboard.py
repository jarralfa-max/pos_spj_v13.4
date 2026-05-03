# core/services/ceo_dashboard.py — SPJ POS v13.30 — FASE 9
"""
CEODashboard — Panel ejecutivo que consolida TODO.

Muestra KPIs, alertas, sugerencias e IA en un solo lugar.
Funciona 100% SIN IA — la IA es un bonus opcional.

SECCIONES:
    1. KPIs financieros (Treasury)
    2. Alertas activas (AlertEngine)
    3. Sugerencias (DecisionEngine)
    4. Forecast (ActionableForecast)
    5. Simulaciones recientes (FinancialSimulator)
    6. IA estratégica (AIAdvisor — opcional)
    7. Comparativo por sucursal

USO:
    dashboard = container.ceo_dashboard
    data = dashboard.get_full_dashboard()
    # → dict con todas las secciones
"""
from __future__ import annotations
import logging
from datetime import date, datetime
from typing import Dict, List, Any, Optional

logger = logging.getLogger("spj.ceo")


class CEODashboard:
    """Panel ejecutivo — agrega todos los servicios en un solo reporte."""

    def __init__(self, db_conn=None, treasury_service=None,
                 alert_engine=None, decision_engine=None,
                 actionable_forecast=None, simulator=None,
                 ai_advisor=None, loyalty_service=None):
        self.db = db_conn
        self.treasury = treasury_service
        self.alerts = alert_engine
        self.decisions = decision_engine
        self.forecast = actionable_forecast
        self.simulator = simulator
        self.ai = ai_advisor
        self.loyalty = loyalty_service

    # ══════════════════════════════════════════════════════════════════════════
    #  Dashboard completo
    # ══════════════════════════════════════════════════════════════════════════

    def get_full_dashboard(self, sucursal_id: int = 0,
                            fecha_desde: str = "",
                            fecha_hasta: str = "") -> Dict[str, Any]:
        """Retorna el dashboard ejecutivo completo."""
        return {
            "timestamp": datetime.now().isoformat(),
            "kpis": self._section_kpis(sucursal_id, fecha_desde, fecha_hasta),
            "alertas": self._section_alertas(),
            "sugerencias": self._section_sugerencias(sucursal_id),
            "ventas_hoy": self._section_ventas_hoy(sucursal_id),
            "fidelizacion": self._section_fidelizacion(),
            "sucursales": self._section_sucursales(fecha_desde, fecha_hasta),
            "ia_disponible": self._ia_disponible(),
        }

    # ══════════════════════════════════════════════════════════════════════════
    #  Secciones individuales
    # ══════════════════════════════════════════════════════════════════════════

    def _section_kpis(self, suc: int, df: str, dt: str) -> Dict:
        """KPIs financieros principales."""
        if not self.treasury:
            return self._kpis_basicos(df, dt)
        try:
            k = self.treasury.kpis_financieros(df, dt, suc)
            return {
                "ingresos": k.get("ingresos", 0),
                "costo_venta": k.get("costo_venta", 0),
                "utilidad_bruta": k.get("utilidad_bruta", 0),
                "margen_bruto_pct": k.get("margen_bruto_pct", 0),
                "egresos_total": k.get("egresos", {}).get("total_egresos", 0),
                "gastos_fijos": k.get("egresos", {}).get("gastos_fijos", 0),
                "gastos_operativos": k.get("egresos", {}).get("gastos_operativos", 0),
                "nomina": k.get("egresos", {}).get("nomina_rrhh", 0),
                "compras_inventario": k.get("egresos", {}).get("compras_inventario", 0),
                "utilidad_neta": k.get("utilidad_neta", 0),
                "margen_neto_pct": k.get("margen_neto_pct", 0),
                "capital_invertido": k.get("capital_invertido", 0),
                "capital_disponible": k.get("capital_disponible", 0),
                "roi_pct": k.get("roi_pct", 0),
                "burn_rate_meses": k.get("burn_rate_meses", 0),
                "valor_inventario": k.get("valor_inventario", 0),
                "valor_activos_fijos": k.get("valor_activos_fijos", 0),
                "pasivo_fidelizacion": k.get("pasivo_fidelizacion", 0),
                "salud": self.treasury._salud(k),
                "periodo": k.get("periodo", {}),
            }
        except Exception as e:
            logger.debug("KPIs: %s", e)
            return self._kpis_basicos(df, dt)

    def _kpis_basicos(self, df: str, dt: str) -> Dict:
        """KPIs mínimos sin TreasuryService."""
        hoy = date.today()
        df = df or date(hoy.year, hoy.month, 1).isoformat()
        dt = dt or hoy.isoformat()
        ingresos = self._q(
            "SELECT COALESCE(SUM(total),0) FROM ventas "
            "WHERE estado='completada' AND DATE(fecha) BETWEEN ? AND ?",
            [df, dt])
        gastos = self._q(
            "SELECT COALESCE(SUM(monto),0) FROM gastos "
            "WHERE DATE(fecha) BETWEEN ? AND ?", [df, dt])
        return {
            "ingresos": round(ingresos, 2),
            "gastos_total": round(gastos, 2),
            "utilidad_neta": round(ingresos - gastos, 2),
            "salud": "🔵 BÁSICO — TreasuryService no activado",
        }

    def _section_alertas(self) -> Dict:
        """Alertas activas por severidad."""
        if not self.alerts:
            return {"total": 0, "criticas": 0, "lista": []}
        try:
            todas = self.alerts.get_alerts_filtered(leida=False, limit=20)
            criticas = [a for a in todas
                        if a.get("severity") == "critical"]
            return {
                "total": len(todas),
                "criticas": len(criticas),
                "lista": todas[:10],
            }
        except Exception:
            return {"total": 0, "criticas": 0, "lista": []}

    def _section_sugerencias(self, suc: int = 0) -> Dict:
        """Top sugerencias del DecisionEngine."""
        if not self.decisions:
            return {"total": 0, "lista": []}
        try:
            sug = self.decisions.generar_sugerencias(suc)
            return {"total": len(sug), "lista": sug[:8]}
        except Exception:
            return {"total": 0, "lista": []}

    def _section_ventas_hoy(self, suc: int = 0) -> Dict:
        """Resumen de ventas del día."""
        sf = " AND sucursal_id=?" if suc else ""
        sp = [suc] if suc else []
        hoy = date.today().isoformat()
        total = self._q(
            f"SELECT COALESCE(SUM(total),0) FROM ventas "
            f"WHERE estado='completada' AND DATE(fecha)=?{sf}",
            [hoy] + sp)
        tickets = int(self._q(
            f"SELECT COUNT(*) FROM ventas "
            f"WHERE estado='completada' AND DATE(fecha)=?{sf}",
            [hoy] + sp))
        avg = (total / tickets) if tickets else 0
        return {
            "total": round(total, 2),
            "tickets": tickets,
            "ticket_promedio": round(avg, 2),
        }

    def _section_fidelizacion(self) -> Dict:
        """Estado del programa de fidelización."""
        if not self.loyalty:
            return {"activo": False}
        try:
            pasivo = self.loyalty.pasivo_financiero()
            return {
                "activo": True,
                "total_estrellas": pasivo.get("total_estrellas", 0),
                "pasivo_monetario": pasivo.get("valor_monetario", 0),
            }
        except Exception:
            return {"activo": True, "total_estrellas": 0, "pasivo_monetario": 0}

    def _section_sucursales(self, df: str, dt: str) -> List[Dict]:
        """Comparativo por sucursal."""
        if not self.treasury:
            return []
        try:
            return self.treasury.kpis_por_sucursal(df, dt)
        except Exception:
            return []

    def _ia_disponible(self) -> bool:
        if not self.ai:
            return False
        return self.ai.is_available_sync()

    # ══════════════════════════════════════════════════════════════════════════
    #  Reporte ejecutivo en texto
    # ══════════════════════════════════════════════════════════════════════════

    def reporte_texto(self, sucursal_id: int = 0) -> str:
        """Genera un reporte ejecutivo en texto plano (para email, WhatsApp)."""
        d = self.get_full_dashboard(sucursal_id)
        k = d["kpis"]
        v = d["ventas_hoy"]
        a = d["alertas"]
        s = d["sugerencias"]

        lines = [
            "═" * 40,
            "📊 REPORTE EJECUTIVO — SPJ POS",
            f"   {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "═" * 40,
            "",
            f"💰 Ingresos del mes: ${k.get('ingresos', 0):,.2f}",
            f"📉 Egresos totales:  ${k.get('egresos_total', k.get('gastos_total', 0)):,.2f}",
            f"📈 Utilidad neta:    ${k.get('utilidad_neta', 0):,.2f}",
            f"📊 Margen neto:      {k.get('margen_neto_pct', 0):.1f}%",
            f"🏦 Capital disp.:    ${k.get('capital_disponible', 0):,.2f}",
            f"📈 ROI:              {k.get('roi_pct', 0):.1f}%",
            f"⏳ Burn rate:        {k.get('burn_rate_meses', 0):.1f} meses",
            f"❤️ Salud:            {k.get('salud', 'N/A')}",
            "",
            "─" * 40,
            f"🛒 Ventas hoy: ${v['total']:,.2f} ({v['tickets']} tickets)",
            f"   Ticket promedio: ${v['ticket_promedio']:,.2f}",
            "",
            f"🚨 Alertas: {a['total']} ({a['criticas']} críticas)",
            f"💡 Sugerencias: {s['total']} pendientes",
            "═" * 40,
        ]
        return "\n".join(lines)

    def _q(self, sql: str, params: list = None) -> float:
        try:
            row = self.db.execute(sql, params or []).fetchone()
            return float(row[0]) if row and row[0] else 0.0
        except Exception:
            return 0.0
