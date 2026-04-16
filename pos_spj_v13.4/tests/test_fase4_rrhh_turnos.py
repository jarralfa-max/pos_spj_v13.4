# tests/test_fase4_rrhh_turnos.py
# Fase 4 — RRHH: nómina con retenciones y turnos
# Verifica calcular_nomina() con retenciones ISR/IMSS (Fase 3 aditivo)
# y la estructura de datos de turno_asignaciones.
import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def rrhh_db():
    """BD en memoria con tablas de personal y asistencias."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE personal (
            id INTEGER PRIMARY KEY,
            nombre TEXT, apellidos TEXT,
            salario REAL DEFAULT 0.0,
            telefono TEXT DEFAULT ''
        );
        CREATE TABLE asistencias (
            id INTEGER PRIMARY KEY,
            personal_id INTEGER,
            fecha TEXT,
            horas_trabajadas REAL DEFAULT 0.0,
            estado TEXT DEFAULT 'PRESENTE'
        );
        -- Semana completa: 5 días x 8 hrs = 40 horas
        INSERT INTO personal VALUES (1, 'Juan', 'García', 8000.0, '+521234567890');
        INSERT INTO asistencias VALUES (1, 1, '2026-04-07', 8.0, 'PRESENTE');
        INSERT INTO asistencias VALUES (2, 1, '2026-04-08', 8.0, 'PRESENTE');
        INSERT INTO asistencias VALUES (3, 1, '2026-04-09', 8.0, 'PRESENTE');
        INSERT INTO asistencias VALUES (4, 1, '2026-04-10', 8.0, 'PRESENTE');
        INSERT INTO asistencias VALUES (5, 1, '2026-04-11', 8.0, 'RETARDO');
    """)
    conn.commit()
    return conn


def _make_rrhh(rrhh_db):
    from core.services.rrhh_service import RRHHService
    return RRHHService(rrhh_db, MagicMock(), MagicMock(), MagicMock())


# ── Estructura de retorno de calcular_nomina ──────────────────────────────────

def test_calcular_nomina_retorna_dict(rrhh_db):
    svc = _make_rrhh(rrhh_db)
    nomina = svc.calcular_nomina(1, '2026-04-07', '2026-04-11')
    assert isinstance(nomina, dict)


def test_calcular_nomina_campos_requeridos(rrhh_db):
    """Todos los campos de nómina deben estar presentes."""
    svc = _make_rrhh(rrhh_db)
    nomina = svc.calcular_nomina(1, '2026-04-07', '2026-04-11')
    campos = ['empleado_id', 'nombre_completo', 'dias_asistidos',
              'total_horas', 'salario_base', 'neto_a_pagar',
              'imss_obrero', 'isr_mensual', 'neto_deducido', 'retenciones']
    for campo in campos:
        assert campo in nomina, f"Campo '{campo}' faltante en nómina"


def test_calcular_nomina_horas_correctas(rrhh_db):
    """Con 5 días de 8 horas, total_horas debe ser 40."""
    svc = _make_rrhh(rrhh_db)
    nomina = svc.calcular_nomina(1, '2026-04-07', '2026-04-11')
    assert nomina['total_horas'] == 40.0
    assert nomina['dias_asistidos'] == 5


def test_calcular_nomina_retenciones_no_negativas(rrhh_db):
    """Retenciones de IMSS e ISR deben ser ≥ 0."""
    svc = _make_rrhh(rrhh_db)
    nomina = svc.calcular_nomina(1, '2026-04-07', '2026-04-11')
    assert nomina['imss_obrero'] >= 0
    assert nomina['isr_mensual'] >= 0


def test_calcular_nomina_neto_deducido_menor_igual_bruto(rrhh_db):
    """Neto deducido (con retenciones) debe ser ≤ neto_a_pagar bruto."""
    svc = _make_rrhh(rrhh_db)
    nomina = svc.calcular_nomina(1, '2026-04-07', '2026-04-11')
    assert nomina['neto_deducido'] <= nomina['neto_a_pagar']


def test_calcular_nomina_empleado_inexistente_lanza_error(rrhh_db):
    """Empleado no encontrado debe lanzar ValueError."""
    svc = _make_rrhh(rrhh_db)
    with pytest.raises(ValueError, match="Empleado no encontrado"):
        svc.calcular_nomina(999, '2026-04-07', '2026-04-11')


def test_calcular_nomina_sin_asistencias_retorna_cero_horas(rrhh_db):
    """Sin asistencias en el periodo, total_horas = 0 y neto = 0."""
    svc = _make_rrhh(rrhh_db)
    nomina = svc.calcular_nomina(1, '2025-01-01', '2025-01-07')  # sin registros
    assert nomina['total_horas'] == 0.0
    assert nomina['neto_a_pagar'] == 0.0


# ── turno_asignaciones: estructura de tabla ───────────────────────────────────

def test_turno_asignaciones_tabla_creada():
    """turno_asignaciones debe poder crearse con la estructura del módulo."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Replicar el CREATE TABLE del módulo rrhh_turnos.py
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS turno_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            hora_inicio TEXT,
            hora_fin TEXT,
            descripcion TEXT DEFAULT '',
            color TEXT DEFAULT '#2563EB'
        );
        CREATE TABLE IF NOT EXISTS turno_asignaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            personal_id INTEGER NOT NULL,
            turno_rol_id INTEGER,
            fecha_inicio TEXT,
            fecha_fin TEXT,
            dia_descanso TEXT DEFAULT 'Domingo',
            rotacion_dias INTEGER DEFAULT 0,
            notif_semana INTEGER DEFAULT 1,
            notif_dia INTEGER DEFAULT 1,
            activo INTEGER DEFAULT 1,
            notas TEXT DEFAULT '',
            FOREIGN KEY(turno_rol_id) REFERENCES turno_roles(id)
        );
    """)
    conn.commit()
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert 'turno_roles' in tables
    assert 'turno_asignaciones' in tables


def test_turno_asignaciones_insert_y_query():
    """Se puede insertar y recuperar asignaciones de turno."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE turno_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            hora_inicio TEXT, hora_fin TEXT,
            descripcion TEXT DEFAULT '', color TEXT DEFAULT '#2563EB'
        );
        CREATE TABLE turno_asignaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            personal_id INTEGER NOT NULL,
            turno_rol_id INTEGER, fecha_inicio TEXT, fecha_fin TEXT,
            dia_descanso TEXT DEFAULT 'Domingo',
            rotacion_dias INTEGER DEFAULT 0,
            notif_semana INTEGER DEFAULT 1, notif_dia INTEGER DEFAULT 1,
            activo INTEGER DEFAULT 1, notas TEXT DEFAULT ''
        );
        INSERT INTO turno_roles(nombre, hora_inicio, hora_fin)
            VALUES ('Matutino', '07:00', '15:00');
        INSERT INTO turno_asignaciones(personal_id, turno_rol_id, fecha_inicio)
            VALUES (1, 1, '2026-04-01');
    """)
    conn.commit()
    row = conn.execute(
        "SELECT ta.personal_id, tr.nombre FROM turno_asignaciones ta "
        "JOIN turno_roles tr ON tr.id = ta.turno_rol_id WHERE ta.personal_id = 1"
    ).fetchone()
    assert row is not None
    assert row['nombre'] == 'Matutino'
