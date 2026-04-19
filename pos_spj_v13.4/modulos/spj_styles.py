# modulos/spj_styles.py — SPJ POS v13.4
"""
Sistema de estilos centralizado SPJ.
Funciones utilitarias para auto-styling y temas globales.

NOTA: Los colores ahora están centralizados en design_tokens.py
Este módulo solo proporciona funciones de utilidad para aplicar estilos.

USO:
    from modulos.spj_styles import apply_spj_buttons, apply_global_theme, apply_theme_dialogs
    
    # Auto-aplicar estilos a botones por keyword
    apply_spj_buttons(widget)
    
    # Aplicar tema global desde BD
    apply_global_theme(db_connection)
    
    # Aplicar tema a dialogs
    apply_theme_dialogs(dialog)
"""

from PyQt5.QtWidgets import QPushButton
from modulos.design_tokens import Colors

# ══════════════════════════════════════════════════════════════════════════════
#  Mapeo de variantes a colores centralizados (design_tokens.py)
# ══════════════════════════════════════════════════════════════════════════════

SPJ_COLORS = {
    "primary":   (Colors.PRIMARY_BASE, Colors.PRIMARY_HOVER),
    "success":   (Colors.SUCCESS_BASE, Colors.SUCCESS_HOVER),
    "danger":    (Colors.DANGER_BASE, Colors.DANGER_HOVER),
    "warning":   (Colors.WARNING_BASE, Colors.WARNING_HOVER),
    "secondary": (Colors.NEUTRAL.SLATE_600, Colors.NEUTRAL.SLATE_500),
    "info":      (Colors.INFO_BASE, Colors.INFO_HOVER),
    "dark":      (Colors.NEUTRAL.SLATE_800, Colors.NEUTRAL.SLATE_700),
    "purple":    (Colors.ACCENT_BASE, Colors.ACCENT_HOVER),
}

# ══════════════════════════════════════════════════════════════════════════════
#  Button styling
# ══════════════════════════════════════════════════════════════════════════════

_BTN_BASE = (
    "QPushButton {{"
    "  background:{bg}; color:white; font-weight:bold;"
    "  padding:{pad}; border-radius:5px; border:none;"
    "}}"
    "QPushButton:hover {{"
    "  background:{hover};"
    "}}"
    "QPushButton:disabled {{"
    "  background:#bdc3c7; color:#7f8c8d;"
    "}}"
    "QPushButton:pressed {{"
    "  background:{hover}; padding-top:{pad_press}px;"
    "}}"
)

_PADDING = {
    "sm": ("2px 6px",  "4"),
    "md": ("3px 9px",  "5"),
    "lg": ("5px 13px", "7"),
}


def spj_btn(button: QPushButton, variant: str = "primary", size: str = "md") -> QPushButton:
    """Aplica el estilo estándar SPJ a un botón."""
    bg, hover = SPJ_COLORS.get(variant, SPJ_COLORS["primary"])
    pad, pad_press = _PADDING.get(size, _PADDING["md"])
    button.setStyleSheet(_BTN_BASE.format(bg=bg, hover=hover, pad=pad, pad_press=pad_press))
    return button


def spj_btn_icon(button: QPushButton, variant: str = "primary", size: str = "md") -> QPushButton:
    """Igual que spj_btn pero con padding balanceado para botones con ícono."""
    bg, hover = SPJ_COLORS.get(variant, SPJ_COLORS["primary"])
    pads = {"sm": "4px 8px", "md": "6px 14px", "lg": "9px 20px"}
    pad = pads.get(size, pads["md"])
    button.setStyleSheet(_BTN_BASE.format(bg=bg, hover=hover, pad=pad, pad_press="2"))
    return button


def apply_btn_styles(pairs: list) -> None:
    """Aplica estilos en lote. pairs: [(btn, variant), ...] o [(btn, variant, size), ...]"""
    for item in pairs:
        if len(item) == 2:
            spj_btn(item[0], item[1])
        else:
            spj_btn(item[0], item[1], item[2])


# ══════════════════════════════════════════════════════════════════════════════
#  Auto-styling by keyword (walk widget tree)
# ══════════════════════════════════════════════════════════════════════════════

