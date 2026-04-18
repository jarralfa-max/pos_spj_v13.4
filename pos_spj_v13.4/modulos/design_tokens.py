# modulos/design_tokens.py — SPJ POS v13.4
"""
Sistema de Design Tokens centralizado para SPJ POS.
Define todas las variables de diseño: colores, espaciado, tipografía, bordes, sombras.

USO:
    from modulos.design_tokens import Colors, Spacing, Typography, Borders, Shadows
    
    # Colores
    Colors.PRIMARY_BASE      # #2563EB
    Colors.PRIMARY_HOVER     # #E600E6
    Colors.SUCCESS_BASE      # #16A34A
    
    # Espaciado (sistema de 8px)
    Spacing.XS   # 4px
    Spacing.SM   # 8px
    Spacing.MD   # 12px
    Spacing.LG   # 16px
    Spacing.XL   # 24px
    
    # Tipografía
    Typography.FONT_FAMILY   # 'Segoe UI', 'Inter', 'Roboto'
    Typography.SIZE_XS       # 10px
    Typography.SIZE_SM       # 11px
    Typography.SIZE_MD       # 12px
    Typography.SIZE_LG       # 13px
    Typography.SIZE_XL       # 14px
    Typography.SIZE_XXL      # 16px
    
    # Bordes
    Borders.RADIUS_SM        # 4px
    Borders.RADIUS_MD        # 6px
    Borders.RADIUS_LG        # 8px
    Borders.RADIUS_XL        # 12px
    
    # Sombras
    Shadows.SM               # shadow suave
    Shadows.MD               # shadow estándar
    Shadows.LG               # shadow pronunciada
"""

from dataclasses import dataclass
from typing import Dict, Tuple


# ═══════════════════════════════════════════════════════════════════════════════
#  COLORES — Design System SPJ POS v13.4
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PrimaryColors:
    """Colores primarios (azul) con variantes hover/active."""
    BASE: str = "#2563EB"
    HOVER: str = "#E600E6"      # Magenta para hover
    ACTIVE: str = "#CC00CC"     # Magenta oscuro para active
    GLOW: str = "#FF4DFF"       # Glow effect
    LIGHT: str = "#DBEAFE"      # Fondo suave
    DARK: str = "#1D4ED8"       # Versión oscura


@dataclass(frozen=True)
class SuccessColors:
    """Colores de éxito (verde)."""
    BASE: str = "#16A34A"
    HOVER: str = "#22C55E"
    ACTIVE: str = "#15803D"
    BG_SOFT: str = "#DCFCE7"
    BORDER: str = "#22C55E"


@dataclass(frozen=True)
class DangerColors:
    """Colores de peligro/error (rojo)."""
    BASE: str = "#DC2626"
    HOVER: str = "#EF4444"
    ACTIVE: str = "#B91C1C"
    BG_SOFT: str = "#FEE2E2"
    BORDER: str = "#EF4444"


@dataclass(frozen=True)
class WarningColors:
    """Colores de advertencia (ámbar/naranja)."""
    BASE: str = "#D97706"
    HOVER: str = "#F59E0B"
    ACTIVE: str = "#B45309"
    BG_SOFT: str = "#FEF3C7"
    BORDER: str = "#F59E0B"


@dataclass(frozen=True)
class InfoColors:
    """Colores informativos (cyan/azul claro)."""
    BASE: str = "#0891B2"
    HOVER: str = "#06B6D4"
    ACTIVE: str = "#0E7490"
    BG_SOFT: str = "#ECFEFF"
    BORDER: str = "#06B6D4"


@dataclass(frozen=True)
class AccentColors:
    """Colores de acento (violeta)."""
    BASE: str = "#7C3AED"
    HOVER: str = "#8B5CF6"
    ACTIVE: str = "#6D28D9"
    BG_SOFT: str = "#F5F3FF"


