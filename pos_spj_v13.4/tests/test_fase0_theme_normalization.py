# tests/test_fase0_theme_normalization.py
# Fase 0 — Bug 5: Normalización de nombres de tema
# main_window.py pasa "Dark"/"Light" mientras TEMAS usa "Oscuro"/"Claro".
# ThemeService.save_preferences() normaliza correctamente. Este test protege esa lógica.
import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture
def theme_db():
    """BD en memoria con tabla configuraciones."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE configuraciones (
            clave TEXT PRIMARY KEY,
            valor TEXT,
            descripcion TEXT
        );
    """)
    conn.commit()
    return conn


def test_dark_normaliza_a_oscuro(theme_db):
    """'Dark' debe normalizarse a 'Oscuro' en ThemeService.get_user_preferences()."""
    from core.services.theme_service import ThemeService
    svc = ThemeService(theme_db)
    svc.save_preferences(theme="Dark", density="Normal", font_size="12", icon_size="24")
    # Verificar que se guardó en BD con clave 'ui_theme'
    row = theme_db.execute("SELECT valor FROM configuraciones WHERE clave='ui_theme'").fetchone()
    assert row is not None, "save_preferences debe persistir el tema en BD como 'ui_theme'"
    # Verificar normalización vía get_user_preferences
    prefs = svc.get_user_preferences()
    assert prefs['theme'] == "Oscuro", f"'Dark' debe normalizarse a 'Oscuro', se obtuvo '{prefs['theme']}'"


def test_light_normaliza_a_claro(theme_db):
    """'Light' debe normalizarse a 'Claro' en ThemeService.get_user_preferences()."""
    from core.services.theme_service import ThemeService
    svc = ThemeService(theme_db)
    svc.save_preferences(theme="Light", density="Normal", font_size="12", icon_size="24")
    prefs = svc.get_user_preferences()
    assert prefs['theme'] == "Claro", f"'Light' debe normalizarse a 'Claro', se obtuvo '{prefs['theme']}'"


def test_oscuro_mantiene_oscuro(theme_db):
    """'Oscuro' ya correcto debe mantenerse como 'Oscuro'."""
    from core.services.theme_service import ThemeService
    svc = ThemeService(theme_db)
    svc.save_preferences(theme="Oscuro", density="Normal", font_size="12", icon_size="24")
    prefs = svc.get_user_preferences()
    assert prefs['theme'] == "Oscuro", f"'Oscuro' debe mantenerse, se obtuvo '{prefs['theme']}'"


def test_claro_mantiene_claro(theme_db):
    """'Claro' ya correcto debe mantenerse como 'Claro'."""
    from core.services.theme_service import ThemeService
    svc = ThemeService(theme_db)
    svc.save_preferences(theme="Claro", density="Normal", font_size="12", icon_size="24")
    prefs = svc.get_user_preferences()
    assert prefs['theme'] == "Claro", f"'Claro' debe mantenerse, se obtuvo '{prefs['theme']}'"


def test_generate_qss_retorna_string_no_vacio(theme_db):
    """generate_qss() debe retornar un QSS no vacío para cualquier tema."""
    from core.services.theme_service import ThemeService
    svc = ThemeService(theme_db)
    for tema in ("Oscuro", "Claro"):
        svc.save_preferences(theme=tema, density="Normal", font_size="12", icon_size="24")
        qss = svc.generate_qss()
        assert isinstance(qss, str), f"generate_qss() debe retornar str para {tema}"
        assert len(qss) > 50, f"QSS para {tema} debe tener contenido real"
