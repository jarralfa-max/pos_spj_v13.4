# tests/test_fase5_forecast.py
# Fase 5 — Motor de Pronóstico (ForecastEngine + ActionableForecastService)
# Verifica SES (Suavizamiento Exponencial Simple), forecast por producto,
# run() completo y ActionableForecastService con BD en memoria.
import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import date, timedelta


def _make_db(with_data: bool = False) -> sqlite3.Connection:
    """BD mínima compatible con ForecastEngine y ActionableForecastService."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    two_ago = (date.today() - timedelta(days=2)).isoformat()

    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY, nombre TEXT,
            precio_venta REAL DEFAULT 100.0,
            precio_compra REAL DEFAULT 50.0,
            costo REAL DEFAULT 50.0,
            existencia REAL DEFAULT 0.0,
            stock_minimo REAL DEFAULT 5.0,
            unidad TEXT DEFAULT 'pza',
            activo INTEGER DEFAULT 1,
            oculto INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS inventario (
            id INTEGER PRIMARY KEY, producto_id INTEGER,
            sucursal_id INTEGER DEFAULT 1,
            existencia REAL DEFAULT 0.0
        );
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY, fecha TEXT,
            estado TEXT DEFAULT 'completada',
            sucursal_id INTEGER DEFAULT 1, total REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS detalles_venta (
            id INTEGER PRIMARY KEY, venta_id INTEGER,
            producto_id INTEGER, cantidad REAL DEFAULT 0,
            precio_unit REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS configuraciones (
            clave TEXT PRIMARY KEY, valor TEXT
        );
    """)

    if with_data:
        conn.executescript(f"""
            INSERT INTO productos VALUES (1, 'Pollo 1kg', 120.0, 60.0, 60.0, 50.0, 10.0, 'kg', 1, 0);
            INSERT INTO inventario VALUES (1, 1, 1, 50.0);
            INSERT INTO ventas VALUES (1, '{two_ago} 10:00:00', 'completada', 1, 240.0);
            INSERT INTO ventas VALUES (2, '{yesterday} 11:00:00', 'completada', 1, 360.0);
            INSERT INTO ventas VALUES (3, '{today} 09:00:00', 'completada', 1, 120.0);
            INSERT INTO detalles_venta VALUES (1, 1, 1, 2.0, 120.0);
            INSERT INTO detalles_venta VALUES (2, 2, 1, 3.0, 120.0);
            INSERT INTO detalles_venta VALUES (3, 3, 1, 1.0, 120.0);
        """)

    conn.commit()
    return conn


# ── ForecastEngine ────────────────────────────────────────────────────────────

def test_forecast_engine_instancia():
    from core.services.forecast_engine import ForecastEngine
    conn = _make_db()
    engine = ForecastEngine(conn, sucursal_id=1)
    assert engine is not None


def test_forecast_engine_run_db_vacia_retorna_lista():
    """run() con DB vacía retorna lista vacía (sin productos activos)."""
    from core.services.forecast_engine import ForecastEngine
    conn = _make_db()
    engine = ForecastEngine(conn)
    result = engine.run()
    assert isinstance(result, list)


def test_forecast_engine_run_con_datos_retorna_resultados():
    """run() con productos e historial retorna al menos un resultado."""
    from core.services.forecast_engine import ForecastEngine
    conn = _make_db(with_data=True)
    engine = ForecastEngine(conn)
    result = engine.run()
    assert isinstance(result, list)
    assert len(result) > 0


def test_forecast_engine_run_estructura_resultado():
    """Cada resultado de run() debe tener los campos esperados."""
    from core.services.forecast_engine import ForecastEngine
    conn = _make_db(with_data=True)
    engine = ForecastEngine(conn)
    result = engine.run()
    if result:  # si hay datos
        r = result[0]
        assert "producto_id" in r
        assert "nombre" in r
        assert "stock_actual" in r
        assert "demanda_diaria" in r
        assert "dias_stock" in r
        assert "requiere_pedido" in r


