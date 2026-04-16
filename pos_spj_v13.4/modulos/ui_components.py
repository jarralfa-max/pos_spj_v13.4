# modulos/ui_components.py — SPJ POS v13.4
"""
Sistema de componentes UI reutilizables para SPJ POS.
Proporciona funciones factory para crear componentes estandarizados.

USO:
    from modulos.ui_components import (
        create_primary_button,
        create_input_field,
        create_card,
        create_badge,
        apply_tooltip,
    )
    
    # Crear botón primario con tooltip
    btn = create_primary_button(parent, "Guardar", "Guardar cambios del pedido")
    
    # Crear input con label y tooltip
    input_field = create_input_field(parent, "Nombre del cliente", "Ingrese el nombre completo")
    
    # Crear card contenedora (con layout por defecto)
    card = create_card(parent, with_layout=True)
    
    # Crear badge de estado
    badge = create_badge(parent, "Completado", "success")
"""

from PyQt5.QtWidgets import (
    QPushButton, QLineEdit, QFrame, QLabel, QVBoxLayout, 
    QHBoxLayout, QWidget, QToolTip, QGraphicsDropShadowEffect,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QComboBox
)
from PyQt5.QtCore import Qt, QPoint, QTimer, QSize
from PyQt5.QtGui import QFont, QPalette, QColor
import logging

from modulos.design_tokens import (
    Colors, Spacing, Typography, Borders, Shadows, ComponentStyles
)

logger = logging.getLogger("spj.ui_components")


# ═══════════════════════════════════════════════════════════════════════════════
#  BOTONES
# ═══════════════════════════════════════════════════════════════════════════════

def _configure_button(btn: QPushButton, variant: str = "primary") -> QPushButton:
    """Configura un botón con estilos estándar según variante."""
    btn.setFixedHeight(Spacing.BTN_HEIGHT_MIN)
    btn.setCursor(Qt.PointingHandCursor)
    
    # Asignar objectName para usar estilos CSS globales de config.py
    variant_map = {
        "primary": "primaryBtn",
        "secondary": "secondaryBtn",
        "success": "successBtn",
        "danger": "dangerBtn",
        "warning": "warningBtn",
        "outline": "outlineBtn",
    }
    
    object_name = variant_map.get(variant, "primaryBtn")
    btn.setObjectName(object_name)
    
    return btn


def _normalize_button_call(parent=None, text: str = "", tooltip: str = None):
    """
    Compatibilidad de firma:
      - create_xxx_button(parent, text, tooltip)
      - create_xxx_button(text, parent, tooltip)
      - create_xxx_button(existing_qpushbutton, text?, tooltip?)
    """
    if isinstance(parent, QPushButton):
        btn = parent
        if isinstance(text, str) and text:
            btn.setText(text)
        return btn, tooltip, True

    if isinstance(parent, str) and (text is None or isinstance(text, QWidget)):
        parent, text = text, parent

    text = text or ""
    if not isinstance(text, str):
        text = str(text)
    if not isinstance(parent, QWidget):
        parent = None
    btn = QPushButton(text, parent)
    return btn, tooltip, False


def create_primary_button(parent=None, text: str = "", tooltip: str = None) -> QPushButton:
    """Crea un botón primario (azul) para acciones principales."""
    btn, tooltip, _ = _normalize_button_call(parent, text, tooltip)
    btn = _configure_button(btn, "primary")
    if tooltip:
        apply_tooltip(btn, tooltip)
    return btn


def create_secondary_button(parent=None, text: str = "", tooltip: str = None) -> QPushButton:
    """Crea un botón secundario (gris) para acciones secundarias."""
    btn, tooltip, _ = _normalize_button_call(parent, text, tooltip)
    btn = _configure_button(btn, "secondary")
    if tooltip:
        apply_tooltip(btn, tooltip)
    return btn


def create_success_button(parent=None, text: str = "", tooltip: str = None) -> QPushButton:
    """Crea un botón de éxito (verde) para guardar/confirmar."""
    btn, tooltip, _ = _normalize_button_call(parent, text, tooltip)
    btn = _configure_button(btn, "success")
    if tooltip:
        apply_tooltip(btn, tooltip)
    return btn


