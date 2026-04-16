# tests/test_fase0_menu_lateral.py
# Fase 0 — Verificación de whitelist y visibilidad del menú lateral
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


def _leer_menu_lateral():
    """Lee menu_lateral.py como texto (sin importar PyQt5)."""
    path = os.path.join(os.path.dirname(__file__), "..", "interfaz", "menu_lateral.py")
    return open(os.path.abspath(path)).read()


def test_modulos_contiene_whitelist():
    """MODULOS en menu_lateral.py incluye los módulos críticos del Plan Maestro."""
    src = _leer_menu_lateral()
    criticos = ["tesoreria", "finanzas", "activos", "whatsapp",
                "configuracion", "decisiones"]
    for m in criticos:
        assert f'"{m}"' in src or f"'{m}'" in src, \
            f"'{m}' no está en MODULOS de menu_lateral.py"


def test_whitelist_siempre_visible_definida():
    """WHITELIST_SIEMPRE_VISIBLE contiene todos los módulos críticos."""
    src = _leer_menu_lateral()
    assert "WHITELIST_SIEMPRE_VISIBLE" in src, \
        "WHITELIST_SIEMPRE_VISIBLE no está definida en menu_lateral.py"
    requeridos = [
        "TESORERIA", "FINANZAS", "ACTIVOS",
        "PLANEACION_COMPRAS", "WHATSAPP", "DECISIONES", "CONFIG_SEGURIDAD",
    ]
    for codigo in requeridos:
        assert f'"{codigo}"' in src or f"'{codigo}'" in src, \
            f"'{codigo}' falta en WHITELIST_SIEMPRE_VISIBLE de menu_lateral.py"


def test_module_config_defaults_tesoreria_visible():
    """treasury_central_enabled debe ser True por defecto (Fase 0 fix)."""
    from core.module_config import DEFAULT_TOGGLES
    assert DEFAULT_TOGGLES.get("treasury_central_enabled") is True, \
        "treasury_central_enabled debe ser True por defecto para que Tesorería sea visible"


def test_module_config_defaults_whatsapp_visible():
    """whatsapp_integration_enabled debe ser True por defecto (Fase 0 fix)."""
    from core.module_config import DEFAULT_TOGGLES
    assert DEFAULT_TOGGLES.get("whatsapp_integration_enabled") is True, \
        "whatsapp_integration_enabled debe ser True por defecto"


def test_module_config_defaults_decisions_visible():
    """decisions_enabled debe ser True por defecto (Fase 0 fix)."""
    from core.module_config import DEFAULT_TOGGLES
    assert DEFAULT_TOGGLES.get("decisions_enabled") is True, \
        "decisions_enabled debe ser True por defecto"


def test_module_config_sin_db_usa_defaults():
    """ModuleConfig sin BD carga los defaults en memoria correctamente."""
    from core.module_config import ModuleConfig
    cfg = ModuleConfig(db_conn=None)
    assert cfg.is_enabled("treasury_central_enabled") is True
    assert cfg.is_enabled("finance_enabled") is True
    assert cfg.is_enabled("whatsapp_integration_enabled") is True
    assert cfg.is_enabled("decisions_enabled") is True


def test_menu_lateral_py_tiene_boton_decisiones():
    """El menú lateral declara el botón DECISIONES."""
    import ast
    src = open("interfaz/menu_lateral.py").read()
    assert "DECISIONES" in src, "El código DECISIONES no está en menu_lateral.py"


def test_main_window_py_wire_decisiones():
    """main_window.py tiene wiring para DECISIONES."""
    src = open("interfaz/main_window.py").read()
    assert "DECISIONES" in src, "DECISIONES no está wired en main_window.py"


def test_menu_lateral_sidebar_siempre_oscuro():
    """Sidebar define QSS oscuro fijo y método de refuerzo tras cambio de tema."""
    src = _leer_menu_lateral()
    assert "_SIDEBAR_DARK_QSS" in src, "Falta QSS oscuro dedicado del sidebar"
    assert "background-color: #020617" in src, "Sidebar no tiene color oscuro base esperado"
    assert "def enforce_dark_mode" in src, "Falta método enforce_dark_mode en MenuLateral"


def test_main_window_refuerza_sidebar_tras_tema():
    """main_window reafirma modo oscuro del sidebar al aplicar/cargar tema."""
    src = open("interfaz/main_window.py").read()
    assert "self.menu.enforce_dark_mode()" in src, \
        "main_window no refuerza sidebar oscuro después de cambios de tema"
