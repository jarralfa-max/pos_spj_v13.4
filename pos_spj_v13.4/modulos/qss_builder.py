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

        /* ===== ENTERPRISE DIALOG / MODAL SYSTEM (DARK) ===== */
        QDialog {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            color: {Colors.NEUTRAL.SLATE_100};
        }}
        QDialogButtonBox QPushButton {{
            min-width: 80px;
            min-height: 30px;
            padding: 4px 14px;
            border-radius: 5px;
            font-size: 11px;
            font-weight: 600;
            background-color: {Colors.NEUTRAL.SLATE_700};
            color: {Colors.NEUTRAL.SLATE_100};
            border: 1px solid {Colors.NEUTRAL.SLATE_600};
        }}
        QDialogButtonBox QPushButton:hover {{
            background-color: {Colors.NEUTRAL.SLATE_600};
            border-color: {Colors.PRIMARY.BASE};
            color: white;
        }}
        QDialogButtonBox QPushButton[text="OK"],
        QDialogButtonBox QPushButton[text="Aceptar"],
        QDialogButtonBox QPushButton[text="Guardar"],
        QDialogButtonBox QPushButton[text="Confirmar"] {{
            background-color: {Colors.PRIMARY.BASE};
            color: white;
            border-color: {Colors.PRIMARY.BASE};
        }}
        QDialogButtonBox QPushButton[text="OK"]:hover,
        QDialogButtonBox QPushButton[text="Aceptar"]:hover,
        QDialogButtonBox QPushButton[text="Guardar"]:hover,
        QDialogButtonBox QPushButton[text="Confirmar"]:hover {{
            background-color: {Colors.PRIMARY.HOVER};
        }}
        QMessageBox {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            color: {Colors.NEUTRAL.SLATE_100};
        }}
        QMessageBox QLabel {{
            color: {Colors.NEUTRAL.SLATE_100};
            font-size: 12px;
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
            background-color: {Colors.NEUTRAL.DARK_INPUT_FOCUS};
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

        /* ===== SEMANTIC OPERATIONAL COLORS (DARK) ===== */
        QPushButton#editBtn, QPushButton#searchBtn, QPushButton[variant="edit"],
        QPushButton[variant="search"] {{
            background: {Colors.PRIMARY.BASE};
            color: white;
            border: none;
            border-radius: 5px;
            padding: 4px 10px;
            font-weight: 600;
            font-size: 11px;
            min-height: 28px;
        }}
        QPushButton#editBtn:hover, QPushButton#searchBtn:hover,
        QPushButton#cartEditBtn:hover,
        QPushButton[variant="edit"]:hover, QPushButton[variant="search"]:hover {{
            background: {Colors.PRIMARY.HOVER};
        }}
        QPushButton#editBtn:disabled, QPushButton#searchBtn:disabled {{
            background: {Colors.NEUTRAL.SLATE_700};
            color: {Colors.NEUTRAL.SLATE_500};
        }}
        QPushButton#deleteBtn, QPushButton#removeBtn, QPushButton[variant="delete"],
        QPushButton[variant="remove"] {{
            background: {Colors.DANGER.BASE};
            color: white;
            border: none;
            border-radius: 5px;
            padding: 4px 10px;
            font-weight: 600;
            font-size: 11px;
            min-height: 28px;
        }}
        QPushButton#deleteBtn:hover, QPushButton#removeBtn:hover,
        QPushButton#cartDeleteBtn:hover,
        QPushButton[variant="delete"]:hover, QPushButton[variant="remove"]:hover {{
            background: {Colors.DANGER.HOVER};
        }}
        QPushButton#deleteBtn:disabled, QPushButton#removeBtn:disabled {{
            background: {Colors.NEUTRAL.SLATE_700};
            color: {Colors.NEUTRAL.SLATE_500};
        }}
        QPushButton#addBtn, QPushButton#createBtn, QPushButton[variant="add"],
        QPushButton[variant="create"] {{
            background: {Colors.SUCCESS.BASE};
            color: white;
            border: none;
            border-radius: 5px;
            padding: 4px 10px;
            font-weight: 600;
            font-size: 11px;
            min-height: 28px;
        }}
        QPushButton#addBtn:hover, QPushButton#createBtn:hover,
        QPushButton[variant="add"]:hover, QPushButton[variant="create"]:hover {{
            background: {Colors.SUCCESS.HOVER};
        }}
        QPushButton#addBtn:disabled, QPushButton#createBtn:disabled {{
            background: {Colors.NEUTRAL.SLATE_700};
            color: {Colors.NEUTRAL.SLATE_500};
        }}
        QPushButton#discountBadgeBtn {{
            background: #EF4444;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 1px 6px;
            font-size: 10px;
            font-weight: 700;
            min-height: 20px;
        }}
        QPushButton#discountBadgeBtn:hover {{
            background: #DC2626;
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

        /* ===== BOTONES GENÉRICOS (fallback) =====
           Solo aplica a QPushButton SIN objectName/variant. Los rangos de
           altura se omiten para que cada botón pueda crecer según su layout
           (ej. botones de "Acciones" en Ventas que llenan el QGroupBox). */
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.NEUTRAL.SLATE_700}, stop:1 {Colors.NEUTRAL.SLATE_800});
            color: {Colors.NEUTRAL.SLATE_100};
            border: 1px solid {Colors.NEUTRAL.SLATE_600};
            border-radius: 5px;
            padding: 4px 8px;
            font-weight: 600;
            font-size: 10px;
            min-height: 22px;
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
            top: -1px;
        }}
        QTabBar {{
            qproperty-drawBase: 0;
            background: transparent;
        }}
        QTabBar::tab {{
            background-color: {Colors.NEUTRAL.SLATE_900};
            color: {Colors.NEUTRAL.SLATE_300};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            border-bottom: none;
            padding: 6px 14px;
            margin-right: 3px;
            border-radius: 6px 6px 0 0;
            font-weight: 600;
            min-width: 90px;
        }}
        QTabBar::tab:selected {{
            background-color: {Colors.PRIMARY.BASE};
            color: {Colors.NEUTRAL.WHITE};
            border: 1px solid {Colors.PRIMARY.DARK};
            border-bottom: 2px solid {Colors.PRIMARY.HOVER};
            font-weight: 700;
        }}
        QTabBar::tab:hover:!selected {{
            background-color: {Colors.NEUTRAL.SLATE_700};
            color: {Colors.NEUTRAL.SLATE_100};
            border: 1px solid {Colors.NEUTRAL.SLATE_600};
        }}
        QTabBar::tab:disabled {{
            color: {Colors.NEUTRAL.SLATE_500};
            background-color: {Colors.NEUTRAL.SLATE_800};
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

        /* ===== FOCUS RINGS ===== */
        QPushButton:focus {{
            outline: none;
        }}

        /* ===== BUSCADOR DE PRODUCTOS (ProductSearchWidget) ===== */
        QFrame#productSearchPopup {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            border: 1px solid {Colors.NEUTRAL.SLATE_600};
            border-radius: 8px;
        }}
        QListWidget#productSearchPopupList {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            color: {Colors.NEUTRAL.SLATE_100};
            border: none;
        }}
        QListWidget#productSearchPopupList::item {{
            padding: 6px 10px;
        }}
        QListWidget#productSearchPopupList::item:hover {{
            background-color: {Colors.NEUTRAL.SLATE_700};
        }}
        QListWidget#productSearchPopupList::item:selected {{
            background-color: {Colors.PRIMARY.BASE};
            color: {Colors.NEUTRAL.WHITE};
        }}

        /* ═══════════════════════════════════════════════════════════════════
           QR MODULE — DARK THEME
           ═══════════════════════════════════════════════════════════════════ */

        QGroupBox#sectionCard {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            border-radius: 8px;
            font-weight: 700;
            font-size: 10px;
            padding-top: 14px;
        }}
        QGroupBox#sectionCard::title {{
            color: #60A5FA;
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }}

        QLabel#statusBadge {{
            background-color: {Colors.NEUTRAL.SLATE_700};
            color: {Colors.NEUTRAL.SLATE_400};
            border-radius: 10px;
            padding: 2px 8px;
            font-size: 10px;
            font-weight: 600;
        }}
        QLabel#statusBadge[variant="warning"] {{ background-color: #78350F; color: #FDE68A; }}
        QLabel#statusBadge[variant="success"] {{ background-color: #14532D; color: #86EFAC; }}
        QLabel#statusBadge[variant="accent"]  {{ background-color: #2E1065; color: #C4B5FD; }}
        QLabel#statusBadge[variant="danger"]  {{ background-color: #7F1D1D; color: #FCA5A5; }}
        QLabel#statusBadge[variant="info"]    {{ background-color: #164E63; color: #67E8F9; }}

        QLabel#monoLabel {{
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 12px; font-weight: 700;
            color: {Colors.NEUTRAL.SLATE_100}; background: transparent;
        }}
        QLineEdit#monoInput {{
            font-family: 'Consolas', 'Courier New', monospace;
            background-color: {Colors.NEUTRAL.SLATE_900};
            color: {Colors.NEUTRAL.SLATE_400};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            border-radius: 4px; padding: 4px 8px;
        }}

        QLabel#formSection {{
            font-size: 10px; font-weight: 700;
            color: {Colors.NEUTRAL.SLATE_500};
            letter-spacing: 0.5px;
            padding: 4px 0 2px 0;
            border-bottom: 1px solid {Colors.NEUTRAL.SLATE_700};
        }}

        QLineEdit#scanInput {{
            border: 2px solid {Colors.SUCCESS.BASE};
            border-radius: 6px; padding: 5px 10px; font-size: 12px;
            background-color: {Colors.NEUTRAL.SLATE_900};
            color: {Colors.NEUTRAL.SLATE_100};
        }}
        QLineEdit#scanInput:focus {{ border-color: {Colors.SUCCESS.HOVER}; }}

        QLabel#hero {{ font-size: 22px; font-weight: 800; color: {Colors.NEUTRAL.SLATE_100}; background: transparent; }}
        QLabel#hero[variant="success"] {{ color: #4ADE80; }}
        QLabel#hero[variant="danger"]  {{ color: #F87171; }}
        QLabel#hero[variant="warning"] {{ color: #FBBF24; }}
        QLabel#hero[variant="info"]    {{ color: #67E8F9; }}

        QFrame#qrPreviewBox {{
            background-color: {Colors.NEUTRAL.SLATE_900};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            border-radius: 6px;
        }}
        QLabel#qrPreviewIcon {{ font-size: 24px; background: transparent; }}
        QLabel#qrPreviewArea {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            border: 2px dashed {Colors.NEUTRAL.SLATE_600};
            border-radius: 8px;
            color: {Colors.NEUTRAL.SLATE_600}; font-size: 36px;
        }}

        QPushButton#qrTypeButton {{
            background-color: {Colors.NEUTRAL.SLATE_800};
            border: 1px solid {Colors.NEUTRAL.SLATE_600};
            border-radius: 6px;
            color: {Colors.NEUTRAL.SLATE_400};
            font-size: 10px; padding: 6px 4px; text-align: center;
        }}
        QPushButton#qrTypeButton:hover {{
            background-color: {Colors.NEUTRAL.SLATE_700};
            border-color: {Colors.PRIMARY.BASE};
            color: {Colors.NEUTRAL.SLATE_100};
        }}
        QPushButton#qrTypeButton:checked {{
            background-color: #1E3A5F;
            border: 2px solid #3B82F6;
            color: {Colors.NEUTRAL.SLATE_100}; font-weight: 700;
        }}

        QListWidget#containerList {{
            background-color: {Colors.NEUTRAL.SLATE_900};
            border: 1px solid {Colors.NEUTRAL.SLATE_700};
            border-radius: 6px;
        }}
        QListWidget#containerList::item {{ border-radius: 4px; padding: 1px; margin: 1px 2px; }}
        QListWidget#containerList::item:hover {{ background-color: {Colors.NEUTRAL.SLATE_700}; }}
        QListWidget#containerList::item:selected {{ background-color: #1E3A5F; border: 1px solid {Colors.PRIMARY.BASE}; }}
        QWidget#containerCard {{ background-color: {Colors.NEUTRAL.SLATE_800}; border-radius: 6px; }}

        QFrame#infoCallout {{
            background-color: #1E3A5F;
            border-left: 3px solid {Colors.PRIMARY.BASE};
            border-radius: 4px;
        }}

        QLabel#stepNum {{
            background-color: {Colors.NEUTRAL.SLATE_700};
            color: {Colors.NEUTRAL.SLATE_400};
            border-radius: 12px; font-weight: 700; font-size: 11px;
        }}
        QLabel#stepNum[active="true"] {{ background-color: {Colors.PRIMARY.BASE}; color: {Colors.NEUTRAL.WHITE}; }}
        QLabel#stepLabel {{ color: {Colors.NEUTRAL.SLATE_500}; font-size: 11px; }}
        QLabel#stepLabel[active="true"] {{ color: {Colors.NEUTRAL.SLATE_100}; font-weight: 600; }}
        QLabel#stepArrow {{ color: {Colors.NEUTRAL.SLATE_600}; font-size: 14px; background: transparent; }}

        QLabel#qrAssignHeader, QLabel#qrRecvHeader {{
            font-size: 13px; font-weight: 700;
            color: {Colors.NEUTRAL.SLATE_100}; background: transparent;
        }}
        QFrame[frameShape="4"] {{ color: {Colors.NEUTRAL.SLATE_700}; max-height: 1px; }}
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

        /* ===== ENTERPRISE DIALOG / MODAL SYSTEM (LIGHT) ===== */
        QDialog {{
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
        }}
        QDialogButtonBox QPushButton {{
            min-width: 80px;
            min-height: 30px;
            padding: 4px 14px;
            border-radius: 5px;
            font-size: 11px;
            font-weight: 600;
            background-color: {Colors.NEUTRAL.SLATE_100};
            color: {Colors.NEUTRAL.SLATE_700};
            border: 1px solid {Colors.NEUTRAL.SLATE_300};
        }}
        QDialogButtonBox QPushButton:hover {{
            background-color: {Colors.NEUTRAL.SLATE_200};
            border-color: {Colors.PRIMARY.BASE};
            color: {Colors.NEUTRAL.SLATE_900};
        }}
        QDialogButtonBox QPushButton[text="OK"],
        QDialogButtonBox QPushButton[text="Aceptar"],
        QDialogButtonBox QPushButton[text="Guardar"],
        QDialogButtonBox QPushButton[text="Confirmar"] {{
            background-color: {Colors.PRIMARY.BASE};
            color: white;
            border-color: {Colors.PRIMARY.BASE};
        }}
        QDialogButtonBox QPushButton[text="OK"]:hover,
        QDialogButtonBox QPushButton[text="Aceptar"]:hover,
        QDialogButtonBox QPushButton[text="Guardar"]:hover,
        QDialogButtonBox QPushButton[text="Confirmar"]:hover {{
            background-color: {Colors.PRIMARY.HOVER};
        }}
        QMessageBox {{
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
        }}
        QMessageBox QLabel {{
            color: {Colors.NEUTRAL.SLATE_800};
            font-size: 12px;
        }}

        QDialog#loginDialog {{
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
            border-radius: 12px;
        }}

        QLabel#loginLogo {{
            padding: 4px;
            background-color: transparent;
        }}

        QLabel#loginTitle {{
            font-size: 16px;
            font-weight: 700;
            color: {Colors.NEUTRAL.SLATE_900};
            margin-bottom: 5px;
        }}

        QLabel#loginSucursal {{
            font-size: 11px;
            color: {Colors.NEUTRAL.SLATE_500};
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
            border: 1px solid {Colors.NEUTRAL.SLATE_300};
            border-radius: 8px;
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
            font-size: 12px;
            min-height: 28px;
        }}

        QLineEdit#inputField:focus {{
            border: 2px solid {Colors.PRIMARY.BASE};
            background-color: {Colors.NEUTRAL.SLATE_50};
        }}

        QLineEdit#inputField::placeholder {{
            color: {Colors.NEUTRAL.SLATE_400};
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

        /* ===== SEMANTIC OPERATIONAL COLORS (LIGHT) ===== */
        QPushButton#editBtn, QPushButton#searchBtn, QPushButton[variant="edit"],
        QPushButton[variant="search"] {{
            background: {Colors.PRIMARY.BASE};
            color: white;
            border: none;
            border-radius: 5px;
            padding: 4px 10px;
            font-weight: 600;
            font-size: 11px;
            min-height: 28px;
        }}
        QPushButton#editBtn:hover, QPushButton#searchBtn:hover,
        QPushButton#cartEditBtn:hover,
        QPushButton[variant="edit"]:hover, QPushButton[variant="search"]:hover {{
            background: {Colors.PRIMARY.HOVER};
        }}
        QPushButton#editBtn:disabled, QPushButton#searchBtn:disabled {{
            background: {Colors.NEUTRAL.SLATE_200};
            color: {Colors.NEUTRAL.SLATE_400};
        }}
        QPushButton#deleteBtn, QPushButton#removeBtn, QPushButton[variant="delete"],
        QPushButton[variant="remove"] {{
            background: {Colors.DANGER.BASE};
            color: white;
            border: none;
            border-radius: 5px;
            padding: 4px 10px;
            font-weight: 600;
            font-size: 11px;
            min-height: 28px;
        }}
        QPushButton#deleteBtn:hover, QPushButton#removeBtn:hover,
        QPushButton#cartDeleteBtn:hover,
        QPushButton[variant="delete"]:hover, QPushButton[variant="remove"]:hover {{
            background: {Colors.DANGER.HOVER};
        }}
        QPushButton#deleteBtn:disabled, QPushButton#removeBtn:disabled {{
            background: {Colors.NEUTRAL.SLATE_200};
            color: {Colors.NEUTRAL.SLATE_400};
        }}
        QPushButton#addBtn, QPushButton#createBtn, QPushButton[variant="add"],
        QPushButton[variant="create"] {{
            background: {Colors.SUCCESS.BASE};
            color: white;
            border: none;
            border-radius: 5px;
            padding: 4px 10px;
            font-weight: 600;
            font-size: 11px;
            min-height: 28px;
        }}
        QPushButton#addBtn:hover, QPushButton#createBtn:hover,
        QPushButton[variant="add"]:hover, QPushButton[variant="create"]:hover {{
            background: {Colors.SUCCESS.HOVER};
        }}
        QPushButton#addBtn:disabled, QPushButton#createBtn:disabled {{
            background: {Colors.NEUTRAL.SLATE_200};
            color: {Colors.NEUTRAL.SLATE_400};
        }}
        QPushButton#discountBadgeBtn {{
            background: #EF4444;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 1px 6px;
            font-size: 10px;
            font-weight: 700;
            min-height: 20px;
        }}
        QPushButton#discountBadgeBtn:hover {{
            background: #DC2626;
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
            top: -1px;
        }}
        QTabBar {{
            qproperty-drawBase: 0;
            background: transparent;
        }}
        QTabBar::tab {{
            background-color: {Colors.NEUTRAL.SLATE_200};
            color: {Colors.NEUTRAL.SLATE_600};
            border: 1px solid {Colors.NEUTRAL.SLATE_300};
            border-bottom: none;
            padding: 6px 14px;
            margin-right: 3px;
            border-radius: 6px 6px 0 0;
            font-weight: 600;
            min-width: 90px;
        }}
        QTabBar::tab:selected {{
            background-color: {Colors.PRIMARY.BASE};
            color: {Colors.NEUTRAL.WHITE};
            border: 1px solid {Colors.PRIMARY.DARK};
            border-bottom: 2px solid {Colors.PRIMARY.HOVER};
            font-weight: 700;
        }}
        QTabBar::tab:hover:!selected {{
            background-color: {Colors.NEUTRAL.SLATE_300};
            color: {Colors.NEUTRAL.SLATE_900};
            border: 1px solid {Colors.NEUTRAL.SLATE_400};
        }}
        QTabBar::tab:disabled {{
            color: {Colors.NEUTRAL.SLATE_400};
            background-color: {Colors.NEUTRAL.SLATE_100};
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

        /* ===== AUTOCOMPLETE POPUP (QCompleter) ===== */
        QListView {{
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
            border-radius: 5px;
            outline: none;
            font-size: 11px;
        }}
        QListView::item {{
            padding: 3px 8px;
            min-height: 22px;
        }}
        QListView::item:hover {{
            background-color: {Colors.NEUTRAL.SLATE_100};
            color: {Colors.NEUTRAL.SLATE_900};
        }}
        QListView::item:selected {{
            background-color: {Colors.PRIMARY.BASE};
            color: {Colors.NEUTRAL.WHITE};
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

        /* ===== FOCUS RINGS ===== */
        QPushButton:focus {{
            outline: none;
        }}

        /* ===== BUSCADOR DE PRODUCTOS (ProductSearchWidget) ===== */
        QFrame#productSearchPopup {{
            background-color: {Colors.NEUTRAL.WHITE};
            border: 1px solid {Colors.NEUTRAL.SLATE_300};
            border-radius: 8px;
        }}
        QListWidget#productSearchPopupList {{
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
            border: none;
        }}
        QListWidget#productSearchPopupList::item {{
            padding: 6px 10px;
        }}
        QListWidget#productSearchPopupList::item:hover {{
            background-color: {Colors.NEUTRAL.SLATE_100};
        }}
        QListWidget#productSearchPopupList::item:selected {{
            background-color: {Colors.PRIMARY.BASE};
            color: {Colors.NEUTRAL.WHITE};
        }}

        /* ═══════════════════════════════════════════════════════════════════
           QR MODULE — LIGHT THEME
           ═══════════════════════════════════════════════════════════════════ */

        QGroupBox#sectionCard {{
            background-color: {Colors.NEUTRAL.WHITE};
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
            border-radius: 8px;
            font-weight: 700; font-size: 10px; padding-top: 14px;
        }}
        QGroupBox#sectionCard::title {{
            color: {Colors.PRIMARY.BASE};
            subcontrol-origin: margin; left: 10px; padding: 0 4px;
        }}

        QLabel#statusBadge {{
            background-color: {Colors.NEUTRAL.SLATE_100};
            color: {Colors.NEUTRAL.SLATE_500};
            border-radius: 10px; padding: 2px 8px;
            font-size: 10px; font-weight: 600;
        }}
        QLabel#statusBadge[variant="warning"] {{ background-color: #FEF3C7; color: #92400E; }}
        QLabel#statusBadge[variant="success"] {{ background-color: #DCFCE7; color: #166534; }}
        QLabel#statusBadge[variant="accent"]  {{ background-color: #EDE9FE; color: #5B21B6; }}
        QLabel#statusBadge[variant="danger"]  {{ background-color: #FEE2E2; color: #991B1B; }}
        QLabel#statusBadge[variant="info"]    {{ background-color: #ECFEFF; color: #155E75; }}

        QLabel#monoLabel {{
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 12px; font-weight: 700;
            color: {Colors.NEUTRAL.SLATE_900}; background: transparent;
        }}
        QLineEdit#monoInput {{
            font-family: 'Consolas', 'Courier New', monospace;
            background-color: {Colors.NEUTRAL.SLATE_50};
            color: {Colors.NEUTRAL.SLATE_600};
            border: 1px solid {Colors.NEUTRAL.SLATE_300};
            border-radius: 4px; padding: 4px 8px;
        }}

        QLabel#formSection {{
            font-size: 10px; font-weight: 700;
            color: {Colors.NEUTRAL.SLATE_400};
            letter-spacing: 0.5px; padding: 4px 0 2px 0;
            border-bottom: 1px solid {Colors.NEUTRAL.SLATE_200};
        }}

        QLineEdit#scanInput {{
            border: 2px solid {Colors.SUCCESS.BASE};
            border-radius: 6px; padding: 5px 10px; font-size: 12px;
            background-color: {Colors.NEUTRAL.WHITE};
            color: {Colors.NEUTRAL.SLATE_900};
        }}
        QLineEdit#scanInput:focus {{ border-color: {Colors.SUCCESS.HOVER}; }}

        QLabel#hero {{ font-size: 22px; font-weight: 800; color: {Colors.NEUTRAL.SLATE_900}; background: transparent; }}
        QLabel#hero[variant="success"] {{ color: {Colors.SUCCESS.BASE}; }}
        QLabel#hero[variant="danger"]  {{ color: {Colors.DANGER.BASE}; }}
        QLabel#hero[variant="warning"] {{ color: {Colors.WARNING.BASE}; }}
        QLabel#hero[variant="info"]    {{ color: {Colors.INFO.BASE}; }}

        QFrame#qrPreviewBox {{
            background-color: {Colors.NEUTRAL.SLATE_50};
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
            border-radius: 6px;
        }}
        QLabel#qrPreviewIcon {{ font-size: 24px; background: transparent; }}
        QLabel#qrPreviewArea {{
            background-color: {Colors.NEUTRAL.SLATE_100};
            border: 2px dashed {Colors.NEUTRAL.SLATE_300};
            border-radius: 8px;
            color: {Colors.NEUTRAL.SLATE_400}; font-size: 36px;
        }}

        QPushButton#qrTypeButton {{
            background-color: {Colors.NEUTRAL.SLATE_100};
            border: 1px solid {Colors.NEUTRAL.SLATE_300};
            border-radius: 6px;
            color: {Colors.NEUTRAL.SLATE_500};
            font-size: 10px; padding: 6px 4px; text-align: center;
        }}
        QPushButton#qrTypeButton:hover {{
            background-color: {Colors.NEUTRAL.SLATE_200};
            border-color: {Colors.PRIMARY.BASE};
            color: {Colors.NEUTRAL.SLATE_900};
        }}
        QPushButton#qrTypeButton:checked {{
            background-color: #EFF6FF;
            border: 2px solid {Colors.PRIMARY.BASE};
            color: {Colors.PRIMARY.DARK}; font-weight: 700;
        }}

        QListWidget#containerList {{
            background-color: {Colors.NEUTRAL.SLATE_50};
            border: 1px solid {Colors.NEUTRAL.SLATE_200};
            border-radius: 6px;
        }}
        QListWidget#containerList::item {{ border-radius: 4px; padding: 1px; margin: 1px 2px; }}
        QListWidget#containerList::item:hover {{ background-color: {Colors.NEUTRAL.SLATE_100}; }}
        QListWidget#containerList::item:selected {{ background-color: #EFF6FF; border: 1px solid {Colors.PRIMARY.BASE}; }}
        QWidget#containerCard {{ background-color: {Colors.NEUTRAL.WHITE}; border-radius: 6px; }}

        QFrame#infoCallout {{
            background-color: #EFF6FF;
            border-left: 3px solid {Colors.PRIMARY.BASE};
            border-radius: 4px;
        }}

        QLabel#stepNum {{
            background-color: {Colors.NEUTRAL.SLATE_200};
            color: {Colors.NEUTRAL.SLATE_400};
            border-radius: 12px; font-weight: 700; font-size: 11px;
        }}
        QLabel#stepNum[active="true"] {{ background-color: {Colors.PRIMARY.BASE}; color: {Colors.NEUTRAL.WHITE}; }}
        QLabel#stepLabel {{ color: {Colors.NEUTRAL.SLATE_400}; font-size: 11px; }}
        QLabel#stepLabel[active="true"] {{ color: {Colors.NEUTRAL.SLATE_900}; font-weight: 600; }}
        QLabel#stepArrow {{ color: {Colors.NEUTRAL.SLATE_300}; font-size: 14px; background: transparent; }}

        QLabel#qrAssignHeader, QLabel#qrRecvHeader {{
            font-size: 13px; font-weight: 700;
            color: {Colors.NEUTRAL.SLATE_900}; background: transparent;
        }}
        QFrame[frameShape="4"] {{ color: {Colors.NEUTRAL.SLATE_200}; max-height: 1px; }}
    """



# ─── Bloques modernos generados desde design_tokens (KPI cards, page header) ──
#  Estos bloques se concatenan al final de cada tema. Usan SOLO tokens —
#  ningún hex literal — para que los cambios en design_tokens.Colors
#  propaguen automáticamente a todos los componentes nuevos.

def _block_kpi_card(*, bg: str, border: str, hover_bg: str, text: str, muted: str) -> str:
    """Genera el QSS del componente KPI card (#kpiCard) para el tema dado."""
    return f"""
        /* ===== KPI CARD (modernos, ui_components.create_kpi_card) ===== */
        QFrame#kpiCard {{
            background-color: {bg};
            border: 1px solid {border};
            border-radius: 12px;
        }}
        QFrame#kpiCard:hover {{
            background-color: {hover_bg};
            border-color: {Colors.PRIMARY.BASE};
        }}
        QFrame#kpiCard QLabel {{
            background-color: transparent;
            border: none;
        }}
        QFrame#kpiCard QLabel#kpiValue {{
            color: {text};
        }}
        QFrame#kpiCard QLabel#kpiLabel {{
            color: {muted};
        }}
        QFrame#kpiAccentBar {{
            border: none;
        }}
    """


def _block_page_header(*, text: str, muted: str, border: str) -> str:
    """Genera el QSS para PageHeader (#pageHeader, #pageTitle, #pageSubtitle)."""
    return f"""
        /* ===== PAGE HEADER (modernos, ui_components.PageHeader) ===== */
        QFrame#pageHeader {{
            background-color: transparent;
            border: none;
            border-bottom: 1px solid {border};
        }}
        QLabel#pageTitle {{
            color: {text};
            font-size: 18px;
            font-weight: 700;
            background: transparent;
            border: none;
        }}
        QLabel#pageSubtitle {{
            color: {muted};
            font-size: 12px;
            background: transparent;
            border: none;
        }}
    """


def _block_typography(*, primary: str, secondary: str, muted: str) -> str:
    """
    Color theme-aware para los object names de los helpers create_heading,
    create_subheading, create_caption, create_label.

    Las propiedades font-size/font-weight las pone Python inline porque
    no varían entre temas; aquí solo controlamos COLOR.
    """
    return f"""
        /* ===== TIPOGRAFÍA SEMÁNTICA (theme-aware via objectName) ===== */
        QLabel#h1Label       {{ color: {primary}; }}
        QLabel#h2Label       {{ color: {secondary}; }}
        QLabel#bodyLabel     {{ color: {primary}; }}
        QLabel#captionLabel  {{ color: {muted}; }}
    """


def _block_empty_loading(*, surface: str, border: str, text: str, muted: str) -> str:
    """QSS para EmptyStateWidget y LoadingIndicator (theme-aware)."""
    return f"""
        /* ===== EMPTY STATE & LOADING INDICATOR ===== */
        QFrame#emptyState {{
            background-color: {surface};
            border: 1px dashed {border};
            border-radius: 8px;
        }}
        QLabel#emptyStateTitle    {{ color: {text}; }}
        QLabel#emptyStateMessage  {{ color: {muted}; }}
        QFrame#loadingIndicator {{
            background-color: {surface};
            border: 1px solid {border};
            border-radius: 8px;
        }}
        QLabel#loadingMessage     {{ color: {muted}; }}
    """


def _block_toast(*, surface: str, border: str, text: str, muted: str) -> str:
    """QSS para Toast notifications (theme-aware)."""
    return f"""
        /* ===== TOAST NOTIFICATIONS ===== */
        QFrame#toast {{
            background-color: {surface};
            border: 1px solid {border};
            border-radius: 10px;
        }}
        QLabel#toastTitle   {{ color: {text}; }}
        QLabel#toastMessage {{ color: {muted}; }}
        QPushButton#toastClose {{
            color: {muted};
            background: transparent;
            border: none;
        }}
    """


def _block_pos_module(
    *,
    bg: str, card: str, card_hover: str, card_selected: str,
    border: str, text: str, muted: str,
    success: str, success_hover: str,
    danger: str, primary: str,
    category_active_bg: str, category_active_text: str,
    cobrar_disabled_bg: str, cobrar_disabled_text: str,
    warning: str, critical: str, out_stock_bg: str,
    action: str, action_hover: str,
    success_soft: str = "#DCFCE7",
    warning_soft: str = "#FEF3C7",
    primary_soft: str = "#DBEAFE",
) -> str:
    """Genera el QSS para el módulo POS (ventas.py)."""
    return f"""
        /* ===== POS: CASHIER INFO BAR ===== */
        QFrame#posCashierBar {{
            background-color: {card};
            border-bottom: 1px solid {border};
            padding: 4px 12px;
        }}
        QLabel#posCashierTitle {{
            color: {text};
            font-size: 15px;
            font-weight: 700;
            background: transparent;
            border: none;
        }}
        QLabel#posCashierMeta {{
            color: {muted};
            font-size: 11px;
            background: transparent;
            border: none;
        }}
        QLabel#posStatusBadge {{
            color: {success};
            background-color: transparent;
            border: 1px solid {success};
            border-radius: 9px;
            padding: 2px 8px;
            font-size: 10px;
            font-weight: 700;
        }}
        QPushButton#posHWBtn {{
            background: transparent;
            color: {muted};
            border: 1px solid {border};
            border-radius: 5px;
            padding: 3px 8px;
            font-size: 10px;
            font-weight: 600;
        }}
        QPushButton#posHWBtn:hover {{
            color: {text};
            border-color: {primary};
        }}
        QPushButton#posHWBtnActive {{
            background: transparent;
            color: {success};
            border: 1px solid {success};
            border-radius: 5px;
            padding: 3px 8px;
            font-size: 10px;
            font-weight: 700;
        }}
        QPushButton#posCorteBtn {{
            background: transparent;
            color: {danger};
            border: 1px solid {danger};
            border-radius: 5px;
            padding: 3px 8px;
            font-size: 10px;
            font-weight: 700;
        }}
        QPushButton#posCorteBtn:hover {{
            background-color: {danger};
            color: white;
        }}

        /* ===== POS: CATEGORY TAB BAR ===== */
        QScrollArea#posCategoryScroll {{
            border: none;
            background: transparent;
            max-height: 40px;
        }}
        QScrollArea#posCategoryScroll QWidget {{
            background: transparent;
        }}
        QScrollArea#posCategoryScroll QScrollBar:horizontal {{
            height: 0px;
        }}
        QPushButton#posCategoryBtn {{
            background: transparent;
            color: {muted};
            border: none;
            border-radius: 6px;
            padding: 5px 12px;
            font-size: 11px;
            font-weight: 600;
            min-height: 28px;
        }}
        QPushButton#posCategoryBtn:hover {{
            color: {text};
            background-color: {card_hover};
        }}
        QPushButton#posCategoryBtn[active="true"] {{
            color: {category_active_text};
            background-color: {category_active_bg};
            font-weight: 700;
        }}

        /* ===== POS: PRODUCT CARDS ===== */
        QFrame[class="product-card"] {{
            background-color: {card};
            border: 1px solid {border};
            border-radius: 10px;
        }}
        QFrame[class="product-card-hover"] {{
            background-color: {card_hover};
            border: 1px solid {primary};
            border-radius: 10px;
        }}
        QFrame[class="product-card-selected"] {{
            background-color: {card_selected};
            border: 2px solid {primary};
            border-radius: 10px;
        }}
        QLabel[class="product-name"] {{
            font-weight: 600;
            font-size: 11px;
            color: {text};
            background: transparent;
            border: none;
        }}
        QLabel[class="product-price"] {{
            color: {success};
            font-size: 11px;
            font-weight: 700;
            background: transparent;
            border: none;
        }}
        QLabel[class="product-stock"] {{
            color: {muted};
            font-size: 10px;
            background: transparent;
            border: none;
        }}
        QLabel[class="product-image-placeholder"] {{
            color: {muted};
            background: transparent;
            border: none;
            font-size: 20px;
        }}

        /* ===== POS: PRODUCT CARD — STOCK STATES ===== */
        QFrame[class="product-card-low-stock"] {{
            background-color: {card};
            border: 1.5px solid {warning};
            border-radius: 10px;
        }}
        QFrame[class="product-card-critical-stock"] {{
            background-color: {card};
            border: 2px solid {critical};
            border-radius: 10px;
        }}
        QFrame[class="product-card-out-of-stock"] {{
            background-color: {out_stock_bg};
            border: 1px solid {critical};
            border-radius: 10px;
        }}
        QLabel[class="product-stock-low"] {{
            color: {warning};
            font-size: 10px;
            font-weight: 600;
            background: transparent;
            border: none;
        }}
        QLabel[class="product-stock-critical"] {{
            color: {critical};
            font-size: 10px;
            font-weight: 700;
            background: transparent;
            border: none;
        }}
        QLabel[class="product-stock-out"] {{
            color: {critical};
            font-size: 10px;
            font-weight: 700;
            background: transparent;
            border: none;
        }}
        QLabel[class="product-name-dimmed"] {{
            font-weight: 600;
            font-size: 11px;
            color: {muted};
            background: transparent;
            border: none;
        }}
        QLabel#posOutOfStockBadge {{
            background-color: {critical};
            color: white;
            border-radius: 6px;
            padding: 1px 5px;
            font-size: 9px;
            font-weight: 700;
        }}
        QLabel#posLowStockBadge {{
            background-color: {warning};
            color: white;
            border-radius: 6px;
            padding: 1px 5px;
            font-size: 9px;
            font-weight: 700;
        }}

        QLabel#posProductCheckBadge {{
            background-color: {primary};
            color: white;
            border-radius: 9px;
            font-size: 11px;
            font-weight: 700;
        }}

        /* ===== POS: SECTION HEADERS ===== */
        QLabel#posSectionHeader {{
            color: {muted};
            font-size: 10px;
            font-weight: 700;
            background: transparent;
            border: none;
            padding: 0px;
        }}

        /* ===== POS: STANDARD ACTION BUTTON (#00755E) ===== */
        QPushButton#posActionBtn {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {action_hover}, stop:1 {action});
            color: white;
            border: none;
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }}
        QPushButton#posActionBtn:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #00C49A, stop:1 {action_hover});
        }}
        QPushButton#posActionBtn:pressed {{
            background-color: {action};
        }}
        QPushButton#posActionBtn:disabled {{
            background-color: {cobrar_disabled_bg};
            color: {cobrar_disabled_text};
        }}

        /* ===== POS: UTILITY ACTION BUTTON (outline teal) ===== */
        QPushButton#posUtilBtn {{
            background: transparent;
            color: {action};
            border: 1px solid {action};
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }}
        QPushButton#posUtilBtn:hover {{
            background-color: {action};
            color: white;
        }}
        QPushButton#posUtilBtn:pressed {{
            background-color: {action_hover};
            color: white;
        }}
        QPushButton#posUtilBtn:disabled {{
            color: {muted};
            border-color: {border};
        }}

        /* ===== POS: COMPACT FLAT BARS (replaces QGroupBox for utility rows) ===== */
        QFrame#posCompactBar {{
            background-color: {card};
            border: 1px solid {border};
            border-radius: 5px;
            min-height: 34px;
            max-height: 38px;
        }}
        QLabel#posBarLabel {{
            color: {muted};
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 0.3px;
            background: transparent;
            border: none;
            padding-right: 2px;
        }}

        /* ===== POS: COMPACT SECTION GROUP BOXES ===== */
        QGroupBox[class="venta-group"],
        QGroupBox[class="client-group"],
        QGroupBox[class="discount-group"] {{
            margin-top: 13px;
            padding-top: 3px;
            border-radius: 5px;
        }}
        QGroupBox[class="venta-group"]::title,
        QGroupBox[class="client-group"]::title,
        QGroupBox[class="discount-group"]::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 6px;
            padding: 0 3px;
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 0.4px;
        }}
        /* Cart QGroupBox — borderless, no title (header shown as separate frame) */
        QGroupBox#posCartGroup {{
            border: none;
            margin-top: 0px;
            padding-top: 0px;
            background-color: {bg};
        }}
        QGroupBox#posCartGroup::title {{
            width: 0px; height: 0px;
        }}

        /* ===== POS: CART TABLE 2-LINE CELLS ===== */
        QLabel#posCartItemName {{
            color: {text};
            font-size: 12px;
            font-weight: 600;
            background: transparent;
            border: none;
        }}
        QLabel#posCartItemCode {{
            color: {muted};
            font-size: 10px;
            font-weight: 400;
            background: transparent;
            border: none;
        }}

        /* ===== POS: CLIENT SECTION ===== */
        QLabel#posClientSectionLabel {{
            color: {muted};
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.4px;
            background: transparent;
            border: none;
        }}
        QLabel#posClientName {{
            color: {text};
            font-size: 13px;
            font-weight: 700;
            background: transparent;
            border: none;
        }}

        /* ===== POS: TOTALS — PUNTOS A GANAR MINI CARD ===== */
        QFrame#posPtsGainCard {{
            background-color: {success_soft};
            border: 1px solid {success};
            border-radius: 6px;
        }}
        QLabel#posPtsGainTitle {{
            color: {success};
            font-size: 9px;
            font-weight: 600;
            background: transparent;
            border: none;
        }}
        QLabel#posPtsGainValue {{
            color: {success};
            font-size: 12px;
            font-weight: 800;
            background: transparent;
            border: none;
        }}

        /* ===== POS: DISCOUNT BUTTONS BAR ===== */
        QFrame#posDiscountBar {{
            background-color: {card};
            border-top: 1px solid {border};
            border-bottom: 1px solid {border};
        }}
        QPushButton#posDiscountBtn {{
            background-color: transparent;
            border: 1px solid {border};
            border-radius: 5px;
            color: {text};
            font-size: 12px;
            font-weight: 600;
            min-height: 30px;
        }}
        QPushButton#posDiscountBtn:hover {{
            background-color: {warning_soft};
            border-color: {warning};
            color: {warning};
        }}
        QPushButton#posDiscountCustomBtn {{
            background-color: {primary_soft};
            border: 1px solid {primary};
            border-radius: 5px;
            color: {primary};
            font-size: 11px;
            font-weight: 600;
            min-height: 30px;
        }}
        QPushButton#posDiscountCustomBtn:hover {{
            background-color: {primary};
            color: #FFFFFF;
        }}

        /* ===== POS: CART DELETE BUTTON ===== */
        QPushButton#cartDeleteBtn {{
            background-color: transparent;
            border: none;
            color: {muted};
            font-size: 16px;
            font-weight: 700;
            border-radius: 4px;
        }}
        QPushButton#cartDeleteBtn:hover {{
            background-color: #FEE2E2;
            color: #EF4444;
        }}

        /* ===== POS: CART TABLE ===== */
        QTableWidget[class="tabla-carrito"] {{
            border: none;
            background-color: transparent;
            gridline-color: {border};
            selection-background-color: {primary};
            selection-color: white;
            font-size: 11px;
        }}
        QTableWidget[class="tabla-carrito"] QHeaderView::section {{
            background-color: {card};
            color: {muted};
            border: none;
            border-bottom: 1px solid {border};
            padding: 3px 4px;
            font-size: 10px;
            font-weight: 600;
        }}
        QTableWidget[class="tabla-carrito"]::item {{
            padding: 2px 4px;
            border-bottom: 1px solid {border};
        }}
        QTableWidget[class="tabla-carrito"]::item:selected {{
            background-color: {primary};
            color: white;
        }}

        /* ===== POS: CART ROW ACTION BUTTONS ===== */
        /* Compact variants of editBtn/deleteBtn — inherit semantic colors, override padding */
        QPushButton#cartEditBtn {{
            background: {primary};
            color: white;
            border: none;
            border-radius: 4px;
            padding: 0px;
            font-size: 12px;
        }}
        QPushButton#cartDeleteBtn {{
            background: {danger};
            color: white;
            border: none;
            border-radius: 4px;
            padding: 0px;
            font-size: 12px;
        }}

        /* ===== POS: TOTALS BREAKDOWN CARD ===== */
        QFrame#posTotalsCard {{
            background-color: {card};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 2px;
        }}
        QLabel#posTotalsRowLabel {{
            color: {muted};
            font-size: 11px;
            background: transparent;
            border: none;
        }}
        QLabel#posTotalsRowValue {{
            color: {text};
            font-size: 11px;
            font-weight: 600;
            background: transparent;
            border: none;
        }}
        QLabel#posDiscountLabel {{
            color: {danger};
            font-size: 11px;
            background: transparent;
            border: none;
        }}
        QLabel#posDiscountValue {{
            color: {danger};
            font-size: 11px;
            font-weight: 600;
            background: transparent;
            border: none;
        }}
        QFrame#posTotalsDivider {{
            background-color: {border};
            max-height: 1px;
            border: none;
        }}
        QLabel#posGrandTotalLabel {{
            color: {text};
            font-size: 14px;
            font-weight: 700;
            background: transparent;
            border: none;
        }}
        QLabel#posGrandTotalValue {{
            color: {success};
            font-size: 20px;
            font-weight: 800;
            background: transparent;
            border: none;
        }}
        QLabel#posFinancialMetric {{
            color: {muted};
            font-size: 12px;
            font-weight: 600;
            background: transparent;
            border: none;
            padding: 1px 0px;
        }}
        QLabel#posCommissionBadge {{
            color: {success};
            background: transparent;
            border: 1px solid {success};
            border-radius: 6px;
            padding: 1px 6px;
            font-size: 10px;
            font-weight: 600;
        }}

        /* ===== POS: INDICATOR CARDS ===== */
        QFrame#posIndicatorCard {{
            background: {card};
            border: 1px solid {border};
            border-radius: 6px;
            min-height: 42px;
        }}
        QLabel#posIndicatorTitle {{
            color: {muted};
            font-size: 9px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.3px;
            background: transparent;
            border: none;
            padding: 0px;
        }}
        QLabel#posIndicatorValue {{
            color: {text};
            font-size: 12px;
            font-weight: 700;
            background: transparent;
            border: none;
            padding: 0px;
        }}

        /* ===== POS: COBRAR BUTTON ===== */
        QPushButton#btnCobrarPOS {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {success_hover}, stop:1 {success});
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 15px;
            font-weight: 800;
            min-height: 44px;
            letter-spacing: 0.3px;
        }}
        QPushButton#btnCobrarPOS:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #4ADE80, stop:1 {success_hover});
        }}
        QPushButton#btnCobrarPOS:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {success}, stop:1 {Colors.SUCCESS.ACTIVE});
        }}
        QPushButton#btnCobrarPOS:disabled {{
            background-color: {cobrar_disabled_bg};
            color: {cobrar_disabled_text};
        }}

        /* ===== POS: PAYMENT DIALOG ===== */
        QFrame#paymentHeader {{
            background-color: {card};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 4px;
        }}
        QLabel#paymentCaption {{
            color: {muted};
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.5px;
            background: transparent;
            border: none;
        }}
        QLabel#paymentTotalAmount {{
            color: {success};
            font-size: 28px;
            font-weight: 800;
            background: transparent;
            border: none;
            letter-spacing: -0.5px;
        }}
        QComboBox#paymentCombo {{
            background-color: {card};
            color: {text};
            border: 1px solid {border};
            border-radius: 5px;
            padding: 4px 8px;
            font-size: 12px;
            min-height: 32px;
        }}
        QComboBox#paymentCombo::drop-down {{
            border: none;
        }}
        QComboBox#paymentCombo:focus {{
            border-color: {primary};
        }}
        QDoubleSpinBox#paymentSpinbox {{
            background-color: {card};
            color: {text};
            border: 1px solid {border};
            border-radius: 5px;
            padding: 4px 8px;
            font-size: 15px;
            font-weight: 700;
            min-height: 36px;
        }}
        QDoubleSpinBox#paymentSpinbox:focus {{
            border-color: {primary};
            border-width: 2px;
        }}
        QLabel#paymentChange {{
            color: {success};
            font-size: 13px;
            font-weight: 700;
            background: transparent;
            border: none;
        }}
        QPushButton#paymentCancelBtn {{
            background: transparent;
            color: {muted};
            border: 1px solid {border};
            border-radius: 6px;
            padding: 6px 14px;
            font-size: 12px;
            font-weight: 600;
            min-height: 36px;
        }}
        QPushButton#paymentCancelBtn:hover {{
            border-color: {danger};
            color: {danger};
        }}
        QPushButton#paymentConfirmBtn {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {success_hover}, stop:1 {success});
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 800;
            min-height: 40px;
            letter-spacing: 0.2px;
        }}
        QPushButton#paymentConfirmBtn:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #4ADE80, stop:1 {success_hover});
        }}
        QPushButton#paymentConfirmBtn:disabled {{
            background-color: {cobrar_disabled_bg};
            color: {cobrar_disabled_text};
        }}

        /* ===== POS: SCANNER INPUT STATES ===== */
        QLineEdit[class="input-scanner-success"] {{
            border: 2px solid {success};
            background-color: {success_soft};
        }}
        QLineEdit[class="input-scanner-primary"] {{
            border: 2px solid {primary};
            background-color: {primary_soft};
        }}
        QLineEdit[class="input-scanner-base"] {{
            border: 1px solid {border};
        }}

        /* ===== POS: SCANNER STATE BADGE ===== */
        QLabel#posScanStateActive {{
            color: {success};
            font-size: 9px;
            font-weight: 700;
            padding: 2px 7px;
            border: 1px solid {success};
            border-radius: 8px;
            background: {success_soft};
            letter-spacing: 0.3px;
        }}
        QLabel#posScanStatePrimary {{
            color: {primary};
            font-size: 9px;
            font-weight: 700;
            padding: 2px 7px;
            border: 1px solid {primary};
            border-radius: 8px;
            background: {primary_soft};
            letter-spacing: 0.3px;
        }}
        QLabel#posScanStateWaiting {{
            color: {muted};
            font-size: 9px;
            font-weight: 600;
            padding: 2px 7px;
            border: 1px solid {border};
            border-radius: 8px;
            background: transparent;
            letter-spacing: 0.3px;
        }}

        /* ===== POS: SCANNER NOTIFICATION LABEL ===== */
        QLabel#posScannerNotif {{
            padding: 2px 10px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            background: transparent;
            border: none;
        }}
        QLabel[class="badge-scanner-success badge"] {{
            background-color: {success_soft};
            color: {success};
            border: 1px solid {success};
            border-radius: 4px;
            padding: 2px 10px;
            font-size: 11px;
            font-weight: 600;
        }}
        QLabel[class="badge-scanner-warning badge"] {{
            background-color: {warning_soft};
            color: {warning};
            border: 1px solid {warning};
            border-radius: 4px;
            padding: 2px 10px;
            font-size: 11px;
            font-weight: 600;
        }}
        QLabel[class="badge-scanner-info badge"] {{
            background-color: {primary_soft};
            color: {primary};
            border: 1px solid {primary};
            border-radius: 4px;
            padding: 2px 10px;
            font-size: 11px;
            font-weight: 600;
        }}
        QLabel[class="badge-scanner-secondary badge"] {{
            background-color: {card};
            color: {muted};
            border: 1px solid {border};
            border-radius: 4px;
            padding: 2px 10px;
            font-size: 11px;
            font-weight: 600;
        }}

        /* ===== POS: LOYALTY TIER BADGE ===== */
        QLabel#posLoyaltyTierBadge {{
            font-size: 9px;
            font-weight: 700;
            padding: 2px 7px;
            border-radius: 8px;
            border: 1px solid {muted};
            background: transparent;
            color: {muted};
            letter-spacing: 0.3px;
        }}
        QLabel#posLoyaltyTierBadge[tier="Bronce"] {{
            color: #CD7F32;
            border-color: #CD7F32;
        }}
        QLabel#posLoyaltyTierBadge[tier="Plata"] {{
            color: #9CA3AF;
            border-color: #9CA3AF;
        }}
        QLabel#posLoyaltyTierBadge[tier="Oro"] {{
            color: #D97706;
            border-color: #D97706;
        }}
        QLabel#posLoyaltyTierBadge[tier="Platino"] {{
            color: {primary};
            border-color: {primary};
        }}

        /* ===== POS: CART EMPTY STATE ===== */
        QLabel#posCartEmpty {{
            color: {muted};
            font-size: 12px;
            font-weight: 400;
            line-height: 1.6;
            background: transparent;
            border: 2px dashed {border};
            border-radius: 8px;
            padding: 24px 16px;
        }}

        /* ===== POS: AUTH DISCOUNT DIALOG ===== */
        QFrame#authDialogHeader {{
            background-color: {warning_soft};
            border: 1px solid {warning};
            border-radius: 6px;
        }}
        QLabel#authDialogIcon {{
            font-size: 18px;
            background: transparent;
            border: none;
        }}
        QLabel#authDialogTitle {{
            color: {warning};
            font-size: 13px;
            font-weight: 700;
            background: transparent;
            border: none;
        }}
        QLabel#authDialogDetail {{
            color: {text};
            font-size: 11px;
            background: transparent;
            border: none;
        }}
        QLineEdit#authDialogInput {{
            background-color: {card};
            color: {text};
            border: 1px solid {border};
            border-radius: 5px;
            padding: 5px 8px;
            font-size: 12px;
            min-height: 32px;
        }}
        QLineEdit#authDialogInput:focus {{
            border-color: {primary};
            border-width: 2px;
        }}

        /* ===== POS: PAGE HEADER (PUNTO DE VENTA) ===== */
        QFrame#posPageHeader {{
            background-color: {card};
            border: none;
            border-bottom: 1px solid {border};
        }}
        QLabel#posPageTitle {{
            color: {text};
            font-size: 16px;
            font-weight: 700;
            letter-spacing: 0.5px;
            background: transparent;
            border: none;
        }}
        QLabel#posPageSubtitle {{
            color: {muted};
            font-size: 11px;
            font-weight: 400;
            background: transparent;
            border: none;
        }}

        /* ===== POS: SEARCH BAR ===== */
        QFrame#posSearchFrame {{
            background-color: {card};
            border: 2px solid {border};
            border-radius: 8px;
        }}
        QFrame#posSearchFrame:hover {{
            border-color: {primary};
        }}
        QFrame#posSearchFrame[focused="true"] {{
            border-color: {primary};
        }}
        QPushButton#posBarcodeBtn {{
            background: transparent;
            border: none;
            color: {muted};
            font-size: 18px;
            font-weight: 700;
            border-radius: 4px;
            padding: 0px;
        }}
        QPushButton#posBarcodeBtn:hover {{
            background-color: {primary_soft};
            color: {primary};
        }}
        QLineEdit#posSearchInput {{
            background-color: transparent;
            border: none;
            color: {text};
            font-size: 13px;
            padding: 4px 2px;
        }}
        QLineEdit#posSearchInput:focus {{
            border: none;
            outline: none;
        }}

        /* ===== POS: CATEGORY ROW ===== */
        QFrame#posCategoryRow {{
            background-color: {card};
            border: none;
            border-bottom: 1px solid {border};
        }}
        QPushButton#posViewIconBtn {{
            background-color: transparent;
            border: 1px solid {border};
            border-radius: 4px;
            color: {muted};
            font-size: 14px;
        }}
        QPushButton#posViewIconBtn:checked {{
            background-color: {card};
            border-color: {primary};
            color: {primary};
        }}
        QPushButton#posViewIconBtn:hover {{
            background-color: {primary_soft};
            border-color: {primary};
            color: {primary};
        }}
        QPushButton#posViewIconBtn:disabled {{
            color: {border};
            border-color: {border};
        }}

        /* ===== POS: CART HEADER ===== */
        QFrame#posCartHeader {{
            background-color: {card};
            border: none;
            border-bottom: 1px solid {border};
        }}
        QLabel#posCartHeaderTitle {{
            color: {text};
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.5px;
            background: transparent;
            border: none;
        }}
        QPushButton#posCartIconBtn {{
            background: transparent;
            border: none;
            color: {muted};
            font-size: 15px;
            border-radius: 4px;
            padding: 0px;
        }}
        QPushButton#posCartIconBtn:hover {{
            background-color: {primary_soft};
            color: {primary};
        }}

        /* ===== POS: CLIENT SECTION ===== */
        QGroupBox#posClientFrame {{
            background-color: {card};
            border: 1px solid {border};
            border-radius: 6px;
            margin-top: 0px;
            padding: 6px 8px;
        }}
        QGroupBox#posClientFrame::title {{
            width: 0px;
            height: 0px;
        }}
        QFrame#posClientDisplayRow {{
            background: transparent;
            border: none;
        }}
        QFrame#posClientSearchRow {{
            background: transparent;
            border: none;
        }}
        QPushButton#posClientChangeBtn {{
            background-color: transparent;
            border: 1px solid {border};
            border-radius: 4px;
            color: {primary};
            font-size: 11px;
            font-weight: 600;
            padding: 2px 8px;
        }}
        QPushButton#posClientChangeBtn:hover {{
            background-color: {primary_soft};
            border-color: {primary};
        }}
        QLabel#posClientIcon {{
            color: {muted};
            font-size: 13px;
            background: transparent;
            border: none;
            padding: 0px;
        }}
        QPushButton#cartEditBtn {{
            background-color: transparent;
            border: none;
            color: {primary};
            font-size: 14px;
            border-radius: 4px;
            padding: 0px;
        }}
        QPushButton#cartEditBtn:hover {{
            background-color: {primary_soft};
            color: {primary};
        }}

        /* ===== POS: COBRAR FRAME ===== */
        QFrame#posCobrarFrame {{
            background-color: {card};
            border: 1px solid {border};
            border-radius: 8px;
        }}
        QFrame#posCobrarBtnWrap {{
            background: transparent;
            border: none;
        }}
        QLabel#posFKeyBadge {{
            background-color: {success};
            color: #FFFFFF;
            font-size: 10px;
            font-weight: 800;
            border-radius: 3px;
            letter-spacing: 0.3px;
        }}
        QFrame#posFKeyBtnWrap {{
            background: transparent;
            border: none;
        }}
        QLabel#posFKeySubLabel {{
            color: {muted};
            font-size: 9px;
            font-weight: 600;
            letter-spacing: 0.3px;
            background: transparent;
            border: none;
        }}

        /* ===== POS: UTILITY BAR ===== */
        QFrame#posUtilBar {{
            background-color: {card};
            border: 1px solid {border};
            border-radius: 6px;
        }}
    """


def _block_stats_bar(
    *, bg: str, border: str, muted: str,
    primary: str, success: str, warning: str, info: str,
) -> str:
    """QSS para la barra de KPIs del módulo de Compras — completamente theme-aware."""
    return f"""
        /* ===== COMPRAS: STATS BAR ===== */
        QFrame#statsBarCmp {{
            background-color: {bg};
            border: 1px solid {border};
            border-radius: 8px;
        }}
        QFrame#statsBarSeparator {{
            background-color: {border};
            border: none;
        }}
        QLabel#statsKpiCaption {{
            color: {muted};
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 0.5px;
            background: transparent;
            border: none;
        }}
        QLabel#statsKpiValue {{
            font-size: 18px;
            font-weight: 700;
            background: transparent;
            border: none;
        }}
        QLabel#statsKpiValue[variant="primary"] {{ color: {primary}; }}
        QLabel#statsKpiValue[variant="success"] {{ color: {success}; }}
        QLabel#statsKpiValue[variant="warning"] {{ color: {warning}; }}
        QLabel#statsKpiValue[variant="info"]    {{ color: {info};    }}
    """


def _block_dash_cards(*, bg: str, border: str, hover_bg: str, text: str, muted: str) -> str:
    """QSS para las tarjetas enterprise del dashboard (v13.5)."""
    return f"""
        /* ===== DASHBOARD ENTERPRISE CARDS (v13.5) ===== */
        QFrame#dashChartCard, QFrame#dashActCard, QFrame#dashWACard,
        QFrame#dashQACard, QFrame#dashAlertCard, QFrame#dashDelivCard {{
            background-color: {bg};
            border: 1px solid {border};
            border-radius: 12px;
        }}
        QFrame#dashChartCard QLabel, QFrame#dashActCard QLabel,
        QFrame#dashWACard QLabel, QFrame#dashQACard QLabel,
        QFrame#dashAlertCard QLabel, QFrame#dashDelivCard QLabel {{
            background-color: transparent;
            border: none;
            color: {text};
        }}
        QPushButton#quickActionBtn {{
            background-color: {bg};
            border: 1px solid {border};
            border-radius: 8px;
            color: {text};
            font-size: 11px;
            font-weight: 600;
            padding: 8px 6px;
            text-align: center;
        }}
        QFrame#pedidoWAItem {{
            background-color: {bg};
            border: 1px solid {border};
            border-radius: 8px;
        }}
        QFrame#pedidoWAItem:hover {{
            border-color: {Colors.PRIMARY.BASE};
            background-color: {hover_bg};
        }}
        QFrame#pedidoWAItem QLabel {{
            background-color: transparent;
            border: none;
            color: {text};
        }}
        QFrame#driverCard QLabel, QFrame#actFeedItem QLabel {{
            background-color: transparent;
            border: none;
        }}
        QLabel#dashboardTime {{
            color: {muted};
        }}
    """


def _modern_blocks(theme: str) -> str:
    """Concatena todos los bloques modernos para el tema dado."""
    if theme == "Oscuro":
        return (
            _block_stats_bar(
                bg=Colors.NEUTRAL.SLATE_800,
                border=Colors.NEUTRAL.SLATE_700,
                muted=Colors.NEUTRAL.SLATE_400,
                primary=Colors.PRIMARY_BASE,
                success=Colors.SUCCESS_BASE,
                warning=Colors.WARNING_BASE,
                info=Colors.INFO_BASE,
            )
            + _block_dash_cards(
                bg=Colors.NEUTRAL.SLATE_800,
                border=Colors.NEUTRAL.SLATE_700,
                hover_bg=Colors.NEUTRAL.SLATE_700,
                text=Colors.NEUTRAL.SLATE_50,
                muted=Colors.NEUTRAL.SLATE_400,
            )
            + _block_kpi_card(
                bg=Colors.NEUTRAL.SLATE_800,
                border=Colors.NEUTRAL.SLATE_700,
                hover_bg=Colors.NEUTRAL.SLATE_700,
                text=Colors.NEUTRAL.SLATE_50,
                muted=Colors.NEUTRAL.SLATE_400,
            )
            + _block_page_header(
                text=Colors.NEUTRAL.SLATE_50,
                muted=Colors.NEUTRAL.SLATE_400,
                border=Colors.NEUTRAL.SLATE_700,
            )
            + _block_typography(
                primary=Colors.NEUTRAL.SLATE_50,
                secondary=Colors.NEUTRAL.SLATE_300,
                muted=Colors.NEUTRAL.SLATE_400,
            )
            + _block_empty_loading(
                surface=Colors.NEUTRAL.SLATE_800,
                border=Colors.NEUTRAL.SLATE_700,
                text=Colors.NEUTRAL.SLATE_50,
                muted=Colors.NEUTRAL.SLATE_400,
            )
            + _block_toast(
                surface=Colors.NEUTRAL.SLATE_800,
                border=Colors.NEUTRAL.SLATE_700,
                text=Colors.NEUTRAL.SLATE_50,
                muted=Colors.NEUTRAL.SLATE_400,
            )
            + _block_pos_module(
                bg=Colors.NEUTRAL.SLATE_900,
                card=Colors.NEUTRAL.SLATE_800,
                card_hover=Colors.NEUTRAL.SLATE_700,
                card_selected=Colors.NEUTRAL.DARK_CARD,
                border=Colors.NEUTRAL.SLATE_700,
                text=Colors.NEUTRAL.SLATE_50,
                muted=Colors.NEUTRAL.SLATE_400,
                success=Colors.SUCCESS.BASE,
                success_hover=Colors.SUCCESS.HOVER,
                danger=Colors.DANGER.BASE,
                primary=Colors.PRIMARY.BASE,
                category_active_bg=Colors.NEUTRAL.SLATE_700,
                category_active_text=Colors.NEUTRAL.WHITE,
                cobrar_disabled_bg=Colors.NEUTRAL.SLATE_700,
                cobrar_disabled_text=Colors.NEUTRAL.SLATE_500,
                warning=Colors.WARNING.BASE,
                critical=Colors.DANGER.BASE,
                out_stock_bg=Colors.NEUTRAL.SLATE_900,
                action=Colors.POS_ACTION_BASE,
                action_hover=Colors.POS_ACTION_HOVER,
                success_soft="#16A34A22",
                warning_soft="#D9770622",
                primary_soft="#2563EB22",
            )
        )
    # Claro
    return (
        _block_stats_bar(
            bg=Colors.NEUTRAL.SLATE_100,
            border=Colors.NEUTRAL.SLATE_200,
            muted=Colors.NEUTRAL.SLATE_500,
            primary=Colors.PRIMARY_BASE,
            success=Colors.SUCCESS_BASE,
            warning=Colors.WARNING_BASE,
            info=Colors.INFO_BASE,
        )
        + _block_dash_cards(
            bg=Colors.NEUTRAL.WHITE,
            border=Colors.NEUTRAL.SLATE_200,
            hover_bg=Colors.NEUTRAL.SLATE_50,
            text=Colors.NEUTRAL.SLATE_900,
            muted=Colors.NEUTRAL.SLATE_500,
        )
        + _block_kpi_card(
            bg=Colors.NEUTRAL.WHITE,
            border=Colors.NEUTRAL.SLATE_200,
            hover_bg=Colors.NEUTRAL.SLATE_50,
            text=Colors.NEUTRAL.SLATE_900,
            muted=Colors.NEUTRAL.SLATE_500,
        )
        + _block_page_header(
            text=Colors.NEUTRAL.SLATE_900,
            muted=Colors.NEUTRAL.SLATE_500,
            border=Colors.NEUTRAL.SLATE_200,
        )
        + _block_typography(
            primary=Colors.NEUTRAL.SLATE_900,
            secondary=Colors.NEUTRAL.SLATE_700,
            muted=Colors.NEUTRAL.SLATE_500,
        )
        + _block_empty_loading(
            surface=Colors.NEUTRAL.WHITE,
            border=Colors.NEUTRAL.SLATE_200,
            text=Colors.NEUTRAL.SLATE_900,
            muted=Colors.NEUTRAL.SLATE_500,
        )
        + _block_toast(
            surface=Colors.NEUTRAL.WHITE,
            border=Colors.NEUTRAL.SLATE_200,
            text=Colors.NEUTRAL.SLATE_900,
            muted=Colors.NEUTRAL.SLATE_500,
        )
        + _block_pos_module(
            bg=Colors.NEUTRAL.SLATE_50,
            card=Colors.NEUTRAL.WHITE,
            card_hover=Colors.NEUTRAL.SLATE_50,
            card_selected=Colors.PRIMARY.LIGHT,
            border=Colors.NEUTRAL.SLATE_200,
            text=Colors.NEUTRAL.SLATE_900,
            muted=Colors.NEUTRAL.SLATE_500,
            success=Colors.SUCCESS.BASE,
            success_hover=Colors.SUCCESS.HOVER,
            danger=Colors.DANGER.BASE,
            primary=Colors.PRIMARY.BASE,
            category_active_bg=Colors.PRIMARY.LIGHT,
            category_active_text=Colors.PRIMARY.DARK,
            cobrar_disabled_bg=Colors.NEUTRAL.SLATE_200,
            cobrar_disabled_text=Colors.NEUTRAL.SLATE_400,
            warning=Colors.WARNING.BASE,
            critical=Colors.DANGER.BASE,
            out_stock_bg=Colors.NEUTRAL.SLATE_100,
            action=Colors.POS_ACTION_BASE,
            action_hover=Colors.POS_ACTION_HOVER,
        )
    )


def build_themes() -> dict[str, str]:
    """Retorna {"Oscuro": qss_oscuro, "Claro": qss_claro}."""
    return {
        "Oscuro": _TPL_OSCURO + _modern_blocks("Oscuro"),
        "Claro":  _TPL_CLARO  + _modern_blocks("Claro"),
    }


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
