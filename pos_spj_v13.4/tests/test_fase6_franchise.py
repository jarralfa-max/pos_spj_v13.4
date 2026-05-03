# tests/test_fase6_franchise.py
# Fase 6 — FranchiseManager: gestión multi-sucursal
# Verifica instanciación, enabled default (False sin module_config),
# ranking_sucursales(), comparar_sucursales() y eficiencia_sucursal().
import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import date
from unittest.mock import MagicMock


def _make_db(with_data: bool = False) -> sqlite3.Connection:
    """BD mínima para FranchiseManager."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    today = date.today().isoformat()
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS sucursales (
            id INTEGER PRIMARY KEY, nombre TEXT,
            activa INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY, fecha TEXT,
            estado TEXT DEFAULT 'completada',
            sucursal_id INTEGER DEFAULT 1,
            total REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY, fecha TEXT,
            monto REAL DEFAULT 0, concepto TEXT, sucursal_id INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS empleados (
            id INTEGER PRIMARY KEY, nombre TEXT,
            sucursal_id INTEGER DEFAULT 1,
            activo INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS nomina_pagos (
            id INTEGER PRIMARY KEY, empleado_id INTEGER,
            total REAL DEFAULT 0, estado TEXT DEFAULT 'pagado',
            fecha TEXT DEFAULT '{today}'
        );
        CREATE TABLE IF NOT EXISTS inventario (
            id INTEGER PRIMARY KEY, producto_id INTEGER,
            sucursal_id INTEGER, existencia REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY, nombre TEXT,
            costo REAL DEFAULT 50.0, activo INTEGER DEFAULT 1
        );
    """)
    if with_data:
        conn.executescript(f"""
            INSERT INTO sucursales VALUES (1, 'Norte', 1);
            INSERT INTO sucursales VALUES (2, 'Sur', 1);
            INSERT INTO ventas VALUES (1, '{today} 10:00', 'completada', 1, 5000.0);
            INSERT INTO ventas VALUES (2, '{today} 11:00', 'completada', 1, 3000.0);
            INSERT INTO ventas VALUES (3, '{today} 12:00', 'completada', 2, 2000.0);
            INSERT INTO empleados VALUES (1, 'Ana', 1, 1);
            INSERT INTO empleados VALUES (2, 'Luis', 1, 1);
            INSERT INTO empleados VALUES (3, 'Marta', 2, 1);
        """)
    conn.commit()
    return conn


# ── Instanciación y enabled ───────────────────────────────────────────────────

def test_franchise_manager_instancia():
    from core.services.franchise_manager import FranchiseManager
    conn = _make_db()
    fm = FranchiseManager(conn)
    assert fm is not None


def test_franchise_manager_enabled_false_sin_module_config():
    """Sin module_config, FranchiseManager.enabled = False (opt-in)."""
    from core.services.franchise_manager import FranchiseManager
    conn = _make_db()
    fm = FranchiseManager(conn)
    assert fm.enabled is False


def test_franchise_manager_enabled_true_con_module_config():
    """Con module_config que activa 'franchise_mode', enabled = True."""
    from core.services.franchise_manager import FranchiseManager
    mc = MagicMock()
    mc.is_enabled.return_value = True
    conn = _make_db()
    fm = FranchiseManager(conn, module_config=mc)
    assert fm.enabled is True


# ── ranking_sucursales ────────────────────────────────────────────────────────

def test_ranking_sucursales_db_vacia_retorna_lista():
    from core.services.franchise_manager import FranchiseManager
    conn = _make_db()
    fm = FranchiseManager(conn)
    result = fm.ranking_sucursales()
    assert isinstance(result, list)


def test_ranking_sucursales_no_lanza_excepcion(capsys):
    from core.services.franchise_manager import FranchiseManager
    conn = _make_db(with_data=True)
    fm = FranchiseManager(conn)
    try:
        fm.ranking_sucursales()
    except Exception as e:
        pytest.fail(f"ranking_sucursales() lanzó excepción: {e}")


def test_ranking_sucursales_con_datos_retorna_entradas():
    from core.services.franchise_manager import FranchiseManager
    conn = _make_db(with_data=True)
    fm = FranchiseManager(conn)
    result = fm.ranking_sucursales()
    assert len(result) == 2


def test_ranking_sucursales_tiene_campos_requeridos():
    from core.services.franchise_manager import FranchiseManager
    conn = _make_db(with_data=True)
    fm = FranchiseManager(conn)
    result = fm.ranking_sucursales()
    if result:
        r = result[0]
        assert "sucursal_id" in r
        assert "ingresos" in r or "ventas" in r or any(
            k in r for k in ("total", "utilidad", "ranking")
        ), f"Campos inesperados: {list(r.keys())}"


# ── eficiencia_sucursal ───────────────────────────────────────────────────────

def test_eficiencia_sucursal_retorna_dict():
    from core.services.franchise_manager import FranchiseManager
    conn = _make_db(with_data=True)
    fm = FranchiseManager(conn)
    result = fm.eficiencia_sucursal(sucursal_id=1)
    assert isinstance(result, dict)


def test_eficiencia_sucursal_no_lanza_excepcion():
    from core.services.franchise_manager import FranchiseManager
    conn = _make_db(with_data=True)
    fm = FranchiseManager(conn)
    try:
        fm.eficiencia_sucursal(sucursal_id=1)
    except Exception as e:
        pytest.fail(f"eficiencia_sucursal() lanzó excepción: {e}")


# ── comparar_sucursales ───────────────────────────────────────────────────────

def test_comparar_sucursales_retorna_dict():
    from core.services.franchise_manager import FranchiseManager
    conn = _make_db(with_data=True)
    fm = FranchiseManager(conn)
    result = fm.comparar_sucursales(sucursal_ids=[1, 2])
    assert isinstance(result, dict)


def test_comparar_sucursales_sin_ids_no_lanza():
    from core.services.franchise_manager import FranchiseManager
    conn = _make_db(with_data=True)
    fm = FranchiseManager(conn)
    try:
        fm.comparar_sucursales()
    except Exception as e:
        pytest.fail(f"comparar_sucursales() lanzó excepción: {e}")


# ── sugerir_transferencias ────────────────────────────────────────────────────

def test_sugerir_transferencias_retorna_lista():
    from core.services.franchise_manager import FranchiseManager
    conn = _make_db(with_data=True)
    fm = FranchiseManager(conn)
    result = fm.sugerir_transferencias()
    assert isinstance(result, list)
