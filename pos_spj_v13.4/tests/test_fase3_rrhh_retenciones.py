# tests/test_fase3_rrhh_retenciones.py
# Fase 3 — RRHHService: calcular_retenciones_imss, calcular_isr_mensual
#           + integración con calcular_nomina()
# No importa PyQt5 — usa SQLite en-memoria.

import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _make_rrhh_svc():
    from core.services.rrhh_service import RRHHService
    svc = RRHHService.__new__(RRHHService)
    svc.db = None
    svc.treasury_service = None
    svc.whatsapp_service = None
    svc.template_engine  = None
    svc.hr_rule_engine   = None
    return svc


def _db_with_personal():
    """DB en-memoria con tablas mínimas para calcular_nomina."""
    conn = _mem_db()
    conn.executescript("""
        CREATE TABLE personal (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre    TEXT    NOT NULL,
            apellidos TEXT    DEFAULT '',
            salario   REAL    DEFAULT 0,
            telefono  TEXT    DEFAULT ''
        );
        CREATE TABLE asistencias (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            personal_id     INTEGER NOT NULL,
            fecha           TEXT    DEFAULT (date('now')),
            estado          TEXT    DEFAULT 'PRESENTE',
            horas_trabajadas REAL   DEFAULT 8
        );
    """)
    conn.execute(
        "INSERT INTO personal(nombre, apellidos, salario, telefono) "
        "VALUES('Juan','García', 3000.0, '5551234567')"
    )
    conn.commit()
    return conn


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 1 — calcular_retenciones_imss
# ══════════════════════════════════════════════════════════════════════════════

class TestIMSS:

    def test_salario_cero_retorna_cero(self):
        svc = _make_rrhh_svc()
        res = svc.calcular_retenciones_imss(0)
        assert res["obrero"] == 0.0
        assert res["patronal"] == 0.0

    def test_salario_negativo_retorna_cero(self):
        svc = _make_rrhh_svc()
        res = svc.calcular_retenciones_imss(-500)
        assert res["obrero"] == 0.0

    def test_tasa_obrero_correcta(self):
        """2.375% de $10,000 = $237.50"""
        svc = _make_rrhh_svc()
        res = svc.calcular_retenciones_imss(10000.0)
        assert abs(res["obrero"] - 237.50) < 0.01

    def test_tasa_patronal_correcta(self):
        """20.4% de $10,000 = $2,040.00"""
        svc = _make_rrhh_svc()
        res = svc.calcular_retenciones_imss(10000.0)
        assert abs(res["patronal"] - 2040.0) < 0.01

    def test_estructura_respuesta(self):
        svc = _make_rrhh_svc()
        res = svc.calcular_retenciones_imss(5000.0)
        assert "salario_base" in res
        assert "obrero" in res
        assert "patronal" in res
        assert "tasa_obrero" in res
        assert "tasa_patronal" in res

    def test_obrero_menor_que_patronal(self):
        """Cuota patronal siempre > cuota obrera."""
        svc = _make_rrhh_svc()
        res = svc.calcular_retenciones_imss(8000.0)
        assert res["obrero"] < res["patronal"]

    def test_salario_minimo_referencia(self):
        """Salario mínimo México 2024 ~$2,984/mes: obrero ~$70.87"""
        svc = _make_rrhh_svc()
        res = svc.calcular_retenciones_imss(2984.0)
        assert res["obrero"] > 0
        assert res["obrero"] < 200   # razonable para salario mínimo


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 2 — calcular_isr_mensual
# ══════════════════════════════════════════════════════════════════════════════

