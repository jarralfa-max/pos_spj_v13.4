# tests/test_fase11_hr_rule_engine.py
"""
FASE 11 — HRRuleEngine: motor de reglas laborales NOM-035 / LFT México.

Verifica: días consecutivos, descanso, nómina vencida, horas extra, cobertura.
Sin dependencia de PyQt5.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ── helpers ───────────────────────────────────────────────────────────────────

def _mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _setup_schema(conn):
    conn.executescript("""
        CREATE TABLE personal (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre      TEXT    NOT NULL,
            apellidos   TEXT    DEFAULT '',
            sucursal_id INTEGER DEFAULT 1,
            activo      INTEGER DEFAULT 1
        );
        CREATE TABLE asistencias (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            personal_id      INTEGER NOT NULL,
            fecha            TEXT    NOT NULL,
            estado           TEXT    DEFAULT 'PRESENTE',
            horas_trabajadas REAL    DEFAULT 8.0,
            UNIQUE(personal_id, fecha)
        );
        CREATE TABLE nomina_pagos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado_id INTEGER NOT NULL,
            fecha       TEXT    NOT NULL,
            estado      TEXT    DEFAULT 'pagado'
        );
    """)


def _add_empleado(conn, nombre="Juan", apellidos="Lopez",
                  sucursal_id=1, activo=1):
    cur = conn.execute(
        "INSERT INTO personal (nombre, apellidos, sucursal_id, activo) "
        "VALUES (?,?,?,?)",
        (nombre, apellidos, sucursal_id, activo),
    )
    conn.commit()
    return cur.lastrowid


def _add_asistencias(conn, empleado_id, fechas,
                     estado="PRESENTE", horas=8.0):
    for f in fechas:
        fecha_str = f.isoformat() if hasattr(f, "isoformat") else f
        conn.execute(
            "INSERT OR IGNORE INTO asistencias "
            "(personal_id, fecha, estado, horas_trabajadas) VALUES (?,?,?,?)",
            (empleado_id, fecha_str, estado, horas),
        )
    conn.commit()


def _make_engine(conn):
    from core.services.hr_rule_engine import HRRuleEngine
    return HRRuleEngine(db_conn=conn, module_config=None)


# ── constantes laborales ──────────────────────────────────────────────────────

class TestConstantesLaborales:
    def test_constantes_cumplen_lft(self):
        from core.services.hr_rule_engine import (
            MAX_CONSECUTIVE_DAYS, MAX_WEEKLY_HOURS,
            MIN_COVERAGE, PAYROLL_PERIOD_DAYS,
        )
        assert MAX_CONSECUTIVE_DAYS == 6
        assert MAX_WEEKLY_HOURS == 48
        assert MIN_COVERAGE >= 1
        assert PAYROLL_PERIOD_DAYS > 0

    def test_max_consecutive_days_en_resultado(self):
        conn = _mem_db()
        _setup_schema(conn)
        emp_id = _add_empleado(conn)
        engine = _make_engine(conn)
        r = engine.verificar_dias_consecutivos(emp_id)
        assert r["max_permitido"] == 6


# ── verificar_dias_consecutivos ───────────────────────────────────────────────

class TestDiasConsecutivos:
    def test_sin_asistencias_retorna_cero(self):
        conn = _mem_db()
        _setup_schema(conn)
        emp_id = _add_empleado(conn)
        engine = _make_engine(conn)
        r = engine.verificar_dias_consecutivos(emp_id)
        assert r["dias_consecutivos"] == 0
        assert r["requiere_descanso"] is False
        assert r["alerta"] == "OK"

    def test_cinco_dias_no_requiere_descanso(self):
        conn = _mem_db()
        _setup_schema(conn)
        emp_id = _add_empleado(conn)
        today = date.today()
        _add_asistencias(conn, emp_id, [today - timedelta(days=i) for i in range(5)])
        engine = _make_engine(conn)
        r = engine.verificar_dias_consecutivos(emp_id)
        assert r["dias_consecutivos"] == 5
        assert r["requiere_descanso"] is False

    def test_seis_dias_requiere_descanso(self):
        conn = _mem_db()
        _setup_schema(conn)
        emp_id = _add_empleado(conn)
        today = date.today()
        _add_asistencias(conn, emp_id, [today - timedelta(days=i) for i in range(6)])
        engine = _make_engine(conn)
        r = engine.verificar_dias_consecutivos(emp_id)
        assert r["dias_consecutivos"] == 6
        assert r["requiere_descanso"] is True
        assert r["alerta"] == "OVERWORK"

    def test_retardo_cuenta_como_laboral(self):
        conn = _mem_db()
        _setup_schema(conn)
        emp_id = _add_empleado(conn)
        today = date.today()
        fechas = [today - timedelta(days=i) for i in range(6)]
        _add_asistencias(conn, emp_id, fechas[:3], estado="PRESENTE")
        _add_asistencias(conn, emp_id, fechas[3:], estado="RETARDO")
        engine = _make_engine(conn)
        r = engine.verificar_dias_consecutivos(emp_id)
        assert r["dias_consecutivos"] == 6
        assert r["requiere_descanso"] is True

    def test_brecha_interrumpe_consecutivos(self):
        conn = _mem_db()
        _setup_schema(conn)
        emp_id = _add_empleado(conn)
        today = date.today()
        # días 0, 1, 2 presentes; día 3 ausente; días 4, 5 también presentes
        fechas = [today - timedelta(days=i) for i in (0, 1, 2)]
        _add_asistencias(conn, emp_id, fechas)
        engine = _make_engine(conn)
        r = engine.verificar_dias_consecutivos(emp_id)
        assert r["dias_consecutivos"] == 3

    def test_resultado_incluye_empleado_id(self):
        conn = _mem_db()
        _setup_schema(conn)
        emp_id = _add_empleado(conn)
        engine = _make_engine(conn)
        r = engine.verificar_dias_consecutivos(emp_id)
        assert r["empleado_id"] == emp_id


# ── programar_descanso ────────────────────────────────────────────────────────

class TestProgramarDescanso:
    def test_empleado_inexistente_retorna_error(self):
        conn = _mem_db()
        _setup_schema(conn)
        engine = _make_engine(conn)
        r = engine.programar_descanso(9999)
        assert r["ok"] is False
        assert "error" in r

    def test_programar_descanso_exitoso(self):
        conn = _mem_db()
        _setup_schema(conn)
        emp_id = _add_empleado(conn, nombre="Ana", apellidos="Ruiz")
        engine = _make_engine(conn)
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        r = engine.programar_descanso(emp_id, fecha_descanso=tomorrow)
        assert r["ok"] is True
        assert r["fecha_descanso"] == tomorrow
        assert r["empleado_id"] == emp_id

    def test_programar_descanso_inserta_en_asistencias(self):
        conn = _mem_db()
        _setup_schema(conn)
        emp_id = _add_empleado(conn)
        engine = _make_engine(conn)
        fecha = (date.today() + timedelta(days=2)).isoformat()
        engine.programar_descanso(emp_id, fecha_descanso=fecha)
        row = conn.execute(
            "SELECT estado FROM asistencias WHERE personal_id=? AND fecha=?",
            (emp_id, fecha),
        ).fetchone()
        assert row is not None
        assert row[0] == "DESCANSO"

    def test_programar_sin_fecha_usa_manana(self):
        conn = _mem_db()
        _setup_schema(conn)
        emp_id = _add_empleado(conn)
        engine = _make_engine(conn)
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        r = engine.programar_descanso(emp_id)
        assert r["ok"] is True
        assert r["fecha_descanso"] == tomorrow


# ── auditar_nomina_pendiente ───────────────────────────────────────────────────

class TestAuditarNominaPendiente:
    def test_sin_empleados_retorna_lista_vacia(self):
        conn = _mem_db()
        _setup_schema(conn)
        engine = _make_engine(conn)
        assert engine.auditar_nomina_pendiente() == []

    def test_empleado_sin_pago_aparece_como_pendiente(self):
        conn = _mem_db()
        _setup_schema(conn)
        emp_id = _add_empleado(conn, nombre="Pedro", apellidos="Gomez")
        engine = _make_engine(conn)
        result = engine.auditar_nomina_pendiente(dias_aviso=30)
        assert len(result) == 1
        assert result[0]["empleado_id"] == emp_id
        assert result[0]["vencida"] is True

    def test_empleado_con_pago_reciente_no_aparece(self):
        conn = _mem_db()
        _setup_schema(conn)
        emp_id = _add_empleado(conn)
        hoy = date.today()
        conn.execute(
            "INSERT INTO nomina_pagos (empleado_id, fecha, estado) VALUES (?,?,?)",
            (emp_id, hoy.isoformat(), "pagado"),
        )
        conn.commit()
        engine = _make_engine(conn)
        result = engine.auditar_nomina_pendiente(dias_aviso=2)
        assert len(result) == 0

    def test_empleado_con_pago_vencido_aparece(self):
        conn = _mem_db()
        _setup_schema(conn)
        emp_id = _add_empleado(conn)
        hace_10 = (date.today() - timedelta(days=10)).isoformat()
        conn.execute(
            "INSERT INTO nomina_pagos (empleado_id, fecha, estado) VALUES (?,?,?)",
            (emp_id, hace_10, "pagado"),
        )
        conn.commit()
        engine = _make_engine(conn)
        result = engine.auditar_nomina_pendiente(dias_aviso=2)
        assert len(result) == 1
        assert result[0]["vencida"] is True

    def test_resultado_incluye_campos_esperados(self):
        conn = _mem_db()
        _setup_schema(conn)
        _add_empleado(conn)
        engine = _make_engine(conn)
        result = engine.auditar_nomina_pendiente(dias_aviso=30)
        assert len(result) >= 1
        for key in ("empleado_id", "nombre", "sucursal_id",
                    "ultimo_pago", "dias_vencimiento", "vencida"):
            assert key in result[0]


# ── verificar_horas_semanales ─────────────────────────────────────────────────

class TestVerificarHorasSemanales:
    def test_horas_dentro_del_limite(self):
        conn = _mem_db()
        _setup_schema(conn)
        emp_id = _add_empleado(conn)
        lunes = date.today() - timedelta(days=date.today().weekday())
        fechas = [lunes + timedelta(days=i) for i in range(5)]
        _add_asistencias(conn, emp_id, fechas, horas=8.0)  # 40 hrs
        engine = _make_engine(conn)
        r = engine.verificar_horas_semanales(emp_id, lunes.isoformat())
        assert r["horas_totales"] == 40.0
        assert r["excede_limite"] is False
        assert r["horas_extra"] == 0.0

    def test_horas_superando_limite(self):
        conn = _mem_db()
        _setup_schema(conn)
        emp_id = _add_empleado(conn)
        lunes = date.today() - timedelta(days=date.today().weekday())
        fechas = [lunes + timedelta(days=i) for i in range(6)]
        _add_asistencias(conn, emp_id, fechas, horas=9.0)  # 54 hrs
        engine = _make_engine(conn)
        r = engine.verificar_horas_semanales(emp_id, lunes.isoformat())
        assert r["horas_totales"] == 54.0
        assert r["excede_limite"] is True
        assert r["horas_extra"] == 6.0

    def test_retardo_cuenta_en_horas(self):
        conn = _mem_db()
        _setup_schema(conn)
        emp_id = _add_empleado(conn)
        lunes = date.today() - timedelta(days=date.today().weekday())
        _add_asistencias(conn, emp_id, [lunes], estado="RETARDO", horas=50.0)
        engine = _make_engine(conn)
        r = engine.verificar_horas_semanales(emp_id, lunes.isoformat())
        assert r["horas_totales"] == 50.0
        assert r["excede_limite"] is True

    def test_resultado_incluye_campos_esperados(self):
        conn = _mem_db()
        _setup_schema(conn)
        emp_id = _add_empleado(conn)
        engine = _make_engine(conn)
        r = engine.verificar_horas_semanales(emp_id)
        for key in ("empleado_id", "semana_inicio", "semana_fin",
                    "horas_totales", "max_legal", "horas_extra", "excede_limite"):
            assert key in r
        assert r["max_legal"] == 48


# ── validar_cobertura ─────────────────────────────────────────────────────────

class TestValidarCobertura:
    def test_sin_empleados_cobertura_falla(self):
        conn = _mem_db()
        _setup_schema(conn)
        engine = _make_engine(conn)
        r = engine.validar_cobertura(sucursal_id=1)
        assert r["cobertura_ok"] is False
        assert r["empleados_activos"] == 0

    def test_con_empleado_activo_cobertura_ok(self):
        conn = _mem_db()
        _setup_schema(conn)
        emp_id = _add_empleado(conn, sucursal_id=1)
        today = date.today()
        _add_asistencias(conn, emp_id, [today])
        engine = _make_engine(conn)
        r = engine.validar_cobertura(sucursal_id=1)
        assert r["cobertura_ok"] is True
        assert r["empleados_activos"] >= 1

    def test_resultado_incluye_fecha_especificada(self):
        conn = _mem_db()
        _setup_schema(conn)
        engine = _make_engine(conn)
        fecha = "2026-01-01"
        r = engine.validar_cobertura(sucursal_id=1, fecha=fecha)
        assert r["fecha"] == fecha
        assert r["sucursal_id"] == 1

    def test_resultado_incluye_cobertura_minima(self):
        conn = _mem_db()
        _setup_schema(conn)
        engine = _make_engine(conn)
        r = engine.validar_cobertura(sucursal_id=1)
        assert "cobertura_minima" in r
        assert r["cobertura_minima"] >= 1


# ── auditar_sucursal ──────────────────────────────────────────────────────────

class TestAuditarSucursal:
    def test_sucursal_sin_empleados(self):
        conn = _mem_db()
        _setup_schema(conn)
        engine = _make_engine(conn)
        r = engine.auditar_sucursal(sucursal_id=1)
        assert r["empleados_total"] == 0
        assert r["overwork"] == []
        assert r["descansos_sugeridos"] == []

    def test_detecta_overwork(self):
        conn = _mem_db()
        _setup_schema(conn)
        emp_id = _add_empleado(conn, sucursal_id=1)
        today = date.today()
        _add_asistencias(conn, emp_id, [today - timedelta(days=i) for i in range(6)])
        engine = _make_engine(conn)
        r = engine.auditar_sucursal(sucursal_id=1)
        assert len(r["overwork"]) == 1
        assert r["overwork"][0]["empleado_id"] == emp_id
        assert r["overwork"][0]["dias_consecutivos"] == 6

    def test_informe_incluye_campos_esperados(self):
        conn = _mem_db()
        _setup_schema(conn)
        engine = _make_engine(conn)
        r = engine.auditar_sucursal(sucursal_id=1)
        for key in ("sucursal_id", "fecha", "empleados_total",
                    "activos_hoy", "overwork", "descansos_sugeridos", "cobertura_ok"):
            assert key in r

    def test_auditoria_persiste_en_log(self):
        conn = _mem_db()
        _setup_schema(conn)
        engine = _make_engine(conn)
        engine.auditar_sucursal(sucursal_id=2)
        row = conn.execute(
            "SELECT COUNT(*) FROM hr_auditoria_log WHERE sucursal_id=2"
        ).fetchone()
        assert row[0] >= 1

    def test_sucursal_id_en_resultado(self):
        conn = _mem_db()
        _setup_schema(conn)
        engine = _make_engine(conn)
        r = engine.auditar_sucursal(sucursal_id=5)
        assert r["sucursal_id"] == 5

    def test_fecha_personalizada(self):
        conn = _mem_db()
        _setup_schema(conn)
        engine = _make_engine(conn)
        r = engine.auditar_sucursal(sucursal_id=1, fecha="2026-03-15")
        assert r["fecha"] == "2026-03-15"


# ── registrar_pago_auditado ───────────────────────────────────────────────────

class TestRegistrarPagoAuditado:
    def test_registra_en_hr_pago_log(self):
        conn = _mem_db()
        _setup_schema(conn)
        engine = _make_engine(conn)
        engine.registrar_pago_auditado(
            empleado_id=42, nombre="Maria Perez",
            periodo="2026-01", total=8000.0, sucursal_id=1,
        )
        row = conn.execute(
            "SELECT total FROM hr_pago_log WHERE empleado_id=42"
        ).fetchone()
        assert row is not None
        assert abs(row[0] - 8000.0) < 0.01

    def test_registrar_no_falla_sin_bus(self):
        conn = _mem_db()
        _setup_schema(conn)
        engine = _make_engine(conn)
        engine._bus = None
        engine.registrar_pago_auditado(1, "Test Usuario", "2026-01", 1000.0)

    def test_multiples_pagos_se_acumulan(self):
        conn = _mem_db()
        _setup_schema(conn)
        engine = _make_engine(conn)
        engine.registrar_pago_auditado(7, "Emp A", "2026-01", 5000.0)
        engine.registrar_pago_auditado(7, "Emp A", "2026-02", 5500.0)
        count = conn.execute(
            "SELECT COUNT(*) FROM hr_pago_log WHERE empleado_id=7"
        ).fetchone()[0]
        assert count == 2


# ── _ensure_tables ────────────────────────────────────────────────────────────

class TestEnsureTables:
    def test_ensure_tables_crea_hr_auditoria_log(self):
        conn = _mem_db()
        _setup_schema(conn)
        _make_engine(conn)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='hr_auditoria_log'"
        ).fetchone()
        assert row is not None

    def test_ensure_tables_crea_hr_pago_log(self):
        conn = _mem_db()
        _setup_schema(conn)
        _make_engine(conn)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='hr_pago_log'"
        ).fetchone()
        assert row is not None