def create_danger_button(parent=None, text: str = "", tooltip: str = None) -> QPushButton:
    """Crea un botón de peligro (rojo) para eliminar/cancelar."""
    btn, tooltip, _ = _normalize_button_call(parent, text, tooltip)
    btn = _configure_button(btn, "danger")
    if tooltip:
        apply_tooltip(btn, tooltip)
    return btn


def create_warning_button(parent=None, text: str = "", tooltip: str = None) -> QPushButton:
    """Crea un botón de advertencia (ámbar) para editar/ajustar."""
    btn, tooltip, _ = _normalize_button_call(parent, text, tooltip)
    btn = _configure_button(btn, "warning")
    if tooltip:
        apply_tooltip(btn, tooltip)
    return btn


def create_accent_button(parent=None, text: str = "", tooltip: str = None) -> QPushButton:
    """
    Botón accent para compatibilidad legacy.
    Actualmente reutiliza variante `primary`.
    """
    btn, tooltip, _ = _normalize_button_call(parent, text, tooltip)
    btn = _configure_button(btn, "primary")
    if tooltip:
        apply_tooltip(btn, tooltip)
    return btn


def create_outline_button(parent=None, text: str = "", tooltip: str = None) -> QPushButton:
    """Crea un botón outline (borde) para acciones menos prominentes."""
    btn, tooltip, _ = _normalize_button_call(parent, text, tooltip)
    btn = _configure_button(btn, "outline")
    if tooltip:
        apply_tooltip(btn, tooltip)
    return btn


def create_icon_button(parent, icon_path: str, tooltip: str, variant: str = "secondary") -> QPushButton:
    """Crea un botón solo con ícono."""
    btn = QPushButton(parent)
    btn.setFixedSize(36, 36)  # Tamaño cuadrado estándar
    btn = _configure_button(btn, variant)
    
    if icon_path:
        from PyQt5.QtGui import QIcon
        btn.setIcon(QIcon(icon_path))
        btn.setIconSize(QSize(18, 18))
    
    apply_tooltip(btn, tooltip)
    return btn


# ═══════════════════════════════════════════════════════════════════════════════
#  INPUTS
# ═══════════════════════════════════════════════════════════════════════════════

def create_input_field(parent, placeholder: str = "", tooltip: str = None,
                       min_width: int = None, max_width: int = None,
                       fixed_width: int = None, **_ignored) -> QLineEdit:
    """Crea un input field estandarizado."""
    input_field = QLineEdit(parent)
    input_field.setFixedHeight(Spacing.BTN_HEIGHT_MIN)
    input_field.setPlaceholderText(placeholder)
    
    # Asignar objectName para estilos CSS
    input_field.setObjectName("standardInput")
    
    if tooltip:
        apply_tooltip(input_field, tooltip)
    if fixed_width:
        input_field.setFixedWidth(int(fixed_width))
    else:
        if min_width:
            input_field.setMinimumWidth(int(min_width))
        if max_width:
            input_field.setMaximumWidth(int(max_width))
    
    return input_field


# Alias para compatibilidad con código legacy
create_input = create_input_field


def create_combo(parent, items: list = None, placeholder: str = "", tooltip: str = None,
                 min_width: int = None, max_width: int = None,
                 fixed_width: int = None, editable: bool = False, **_ignored) -> QComboBox:
    """Crea un ComboBox estandarizado."""
    from PyQt5.QtWidgets import QComboBox
    
    combo = QComboBox(parent)
    combo.setFixedHeight(Spacing.BTN_HEIGHT_MIN)
    combo.setObjectName("standardInput")
    
    if items:
        combo.addItems(items)
    
    if placeholder:
        combo.addItem(placeholder)
        combo.setCurrentIndex(-1)
    combo.setEditable(bool(editable))
    
    if tooltip:
        apply_tooltip(combo, tooltip)
    if fixed_width:
        combo.setFixedWidth(int(fixed_width))
    else:
        if min_width:
            combo.setMinimumWidth(int(min_width))
        if max_width:
            combo.setMaximumWidth(int(max_width))
    
    return combo


