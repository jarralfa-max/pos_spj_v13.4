# core/services/financial_simulator.py — SPJ POS v13.30 — FASE 7
"""
FinancialSimulator — Simula escenarios ANTES de comprometer capital.

ESCENARIOS SOPORTADOS:
    1. Nueva sucursal — ¿cuánto cuesta abrir y cuándo es rentable?
    2. Compra de activo — ¿vale la pena comprar equipo nuevo?
    3. Contratación — impacto de más personal en costos y productividad
    4. Cambio en fidelización — ¿qué pasa si cambio la tasa?
    5. Inversión genérica — ROI proyectado de cualquier gasto de capital

NUNCA ejecuta — solo calcula proyecciones y las presenta al usuario.

USO:
    sim = container.financial_simulator
    resultado = sim.simular_nueva_sucursal(
        renta=15000, personal=3, inv_inicial=80000)
    # → {"inversion_total": 95000, "mes_breakeven": 8, "roi_12m": 22.5, ...}
"""
from __future__ import annotations
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("spj.simulator")


class FinancialSimulator:

    def __init__(self, db_conn, treasury_service=None, module_config=None):
        self.db = db_conn
        self.treasury = treasury_service
        self._module_config = module_config

    @property
    def enabled(self) -> bool:
        if self._module_config:
            return self._module_config.is_enabled('simulation')
        return True

    # ══════════════════════════════════════════════════════════════════════════
    #  1. Simular nueva sucursal
    # ══════════════════════════════════════════════════════════════════════════

    def simular_nueva_sucursal(self, renta_mensual: float = 15000,
                                personal: int = 3,
                                salario_promedio: float = 8000,
                                inversion_inicial: float = 80000,
                                gastos_fijos_extra: float = 5000,
                                meses: int = 12) -> Dict:
        """Simula apertura de nueva sucursal."""
        # Datos base del negocio actual
        avg_venta_suc = self._q(
            "SELECT AVG(total_mes) FROM ("
            "  SELECT sucursal_id, SUM(total) as total_mes FROM ventas "
            "  WHERE estado='completada' AND fecha > datetime('now','-90 days') "
            "  GROUP BY sucursal_id, strftime('%Y-%m', fecha))")
        if avg_venta_suc <= 0:
            avg_venta_suc = 100000  # default

        nomina = personal * salario_promedio
        gastos_fijos = renta_mensual + gastos_fijos_extra
        total_mensual = nomina + gastos_fijos
        margen_neto_actual = self._q(
            "SELECT COALESCE(AVG(margen),25) FROM ("
            "  SELECT (SUM(v.total) - SUM(dv.cantidad*COALESCE(p.precio_compra,p.costo,0))) "
            "  / NULLIF(SUM(v.total),0) * 100 as margen "
            "  FROM ventas v "
            "  JOIN detalles_venta dv ON dv.venta_id=v.id "
            "  JOIN productos p ON p.id=dv.producto_id "
            "  WHERE v.estado='completada' AND v.fecha > datetime('now','-90 days'))") or 25

        proyeccion = []
        acumulado = -inversion_inicial
        breakeven_mes = 0

        for mes_n in range(1, meses + 1):
            # Ramp-up: 40% mes 1, 60% mes 2, 80% mes 3, 100% mes 4+
            factor = min(1.0, 0.2 + mes_n * 0.2)
            ingresos_mes = avg_venta_suc * factor
            utilidad_bruta = ingresos_mes * (margen_neto_actual / 100)
            utilidad_mes = utilidad_bruta - total_mensual
            acumulado += utilidad_mes

            proyeccion.append({
                "mes": mes_n,
                "ingresos": round(ingresos_mes, 2),
                "gastos": round(total_mensual, 2),
                "utilidad": round(utilidad_mes, 2),
                "acumulado": round(acumulado, 2),
            })
            if acumulado >= 0 and breakeven_mes == 0:
                breakeven_mes = mes_n

        roi_final = (acumulado / inversion_inicial * 100) if inversion_inicial else 0

        # v13.30: Impacto en flujo de caja
        capital_actual = 0
        if self.treasury:
            try:
                capital_actual = self.treasury.capital_total()
            except Exception:
                pass
        flujo_impacto = {
            "capital_antes": round(capital_actual, 2),
            "capital_despues": round(capital_actual - inversion_inicial, 2),
            "egreso_mensual_nuevo": round(total_mensual, 2),
            "meses_sostenible": round(
                (capital_actual - inversion_inicial) / max(1, total_mensual), 1),
        }

        return {
            "escenario": "nueva_sucursal",
            "inversion_inicial": inversion_inicial,
            "gastos_mensuales": {
                "renta": renta_mensual,
                "nomina": nomina,
                "otros_fijos": gastos_fijos_extra,
                "total": total_mensual,
            },
            "ingreso_estimado_maduro": round(avg_venta_suc, 2),
            "margen_estimado_pct": round(margen_neto_actual, 1),
            "mes_breakeven": breakeven_mes or f">{meses}",
            "meses_para_roi": breakeven_mes or meses + 1,
            "roi_{meses}m_pct": round(roi_final, 1),
            "utilidad_acumulada": round(acumulado, 2),
            "flujo_caja_impacto": flujo_impacto,
            "proyeccion_mensual": proyeccion,
            "recomendacion": (
                "✅ Viable" if breakeven_mes and breakeven_mes <= 8
                else "⚠️ Revisar" if breakeven_mes and breakeven_mes <= 12
                else "❌ Riesgoso — recuperación >12 meses"),
        }

    # ══════════════════════════════════════════════════════════════════════════
    #  2. Simular compra de activo
    # ══════════════════════════════════════════════════════════════════════════

    def simular_compra_activo(self, nombre: str, costo: float,
                               vida_util_anios: int = 5,
                               ahorro_mensual: float = 0,
                               ingreso_extra_mensual: float = 0) -> Dict:
        """Evalúa si vale la pena comprar un equipo/activo."""
        depreciacion_mensual = costo / (vida_util_anios * 12)
        beneficio_mensual = ahorro_mensual + ingreso_extra_mensual
        meses_recuperacion = (costo / beneficio_mensual) if beneficio_mensual > 0 else 999
        roi_anual = ((beneficio_mensual * 12 - depreciacion_mensual * 12)
                     / costo * 100) if costo > 0 else 0

        # Capital disponible
        capital_ok = True
        capital_disp = 0
        if self.treasury:
            try:
                estado = self.treasury.estado_cuenta()
                capital_disp = estado.get("capital_disponible", 0)
                capital_ok = capital_disp >= costo
            except Exception:
                pass

        return {
            "escenario": "compra_activo",
            "activo": nombre,
            "costo": costo,
            "vida_util_anios": vida_util_anios,
            "depreciacion_mensual": round(depreciacion_mensual, 2),
            "beneficio_mensual": round(beneficio_mensual, 2),
            "meses_recuperacion": round(meses_recuperacion, 1),
            "roi_anual_pct": round(roi_anual, 1),
            "capital_suficiente": capital_ok,
            "flujo_caja_impacto": {
                "capital_antes": round(capital_disp, 2),
                "capital_despues": round(capital_disp - costo, 2),
                "pct_del_capital": round(costo / max(1, capital_disp) * 100, 1),
            },
            "recomendacion": (
                "✅ Buena inversión" if meses_recuperacion <= 18
                else "⚠️ Recuperación lenta" if meses_recuperacion <= 36
                else "❌ No recomendable"),
        }

    # ══════════════════════════════════════════════════════════════════════════
    #  3. Simular contratación
    # ══════════════════════════════════════════════════════════════════════════

    def simular_contratacion(self, cantidad: int = 1,
                              salario: float = 8000,
                              productividad_esperada: float = 25000) -> Dict:
        """Simula impacto de contratar personal adicional."""
        costo_total_mensual = cantidad * salario * 1.35  # +35% cargas sociales
        ingresos_adicionales = cantidad * productividad_esperada

        empleados_actual = self._q("SELECT COUNT(*) FROM empleados WHERE activo=1")
        nomina_actual = self._q(
            "SELECT COALESCE(SUM(total),0) FROM nomina_pagos "
            "WHERE estado='pagado' AND fecha > datetime('now','-30 days')")
        ingresos_actual = self._q(
            "SELECT COALESCE(SUM(total),0) FROM ventas "
            "WHERE estado='completada' AND fecha > datetime('now','-30 days')")

        nueva_nomina = nomina_actual + costo_total_mensual
        nuevos_ingresos = ingresos_actual + ingresos_adicionales
        ratio_actual = (nomina_actual / ingresos_actual * 100) if ingresos_actual else 0
        ratio_nuevo = (nueva_nomina / nuevos_ingresos * 100) if nuevos_ingresos else 0

        return {
            "escenario": "contratacion",
            "nuevos_empleados": cantidad,
            "salario_bruto": salario,
            "costo_real_mensual": round(costo_total_mensual, 2),
            "ingreso_esperado_adicional": round(ingresos_adicionales, 2),
            "estado_actual": {
                "empleados": int(empleados_actual),
                "nomina_mensual": round(nomina_actual, 2),
                "ratio_nomina_ingresos": f"{ratio_actual:.1f}%",
            },
            "estado_proyectado": {
                "empleados": int(empleados_actual + cantidad),
                "nomina_mensual": round(nueva_nomina, 2),
                "ratio_nomina_ingresos": f"{ratio_nuevo:.1f}%",
            },
            "flujo_caja_impacto": {
                "egreso_mensual_nuevo": round(costo_total_mensual, 2),
                "egreso_anual_nuevo": round(costo_total_mensual * 12, 2),
                "ingreso_esperado_mensual": round(ingresos_adicionales, 2),
                "neto_mensual": round(ingresos_adicionales - costo_total_mensual, 2),
            },
            "recomendacion": (
                "✅ Viable" if ratio_nuevo < 30
                else "⚠️ Nómina alta" if ratio_nuevo < 40
                else "❌ Riesgoso — nómina excedería 40% de ingresos"),
        }

    # ══════════════════════════════════════════════════════════════════════════
    #  4. Simular cambio en fidelización
    # ══════════════════════════════════════════════════════════════════════════

    def simular_cambio_fidelizacion(self, nueva_tasa: float = 0.5,
                                      nuevo_cap_pct: float = 50) -> Dict:
        """Simula el impacto de cambiar la tasa de acumulación de estrellas."""
        # Tasa actual: 1 estrella por peso (100%)
        tasa_actual = 1.0
        valor_estrella = float(self._cfg("loyalty_valor_estrella", "0.10"))

        ingresos_mes = self._q(
            "SELECT COALESCE(SUM(total),0) FROM ventas "
            "WHERE estado='completada' AND fecha > datetime('now','-30 days')")

        emision_actual = ingresos_mes * tasa_actual * valor_estrella
        emision_nueva = ingresos_mes * nueva_tasa * valor_estrella
        ahorro = emision_actual - emision_nueva

        pasivo_actual = self._q(
            "SELECT COALESCE(SUM(monto_total),0) FROM loyalty_pasivo_log")

        return {
            "escenario": "cambio_fidelizacion",
            "tasa_actual": tasa_actual,
            "tasa_nueva": nueva_tasa,
            "valor_estrella": valor_estrella,
            "emision_mensual_actual": round(emision_actual, 2),
            "emision_mensual_nueva": round(emision_nueva, 2),
            "ahorro_mensual": round(ahorro, 2),
            "ahorro_anual": round(ahorro * 12, 2),
            "pasivo_actual": round(pasivo_actual, 2),
            "recomendacion": (
                f"Reducir tasa a {nueva_tasa} ahorra ${ahorro:,.2f}/mes"
                if ahorro > 0 else "La nueva tasa aumenta costos"),
        }

    # ══════════════════════════════════════════════════════════════════════════
    #  5. Simulación genérica de inversión
    # ══════════════════════════════════════════════════════════════════════════

    def simular_inversion(self, monto: float, retorno_mensual: float,
                           duracion_meses: int = 12,
                           descripcion: str = "") -> Dict:
        """Calcula ROI y viabilidad de cualquier inversión."""
        total_retorno = retorno_mensual * duracion_meses
        roi = ((total_retorno - monto) / monto * 100) if monto > 0 else 0
        meses_rec = (monto / retorno_mensual) if retorno_mensual > 0 else 999

        capital_ok = True
        if self.treasury:
            try:
                estado = self.treasury.estado_cuenta()
                capital_ok = estado.get("capital_disponible", 0) >= monto
            except Exception:
                pass

        return {
            "escenario": "inversion_generica",
            "descripcion": descripcion or "Inversión",
            "monto": monto,
            "retorno_mensual": retorno_mensual,
            "duracion_meses": duracion_meses,
            "retorno_total": round(total_retorno, 2),
            "utilidad_neta": round(total_retorno - monto, 2),
            "roi_pct": round(roi, 1),
            "meses_recuperacion": round(meses_rec, 1),
            "capital_suficiente": capital_ok,
            "recomendacion": (
                "✅ Rentable" if roi > 20
                else "⚠️ Marginal" if roi > 0
                else "❌ No rentable"),
        }

    # ══════════════════════════════════════════════════════════════════════════
    #  Helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _q(self, sql: str, params: list = None) -> float:
        try:
            row = self.db.execute(sql, params or []).fetchone()
            return float(row[0]) if row and row[0] else 0.0
        except Exception:
            return 0.0

    def _cfg(self, key: str, default: str = "") -> str:
        try:
            row = self.db.execute(
                "SELECT valor FROM configuraciones WHERE clave=?",
                (key,)).fetchone()
            return row[0] if row and row[0] else default
        except Exception:
            return default