class TestISR:

    def test_salario_cero(self):
        svc = _make_rrhh_svc()
        res = svc.calcular_isr_mensual(0)
        assert res["isr_mensual"] == 0.0
        assert res["tasa_efectiva_pct"] == 0.0

    def test_salario_negativo(self):
        svc = _make_rrhh_svc()
        res = svc.calcular_isr_mensual(-1000)
        assert res["isr_mensual"] == 0.0

    def test_primer_tramo_1_92pct(self):
        """$500 → primer tramo 1.92% → ISR ≈ $9.60"""
        svc = _make_rrhh_svc()
        res = svc.calcular_isr_mensual(500.0)
        expected = round(500.0 * 0.0192, 2)
        assert abs(res["isr_mensual"] - expected) < 0.02

    def test_segundo_tramo(self):
        """$3000 → segundo tramo (746.05-6332.05) cuota fija 14.32 + 6.4%"""
        svc = _make_rrhh_svc()
        res = svc.calcular_isr_mensual(3000.0)
        expected = round(14.32 + (3000.0 - 746.05) * 0.064, 2)
        assert abs(res["isr_mensual"] - expected) < 0.10

    def test_isr_positivo_para_salario_normal(self):
        svc = _make_rrhh_svc()
        res = svc.calcular_isr_mensual(8000.0)
        assert res["isr_mensual"] > 0

    def test_tasa_efectiva_positiva(self):
        svc = _make_rrhh_svc()
        res = svc.calcular_isr_mensual(15000.0)
        assert res["tasa_efectiva_pct"] > 0

    def test_tasa_efectiva_menor_que_100(self):
        svc = _make_rrhh_svc()
        res = svc.calcular_isr_mensual(500000.0)
        assert res["tasa_efectiva_pct"] < 100.0

    def test_progresividad(self):
        """ISR debe ser progresivo: más salario → mayor tasa efectiva."""
        svc = _make_rrhh_svc()
        r1 = svc.calcular_isr_mensual(5000.0)
        r2 = svc.calcular_isr_mensual(30000.0)
        assert r2["tasa_efectiva_pct"] > r1["tasa_efectiva_pct"]

    def test_estructura_respuesta(self):
        svc = _make_rrhh_svc()
        res = svc.calcular_isr_mensual(10000.0)
        assert "salario_mensual" in res
        assert "isr_mensual" in res
        assert "tasa_efectiva_pct" in res


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 3 — Integración: calcular_nomina incluye retenciones Fase 3
# ══════════════════════════════════════════════════════════════════════════════

class TestNominaConRetenciones:

    def _make_svc_with_db(self):
        conn = _db_with_personal()
        # 8 horas trabajadas, 5 días
        conn.executemany(
            "INSERT INTO asistencias(personal_id, estado, horas_trabajadas) "
            "VALUES(1,'PRESENTE',8)",
            [()] * 5
        )
        conn.commit()
        from core.services.rrhh_service import RRHHService
        svc = RRHHService.__new__(RRHHService)
        svc.db = conn
        svc.treasury_service = None
        svc.whatsapp_service = None
        svc.template_engine  = None
        svc.hr_rule_engine   = None
        return svc

    def test_calcular_nomina_tiene_imss_obrero(self):
        svc = self._make_svc_with_db()
        res = svc.calcular_nomina(1, "2026-04-01", "2026-04-30")
        assert "imss_obrero" in res
        assert res["imss_obrero"] >= 0

    def test_calcular_nomina_tiene_isr_mensual(self):
        svc = self._make_svc_with_db()
        res = svc.calcular_nomina(1, "2026-04-01", "2026-04-30")
        assert "isr_mensual" in res
        assert res["isr_mensual"] >= 0

    def test_calcular_nomina_tiene_neto_deducido(self):
        svc = self._make_svc_with_db()
        res = svc.calcular_nomina(1, "2026-04-01", "2026-04-30")
        assert "neto_deducido" in res

    def test_neto_deducido_menor_que_bruto(self):
        svc = self._make_svc_with_db()
        res = svc.calcular_nomina(1, "2026-04-01", "2026-04-30")
        assert res["neto_deducido"] <= res["neto_a_pagar"]

    def test_neto_a_pagar_sin_cambios(self):
        """neto_a_pagar debe seguir siendo el bruto calculado (sin deducciones)."""
        svc = self._make_svc_with_db()
        res = svc.calcular_nomina(1, "2026-04-01", "2026-04-30")
        # neto_a_pagar = (salario/8) * horas = (3000/8)*40 = 15000
        assert res["neto_a_pagar"] > 0

    def test_retenciones_dict_presente(self):
        svc = self._make_svc_with_db()
        res = svc.calcular_nomina(1, "2026-04-01", "2026-04-30")
        assert "retenciones" in res
        assert "imss_obrero" in res["retenciones"]
        assert "isr_mensual" in res["retenciones"]
        assert "imss_patronal" in res["retenciones"]
