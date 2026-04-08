# tests/test_bootstrap_wiring.py — v13.4
"""
Tests para:
  1. verificar_tablas() en core/db/connection.py
  2. ForecastEngine.generar_forecast_diario()
  3. InventoryService aliases en español
  4. FinanceService.registrar_ingreso / registrar_egreso / registrar_perdida
"""
from __future__ import annotations

import sqlite3
import pytest
from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────────────
# 1. verificar_tablas
# ─────────────────────────────────────────────────────────────

def test_verificar_tablas_raises_when_missing():
    """DB vacía debe levantar RuntimeError con las tablas faltantes."""
    from core.db.connection import verificar_tablas
    conn = sqlite3.connect(":memory:")
    with pytest.raises(RuntimeError) as exc_info:
        verificar_tablas(conn)
    conn.close()
    assert "tablas faltantes" in str(exc_info.value)
    assert "usuarios" in str(exc_info.value)


def test_verificar_tablas_passes_with_all_required_tables():
    """DB con todas las tablas requeridas no debe levantar error."""
    from core.db.connection import verificar_tablas, TABLAS_REQUERIDAS
    conn = sqlite3.connect(":memory:")
    for tabla in TABLAS_REQUERIDAS:
        conn.execute(f"CREATE TABLE {tabla} (id INTEGER PRIMARY KEY)")
    conn.commit()
    # No debe lanzar excepción
    verificar_tablas(conn)
    conn.close()


def test_verificar_tablas_partial_raises():
    """DB con algunas tablas debe listar solo las faltantes."""
    from core.db.connection import verificar_tablas
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE productos (id INTEGER PRIMARY KEY)")
    conn.commit()
    with pytest.raises(RuntimeError) as exc_info:
        verificar_tablas(conn)
    conn.close()
    msg = str(exc_info.value)
    # usuarios y productos existen → no deben aparecer como faltantes
    assert "usuarios" not in msg
    assert "productos" not in msg
    # clientes falta → debe aparecer
    assert "clientes" in msg


# ─────────────────────────────────────────────────────────────
# 2. ForecastEngine.generar_forecast_diario
# ─────────────────────────────────────────────────────────────

def test_forecast_engine_generar_forecast_diario_returns_list():
    """generar_forecast_diario() debe delegar a run() y retornar lista."""
    from core.services.forecast_engine import ForecastEngine

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Tablas mínimas que run() necesita para no fallar
    conn.execute(
        "CREATE TABLE productos "
        "(id INTEGER PRIMARY KEY, nombre TEXT, stock_minimo REAL, activo INTEGER, oculto INTEGER)"
    )
    conn.commit()

    eng = ForecastEngine(conn, sucursal_id=1)
    result = eng.generar_forecast_diario()
    conn.close()

    assert isinstance(result, list)


def test_forecast_engine_generar_forecast_diario_delegates_to_run():
    """generar_forecast_diario() debe ser idéntico a run()."""
    from core.services.forecast_engine import ForecastEngine

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE productos "
        "(id INTEGER PRIMARY KEY, nombre TEXT, stock_minimo REAL, activo INTEGER, oculto INTEGER)"
    )
    conn.commit()

    eng = ForecastEngine(conn, sucursal_id=1)
    assert eng.generar_forecast_diario() == eng.run()
    conn.close()


# ─────────────────────────────────────────────────────────────
# 3. InventoryService Spanish aliases
# ─────────────────────────────────────────────────────────────

def _make_inventory_service():
    """Crea un InventoryService con repo mock."""
    from core.services.inventory_service import InventoryService

    mock_repo = MagicMock()
    mock_repo.get_current_stock.return_value = 100.0
    mock_repo.get_average_cost.return_value = 10.0
    mock_service = InventoryService(db_conn=MagicMock(), inventory_repo=mock_repo)
    return mock_service, mock_repo


def test_inventory_descontar_stock_exists_and_callable():
    svc, _ = _make_inventory_service()
    assert callable(getattr(svc, "descontar_stock", None))


def test_inventory_incrementar_stock_exists_and_callable():
    svc, _ = _make_inventory_service()
    assert callable(getattr(svc, "incrementar_stock", None))


def test_inventory_ajustar_merma_exists_and_callable():
    svc, _ = _make_inventory_service()
    assert callable(getattr(svc, "ajustar_merma", None))


