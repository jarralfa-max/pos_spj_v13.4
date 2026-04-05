# core/services/expansion_analyzer.py — SPJ POS v13.30 — FASE 11
"""
ExpansionAnalyzer — Evaluación estratégica de expansión basada en datos.

Funciona en 2 modos:
    1. SIN IA: análisis basado en reglas y datos reales (SIEMPRE disponible)
    2. CON IA: análisis enriquecido con DeepSeek/Ollama (opcional)

EVALÚA:
    - ¿Abrir nueva sucursal? (datos de mercado + capacidad financiera)
    - ¿Comprar equipo? (ROI proyectado + depreciación)
    - ¿Contratar personal? (ingreso/empleado + carga nómina)
    - ¿Optimizar fidelización? (costo vs retención)
    - ¿Reducir costos? (análisis de gastos por categoría)

USO:
    analyzer = container.expansion_analyzer
    eval = analyzer.evaluar_nueva_sucursal(renta=15000, empleados=4)
    eval = analyzer.evaluar_compra_equipo("Horno", 85000, vida_util=5)
    eval = analyzer.plan_crecimiento()  # plan integral
"""
from __future__ import annotations
import logging
from datetime import date, datetime
from typing import Dict, List, Any, Optional

logger = logging.getLogger("spj.expansion")