def create_labeled_input(parent, label_text: str, placeholder: str = "", 
                         tooltip: str = None, required: bool = False) -> QWidget:
    """Crea un input con label encima."""
    container = QWidget(parent)
    layout = QVBoxLayout(container)
    layout.setSpacing(Spacing.XS)
    layout.setContentsMargins(0, 0, 0, 0)
    
    # Label
    label = QLabel(label_text, container)
    label.setFont(QFont(Typography.FONT_FAMILY, 12, QFont.Medium))
    if required:
        label.setText(f"{label_text} *")
        label.setStyleSheet(f"color: {Colors.DANGER.BASE}; font-weight: 600;")
    else:
        label.setStyleSheet(f"color: {Colors.NEUTRAL.SLATE_700}; font-weight: 500;")
    
    # Input
    input_field = create_input_field(container, placeholder, tooltip)
    
    layout.addWidget(label)
    layout.addWidget(input_field)
    
    return container


# ═══════════════════════════════════════════════════════════════════════════════
#  CARDS
# ═══════════════════════════════════════════════════════════════════════════════

def create_card(parent, padding: int = Spacing.LG, with_layout: bool = True, 
                layout_type: str = "vertical") -> QFrame:
    """
    Crea una card contenedora con sombra suave.
    
    Args:
        parent: Widget padre
        padding: Espacio interno en píxeles
        with_layout: Si True (default), crea un layout interno. 
                     Si False, el caller debe agregar su propio layout.
        layout_type: Tipo de layout a crear si with_layout=True. 
                     Valores: "vertical" (QVBoxLayout), "horizontal" (QHBoxLayout)
    
    Returns:
        QFrame configurado como card
    """
    card = QFrame(parent)
    card.setObjectName("card")
    card.setFrameStyle(QFrame.StyledPanel)
    
    if with_layout:
        # Seleccionar tipo de layout según parámetro
        if layout_type == "horizontal":
            layout = QHBoxLayout(card)
        else:
            layout = QVBoxLayout(card)
        layout.setSpacing(Spacing.MD)
        layout.setContentsMargins(padding, padding, padding, padding)
    
    return card


def create_stat_card(parent, title: str, value: str, icon_path: str = None,
                     color_variant: str = "primary") -> QFrame:
    """
    Crea una card de estadística para dashboards.
    Fondo neutro con indicador de color en ícono/borde.
    
    Args:
        parent: Widget padre
        title: Título de la estadística
        value: Valor a mostrar
        icon_path: Ruta al ícono (opcional)
        color_variant: Variante de color (primary, success, danger, warning)
    
    Returns:
        QFrame configurado como stat card
    """
    # CORRECCIÓN CRÍTICA: with_layout=False porque vamos a usar QHBoxLayout personalizado
    card = create_card(parent, padding=Spacing.MD, with_layout=False)
    card.setFixedHeight(80)  # Height reducido
    
    layout = QHBoxLayout(card)
    layout.setSpacing(Spacing.MD)
    
    # Ícono (si existe)
    if icon_path:
        from PyQt5.QtGui import QPixmap
        
        icon_label = QLabel()
        icon_label.setFixedSize(40, 40)
        pixmap = QPixmap(icon_path).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon_label.setPixmap(pixmap)
        
        # Color del ícono según variante
        color_map = {
            "primary": Colors.PRIMARY.BASE,
            "success": Colors.SUCCESS.BASE,
            "danger": Colors.DANGER.BASE,
            "warning": Colors.WARNING.BASE,
        }
        # Aplicar tinte al ícono (simplificado)
        icon_label.setStyleSheet(f"background-color: {color_map.get(color_variant, Colors.PRIMARY.BASE)}20; border-radius: 8px;")
        
        layout.addWidget(icon_label)
    
    # Texto
    text_layout = QVBoxLayout()
    text_layout.setSpacing(Spacing.XS)
    
    # Título
    title_label = QLabel(title)
    title_label.setStyleSheet(f"color: {Colors.NEUTRAL.SLATE_500}; font-size: {Typography.SIZE_XS}; font-weight: 500;")
    text_layout.addWidget(title_label)
    
    # Valor
    value_label = QLabel(value)
    value_label.setStyleSheet(f"color: {Colors.NEUTRAL.SLATE_900}; font-size: {Typography.SIZE_XL}; font-weight: 700;")
    text_layout.addWidget(value_label)
    
    layout.addLayout(text_layout)
    layout.addStretch()
    
    return card


