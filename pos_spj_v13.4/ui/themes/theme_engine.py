
# ui/themes/theme_engine.py — SPJ POS v6.1
# Motor de temas enterprise — extrae QSS de config.py y añade los 5 temas requeridos.
# Los temas existentes (Oscuro Moderno, Claro Elegante, etc.) son preservados.
# Los nuevos temas del spec se mapean a los existentes para compatibilidad.
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger("spj.theme_engine")

# Mapa: nombres spec → nombres en TEMAS existentes
_THEME_ALIASES = {
    "SPJ_DARK":           "Oscuro Moderno",
    "SPJ_LIGHT":          "Claro Elegante",
    "SPJ_BLUE_PRO":       "Azul Profesional",
    "SPJ_GREEN_ELEGANT":  "Verde Naturaleza",
    "SPJ_PURPLE_PREMIUM": "Púrpura Creativo",
}

# Nombre por defecto
_DEFAULT_THEME = "Oscuro Moderno"
_current_theme = _DEFAULT_THEME


def _get_temas() -> dict:
    """Carga TEMAS desde config.py (fuente única de QSS)."""
    try:
        import config
        return config.TEMAS
    except Exception as e:
        logger.error("No se pudo cargar config.TEMAS: %s", e)
        return {}


def get_available_themes() -> list:
    """Retorna nombres de temas disponibles (spec + legacy)."""
    temas = _get_temas()
    result = list(_THEME_ALIASES.keys()) + [
        t for t in temas.keys() if t not in _THEME_ALIASES.values()
    ]
    return result


def get_qss(theme_name: str) -> str:
    """Retorna el QSS para el tema dado. Acepta nombres spec o nombres legacy."""
    temas = _get_temas()
    # Resolver alias
    real_name = _THEME_ALIASES.get(theme_name, theme_name)
    qss = temas.get(real_name, "")
    if not qss:
        logger.warning("Tema '%s' no encontrado, usando default", theme_name)
        qss = temas.get(_DEFAULT_THEME, "")
    return qss


def apply_theme(widget, theme_name: str) -> bool:
    """Aplica un tema a un QWidget (usualmente la QApplication o QMainWindow)."""
    global _current_theme
    qss = get_qss(theme_name)
    if not qss:
        return False
    try:
        widget.setStyleSheet(qss)
        _current_theme = theme_name
        _persist_theme(theme_name)
        logger.info("Tema aplicado: %s", theme_name)
        return True
    except Exception as e:
        logger.error("Error aplicando tema '%s': %s", theme_name, e)
        return False


def get_current_theme() -> str:
    return _current_theme


def load_saved_theme(widget) -> str:
    """Carga el tema guardado en BD y lo aplica."""
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
            "INSERT OR REPLACE INTO configuraciones (clave, valor, descripcion) VALUES (?,?,?)",
            ("tema", theme_name, "Tema de la interfaz")
        )
        conn.commit()
    except Exception as e:
        logger.debug("No se pudo persistir tema: %s", e)


class ThemeEngine:
    """Clase de compatibilidad con GestorTemas existente en config.py."""
    def __init__(self, conexion=None):
        self.conexion = conexion

    def obtener_temas_disponibles(self) -> list:
        return list(_get_temas().keys())

    def obtener_estilo_tema(self, nombre: str) -> str:
        return get_qss(nombre)

    def aplicar_tema(self, widget, nombre: str) -> bool:
        return apply_theme(widget, nombre)

    def obtener_tema_actual(self) -> str:
        return get_current_theme()

    def cargar_tema_guardado(self, widget) -> Optional[str]:
        return load_saved_theme(widget)