@dataclass(frozen=True)
class NeutralColors:
    """Colores neutrales (grises Slate)."""
    # Modo claro
    WHITE: str = "#FFFFFF"
    SLATE_50: str = "#F8FAFC"
    SLATE_100: str = "#F1F5F9"
    SLATE_200: str = "#E2E8F0"
    SLATE_300: str = "#CBD5E1"
    SLATE_400: str = "#94A3B8"
    SLATE_500: str = "#64748B"
    SLATE_600: str = "#475569"
    SLATE_700: str = "#334155"
    SLATE_800: str = "#1E293B"
    SLATE_900: str = "#0F172A"
    SLATE_950: str = "#020617"
    
    # Modo oscuro (inverso)
    DARK_BG: str = "#0F172A"
    DARK_CARD: str = "#1E293B"
    DARK_BORDER: str = "#334155"
    DARK_TEXT: str = "#F1F5F9"
    DARK_TEXT_SEC: str = "#94A3B8"


@dataclass(frozen=True)
class SidebarColors:
    """Colores del sidebar (SIEMPRE OSCURO)."""
    BG: str = "#020617"         # Slate 950
    HOVER: str = "#1E293B"      # Slate 800
    ACTIVE: str = "#2563EB"     # Primary blue
    TEXT: str = "#E2E8F0"       # Slate 200
    ICON: str = "#94A3B8"       # Slate 400
    BORDER: str = "#1E293B"     # Slate 800


@dataclass(frozen=True)
class TooltipColors:
    """Colores para tooltips globales."""
    # Claro
    LIGHT_BG: str = "#0F172A"
    LIGHT_TEXT: str = "#F8FAFC"
    # Oscuro
    DARK_BG: str = "#1E293B"
    DARK_TEXT: str = "#E2E8F0"
    BORDER: str = "#334155"


class Colors:
    """Clase contenedora de todos los colores."""
    PRIMARY = PrimaryColors()
    SUCCESS = SuccessColors()
    DANGER = DangerColors()
    WARNING = WarningColors()
    INFO = InfoColors()
    ACCENT = AccentColors()
    NEUTRAL = NeutralColors()
    SIDEBAR = SidebarColors()
    TOOLTIP = TooltipColors()
    
    # Alias directos para compatibilidad (Single Source of Truth)
    PRIMARY_BASE = "#2563EB"
    PRIMARY_HOVER = "#E600E6"
    PRIMARY_ACTIVE = "#CC00CC"
    SUCCESS_BASE = "#16A34A"
    SUCCESS_HOVER = "#22C55E"
    DANGER_BASE = "#DC2626"
    DANGER_HOVER = "#EF4444"
    WARNING_BASE = "#D97706"
    WARNING_HOVER = "#F59E0B"
    INFO_BASE = "#0891B2"
    INFO_HOVER = "#06B6D4"
    ACCENT_BASE = "#7C3AED"
    ACCENT_HOVER = "#8B5CF6"

    # Alias legacy de texto (evita crashes por atributos faltantes).
    TEXT_PRIMARY = NeutralColors().SLATE_800
    TEXT_SECONDARY = NeutralColors().SLATE_500
    TEXT_MUTED = NeutralColors().SLATE_400


# ═══════════════════════════════════════════════════════════════════════════════
#  ESPACIADO — Sistema de grid de 8px
# ═══════════════════════════════════════════════════════════════════════════════

class Spacing:
    """Sistema de espaciado consistente basado en múltiplos de 4px."""
    XS = 4    # 4px - mínimo
    SM = 8    # 8px - base
    MD = 12   # 12px - estándar
    LG = 16   # 16px - amplio
    XL = 24   # 24px - extra amplio
    XXL = 32  # 32px - sección
    XXXL = 48 # 48px - separación grande
    
    # Para padding de botones (height 22-26px)
    BTN_PADDING_X = 8
    BTN_PADDING_Y = 3
    BTN_HEIGHT_MIN = 22
    BTN_HEIGHT_MAX = 26


# ═══════════════════════════════════════════════════════════════════════════════
#  TIPOGRAFÍA
# ═══════════════════════════════════════════════════════════════════════════════

