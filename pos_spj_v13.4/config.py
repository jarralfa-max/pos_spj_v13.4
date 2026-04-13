
# config.py
import os
import sqlite3

# --- Rutas ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICONS_DIR = os.path.join(BASE_DIR, "recursos", "icons")
DATABASE_NAME = "punto_venta.db"

# --- TEMAS SIMPLIFICADOS: SOLO CLARO Y OSCURO ---
TEMAS = {
    "Oscuro": """
        /* ===== PALETA DE COLORES OSCURO ===== */
        QMainWindow, QDialog, QWidget {
            background-color: #1E1E1E;
            color: #E8E8E8;
            font-family: 'Segoe UI', 'Roboto', sans-serif;
            font-size: 11px;
        }
        
        /* ===== TOOLTIPS ===== */
        QToolTip {
            background-color: #2D3748;
            color: #E8E8E8;
            border: 1px solid #4A5568;
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 10px;
        }
        
        /* ===== BOTONES PRINCIPALES ===== */
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #4A5568, stop:1 #2D3748);
            color: #FFFFFF;
            border: 1px solid #4A5568;
            border-radius: 8px;
            padding: 10px 15px;
            font-weight: 600;
            font-size: 11px;
            min-height: 35px;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #5A6578, stop:1 #3D4758);
            border: 1px solid #63B3ED;
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #2D3748, stop:1 #1A202C);
        }
        QPushButton:disabled {
            background: #2D3748;
            color: #718096;
            border: 1px solid #4A5568;
        }
        
        /* ===== SCROLLBARS ===== */
        QScrollBar:vertical {
            background-color: #1E1E1E;
            width: 10px;
            border-radius: 5px;
        }
        QScrollBar::handle:vertical {
            background-color: #4A5568;
            border-radius: 5px;
            min-height: 20px;
        }
        QScrollBar::handle:vertical:hover {
            background-color: #63B3ED;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar:horizontal {
            background-color: #1E1E1E;
            height: 10px;
            border-radius: 5px;
        }
        QScrollBar::handle:horizontal {
            background-color: #4A5568;
            border-radius: 5px;
            min-width: 20px;
        }
        QScrollBar::handle:horizontal:hover {
            background-color: #63B3ED;
        }
        
        /* ===== TABS ===== */
        QTabWidget::pane {
            border: 1px solid #4A5568;
            border-radius: 4px;
            background-color: #2D3748;
        }
        QTabBar::tab {
            background-color: #2D3748;
            color: #E8E8E8;
            border: 1px solid #4A5568;
            border-bottom: none;
            padding: 8px 16px;
            margin-right: 2px;
            border-radius: 4px 4px 0 0;
        }
        QTabBar::tab:selected {
            background-color: #4A5568;
            font-weight: bold;
        }
        QTabBar::tab:hover:!selected {
            background-color: #3D4758;
        }
        
        /* ===== INPUTS ===== */
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
            background-color: #2D3748;
            color: #E8E8E8;
            border: 1px solid #4A5568;
            border-radius: 4px;
            padding: 6px 10px;
            selection-background-color: #4A5568;
        }
        QLineEdit:focus, QTextEdit:focus {
            border: 2px solid #63B3ED;
        }
        QComboBox {
            background-color: #2D3748;
            color: #E8E8E8;
            border: 1px solid #4A5568;
            border-radius: 4px;
            padding: 6px 10px;
        }
        QComboBox::drop-down {
            border: none;
            width: 20px;
        }
        QComboBox QAbstractItemView {
            background-color: #2D3748;
            color: #E8E8E8;
            border: 1px solid #4A5568;
            selection-background-color: #4A5568;
        }
        
        /* ===== TABLAS ===== */
        QTableWidget, QTableView {
            background-color: #2D3748;
            color: #E8E8E8;
            gridline-color: #4A5568;
            border: 1px solid #4A5568;
            alternate-background-color: #1E1E1E;
        }
        QTableWidget::item:selected, QTableView::item:selected {
            background-color: #4A5568;
            color: #FFFFFF;
        }
        QHeaderView::section {
            background-color: #3D4758;
            color: #E8E8E8;
            border: none;
            border-bottom: 1px solid #4A5568;
            font-weight: bold;
            padding: 8px;
        }
        
        /* ===== GRUPOS ===== */
        QGroupBox {
            border: 1px solid #4A5568;
            border-radius: 6px;
            margin-top: 12px;
            padding-top: 10px;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 6px;
            color: #63B3ED;
        }
    """,
    
    "Claro": """
        /* ===== PALETA DE COLORES CLARO ===== */
        QMainWindow, QDialog, QWidget {
            background-color: #F7FAFC;
            color: #2D3748;
            font-family: 'Segoe UI', 'Roboto', sans-serif;
            font-size: 11px;
        }
        
        /* ===== TOOLTIPS ===== */
        QToolTip {
            background-color: #FFFFFF;
            color: #2D3748;
            border: 1px solid #CBD5E0;
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 10px;
        }
        
        /* ===== BOTONES PRINCIPALES ===== */
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFFFFF, stop:1 #EDF2F7);
            color: #2D3748;
            border: 2px solid #E2E8F0;
            border-radius: 8px;
            padding: 10px 15px;
            font-weight: 600;
            font-size: 11px;
            min-height: 35px;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFFFFF, stop:1 #E2E8F0);
            border: 2px solid #4299E1;
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #EDF2F7, stop:1 #CBD5E0);
        }
        QPushButton:disabled {
            background: #EDF2F7;
            color: #A0AEC0;
            border: 2px solid #E2E8F0;
        }
        
        /* ===== SCROLLBARS ===== */
        QScrollBar:vertical {
            background-color: #F7FAFC;
            width: 10px;
            border-radius: 5px;
        }
        QScrollBar::handle:vertical {
            background-color: #CBD5E0;
            border-radius: 5px;
            min-height: 20px;
        }
        QScrollBar::handle:vertical:hover {
            background-color: #4299E1;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar:horizontal {
            background-color: #F7FAFC;
            height: 10px;
            border-radius: 5px;
        }
        QScrollBar::handle:horizontal {
            background-color: #CBD5E0;
            border-radius: 5px;
            min-width: 20px;
        }
        QScrollBar::handle:horizontal:hover {
            background-color: #4299E1;
        }
        
        /* ===== TABS ===== */
        QTabWidget::pane {
            border: 1px solid #E2E8F0;
            border-radius: 4px;
            background-color: #FFFFFF;
        }
        QTabBar::tab {
            background-color: #EDF2F7;
            color: #2D3748;
            border: 1px solid #E2E8F0;
            border-bottom: none;
            padding: 8px 16px;
            margin-right: 2px;
            border-radius: 4px 4px 0 0;
        }
        QTabBar::tab:selected {
            background-color: #FFFFFF;
            font-weight: bold;
            border-bottom: 2px solid #4299E1;
        }
        QTabBar::tab:hover:!selected {
            background-color: #E2E8F0;
        }
        
        /* ===== INPUTS ===== */
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
            background-color: #FFFFFF;
            color: #2D3748;
            border: 1px solid #E2E8F0;
            border-radius: 4px;
            padding: 6px 10px;
            selection-background-color: #E2E8F0;
        }
        QLineEdit:focus, QTextEdit:focus {
            border: 2px solid #4299E1;
        }
        QComboBox {
            background-color: #FFFFFF;
            color: #2D3748;
            border: 1px solid #E2E8F0;
            border-radius: 4px;
            padding: 6px 10px;
        }
        QComboBox::drop-down {
            border: none;
            width: 20px;
        }
        QComboBox QAbstractItemView {
            background-color: #FFFFFF;
            color: #2D3748;
            border: 1px solid #E2E8F0;
            selection-background-color: #E2E8F0;
        }
        
        /* ===== TABLAS ===== */
        QTableWidget, QTableView {
            background-color: #FFFFFF;
            color: #2D3748;
            gridline-color: #E2E8F0;
            border: 1px solid #E2E8F0;
            alternate-background-color: #F7FAFC;
        }
        QTableWidget::item:selected, QTableView::item:selected {
            background-color: #4299E1;
            color: #FFFFFF;
        }
        QHeaderView::section {
            background-color: #EDF2F7;
            color: #2D3748;
            border: none;
            border-bottom: 1px solid #E2E8F0;
            font-weight: bold;
            padding: 8px;
        }
        
        /* ===== GRUPOS ===== */
        QGroupBox {
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            margin-top: 12px;
            padding-top: 10px;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 6px;
            color: #4299E1;
        }
    """
}

# --- Rutas y configuración adicional ---
