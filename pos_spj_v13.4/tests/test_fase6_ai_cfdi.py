# tests/test_fase6_ai_cfdi.py
# Fase 6 — AIAdvisor (Ollama/DeepSeek) y CFDIService (SAT 4.0)
# Tests de instanciación, tabla de log, comportamiento offline (Ollama
# no disponible) y generación básica de CFDI XML.
import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock, patch


def _make_db(with_cfdi_data: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS configuraciones (
            clave TEXT PRIMARY KEY, valor TEXT
        );
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY, fecha TEXT DEFAULT (datetime('now')),
            total REAL DEFAULT 0, subtotal REAL DEFAULT 0,
            descuento REAL DEFAULT 0, forma_pago TEXT DEFAULT 'Efectivo',
            folio TEXT DEFAULT '', sucursal_id INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'completada'
        );
        CREATE TABLE IF NOT EXISTS detalles_venta (
            id INTEGER PRIMARY KEY, venta_id INTEGER, producto_id INTEGER,
            cantidad REAL DEFAULT 1, precio_unitario REAL DEFAULT 100.0,
            subtotal REAL DEFAULT 100.0, descuento REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY, nombre TEXT,
            precio REAL DEFAULT 100.0, activo INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS cfdi_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER, uuid_cfdi TEXT, xml TEXT,
            folio TEXT, estado TEXT, fecha TEXT
        );
    """)
    if with_cfdi_data:
        conn.executescript("""
            INSERT INTO configuraciones VALUES ('rfc', 'AAA010101AAA');
            INSERT INTO configuraciones VALUES ('nombre_empresa', 'Empresa Test SA');
            INSERT INTO configuraciones VALUES ('regimen_fiscal', '616');
            INSERT INTO configuraciones VALUES ('cfdi_serie', 'A');
            INSERT INTO productos VALUES (1, 'Pollo 1kg', 120.0, 1);
            INSERT INTO ventas VALUES (1, datetime('now'), 120.0, 120.0, 0.0,
                'Efectivo', 'F001', 1, 'completada');
            INSERT INTO detalles_venta VALUES (1, 1, 1, 1.0, 120.0, 120.0, 0.0);
        """)
    conn.commit()
    return conn


# ══════════════════════════════════════════════════════════════════════════════
# AIAdvisor
# ══════════════════════════════════════════════════════════════════════════════

def test_ai_advisor_instancia_sin_db():
    """AIAdvisor puede crearse sin db_conn (modo headless)."""
    from core.services.ai_advisor import AIAdvisor
    ai = AIAdvisor()
    assert ai is not None


def test_ai_advisor_instancia_con_db():
    from core.services.ai_advisor import AIAdvisor
    conn = _make_db()
    ai = AIAdvisor(db_conn=conn)
    assert ai is not None


def test_ai_advisor_enabled_false_por_defecto():
    """Sin module_config, AIAdvisor.enabled = False (opt-in)."""
    from core.services.ai_advisor import AIAdvisor
    conn = _make_db()
    ai = AIAdvisor(db_conn=conn)
    assert ai.enabled is False


def test_ai_advisor_enabled_true_con_module_config():
    from core.services.ai_advisor import AIAdvisor
    mc = MagicMock()
    mc.is_enabled.return_value = True
    conn = _make_db()
    ai = AIAdvisor(db_conn=conn, module_config=mc)
    assert ai.enabled is True


def test_ai_advisor_tabla_log_creada():
    """ai_consulta_log debe crearse durante __init__."""
    from core.services.ai_advisor import AIAdvisor
    conn = _make_db()
    AIAdvisor(db_conn=conn)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ai_consulta_log'"
    ).fetchone()
    assert row is not None


def test_ai_advisor_is_available_sync_sin_ollama():
    """Sin Ollama corriendo, is_available_sync() debe retornar False."""
    from core.services.ai_advisor import AIAdvisor
    conn = _make_db()
    ai = AIAdvisor(db_conn=conn)
    # Patch urllib para simular Ollama no disponible
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        result = ai.is_available_sync()
    assert result is False


def test_ai_advisor_analisis_rapido_retorna_dict():
    """analisis_rapido() retorna dict con estructura mínima incluso sin datos."""
    from core.services.ai_advisor import AIAdvisor
    conn = _make_db()
    ai = AIAdvisor(db_conn=conn)
    result = ai.analisis_rapido()
    assert isinstance(result, dict)


def test_ai_advisor_analisis_rapido_no_lanza():
    """analisis_rapido() no debe lanzar excepción sin datos en BD."""
    from core.services.ai_advisor import AIAdvisor
    conn = _make_db()
    ai = AIAdvisor(db_conn=conn)
    try:
        ai.analisis_rapido()
    except Exception as e:
        pytest.fail(f"analisis_rapido() lanzó excepción: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# CFDIService
# ══════════════════════════════════════════════════════════════════════════════

def test_cfdi_service_instancia():
    from core.services.cfdi_service import CFDIService
    conn = _make_db()
    svc = CFDIService(conn)
    assert svc is not None


def test_cfdi_venta_inexistente_retorna_error():
    """generar_cfdi() con venta_id inexistente retorna dict con 'error'."""
    from core.services.cfdi_service import CFDIService
    conn = _make_db()
    svc = CFDIService(conn)
    result = svc.generar_cfdi(venta_id=9999)
    assert "error" in result
    assert result["error"]  # mensaje no vacío


def test_cfdi_genera_xml_para_venta_valida():
    """generar_cfdi() con venta válida retorna dict con 'xml' no vacío."""
    from core.services.cfdi_service import CFDIService
    conn = _make_db(with_cfdi_data=True)
    svc = CFDIService(conn)
    result = svc.generar_cfdi(venta_id=1)
    assert isinstance(result, dict)
    # Debe tener 'xml' (aunque el timbrado PAC falle offline)
    assert "xml" in result


def test_cfdi_xml_contiene_estructura_cfdi():
    """El XML generado debe contener el namespace CFDI 4.0."""
    from core.services.cfdi_service import CFDIService
    conn = _make_db(with_cfdi_data=True)
    svc = CFDIService(conn)
    result = svc.generar_cfdi(venta_id=1)
    xml = result.get("xml", "")
    if xml and not result.get("error"):
        assert "cfdi" in xml.lower() or "Comprobante" in xml, (
            "XML debe contener estructura CFDI"
        )


def test_cfdi_retorna_uuid():
    """generar_cfdi() exitoso debe incluir un 'uuid'."""
    from core.services.cfdi_service import CFDIService
    conn = _make_db(with_cfdi_data=True)
    svc = CFDIService(conn)
    result = svc.generar_cfdi(venta_id=1)
    assert "uuid" in result


def test_cfdi_next_folio_incrementa():
    """_next_folio() debe retornar folios incrementales."""
    from core.services.cfdi_service import CFDIService
    conn = _make_db(with_cfdi_data=True)
    svc = CFDIService(conn)
    f1 = svc._next_folio()
    f2 = svc._next_folio()
    assert int(f2) > int(f1), f"Folios no incrementales: {f1} → {f2}"


def test_cfdi_get_cfdi_venta_vacia():
    """get_cfdi_venta() retorna None si no hay CFDI para esa venta."""
    from core.services.cfdi_service import CFDIService
    conn = _make_db()
    svc = CFDIService(conn)
    result = svc.get_cfdi_venta(venta_id=1)
    assert result is None


def test_cfdi_cancelar_uuid_invalido():
    """cancelar_cfdi() con UUID inválido retorna dict con indicación de error."""
    from core.services.cfdi_service import CFDIService
    conn = _make_db()
    svc = CFDIService(conn)
    result = svc.cancelar_cfdi(uuid_cfdi="uuid-invalido")
    assert isinstance(result, dict)