class Typography:
    """Sistema tipográfico consistente."""
    FONT_FAMILY = "'Segoe UI', 'Inter', 'Roboto', sans-serif"
    
    # Tamaños
    SIZE_XS = "10px"   # Captions, labels secundarios
    SIZE_SM = "11px"   # Botones, inputs, texto pequeño
    SIZE_MD = "12px"   # Texto base
    SIZE_LG = "13px"   # Subtítulos, labels importantes
    SIZE_XL = "14px"   # Títulos de sección
    SIZE_XXL = "16px"  # Títulos principales
    
    # Pesos
    WEIGHT_NORMAL = 400
    WEIGHT_MEDIUM = 500
    WEIGHT_SEMIBOLD = 600
    WEIGHT_BOLD = 700
    
    # Alturas de línea
    LINE_HEIGHT_TIGHT = 1.25
    LINE_HEIGHT_NORMAL = 1.5
    LINE_HEIGHT_RELAXED = 1.75


# ═══════════════════════════════════════════════════════════════════════════════
#  BORDES
# ═══════════════════════════════════════════════════════════════════════════════

class Borders:
    """Sistema de bordes y border-radius."""
    RADIUS_NONE = 0
    RADIUS_SM = 4   # Elementos pequeños
    RADIUS_MD = 6   # Tooltips, badges
    RADIUS_LG = 8   # Botones, inputs (ESTÁNDAR)
    RADIUS_XL = 12  # Cards, modales
    RADIUS_FULL = 9999  # Circular
    
    # Grosores de borde
    THIN = 1
    NORMAL = 2
    THICK = 3


# ═══════════════════════════════════════════════════════════════════════════════
#  SOMBRAS
# ═══════════════════════════════════════════════════════════════════════════════

class Shadows:
    """Sistema de sombras para profundidad."""
    # Formato: offset-x offset-y blur spread color
    NONE = "none"
    
    # Modo claro
    SM_LIGHT = "0 1px 2px rgba(0, 0, 0, 0.05)"
    MD_LIGHT = "0 4px 6px rgba(0, 0, 0, 0.07), 0 2px 4px rgba(0, 0, 0, 0.06)"
    LG_LIGHT = "0 10px 15px rgba(0, 0, 0, 0.1), 0 4px 6px rgba(0, 0, 0, 0.05)"
    XL_LIGHT = "0 20px 25px rgba(0, 0, 0, 0.1), 0 10px 10px rgba(0, 0, 0, 0.04)"
    
    # Modo oscuro (más sutiles)
    SM_DARK = "0 1px 2px rgba(0, 0, 0, 0.2)"
    MD_DARK = "0 4px 6px rgba(0, 0, 0, 0.25), 0 2px 4px rgba(0, 0, 0, 0.2)"
    LG_DARK = "0 10px 15px rgba(0, 0, 0, 0.3), 0 4px 6px rgba(0, 0, 0, 0.2)"
    XL_DARK = "0 20px 25px rgba(0, 0, 0, 0.35), 0 10px 10px rgba(0, 0, 0, 0.25)"
    
    # Glow effects (para hover magenta)
    GLOW_PRIMARY = "0 0 12px rgba(37, 99, 235, 0.4)"
    GLOW_MAGENTA = "0 0 12px rgba(230, 0, 230, 0.4)"
    GLOW_SUCCESS = "0 0 12px rgba(22, 163, 74, 0.4)"
    GLOW_DANGER = "0 0 12px rgba(220, 38, 38, 0.4)"


# ═══════════════════════════════════════════════════════════════════════════════
#  TRANSICIONES Y ANIMACIONES
# ═══════════════════════════════════════════════════════════════════════════════

class Transitions:
    """Duraciones y easing para transiciones."""
    FAST = "150ms"
    NORMAL = "200ms"
    SLOW = "300ms"
    
    EASING_IN = "ease-in"
    EASING_OUT = "ease-out"
    EASING_IN_OUT = "ease-in-out"
    EASING_LINEAR = "linear"
    
    # Propiedades comunes a animar
    COMMON_PROPS = "background-color, border-color, color, box-shadow, transform"


# ═══════════════════════════════════════════════════════════════════════════════
#  Z-INDEX
# ═══════════════════════════════════════════════════════════════════════════════