class ExpansionAnalyzer:
    """Evalúa oportunidades de crecimiento con datos reales."""

    def __init__(self, db_conn=None, treasury_service=None,
                 simulator=None, franchise_manager=None,
                 ai_advisor=None, module_config=None):
        self.db = db_conn
        self.treasury = treasury_service
        self.simulator = simulator
        self.franchise = franchise_manager
        self.ai = ai_advisor
        self._module_config = module_config

    # ══════════════════════════════════════════════════════════════════════════
    #  Evaluar nueva sucursal
    # ══════════════════════════════════════════════════════════════════════════

    def evaluar_nueva_sucursal(self, renta_mensual: float = 15000,
                                empleados: int = 4,
                                inversion_inicial: float = 100000,
                                salario_promedio: float = 7000) -> Dict:
        """
        Evalúa viabilidad de abrir nueva sucursal.
        Combina simulación financiera + datos de sucursales existentes.
        """
        resultado = {
            "tipo": "nueva_sucursal",
            "viable": False,
            "confianza": "baja",
            "razon": "",
            "datos": {},
            "recomendacion": "",
        }

        # 1. ¿Hay capital suficiente?
        capital = 0
        if self.treasury:
            try:
                estado = self.treasury.estado_cuenta()
                capital = estado.get("capital_disponible", 0)
                resultado["datos"]["capital_disponible"] = capital
                resultado["datos"]["salud_actual"] = estado.get("salud", "")
            except Exception:
                pass

        if capital < inversion_inicial * 1.5:
            resultado["razon"] = (
                f"Capital insuficiente: ${capital:,.0f} disponible, "
                f"se necesitan al menos ${inversion_inicial * 1.5:,.0f} "
                f"(inversión + 50% colchón)")
            resultado["recomendacion"] = (
                "Acumular capital antes de expandir. "
                f"Faltan ${inversion_inicial * 1.5 - capital:,.0f}")
            return resultado

        # 2. ¿Las sucursales actuales son rentables?
        if self.franchise:
            try:
                ranking = self.franchise.ranking_sucursales()
                if ranking:
                    peor = ranking[-1]
                    resultado["datos"]["peor_sucursal"] = peor
                    if peor.get("utilidad_estimada", 0) < 0:
                        resultado["razon"] = (
                            f"La sucursal '{peor['nombre']}' opera con pérdida. "
                            f"Corregir antes de abrir otra.")
                        resultado["recomendacion"] = (
                            "Optimizar sucursales existentes primero")
                        return resultado
                    avg_ingreso = sum(r["ingresos"] for r in ranking) / len(ranking)
                    resultado["datos"]["ingreso_promedio_sucursal"] = round(avg_ingreso, 2)
            except Exception:
                pass

        # 3. Simulación financiera
        if self.simulator:
            try:
                sim = self.simulator.simular_nueva_sucursal(
                    renta_mensual=renta_mensual,
                    empleados=empleados,
                    inversion_inicial=inversion_inicial,
                    salario_promedio=salario_promedio)
                resultado["datos"]["simulacion"] = sim
                meses_roi = sim.get("meses_para_roi", 99)
                if meses_roi <= 12:
                    resultado["viable"] = True
                    resultado["confianza"] = "alta"
                    resultado["recomendacion"] = (
                        f"✅ Viable. ROI en ~{meses_roi} meses.")
                elif meses_roi <= 24:
                    resultado["viable"] = True
                    resultado["confianza"] = "media"
                    resultado["recomendacion"] = (
                        f"⚠️ Viable con precaución. ROI en ~{meses_roi} meses.")
                else:
                    resultado["razon"] = f"ROI > 24 meses ({meses_roi})"
                    resultado["recomendacion"] = (
                        "No recomendable — retorno muy lento")
            except Exception:
                pass

        if not resultado["razon"] and not resultado["viable"]:
            resultado["viable"] = True
            resultado["confianza"] = "media"
            resultado["recomendacion"] = "Datos insuficientes para evaluación completa"

        return resultado

    # ══════════════════════════════════════════════════════════════════════════
    #  Evaluar compra de equipo
    # ══════════════════════════════════════════════════════════════════════════

    def evaluar_compra_equipo(self, nombre: str, costo: float,
                               vida_util_anios: int = 5,
                               ahorro_mensual: float = 0) -> Dict:
        """Evalúa si comprar un activo fijo tiene sentido."""
        resultado = {"tipo": "compra_equipo", "viable": False, "datos": {}}

        depreciacion_mensual = costo / (vida_util_anios * 12)
        resultado["datos"]["depreciacion_mensual"] = round(depreciacion_mensual, 2)

        # ROI si genera ahorro
        if ahorro_mensual > 0:
            meses_roi = costo / ahorro_mensual
            resultado["datos"]["meses_roi"] = round(meses_roi, 1)
            resultado["viable"] = meses_roi < vida_util_anios * 12
            resultado["recomendacion"] = (
                f"ROI en {meses_roi:.0f} meses "
                f"({'✅ antes' if resultado['viable'] else '❌ después'} "
                f"de vida útil)")
        else:
            resultado["recomendacion"] = (
                "Sin ahorro proyectado — evaluar impacto cualitativo")

        # Capital disponible
        if self.treasury:
            try:
                capital = self.treasury.estado_cuenta().get("capital_disponible", 0)
                resultado["datos"]["capital_disponible"] = capital
                resultado["datos"]["pct_del_capital"] = round(
                    costo / max(1, capital) * 100, 1)
                if costo > capital * 0.3:
                    resultado["recomendacion"] += (
                        f"\n⚠️ Representa {costo/capital*100:.0f}% del capital")
            except Exception:
                pass

        return resultado

    # ══════════════════════════════════════════════════════════════════════════
    #  Evaluar contratación
    # ══════════════════════════════════════════════════════════════════════════

    def evaluar_contratacion(self, cantidad: int = 1,
                              salario: float = 7000,
                              sucursal_id: int = 1) -> Dict:
        """Evalúa si contratar más personal es viable."""
        resultado = {"tipo": "contratacion", "viable": False, "datos": {}}

        costo_mensual = cantidad * salario * 1.35  # +35% carga social
        resultado["datos"]["costo_mensual_total"] = round(costo_mensual, 2)

        if self.franchise:
            try:
                eff = self.franchise.eficiencia_sucursal(sucursal_id)
                resultado["datos"]["eficiencia_actual"] = eff
                ingreso_emp = eff.get("ingreso_por_empleado", 0)
                resultado["datos"]["ingreso_por_empleado"] = ingreso_emp

                if ingreso_emp > salario * 3:
                    resultado["viable"] = True
                    resultado["recomendacion"] = (
                        f"✅ Cada empleado genera ${ingreso_emp:,.0f}/mes "
                        f"(3x su costo). Contratar es rentable.")
                elif ingreso_emp > salario * 1.5:
                    resultado["viable"] = True
                    resultado["recomendacion"] = (
                        f"⚠️ Viable pero ajustado. "
                        f"Ingreso/empleado: ${ingreso_emp:,.0f}")
                else:
                    resultado["recomendacion"] = (
                        f"❌ No recomendable. Ingreso/empleado muy bajo: "
                        f"${ingreso_emp:,.0f}")
            except Exception:
                pass

        return resultado

    # ══════════════════════════════════════════════════════════════════════════
    #  Evaluar optimización de fidelización
    # ══════════════════════════════════════════════════════════════════════════

    def evaluar_fidelizacion(self) -> Dict:
        """Evalúa si el programa de fidelización es rentable o necesita ajuste."""
        resultado = {"tipo": "fidelizacion", "viable": True, "datos": {}, "recomendacion": ""}

        if not self.treasury:
            resultado["recomendacion"] = "Sin datos financieros para evaluar"
            return resultado

        try:
            kpis = self.treasury.kpis_financieros()
            ingresos = kpis.get("ingresos", 0)
            pasivo = kpis.get("pasivo_fidelizacion", 0)
            resultado["datos"]["ingresos_mes"] = ingresos
            resultado["datos"]["pasivo_total"] = pasivo

            if ingresos > 0:
                ratio = pasivo / ingresos * 100
                resultado["datos"]["ratio_pasivo_ingresos"] = round(ratio, 1)

                if ratio > 15:
                    resultado["viable"] = False
                    resultado["recomendacion"] = (
                        f"🔴 Pasivo de fidelización excesivo ({ratio:.1f}% de ingresos).\n"
                        f"Reducir tasa de acumulación de 1.0 a 0.5 estrellas/peso.\n"
                        f"Ahorro estimado: ${pasivo * 0.5:,.0f}")
                elif ratio > 8:
                    resultado["recomendacion"] = (
                        f"🟡 Fidelización costosa ({ratio:.1f}%). "
                        f"Considerar reducir tasa o aumentar mínimo de canje.")
                else:
                    resultado["recomendacion"] = (
                        f"🟢 Fidelización saludable ({ratio:.1f}% de ingresos).")
            else:
                resultado["recomendacion"] = "Sin ingresos para evaluar ratio"
        except Exception as e:
            resultado["recomendacion"] = f"Error: {e}"

        return resultado

    # ══════════════════════════════════════════════════════════════════════════
    #  Plan de crecimiento integral
    # ══════════════════════════════════════════════════════════════════════════

    def plan_crecimiento(self) -> Dict:
        """
        Plan integral de crecimiento basado en datos.
        No requiere IA — usa reglas y datos reales.
        """
        plan = {
            "timestamp": datetime.now().isoformat(),
            "estado_actual": {},
            "oportunidades": [],
            "riesgos": [],
            "acciones_priorizadas": [],
        }

        # Estado actual
        if self.treasury:
            try:
                plan["estado_actual"] = self.treasury.estado_cuenta()
            except Exception:
                pass

        # Oportunidades
        kpis = plan["estado_actual"]
        capital = kpis.get("capital_disponible", 0)
        roi = kpis.get("roi_pct", 0)
        utilidad = kpis.get("utilidad_neta", 0)

        if capital > 100000 and roi > 10:
            plan["oportunidades"].append({
                "tipo": "expansion",
                "titulo": "Capital suficiente para nueva sucursal",
                "detalle": f"${capital:,.0f} disponibles, ROI {roi:.1f}%",
            })

        if utilidad > 0 and roi > 15:
            plan["oportunidades"].append({
                "tipo": "inversion",
                "titulo": "Negocio rentable — invertir en equipo",
                "detalle": f"Margen sólido permite reinversión",
            })

        # Riesgos
        burn = kpis.get("burn_rate_meses", 99)
        if burn < 3:
            plan["riesgos"].append({
                "tipo": "capital",
                "titulo": f"Solo {burn:.1f} meses de capital",
                "severidad": "alta",
            })

        if utilidad < 0:
            plan["riesgos"].append({
                "tipo": "perdida",
                "titulo": "Operando con pérdida",
                "severidad": "crítica",
            })

        # Acciones priorizadas
        if utilidad < 0:
            plan["acciones_priorizadas"].append(
                "1. 🔴 Reducir gastos operativos inmediatamente")
            plan["acciones_priorizadas"].append(
                "2. 🔴 Revisar precios — posible margen insuficiente")
        elif roi < 5:
            plan["acciones_priorizadas"].append(
                "1. 🟡 Optimizar costos para mejorar margen")
            plan["acciones_priorizadas"].append(
                "2. 🟡 Evaluar reducción de nómina vs ingresos")
        else:
            plan["acciones_priorizadas"].append(
                "1. 🟢 Mantener operación — sistema rentable")
            if capital > 100000:
                plan["acciones_priorizadas"].append(
                    "2. 🟢 Evaluar expansión (nueva sucursal o equipo)")
            plan["acciones_priorizadas"].append(
                "3. 🔵 Optimizar fidelización para retención")

        return plan
