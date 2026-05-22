# tests/test_fase11_expansion_analyzer.py
"""
FASE 11 — ExpansionAnalyzer: evaluación estratégica de expansión.

Sin dependencia de PyQt5 — servicios dependientes mockeados con SimpleNamespace.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_analyzer(**kwargs):
    from core.services.expansion_analyzer import ExpansionAnalyzer
    return ExpansionAnalyzer(**kwargs)


def _treasury(capital=200000.0, utilidad=20000.0, roi_pct=15.0,
              burn_rate=12.0, ingresos=100000.0, pasivo_fidelizacion=5000.0):
    return SimpleNamespace(
        estado_cuenta=lambda: {
            "capital_disponible": capital,
            "salud": "buena",
            "utilidad_neta": utilidad,
            "roi_pct": roi_pct,
            "burn_rate_meses": burn_rate,
        },
        kpis_financieros=lambda: {
            "ingresos": ingresos,
            "pasivo_fidelizacion": pasivo_fidelizacion,
        },
    )


def _simulator(meses_roi=10):
    return SimpleNamespace(
        simular_nueva_sucursal=lambda **kw: {"meses_para_roi": meses_roi}
    )


def _franchise(ingreso_por_empleado=25000, utilidad_peor=5000):
    return SimpleNamespace(
        ranking_sucursales=lambda: [
            {"nombre": "Principal", "ingresos": 80000, "utilidad_estimada": utilidad_peor},
        ],
        eficiencia_sucursal=lambda sid: {
            "ingreso_por_empleado": ingreso_por_empleado
        },
    )


# ── evaluar_nueva_sucursal ────────────────────────────────────────────────────

class TestEvaluarNuevaSucursal:
    def test_capital_insuficiente_retorna_no_viable(self):
        analyzer = _make_analyzer(treasury_service=_treasury(capital=50000))
        r = analyzer.evaluar_nueva_sucursal(inversion_inicial=100000)
        assert r["viable"] is False
        assert "Capital insuficiente" in r["razon"]

    def test_capital_suficiente_sin_simulator_retorna_viable(self):
        analyzer = _make_analyzer(treasury_service=_treasury(capital=300000))
        r = analyzer.evaluar_nueva_sucursal(inversion_inicial=100000)
        assert r["viable"] is True

    def test_roi_corto_confianza_alta(self):
        analyzer = _make_analyzer(
            treasury_service=_treasury(capital=500000),
            simulator=_simulator(meses_roi=8),
        )
        r = analyzer.evaluar_nueva_sucursal(inversion_inicial=100000)
        assert r["viable"] is True
        assert r["confianza"] == "alta"

    def test_roi_medio_confianza_media(self):
        analyzer = _make_analyzer(
            treasury_service=_treasury(capital=500000),
            simulator=_simulator(meses_roi=18),
        )
        r = analyzer.evaluar_nueva_sucursal(inversion_inicial=100000)
        assert r["viable"] is True
        assert r["confianza"] == "media"

    def test_roi_largo_no_viable(self):
        analyzer = _make_analyzer(
            treasury_service=_treasury(capital=500000),
            simulator=_simulator(meses_roi=36),
        )
        r = analyzer.evaluar_nueva_sucursal(inversion_inicial=100000)
        assert r["viable"] is False

    def test_resultado_incluye_tipo(self):
        analyzer = _make_analyzer()
        r = analyzer.evaluar_nueva_sucursal()
        assert r["tipo"] == "nueva_sucursal"

    def test_sucursal_en_perdida_bloquea_expansion(self):
        franchise = SimpleNamespace(
            ranking_sucursales=lambda: [
                {"nombre": "Mala", "ingresos": 0, "utilidad_estimada": -5000}
            ],
            eficiencia_sucursal=lambda sid: {},
        )
        analyzer = _make_analyzer(
            treasury_service=_treasury(capital=500000),
            franchise_manager=franchise,
        )
        r = analyzer.evaluar_nueva_sucursal(inversion_inicial=100000)
        assert r["viable"] is False
        assert "pérdida" in r["razon"] or "perdida" in r["razon"].lower()

    def test_sin_dependencias_retorna_estructura_valida(self):
        analyzer = _make_analyzer()
        r = analyzer.evaluar_nueva_sucursal()
        for key in ("tipo", "viable", "confianza", "razon", "datos", "recomendacion"):
            assert key in r


# ── evaluar_compra_equipo ─────────────────────────────────────────────────────

class TestEvaluarCompraEquipo:
    def test_calcula_depreciacion_mensual(self):
        analyzer = _make_analyzer()
        r = analyzer.evaluar_compra_equipo("Horno", 60000, vida_util_anios=5)
        assert abs(r["datos"]["depreciacion_mensual"] - 1000.0) < 0.1

    def test_roi_dentro_vida_util_viable(self):
        analyzer = _make_analyzer()
        r = analyzer.evaluar_compra_equipo("Horno", 12000,
                                            vida_util_anios=5,
                                            ahorro_mensual=1000)
        assert r["viable"] is True
        assert abs(r["datos"]["meses_roi"] - 12.0) < 0.1

    def test_roi_fuera_vida_util_no_viable(self):
        analyzer = _make_analyzer()
        r = analyzer.evaluar_compra_equipo("Máquina", 120000,
                                            vida_util_anios=5,
                                            ahorro_mensual=100)
        assert r["viable"] is False

    def test_sin_ahorro_no_viable(self):
        analyzer = _make_analyzer()
        r = analyzer.evaluar_compra_equipo("Equipo", 50000)
        assert r["viable"] is False

    def test_resultado_incluye_tipo(self):
        analyzer = _make_analyzer()
        r = analyzer.evaluar_compra_equipo("X", 1000)
        assert r["tipo"] == "compra_equipo"

    def test_capital_alto_pct_bajo(self):
        analyzer = _make_analyzer(treasury_service=_treasury(capital=1000000))
        r = analyzer.evaluar_compra_equipo("Equipo", 10000,
                                            ahorro_mensual=500)
        assert "pct_del_capital" in r["datos"]
        assert r["datos"]["pct_del_capital"] < 5.0


# ── evaluar_contratacion ──────────────────────────────────────────────────────

class TestEvaluarContratacion:
    def test_sin_franchise_retorna_estructura_basica(self):
        analyzer = _make_analyzer()
        r = analyzer.evaluar_contratacion(cantidad=2, salario=7000)
        assert r["tipo"] == "contratacion"
        assert "costo_mensual_total" in r["datos"]
        assert abs(r["datos"]["costo_mensual_total"] - 2 * 7000 * 1.35) < 1

    def test_ingreso_triple_salario_viable(self):
        analyzer = _make_analyzer(
            franchise_manager=_franchise(ingreso_por_empleado=21001)
        )
        r = analyzer.evaluar_contratacion(cantidad=1, salario=7000)
        assert r["viable"] is True
        assert "✅" in r.get("recomendacion", "")

    def test_ingreso_bajo_no_viable(self):
        analyzer = _make_analyzer(
            franchise_manager=_franchise(ingreso_por_empleado=5000)
        )
        r = analyzer.evaluar_contratacion(cantidad=1, salario=7000)
        assert r["viable"] is False

    def test_ingreso_entre_1_5x_y_3x_viable_con_precaucion(self):
        analyzer = _make_analyzer(
            franchise_manager=_franchise(ingreso_por_empleado=12000)
        )
        r = analyzer.evaluar_contratacion(cantidad=1, salario=7000)
        assert r["viable"] is True
        assert "⚠️" in r.get("recomendacion", "")


# ── evaluar_fidelizacion ──────────────────────────────────────────────────────

class TestEvaluarFidelizacion:
    def test_sin_treasury_mensaje_sin_datos(self):
        analyzer = _make_analyzer()
        r = analyzer.evaluar_fidelizacion()
        assert r["tipo"] == "fidelizacion"
        assert "Sin datos" in r["recomendacion"]

    def test_pasivo_bajo_verde(self):
        analyzer = _make_analyzer(
            treasury_service=_treasury(ingresos=100000, pasivo_fidelizacion=5000)
        )
        r = analyzer.evaluar_fidelizacion()
        assert "🟢" in r["recomendacion"]

    def test_pasivo_medio_amarillo(self):
        analyzer = _make_analyzer(
            treasury_service=_treasury(ingresos=100000, pasivo_fidelizacion=10000)
        )
        r = analyzer.evaluar_fidelizacion()
        assert "🟡" in r["recomendacion"]

    def test_pasivo_alto_no_viable(self):
        analyzer = _make_analyzer(
            treasury_service=_treasury(ingresos=100000, pasivo_fidelizacion=20000)
        )
        r = analyzer.evaluar_fidelizacion()
        assert r["viable"] is False
        assert "🔴" in r["recomendacion"]

    def test_resultado_incluye_ratio(self):
        analyzer = _make_analyzer(
            treasury_service=_treasury(ingresos=100000, pasivo_fidelizacion=5000)
        )
        r = analyzer.evaluar_fidelizacion()
        assert "ratio_pasivo_ingresos" in r["datos"]
        assert abs(r["datos"]["ratio_pasivo_ingresos"] - 5.0) < 0.1


# ── plan_crecimiento ──────────────────────────────────────────────────────────

class TestPlanCrecimiento:
    def test_retorna_estructura_correcta(self):
        analyzer = _make_analyzer()
        plan = analyzer.plan_crecimiento()
        for key in ("timestamp", "estado_actual", "oportunidades",
                    "riesgos", "acciones_priorizadas"):
            assert key in plan

    def test_capital_alto_roi_bueno_agrega_oportunidad_expansion(self):
        analyzer = _make_analyzer(
            treasury_service=_treasury(capital=150000, roi_pct=15.0, utilidad=20000)
        )
        plan = analyzer.plan_crecimiento()
        tipos = [o["tipo"] for o in plan["oportunidades"]]
        assert "expansion" in tipos

    def test_perdida_agrega_riesgo_y_accion_urgente(self):
        treasury = SimpleNamespace(
            estado_cuenta=lambda: {
                "capital_disponible": 10000,
                "utilidad_neta": -5000,
                "roi_pct": -10,
                "burn_rate_meses": 2,
            }
        )
        analyzer = _make_analyzer(treasury_service=treasury)
        plan = analyzer.plan_crecimiento()
        tipos_riesgo = [r["tipo"] for r in plan["riesgos"]]
        assert "perdida" in tipos_riesgo
        assert any("🔴" in a for a in plan["acciones_priorizadas"])

    def test_burn_rate_bajo_agrega_riesgo_capital(self):
        treasury = SimpleNamespace(
            estado_cuenta=lambda: {
                "capital_disponible": 5000,
                "utilidad_neta": 0,
                "roi_pct": 0,
                "burn_rate_meses": 1.5,
            }
        )
        analyzer = _make_analyzer(treasury_service=treasury)
        plan = analyzer.plan_crecimiento()
        tipos = [r["tipo"] for r in plan["riesgos"]]
        assert "capital" in tipos

    def test_sin_treasury_no_falla(self):
        analyzer = _make_analyzer()
        plan = analyzer.plan_crecimiento()
        assert isinstance(plan["oportunidades"], list)
        assert isinstance(plan["riesgos"], list)

    def test_roi_bajo_agrega_accion_optimizar(self):
        treasury = SimpleNamespace(
            estado_cuenta=lambda: {
                "capital_disponible": 50000,
                "utilidad_neta": 1000,
                "roi_pct": 3,
                "burn_rate_meses": 10,
            }
        )
        analyzer = _make_analyzer(treasury_service=treasury)
        plan = analyzer.plan_crecimiento()
        assert any("🟡" in a for a in plan["acciones_priorizadas"])

    def test_negocio_rentable_con_capital_sugiere_expansion(self):
        treasury = SimpleNamespace(
            estado_cuenta=lambda: {
                "capital_disponible": 200000,
                "utilidad_neta": 30000,
                "roi_pct": 20,
                "burn_rate_meses": 24,
            }
        )
        analyzer = _make_analyzer(treasury_service=treasury)
        plan = analyzer.plan_crecimiento()
        all_actions = " ".join(plan["acciones_priorizadas"])
        assert "expansión" in all_actions or "expansion" in all_actions.lower()