def test_forecast_engine_producto_individual_estructura():
    """forecast_producto() retorna dict con demanda_diaria, semana, mes."""
    from core.services.forecast_engine import ForecastEngine
    conn = _make_db(with_data=True)
    engine = ForecastEngine(conn)
    fc = engine.forecast_producto(1)
    assert isinstance(fc, dict)
    assert "producto_id" in fc
    assert "demanda_diaria" in fc
    assert "demanda_semana" in fc
    assert "demanda_mes" in fc


def test_forecast_engine_demanda_no_negativa():
    """La demanda pronosticada no puede ser negativa."""
    from core.services.forecast_engine import ForecastEngine
    conn = _make_db(with_data=True)
    engine = ForecastEngine(conn)
    fc = engine.forecast_producto(1)
    assert fc["demanda_diaria"] >= 0
    assert fc["demanda_semana"] >= 0
    assert fc["demanda_mes"] >= 0


def test_forecast_engine_demanda_mes_es_30x_diaria():
    """demanda_mes debe ser ~30x demanda_diaria."""
    from core.services.forecast_engine import ForecastEngine
    conn = _make_db(with_data=True)
    engine = ForecastEngine(conn)
    fc = engine.forecast_producto(1)
    if fc["demanda_diaria"] > 0:
        assert abs(fc["demanda_mes"] / fc["demanda_diaria"] - 30) < 0.1


def test_forecast_engine_sin_historial_demanda_cero():
    """Sin historial de ventas, la demanda SES debe ser 0."""
    from core.services.forecast_engine import ForecastEngine
    conn = _make_db()
    # Agregar producto sin ventas
    conn.execute("INSERT INTO productos VALUES (99, 'Sin ventas', 100, 50, 50, 10, 5, 'pza', 1, 0)")
    conn.commit()
    engine = ForecastEngine(conn)
    fc = engine.forecast_producto(99)
    assert fc["demanda_diaria"] == 0.0


def test_generar_forecast_diario_alias_run():
    """generar_forecast_diario() debe retornar el mismo resultado que run()."""
    from core.services.forecast_engine import ForecastEngine
    conn = _make_db(with_data=True)
    engine = ForecastEngine(conn)
    assert engine.generar_forecast_diario() == engine.run()


# ── ActionableForecastService ─────────────────────────────────────────────────

def test_actionable_forecast_instancia():
    from core.services.actionable_forecast import ActionableForecastService
    conn = _make_db()
    svc = ActionableForecastService(conn)
    assert svc is not None


def test_actionable_forecast_enabled_por_defecto():
    from core.services.actionable_forecast import ActionableForecastService
    conn = _make_db()
    svc = ActionableForecastService(conn)
    assert svc.enabled is True


def test_analisis_demanda_db_vacia_retorna_lista():
    from core.services.actionable_forecast import ActionableForecastService
    conn = _make_db()
    svc = ActionableForecastService(conn)
    result = svc.analisis_demanda(sucursal_id=1, dias=30)
    assert isinstance(result, list)


def test_analisis_demanda_no_lanza_excepcion():
    from core.services.actionable_forecast import ActionableForecastService
    conn = _make_db(with_data=True)
    svc = ActionableForecastService(conn)
    try:
        svc.analisis_demanda(sucursal_id=1, dias=30)
    except Exception as e:
        pytest.fail(f"analisis_demanda() lanzó excepción: {e}")


def test_plan_compras_semanal_retorna_dict_con_items():
    """plan_compras_semanal() retorna dict con key 'items' (lista de compras)."""
    from core.services.actionable_forecast import ActionableForecastService
    conn = _make_db(with_data=True)
    svc = ActionableForecastService(conn)
    plan = svc.plan_compras_semanal(sucursal_id=1)
    assert isinstance(plan, dict), f"Se esperaba dict, se obtuvo {type(plan)}"
    assert "items" in plan, f"Falta key 'items' en plan: {list(plan.keys())}"
    assert isinstance(plan["items"], list)


def test_analisis_riesgos_retorna_lista():
    from core.services.actionable_forecast import ActionableForecastService
    conn = _make_db(with_data=True)
    svc = ActionableForecastService(conn)
    riesgos = svc.analisis_riesgos(sucursal_id=1)
    assert isinstance(riesgos, list)
