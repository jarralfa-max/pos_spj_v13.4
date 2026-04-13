# core/services/theme_service.py — SPJ POS v13.30
"""
ThemeService — DELEGADO a theme_engine para consistencia global.
Solo usa Claro/Oscuro. No modifica fuentes, paddings ni tamaños.
"""
import logging

logger = logging.getLogger(__name__)


class ThemeService:

    def __init__(self, db_conn):
        self.db = db_conn

    def get_user_preferences(self) -> dict:
        prefs = {'theme': 'Oscuro', 'density': 'Normal',
                 'font_size': '12', 'icon_size': '24'}
        try:
            rows = self.db.execute(
                "SELECT clave, valor FROM configuraciones "
                "WHERE clave IN ('ui_theme','ui_density','ui_font_size','ui_icon_size')"
            ).fetchall()
            for r in rows:
                prefs[r['clave'].replace('ui_', '')] = r['valor']
        except Exception:
            pass
        # Normalizar tema a Claro/Oscuro
        tema = prefs.get('theme', 'Oscuro')
        prefs['theme'] = 'Oscuro' if 'dark' in tema.lower() or tema == 'Oscuro' else 'Claro'
        return prefs

    def save_preferences(self, theme: str, density: str,
                         font_size: str, icon_size: str):
        try:
            for k, v in [('ui_theme', theme), ('ui_density', density),
                         ('ui_font_size', font_size), ('ui_icon_size', icon_size)]:
                self.db.execute(
                    "INSERT INTO configuraciones(clave,valor) VALUES(?,?) "
                    "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                    (k, str(v)))
            try: self.db.commit()
            except Exception: pass
        except Exception as e:
            logger.error("save_preferences: %s", e)

    def generate_qss(self) -> str:
        """Delega a theme_engine para obtener QSS."""
        prefs = self.get_user_preferences()
        try:
            from ui.themes.theme_engine import get_qss
            return get_qss(prefs['theme'])
        except Exception as e:
            logger.error("Error generando QSS: %s", e)
            return ""

    def apply_to_app(self, app):
        """Delega a theme_engine para aplicar tema globalmente."""
        try:
            from ui.themes.theme_engine import apply_theme
            apply_theme(app, self.get_user_preferences()['theme'])
        except Exception as e:
            logger.error("Error aplicando tema: %s", e)
