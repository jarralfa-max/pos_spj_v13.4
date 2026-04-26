"""
modulos/qss_builder.py — SPJ POS v13.4
Genera el QSS de los temas Claro/Oscuro a partir de design_tokens.Colors.

Templates auto-generados desde config.TEMAS original (commit pre-paso2).
Cada hex code de design_tokens se referencia como un f-string placeholder,
de modo que cambiar un color en design_tokens.py propaga al QSS sin tocar
este archivo.

USO:
    from modulos.qss_builder import build_themes
    TEMAS = build_themes()  # → {"Oscuro": "...QSS...", "Claro": "...QSS..."}

NOTA: Algunos hex codes (sombras hover, fondos sutiles) se conservan
literales porque aún no tienen alias en design_tokens. Ver TODO al final.
"""
from __future__ import annotations
from modulos.design_tokens import Colors


# ─── Template del tema Oscuro ─────────────────────────────────────────────
_TPL_OSCURO = f"""
        /* ═══════════════════════════════════════════════════════════════════
           TEMA OSCURO — SPJ POS v13.4 OPTIMIZED
           Paleta: Slate/Zinc modern dark theme con acentos magenta hover
           BOTONES REDUCIDOS: 36px height, padding 6px 12px
           ═══════════════════════════════════════════════════════════════════ */

        /* ===== VARIABLES GLOBALES ===== */
        QMainWindow, QWidget {{
            background-color: {Colors.NEUTRAL.SLATE_900};
            color: {Colors.NEUTRAL.SLATE_100};
            font-family: 'Segoe UI', 'Inter', 'Roboto', sans-serif;
            font-size: 11px;
        }}
        
        QDialog#loginDialog {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            color: {Colors.NEUTRAL.SLATE_100};
            border-radius: 12px;
        }}

        QLabel#loginLogo {{
            padding: 4px;
            background-color: transparent;
        }}

        QLabel#loginTitle {{
            font-size: 16px;
            font-weight: 700;
            color: {Colors.NEUTRAL.SLATE_100};
            margin-bottom: 5px;
        }}

        QLabel#loginSucursal {{
            font-size: 11px;
            color: {Colors.NEUTRAL.SLATE_400};
        }}

        QLabel#errorMsg {{
            color: {Colors.DANGER.BASE};
            font-weight: bold;
            padding: 5px;
            background-color: {Colors.DANGER.BG_SOFT};
            border-radius: 6px;
        }}

        QLineEdit#inputField {{
            padding: 5px 8px;
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            border-radius: 8px;
            background-color: {Colors.NEUTRAL.SLATE_800};
            color: {Colors.NEUTRAL.SLATE_100};
            font-size: 12px;
            min-height: 28px;
        }}

        QLineEdit#inputField:focus {{
            border: 2px solid {Colors.PRIMARY.BASE};
            background-color: #1E3A5F;
        }}

        QLineEdit#inputField::placeholder {{
            color: {Colors.NEUTRAL.SLATE_500};
        }}

        /* ===== TOOLTIPS GLOBALES ===== */
        QToolTip {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            color: {Colors.NEUTRAL.SLATE_100};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            border-radius: 6px;
            padding: 3px 6px;
            font-size: 10px;
            font-weight: 500;
        }}

        /* ===== BOTONES PRIMARIOS ===== */
        QPushButton#primaryBtn, QPushButton[variant="primary"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.PRIMARY.BASE}, stop:1 {Colors.PRIMARY.DARK});
            color: {Colors.NEUTRAL.WHITE};
            border: 1px solid #3B82F6;
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }}
        QPushButton#primaryBtn:hover, QPushButton[variant="primary"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.PRIMARY.HOVER}, stop:1 {Colors.PRIMARY.ACTIVE});
            border: 1px solid #FF4DFF;
        }}
        QPushButton#primaryBtn:pressed, QPushButton[variant="primary"]:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.PRIMARY.ACTIVE}, stop:1 #990099);
        }}

        /* ===== BOTONES SECUNDARIOS ===== */
        QPushButton#secondaryBtn, QPushButton[variant="secondary"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.NEUTRAL.SLATE_700}, stop:1 {Colors.NEUTRAL.SLATE_800});
            color: {Colors.NEUTRAL.SLATE_100};
            border: 1px solid {Colors.NEUTRAL.SLATE_600};
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }}
        QPushButton#secondaryBtn:hover, QPushButton[variant="secondary"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.NEUTRAL.SLATE_600}, stop:1 {Colors.NEUTRAL.SLATE_700});
            border: 1px solid {Colors.NEUTRAL.SLATE_500};
        }}

        /* ===== BOTONES ÉXITO ===== */
        QPushButton#successBtn, QPushButton[variant="success"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.SUCCESS.BASE}, stop:1 {Colors.SUCCESS.ACTIVE});
            color: {Colors.NEUTRAL.WHITE};
            border: 1px solid {Colors.SUCCESS.HOVER};
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }}
        QPushButton#successBtn:hover, QPushButton[variant="success"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.SUCCESS.HOVER}, stop:1 {Colors.SUCCESS.BASE});
            border: 1px solid #4ADE80;
        }}

        /* ===== BOTONES PELIGRO ===== */
        QPushButton#dangerBtn, QPushButton[variant="danger"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.DANGER.BASE}, stop:1 {Colors.DANGER.ACTIVE});
            color: {Colors.NEUTRAL.WHITE};
            border: 1px solid {Colors.DANGER.HOVER};
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }}
        QPushButton#dangerBtn:hover, QPushButton[variant="danger"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.DANGER.HOVER}, stop:1 {Colors.DANGER.BASE});
            border: 1px solid #F87171;
        }}

        /* ===== BOTONES ADVERTENCIA ===== */
        QPushButton#warningBtn, QPushButton[variant="warning"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.WARNING.BASE}, stop:1 {Colors.WARNING.ACTIVE});
            color: {Colors.NEUTRAL.WHITE};
            border: 1px solid {Colors.WARNING.HOVER};
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }}
        QPushButton#warningBtn:hover, QPushButton[variant="warning"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.WARNING.HOVER}, stop:1 {Colors.WARNING.BASE});
            border: 1px solid #FBBF24;
        }}

        /* ===== BOTONES OUTLINE ===== */
        QPushButton#outlineBtn, QPushButton[variant="outline"] {{
            background: transparent;
            color: {Colors.PRIMARY.BASE};
            border: 2px solid {Colors.PRIMARY.BASE};
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }}
        QPushButton#outlineBtn:hover, QPushButton[variant="outline"]:hover {{
            background: rgba(37, 99, 235, 0.1);
            border: 2px solid {Colors.PRIMARY.HOVER};
            color: {Colors.PRIMARY.HOVER};
        }}

        /* ===== BOTONES GENÉRICOS (fallback) ===== */
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.NEUTRAL.SLATE_700}, stop:1 {Colors.NEUTRAL.SLATE_800});
            color: {Colors.NEUTRAL.SLATE_100};
            border: 1px solid {Colors.NEUTRAL.SLATE_600};
            border-radius: 5px;
            padding: 2px 6px;
            font-weight: 600;
            font-size: 10px;
            min-height: 20px;
            max-height: 22px;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.NEUTRAL.SLATE_600}, stop:1 {Colors.NEUTRAL.SLATE_700});
            border: 1px solid {Colors.NEUTRAL.SLATE_500};
        }}
        QPushButton:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.NEUTRAL.SLATE_800}, stop:1 {Colors.NEUTRAL.SLATE_900});
        }}
        QPushButton:disabled {{
            background: {Colors.NEUTRAL.SLATE_800};
            color: {Colors.NEUTRAL.SLATE_500};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
        }}

        /* ===== SCROLLBARS ===== */
        QScrollBar:vertical {{
            background-color: {Colors.NEUTRAL.SLATE_900};
            width: 7px;
            border-radius: 4px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {Colors.NEUTRAL.SLATE_700};
            border-radius: 4px;
            min-height: 18px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {Colors.NEUTRAL.SLATE_600};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar:horizontal {{
            background-color: {Colors.NEUTRAL.SLATE_900};
            height: 7px;
            border-radius: 4px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal {{
            background-color: {Colors.NEUTRAL.SLATE_700};
            border-radius: 4px;
            min-width: 18px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background-color: {Colors.NEUTRAL.SLATE_600};
        }}

        /* ===== TABS ===== */
        QTabWidget::pane {{
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            border-radius: 8px;
            background-color: {Colors.NEUTRAL.SLATE_800};
        }}
        QTabBar::tab {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            color: {Colors.NEUTRAL.SLATE_400};
            border: 1px solid transparent;
            border-bottom: none;
            padding: 3px 8px;
            margin-right: 2px;
            border-radius: 5px 5px 0 0;
            font-weight: 500;
        }}
        QTabBar::tab:selected {{
            background-color: {Colors.NEUTRAL.SLATE_700};
            color: {Colors.NEUTRAL.SLATE_100};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            border-bottom: none;
            font-weight: 600;
        }}
        QTabBar::tab:hover:!selected {{
            background-color: #283548;
            color: {Colors.NEUTRAL.SLATE_100};
        }}

        /* ===== INPUTS ===== */
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            color: {Colors.NEUTRAL.SLATE_100};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            border-radius: 5px;
            padding: 3px 7px;
            selection-background-color: {Colors.PRIMARY.BASE};
            font-size: 11px;
            min-height: 22px;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, 
        QSpinBox:focus, QDoubleSpinBox:focus {{
            border: 2px solid {Colors.PRIMARY.HOVER};
            outline: none;
        }}
        QLineEdit:disabled, QTextEdit:disabled {{
            background-color: {Colors.NEUTRAL.SLATE_900};
            color: {Colors.NEUTRAL.SLATE_500};
        }}

        /* ===== COMBOBOX ===== */
        QComboBox {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            color: {Colors.NEUTRAL.SLATE_100};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            border-radius: 5px;
            padding: 3px 7px;
            min-height: 22px;
        }}
        QComboBox:hover {{
            border: 1px solid {Colors.NEUTRAL.SLATE_600};
        }}
        QComboBox:focus {{
            border: 2px solid {Colors.PRIMARY.HOVER};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
            border-radius: 0 5px 5px 0;
        }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 3px solid transparent;
            border-right: 3px solid transparent;
            border-top: 4px solid {Colors.NEUTRAL.SLATE_400};
            margin-right: 6px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            color: {Colors.NEUTRAL.SLATE_100};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            selection-background-color: {Colors.PRIMARY.BASE};
            border-radius: 5px;
            padding: 2px;
        }}
        QComboBox QAbstractItemView::item {{
            min-height: 22px;
            padding: 3px 7px;
            border-radius: 4px;
        }}
        QComboBox QAbstractItemView::item:hover {{
            background-color: {Colors.NEUTRAL.SLATE_700};
        }}
        QComboBox QAbstractItemView::item:selected {{
            background-color: {Colors.PRIMARY.BASE};
        }}

        /* ===== AUTOCOMPLETE POPUP (QCompleter) ===== */
        QListView {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            color: {Colors.NEUTRAL.SLATE_100};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            border-radius: 5px;
            outline: none;
            font-size: 11px;
        }}
        QListView::item {{
            padding: 3px 8px;
            min-height: 22px;
        }}
        QListView::item:hover {{
            background-color: {Colors.NEUTRAL.SLATE_700};
            color: {Colors.NEUTRAL.SLATE_100};
        }}
        QListView::item:selected {{
            background-color: {Colors.PRIMARY.BASE};
            color: {Colors.NEUTRAL.WHITE};
        }}

        /* ===== TABLAS ===== */
        QTableWidget, QTableView {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            color: {Colors.NEUTRAL.SLATE_100};
            gridline-color: {Colors.NEUTRAL.SLATE_700};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            alternate-background-color: {Colors.NEUTRAL.SLATE_900};
            border-radius: 8px;
        }}
        QTableWidget::item, QTableView::item {{
            padding: 4px 8px;
            border-bottom: 1px solid {Colors.NEUTRAL.SLATE_700};
        }}
        QTableWidget::item:selected, QTableView::item:selected {{
            background-color: {Colors.PRIMARY.BASE};
            color: {Colors.NEUTRAL.WHITE};
        }}
        QTableWidget::item:hover, QTableView::item:hover {{
            background-color: {Colors.NEUTRAL.SLATE_700};
        }}
        QHeaderView::section {{
            background-color: {Colors.NEUTRAL.SLATE_700};
            color: {Colors.NEUTRAL.SLATE_100};
            border: none;
            border-bottom: 2px solid {Colors.NEUTRAL.SLATE_600};
            font-weight: 600;
            padding: 3px 6px;
            text-transform: uppercase;
            font-size: 10px;
            letter-spacing: 0.5px;
            min-height: 24px;
            max-height: 24px;
        }}
        QHeaderView::section:hover {{
            background-color: {Colors.NEUTRAL.SLATE_600};
        }}

        /* ===== GRUPOS ===== */
        QGroupBox {{
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            border-radius: 6px;
            margin-top: 8px;
            padding-top: 8px;
            background-color: {Colors.NEUTRAL.SLATE_800};
            font-weight: 600;
            font-size: 11px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 6px;
            color: #60A5FA;
            background-color: {Colors.NEUTRAL.SLATE_800};
        }}

        /* ===== CARDS / FRAMES ===== */
        QFrame#card, QFrame[variant="card"] {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            border-radius: 6px;
            padding: 8px;
        }}
        QFrame#cardHover:hover, QFrame[variant="card-hover"]:hover {{
            background-color: {Colors.NEUTRAL.SLATE_700};
            border: 1px solid {Colors.NEUTRAL.SLATE_600};
        }}
        QFrame#kpiCard {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            border-radius: 8px;
            min-height: 70px;
            max-height: 90px;
        }}
        QFrame#kpiCard:hover {{
            background-color: #263548;
            border-color: {Colors.PRIMARY.BASE};
        }}
        QLabel#kpiValue {{
            color: {Colors.NEUTRAL.SLATE_100};
            font-size: 18px;
            font-weight: 700;
            background: transparent;
        }}

        /* ===== LABELS ===== */
        QLabel#heading {{
            font-size: 14px;
            font-weight: 700;
            color: {Colors.NEUTRAL.SLATE_100};
        }}
        QLabel#subheading {{
            font-size: 12px;
            font-weight: 600;
            color: {Colors.NEUTRAL.SLATE_400};
        }}
        QLabel#caption {{
            font-size: 10px;
            color: {Colors.NEUTRAL.SLATE_500};
        }}

        /* ===== CHECKBOX ===== */
        QCheckBox {{
            color: {Colors.NEUTRAL.SLATE_100};
            spacing: 6px;
            font-size: 11px;
        }}
        QCheckBox::indicator {{
            width: 14px;
            height: 14px;
            border-radius: 3px;
            border: 2px solid {Colors.NEUTRAL.SLATE_600};
            background-color: {Colors.NEUTRAL.SLATE_800};
        }}
        QCheckBox::indicator:checked {{
            background-color: {Colors.PRIMARY.BASE};
            border: 2px solid {Colors.PRIMARY.BASE};
        }}
        QCheckBox::indicator:hover {{
            border: 2px solid {Colors.PRIMARY.HOVER};
        }}

        /* ===== RADIO BUTTON ===== */
        QRadioButton {{
            color: {Colors.NEUTRAL.SLATE_100};
            spacing: 6px;
            font-size: 11px;
        }}
        QRadioButton::indicator {{
            width: 14px;
            height: 14px;
            border-radius: 7px;
            border: 2px solid {Colors.NEUTRAL.SLATE_600};
            background-color: {Colors.NEUTRAL.SLATE_800};
        }}
        QRadioButton::indicator:checked {{
            background-color: {Colors.PRIMARY.BASE};
            border: 2px solid {Colors.PRIMARY.BASE};
        }}
        QRadioButton::indicator:hover {{
            border: 2px solid {Colors.PRIMARY.HOVER};
        }}

        /* ===== PROGRESS BAR ===== */
        QProgressBar {{
            background-color: {Colors.NEUTRAL.SLATE_700};
            border-radius: 8px;
            height: 10px;
            text-align: center;
            border: 1px solid {Colors.NEUTRAL.SLATE_600};
        }}
        QProgressBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {Colors.PRIMARY.BASE}, stop:1 {Colors.PRIMARY.HOVER});
            border-radius: 6px;
        }}

        /* ===== SLIDER ===== */
        QSlider::groove:horizontal {{
            background-color: {Colors.NEUTRAL.SLATE_700};
            height: 8px;
            border-radius: 4px;
        }}
        QSlider::handle:horizontal {{
            background-color: {Colors.PRIMARY.BASE};
            width: 20px;
            margin: -6px 0;
            border-radius: 10px;
        }}
        QSlider::handle:horizontal:hover {{
            background-color: {Colors.PRIMARY.HOVER};
        }}

        /* ===== LIST WIDGET ===== */
        QListWidget {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            color: {Colors.NEUTRAL.SLATE_100};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            border-radius: 8px;
            padding: 8px;
        }}
        QListWidget::item {{
            padding: 10px 12px;
            border-radius: 6px;
            margin: 2px 0;
        }}
        QListWidget::item:hover {{
            background-color: {Colors.NEUTRAL.SLATE_700};
        }}
        QListWidget::item:selected {{
            background-color: {Colors.PRIMARY.BASE};
            color: {Colors.NEUTRAL.WHITE};
        }}

        /* ===== TREE WIDGET ===== */
        QTreeWidget {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            color: {Colors.NEUTRAL.SLATE_100};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            border-radius: 8px;
            alternate-background-color: {Colors.NEUTRAL.SLATE_900};
        }}
        QTreeWidget::item {{
            padding: 8px;
            border-radius: 4px;
        }}
        QTreeWidget::item:hover {{
            background-color: {Colors.NEUTRAL.SLATE_700};
        }}
        QTreeWidget::item:selected {{
            background-color: {Colors.PRIMARY.BASE};
        }}
        QTreeWidget::branch:has-children:!has-siblings:closed,
        QTreeWidget::branch:closed:has-children:has-siblings {{
            border-image: none;
        }}
        QTreeWidget::branch:open:has-children:!has-siblings,
        QTreeWidget::branch:open:has-children:has-siblings {{
            border-image: none;
        }}

        /* ===== MENU BAR ===== */
        QMenuBar {{
            background-color: {Colors.NEUTRAL.SLATE_900};
            color: {Colors.NEUTRAL.SLATE_100};
            border-bottom: 1px solid {Colors.NEUTRAL.SLATE_700};
            padding: 4px;
        }}
        QMenuBar::item {{
            padding: 8px 16px;
            border-radius: 6px;
        }}
        QMenuBar::item:selected {{
            background-color: {Colors.NEUTRAL.SLATE_700};
        }}
        QMenuBar::item:pressed {{
            background-color: {Colors.PRIMARY.BASE};
        }}

        /* ===== DROPDOWN MENU ===== */
        QMenu {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            color: {Colors.NEUTRAL.SLATE_100};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            border-radius: 8px;
            padding: 8px;
        }}
        QMenu::item {{
            padding: 10px 30px 10px 16px;
            border-radius: 6px;
        }}
        QMenu::item:selected {{
            background-color: {Colors.PRIMARY.BASE};
        }}
        QMenu::separator {{
            height: 1px;
            background-color: {Colors.NEUTRAL.SLATE_700};
            margin: 8px 0;
        }}

        /* ===== STATUS BAR ===== */
        QStatusBar {{
            background-color: {Colors.NEUTRAL.SLATE_900};
            color: {Colors.NEUTRAL.SLATE_400};
            border-top: 1px solid {Colors.NEUTRAL.SLATE_700};
        }}

        /* ===== SPLASH SCREEN ===== */
        QSplashScreen {{
            background-color: {Colors.NEUTRAL.SLATE_900};
            border: 2px solid {Colors.PRIMARY.BASE};
            border-radius: 16px;
        }}

        /* ===== CALENDAR ===== */
        QCalendarWidget {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            color: {Colors.NEUTRAL.SLATE_100};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            border-radius: 8px;
        }}
        QCalendarWidget QToolButton {{
            background-color: transparent;
            color: {Colors.NEUTRAL.SLATE_100};
            border: none;
            border-radius: 6px;
            padding: 8px;
            font-weight: 600;
        }}
        QCalendarWidget QToolButton:hover {{
            background-color: {Colors.NEUTRAL.SLATE_700};
        }}
        QCalendarWidget QMenu {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            color: {Colors.NEUTRAL.SLATE_100};
        }}
        QCalendarWidget QSpinBox {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            color: {Colors.NEUTRAL.SLATE_100};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
        }}

        /* ===== DOCK WIDGET ===== */
        QDockWidget {{
            titlebar-close-icon: none;
            titlebar-normal-icon: none;
        }}
        QDockWidget::title {{
            background-color: {Colors.NEUTRAL.SLATE_700};
            padding: 8px;
            font-weight: 600;
        }}
        QDockWidget::close-button, QDockWidget::float-button {{
            border: none;
            padding: 4px;
        }}
    """


