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
    QComboBox, QProgressBar, QMessageBox, QTabWidget, QScrollArea, QSizePolicy, QDialog
)
from PyQt5.QtCore import Qt, QPoint, QTimer, QSize, pyqtSignal, QObject, QEvent
from PyQt5.QtGui import QFont, QPalette, QColor
import logging

from modulos.design_tokens import (
    Colors, Spacing, Typography, Borders, Shadows, ComponentStyles
)

logger = logging.getLogger("spj.ui_components")
_DIALOG_NORMALIZER = None


_GLOBAL_THEME_QSS = {
    "oscuro": f"""
        QWidget {{
            background-color: {Colors.NEUTRAL.DARK_BG};
            color: {Colors.NEUTRAL.DARK_TEXT};
        }}
        QFrame, QGroupBox {{
            background-color: {Colors.NEUTRAL.DARK_CARD};
            border: 1px solid {Colors.NEUTRAL.DARK_BORDER};
            border-radius: {Borders.RADIUS_LG}px;
        }}
        QPushButton#primaryBtn, QPushButton#successBtn, QPushButton#dangerBtn,
        QPushButton#secondaryBtn, QPushButton#warningBtn, QPushButton#outlineBtn {{
            min-height: {Spacing.BTN_HEIGHT_MIN}px;
            border-radius: {Borders.RADIUS_MD}px;
            padding: 6px 12px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
        }}
        QTabWidget::pane {{
            border: 1px solid {Colors.NEUTRAL.DARK_BORDER};
            border-radius: {Borders.RADIUS_LG}px;
            top: -1px;
        }}
        QTabBar::tab {{
            background: {Colors.NEUTRAL.SLATE_700};
            color: {Colors.NEUTRAL.SLATE_200};
            padding: 8px 14px;
            margin-right: 4px;
            border-top-left-radius: {Borders.RADIUS_MD}px;
            border-top-right-radius: {Borders.RADIUS_MD}px;
        }}
        QTabBar::tab:selected {{
            background: {Colors.PRIMARY.BASE};
            color: {Colors.NEUTRAL.WHITE};
        }}
    """,
    "claro": f"""
        QWidget {{
            background-color: #F8FAFC;
            color: #0F172A;
        }}
        QFrame, QGroupBox {{
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: {Borders.RADIUS_LG}px;
        }}
        QPushButton#primaryBtn, QPushButton#successBtn, QPushButton#dangerBtn,
        QPushButton#secondaryBtn, QPushButton#warningBtn, QPushButton#outlineBtn {{
            min-height: {Spacing.BTN_HEIGHT_MIN}px;
            border-radius: {Borders.RADIUS_MD}px;
            padding: 6px 12px;
            font-weight: {Typography.WEIGHT_SEMIBOLD};
        }}
        QTabWidget::pane {{
            border: 1px solid #CBD5E1;
            border-radius: {Borders.RADIUS_LG}px;
            top: -1px;
        }}
        QTabBar::tab {{
            background: #E2E8F0;
            color: #334155;
            padding: 8px 14px;
            margin-right: 4px;
            border-top-left-radius: {Borders.RADIUS_MD}px;
            border-top-right-radius: {Borders.RADIUS_MD}px;
        }}
        QTabBar::tab:selected {{
            background: #2563EB;
            color: #FFFFFF;
        }}
    """,
}


# ═══════════════════════════════════════════════════════════════════════════════
#  BOTONES
# ═══════════════════════════════════════════════════════════════════════════════

def _configure_button(btn: QPushButton, variant: str = "primary") -> QPushButton:
    """Configura un botón con estilos estándar según variante."""
    btn.setFixedHeight(Spacing.BTN_HEIGHT_MIN)
    btn.setCursor(Qt.PointingHandCursor)
    # Evitar botones que se expanden a todo el ancho en layouts verticales.
    btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    
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

    # Caso legacy: se pasa un QPushButton ya creado en "text".
    if isinstance(text, QPushButton):
        btn = text
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