class ZIndex:
    """Sistema de capas z-index."""
    BASE = 0
    DROPDOWN = 10
    STICKY = 20
    MODAL_BACKDROP = 30
    MODAL = 40
    POPPER = 50
    TOOLTIP = 60
    TOAST = 70


# ═══════════════════════════════════════════════════════════════════════════════
#  BREAKPOINTS (para responsive si aplica)
# ═══════════════════════════════════════════════════════════════════════════════

class Breakpoints:
    """Breakpoints para diseño responsive."""
    SM = 640    # móviles grandes
    MD = 768    # tablets
    LG = 1024   # laptops
    XL = 1280   # desktops
    XXL = 1536  # pantallas grandes


# ═══════════════════════════════════════════════════════════════════════════════
#  ICONOS
# ═══════════════════════════════════════════════════════════════════════════════

class Icons:
    """Tamaños de iconos estándar."""
    XS = 14
    SM = 18
    MD = 20
    LG = 24
    XL = 32
    XXL = 48


# ═══════════════════════════════════════════════════════════════════════════════
#  COMPONENTES — Estilos predefinidos
# ═══════════════════════════════════════════════════════════════════════════════

class ComponentStyles:
    """Estilos predefinidos para componentes comunes."""
    
    # Botón estándar (22-26px height)
    BTN_HEIGHT = f"{Spacing.BTN_HEIGHT_MIN}px"
    BTN_PADDING = f"{Spacing.BTN_PADDING_Y}px {Spacing.BTN_PADDING_X}px"
    BTN_RADIUS = f"{Borders.RADIUS_LG}px"
    BTN_FONT_SIZE = Typography.SIZE_SM
    
    # Input estándar
    INPUT_HEIGHT = f"{Spacing.BTN_HEIGHT_MIN}px"
    INPUT_PADDING = f"{Spacing.BTN_PADDING_Y}px {Spacing.MD}px"
    INPUT_RADIUS = f"{Borders.RADIUS_LG}px"
    INPUT_FONT_SIZE = Typography.SIZE_SM
    
    # Card estándar
    CARD_RADIUS = f"{Borders.RADIUS_XL}px"
    CARD_PADDING = f"{Spacing.LG}px"
    
    # Tooltip estándar
    TOOLTIP_RADIUS = f"{Borders.RADIUS_MD}px"
    TOOLTIP_PADDING = f"{Spacing.XS}px {Spacing.SM}px"
    TOOLTIP_FONT_SIZE = Typography.SIZE_XS
    
    # Tabla estándar
    TABLE_CELL_PADDING = f"{Spacing.SM}px {Spacing.MD}px"
    TABLE_HEADER_BG = Colors.NEUTRAL.SLATE_100
    TABLE_ROW_HOVER = Colors.NEUTRAL.SLATE_50
    
    # Badge estándar
    BADGE_RADIUS = f"{Borders.RADIUS_FULL}px"
    BADGE_PADDING = f"{Spacing.XS}px {Spacing.SM}px"
    BADGE_FONT_SIZE = Typography.SIZE_XS


# ═══════════════════════════════════════════════════════════════════════════════
#  UTILIDADES
# ═══════════════════════════════════════════════════════════════════════════════

def get_color_variants(base_color: str) -> Dict[str, str]:
    """Genera variantes hover/active para un color base."""
    # Esto es simplificado - en producción usaría cálculos reales de color
    return {
        "base": base_color,
        "hover": base_color,  # Se calcularía más claro
        "active": base_color, # Se calcularía más oscuro
    }


def generate_shadow_string(offset_y: int = 4, blur: int = 6, alpha: float = 0.1) -> str:
    """Genera string de sombra CSS."""
    return f"0 {offset_y}px {blur}px rgba(0, 0, 0, {alpha})"


# Exportar todo para importación fácil
__all__ = [
    "Colors",
    "PrimaryColors",
    "SuccessColors", 
    "DangerColors",
    "WarningColors",
    "InfoColors",
    "AccentColors",
    "NeutralColors",
    "SidebarColors",
    "TooltipColors",
    "Spacing",
    "Typography",
    "Borders",
    "Shadows",
    "Transitions",
    "ZIndex",
    "Breakpoints",
    "Icons",
    "ComponentStyles",
]