# ─── Template del tema Claro ──────────────────────────────────────────────
_TPL_CLARO = f"""
        /* ═══════════════════════════════════════════════════════════════════
           TEMA CLARO — SPJ POS v13.4
           Paleta: Slate/Zinc modern light theme con acentos magenta hover
           ═══════════════════════════════════════════════════════════════════ */

        /* ===== VARIABLES GLOBALES ===== */
        QMainWindow, QDialog, QWidget {{
            background-color: {Colors.NEUTRAL.SLATE_50};
            color: {Colors.NEUTRAL.SLATE_900};
            font-family: 'Segoe UI', 'Inter', 'Roboto', sans-serif;
            font-size: 11px;
        }}

        /* ===== TOOLTIPS ===== */
        QToolTip {{
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 12px;
            font-weight: 500;
        }}

        /* ===== BOTONES PRIMARIOS ===== */
        QPushButton#primaryBtn, QPushButton[variant="primary"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.PRIMARY.BASE}, stop:1 {Colors.PRIMARY.DARK});
            color: {Colors.NEUTRAL.WHITE};
            border: 1px solid #3B82F6;
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }}
        QPushButton#primaryBtn:hover, QPushButton[variant="primary"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.PRIMARY.HOVER}, stop:1 {Colors.PRIMARY.ACTIVE});
            border: 1px solid #FF4DFF;
        }}
        QPushButton#primaryBtn:pressed, QPushButton[variant="primary"]:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.PRIMARY.ACTIVE}, stop:1 #990099);
        }}

        /* ===== BOTONES SECUNDARIOS ===== */
        QPushButton#secondaryBtn, QPushButton[variant="secondary"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.NEUTRAL.SLATE_100}, stop:1 {Colors.NEUTRAL.SLATE_200});
            color: {Colors.NEUTRAL.SLATE_700};
            border: 1px solid #CBD5E0;
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }}
        QPushButton#secondaryBtn:hover, QPushButton[variant="secondary"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.NEUTRAL.SLATE_200}, stop:1 #CBD5E0);
            border: 1px solid {Colors.NEUTRAL.SLATE_400};
        }}

        /* ===== BOTONES ÉXITO ===== */
        QPushButton#successBtn, QPushButton[variant="success"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.SUCCESS.BASE}, stop:1 {Colors.SUCCESS.ACTIVE});
            color: {Colors.NEUTRAL.WHITE};
            border: 1px solid {Colors.SUCCESS.HOVER};
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }}
        QPushButton#successBtn:hover, QPushButton[variant="success"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.SUCCESS.HOVER}, stop:1 {Colors.SUCCESS.BASE});
            border: 1px solid #4ADE80;
        }}

        /* ===== BOTONES PELIGRO ===== */
        QPushButton#dangerBtn, QPushButton[variant="danger"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.DANGER.BASE}, stop:1 {Colors.DANGER.ACTIVE});
            color: {Colors.NEUTRAL.WHITE};
            border: 1px solid {Colors.DANGER.HOVER};
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }}
        QPushButton#dangerBtn:hover, QPushButton[variant="danger"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.DANGER.HOVER}, stop:1 {Colors.DANGER.BASE});
            border: 1px solid #F87171;
        }}

        /* ===== BOTONES ADVERTENCIA ===== */
        QPushButton#warningBtn, QPushButton[variant="warning"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.WARNING.BASE}, stop:1 {Colors.WARNING.ACTIVE});
            color: {Colors.NEUTRAL.WHITE};
            border: 1px solid {Colors.WARNING.HOVER};
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }}
        QPushButton#warningBtn:hover, QPushButton[variant="warning"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.WARNING.HOVER}, stop:1 {Colors.WARNING.BASE});
            border: 1px solid #FBBF24;
        }}

        /* ===== BOTONES OUTLINE ===== */
        QPushButton#outlineBtn, QPushButton[variant="outline"] {{
            background: transparent;
            color: {Colors.PRIMARY.BASE};
            border: 2px solid {Colors.PRIMARY.BASE};
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }}
        QPushButton#outlineBtn:hover, QPushButton[variant="outline"]:hover {{
            background: rgba(37, 99, 235, 0.08);
            border: 2px solid {Colors.PRIMARY.HOVER};
            color: {Colors.PRIMARY.HOVER};
        }}

        /* ===== BOTONES GENÉRICOS (fallback) ===== */
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.NEUTRAL.WHITE}, stop:1 {Colors.NEUTRAL.SLATE_100});
            color: {Colors.NEUTRAL.SLATE_700};
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.NEUTRAL.SLATE_100}, stop:1 {Colors.NEUTRAL.SLATE_200});
            border: 1px solid #CBD5E0;
        }}
        QPushButton:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.NEUTRAL.SLATE_200}, stop:1 #CBD5E0);
        }}
        QPushButton:disabled {{
            background: {Colors.NEUTRAL.SLATE_100};
            color: {Colors.NEUTRAL.SLATE_400};
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
        }}

        /* ===== SCROLLBARS ===== */
        QScrollBar:vertical {{
            background-color: {Colors.NEUTRAL.SLATE_50};
            width: 7px;
            border-radius: 4px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background-color: #CBD5E0;
            border-radius: 4px;
            min-height: 18px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {Colors.NEUTRAL.SLATE_400};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar:horizontal {{
            background-color: {Colors.NEUTRAL.SLATE_50};
            height: 7px;
            border-radius: 4px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal {{
            background-color: #CBD5E0;
            border-radius: 4px;
            min-width: 18px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background-color: {Colors.NEUTRAL.SLATE_400};
        }}

        /* ===== TABS ===== */
        QTabWidget::pane {{
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
            border-radius: 8px;
            background-color: {Colors.NEUTRAL.WHITE};
        }}
        QTabBar::tab {{
            background-color: {Colors.NEUTRAL.SLATE_100};
            color: {Colors.NEUTRAL.SLATE_500};
            border: 1px solid transparent;
            border-bottom: none;
            padding: 3px 8px;
            margin-right: 2px;
            border-radius: 5px 5px 0 0;
            font-weight: 500;
        }}
        QTabBar::tab:selected {{
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
            border-bottom: none;
            font-weight: 600;
        }}
        QTabBar::tab:hover:!selected {{
            background-color: {Colors.NEUTRAL.SLATE_200};
            color: {Colors.NEUTRAL.SLATE_700};
        }}

        /* ===== INPUTS ===== */
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
            border-radius: 5px;
            padding: 3px 7px;
            selection-background-color: {Colors.PRIMARY.BASE};
            font-size: 11px;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, 
        QSpinBox:focus, QDoubleSpinBox:focus {{
            border: 2px solid {Colors.PRIMARY.HOVER};
            outline: none;
        }}
        QLineEdit:disabled, QTextEdit:disabled {{
            background-color: {Colors.NEUTRAL.SLATE_50};
            color: {Colors.NEUTRAL.SLATE_400};
        }}

        /* ===== COMBOBOX ===== */
        QComboBox {{
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
            border-radius: 5px;
            padding: 3px 7px;
            min-height: 22px;
        }}
        QComboBox:hover {{
            border: 1px solid #CBD5E0;
        }}
        QComboBox:focus {{
            border: 2px solid {Colors.PRIMARY.HOVER};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
            border-radius: 0 5px 5px 0;
        }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 3px solid transparent;
            border-right: 3px solid transparent;
            border-top: 4px solid {Colors.NEUTRAL.SLATE_500};
            margin-right: 6px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
            selection-background-color: {Colors.PRIMARY.BASE};
            border-radius: 5px;
            padding: 2px;
        }}
        QComboBox QAbstractItemView::item {{
            min-height: 22px;
            padding: 3px 7px;
            border-radius: 4px;
        }}
        QComboBox QAbstractItemView::item:hover {{
            background-color: {Colors.NEUTRAL.SLATE_100};
        }}
        QComboBox QAbstractItemView::item:selected {{
            background-color: {Colors.PRIMARY.BASE};
        }}

        /* ===== TABLAS ===== */
        QTableWidget, QTableView {{
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
            gridline-color: {Colors.NEUTRAL.SLATE_200};
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
            alternate-background-color: {Colors.NEUTRAL.SLATE_50};
            border-radius: 8px;
        }}
        QTableWidget::item, QTableView::item {{
            padding: 8px 12px;
            border-bottom: 1px solid {Colors.NEUTRAL.SLATE_200};
        }}
        QTableWidget::item:selected, QTableView::item:selected {{
            background-color: {Colors.PRIMARY.BASE};
            color: {Colors.NEUTRAL.WHITE};
        }}
        QTableWidget::item:hover, QTableView::item:hover {{
            background-color: {Colors.NEUTRAL.SLATE_100};
        }}
        QHeaderView::section {{
            background-color: {Colors.NEUTRAL.SLATE_100};
            color: {Colors.NEUTRAL.SLATE_700};
            border: none;
            border-bottom: 2px solid {Colors.NEUTRAL.SLATE_200};
            font-weight: 600;
            padding: 3px 6px;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.5px;
            min-height: 20px;
            max-height: 20px;
        }}
        QHeaderView::section:hover {{
            background-color: {Colors.NEUTRAL.SLATE_200};
        }}

        /* ===== GRUPOS ===== */
        QGroupBox {{
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
            border-radius: 6px;
            margin-top: 8px;
            padding-top: 8px;
            background-color: {Colors.NEUTRAL.WHITE};
            font-weight: 600;
            font-size: 11px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 6px;
            color: {Colors.PRIMARY.BASE};
            background-color: {Colors.NEUTRAL.WHITE};
        }}

        /* ===== CARDS / FRAMES ===== */
        QFrame#card, QFrame[variant="card"] {{
            background-color: {Colors.NEUTRAL.WHITE};
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
            border-radius: 6px;
            padding: 8px;
        }}
        QFrame#cardHover:hover, QFrame[variant="card-hover"]:hover {{
            background-color: {Colors.NEUTRAL.SLATE_50};
            border: 1px solid #CBD5E0;
        }}
        QFrame#kpiCard {{
            background-color: {Colors.NEUTRAL.WHITE};
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
            border-radius: 8px;
            min-height: 70px;
            max-height: 90px;
        }}
        QFrame#kpiCard:hover {{
            background-color: {Colors.NEUTRAL.SLATE_100};
            border-color: {Colors.PRIMARY.BASE};
        }}
        QLabel#kpiValue {{
            color: {Colors.NEUTRAL.SLATE_900};
            font-size: 18px;
            font-weight: 700;
            background: transparent;
        }}

        /* ===== LABELS ===== */
        QLabel#heading {{
            font-size: 14px;
            font-weight: 700;
            color: {Colors.NEUTRAL.SLATE_900};
        }}
        QLabel#subheading {{
            font-size: 12px;
            font-weight: 600;
            color: {Colors.NEUTRAL.SLATE_500};
        }}
        QLabel#caption {{
            font-size: 10px;
            color: {Colors.NEUTRAL.SLATE_400};
        }}

        /* ===== CHECKBOX ===== */
        QCheckBox {{
            color: {Colors.NEUTRAL.SLATE_900};
            spacing: 6px;
            font-size: 11px;
        }}
        QCheckBox::indicator {{
            width: 14px;
            height: 14px;
            border-radius: 3px;
            border: 2px solid #CBD5E0;
            background-color: {Colors.NEUTRAL.WHITE};
        }}
        QCheckBox::indicator:checked {{
            background-color: {Colors.PRIMARY.BASE};
            border: 2px solid {Colors.PRIMARY.BASE};
        }}
        QCheckBox::indicator:hover {{
            border: 2px solid {Colors.PRIMARY.HOVER};
        }}

        /* ===== RADIO BUTTON ===== */
        QRadioButton {{
            color: {Colors.NEUTRAL.SLATE_900};
            spacing: 6px;
            font-size: 11px;
        }}
        QRadioButton::indicator {{
            width: 14px;
            height: 14px;
            border-radius: 7px;
            border: 2px solid #CBD5E0;
            background-color: {Colors.NEUTRAL.WHITE};
        }}
        QRadioButton::indicator:checked {{
            background-color: {Colors.PRIMARY.BASE};
            border: 2px solid {Colors.PRIMARY.BASE};
        }}
        QRadioButton::indicator:hover {{
            border: 2px solid {Colors.PRIMARY.HOVER};
        }}

        /* ===== PROGRESS BAR ===== */
        QProgressBar {{
            background-color: {Colors.NEUTRAL.SLATE_200};
            border-radius: 8px;
            height: 10px;
            text-align: center;
            border: 1px solid #CBD5E0;
        }}
        QProgressBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {Colors.PRIMARY.BASE}, stop:1 {Colors.PRIMARY.HOVER});
            border-radius: 6px;
        }}

        /* ===== SLIDER ===== */
        QSlider::groove:horizontal {{
            background-color: {Colors.NEUTRAL.SLATE_200};
            height: 8px;
            border-radius: 4px;
        }}
        QSlider::handle:horizontal {{
            background-color: {Colors.PRIMARY.BASE};
            width: 20px;
            margin: -6px 0;
            border-radius: 10px;
        }}
        QSlider::handle:horizontal:hover {{
            background-color: {Colors.PRIMARY.HOVER};
        }}

        /* ===== LIST WIDGET ===== */
        QListWidget {{
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
            border-radius: 8px;
            padding: 8px;
        }}
        QListWidget::item {{
            padding: 10px 12px;
            border-radius: 6px;
            margin: 2px 0;
        }}
        QListWidget::item:hover {{
            background-color: {Colors.NEUTRAL.SLATE_100};
        }}
        QListWidget::item:selected {{
            background-color: {Colors.PRIMARY.BASE};
            color: {Colors.NEUTRAL.WHITE};
        }}

        /* ===== TREE WIDGET ===== */
        QTreeWidget {{
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
            border-radius: 8px;
            alternate-background-color: {Colors.NEUTRAL.SLATE_50};
        }}
        QTreeWidget::item {{
            padding: 8px;
            border-radius: 4px;
        }}
        QTreeWidget::item:hover {{
            background-color: {Colors.NEUTRAL.SLATE_100};
        }}
        QTreeWidget::item:selected {{
            background-color: {Colors.PRIMARY.BASE};
        }}

        /* ===== MENU BAR ===== */
        QMenuBar {{
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
            border-bottom: 1px solid {Colors.NEUTRAL.SLATE_200};
            padding: 4px;
        }}
        QMenuBar::item {{
            padding: 8px 16px;
            border-radius: 6px;
        }}
        QMenuBar::item:selected {{
            background-color: {Colors.NEUTRAL.SLATE_100};
        }}
        QMenuBar::item:pressed {{
            background-color: {Colors.PRIMARY.BASE};
            color: {Colors.NEUTRAL.WHITE};
        }}

        /* ===== DROPDOWN MENU ===== */
        QMenu {{
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
            border-radius: 8px;
            padding: 8px;
        }}
        QMenu::item {{
            padding: 10px 30px 10px 16px;
            border-radius: 6px;
        }}
        QMenu::item:selected {{
            background-color: {Colors.PRIMARY.BASE};
            color: {Colors.NEUTRAL.WHITE};
        }}
        QMenu::separator {{
            height: 1px;
            background-color: {Colors.NEUTRAL.SLATE_200};
            margin: 8px 0;
        }}

        /* ===== STATUS BAR ===== */
        QStatusBar {{
            background-color: {Colors.NEUTRAL.SLATE_50};
            color: {Colors.NEUTRAL.SLATE_500};
            border-top: 1px solid {Colors.NEUTRAL.SLATE_200};
        }}

        /* ===== SPLASH SCREEN ===== */
        QSplashScreen {{
            background-color: {Colors.NEUTRAL.WHITE};
            border: 2px solid {Colors.PRIMARY.BASE};
            border-radius: 16px;
        }}

        /* ===== CALENDAR ===== */
        QCalendarWidget {{
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
            border-radius: 8px;
        }}
        QCalendarWidget QToolButton {{
            background-color: transparent;
            color: {Colors.NEUTRAL.SLATE_900};
            border: none;
            border-radius: 6px;
            padding: 8px;
            font-weight: 600;
        }}
        QCalendarWidget QToolButton:hover {{
            background-color: {Colors.NEUTRAL.SLATE_100};
        }}
        QCalendarWidget QMenu {{
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
        }}
        QCalendarWidget QSpinBox {{
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
        }}

        /* ===== DOCK WIDGET ===== */
        QDockWidget {{
            titlebar-close-icon: none;
            titlebar-normal-icon: none;
        }}
        QDockWidget::title {{
            background-color: {Colors.NEUTRAL.SLATE_100};
            padding: 8px;
            font-weight: 600;
        }}
        QDockWidget::close-button, QDockWidget::float-button {{
            border: none;
            padding: 4px;
        }}
    """



def build_themes() -> dict[str, str]:
    """Retorna {"Oscuro": qss_oscuro, "Claro": qss_claro}."""
    return {"Oscuro": _TPL_OSCURO, "Claro": _TPL_CLARO}


# ─── TODO: extender design_tokens.Colors con estos alias para
#  reemplazar los últimos hex literales:
#
#    PRIMARY.BASE_LIGHT  = "#3B82F6"  (Blue-500, hover sutil)
#    PRIMARY.BASE_LIGHTER= "#60A5FA"  (Blue-400)
#    DANGER.LIGHT        = "#F87171"  (Red-400)
#    SUCCESS.LIGHT       = "#4ADE80"  (Green-400)
#    WARNING.LIGHT       = "#FBBF24"  (Yellow-400)
#    NEUTRAL.SLATE_300_ALT="#CBD5E0"  (typo histórico)
#    PRIMARY.DARKER       ="#990099"  (magenta dark)
#    NEUTRAL.DARK_HOVER   ="#1E3A5F"
#    NEUTRAL.DARK_ALT     ="#263548"
#    NEUTRAL.DARK_ALT_2   ="#283548"