# ═══════════════════════════════════════════════════════════════════════════════
#  BADGES
# ═══════════════════════════════════════════════════════════════════════════════

def create_badge(parent, text: str, variant: str = "primary") -> QLabel:
    """
    Crea un badge/pill de estado.
    Variantes: primary, success, danger, warning, info, neutral
    """
    badge = QLabel(text, parent)
    badge.setAlignment(Qt.AlignCenter)
    
    # Colores según variante
    color_map = {
        "primary": (Colors.PRIMARY.BASE, Colors.PRIMARY.LIGHT),
        "success": (Colors.SUCCESS.BASE, Colors.SUCCESS.BG_SOFT),
        "danger": (Colors.DANGER.BASE, Colors.DANGER.BG_SOFT),
        "warning": (Colors.WARNING.BASE, Colors.WARNING.BG_SOFT),
        "info": (Colors.INFO.BASE, Colors.INFO.BG_SOFT),
        "neutral": (Colors.NEUTRAL.SLATE_600, Colors.NEUTRAL.SLATE_100),
    }
    
    text_color, bg_color = color_map.get(variant, color_map["primary"])
    
    badge.setStyleSheet(f"""
        background-color: {bg_color};
        color: {text_color};
        border-radius: {Borders.RADIUS_FULL}px;
        padding: {Spacing.XS}px {Spacing.SM}px;
        font-size: {Typography.SIZE_XS};
        font-weight: 600;
    """)
    
    # Size mínimo
    badge.setMinimumHeight(24)
    
    return badge


# ═══════════════════════════════════════════════════════════════════════════════
#  TOOLTIPS
# ═══════════════════════════════════════════════════════════════════════════════

def apply_tooltip(widget, text: str, delay_ms: int = 300):
    """
    Aplica un tooltip global estilizado a cualquier widget.
    El tooltip aparece en hover después del delay especificado.
    """
    if not text:
        return
    
    widget.setToolTip(text)
    
    # Configurar estilo del tooltip (se aplica globalmente desde config.py)
    # El QSS ya define QToolTip con colores correctos según tema
    
    # Opcional: agregar timer para control más fino del delay
    if hasattr(widget, '_tooltip_timer'):
        return
    
    widget._tooltip_timer = QTimer(widget)
    widget._tooltip_timer.setSingleShot(True)
    widget._tooltip_timer.setInterval(delay_ms)
    
    original_enter = widget.enterEvent
    original_leave = widget.leaveEvent
    
    def enter_event(e):
        widget._tooltip_timer.start()
        if original_enter:
            original_enter(e)
    
    def leave_event(e):
        widget._tooltip_timer.stop()
        QToolTip.hideText()
        if original_leave:
            original_leave(e)
    
    widget.enterEvent = enter_event
    widget.leaveEvent = leave_event


# ═══════════════════════════════════════════════════════════════════════════════
#  SEPARADORES
# ═══════════════════════════════════════════════════════════════════════════════

def create_divider(parent, orientation: str = "horizontal") -> QFrame:
    """Crea un separador/divisor."""
    divider = QFrame(parent)
    
    if orientation == "horizontal":
        divider.setFrameShape(QFrame.HLine)
        divider.setFixedHeight(1)
    else:
        divider.setFrameShape(QFrame.VLine)
        divider.setFixedWidth(1)
    
    divider.setObjectName("divider")
    return divider