_BTN_KEYWORDS = {
    "success":   ["guardar", "nuevo", "agregar", "crear", "confirmar", "aceptar",
                  "completar", "aplicar", "registrar", "procesar", "finalizar",
                  "recibir", "restaurar", "save", "add", "create"],
    "danger":    ["eliminar", "borrar", "cancelar", "rechazar", "quitar",
                  "limpiar", "anular", "bloquear", "delete", "remove", "cancel"],
    "warning":   ["editar", "modificar", "ajustar", "cambiar", "actualizar",
                  "corregir", "edit", "update", "modify"],
    "info":      ["ver", "detalle", "buscar", "filtrar", "reimprimir",
                  "probar", "test", "ping", "conectar", "view", "search",
                  "consultar", "analizar"],
    "primary":   ["cobrar", "nueva venta", "abrir caja", "iniciar",
                  "enviar", "imprimir", "abrir turno", "generar", "corte"],
    "secondary": ["cerrar", "salir", "volver", "regresar", "close", "exit", "back"],
    "purple":    ["reporte", "exportar", "analisis", "bi", "report", "export",
                  "muestra", "historial"],
}

_KW_MAP = {}
for _v, _kws in _BTN_KEYWORDS.items():
    for _kw in _kws:
        _KW_MAP[_kw] = _v


def _variant_for_text(text: str):
    """Determine button variant from its text label."""
    import re as _re
    t = _re.sub(r'[^\w\s]', ' ', text.lower()).strip()
    best_kw, best_v = "", None
    for kw, v in _KW_MAP.items():
        if kw in t and len(kw) > len(best_kw):
            best_kw, best_v = kw, v
    return best_v


def apply_spj_buttons(widget) -> None:
    """Walk widget tree and apply spj_btn() to all QPushButtons by keyword.
    Skips buttons that already have SPJ styling applied."""
    from PyQt5.QtWidgets import QPushButton
    for btn in widget.findChildren(QPushButton):
        existing = btn.styleSheet()
        # Skip if already styled by SPJ (has border-radius:5px and font-weight:bold)
        if "border-radius:5px" in existing and "font-weight:bold" in existing:
            continue
        # Skip very small buttons (icon-only, 30px wide action buttons)
        if btn.maximumWidth() <= 36 or btn.fixedSize().width() == 30:
            continue
        v = _variant_for_text(btn.text())
        if v:
            spj_btn(btn, v)


# ══════════════════════════════════════════════════════════════════════════════
#  Global theme
# ══════════════════════════════════════════════════════════════════════════════

SPJ_PANEL_STYLE = "background:#f8f9fa; border-radius:6px; padding:8px;"
SPJ_GROUP_STYLE = (
    "QGroupBox { font-weight:bold; border:1px solid #dee2e6;"
    " border-radius:6px; margin-top:8px; padding-top:8px; }"
    "QGroupBox::title { subcontrol-origin:margin; left:10px; color:#2c3e50; }"
)


def apply_theme_dialogs(dialog) -> None:
    """Apply active app theme to a QDialog/QWidget so backgrounds match."""
    from PyQt5.QtWidgets import QApplication
    import re as _re
    app = QApplication.instance()
    qss = app.styleSheet() if app else ""
    bg_m = _re.search(r'background-color:\s*([#\w]+)', qss)
    fg_m = _re.search(r'QMainWindow[^}]*\bcolor:\s*([#\w]+)', qss)
    bg = bg_m.group(1) if bg_m else "#f5f6fa"
    fg = fg_m.group(1) if fg_m else "#2c3e50"
    base = (
        "QDialog, QWidget { background-color:" + bg + "; color:" + fg + "; }"
        "QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {"
        " background-color:white; color:#2c3e50; border:1px solid #ccc;"
        " border-radius:3px; padding:3px; }"
        "QGroupBox { border:1px solid #dee2e6; border-radius:5px;"
        " margin-top:8px; padding-top:6px; }"
        "QGroupBox::title { color:" + fg + "; font-weight:bold; }"
        "QTableWidget { background:white; gridline-color:#e0e0e0; }"
        "QHeaderView::section { background:#f0f0f0; color:#2c3e50;"
        " border:none; font-weight:bold; padding:4px; }"
    )
    dialog.setStyleSheet(base)


def apply_global_theme(db_conn=None) -> None:
    """
    v13.5: Lee 'tema' de BD y aplica QSS a QApplication via theme_engine.
    Solo aplica — no escribe en BD.
    """
    try:
        from ui.themes.theme_engine import load_saved_theme
        load_saved_theme(None)
    except Exception as e:
        __import__("logging").getLogger("spj.styles").debug("apply_global_theme: %s", e)


# ══════════════════════════════════════════════════════════════════════════════
#  Tooltips obligatorios (Fase 1 — Plan Maestro SPJ v13.4)
# ══════════════════════════════════════════════════════════════════════════════