def create_input_field(parent=None, placeholder: str = "", tooltip: str = None,
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


def create_combo(parent=None, items: list = None, placeholder: str = "", tooltip: str = None,
                 min_width: int = None, max_width: int = None,
                 fixed_width: int = None, editable: bool = False, **_ignored) -> QComboBox:
    """Crea un ComboBox estandarizado."""
    from PyQt5.QtWidgets import QComboBox
    
    combo = QComboBox(parent)
    combo.setFixedHeight(Spacing.BTN_HEIGHT_MIN)
    combo.setObjectName("standardInput")
    
    if items and combo is not None:
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
    card.setFixedHeight(48)
    
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
    badge.setMinimumHeight(16)
    
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
        color: {Colors.NEUTRAL.DARK_TEXT};
        font-size: {Typography.SIZE_XL};
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
        color: {Colors.NEUTRAL.DARK_TEXT_SEC};
        font-size: {Typography.SIZE_MD};
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
    table.verticalHeader().setDefaultSectionSize(22)
    
    # Scrollbars
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
    
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
            min-height: 20px;
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
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    return table


def create_standard_tabs(parent=None) -> QTabWidget:
    """Crea tabs estandarizados para dividir pantallas cargadas."""
    tabs = QTabWidget(parent)
    tabs.setObjectName("standardTabs")
    tabs.setUsesScrollButtons(True)
    tabs.setDocumentMode(True)
    tabs.setElideMode(Qt.ElideRight)
    return tabs


def wrap_in_scroll_area(widget: QWidget, parent=None) -> QScrollArea:
    """Envuelve un widget en QScrollArea para formularios/tablas extensas."""
    area = QScrollArea(parent)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    area.setWidget(widget)
    return area


def get_global_theme_qss(theme: str = "oscuro") -> str:
    """Retorna QSS global base para tema claro/oscuro."""
    key = (theme or "oscuro").strip().lower()
    return _GLOBAL_THEME_QSS.get(key, _GLOBAL_THEME_QSS["oscuro"])


def apply_global_theme(app_or_widget, theme: str = "oscuro") -> bool:
    """Aplica el tema global base a QApplication y opcionalmente a un widget."""
    qss = get_global_theme_qss(theme)
    if not qss:
        return False
    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(qss)
        if app_or_widget is not None and hasattr(app_or_widget, "setStyleSheet"):
            app_or_widget.setStyleSheet(qss)
        return True
    except Exception:
        return False


class _DialogButtonNormalizer(QObject):
    """Normaliza políticas de tamaño de botones al mostrarse cualquier diálogo."""

    def eventFilter(self, obj, event):
        if isinstance(obj, QDialog) and event.type() == QEvent.Show:
            try:
                for btn in obj.findChildren(QPushButton):
                    if btn.minimumWidth() and btn.minimumWidth() <= 45:
                        continue
                    btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                    if btn.minimumHeight() < 32:
                        btn.setMinimumHeight(32)
            except Exception:
                pass
        return super().eventFilter(obj, event)


def install_dialog_button_normalizer(app=None) -> bool:
    """
    Instala un event filter global para evitar botones full-width en QDialog
    de todos los módulos sin tocar cada diálogo individual.
    """
    global _DIALOG_NORMALIZER
    try:
        from PyQt5.QtWidgets import QApplication
        target = app or QApplication.instance()
        if target is None:
            return False
        if _DIALOG_NORMALIZER is None:
            _DIALOG_NORMALIZER = _DialogButtonNormalizer(target)
            target.installEventFilter(_DIALOG_NORMALIZER)
        return True
    except Exception:
        return False


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
    btn.setFixedHeight(18)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    
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
#  COMPONENTES AVANZADOS (UI/UX POS)
# ═══════════════════════════════════════════════════════════════════════════════


class EmptyStateWidget(QFrame):
    """Estado vacío reutilizable para tablas, listas y dashboards."""

    def __init__(self, title: str = "Sin información", message: str = "No hay datos para mostrar.",
                 icon: str = "📭", parent=None):
        super().__init__(parent)
        self.setObjectName("emptyState")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 24, 20, 24)
        lay.setSpacing(6)

        lbl_icon = QLabel(icon)
        lbl_icon.setAlignment(Qt.AlignCenter)
        lbl_icon.setStyleSheet("font-size: 26px;")

        self.lbl_title = QLabel(title)
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setStyleSheet("font-weight: 700; font-size: 14px;")

        self.lbl_message = QLabel(message)
        self.lbl_message.setWordWrap(True)
        self.lbl_message.setAlignment(Qt.AlignCenter)
        self.lbl_message.setStyleSheet("color: #64748B; font-size: 12px;")

        lay.addWidget(lbl_icon)
        lay.addWidget(self.lbl_title)
        lay.addWidget(self.lbl_message)