# ═══════════════════════════════════════════════════════════════════════════════
#  LABELS CON JERARQUÍA
# ═══════════════════════════════════════════════════════════════════════════════

def create_heading(parent=None, text: str = "") -> QLabel:
    """Crea un label de título principal (24px bold)."""
    if isinstance(parent, str) and not text:
        parent, text = None, parent
    if text is None:
        text = ""
    if not isinstance(parent, QWidget):
        parent = None
    label = QLabel(text, parent)
    label.setStyleSheet(f"""
        color: {Colors.NEUTRAL.SLATE_900};
        font-size: {Typography.SIZE_XXL};
        font-weight: {Typography.WEIGHT_BOLD};
    """)
    return label


def create_heading_label(parent=None, text: str = "") -> QLabel:
    """Alias legacy de create_heading para módulos existentes."""
    return create_heading(parent, text)


def create_subheading(parent=None, text: str = "") -> QLabel:
    """Crea un label de subtítulo (16px semibold)."""
    if isinstance(parent, str) and not text:
        parent, text = None, parent
    if text is None:
        text = ""
    if not isinstance(parent, QWidget):
        parent = None
    label = QLabel(text, parent)
    label.setStyleSheet(f"""
        color: {Colors.NEUTRAL.SLATE_700};
        font-size: {Typography.SIZE_LG};
        font-weight: {Typography.WEIGHT_SEMIBOLD};
    """)
    return label


def create_caption(parent=None, text: str = "") -> QLabel:
    """Crea un label de caption/texto secundario (11px)."""
    if isinstance(parent, str) and not text:
        parent, text = None, parent
    if text is None:
        text = ""
    if not isinstance(parent, QWidget):
        parent = None
    label = QLabel(text, parent)
    label.setStyleSheet(f"""
        color: {Colors.NEUTRAL.SLATE_500};
        font-size: {Typography.SIZE_XS};
    """)
    return label


def create_label(parent, text: str, variant: str = "body") -> QLabel:
    """
    Helper legacy para crear labels por variante.
    Variantes: heading, subheading, caption, body.
    """
    v = (variant or "body").strip().lower()
    if v == "heading":
        return create_heading(parent, text)
    if v == "subheading":
        return create_subheading(parent, text)
    if v == "caption":
        return create_caption(parent, text)

    label = QLabel(text, parent)
    label.setStyleSheet(f"""
        color: {Colors.NEUTRAL.SLATE_700};
        font-size: {Typography.SIZE_MD};
        font-weight: {Typography.WEIGHT_REGULAR};
    """)
    return label


# ═══════════════════════════════════════════════════════════════════════════════
#  CONTENEDORES
# ═══════════════════════════════════════════════════════════════════════════════

def create_section_container(parent, title: str = None) -> QFrame:
    """Crea un contenedor de sección con borde y padding."""
    container = QFrame(parent)
    container.setObjectName("sectionContainer")
    container.setFrameStyle(QFrame.StyledPanel)
    
    layout = QVBoxLayout(container)
    layout.setSpacing(Spacing.LG)
    layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
    
    if title:
        title_label = create_subheading(container, title)
        layout.addWidget(title_label)
    
    return container


# ═══════════════════════════════════════════════════════════════════════════════
#  TABLAS
# ═══════════════════════════════════════════════════════════════════════════════

