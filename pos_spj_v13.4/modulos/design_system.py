"""
SISTEMA DE DISEÑO CENTRALIZADO (DESIGN SYSTEM)
Estándar UI/UX v2.0 - Basado en Tailwind CSS & Material Design 3
"""
from PyQt5.QtGui import QColor, QFont, QFontDatabase
from PyQt5.QtCore import Qt

class Colors:
    """Paleta de colores centralizada"""
    # Primarios
    PRIMARY = "#3B82F6"       # Blue-500
    PRIMARY_HOVER = "#2563EB" # Blue-600
    PRIMARY_LIGHT = "#EFF6FF" # Blue-50
    
    # Neutros (Texto y Fondos)
    SLATE_50 = "#F8FAFC"
    SLATE_100 = "#F1F5F9"
    SLATE_200 = "#E2E8F0"
    SLATE_300 = "#CBD5E1"
    SLATE_400 = "#94A3B8"
    SLATE_500 = "#64748B"     # Títulos de sección
    SLATE_600 = "#475569"
    SLATE_700 = "#334155"
    SLATE_800 = "#1E293B"
    SLATE_900 = "#0F172A"
    
    # Estados
    SUCCESS = "#10B981"       # Emerald-500
    SUCCESS_BG = "#D1FAE5"
    WARNING = "#F59E0B"       # Amber-500
    WARNING_BG = "#FEF3C7"
    ERROR = "#EF4444"         # Red-500
    ERROR_BG = "#FEE2E2"
    INFO = "#3B82F6"
    INFO_BG = "#DBEAFE"
    
    # Fondos de aplicación
    APP_BACKGROUND = "#F1F5F9"      # Slate-100 (Modo Claro)
    CARD_BACKGROUND = "#FFFFFF"
    SIDEBAR_BACKGROUND = "#0F172A"  # Slate-900
    SIDEBAR_TEXT = "#F8FAFC"
    SIDEBAR_SECTION = "#64748B"     # Slate-500
    
    # Modo Oscuro (Para implementar futura compatibilidad)
    DARK_BG = "#020617"
    DARK_CARD = "#1E293B"
    DARK_TEXT = "#F8FAFC"

class Spacing:
    """Sistema de espaciado consistente (en píxeles)"""
    XS = 4
    SM = 8
    MD = 16
    LG = 24
    XL = 32
    XXL = 48

class Typography:
    """Tipografía estandarizada"""
    FONT_FAMILY = "Segoe UI"  # Fallback: Arial, sans-serif
    
    # Tamaños
    XS = 10
    SM = 12
    BASE = 14
    LG = 16
    XL = 20
    XXL = 24
    XXXL = 32
    
    # Pesos
    LIGHT = QFont.Light
    NORMAL = QFont.Normal
    MEDIUM = QFont.Medium
    BOLD = QFont.Bold
    
    @staticmethod
    def get_font(size=BASE, weight=NORMAL, italic=False):
        font = QFont(Typography.FONT_FAMILY, size)
        font.setWeight(weight)
        font.setItalic(italic)
        font.setHintingPreference(QFont.PreferFullHinting)
        font.setStyleStrategy(QFont.PreferAntialias)
        return font

class Shadows:
    """Sombras consistentes"""
    NONE = ""
    SM = "QFrame#card { background: white; border-radius: 6px; border: 1px solid #E2E8F0; }"
    MD = "QFrame#card { background: white; border-radius: 8px; border: 1px solid #E2E8F0; }"
    LG = "QFrame#card { background: white; border-radius: 12px; border: 1px solid #E2E8F0; }"
    HOVER = "QFrame#card:hover { background: #F8FAFC; border-color: #3B82F6; }"

class Sizes:
    """Tamaños estándar de componentes"""
    BUTTON_HEIGHT = 36
    BUTTON_MIN_WIDTH = 100
    INPUT_HEIGHT = 36
    TABLE_ROW_HEIGHT = 32
    HEADER_HEIGHT = 48
    ICON_SIZE = 16
    LOGO_MAX_SIZE = 140

class Styles:
    """Clases de utilidad para estilos inline"""
    
    @staticmethod
    def heading():
        return f"color: {Colors.SLATE_900}; font-size: {Typography.XXL}px; font-weight: bold;"
    
    @staticmethod
    def subheading():
        return f"color: {Colors.SLATE_700}; font-size: {Typography.LG}px; font-weight: 600;"
    
    @staticmethod
    def caption():
        return f"color: {Colors.SLATE_500}; font-size: {Typography.SM}px;"
    
    @staticmethod
    def sidebar_section():
        return f"color: {Colors.SIDEBAR_SECTION}; font-size: {Typography.XS}px; font-weight: bold; text-transform: uppercase; padding: 8px 16px;"
    
    @staticmethod
    def button_primary():
        return f"""
            QPushButton {{
                background-color: {Colors.PRIMARY};
                color: white;
                border-radius: 6px;
                font-weight: 600;
                min-height: {Sizes.BUTTON_HEIGHT}px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: {Colors.PRIMARY_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {Colors.PRIMARY};
            }}
        """
    
    @staticmethod
    def button_secondary():
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {Colors.SLATE_700};
                border: 1px solid {Colors.SLATE_300};
                border-radius: 6px;
                font-weight: 500;
                min-height: {Sizes.BUTTON_HEIGHT}px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: {Colors.SLATE_100};
                border-color: {Colors.SLATE_400};
            }}
        """
    
    @staticmethod
    def button_success():
        return f"""
            QPushButton {{
                background-color: {Colors.SUCCESS};
                color: white;
                border-radius: 6px;
                font-weight: 600;
                min-height: {Sizes.BUTTON_HEIGHT}px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: #059669;
            }}
        """
    
    @staticmethod
    def input_field():
        return f"""
            QLineEdit, QComboBox, QDateEdit, QSpinBox {{
                background-color: white;
                border: 1px solid {Colors.SLATE_300};
                border-radius: 6px;
                padding: 6px 12px;
                min-height: {Sizes.INPUT_HEIGHT}px;
                color: {Colors.SLATE_900};
                selection-background-color: {Colors.PRIMARY};
                selection-color: white;
            }}
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus {{
                border-color: {Colors.PRIMARY};
                outline: 2px solid {Colors.PRIMARY_LIGHT};
            }}
        """
    
    @staticmethod
    def table_header():
        return f"""
            QHeaderView::section {{
                background-color: {Colors.SLATE_50};
                color: {Colors.SLATE_700};
                font-weight: 600;
                font-size: {Typography.SM}px;
                padding: 8px;
                border: none;
                border-bottom: 2px solid {Colors.SLATE_200};
                text-align: left;
            }}
        """
    
    @staticmethod
    def table_row():
        return f"""
            QTableView {{
                gridline-color: {Colors.SLATE_200};
                background-color: white;
                alternate-background-color: {Colors.SLATE_50};
                selection-background-color: {Colors.PRIMARY_LIGHT};
                selection-color: {Colors.SLATE_900};
                border: 1px solid {Colors.SLATE_200};
                border-radius: 6px;
            }}
            QTableView::item {{
                padding: 6px;
                min-height: {Sizes.TABLE_ROW_HEIGHT}px;
            }}
            QTableView::item:hover {{
                background-color: {Colors.SLATE_100};
            }}
        """