# Mapeo texto → tooltip descriptivo por keyword
_TOOLTIP_MAP = {
    "guardar":       "Guardar cambios",
    "nuevo":         "Crear nuevo registro",
    "agregar":       "Agregar elemento",
    "crear":         "Crear nuevo elemento",
    "confirmar":     "Confirmar operación",
    "aceptar":       "Aceptar y continuar",
    "eliminar":      "Eliminar permanentemente",
    "borrar":        "Borrar registro",
    "cancelar":      "Cancelar operación",
    "editar":        "Editar registro",
    "modificar":     "Modificar datos",
    "actualizar":    "Actualizar información",
    "buscar":        "Buscar en catálogo",
    "filtrar":       "Filtrar resultados",
    "imprimir":      "Enviar a impresora",
    "reimprimir":    "Reimprimir último documento",
    "exportar":      "Exportar a archivo",
    "reporte":       "Ver reporte",
    "cerrar":        "Cerrar ventana",
    "salir":         "Salir del módulo",
    "cobrar":        "Procesar pago",
    "nueva venta":   "Iniciar nueva venta",
    "abrir caja":    "Abrir turno de caja",
    "corte":         "Generar corte de caja",
    "generar":       "Generar documento",
    "enviar":        "Enviar información",
    "conectar":      "Probar conexión",
    "probar":        "Probar función",
    "analizar":      "Analizar datos",
}


def _tooltip_for_text(text: str) -> str:
    """Determina tooltip a partir del texto del botón."""
    import re
    t = re.sub(r'[^\w\s]', ' ', text.lower()).strip()
    best_kw, best_tip = "", ""
    for kw, tip in _TOOLTIP_MAP.items():
        if kw in t and len(kw) > len(best_kw):
            best_kw, best_tip = kw, tip
    return best_tip


def apply_object_names(widget) -> None:
    """
    Recorre todos los QPushButton del widget y asigna objectName según el texto,
    SOLO si el botón aún no tiene objectName asignado (es idempotente).

    Permite que el QSS global de TEMAS (QPushButton#primaryBtn, etc.) se aplique
    a botones creados con QPushButton() directo sin usar las factories de ui_components.

    Fase 1 — Plan Maestro: design tokens uniformes en todos los módulos.
    """
    from PyQt5.QtWidgets import QPushButton
    _NAMED = {"primaryBtn", "secondaryBtn", "successBtn", "dangerBtn",
              "warningBtn", "outlineBtn"}
    for btn in widget.findChildren(QPushButton):
        if btn.objectName() in _NAMED:
            continue  # Ya tiene objectName SPJ — no sobrescribir
        v = _variant_for_text(btn.text())
        if v:
            name_map = {
                "primary": "primaryBtn", "success": "successBtn",
                "danger": "dangerBtn", "warning": "warningBtn",
                "secondary": "secondaryBtn", "info": "primaryBtn",
                "purple": "outlineBtn",
            }
            btn.setObjectName(name_map.get(v, "secondaryBtn"))
        else:
            btn.setObjectName("secondaryBtn")  # Fallback seguro para botones sin keyword


def apply_spj_tooltips(widget) -> None:
    """
    Recorre todos los QPushButton del widget y asigna tooltips descriptivos
    basados en el texto del botón. Solo asigna si el botón no tiene tooltip.

    Fase 1 — Plan Maestro: tooltips obligatorios en UI.
    """
    from PyQt5.QtWidgets import QPushButton
    for btn in widget.findChildren(QPushButton):
        if btn.toolTip():
            continue  # Ya tiene tooltip
        tip = _tooltip_for_text(btn.text())
        if tip:
            btn.setToolTip(tip)


# ══════════════════════════════════════════════════════════════════════════════
#  Scrollbars uniformes (Fase 1 — Plan Maestro SPJ v13.4)
# ══════════════════════════════════════════════════════════════════════════════

SCROLLBAR_QSS = """
QScrollBar:vertical {
    background: #f0f0f0;
    width: 10px;
    margin: 0;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #b0b8c1;
    min-height: 30px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #0FB9B1;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    background: none;
}
QScrollBar:horizontal {
    background: #f0f0f0;
    height: 10px;
    margin: 0;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background: #b0b8c1;
    min-width: 30px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal:hover {
    background: #0FB9B1;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    background: none;
}
"""


def apply_scrollbars(widget) -> None:
    """
    Aplica el estilo uniforme de scrollbars a un widget.
    Fase 1 — Plan Maestro: scrollbars consistentes en toda la app.
    """
    existing = widget.styleSheet() or ""
    if "QScrollBar" not in existing:
        widget.setStyleSheet(existing + SCROLLBAR_QSS)