def create_table(parent, show_grid: bool = False, alternating_colors: bool = True,
                 selection_behavior: str = "SelectRows", editable: bool = False) -> QTableWidget:
    """
    Crea una QTableWidget estandarizada con estilos consistentes.
    
    Args:
        parent: Widget padre
        show_grid: Mostrar líneas de grid (default: False)
        alternating_colors: Colores alternos en filas (default: True)
        selection_behavior: "SelectRows", "SelectItems", "NoSelection"
        editable: Si las celdas son editables (default: False)
    
    Returns:
        QTableWidget configurada con estilos estándar
    """
    table = QTableWidget(parent)
    table.setObjectName("standardTable")
    
    # Configuración básica
    table.setAlternatingRowColors(alternating_colors)
    table.setShowGrid(show_grid)
    
    # Comportamiento de selección
    selection_map = {
        "SelectRows": QAbstractItemView.SelectRows,
        "SelectItems": QAbstractItemView.SelectItems,
        "NoSelection": QAbstractItemView.NoSelection,
    }
    table.setSelectionBehavior(selection_map.get(selection_behavior, QAbstractItemView.SelectRows))
    table.setSelectionMode(QAbstractItemView.SingleSelection if selection_behavior != "SelectItems" else QAbstractItemView.ExtendedSelection)
    
    # Edición
    if not editable:
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    
    # Headers optimizados
    header = table.horizontalHeader()
    header.setStretchLastSection(True)
    header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    header.setMinimumSectionSize(80)
    header.setMaximumSectionSize(400)
    
    # Header vertical oculto por defecto
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(Spacing.BTN_HEIGHT_MIN + 8)  # Altura de fila consistente
    
    # Scrollbars
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    
    # Ajuste automático
    table.setSizeAdjustPolicy(QAbstractItemView.AdjustToContentsOnFirstShow)
    
    # Estilo CSS inline para garantizar consistencia
    table.setStyleSheet(f"""
        QTableWidget {{
            background-color: {Colors.NEUTRAL.DARK_CARD};
            color: {Colors.NEUTRAL.DARK_TEXT};
            gridline-color: {Colors.NEUTRAL.DARK_BORDER};
            border: 1px solid {Colors.NEUTRAL.DARK_BORDER};
            alternate-background-color: {Colors.NEUTRAL.DARK_BG};
            border-radius: {Borders.RADIUS_LG}px;
            font-size: {Typography.SIZE_SM};
        }}
        QTableWidget::item {{
            padding: {Spacing.SM}px {Spacing.MD}px;
            border-bottom: 1px solid {Colors.NEUTRAL.DARK_BORDER};
        }}
        QTableWidget::item:selected {{
            background-color: {Colors.PRIMARY.BASE};
            color: {Colors.NEUTRAL.WHITE};
        }}
        QTableWidget::item:hover {{
            background-color: {Colors.NEUTRAL.SLATE_700};
        }}
        QHeaderView::section {{
            background-color: {Colors.NEUTRAL.SLATE_700};
            color: {Colors.NEUTRAL.DARK_TEXT};
            border: none;
            border-bottom: 2px solid {Colors.NEUTRAL.SLATE_600};
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            padding: {Spacing.SM}px {Spacing.MD}px;
            text-transform: uppercase;
            font-size: {Typography.SIZE_XS};
            letter-spacing: 0.5px;
            min-height: 40px;
        }}
        QHeaderView::section:hover {{
            background-color: {Colors.NEUTRAL.SLATE_600};
        }}
    """)
    
    return table


def create_table_with_columns(parent, columns: list, 
                              show_grid: bool = False,
                              alternating_colors: bool = True) -> QTableWidget:
    """
    Crea una tabla con columnas predefinidas.
    
    Args:
        parent: Widget padre
        columns: Lista de nombres de columnas
        show_grid: Mostrar líneas de grid
        alternating_colors: Colores alternos
    
    Returns:
        QTableWidget con columnas configuradas
    """
    table = create_table(parent, show_grid, alternating_colors)
    table.setColumnCount(len(columns))
    table.setHorizontalHeaderLabels(columns)
    return table


# ═══════════════════════════════════════════════════════════════════════════════
#  BOTONES PARA TABLAS
# ═══════════════════════════════════════════════════════════════════════════════