def test_inventory_descontar_stock_calls_deduct():
    svc, repo = _make_inventory_service()
    svc.descontar_stock(producto_id=1, cantidad=5.0, branch_id=1)
    repo.insert_movement.assert_called_once()
    call_kwargs = repo.insert_movement.call_args
    assert call_kwargs.kwargs.get("movement_type") == "OUT"


def test_inventory_incrementar_stock_calls_add():
    svc, repo = _make_inventory_service()
    repo.get_current_stock.return_value = 0.0
    svc.incrementar_stock(producto_id=2, cantidad=10.0, unit_cost=5.0, branch_id=1)
    repo.insert_movement.assert_called_once()
    call_kwargs = repo.insert_movement.call_args
    assert call_kwargs.kwargs.get("movement_type") == "IN"


def test_inventory_ajustar_merma_uses_waste_reference():
    svc, repo = _make_inventory_service()
    svc.ajustar_merma(producto_id=3, cantidad=2.0, branch_id=1)
    repo.insert_movement.assert_called_once()
    call_kwargs = repo.insert_movement.call_args
    assert call_kwargs.kwargs.get("reference_type") == "WASTE"


# ─────────────────────────────────────────────────────────────
# 4. FinanceService registrar_ingreso / egreso / perdida
# ─────────────────────────────────────────────────────────────

def _make_finance_service():
    """Crea FinanceService con DB in-memory que tiene financial_event_log."""
    from core.services.enterprise.finance_service import FinanceService

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE financial_event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evento TEXT,
            modulo TEXT,
            referencia_id INTEGER,
            monto REAL,
            cuenta_debe TEXT,
            cuenta_haber TEXT,
            usuario_id INTEGER,
            sucursal_id INTEGER,
            metadata TEXT,
            timestamp DATETIME DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    # FinanceService.__init__ puede requerir varios parámetros — usamos mock
    svc = object.__new__(FinanceService)
    svc.db = conn
    return svc, conn


def test_finance_registrar_ingreso_exists():
    svc, conn = _make_finance_service()
    assert callable(getattr(svc, "registrar_ingreso", None))
    conn.close()


def test_finance_registrar_egreso_exists():
    svc, conn = _make_finance_service()
    assert callable(getattr(svc, "registrar_egreso", None))
    conn.close()


def test_finance_registrar_perdida_exists():
    svc, conn = _make_finance_service()
    assert callable(getattr(svc, "registrar_perdida", None))
    conn.close()


def test_finance_registrar_ingreso_inserts_row():
    svc, conn = _make_finance_service()
    row_id = svc.registrar_ingreso("Test ingreso", 100.0)
    assert row_id > 0
    row = conn.execute(
        "SELECT * FROM financial_event_log WHERE id=?", (row_id,)
    ).fetchone()
    assert row is not None
    assert row["cuenta_debe"] == "caja_ventas"
    assert row["cuenta_haber"] == "ventas_contado"
    assert float(row["monto"]) == 100.0
    conn.close()


def test_finance_registrar_egreso_inserts_row():
    svc, conn = _make_finance_service()
    row_id = svc.registrar_egreso("Test egreso", 200.0)
    assert row_id > 0
    row = conn.execute(
        "SELECT * FROM financial_event_log WHERE id=?", (row_id,)
    ).fetchone()
    assert row["cuenta_debe"] == "inventario_almacen"
    assert row["cuenta_haber"] == "cuentas_por_pagar"
    conn.close()


def test_finance_registrar_perdida_inserts_row():
    svc, conn = _make_finance_service()
    row_id = svc.registrar_perdida("Merma pollo", 50.0)
    assert row_id > 0
    row = conn.execute(
        "SELECT * FROM financial_event_log WHERE id=?", (row_id,)
    ).fetchone()
    assert row["cuenta_debe"] == "mermas_y_deterioro"
    assert row["cuenta_haber"] == "inventario_almacen"
    conn.close()


def test_finance_registrar_perdida_custom_cuentas():
    """Se pueden sobreescribir las cuentas via kwargs."""
    svc, conn = _make_finance_service()
    row_id = svc.registrar_perdida(
        "Robo bodega", 300.0,
        debe="perdidas_extraordinarias",
        haber="caja",
    )
    row = conn.execute(
        "SELECT * FROM financial_event_log WHERE id=?", (row_id,)
    ).fetchone()
    assert row["cuenta_debe"] == "perdidas_extraordinarias"
    assert row["cuenta_haber"] == "caja"
    conn.close()
