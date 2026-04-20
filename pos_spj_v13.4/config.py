
# config.py
import os
import sqlite3

# --- Rutas ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICONS_DIR = os.path.join(BASE_DIR, "recursos", "icons")
DATABASE_NAME = "punto_venta.db"

# ═══════════════════════════════════════════════════════════════════════════════
#  SISTEMA DE DISEÑO SPJ POS v13.4 — Modern SaaS UI (Stripe/Notion/Linear style)
# ═══════════════════════════════════════════════════════════════════════════════
#
#  COLORES PRINCIPALES:
#  • Primario: #2563EB (azul) → Hover: #E600E6 (magenta) → Active: #CC00CC
#  • Éxito: #16A34A (verde)
#  • Error: #DC2626 (rojo)
#  • Advertencia: #D97706 (ámbar)
#  • Acento: #7C3AED (violeta)
#
#  HOVER EFFECTS:
#  • Usar variantes de #FF00FF para interacción (hover, focus, glow)
#  • Solo en elementos interactivos, nunca como fondo principal
#
#  SIDEBAR (SIEMPRE OSCURO):
#  • Fondo: #020617 | Hover: #1E293B | Activo: #2563EB
#
# ═══════════════════════════════════════════════════════════════════════════════

TEMAS = {
    "Oscuro": """
        /* ═══════════════════════════════════════════════════════════════════
           TEMA OSCURO — SPJ POS v13.4 OPTIMIZED
           Paleta: Slate/Zinc modern dark theme con acentos magenta hover
           BOTONES REDUCIDOS: 36px height, padding 6px 12px
           ═══════════════════════════════════════════════════════════════════ */

        /* ===== VARIABLES GLOBALES ===== */
        QMainWindow, QWidget {
            background-color: #0F172A;
            color: #F1F5F9;
            font-family: 'Segoe UI', 'Inter', 'Roboto', sans-serif;
            font-size: 11px;
        }
        
        QDialog#loginDialog {
            background-color: #1E293B;
            color: #F1F5F9;
            border-radius: 12px;
        }

        QLabel#loginLogo {
            padding: 4px;
            background-color: transparent;
        }

        QLabel#loginTitle {
            font-size: 16px;
            font-weight: 700;
            color: #F1F5F9;
            margin-bottom: 5px;
        }

        QLabel#loginSucursal {
            font-size: 11px;
            color: #94A3B8;
        }

        QLabel#errorMsg {
            color: #DC2626;
            font-weight: bold;
            padding: 5px;
            background-color: #FEE2E2;
            border-radius: 6px;
        }

        QLineEdit#inputField {
            padding: 5px 8px;
            border: 1px solid #334155;
            border-radius: 8px;
            background-color: #1E293B;
            color: #F1F5F9;
            font-size: 12px;
            min-height: 28px;
        }

        QLineEdit#inputField:focus {
            border: 2px solid #2563EB;
            background-color: #1E3A5F;
        }

        QLineEdit#inputField::placeholder {
            color: #64748B;
        }

        /* ===== TOOLTIPS GLOBALES ===== */
        QToolTip {
            background-color: #1E293B;
            color: #F1F5F9;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 3px 6px;
            font-size: 10px;
            font-weight: 500;
        }

        /* ===== BOTONES PRIMARIOS ===== */
        QPushButton#primaryBtn, QPushButton[variant="primary"] {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #2563EB, stop:1 #1D4ED8);
            color: #FFFFFF;
            border: 1px solid #3B82F6;
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }
        QPushButton#primaryBtn:hover, QPushButton[variant="primary"]:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #E600E6, stop:1 #CC00CC);
            border: 1px solid #FF4DFF;
        }
        QPushButton#primaryBtn:pressed, QPushButton[variant="primary"]:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #CC00CC, stop:1 #990099);
        }

        /* ===== BOTONES SECUNDARIOS ===== */
        QPushButton#secondaryBtn, QPushButton[variant="secondary"] {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #334155, stop:1 #1E293B);
            color: #F1F5F9;
            border: 1px solid #475569;
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }
        QPushButton#secondaryBtn:hover, QPushButton[variant="secondary"]:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #475569, stop:1 #334155);
            border: 1px solid #64748B;
        }

        /* ===== BOTONES ÉXITO ===== */
        QPushButton#successBtn, QPushButton[variant="success"] {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #16A34A, stop:1 #15803D);
            color: #FFFFFF;
            border: 1px solid #22C55E;
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }
        QPushButton#successBtn:hover, QPushButton[variant="success"]:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #22C55E, stop:1 #16A34A);
            border: 1px solid #4ADE80;
        }

        /* ===== BOTONES PELIGRO ===== */
        QPushButton#dangerBtn, QPushButton[variant="danger"] {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #DC2626, stop:1 #B91C1C);
            color: #FFFFFF;
            border: 1px solid #EF4444;
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }
        QPushButton#dangerBtn:hover, QPushButton[variant="danger"]:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #EF4444, stop:1 #DC2626);
            border: 1px solid #F87171;
        }

        /* ===== BOTONES ADVERTENCIA ===== */
        QPushButton#warningBtn, QPushButton[variant="warning"] {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #D97706, stop:1 #B45309);
            color: #FFFFFF;
            border: 1px solid #F59E0B;
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }
        QPushButton#warningBtn:hover, QPushButton[variant="warning"]:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #F59E0B, stop:1 #D97706);
            border: 1px solid #FBBF24;
        }

        /* ===== BOTONES OUTLINE ===== */
        QPushButton#outlineBtn, QPushButton[variant="outline"] {
            background: transparent;
            color: #2563EB;
            border: 2px solid #2563EB;
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }
        QPushButton#outlineBtn:hover, QPushButton[variant="outline"]:hover {
            background: rgba(37, 99, 235, 0.1);
            border: 2px solid #E600E6;
            color: #E600E6;
        }

        /* ===== BOTONES GENÉRICOS (fallback) ===== */
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #334155, stop:1 #1E293B);
            color: #F1F5F9;
            border: 1px solid #475569;
            border-radius: 5px;
            padding: 2px 6px;
            font-weight: 600;
            font-size: 10px;
            min-height: 20px;
            max-height: 22px;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #475569, stop:1 #334155);
            border: 1px solid #64748B;
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #1E293B, stop:1 #0F172A);
        }
        QPushButton:disabled {
            background: #1E293B;
            color: #64748B;
            border: 1px solid #334155;
        }

        /* ===== SCROLLBARS ===== */
        QScrollBar:vertical {
            background-color: #0F172A;
            width: 7px;
            border-radius: 4px;
            margin: 2px;
        }
        QScrollBar::handle:vertical {
            background-color: #334155;
            border-radius: 4px;
            min-height: 18px;
        }
        QScrollBar::handle:vertical:hover {
            background-color: #475569;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar:horizontal {
            background-color: #0F172A;
            height: 7px;
            border-radius: 4px;
            margin: 2px;
        }
        QScrollBar::handle:horizontal {
            background-color: #334155;
            border-radius: 4px;
            min-width: 18px;
        }
        QScrollBar::handle:horizontal:hover {
            background-color: #475569;
        }

        /* ===== TABS ===== */
        QTabWidget::pane {
            border: 1px solid #334155;
            border-radius: 8px;
            background-color: #1E293B;
        }
        QTabBar::tab {
            background-color: #1E293B;
            color: #94A3B8;
            border: 1px solid transparent;
            border-bottom: none;
            padding: 3px 8px;
            margin-right: 2px;
            border-radius: 5px 5px 0 0;
            font-weight: 500;
        }
        QTabBar::tab:selected {
            background-color: #334155;
            color: #F1F5F9;
            border: 1px solid #334155;
            border-bottom: none;
            font-weight: 600;
        }
        QTabBar::tab:hover:!selected {
            background-color: #283548;
            color: #F1F5F9;
        }

        /* ===== INPUTS ===== */
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
            background-color: #1E293B;
            color: #F1F5F9;
            border: 1px solid #334155;
            border-radius: 5px;
            padding: 3px 7px;
            selection-background-color: #2563EB;
            font-size: 11px;
            min-height: 22px;
        }
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, 
        QSpinBox:focus, QDoubleSpinBox:focus {
            border: 2px solid #E600E6;
            outline: none;
        }
        QLineEdit:disabled, QTextEdit:disabled {
            background-color: #0F172A;
            color: #64748B;
        }

        /* ===== COMBOBOX ===== */
        QComboBox {
            background-color: #1E293B;
            color: #F1F5F9;
            border: 1px solid #334155;
            border-radius: 5px;
            padding: 3px 7px;
            min-height: 22px;
        }
        QComboBox:hover {
            border: 1px solid #475569;
        }
        QComboBox:focus {
            border: 2px solid #E600E6;
        }
        QComboBox::drop-down {
            border: none;
            width: 20px;
            border-radius: 0 5px 5px 0;
        }
        QComboBox::down-arrow {
            image: none;
            border-left: 3px solid transparent;
            border-right: 3px solid transparent;
            border-top: 4px solid #94A3B8;
            margin-right: 6px;
        }
        QComboBox QAbstractItemView {
            background-color: #1E293B;
            color: #F1F5F9;
            border: 1px solid #334155;
            selection-background-color: #2563EB;
            border-radius: 5px;
            padding: 2px;
        }
        QComboBox QAbstractItemView::item {
            min-height: 22px;
            padding: 3px 7px;
            border-radius: 4px;
        }
        QComboBox QAbstractItemView::item:hover {
            background-color: #334155;
        }
        QComboBox QAbstractItemView::item:selected {
            background-color: #2563EB;
        }

        /* ===== AUTOCOMPLETE POPUP (QCompleter) ===== */
        QListView {
            background-color: #1E293B;
            color: #F1F5F9;
            border: 1px solid #334155;
            border-radius: 5px;
            outline: none;
            font-size: 11px;
        }
        QListView::item {
            padding: 3px 8px;
            min-height: 22px;
        }
        QListView::item:hover {
            background-color: #334155;
            color: #F1F5F9;
        }
        QListView::item:selected {
            background-color: #2563EB;
            color: #FFFFFF;
        }

        /* ===== TABLAS ===== */
        QTableWidget, QTableView {
            background-color: #1E293B;
            color: #F1F5F9;
            gridline-color: #334155;
            border: 1px solid #334155;
            alternate-background-color: #0F172A;
            border-radius: 8px;
        }
        QTableWidget::item, QTableView::item {
            padding: 4px 8px;
            border-bottom: 1px solid #334155;
        }
        QTableWidget::item:selected, QTableView::item:selected {
            background-color: #2563EB;
            color: #FFFFFF;
        }
        QTableWidget::item:hover, QTableView::item:hover {
            background-color: #334155;
        }
        QHeaderView::section {
            background-color: #334155;
            color: #F1F5F9;
            border: none;
            border-bottom: 2px solid #475569;
            font-weight: 600;
            padding: 3px 6px;
            text-transform: uppercase;
            font-size: 10px;
            letter-spacing: 0.5px;
            min-height: 24px;
            max-height: 24px;
        }
        QHeaderView::section:hover {
            background-color: #475569;
        }

        /* ===== GRUPOS ===== */
        QGroupBox {
            border: 1px solid #334155;
            border-radius: 6px;
            margin-top: 8px;
            padding-top: 8px;
            background-color: #1E293B;
            font-weight: 600;
            font-size: 11px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 6px;
            color: #60A5FA;
            background-color: #1E293B;
        }

        /* ===== CARDS / FRAMES ===== */
        QFrame#card, QFrame[variant="card"] {
            background-color: #1E293B;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 8px;
        }
        QFrame#cardHover:hover, QFrame[variant="card-hover"]:hover {
            background-color: #334155;
            border: 1px solid #475569;
        }
        QFrame#kpiCard {
            background-color: #1E293B;
            border: 1px solid #334155;
            border-radius: 8px;
            min-height: 70px;
            max-height: 90px;
        }
        QFrame#kpiCard:hover {
            background-color: #263548;
            border-color: #2563EB;
        }
        QLabel#kpiValue {
            color: #F1F5F9;
            font-size: 18px;
            font-weight: 700;
            background: transparent;
        }

        /* ===== LABELS ===== */
        QLabel#heading {
            font-size: 14px;
            font-weight: 700;
            color: #F1F5F9;
        }
        QLabel#subheading {
            font-size: 12px;
            font-weight: 600;
            color: #94A3B8;
        }
        QLabel#caption {
            font-size: 10px;
            color: #64748B;
        }
        QLabel#infoValue {
            color: #F1F5F9;
            font-size: 11px;
            font-weight: 600;
        }

        /* ===== CHECKBOX ===== */
        QCheckBox {
            color: #F1F5F9;
            spacing: 6px;
            font-size: 11px;
        }
        QCheckBox::indicator {
            width: 14px;
            height: 14px;
            border-radius: 3px;
            border: 2px solid #475569;
            background-color: #1E293B;
        }
        QCheckBox::indicator:checked {
            background-color: #2563EB;
            border: 2px solid #2563EB;
        }
        QCheckBox::indicator:hover {
            border: 2px solid #E600E6;
        }

        /* ===== RADIO BUTTON ===== */
        QRadioButton {
            color: #F1F5F9;
            spacing: 6px;
            font-size: 11px;
        }
        QRadioButton::indicator {
            width: 14px;
            height: 14px;
            border-radius: 7px;
            border: 2px solid #475569;
            background-color: #1E293B;
        }
        QRadioButton::indicator:checked {
            background-color: #2563EB;
            border: 2px solid #2563EB;
        }
        QRadioButton::indicator:hover {
            border: 2px solid #E600E6;
        }

        /* ===== PROGRESS BAR ===== */
        QProgressBar {
            background-color: #334155;
            border-radius: 8px;
            height: 10px;
            text-align: center;
            border: 1px solid #475569;
        }
        QProgressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #2563EB, stop:1 #E600E6);
            border-radius: 6px;
        }

        /* ===== SLIDER ===== */
        QSlider::groove:horizontal {
            background-color: #334155;
            height: 8px;
            border-radius: 4px;
        }
        QSlider::handle:horizontal {
            background-color: #2563EB;
            width: 20px;
            margin: -6px 0;
            border-radius: 10px;
        }
        QSlider::handle:horizontal:hover {
            background-color: #E600E6;
        }

        /* ===== LIST WIDGET ===== */
        QListWidget {
            background-color: #1E293B;
            color: #F1F5F9;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 8px;
        }
        QListWidget::item {
            padding: 10px 12px;
            border-radius: 6px;
            margin: 2px 0;
        }
        QListWidget::item:hover {
            background-color: #334155;
        }
        QListWidget::item:selected {
            background-color: #2563EB;
            color: #FFFFFF;
        }

        /* ===== TREE WIDGET ===== */
        QTreeWidget {
            background-color: #1E293B;
            color: #F1F5F9;
            border: 1px solid #334155;
            border-radius: 8px;
            alternate-background-color: #0F172A;
        }
        QTreeWidget::item {
            padding: 8px;
            border-radius: 4px;
        }
        QTreeWidget::item:hover {
            background-color: #334155;
        }
        QTreeWidget::item:selected {
            background-color: #2563EB;
        }
        QTreeWidget::branch:has-children:!has-siblings:closed,
        QTreeWidget::branch:closed:has-children:has-siblings {
            border-image: none;
        }
        QTreeWidget::branch:open:has-children:!has-siblings,
        QTreeWidget::branch:open:has-children:has-siblings {
            border-image: none;
        }

        /* ===== MENU BAR ===== */
        QMenuBar {
            background-color: #0F172A;
            color: #F1F5F9;
            border-bottom: 1px solid #334155;
            padding: 4px;
        }
        QMenuBar::item {
            padding: 8px 16px;
            border-radius: 6px;
        }
        QMenuBar::item:selected {
            background-color: #334155;
        }
        QMenuBar::item:pressed {
            background-color: #2563EB;
        }

        /* ===== DROPDOWN MENU ===== */
        QMenu {
            background-color: #1E293B;
            color: #F1F5F9;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 8px;
        }
        QMenu::item {
            padding: 10px 30px 10px 16px;
            border-radius: 6px;
        }
        QMenu::item:selected {
            background-color: #2563EB;
        }
        QMenu::separator {
            height: 1px;
            background-color: #334155;
            margin: 8px 0;
        }

        /* ===== STATUS BAR ===== */
        QStatusBar {
            background-color: #0F172A;
            color: #94A3B8;
            border-top: 1px solid #334155;
        }

        /* ===== SPLASH SCREEN ===== */
        QSplashScreen {
            background-color: #0F172A;
            border: 2px solid #2563EB;
            border-radius: 16px;
        }

        /* ===== CALENDAR ===== */
        QCalendarWidget {
            background-color: #1E293B;
            color: #F1F5F9;
            border: 1px solid #334155;
            border-radius: 8px;
        }
        QCalendarWidget QToolButton {
            background-color: transparent;
            color: #F1F5F9;
            border: none;
            border-radius: 6px;
            padding: 8px;
            font-weight: 600;
        }
        QCalendarWidget QToolButton:hover {
            background-color: #334155;
        }
        QCalendarWidget QMenu {
            background-color: #1E293B;
            color: #F1F5F9;
        }
        QCalendarWidget QSpinBox {
            background-color: #1E293B;
            color: #F1F5F9;
            border: 1px solid #334155;
        }

        /* ===== DOCK WIDGET ===== */
        QDockWidget {
            titlebar-close-icon: none;
            titlebar-normal-icon: none;
        }
        QDockWidget::title {
            background-color: #334155;
            padding: 8px;
            font-weight: 600;
        }
        QDockWidget::close-button, QDockWidget::float-button {
            border: none;
            padding: 4px;
        }

        /* ===== PRODUCT CARD STATES (ventas.py dynamic) ===== */
        QFrame[class="product-card"] {
            background-color: #1E293B;
            border: 1px solid #334155;
            border-radius: 8px;
        }
        QFrame[class="product-card-selected"] {
            background-color: #1E3A5F;
            border: 2px solid #2563EB;
            border-radius: 8px;
        }
        QFrame[class="product-card-hover"] {
            background-color: #263548;
            border: 1px solid #475569;
            border-radius: 8px;
        }

        /* ===== SCANNER INPUT FEEDBACK ===== */
        QLineEdit[class="input-scanner-success"] {
            border: 2px solid #10B981;
            background-color: rgba(16, 185, 129, 0.08);
        }
        QLineEdit[class="input-scanner-primary"] {
            border: 2px solid #2563EB;
        }
        QLineEdit[class="input-scanner-base"] {
            border: 1px solid #334155;
        }

        /* ===== PAYMENT / DIALOG LABELS ===== */
        QLabel[class="payment-total"] {
            font-size: 22px;
            font-weight: 700;
            color: #10B981;
        }
        QLabel[class="payment-change"] {
            font-size: 16px;
            font-weight: 700;
            color: #F1F5F9;
        }
        QLabel[class="payment-change-negative"] {
            font-size: 16px;
            font-weight: 700;
            color: #EF4444;
        }
        QLabel[class="dialog-title"], QLabel[class="payment-title"] {
            font-size: 14px;
            font-weight: 700;
            color: #F1F5F9;
        }

        /* ===== SEMANTIC TEXT UTILITIES ===== */
        QLabel[class="text-bold"]    { font-weight: 700; }
        QLabel[class="text-success"] { color: #10B981; font-weight: 600; }
        QLabel[class="text-danger"]  { color: #EF4444; font-weight: 600; }
        QLabel[class="text-warning"] { color: #F59E0B; font-weight: 600; }
        QLabel[class="text-info"]    { color: #3B82F6; font-weight: 600; }

        /* ===== STATUS LABELS (caja.py) ===== */
        QLabel[class="status-success"] {
            background-color: #064E3B;
            color: #10B981;
            border-radius: 4px;
            padding: 4px 8px;
            font-weight: 600;
        }
        QLabel[class="status-neutral"] {
            background-color: #1E293B;
            color: #94A3B8;
            border-radius: 4px;
            padding: 4px 8px;
        }

        /* ===== TYPOGRAPHY LABELS (ui_components.py) ===== */
        QLabel#headingLabel    { color: #F1F5F9; font-size: 14px; font-weight: 700; }
        QLabel#subheadingLabel { color: #94A3B8; font-size: 12px; font-weight: 600; }
        QLabel#captionLabel    { color: #64748B; font-size: 10px; }
        QLabel#bodyLabel       { color: #CBD5E1; font-size: 12px; }
        QLabel#labelRequired   { color: #EF4444; font-weight: 600; }
        QLabel#labelOptional   { color: #94A3B8; font-weight: 500; }

        /* ===== STAT CARD LABELS ===== */
        QLabel#statTitle { color: #64748B; font-size: 10px; font-weight: 500; }
        QLabel#statValue { color: #F1F5F9; font-size: 14px; font-weight: 700; }
        QLabel#statIconBg-primary { background-color: rgba(37, 99, 235, 0.12); border-radius: 8px; }
        QLabel#statIconBg-success { background-color: rgba(22, 163, 74, 0.12); border-radius: 8px; }
        QLabel#statIconBg-danger  { background-color: rgba(220, 38, 38, 0.12); border-radius: 8px; }
        QLabel#statIconBg-warning { background-color: rgba(217, 119, 6, 0.12); border-radius: 8px; }

        /* ===== BADGES ===== */
        QLabel#badge-primary { background-color: rgba(37, 99, 235, 0.15); color: #60A5FA; border-radius: 9999px; padding: 4px 8px; font-size: 10px; font-weight: 600; }
        QLabel#badge-success { background-color: rgba(22, 163, 74, 0.15); color: #4ADE80; border-radius: 9999px; padding: 4px 8px; font-size: 10px; font-weight: 600; }
        QLabel#badge-danger  { background-color: rgba(220, 38, 38, 0.15); color: #F87171; border-radius: 9999px; padding: 4px 8px; font-size: 10px; font-weight: 600; }
        QLabel#badge-warning { background-color: rgba(217, 119, 6, 0.15); color: #FCD34D; border-radius: 9999px; padding: 4px 8px; font-size: 10px; font-weight: 600; }
        QLabel#badge-info    { background-color: rgba(8, 145, 178, 0.15); color: #22D3EE; border-radius: 9999px; padding: 4px 8px; font-size: 10px; font-weight: 600; }
        QLabel#badge-neutral { background-color: #334155; color: #94A3B8; border-radius: 9999px; padding: 4px 8px; font-size: 10px; font-weight: 600; }

        /* ===== STANDARD TABLE (ui_components.py) ===== */
        QTableWidget#standardTable {
            background-color: #1E293B;
            color: #F1F5F9;
            gridline-color: #334155;
            border: 1px solid #334155;
            alternate-background-color: #0F172A;
            border-radius: 8px;
            font-size: 11px;
        }
        QTableWidget#standardTable::item {
            padding: 8px 12px;
            border-bottom: 1px solid #334155;
        }
        QTableWidget#standardTable::item:selected {
            background-color: #2563EB;
            color: #FFFFFF;
        }
        QTableWidget#standardTable::item:hover {
            background-color: #334155;
        }
        QTableWidget#standardTable QHeaderView::section {
            background-color: #334155;
            color: #F1F5F9;
            border: none;
            border-bottom: 2px solid #475569;
            font-weight: 600;
            padding: 8px 12px;
            font-size: 10px;
            min-height: 20px;
        }
        QTableWidget#standardTable QHeaderView::section:hover {
            background-color: #475569;
        }

        /* ===== TABLE BUTTONS ===== */
        QPushButton#tableBtn {
            background-color: transparent;
            border: 1px solid #475569;
            border-radius: 6px;
            padding: 4px 8px;
            font-size: 10px;
            font-weight: 500;
            color: #CBD5E1;
            min-height: 18px;
        }
        QPushButton#tableBtn:hover {
            background-color: #334155;
            border-color: #64748B;
            color: #F1F5F9;
        }
        QPushButton#tableBtn:pressed {
            background-color: #1E293B;
        }

        /* ===== QR PREVIEW PLACEHOLDER ===== */
        QLabel#qrPreviewEmpty {
            border: 2px dashed #475569;
            background-color: #1E293B;
            color: #64748B;
            font-size: 13px;
        }
        QLabel#selectionChip {
            color: #60A5FA;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 4px;
            border: 1px solid #475569;
            min-width: 120px;
        }

        /* ===== PAGE HEADINGS ===== */
        QLabel#pageHeading { font-size: 18px; font-weight: 700; color: #F1F5F9; }

        /* ===== INFO BOXES ===== */
        QLabel#infoBoxWarning {
            color: #94A3B8;
            background-color: #1E293B;
            padding: 6px;
            border-radius: 5px;
            font-size: 11px;
            border-left: 3px solid #D97706;
        }
        QLabel#infoBoxInfo {
            color: #94A3B8;
            background-color: #1E2D40;
            padding: 7px 16px;
            border-radius: 5px;
            font-size: 11px;
            border-left: 3px solid #2563EB;
        }
        QLabel#infoContent { font-size: 13px; padding: 8px 12px; color: #CBD5E1; }

        /* ===== SESSION BAR STATES (main_window.py) ===== */
        QLabel#sessionBarAdmin   { background: #1a252f; color: #EF4444; font-size: 11px; padding: 0 12px; font-weight: 700; }
        QLabel#sessionBarManager { background: #1a252f; color: #F59E0B; font-size: 11px; padding: 0 12px; font-weight: 700; }
        QLabel#sessionBarDefault { background: #2C3E50; color: #ecf0f1; font-size: 11px; padding: 0 12px; }
    """,

    "Claro": """
        /* ═══════════════════════════════════════════════════════════════════
           TEMA CLARO — SPJ POS v13.4
           Paleta: Slate/Zinc modern light theme con acentos magenta hover
           ═══════════════════════════════════════════════════════════════════ */

        /* ===== VARIABLES GLOBALES ===== */
        QMainWindow, QDialog, QWidget {
            background-color: #F8FAFC;
            color: #0F172A;
            font-family: 'Segoe UI', 'Inter', 'Roboto', sans-serif;
            font-size: 11px;
        }

        /* ===== TOOLTIPS ===== */
        QToolTip {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 12px;
            font-weight: 500;
        }

        /* ===== BOTONES PRIMARIOS ===== */
        QPushButton#primaryBtn, QPushButton[variant="primary"] {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #2563EB, stop:1 #1D4ED8);
            color: #FFFFFF;
            border: 1px solid #3B82F6;
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }
        QPushButton#primaryBtn:hover, QPushButton[variant="primary"]:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #E600E6, stop:1 #CC00CC);
            border: 1px solid #FF4DFF;
        }
        QPushButton#primaryBtn:pressed, QPushButton[variant="primary"]:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #CC00CC, stop:1 #990099);
        }

        /* ===== BOTONES SECUNDARIOS ===== */
        QPushButton#secondaryBtn, QPushButton[variant="secondary"] {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #F1F5F9, stop:1 #E2E8F0);
            color: #334155;
            border: 1px solid #CBD5E0;
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }
        QPushButton#secondaryBtn:hover, QPushButton[variant="secondary"]:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #E2E8F0, stop:1 #CBD5E0);
            border: 1px solid #94A3B8;
        }

        /* ===== BOTONES ÉXITO ===== */
        QPushButton#successBtn, QPushButton[variant="success"] {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #16A34A, stop:1 #15803D);
            color: #FFFFFF;
            border: 1px solid #22C55E;
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }
        QPushButton#successBtn:hover, QPushButton[variant="success"]:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #22C55E, stop:1 #16A34A);
            border: 1px solid #4ADE80;
        }

        /* ===== BOTONES PELIGRO ===== */
        QPushButton#dangerBtn, QPushButton[variant="danger"] {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #DC2626, stop:1 #B91C1C);
            color: #FFFFFF;
            border: 1px solid #EF4444;
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }
        QPushButton#dangerBtn:hover, QPushButton[variant="danger"]:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #EF4444, stop:1 #DC2626);
            border: 1px solid #F87171;
        }

        /* ===== BOTONES ADVERTENCIA ===== */
        QPushButton#warningBtn, QPushButton[variant="warning"] {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #D97706, stop:1 #B45309);
            color: #FFFFFF;
            border: 1px solid #F59E0B;
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }
        QPushButton#warningBtn:hover, QPushButton[variant="warning"]:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #F59E0B, stop:1 #D97706);
            border: 1px solid #FBBF24;
        }

        /* ===== BOTONES OUTLINE ===== */
        QPushButton#outlineBtn, QPushButton[variant="outline"] {
            background: transparent;
            color: #2563EB;
            border: 2px solid #2563EB;
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }
        QPushButton#outlineBtn:hover, QPushButton[variant="outline"]:hover {
            background: rgba(37, 99, 235, 0.08);
            border: 2px solid #E600E6;
            color: #E600E6;
        }

        /* ===== BOTONES GENÉRICOS (fallback) ===== */
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFFFFF, stop:1 #F1F5F9);
            color: #334155;
            border: 1px solid #E2E8F0;
            border-radius: 5px;
            padding: 3px 8px;
            font-weight: 600;
            font-size: 11px;
            min-height: 22px;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #F1F5F9, stop:1 #E2E8F0);
            border: 1px solid #CBD5E0;
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #E2E8F0, stop:1 #CBD5E0);
        }
        QPushButton:disabled {
            background: #F1F5F9;
            color: #94A3B8;
            border: 1px solid #E2E8F0;
        }

        /* ===== SCROLLBARS ===== */
        QScrollBar:vertical {
            background-color: #F8FAFC;
            width: 7px;
            border-radius: 4px;
            margin: 2px;
        }
        QScrollBar::handle:vertical {
            background-color: #CBD5E0;
            border-radius: 4px;
            min-height: 18px;
        }
        QScrollBar::handle:vertical:hover {
            background-color: #94A3B8;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar:horizontal {
            background-color: #F8FAFC;
            height: 7px;
            border-radius: 4px;
            margin: 2px;
        }
        QScrollBar::handle:horizontal {
            background-color: #CBD5E0;
            border-radius: 4px;
            min-width: 18px;
        }
        QScrollBar::handle:horizontal:hover {
            background-color: #94A3B8;
        }

        /* ===== TABS ===== */
        QTabWidget::pane {
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            background-color: #FFFFFF;
        }
        QTabBar::tab {
            background-color: #F1F5F9;
            color: #64748B;
            border: 1px solid transparent;
            border-bottom: none;
            padding: 3px 8px;
            margin-right: 2px;
            border-radius: 5px 5px 0 0;
            font-weight: 500;
        }
        QTabBar::tab:selected {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #E2E8F0;
            border-bottom: none;
            font-weight: 600;
        }
        QTabBar::tab:hover:!selected {
            background-color: #E2E8F0;
            color: #334155;
        }

        /* ===== INPUTS ===== */
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #E2E8F0;
            border-radius: 5px;
            padding: 3px 7px;
            selection-background-color: #2563EB;
            font-size: 11px;
        }
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, 
        QSpinBox:focus, QDoubleSpinBox:focus {
            border: 2px solid #E600E6;
            outline: none;
        }
        QLineEdit:disabled, QTextEdit:disabled {
            background-color: #F8FAFC;
            color: #94A3B8;
        }

        /* ===== COMBOBOX ===== */
        QComboBox {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #E2E8F0;
            border-radius: 5px;
            padding: 3px 7px;
            min-height: 22px;
        }
        QComboBox:hover {
            border: 1px solid #CBD5E0;
        }
        QComboBox:focus {
            border: 2px solid #E600E6;
        }
        QComboBox::drop-down {
            border: none;
            width: 20px;
            border-radius: 0 5px 5px 0;
        }
        QComboBox::down-arrow {
            image: none;
            border-left: 3px solid transparent;
            border-right: 3px solid transparent;
            border-top: 4px solid #64748B;
            margin-right: 6px;
        }
        QComboBox QAbstractItemView {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #E2E8F0;
            selection-background-color: #2563EB;
            border-radius: 5px;
            padding: 2px;
        }
        QComboBox QAbstractItemView::item {
            min-height: 22px;
            padding: 3px 7px;
            border-radius: 4px;
        }
        QComboBox QAbstractItemView::item:hover {
            background-color: #F1F5F9;
        }
        QComboBox QAbstractItemView::item:selected {
            background-color: #2563EB;
        }

        /* ===== TABLAS ===== */
        QTableWidget, QTableView {
            background-color: #FFFFFF;
            color: #0F172A;
            gridline-color: #E2E8F0;
            border: 1px solid #E2E8F0;
            alternate-background-color: #F8FAFC;
            border-radius: 8px;
        }
        QTableWidget::item, QTableView::item {
            padding: 8px 12px;
            border-bottom: 1px solid #E2E8F0;
        }
        QTableWidget::item:selected, QTableView::item:selected {
            background-color: #2563EB;
            color: #FFFFFF;
        }
        QTableWidget::item:hover, QTableView::item:hover {
            background-color: #F1F5F9;
        }
        QHeaderView::section {
            background-color: #F1F5F9;
            color: #334155;
            border: none;
            border-bottom: 2px solid #E2E8F0;
            font-weight: 600;
            padding: 3px 6px;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.5px;
            min-height: 20px;
            max-height: 20px;
        }
        QHeaderView::section:hover {
            background-color: #E2E8F0;
        }

        /* ===== GRUPOS ===== */
        QGroupBox {
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            margin-top: 8px;
            padding-top: 8px;
            background-color: #FFFFFF;
            font-weight: 600;
            font-size: 11px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 6px;
            color: #2563EB;
            background-color: #FFFFFF;
        }

        /* ===== CARDS / FRAMES ===== */
        QFrame#card, QFrame[variant="card"] {
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 8px;
        }
        QFrame#cardHover:hover, QFrame[variant="card-hover"]:hover {
            background-color: #F8FAFC;
            border: 1px solid #CBD5E0;
        }
        QFrame#kpiCard {
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            min-height: 70px;
            max-height: 90px;
        }
        QFrame#kpiCard:hover {
            background-color: #F1F5F9;
            border-color: #2563EB;
        }
        QLabel#kpiValue {
            color: #0F172A;
            font-size: 18px;
            font-weight: 700;
            background: transparent;
        }

        /* ===== LABELS ===== */
        QLabel#heading {
            font-size: 14px;
            font-weight: 700;
            color: #0F172A;
        }
        QLabel#subheading {
            font-size: 12px;
            font-weight: 600;
            color: #64748B;
        }
        QLabel#caption {
            font-size: 10px;
            color: #94A3B8;
        }
        QLabel#infoValue {
            color: #0F172A;
            font-size: 11px;
            font-weight: 600;
        }

        /* ===== CHECKBOX ===== */
        QCheckBox {
            color: #0F172A;
            spacing: 6px;
            font-size: 11px;
        }
        QCheckBox::indicator {
            width: 14px;
            height: 14px;
            border-radius: 3px;
            border: 2px solid #CBD5E0;
            background-color: #FFFFFF;
        }
        QCheckBox::indicator:checked {
            background-color: #2563EB;
            border: 2px solid #2563EB;
        }
        QCheckBox::indicator:hover {
            border: 2px solid #E600E6;
        }

        /* ===== RADIO BUTTON ===== */
        QRadioButton {
            color: #0F172A;
            spacing: 6px;
            font-size: 11px;
        }
        QRadioButton::indicator {
            width: 14px;
            height: 14px;
            border-radius: 7px;
            border: 2px solid #CBD5E0;
            background-color: #FFFFFF;
        }
        QRadioButton::indicator:checked {
            background-color: #2563EB;
            border: 2px solid #2563EB;
        }
        QRadioButton::indicator:hover {
            border: 2px solid #E600E6;
        }

        /* ===== PROGRESS BAR ===== */
        QProgressBar {
            background-color: #E2E8F0;
            border-radius: 8px;
            height: 10px;
            text-align: center;
            border: 1px solid #CBD5E0;
        }
        QProgressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #2563EB, stop:1 #E600E6);
            border-radius: 6px;
        }

        /* ===== SLIDER ===== */
        QSlider::groove:horizontal {
            background-color: #E2E8F0;
            height: 8px;
            border-radius: 4px;
        }
        QSlider::handle:horizontal {
            background-color: #2563EB;
            width: 20px;
            margin: -6px 0;
            border-radius: 10px;
        }
        QSlider::handle:horizontal:hover {
            background-color: #E600E6;
        }

        /* ===== LIST WIDGET ===== */
        QListWidget {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 8px;
        }
        QListWidget::item {
            padding: 10px 12px;
            border-radius: 6px;
            margin: 2px 0;
        }
        QListWidget::item:hover {
            background-color: #F1F5F9;
        }
        QListWidget::item:selected {
            background-color: #2563EB;
            color: #FFFFFF;
        }

        /* ===== TREE WIDGET ===== */
        QTreeWidget {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            alternate-background-color: #F8FAFC;
        }
        QTreeWidget::item {
            padding: 8px;
            border-radius: 4px;
        }
        QTreeWidget::item:hover {
            background-color: #F1F5F9;
        }
        QTreeWidget::item:selected {
            background-color: #2563EB;
        }

        /* ===== MENU BAR ===== */
        QMenuBar {
            background-color: #FFFFFF;
            color: #0F172A;
            border-bottom: 1px solid #E2E8F0;
            padding: 4px;
        }
        QMenuBar::item {
            padding: 8px 16px;
            border-radius: 6px;
        }
        QMenuBar::item:selected {
            background-color: #F1F5F9;
        }
        QMenuBar::item:pressed {
            background-color: #2563EB;
            color: #FFFFFF;
        }

        /* ===== DROPDOWN MENU ===== */
        QMenu {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 8px;
        }
        QMenu::item {
            padding: 10px 30px 10px 16px;
            border-radius: 6px;
        }
        QMenu::item:selected {
            background-color: #2563EB;
            color: #FFFFFF;
        }
        QMenu::separator {
            height: 1px;
            background-color: #E2E8F0;
            margin: 8px 0;
        }

        /* ===== STATUS BAR ===== */
        QStatusBar {
            background-color: #F8FAFC;
            color: #64748B;
            border-top: 1px solid #E2E8F0;
        }

        /* ===== SPLASH SCREEN ===== */
        QSplashScreen {
            background-color: #FFFFFF;
            border: 2px solid #2563EB;
            border-radius: 16px;
        }

        /* ===== CALENDAR ===== */
        QCalendarWidget {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
        }
        QCalendarWidget QToolButton {
            background-color: transparent;
            color: #0F172A;
            border: none;
            border-radius: 6px;
            padding: 8px;
            font-weight: 600;
        }
        QCalendarWidget QToolButton:hover {
            background-color: #F1F5F9;
        }
        QCalendarWidget QMenu {
            background-color: #FFFFFF;
            color: #0F172A;
        }
        QCalendarWidget QSpinBox {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #E2E8F0;
        }

        /* ===== DOCK WIDGET ===== */
        QDockWidget {
            titlebar-close-icon: none;
            titlebar-normal-icon: none;
        }
        QDockWidget::title {
            background-color: #F1F5F9;
            padding: 8px;
            font-weight: 600;
        }
        QDockWidget::close-button, QDockWidget::float-button {
            border: none;
            padding: 4px;
        }

        /* ===== PRODUCT CARD STATES (ventas.py dynamic) ===== */
        QFrame[class="product-card"] {
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
        }
        QFrame[class="product-card-selected"] {
            background-color: #EFF6FF;
            border: 2px solid #2563EB;
            border-radius: 8px;
        }
        QFrame[class="product-card-hover"] {
            background-color: #F8FAFC;
            border: 1px solid #CBD5E0;
            border-radius: 8px;
        }

        /* ===== SCANNER INPUT FEEDBACK ===== */
        QLineEdit[class="input-scanner-success"] {
            border: 2px solid #059669;
            background-color: rgba(5, 150, 105, 0.05);
        }
        QLineEdit[class="input-scanner-primary"] {
            border: 2px solid #2563EB;
        }
        QLineEdit[class="input-scanner-base"] {
            border: 1px solid #CBD5E0;
        }

        /* ===== PAYMENT / DIALOG LABELS ===== */
        QLabel[class="payment-total"] {
            font-size: 22px;
            font-weight: 700;
            color: #059669;
        }
        QLabel[class="payment-change"] {
            font-size: 16px;
            font-weight: 700;
            color: #0F172A;
        }
        QLabel[class="payment-change-negative"] {
            font-size: 16px;
            font-weight: 700;
            color: #DC2626;
        }
        QLabel[class="dialog-title"], QLabel[class="payment-title"] {
            font-size: 14px;
            font-weight: 700;
            color: #0F172A;
        }

        /* ===== SEMANTIC TEXT UTILITIES ===== */
        QLabel[class="text-bold"]    { font-weight: 700; }
        QLabel[class="text-success"] { color: #059669; font-weight: 600; }
        QLabel[class="text-danger"]  { color: #DC2626; font-weight: 600; }
        QLabel[class="text-warning"] { color: #D97706; font-weight: 600; }
        QLabel[class="text-info"]    { color: #2563EB; font-weight: 600; }

        /* ===== STATUS LABELS (caja.py) ===== */
        QLabel[class="status-success"] {
            background-color: #D1FAE5;
            color: #065F46;
            border-radius: 4px;
            padding: 4px 8px;
            font-weight: 600;
        }
        QLabel[class="status-neutral"] {
            background-color: #F1F5F9;
            color: #64748B;
            border-radius: 4px;
            padding: 4px 8px;
        }

        /* ===== TYPOGRAPHY LABELS (ui_components.py) ===== */
        QLabel#headingLabel    { color: #0F172A; font-size: 14px; font-weight: 700; }
        QLabel#subheadingLabel { color: #334155; font-size: 12px; font-weight: 600; }
        QLabel#captionLabel    { color: #64748B; font-size: 10px; }
        QLabel#bodyLabel       { color: #475569; font-size: 12px; }
        QLabel#labelRequired   { color: #DC2626; font-weight: 600; }
        QLabel#labelOptional   { color: #475569; font-weight: 500; }

        /* ===== STAT CARD LABELS ===== */
        QLabel#statTitle { color: #64748B; font-size: 10px; font-weight: 500; }
        QLabel#statValue { color: #0F172A; font-size: 14px; font-weight: 700; }
        QLabel#statIconBg-primary { background-color: rgba(37, 99, 235, 0.08); border-radius: 8px; }
        QLabel#statIconBg-success { background-color: rgba(22, 163, 74, 0.08); border-radius: 8px; }
        QLabel#statIconBg-danger  { background-color: rgba(220, 38, 38, 0.08); border-radius: 8px; }
        QLabel#statIconBg-warning { background-color: rgba(217, 119, 6, 0.08); border-radius: 8px; }

        /* ===== BADGES ===== */
        QLabel#badge-primary { background-color: #DBEAFE; color: #2563EB; border-radius: 9999px; padding: 4px 8px; font-size: 10px; font-weight: 600; }
        QLabel#badge-success { background-color: #DCFCE7; color: #16A34A; border-radius: 9999px; padding: 4px 8px; font-size: 10px; font-weight: 600; }
        QLabel#badge-danger  { background-color: #FEE2E2; color: #DC2626; border-radius: 9999px; padding: 4px 8px; font-size: 10px; font-weight: 600; }
        QLabel#badge-warning { background-color: #FEF3C7; color: #D97706; border-radius: 9999px; padding: 4px 8px; font-size: 10px; font-weight: 600; }
        QLabel#badge-info    { background-color: #ECFEFF; color: #0891B2; border-radius: 9999px; padding: 4px 8px; font-size: 10px; font-weight: 600; }
        QLabel#badge-neutral { background-color: #F1F5F9; color: #475569; border-radius: 9999px; padding: 4px 8px; font-size: 10px; font-weight: 600; }

        /* ===== STANDARD TABLE (ui_components.py) ===== */
        QTableWidget#standardTable {
            background-color: #FFFFFF;
            color: #0F172A;
            gridline-color: #E2E8F0;
            border: 1px solid #E2E8F0;
            alternate-background-color: #F8FAFC;
            border-radius: 8px;
            font-size: 11px;
        }
        QTableWidget#standardTable::item {
            padding: 8px 12px;
            border-bottom: 1px solid #E2E8F0;
        }
        QTableWidget#standardTable::item:selected {
            background-color: #2563EB;
            color: #FFFFFF;
        }
        QTableWidget#standardTable::item:hover {
            background-color: #F1F5F9;
        }
        QTableWidget#standardTable QHeaderView::section {
            background-color: #F1F5F9;
            color: #0F172A;
            border: none;
            border-bottom: 2px solid #E2E8F0;
            font-weight: 600;
            padding: 8px 12px;
            font-size: 10px;
            min-height: 20px;
        }
        QTableWidget#standardTable QHeaderView::section:hover {
            background-color: #E2E8F0;
        }

        /* ===== TABLE BUTTONS ===== */
        QPushButton#tableBtn {
            background-color: transparent;
            border: 1px solid #CBD5E0;
            border-radius: 6px;
            padding: 4px 8px;
            font-size: 10px;
            font-weight: 500;
            color: #475569;
            min-height: 18px;
        }
        QPushButton#tableBtn:hover {
            background-color: #F1F5F9;
            border-color: #94A3B8;
            color: #0F172A;
        }
        QPushButton#tableBtn:pressed {
            background-color: #E2E8F0;
        }

        /* ===== QR PREVIEW PLACEHOLDER ===== */
        QLabel#qrPreviewEmpty {
            border: 2px dashed #CBD5E0;
            background-color: #F8FAFC;
            color: #94A3B8;
            font-size: 13px;
        }
        QLabel#selectionChip {
            color: #2563EB;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 4px;
            border: 1px solid #94A3B8;
            min-width: 120px;
        }

        /* ===== PAGE HEADINGS ===== */
        QLabel#pageHeading { font-size: 18px; font-weight: 700; color: #0F172A; }

        /* ===== INFO BOXES ===== */
        QLabel#infoBoxWarning {
            color: #64748B;
            background-color: #FFFBEA;
            padding: 6px;
            border-radius: 5px;
            font-size: 11px;
            border-left: 3px solid #D97706;
        }
        QLabel#infoBoxInfo {
            color: #64748B;
            background-color: #F0F4FF;
            padding: 7px 16px;
            border-radius: 5px;
            font-size: 11px;
            border-left: 3px solid #2563EB;
        }
        QLabel#infoContent { font-size: 13px; padding: 8px 12px; color: #334155; }

        /* ===== SESSION BAR STATES (main_window.py) ===== */
        QLabel#sessionBarAdmin   { background: #1a252f; color: #DC2626; font-size: 11px; padding: 0 12px; font-weight: 700; }
        QLabel#sessionBarManager { background: #1a252f; color: #D97706; font-size: 11px; padding: 0 12px; font-weight: 700; }
        QLabel#sessionBarDefault { background: #2C3E50; color: #ecf0f1; font-size: 11px; padding: 0 12px; }
    """
}

# --- Rutas y configuración adicional ---
