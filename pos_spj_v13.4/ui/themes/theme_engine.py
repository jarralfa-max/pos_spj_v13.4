
# ui/themes/theme_engine.py — SPJ POS v13.4
# ThemeManager global — aplica QSS a QApplication + widget activo.
# Los temas se cargan desde config.TEMAS (fuente única de verdad).
# La persistencia usa la tabla configuraciones (clave='tema').
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger("spj.theme_engine")

# Mapa: nombres spec → nombres en TEMAS existentes
_THEME_ALIASES = {
    "SPJ_DARK":          "Oscuro",
    "SPJ_LIGHT":         "Claro",
    "Dark":              "Oscuro",
    "Light":             "Claro",
    "Oscuro Moderno":    "Oscuro",  # Alias para compatibilidad con versiones anteriores
}

# Nombre por defecto
_DEFAULT_THEME = "Oscuro"
_current_theme = _DEFAULT_THEME
_qss_cache: dict = {}  # theme_name → qss string (loaded once per session)


def _get_temas() -> dict:
    """Carga TEMAS desde config.py (fuente única de QSS)."""
    try:
        import config
        return config.TEMAS
    except Exception as e:
        logger.error("No se pudo cargar config.TEMAS: %s", e)
        return {}


def get_available_themes() -> list:
    """Retorna nombres de temas disponibles (solo Claro/Oscuro)."""
    return ["Claro", "Oscuro"]


def get_qss(theme_name: str) -> str:
    """Retorna el QSS para el tema dado. Cachea por nombre para evitar re-parseo."""
    global _qss_cache
    real_name = _THEME_ALIASES.get(theme_name, theme_name)
    if real_name in _qss_cache:
        return _qss_cache[real_name]
    temas = _get_temas()
    qss = temas.get(real_name, "")
    if not qss:
        logger.warning("Tema '%s' no encontrado, usando default", theme_name)
        qss = temas.get(_DEFAULT_THEME, "")
    _qss_cache[real_name] = qss
    return qss


def apply_theme(widget, theme_name: str) -> bool:
    """
    Aplica un tema GLOBALMENTE vía QApplication.setStyleSheet.

    Una sola llamada a app.setStyleSheet re-estiliza todos los widgets.
    No se aplica al widget individual (doble aplicación no agrega nada
    y duplica el trabajo de polish en todos los hijos).
    """
    global _current_theme
    qss = get_qss(theme_name)
    if not qss:
        return False
    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(qss)
        elif widget is not None:
            # Fallback sin QApplication — aplica solo al widget raíz
            widget.setStyleSheet(qss)

        _current_theme = theme_name
        _persist_theme(theme_name)
        logger.info("Tema aplicado globalmente: %s", theme_name)
        return True
    except Exception as e:
        logger.error("Error aplicando tema '%s': %s", theme_name, e)
        return False


def get_current_theme() -> str:
    return _current_theme


def load_saved_theme(widget=None) -> str:
    """
    Carga el tema guardado en BD y lo aplica globalmente.
    Si no hay widget, aplica solo a QApplication.
    """
    try:
        from core.db.connection import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT valor FROM configuraciones WHERE clave='tema'"
        ).fetchone()
        tema = row[0] if row else _DEFAULT_THEME
    except Exception:
        tema = _DEFAULT_THEME
    apply_theme(widget, tema)
    return tema


def _persist_theme(theme_name: str) -> None:
    try:
        from core.db.connection import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO configuraciones (clave, valor) VALUES (?,?)",
            ("tema", theme_name)
        )
        conn.commit()
    except Exception as e:
        logger.debug("No se pudo persistir tema: %s", e)


class ThemeEngine:
    """
    Clase de compatibilidad con GestorTemas existente en config.py.
    Delega en las funciones de módulo para garantizar consistencia global.
    """
    def __init__(self, conexion=None):
        self.conexion = conexion

    def obtener_temas_disponibles(self) -> list:
        return ["Claro", "Oscuro"]

    def obtener_estilo_tema(self, nombre: str) -> str:
        return get_qss(nombre)

    def aplicar_tema(self, widget, nombre: str) -> bool:
        return apply_theme(widget, nombre)

    def obtener_tema_actual(self) -> str:
        return get_current_theme()

    def cargar_tema_guardado(self, widget=None) -> Optional[str]:
        return load_saved_theme(widget)


# Alias de conveniencia — ThemeManager es el punto de entrada preferido
ThemeManager = ThemeEngine
