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
    "sm": ("4px 10px",  "6"),
    "md": ("7px 16px",  "9"),
    "lg": ("10px 22px", "12"),
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
    v13.4: Lee 'tema' de BD y aplica QSS a QApplication.
    Primero intenta ThemeService; si falla, usa theme_engine.
    No modifica tamaño de iconos ni botones — solo colores.
    """
    from PyQt5.QtWidgets import QApplication
    _log = __import__("logging").getLogger("spj.styles")

    tema = "Light"
    if db_conn:
        try:
            row = db_conn.execute(
                "SELECT valor FROM configuraciones WHERE clave='tema'"
            ).fetchone()
            if row and row[0]:
                tema = str(row[0])
                if 'dark' in tema.lower():
                    tema = "Dark"
        except Exception:
            pass

    # Intento 1: ThemeService (puede generar QSS richer)
    try:
        from core.services.theme_service import ThemeService
        ts = ThemeService(db_conn)
        ts.save_preferences(theme=tema, density="Normal",
                            font_size="12", icon_size="24")
        qss = ts.generate_qss()
        app = QApplication.instance()
        if app and qss:
            app.setStyleSheet(qss)
            return
    except Exception as e:
        _log.debug("ThemeService no disponible, usando theme_engine: %s", e)

    # Intento 2: theme_engine (fuente de verdad config.TEMAS)
    try:
        from ui.themes.theme_engine import load_saved_theme
        load_saved_theme(None)
    except Exception as e:
        _log.debug("apply_global_theme: %s", e)