class LoadingIndicator(QFrame):
    """Indicador de carga liviano para operaciones de refresh en dashboards."""

    def __init__(self, message: str = "Cargando…", parent=None):
        super().__init__(parent)
        self.setObjectName("loadingIndicator")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        self.progress.setFixedWidth(140)
        self.progress.setTextVisible(False)

        self.lbl = QLabel(message)
        self.lbl.setStyleSheet("color: #64748B; font-size: 12px;")

        lay.addWidget(self.progress)
        lay.addWidget(self.lbl)
        lay.addStretch()

    def set_message(self, message: str) -> None:
        self.lbl.setText(message)


class FilterBar(QFrame):
    """Barra de filtros reutilizable: búsqueda + filtros rápidos + limpiar."""

    filters_changed = pyqtSignal(dict)

    def __init__(self, parent=None, placeholder: str = "Buscar…", combo_filters: dict | None = None):
        super().__init__(parent)
        self.setObjectName("filterBar")
        self._combos = {}

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)

        self.search = create_input_field(self, placeholder=placeholder)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._emit_filters)
        lay.addWidget(self.search, 2)

        for key, options in (combo_filters or {}).items():
            cmb = create_combo(self, items=["Todos"] + list(options))
            cmb.currentTextChanged.connect(self._emit_filters)
            cmb.setMinimumWidth(140)
            self._combos[key] = cmb
            lay.addWidget(cmb, 1)

        self.btn_clear = create_outline_button(self, "Limpiar")
        self.btn_clear.clicked.connect(self.clear)
        lay.addWidget(self.btn_clear)

    def clear(self) -> None:
        self.search.clear()
        for cmb in self._combos.values():
            cmb.setCurrentIndex(0)
        self._emit_filters()

    def values(self) -> dict:
        payload = {"search": self.search.text().strip()}
        for key, cmb in self._combos.items():
            value = cmb.currentText().strip()
            payload[key] = "" if value.lower() == "todos" else value
        return payload

    def _emit_filters(self, *_args) -> None:
        self.filters_changed.emit(self.values())


def confirm_action(parent, title: str, message: str,
                   confirm_text: str = "Confirmar", cancel_text: str = "Cancelar") -> bool:
    """Diálogo estándar para acciones críticas (no destructivas irreversibles)."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle(title)
    box.setText(message)
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    yes_btn = box.button(QMessageBox.Yes)
    no_btn = box.button(QMessageBox.No)
    if yes_btn:
        yes_btn.setText(confirm_text)
    if no_btn:
        no_btn.setText(cancel_text)
    return box.exec_() == QMessageBox.Yes


class DataTableWithFilters(QWidget):
    """Tabla reutilizable con barra de filtros, loading y estado vacío."""

    def __init__(self, headers: list[str], parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.filter_bar = FilterBar(self, placeholder="Filtrar en tabla…")
        lay.addWidget(self.filter_bar)

        self.loading = LoadingIndicator("Cargando tabla…", self)
        self.loading.hide()
        lay.addWidget(self.loading)

        self.table = QTableWidget(self)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.table, 1)

        self.empty_state = EmptyStateWidget("Sin resultados", "Ajusta los filtros para continuar.", "🔎", self)
        self.empty_state.hide()
        lay.addWidget(self.empty_state)

        self.filter_bar.filters_changed.connect(self._apply_filter)

    def set_loading(self, loading: bool, message: str = "Cargando tabla…") -> None:
        self.loading.set_message(message)
        self.loading.setVisible(loading)

    def _apply_filter(self, payload: dict) -> None:
        search = (payload or {}).get("search", "").lower().strip()
        visible_rows = 0
        for row in range(self.table.rowCount()):
            visible = True
            if search:
                row_text = " | ".join(
                    (self.table.item(row, col).text() if self.table.item(row, col) else "")
                    for col in range(self.table.columnCount())
                ).lower()
                visible = search in row_text
            self.table.setRowHidden(row, not visible)
            if visible:
                visible_rows += 1
        self.empty_state.setVisible(self.table.rowCount() == 0 or visible_rows == 0)


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
    "create_input",
    "create_combo",
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
    # Tablas
    "create_table",
    "create_table_with_columns",
    "create_table_button",
    "create_standard_tabs",
    "wrap_in_scroll_area",
    # Componentes avanzados
    "EmptyStateWidget",
    "LoadingIndicator",
    "FilterBar",
    "DataTableWithFilters",
    "confirm_action",
    # Tema global
    "get_global_theme_qss",
    "apply_global_theme",
    "install_dialog_button_normalizer",
]