def create_table_button(parent, text: str, tooltip: str, variant: str = "outline") -> QPushButton:
    """
    Crea un botón compacto para usar dentro de tablas (acciones por fila).
    Tamaño reducido para no romper el layout de la tabla.
    
    Args:
        parent: Widget padre
        text: Texto del botón (o ícono)
        tooltip: Tooltip al hover
        variant: Variante de color (outline, primary, danger, etc.)
    
    Returns:
        QPushButton compacto estilizado
    """
    btn = QPushButton(text, parent)
    btn.setFixedHeight(28)  # Más pequeño que el estándar 36px
    btn.setCursor(Qt.PointingHandCursor)
    
    # Mapeo de variantes
    variant_map = {
        "primary": "primaryBtn",
        "secondary": "secondaryBtn",
        "success": "successBtn",
        "danger": "dangerBtn",
        "warning": "warningBtn",
        "outline": "outlineBtn",
    }
    
    object_name = variant_map.get(variant, "outlineBtn")
    btn.setObjectName(object_name)
    
    # Estilo inline específico para botones de tabla
    btn.setStyleSheet(f"""
        QPushButton#{object_name} {{
            background-color: transparent;
            border: 1px solid {Colors.NEUTRAL.SLATE_600};
            border-radius: {Borders.RADIUS_MD}px;
            padding: {Spacing.XS}px {Spacing.SM}px;
            font-size: {Typography.SIZE_XS};
            font-weight: {Typography.WEIGHT_MEDIUM};
            color: {Colors.NEUTRAL.SLATE_300};
        }}
        QPushButton#{object_name}:hover {{
            background-color: {Colors.NEUTRAL.SLATE_700};
            border-color: {Colors.NEUTRAL.SLATE_500};
            color: {Colors.NEUTRAL.WHITE};
        }}
        QPushButton#{object_name}:pressed {{
            background-color: {Colors.NEUTRAL.SLATE_800};
        }}
    """)
    
    if tooltip:
        apply_tooltip(btn, tooltip)
    
    return btn


# ═══════════════════════════════════════════════════════════════════════════════
#  COMPATIBILIDAD DINÁMICA (IMPORTS LEGACY)
# ═══════════════════════════════════════════════════════════════════════════════
_LEGACY_WARNED = set()


def _resolve_legacy_factory(name: str):
    """Mapea helpers create_* legacy a factories existentes."""
    n = name.lower()
    if "button" in n:
        if "primary" in n:
            return create_primary_button
        if "success" in n:
            return create_success_button
        if "danger" in n:
            return create_danger_button
        if "warning" in n:
            return create_warning_button
        if "accent" in n:
            return create_accent_button
        if "outline" in n:
            return create_outline_button
        return create_secondary_button
    if "heading_label" in n:
        return create_heading_label
    if "heading" in n:
        return create_heading
    if "subheading" in n:
        return create_subheading
    if "caption" in n:
        return create_caption
    if "label" in n:
        return create_label
    if "input" in n:
        return create_input_field
    if "combo" in n:
        return create_combo
    if "card" in n:
        return create_card
    if "table_button" in n:
        return create_table_button
    if "table" in n:
        return create_table
    return None


def __getattr__(name: str):
    """
    Fallback para imports legacy:
      from modulos.ui_components import create_xxx
    """
    if not name.startswith("create_"):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    factory = _resolve_legacy_factory(name)
    if factory is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    if name not in _LEGACY_WARNED:
        logger.warning("ui_components alias dinámico: %s -> %s", name, factory.__name__)
        _LEGACY_WARNED.add(name)
    return factory


# Exportar todo
__all__ = [
    # Botones
    "create_primary_button",
    "create_secondary_button",
    "create_success_button",
    "create_danger_button",
    "create_warning_button",
    "create_accent_button",
    "create_outline_button",
    "create_icon_button",
    
    # Inputs
    "create_input_field",
    "create_input",  # Alias para compatibilidad
    "create_combo",  # Nuevo
    "create_labeled_input",
    
    # Cards
    "create_card",
    "create_stat_card",
    
    # Badges
    "create_badge",
    
    # Tooltips
    "apply_tooltip",
    
    # Separadores
    "create_divider",
    
    # Labels
    "create_heading",
    "create_heading_label",
    "create_subheading",
    "create_caption",
    "create_label",
    
    # Contenedores
    "create_section_container",
    
    # Tablas (NUEVO)
    "create_table",
    "create_table_with_columns",
    "create_table_button",
]
