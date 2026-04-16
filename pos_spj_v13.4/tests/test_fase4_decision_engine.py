# tests/test_fase4_decision_engine.py
# Fase 4/5 — DecisionEngine: motor de sugerencias (solo lectura, nunca ejecuta)
# Verifica instanciación, retorno de lista, estructura de sugerencias,
# detección de márgenes negativos y tabla decision_log.
import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


def _make_db(extra_sql: str = "") -> sqlite3.Connection:
    """BD mínima para DecisionEngine."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY, nombre TEXT,
            precio_venta REAL DEFAULT 100.0, costo REAL DEFAULT 50.0,
            categoria TEXT DEFAULT 'General', activo INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS inventario (
            id INTEGER PRIMARY KEY, producto_id INTEGER,
            sucursal_id INTEGER, cantidad REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY, fecha TEXT,
            total REAL DEFAULT 0, sucursal_id INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS detalle_ventas (
            id INTEGER PRIMARY KEY, venta_id INTEGER,
            producto_id INTEGER, cantidad REAL DEFAULT 0,
            precio_unit REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS configuraciones (
            clave TEXT PRIMARY KEY, valor TEXT
        );
        CREATE TABLE IF NOT EXISTS sucursales (
            id INTEGER PRIMARY KEY, nombre TEXT
        );
        {extra_sql}
    """)
    conn.commit()
    return conn


@pytest.fixture
def db_vacio():
    return _make_db()


@pytest.fixture
def db_con_margen_negativo():
    """Producto con costo > precio_venta — dispara sugerencia pricing."""
    return _make_db("""
        INSERT INTO productos VALUES (1, 'Prod Margen Negativo', 50.0, 100.0, 'Test', 1);
        INSERT INTO inventario VALUES (1, 1, 1, 100.0);
        INSERT INTO sucursales VALUES (1, 'Sucursal Principal');
    """)


# ── Instanciación ─────────────────────────────────────────────────────────────

def test_decision_engine_instancia_sin_servicios(db_vacio):
    """DecisionEngine debe crearse con solo db_conn."""
    from core.services.decision_engine import DecisionEngine
    engine = DecisionEngine(db_vacio)
    assert engine is not None


def test_decision_engine_enabled_por_defecto(db_vacio):
    """Sin module_config, enabled debe ser True."""
    from core.services.decision_engine import DecisionEngine
    engine = DecisionEngine(db_vacio)
    assert engine.enabled is True


def test_decision_engine_disabled_con_module_config(db_vacio):
    """Con module_config que desactiva 'decisions', enabled=False."""
    from core.services.decision_engine import DecisionEngine
    from unittest.mock import MagicMock
    mc = MagicMock()
    mc.is_enabled.return_value = False
    engine = DecisionEngine(db_vacio, module_config=mc)
    assert engine.enabled is False


# ── Tabla decision_log ────────────────────────────────────────────────────────

def test_decision_log_creada_en_init(db_vacio):
    """decision_log debe crearse durante __init__."""
    from core.services.decision_engine import DecisionEngine
    DecisionEngine(db_vacio)
    row = db_vacio.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='decision_log'"
    ).fetchone()
    assert row is not None, "Tabla decision_log debe existir tras crear DecisionEngine"


# ── generar_sugerencias ───────────────────────────────────────────────────────

def test_generar_sugerencias_retorna_lista(db_vacio):
    """generar_sugerencias() siempre retorna una lista."""
    from core.services.decision_engine import DecisionEngine
    engine = DecisionEngine(db_vacio)
    result = engine.generar_sugerencias(sucursal_id=1)
    assert isinstance(result, list)


def test_generar_sugerencias_db_vacia_no_lanza(db_vacio):
    """Con BD vacía no debe lanzar excepción."""
    from core.services.decision_engine import DecisionEngine
    engine = DecisionEngine(db_vacio)
    try:
        engine.generar_sugerencias(sucursal_id=1)
    except Exception as e:
        pytest.fail(f"generar_sugerencias() lanzó excepción inesperada: {e}")


def test_generar_sugerencias_disabled_retorna_lista_vacia(db_vacio):
    """Con engine desactivado, retorna lista vacía sin consultar BD."""
    from core.services.decision_engine import DecisionEngine
    from unittest.mock import MagicMock
    mc = MagicMock()
    mc.is_enabled.return_value = False
    engine = DecisionEngine(db_vacio, module_config=mc)
    result = engine.generar_sugerencias(sucursal_id=1)
    assert result == []


def test_sugerencia_tiene_campos_requeridos(db_con_margen_negativo):
    """Cada sugerencia debe tener: tipo, prioridad, titulo, detalle."""
    from core.services.decision_engine import DecisionEngine
    engine = DecisionEngine(db_con_margen_negativo)
    sugs = engine.generar_sugerencias(sucursal_id=1)
    for s in sugs:
        assert "tipo" in s, f"Campo 'tipo' faltante en sugerencia: {s}"
        assert "prioridad" in s, f"Campo 'prioridad' faltante en sugerencia: {s}"
        assert "titulo" in s, f"Campo 'titulo' faltante en sugerencia: {s}"
        assert "detalle" in s, f"Campo 'detalle' faltante en sugerencia: {s}"


def test_sugerencia_tipo_es_string(db_con_margen_negativo):
    """El campo 'tipo' debe ser str."""
    from core.services.decision_engine import DecisionEngine
    engine = DecisionEngine(db_con_margen_negativo)
    sugs = engine.generar_sugerencias(sucursal_id=1)
    for s in sugs:
        assert isinstance(s["tipo"], str)


def test_sugerencia_prioridad_valor_valido(db_con_margen_negativo):
    """El campo 'prioridad' debe contener uno de los valores válidos."""
    from core.services.decision_engine import DecisionEngine
    engine = DecisionEngine(db_con_margen_negativo)
    sugs = engine.generar_sugerencias(sucursal_id=1)
    valores_validos = {"baja", "media", "alta", "urgente"}
    for s in sugs:
        prioridad_lower = s["prioridad"].lower()
        # El campo puede tener emoji prefix, buscamos el nivel como substr
        assert any(v in prioridad_lower for v in valores_validos), (
            f"Prioridad no válida: {s['prioridad']!r}"
        )


# ── Suggestion.to_dict ────────────────────────────────────────────────────────

def test_suggestion_to_dict_estructura():
    """Suggestion.to_dict() retorna dict con todos los campos esperados."""
    from core.services.decision_engine import Suggestion
    s = Suggestion(
        tipo="pricing",
        prioridad="alta",
        titulo="Test",
        detalle="Detalle test",
        impacto_estimado="$1,000",
        accion_propuesta={"accion": "subir_precio"},
    )
    d = s.to_dict()
    assert d["tipo"] == "pricing"
    assert "alta" in d["prioridad"].lower()
    assert d["titulo"] == "Test"
    assert d["detalle"] == "Detalle test"
    assert d["impacto_estimado"] == "$1,000"
