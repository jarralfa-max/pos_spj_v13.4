# core/services/theme_service.py — SPJ POS v13.30
"""
ThemeService — genera QSS global para Light y Dark mode.
Solo cambia COLORES. No modifica fuentes, paddings ni tamaños.
"""
import logging

logger = logging.getLogger(__name__)


class ThemeService:

    def __init__(self, db_conn):
        self.db = db_conn

        self.palettes = {
            'Light': {
                'bg': '#f5f6fa', 'fg': '#2c3e50', 'panel': '#ffffff',
                'primary': '#2E86C1', 'primary_hover': '#1A5276',
                'border': '#dcdde1', 'accent': '#e74c3c',
                'sidebar': '#1E272E', 'sidebar_text': '#D2DAE2',
                'input_bg': '#ffffff', 'table_alt': '#f8f9fa',
                'header_bg': '#f0f0f0',
            },
            'Dark': {
                'bg': '#1E272E', 'fg': '#D2DAE2', 'panel': '#2C3A47',
                'primary': '#3498db', 'primary_hover': '#2980b9',
                'border': '#485460', 'accent': '#e94560',
                'sidebar': '#141d26', 'sidebar_text': '#D2DAE2',
                'input_bg': '#354452', 'table_alt': '#253240',
                'header_bg': '#354452',
            },
        }

    def get_user_preferences(self) -> dict:
        prefs = {'theme': 'Light', 'density': 'Normal',
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
        """Solo cambia COLORES. No toca font-size, padding ni height."""
        prefs = self.get_user_preferences()
        c = self.palettes.get(prefs['theme'], self.palettes['Light'])

        return f"""
        /* ═══ SPJ POS — {prefs['theme']} Mode ═══ */

        QWidget {{ background-color: {c['bg']}; color: {c['fg']}; }}
        QMainWindow {{ background-color: {c['bg']}; }}
        QDialog {{ background-color: {c['bg']}; color: {c['fg']}; }}
        QStackedWidget {{ background-color: {c['bg']}; }}
        QLabel {{ color: {c['fg']}; background: transparent; }}
        QCheckBox, QRadioButton {{ color: {c['fg']}; background: transparent; }}

        /* Menú */
        QMenuBar {{ background: {c['panel']}; color: {c['fg']}; }}
        QMenuBar::item:selected {{ background: {c['primary']}; color: white; }}
        QMenu {{ background: {c['panel']}; color: {c['fg']}; border: 1px solid {c['border']}; }}
        QMenu::item:selected {{ background: {c['primary']}; color: white; }}

        /* Inputs */
        QLineEdit, QTextEdit, QPlainTextEdit,
        QSpinBox, QDoubleSpinBox, QTimeEdit, QDateEdit {{
            background: {c['input_bg']}; color: {c['fg']};
            border: 1px solid {c['border']}; border-radius: 3px;
            padding: 3px 6px; selection-background-color: {c['primary']};
        }}
        QLineEdit:focus, QTextEdit:focus {{ border-color: {c['primary']}; }}
        QComboBox {{
            background: {c['input_bg']}; color: {c['fg']};
            border: 1px solid {c['border']}; border-radius: 3px; padding: 3px 6px;
        }}
        QComboBox QAbstractItemView {{
            background: {c['panel']}; color: {c['fg']};
            selection-background-color: {c['primary']}; selection-color: white;
        }}
        QComboBox::drop-down {{ border: none; }}

        /* Tabs */
        QTabWidget::pane {{ border: 1px solid {c['border']}; background: {c['bg']}; }}
        QTabBar::tab {{
            background: {c['panel']}; color: {c['fg']};
            padding: 6px 14px; border: 1px solid {c['border']};
            border-bottom: none; border-radius: 3px 3px 0 0;
        }}
        QTabBar::tab:selected {{ background: {c['primary']}; color: white; font-weight: bold; }}
        QTabBar::tab:hover:!selected {{ background: {c['border']}; }}

        /* Tables */
        QTableWidget, QTableView, QListWidget, QTreeWidget {{
            background: {c['panel']}; color: {c['fg']};
            gridline-color: {c['border']}; border: 1px solid {c['border']};
            alternate-background-color: {c['table_alt']};
        }}
        QTableWidget::item:selected, QListWidget::item:selected {{
            background: {c['primary']}; color: white;
        }}
        QHeaderView::section {{
            background: {c['header_bg']}; color: {c['fg']};
            border: none; border-bottom: 1px solid {c['border']};
            font-weight: bold; padding: 4px;
        }}

        /* GroupBox */
        QGroupBox {{
            border: 1px solid {c['border']}; border-radius: 4px;
            margin-top: 8px; padding-top: 6px; color: {c['fg']};
        }}
        QGroupBox::title {{ color: {c['fg']}; font-weight: bold; }}

        /* Splitter */
        QSplitter::handle {{ background: {c['border']}; }}

        /* Scrollbars */
        QScrollBar:vertical {{ background: {c['bg']}; width: 8px; }}
        QScrollBar::handle:vertical {{
            background: {c['border']}; border-radius: 4px; min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {c['primary']}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height: 0px; }}
        QScrollBar:horizontal {{ background: {c['bg']}; height: 8px; }}
        QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 4px; }}

        QToolTip {{
            background: {c['panel']}; color: {c['fg']};
            border: 1px solid {c['primary']}; padding: 4px;
        }}
        """

    def apply_to_app(self, app):
        app.setStyleSheet(self.generate_qss())
