# modulos/compras_pro.py — SPJ POS v13.4
"""
Compras a Proveedores.
  - Busca productos por nombre, código, barcode o ID
  - Carrito editable (doble clic = editar, botón = eliminar)
  - Alerta si el costo varía >20% respecto al histórico
  - Procesa recetas al ingresar insumos que tengan receta
  - Auto-refresca lista de productos via EventBus
"""
from __future__ import annotations

from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import (
    create_primary_button, create_success_button, create_secondary_button,
    create_danger_button, create_input, create_combo, create_card,
    create_heading, create_subheading, create_caption, apply_tooltip,
    FilterBar, LoadingIndicator, EmptyStateWidget, confirm_action,
    create_standard_tabs, wrap_in_scroll_area,
    PageHeader, Toast, create_badge, create_kpi_card,
)
from modulos.spj_styles import apply_spj_buttons
from modulos.spj_refresh_mixin import RefreshMixin
from core.services.auto_audit import audit_write
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout, QGroupBox, QFrame,
    QLabel, QComboBox, QLineEdit, QPushButton, QDoubleSpinBox, QSpinBox, QCompleter,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QMenu, QSizePolicy, QCheckBox, QListWidget, QListWidgetItem,
    QDialog, QInputDialog, QShortcut, QTextBrowser, QDateEdit, QFileDialog, QScrollArea,
    QPlainTextEdit,
)
from PyQt5.QtCore import Qt, QTimer, QThread, QStringListModel, QDate, pyqtSignal
from PyQt5.QtGui import QCursor, QKeySequence
from datetime import datetime
import json, logging, os, unicodedata

logger = logging.getLogger("spj.compras")

# ── Payment method constants ────────────────────────────────────────────────
_PAGO_ITEMS = [
    ("CONTADO (Efectivo)",         "CONTADO"),
    ("CREDITO (Cuentas por Pagar)", "CREDITO"),
    ("TRANSFERENCIA",               "TRANSFERENCIA"),
    ("CHEQUE",                      "CHEQUE"),
]

# Price variance threshold (%) that triggers audit alert
_PRICE_VARIANCE_THRESHOLD = 20.0
# History query row limit
_HIST_LIMIT = 500


_COLOR_PARCIAL  = Colors.ACCENT_BASE
_COLOR_NEUTRAL  = Colors.NEUTRAL.SLATE_500

# Mapping: estado_key → (badge_label, badge_variant)
# Variants match create_badge() palette: success|warning|info|danger|neutral|primary
_STATUS_CHIP_MAP: dict[str, tuple[str, str]] = {
    "completada": ("✔ Completada",  "success"),
    "completa":   ("✔ Completada",  "success"),
    "credito":    ("💳 Crédito",    "warning"),
    "pendiente":  ("⏳ Pendiente",  "info"),
    "cancelada":  ("✕ Cancelada",  "danger"),
    "parcial":    ("▶ Parcial",     "primary"),
}
_COND_CHIP_MAP: dict[str, tuple[str, str]] = {
    "liquidado": ("✓ Liquidado", "success"),
    "credito":   ("⏱ Crédito",  "warning"),
    "parcial":   ("◑ Parcial",   "info"),
}

# Draft purchase — persisted to user home so it survives restarts
_DRAFT_PATH = os.path.join(os.path.expanduser("~"), ".spj_compra_borrador.json")

# IVA rate for Mexico
_IVA_RATE = 0.16

# Roles that must not see monetary totals (cashiers, basic operators)
_ROLES_SIN_TOTALES: frozenset[str] = frozenset({
    "CAJERO", "BÁSICO", "BASIC", "CASHIER", "VENDEDOR",
})


class _PurchaseKPICard(QFrame):
    """KPI card for Compra Tradicional tab — mirrors _InvKPICard pattern."""

    def __init__(self, titulo, valor="—", icono="📦", variant="primary", parent=None):
        super().__init__(parent)
        _accent = {
            "primary": Colors.PRIMARY.BASE,
            "success": Colors.SUCCESS.BASE,
            "danger":  Colors.DANGER.BASE,
            "warning": Colors.WARNING.BASE,
            "info":    Colors.INFO.BASE,
        }.get(variant, Colors.PRIMARY.BASE)
        self.setObjectName("kpiCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(86)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        bar = QFrame(self)
        bar.setFixedHeight(3)
        bar.setStyleSheet(
            f"background: {_accent}; border: none;"
            f" border-top-left-radius: 12px; border-top-right-radius: 12px;"
        )
        outer.addWidget(bar)
        body = QHBoxLayout()
        body.setContentsMargins(14, 10, 14, 10)
        body.setSpacing(8)
        outer.addLayout(body)
        col = QVBoxLayout()
        col.setSpacing(2)
        lbl_t = QLabel(titulo.upper())
        lbl_t.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_500}; font-size: {Typography.SIZE_XS};"
            f" font-weight: {Typography.WEIGHT_SEMIBOLD}; letter-spacing: 0.08em;"
            f" background: transparent; border: none;"
        )
        col.addWidget(lbl_t)
        self.lbl_valor = QLabel(valor)
        self.lbl_valor.setObjectName("kpiValue")
        self.lbl_valor.setStyleSheet(
            f"font-size: 22px; font-weight: {Typography.WEIGHT_BOLD};"
            f" letter-spacing: -0.02em; background: transparent; border: none;"
        )
        col.addWidget(self.lbl_valor)
        body.addLayout(col, 1)
        lbl_icon = QLabel(icono)
        lbl_icon.setFixedSize(36, 36)
        lbl_icon.setAlignment(Qt.AlignCenter)
        lbl_icon.setStyleSheet(
            f"font-size: 18px; background: {_accent}1A;"
            f" border-radius: 18px; border: none;"
        )
        body.addWidget(lbl_icon, 0, alignment=Qt.AlignTop)

    def set_valor(self, v: str):
        self.lbl_valor.setText(v)


class PurchaseKpiBar(QFrame):
    """Componente Fase 3: barra KPI de Compras, hermana visual de Inventario."""


class PurchaseDocumentToolbar(QFrame):
    """Componente Fase 3: columna izquierda documental ERP."""


class PurchaseCapturePanel(QWidget):
    """Componente Fase 3: columna central de captura documental."""


class PurchaseProviderCard(QFrame):
    """Componente Fase 3: card de datos del proveedor."""


class PurchaseDocumentCard(QFrame):
    """Componente Fase 3: card de datos del documento."""


class PurchaseProductSearchCard(QFrame):
    """Componente Fase 3: card de búsqueda de producto."""


class PurchaseQuickProductsCard(QFrame):
    """Componente Fase 3: card de productos rápidos."""


class PurchaseItemsAndTotalsPanel(QFrame):
    """Componente Fase 3: columna derecha de partidas + totales."""


class PurchaseTotalsFooter(QFrame):
    """Componente Fase 3: bloque compacto de totales/pago."""


class PurchaseDynamicActionBar(QWidget):
    """Componente Fase 3: acción dinámica según estado documental."""


# ═══════════════════════════════════════════════════════════════════════════════
#  Helpers theme-aware — TODO el styling de la tab Tradicional pasa por aquí.
#  Apunta a los tokens DARK del design system (Colors.NEUTRAL.DARK_*) para que
#  coincida con el HTML de referencia. Si la app conmuta a light mode, sólo
#  redefines estos 8 alias y todo el módulo se reorganiza — no hay px ni #hex
#  literales en los _build_*.
# ═══════════════════════════════════════════════════════════════════════════════

_C_PAGE_BG      = Colors.NEUTRAL.SLATE_950        # fondo página (más oscuro)
_C_CARD_BG      = Colors.NEUTRAL.SLATE_900        # fondo cards / panels
_C_CARD_HDR_BG  = Colors.NEUTRAL.DARK_CARD        # header bar dentro de la card (slate-800)
_C_BORDER       = Colors.NEUTRAL.SLATE_700        # bordes (slate-700)
_C_HEADER_TXT   = Colors.NEUTRAL.DARK_TEXT       # texto fuerte (cabeceras)
_C_BODY_TXT     = Colors.NEUTRAL.SLATE_300       # texto cuerpo
_C_FIELD_LABEL  = Colors.NEUTRAL.DARK_TEXT_SEC   # labels de campos (slate-400)
_C_HINT         = Colors.NEUTRAL.SLATE_500       # placeholder / hint
_C_MUTED_BG     = Colors.NEUTRAL.DARK_CARD       # fondos sutiles (filas table, mini-bar)


def _section_label_style(accent: str = None) -> str:
    return (
        f"font-size:{Typography.SIZE_XS};"
        f"font-weight:{Typography.WEIGHT_BOLD};"
        "letter-spacing:0.08em;"
        "background:transparent;border:none;"
        f"color:{accent or _C_HEADER_TXT};"
    )


def _field_label_style() -> str:
    return (
        f"font-size:{Typography.SIZE_XS};"
        f"font-weight:{Typography.WEIGHT_BOLD};"
        f"letter-spacing:0.05em;color:{_C_FIELD_LABEL};"
        "background:transparent;border:none;"
    )


def _hint_label_style() -> str:
    return (
        f"font-size:{Typography.SIZE_XS};font-style:italic;"
        f"color:{_C_HINT};background:transparent;border:none;"
    )


def _make_field_label(text: str) -> QLabel:
    """Label uppercase pequeño para cabeceras de campos en grillas."""
    lbl = QLabel(text.upper())
    lbl.setObjectName("fieldLabel")
    lbl.setStyleSheet(_field_label_style())
    return lbl


def _make_section_card(header_text: str, accent_color: str = None,
                       panel_cls=QFrame, *, action: QWidget = None,
                       hint: str = None) -> tuple:
    """
    Section card con header + body. Theme-aware vía tokens.

    Args:
        header_text:   Texto del header (uppercase auto).
        accent_color:  Color del texto del header (default: _C_HEADER_TXT).
        panel_cls:     Subclase de QFrame para selector CSS específico.
        action:        Widget opcional alineado a la derecha del header.
        hint:          Texto auxiliar italic (ej. "* Obligatorio").

    Returns:
        (panel, body_layout)
    """
    panel = panel_cls()
    panel.setObjectName("sectionCard")
    panel.setStyleSheet(
        f"QFrame#sectionCard{{"
        f"  background:{_C_CARD_BG};"
        f"  border:1px solid {_C_BORDER};"
        f"  border-radius:{Borders.RADIUS_MD}px;"
        f"}}"
    )
    panel_lay = QVBoxLayout(panel)
    panel_lay.setContentsMargins(0, 0, 0, 0)
    panel_lay.setSpacing(0)

    # Header bar — slightly lighter than card body
    hdr_frame = QFrame()
    hdr_frame.setObjectName("sectionCardHeader")
    hdr_frame.setStyleSheet(
        f"QFrame#sectionCardHeader{{"
        f"  background:{_C_CARD_HDR_BG};"
        f"  border-bottom:1px solid {_C_BORDER};"
        f"  border-top-left-radius:{Borders.RADIUS_MD}px;"
        f"  border-top-right-radius:{Borders.RADIUS_MD}px;"
        f"}}"
    )
    hdr_row = QHBoxLayout(hdr_frame)
    hdr_row.setContentsMargins(Spacing.SM + 2, Spacing.XS, Spacing.SM + 2, Spacing.XS)
    hdr_row.setSpacing(Spacing.XS)

    hdr_lbl = QLabel(header_text.upper())
    hdr_lbl.setStyleSheet(_section_label_style(accent_color))
    hdr_row.addWidget(hdr_lbl)
    hdr_row.addStretch()
    if hint:
        hint_lbl = QLabel(hint)
        hint_lbl.setStyleSheet(_hint_label_style())
        hdr_row.addWidget(hint_lbl)
    if action is not None:
        hdr_row.addWidget(action)
    panel_lay.addWidget(hdr_frame)

    # Body
    body = QVBoxLayout()
    body.setContentsMargins(Spacing.SM + 2, Spacing.SM, Spacing.SM + 2, Spacing.SM)
    body.setSpacing(Spacing.XS + 2)
    panel_lay.addLayout(body)
    return panel, body


# ── Role-based permissions ───────────────────────────────────────────────────
_PERMISOS_POR_ROL: dict[str, frozenset] = {
    "ADMIN":      frozenset({"procesar", "cancelar", "reabrir", "editar",
                              "exportar", "ver_totales", "borrador", "historial"}),
    "GERENTE":    frozenset({"procesar", "cancelar", "reabrir", "editar",
                              "exportar", "ver_totales", "borrador", "historial"}),
    "SUPERVISOR": frozenset({"procesar", "cancelar", "exportar",
                              "ver_totales", "borrador", "historial"}),
    "COMPRAS":    frozenset({"procesar", "exportar", "ver_totales",
                              "borrador", "historial"}),
    "ALMACEN":    frozenset({"procesar", "exportar", "ver_totales",
                              "borrador", "historial"}),
    "CAJERO":     frozenset({"historial"}),
    "VENDEDOR":   frozenset({"historial"}),
    "BÁSICO":     frozenset({"historial"}),
    "BASIC":      frozenset({"historial"}),
    "CASHIER":    frozenset({"historial"}),
}
_PERMISOS_DEFAULT = frozenset({"procesar", "exportar", "ver_totales",
                                "borrador", "historial"})


def _make_status_chip(estado: str, parent=None) -> QLabel:
    """Returns a badge QLabel for a purchase estado using the design system."""
    lower = estado.strip().lower()
    label, variant = _STATUS_CHIP_MAP.get(lower, (estado.upper() or "—", "neutral"))
    return create_badge(parent, label, variant)


def _make_cond_chip(condicion: str, parent=None) -> QLabel:
    """Returns a badge QLabel for condicion_pago using the design system."""
    lower = condicion.strip().lower()
    label, variant = _COND_CHIP_MAP.get(lower, (condicion.capitalize() or "—", "neutral"))
    return create_badge(parent, label, variant)


class _DialogItemCompra(QDialog):
    """
    Dialog único para agregar o editar un ítem del carrito de compra.
    Reemplaza los 3 QInputDialog secuenciales con un formulario compacto
    que muestra la variación de precio en tiempo real.
    """

    def __init__(self, nombre: str, costo_hist: float, *,
                 cantidad: float = 1.0, costo: float | None = None,
                 modo: str = "add", parent=None):
        super().__init__(parent)
        self._costo_hist = costo_hist
        self._modo = modo
        costo_inicial = costo if costo is not None else (costo_hist or 0.0)

        titulo = f"{'Agregar' if modo == 'add' else 'Editar'}: {nombre}"
        self.setWindowTitle(titulo)
        self.setMinimumWidth(380)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(16, 14, 16, 14)

        # Product name header
        lbl_nombre = QLabel(nombre)
        lbl_nombre.setObjectName("subheading")
        lbl_nombre.setWordWrap(True)
        lay.addWidget(lbl_nombre)

        # Form
        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._spin_qty = QDoubleSpinBox()
        self._spin_qty.setDecimals(3)
        self._spin_qty.setMinimum(0.001)
        self._spin_qty.setMaximum(99999.0)
        self._spin_qty.setValue(cantidad)
        self._spin_qty.setMinimumWidth(130)
        self._spin_qty.setObjectName("styledInput")
        form.addRow("Cantidad:", self._spin_qty)

        self._spin_costo = QDoubleSpinBox()
        self._spin_costo.setDecimals(4)
        self._spin_costo.setMinimum(0.0)
        self._spin_costo.setMaximum(999999.0)
        self._spin_costo.setPrefix("$")
        self._spin_costo.setValue(costo_inicial)
        self._spin_costo.setMinimumWidth(130)
        self._spin_costo.setObjectName("styledInput")
        form.addRow("Costo unitario:", self._spin_costo)

        if costo_hist > 0:
            self._lbl_hist = QLabel(f"Precio histórico: ${costo_hist:.4f}")
            self._lbl_hist.setObjectName("caption")
            form.addRow("", self._lbl_hist)

        # Live variance indicator
        self._lbl_variacion = QLabel("")
        self._lbl_variacion.setObjectName("caption")
        form.addRow("Variación:", self._lbl_variacion)

        # Live subtotal
        self._lbl_subtotal = QLabel("Subtotal: $0.00")
        self._lbl_subtotal.setObjectName("statsKpiValue")
        self._lbl_subtotal.setProperty("variant", "success")
        form.addRow("", self._lbl_subtotal)

        lay.addLayout(form)

        # Buttons
        btn_row = QHBoxLayout()
        btn_cancel = create_secondary_button(self, "Cancelar", "Cancelar sin guardar")
        verb = "Agregar al carrito" if modo == "add" else "Guardar cambios"
        self._btn_ok = create_success_button(self, f"✔ {verb}", verb)
        btn_cancel.clicked.connect(self.reject)
        self._btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_ok)
        lay.addLayout(btn_row)

        # Wire live updates
        self._spin_qty.valueChanged.connect(self._actualizar_preview)
        self._spin_costo.valueChanged.connect(self._actualizar_preview)
        self._actualizar_preview()

        # Keyboard: Enter → accept, focus quantity
        QShortcut(QKeySequence(Qt.Key_Return), self, self._btn_ok.click)
        self._spin_qty.setFocus()
        self._spin_qty.selectAll()

    def _actualizar_preview(self) -> None:
        qty   = self._spin_qty.value()
        costo = self._spin_costo.value()
        subtotal = round(qty * costo, 4)
        self._lbl_subtotal.setText(f"Subtotal: ${subtotal:,.4f}")

        if self._costo_hist > 0 and costo > 0:
            variacion = (costo - self._costo_hist) / self._costo_hist * 100
            simbolo = "▲" if variacion > 0 else "▼"
            color_var = (Colors.DANGER_BASE if abs(variacion) >= _PRICE_VARIANCE_THRESHOLD
                         else Colors.SUCCESS_BASE)
            self._lbl_variacion.setText(f"{simbolo} {abs(variacion):.1f}%")
            self._lbl_variacion.setStyleSheet(
                f"color:{color_var};font-weight:700;background:transparent;border:none;")
        else:
            self._lbl_variacion.setText("—")
            self._lbl_variacion.setStyleSheet("")

    @property
    def cantidad(self) -> float:
        v = self._spin_qty.value()
        return max(0.001, v)

    @property
    def costo(self) -> float:
        return max(0.0, self._spin_costo.value())

    def accept(self) -> None:
        if self._spin_qty.value() < 0.001:
            self._lbl_variacion.setText("⚠ Cantidad debe ser > 0")
            self._lbl_variacion.setStyleSheet(f"color:{Colors.DANGER_BASE};font-weight:700;")
            self._spin_qty.setFocus()
            return
        if self._spin_costo.value() < 0:
            self._lbl_variacion.setText("⚠ Costo no puede ser negativo")
            self._lbl_variacion.setStyleSheet(f"color:{Colors.DANGER_BASE};font-weight:700;")
            self._spin_costo.setFocus()
            return
        subtotal = self._spin_qty.value() * self._spin_costo.value()
        if subtotal > 9_999_999:
            self._lbl_variacion.setText("⚠ Subtotal supera $9,999,999")
            self._lbl_variacion.setStyleSheet(f"color:{Colors.DANGER_BASE};font-weight:700;")
            return
        super().accept()


class _ConfirmDestructiveDialog(QDialog):
    """
    Diálogo de confirmación para acciones destructivas.
    Requiere que el operador escriba el motivo antes de habilitar el botón.
    Genera un registro auditable independientemente de dónde se llame.
    """

    def __init__(self, titulo: str, mensaje: str,
                 accion_label: str = "Confirmar",
                 require_reason: bool = True,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setMinimumWidth(440)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._require_reason = require_reason

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 16, 20, 16)

        warn = QLabel(f"⚠️  {mensaje}")
        warn.setWordWrap(True)
        warn.setObjectName("subheading")
        warn.setStyleSheet(f"color:{Colors.DANGER_BASE};")
        lay.addWidget(warn)

        if require_reason:
            lbl_m = QLabel("Motivo (obligatorio para auditoría):")
            lbl_m.setObjectName("caption")
            lay.addWidget(lbl_m)
            self._txt_motivo = QLineEdit()
            self._txt_motivo.setPlaceholderText("Describe el motivo de esta acción…")
            self._txt_motivo.setMinimumHeight(32)
            self._txt_motivo.textChanged.connect(self._validar)
            lay.addWidget(self._txt_motivo)

        btn_row = QHBoxLayout()
        btn_cancel = create_secondary_button(None, "✕ No, volver", "Cancelar sin cambios")
        self._btn_ok = create_danger_button(None, f"⚠ {accion_label}", accion_label)
        self._btn_ok.setEnabled(not require_reason)
        btn_cancel.clicked.connect(self.reject)
        self._btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_ok)
        lay.addLayout(btn_row)

        QShortcut(QKeySequence(Qt.Key_Escape), self, self.reject)

    def _validar(self) -> None:
        if self._require_reason:
            self._btn_ok.setEnabled(len(self._txt_motivo.text().strip()) >= 3)

    @property
    def motivo(self) -> str:
        if self._require_reason and hasattr(self, '_txt_motivo'):
            return self._txt_motivo.text().strip()
        return ""


class _PINDialog(QDialog):
    """
    Diálogo de PIN de supervisor para autorizar acciones sensibles.
    Si `pin_supervisor` no está configurado en la tabla `configuracion`,
    el método `verificar()` retorna True sin mostrar el diálogo (modo sin PIN).
    El PIN se lee de la DB cada vez para reflejar cambios en caliente.
    """

    def __init__(self, pin_correcto: str, accion_label: str, parent=None):
        super().__init__(parent)
        self._pin = pin_correcto
        self.setWindowTitle("Autorización de Supervisor")
        self.setMinimumWidth(320)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(20, 16, 20, 16)

        lbl = QLabel(f"Acción restringida:\n{accion_label}\n\nIngresa el PIN de supervisor:")
        lbl.setWordWrap(True)
        lbl.setObjectName("subheading")
        lay.addWidget(lbl)

        self._txt_pin = QLineEdit()
        self._txt_pin.setEchoMode(QLineEdit.Password)
        self._txt_pin.setMaxLength(12)
        self._txt_pin.setAlignment(Qt.AlignCenter)
        self._txt_pin.setPlaceholderText("PIN  ·  ·  ·  ·")
        self._txt_pin.setObjectName("styledInput")
        lay.addWidget(self._txt_pin)

        self._lbl_err = QLabel("")
        self._lbl_err.setObjectName("caption")
        self._lbl_err.setStyleSheet(f"color:{Colors.DANGER_BASE};")
        lay.addWidget(self._lbl_err)

        btn_row = QHBoxLayout()
        btn_cancel = create_secondary_button(None, "✕ Cancelar", "Cancelar")
        btn_ok = create_primary_button(None, "✓ Autorizar", "Verificar PIN")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._verificar)
        btn_row.addWidget(btn_cancel); btn_row.addStretch(); btn_row.addWidget(btn_ok)
        lay.addLayout(btn_row)

        QShortcut(QKeySequence(Qt.Key_Return), self, self._verificar)
        QShortcut(QKeySequence(Qt.Key_Escape), self, self.reject)
        self._txt_pin.setFocus()

    def _verificar(self) -> None:
        if self._txt_pin.text().strip() == self._pin:
            self.accept()
        else:
            self._lbl_err.setText("⚠ PIN incorrecto — intenta de nuevo")
            self._txt_pin.clear()
            self._txt_pin.setFocus()

    @staticmethod
    def _leer_pin(db) -> str:
        """Lee el PIN de supervisor desde configuracion. Retorna "" si no configurado."""
        _CONFIGS = [
            ("configuracion", "clave",    "valor"),
            ("settings",      "key",      "value"),
            ("parametros",    "parametro","valor"),
        ]
        for tabla, col_k, col_v in _CONFIGS:
            try:
                r = db.execute(
                    f"SELECT {col_v} FROM {tabla} WHERE {col_k}=? LIMIT 1",
                    ("pin_supervisor",)
                ).fetchone()
                if r:
                    return str(r[0] or "").strip()
            except Exception:
                pass
        return ""

    @classmethod
    def verificar(cls, db, accion_label: str, parent=None) -> bool:
        """
        Punto de entrada único. Retorna True si autorizado.
        No muestra diálogo si PIN no está configurado (modo sin PIN).
        """
        pin = cls._leer_pin(db)
        if not pin:
            return True   # PIN no configurado — sólo require motivo (ya capturado antes)
        dlg = cls(pin, accion_label, parent)
        return dlg.exec_() == QDialog.Accepted


class _HistorialLoader(QThread):
    """Carga el historial de compras en background para no bloquear la UI."""
    loaded  = pyqtSignal(list)   # emite lista de rows cuando termina
    error   = pyqtSignal(str)    # emite mensaje de error si falla

    def __init__(self, db, sucursal_id: int, desde: str, hasta: str,
                 limit: int = _HIST_LIMIT):
        super().__init__()
        self._db         = db
        self._sucursal   = sucursal_id
        self._desde      = desde
        self._hasta      = hasta
        self._limit      = limit

    def run(self) -> None:
        try:
            rows = self._db.execute("""
                SELECT c.folio, c.fecha, COALESCE(p.nombre,'(sin proveedor)') as proveedor,
                       c.usuario, c.total, c.estado, c.id,
                       COALESCE(c.condicion_pago,'liquidado') AS condicion_pago,
                       COALESCE(c.moneda,'MXN') AS moneda,
                       COALESCE(c.purchase_order_id, 0) AS po_id,
                       COALESCE(oc.estado, '') AS po_estado
                FROM compras c
                LEFT JOIN proveedores p ON p.id=c.proveedor_id
                LEFT JOIN ordenes_compra oc ON oc.id=c.purchase_order_id
                WHERE c.sucursal_id=? AND c.fecha BETWEEN ? AND ?
                ORDER BY c.fecha DESC LIMIT ?
            """, (self._sucursal, self._desde, self._hasta, self._limit)).fetchall()
            self.loaded.emit(rows)
        except Exception as e:
            self.error.emit(str(e))


class ModuloComprasPro(QWidget, RefreshMixin):
    """Módulo Enterprise para Recepción de Mercancía."""

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container       = container
        self.sucursal_id     = 1
        self.usuario_actual  = ""
        self._usuario_rol    = ""
        self.carrito_compra: list[dict] = []

        # EventBus: auto-refresh when products or purchases change
        try:
            self._init_refresh(container, [
                "COMPRA_REGISTRADA", "RECEPCION_CONFIRMADA",
                "PRODUCTO_CREADO",   "PRODUCTO_ACTUALIZADO",
                "PROVEEDOR_CREADO",  "PROVEEDOR_ACTUALIZADO",
            ])
        except Exception:
            pass

        self._doc_type = "DIRECT"   # Phase 5: DIRECT | PR | PO
        self._build_ui()
        QTimer.singleShot(200, self.cargar_proveedores)

        # Auto-save timer: silent draft every 45 s when cart is non-empty
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(45_000)
        self._autosave_timer.timeout.connect(self._auto_save_draft)
        self._autosave_timer.start()

    # ── Repository access (lazy, same DB connection) ─────────────────────────
    @property
    def _purchase_repo(self):
        """Lazy PurchaseRepository bound to the container's DB connection."""
        if not hasattr(self, '_purchase_repo_instance'):
            from repositories.purchase_repository import PurchaseRepository
            self._purchase_repo_instance = PurchaseRepository(self.container.db)
        return self._purchase_repo_instance

    def _get_iva_rate(self) -> float:
        """Read IVA rate from DB configuraciones with fallback to _IVA_RATE constant."""
        if hasattr(self, '_iva_rate_cached'):
            return self._iva_rate_cached
        try:
            db = self.container.db
            for tabla, col_k, col_v in [
                ('configuraciones', 'clave', 'valor'),
                ('settings', 'key', 'value'),
            ]:
                try:
                    row = db.execute(
                        f"SELECT {col_v} FROM {tabla} WHERE {col_k}=? LIMIT 1",
                        ('iva_rate',)
                    ).fetchone()
                    if row:
                        raw = float(row[0] or _IVA_RATE)
                        # Accept both fractional (0.16) and percentage (16) forms
                        self._iva_rate_cached = raw / 100.0 if raw > 1 else raw
                        return self._iva_rate_cached
                except Exception:
                    continue
        except Exception:
            pass
        self._iva_rate_cached = _IVA_RATE
        return self._iva_rate_cached

    # ── Propagation ──────────────────────────────────────────────────────────
    def set_sucursal(self, sucursal_id: int, nombre: str = "") -> None:
        self.sucursal_id = sucursal_id
        self.cargar_proveedores()
        if hasattr(self, '_buscador'):
            self._buscador.set_db(self.container.db)
        if hasattr(self, '_quick_grid'):
            self._cargar_quick_products()

    # ── E-6: Planeacion → Compras bridge ─────────────────────────────────────

    def set_suggested_order(self, items: list[dict], proveedor_id: int = 0,
                             proveedor_nombre: str = "") -> None:
        """
        Pre-fills the cart from a planning suggestion.

        Expected item keys: product_id (int), nombre (str), qty (float),
                            unit_cost (float, optional)
        Called by ModuloPlaneacionCompras.enviar_a_modulo_compras() via container.
        """
        if not items:
            return
        # Switch to the Compra Tradicional tab
        if hasattr(self, '_tabs'):
            self._tabs.setCurrentIndex(0)

        added = 0
        for it in items:
            prod_id    = int(it.get("product_id", it.get("producto_id", 0)) or 0)
            nombre     = str(it.get("nombre", f"Producto {prod_id}"))
            qty        = float(it.get("qty", it.get("cantidad", 0)) or 0)
            unit_cost  = float(it.get("unit_cost", it.get("costo_unitario", 0)) or 0)
            if prod_id <= 0 or qty <= 0:
                continue
            # Avoid duplicating items already in cart
            for cart_item in self.carrito_compra:
                if cart_item["producto_id"] == prod_id:
                    cart_item["cantidad"] += qty
                    cart_item["subtotal"] = round(
                        cart_item["cantidad"] * cart_item["costo_unitario"], 4)
                    added += 1
                    break
            else:
                self.carrito_compra.append({
                    "producto_id":   prod_id,
                    "nombre":        nombre,
                    "cantidad":      qty,
                    "costo_unitario": unit_cost,
                    "subtotal":      round(qty * unit_cost, 4),
                    "unidad":        it.get("unidad", "kg"),
                    "descuento_pct": 0.0,
                    "iva_pct":       0.0,
                })
                added += 1

        # Pre-select provider if given
        if proveedor_id > 0:
            self._proveedor_id_selected = proveedor_id
            if proveedor_nombre and hasattr(self, 'txt_proveedor'):
                self.txt_proveedor.setText(proveedor_nombre)
            self._cargar_info_proveedor(proveedor_id)
            self._cargar_recientes_proveedor(proveedor_id)
            self._cargar_alertas_cxp(proveedor_id)

        self._refresh_tabla()
        self._refresh_stepper()
        if added:
            Toast.info(self, "🧠 Sugerencia cargada",
                       f"{added} ítem(s) desde Planeación · revisa cantidades antes de autorizar.")

    def set_usuario_actual(self, usuario: str, rol: str = "") -> None:
        self.usuario_actual = usuario
        self._usuario_rol = rol.upper().strip()
        QTimer.singleShot(0, self._aplicar_permisos_ui)
        # Auto-fill solicitante with the logged-in user
        if usuario and hasattr(self, 'txt_solicitante'):
            self.txt_solicitante.setText(usuario)
        # Offer draft restore 1.5 s after login (cart must still be empty)
        QTimer.singleShot(1500, self._check_pending_draft)

    def _tiene_permiso(self, accion: str) -> bool:
        """Retorna True si el rol actual tiene el permiso solicitado."""
        rol = self._usuario_rol
        if not rol or rol == "ADMIN":
            return True
        return accion in _PERMISOS_POR_ROL.get(rol, _PERMISOS_DEFAULT)

    def _aplicar_permisos_ui(self) -> None:
        """Muestra/oculta/deshabilita controles según el rol del usuario."""
        puede_procesar = self._tiene_permiso("procesar")
        puede_exportar = self._tiene_permiso("exportar")
        puede_borrador = self._tiene_permiso("borrador")
        puede_editar   = self._tiene_permiso("editar")

        for attr, visible in [
            ("_btn_procesar",  puede_procesar),
            ("_btn_draft_save", puede_borrador),
            ("_btn_draft_load", puede_borrador),
            ("_btn_del_sel",    puede_editar or puede_procesar),
            ("_btn_export_csv", puede_exportar),
        ]:
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.setVisible(visible)

    # ── UI ───────────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)

        # ── PageHeader ────────────────────────────────────────────────────────
        root.addWidget(PageHeader(self,
            title="🛒 Compras a Proveedores",
            subtitle="Recepción de mercancía · Actualización de stock · Historial",
        ))

        # ── KPI bar (outside tabs, spans all 3 tabs) ─────────────────────────
        root.addWidget(self._build_purchase_kpi_bar())

        # Tabs: Tradicional | QR
        self._tabs = create_standard_tabs(self)
        root.addWidget(self._tabs)

        tab_trad = QWidget()
        self._tabs.addTab(tab_trad, "🛒 Compra Tradicional")
        self._build_tab_tradicional(tab_trad)

        tab_qr = QWidget()
        self._tabs.addTab(tab_qr, "📦 Recepción con QR")
        self._build_tab_qr(tab_qr)

        tab_hist = QWidget()
        self._tabs.addTab(tab_hist, "📋 Historial de Compras")
        self._build_tab_historial(tab_hist)

        self._remove_accidental_po_tabs()
        self._tabs.currentChanged.connect(self._on_tab_change)
        apply_spj_buttons(self)
        self._normalizar_botones_ui()

    def _remove_accidental_po_tabs(self) -> None:
        """Fail-safe: Compras no debe exponer una pestaña superior dedicada a PO."""
        if not hasattr(self, '_tabs'):
            return
        banned = (
            "recepcion po", "recepcion de po", "po reception",
            "recepcion oc", "recepcion de oc", "recibir orden",
        )
        for idx in range(self._tabs.count() - 1, -1, -1):
            label = self._tabs.tabText(idx) or ""
            normalized = unicodedata.normalize("NFKD", label).encode(
                "ascii", "ignore"
            ).decode("ascii").lower()
            if any(token in normalized for token in banned):
                self._tabs.removeTab(idx)

    def _normalizar_botones_ui(self) -> None:
        """Ensure minimum height on module buttons; excludes icon-only and QR widget."""
        _recv = getattr(self, '_recv_qr', None)
        for btn in self.findChildren(QPushButton):
            if btn.minimumWidth() and btn.minimumWidth() <= 40:
                continue
            if _recv is not None and _recv.isAncestorOf(btn):
                continue
            if btn.minimumHeight() < 32:
                btn.setMinimumHeight(32)

    def _crear_stats_compras(self) -> QWidget:
        """Barra de KPIs: compras del mes, proveedores activos, órdenes pendientes, gasto."""
        bar = QFrame()
        bar.setObjectName("statsBarCmp")
        bar.setFixedHeight(64)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 8, 20, 8)
        lay.setSpacing(0)

        kpi_defs = [
            ("Compras este mes",    "—", "primary"),
            ("Proveedores activos", "—", "success"),
            ("Órdenes pendientes",  "—", "warning"),
            ("Gasto del mes",       "—", "info"),
        ]
        self._stats_value_labels: list[QLabel] = []

        for i, (caption, val, variant) in enumerate(kpi_defs):
            if i > 0:
                sep = QFrame()
                sep.setObjectName("statsBarSeparator")
                sep.setFrameShape(QFrame.VLine)
                sep.setFixedWidth(1)
                lay.addWidget(sep)
                lay.addSpacing(20)
            col_lay = QVBoxLayout()
            col_lay.setSpacing(1)
            lbl_val = QLabel(val)
            lbl_val.setObjectName("statsKpiValue")
            lbl_val.setProperty("variant", variant)   # theme-aware via QSS
            lbl_cap = QLabel(caption.upper())
            lbl_cap.setObjectName("statsKpiCaption")
            col_lay.addWidget(lbl_val)
            col_lay.addWidget(lbl_cap)
            lay.addLayout(col_lay)
            self._stats_value_labels.append(lbl_val)
            if i < 3:
                lay.addSpacing(20)
        lay.addStretch()
        # Defer DB queries so stats don't block __init__
        QTimer.singleShot(250, self._refresh_stats)
        return bar

    def _refresh_stats(self) -> None:
        """Recarga los KPIs de la barra de estadísticas (deferred, non-blocking)."""
        if not hasattr(self, '_stats_value_labels'):
            return
        try:
            stats = self._purchase_repo.get_header_stats(self.sucursal_id)
            self._stats_value_labels[0].setText(str(stats["count_mes"]))
            self._stats_value_labels[1].setText(str(stats["prov_activos"]))
            self._stats_value_labels[2].setText(str(stats["oc_pendientes"]))
            self._stats_value_labels[3].setText(f"${stats['total_mes']:,.0f}")
        except Exception as e:
            logger.debug("_refresh_stats: %s", e)

    def _build_tab_tradicional(self, parent: QWidget) -> None:
        """3-column ERP layout: Sidebar | Center | Right panel."""
        from PyQt5.QtWidgets import QSplitter
        root = QVBoxLayout(parent)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── 3-column splitter ─────────────────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("purchaseThreeColumnSplitter")
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(
            "QSplitter::handle{background:rgba(148,163,184,0.25);}"
        )
        root.addWidget(splitter, 1)

        # Left column — Documental Toolbar (ERP documental)
        left_col = self._build_documental_toolbar()
        splitter.addWidget(left_col)

        # Center column — Captura Documental
        center_col = self._build_center_column()
        splitter.addWidget(center_col)

        # Right column — Summary + Payment + Actions
        right_col = self._build_summary_panel()
        splitter.addWidget(right_col)

        # Set initial sizes: left=280, center=520, right=520.
        # Fase 3: la columna derecha no es sidebar; crece junto con captura.
        splitter.setSizes([285, 380, 475])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 5)
        self._tradicional_splitter = splitter

        QShortcut(QKeySequence(Qt.Key_F10), parent, self._procesar_compra)

        # Apply initial doctype state after all panels are built
        self._refresh_doctype_ui()

    def _build_purchase_kpi_bar(self) -> QWidget:
        """Full-width KPI bar with 5 operational metrics using _PurchaseKPICard."""
        bar = PurchaseKpiBar()
        bar.setObjectName("kpiStripBar")
        bar.setFixedHeight(96)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)
        lay.setSpacing(0)

        kpi_defs = [
            ("Compras del mes",     "—", "💰", "success"),
            ("Ordenes en curso",    "—", "📋", "primary"),
            ("Por pagar (CXP)",     "—", "⏱", "warning"),
            ("Proveedores activos", "—", "🏢", "info"),
            ("Lead time prom.",     "—", "📅", "neutral"),
        ]

        self._kpi_strip_cards: list[_PurchaseKPICard] = []

        for i, (titulo, valor, icono, variant) in enumerate(kpi_defs):
            if i > 0:
                div = QFrame()
                div.setObjectName("kpiDivider")
                div.setFixedWidth(1)
                lay.addWidget(div)

            card = _PurchaseKPICard(titulo, valor, icono, variant, bar)
            lay.addWidget(card, 1)
            self._kpi_strip_cards.append(card)

        QTimer.singleShot(300, self._refresh_kpi_strip)
        return bar

    def _refresh_kpi_strip(self) -> None:
        """Refresh the 5 KPI strip cards from purchase_repo stats."""
        if not hasattr(self, '_kpi_strip_cards') or not self._kpi_strip_cards:
            return
        try:
            stats = self._purchase_repo.get_header_stats(self.sucursal_id)
            vals = [
                f"${stats.get('total_mes', 0):,.0f}",
                str(stats.get("oc_pendientes", "—")),
                f"${stats.get('cxp_total', stats.get('total_mes', 0)):,.0f}",
                str(stats.get("prov_activos", "—")),
                f"{stats.get('lead_time', '—')}d",
            ]
            for card, v in zip(self._kpi_strip_cards, vals):
                card.set_valor(v)
        except Exception as e:
            logger.debug("_refresh_kpi_strip: %s", e)

    # ── Named sub-builders for center column ─────────────────────────────────

    def _build_provider_card(self) -> QFrame:
        """Provider section card. Sets up all provider-related instance attrs."""
        panel, body = _make_section_card(
            "Datos del Proveedor",
            panel_cls=PurchaseProviderCard,
        )

        self._proveedor_id_selected = None
        self._proveedores_cache = []
        self.txt_proveedor = create_input(self, "Buscar proveedor…")
        self.txt_proveedor.setMinimumWidth(280)
        self._prov_model = QStringListModel(self)
        self._prov_completer = QCompleter(self._prov_model, self)
        self._prov_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._prov_completer.setFilterMode(Qt.MatchContains)
        self._prov_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.txt_proveedor.setCompleter(self._prov_completer)
        self._prov_completer.activated[str].connect(self._on_completer_activated)
        self.txt_proveedor.editingFinished.connect(self._resolver_proveedor_desde_texto)

        self._lbl_prov_status = QLabel("Sin proveedor seleccionado")
        self._lbl_prov_status.setObjectName("caption")
        self._lbl_prov_status.setStyleSheet(
            f"color:{Colors.WARNING_BASE};"
            f"font-size:{Typography.SIZE_XS};background:transparent;"
        )

        # _lbl_prov_info kept hidden for backward compatibility with existing code
        self._lbl_prov_info = QLabel("")
        self._lbl_prov_info.setObjectName("caption")
        self._lbl_prov_info.setWordWrap(True)
        self._lbl_prov_info.hide()

        def _ro_input(placeholder="—") -> QLineEdit:
            """Disabled read-only input for provider info display."""
            w = QLineEdit(placeholder)
            w.setReadOnly(True)
            w.setObjectName("standardInput")
            w.setStyleSheet("opacity:0.6;")
            return w

        # Read-only display inputs (populated by _cargar_info_proveedor)
        self._inp_rfc  = _ro_input()
        self._inp_tel  = _ro_input()
        self._inp_dir  = _ro_input()
        self._inp_cred = _ro_input()
        self._inp_cred.setStyleSheet(
            f"opacity:0.85;color:{Colors.ACCENT_BASE};"
            f"font-weight:{Typography.WEIGHT_BOLD};"
        )
        # Aliases backward-compat — point to input.text() via proxy
        self._lbl_rfc      = self._inp_rfc
        self._lbl_tel      = self._inp_tel
        self._lbl_dir      = self._inp_dir
        self._lbl_cred_disp = self._inp_cred

        # Condiciones combo (editable — applies to this purchase)
        self._cmb_cond_prov = create_combo(self)
        for c in ["30 Días Crédito", "Contado / Contra Entrega",
                  "15 Días Crédito", "60 Días Crédito"]:
            self._cmb_cond_prov.addItem(c)
        self._lbl_cond_disp = self._cmb_cond_prov

        grid = QGridLayout()
        grid.setSpacing(Spacing.XS + 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        # Row 0: Proveedor (full width)
        grid.addWidget(_make_field_label("Proveedor"), 0, 0, 1, 2)
        grid.addWidget(self.txt_proveedor,             1, 0, 1, 2)
        grid.addWidget(self._lbl_prov_status,          2, 0, 1, 2)
        # Row 1: RFC | Teléfono
        grid.addWidget(_make_field_label("RFC"),       3, 0)
        grid.addWidget(_make_field_label("Teléfono"),  3, 1)
        grid.addWidget(self._inp_rfc,                  4, 0)
        grid.addWidget(self._inp_tel,                  4, 1)
        # Row 2: Dirección (full width)
        grid.addWidget(_make_field_label("Dirección"), 5, 0, 1, 2)
        grid.addWidget(self._inp_dir,                  6, 0, 1, 2)
        # Row 3: Crédito disp. | Condiciones
        grid.addWidget(_make_field_label("Crédito disp."), 7, 0)
        grid.addWidget(_make_field_label("Condiciones"),   7, 1)
        grid.addWidget(self._inp_cred,                 8, 0)
        grid.addWidget(self._cmb_cond_prov,            8, 1)

        body.addLayout(grid)
        body.addWidget(self._lbl_prov_info)
        return panel

    def _build_document_card(self) -> QFrame:
        """Document section card — 2-col grid layout matching ERP reference."""
        panel, body = _make_section_card(
            "Datos del Documento",
            panel_cls=PurchaseDocumentCard,
            hint="* Obligatorio",
        )

        # Build all widgets
        self.txt_factura = create_input(self, "Ej. FAC-001 / REM-00129")

        self._adjunto_path: str = ""
        self._lbl_adjunto = QLabel("Sin archivo")
        self._lbl_adjunto.setObjectName("caption")
        self._lbl_adjunto.hide()
        btn_adjunto = create_secondary_button(self, "📎", "Adjuntar PDF o imagen de factura")
        btn_adjunto.setFixedSize(28, 28)
        btn_adjunto.clicked.connect(self._adjuntar_factura)
        _fac_row = QHBoxLayout()
        _fac_row.setSpacing(Spacing.XS)
        _fac_row.addWidget(self.txt_factura, 1)
        _fac_row.addWidget(btn_adjunto)

        self._date_factura = QDateEdit(QDate.currentDate())
        self._date_factura.setCalendarPopup(True)
        self._date_factura.setDisplayFormat("dd/MM/yyyy")
        self._date_factura.setObjectName("standardInput")

        # Commercial document type (Factura / Remisión / Nota) — distinct from
        # the workflow doctype toolbar (DIRECT / PR / PO) shown above the cards.
        self._cmb_tipo_doc = create_combo(self)
        for t in ["Factura", "Remisión", "Nota de Entrada"]:
            self._cmb_tipo_doc.addItem(t)

        self.cmb_sucursal_destino = create_combo(self)
        self.cmb_sucursal_destino.setToolTip("Sucursal destino del inventario")
        self._cargar_sucursales_compra()

        self._cmb_moneda = create_combo(self)
        for code, label in [("MXN", "MXN - Pesos"),
                            ("USD", "USD - Dólares"),
                            ("EUR", "EUR - Euros")]:
            self._cmb_moneda.addItem(label, code)

        self._cmb_prioridad = create_combo(self)
        for p in ["ALTA", "MEDIA", "BAJA"]:
            self._cmb_prioridad.addItem(p)

        self.txt_solicitante = create_input(self, "Nombre del solicitante")
        if self.usuario_actual:
            self.txt_solicitante.setText(self.usuario_actual)

        self.txt_notas = QPlainTextEdit()
        self.txt_notas.setPlaceholderText("Observaciones adicionales…")
        self.txt_notas.setObjectName("standardInput")
        self.txt_notas.setFixedHeight(48)

        # 2-col grid
        grid = QGridLayout()
        grid.setSpacing(Spacing.XS + 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        r = 0
        grid.addWidget(_make_field_label("Factura / Remisión *"), r, 0)
        grid.addWidget(_make_field_label("Fecha Doc."),            r, 1); r += 1
        grid.addLayout(_fac_row,                                   r, 0)
        grid.addWidget(self._date_factura,                         r, 1); r += 1

        grid.addWidget(_make_field_label("Tipo Documento"),        r, 0)
        grid.addWidget(_make_field_label("Sucursal Destino"),      r, 1); r += 1
        grid.addWidget(self._cmb_tipo_doc,                         r, 0)
        grid.addWidget(self.cmb_sucursal_destino,                  r, 1); r += 1

        grid.addWidget(_make_field_label("Moneda"),                r, 0)
        grid.addWidget(_make_field_label("Prioridad"),             r, 1); r += 1
        grid.addWidget(self._cmb_moneda,                           r, 0)
        grid.addWidget(self._cmb_prioridad,                        r, 1); r += 1

        grid.addWidget(_make_field_label("Solicitante"),           r, 0, 1, 2); r += 1
        grid.addWidget(self.txt_solicitante,                       r, 0, 1, 2); r += 1

        grid.addWidget(_make_field_label("Notas"),                 r, 0, 1, 2); r += 1
        grid.addWidget(self.txt_notas,                             r, 0, 1, 2); r += 1

        body.addLayout(grid)
        return panel

    def _build_product_search_card(self) -> QFrame:
        """Product search card with status bar. Sets up _buscador and _trad_filter."""
        panel, body = _make_section_card("Buscar Producto", Colors.PRIMARY_BASE, PurchaseProductSearchCard)

        from modulos.spj_product_search import ProductSearchWidget
        self._buscador = ProductSearchWidget(
            db=self.container.db,
            placeholder="Escanee SKU / Barcode o nombre...",
            show_stock=True,
        )
        self._buscador.producto_seleccionado.connect(self._agregar_producto)
        body.addWidget(self._buscador)

        status_row = QHBoxLayout()
        status_row.setSpacing(Spacing.SM)
        lbl_bascula = QLabel("⚖ Báscula: <b>Integrada</b>")
        lbl_bascula.setObjectName("caption")
        lbl_bascula.setStyleSheet(f"color:{Colors.ACCENT_BASE};background:transparent;")
        lbl_etiquetas = QLabel("🖨 Etiquetas: <b>Lista</b>")
        lbl_etiquetas.setObjectName("caption")
        lbl_etiquetas.setStyleSheet(f"color:{Colors.NEUTRAL.SLATE_500};background:transparent;")
        status_row.addWidget(lbl_bascula)
        status_row.addStretch()
        status_row.addWidget(lbl_etiquetas)
        body.addLayout(status_row)

        # Cart filter — placed in right panel header
        self._trad_filter = FilterBar(self, placeholder="Filtrar carrito por nombre de producto…")
        self._trad_filter.filters_changed.connect(lambda _v: self._refresh_tabla())
        return panel

    def _build_purchase_items_panel(self) -> QFrame:
        """Cart items panel with header, table, loading, and empty state."""
        cart_panel = PurchaseItemsAndTotalsPanel()
        cart_panel.setObjectName("sectionCard")
        cart_panel.setStyleSheet(
            f"QFrame#sectionCard{{"
            f"  background:{_C_CARD_BG};"
            f"  border:1px solid {_C_BORDER};"
            f"  border-radius:{Borders.RADIUS_MD}px;"
            f"}}"
        )
        cart_lay_outer = QVBoxLayout(cart_panel)
        cart_lay_outer.setContentsMargins(0, 0, 0, 0)
        cart_lay_outer.setSpacing(0)

        # ── Header bar — title + counter + actions ──────────────────────────
        cart_hdr_frame = QFrame()
        cart_hdr_frame.setObjectName("cartHdrFrame")
        cart_hdr_frame.setStyleSheet(
            f"QFrame#cartHdrFrame{{"
            f"  background:{_C_CARD_HDR_BG};"
            f"  border-bottom:1px solid {_C_BORDER};"
            f"  border-top-left-radius:{Borders.RADIUS_MD}px;"
            f"  border-top-right-radius:{Borders.RADIUS_MD}px;"
            f"}}"
        )
        cart_hdr = QHBoxLayout(cart_hdr_frame)
        cart_hdr.setContentsMargins(Spacing.SM + 2, Spacing.XS, Spacing.SM + 2, Spacing.XS)
        cart_hdr.setSpacing(Spacing.XS + 2)

        lbl_cart_hdr = QLabel("PARTIDAS DEL DOCUMENTO")
        lbl_cart_hdr.setStyleSheet(_section_label_style(Colors.PRIMARY_BASE))
        self._lbl_cart_count = QLabel("0 items")
        self._lbl_cart_count.setObjectName("caption")
        self._lbl_cart_count.setStyleSheet(
            f"color:{_C_FIELD_LABEL};"
            f"font-size:{Typography.SIZE_XS};"
            "background:transparent;border:none;"
        )

        btn_clear = create_danger_button(self, "Limpiar", "Vaciar carrito de compras")
        btn_clear.setFixedHeight(26)
        btn_clear.clicked.connect(self._limpiar_carrito)
        btn_del_sel = create_danger_button(self, "Eliminar sel.", "Eliminar filas seleccionadas")
        btn_del_sel.setFixedHeight(26)
        btn_del_sel.clicked.connect(self._eliminar_seleccionados)
        btn_draft_save = create_secondary_button(self, "Borrador", "Guardar carrito como borrador")
        btn_draft_save.setFixedHeight(26)
        btn_draft_load = create_secondary_button(self, "Recuperar", "Cargar último borrador guardado")
        btn_draft_load.setFixedHeight(26)
        btn_draft_save.clicked.connect(self._guardar_borrador)
        btn_draft_load.clicked.connect(self._cargar_borrador)
        self._btn_draft_save = btn_draft_save
        self._btn_draft_load = btn_draft_load
        self._btn_del_sel    = btn_del_sel

        cart_hdr.addWidget(lbl_cart_hdr)
        cart_hdr.addWidget(self._lbl_cart_count)
        cart_hdr.addStretch()
        cart_hdr.addWidget(btn_clear)
        cart_hdr.addWidget(btn_del_sel)
        cart_hdr.addWidget(btn_draft_save)
        cart_hdr.addWidget(btn_draft_load)
        cart_lay_outer.addWidget(cart_hdr_frame)

        # ── Body — table + states ───────────────────────────────────────────
        cart_body = QVBoxLayout()
        cart_body.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)
        cart_body.setSpacing(Spacing.XS)
        cart_lay_outer.addLayout(cart_body)

        self.tabla = QTableWidget()
        self.tabla.setColumnCount(9)
        self.tabla.setHorizontalHeaderLabels(
            ["SKU/ID", "Producto", "Lote", "Cant./UM", "Peso Est.",
             "Costo", "Desc/Imp", "Subtotal", ""])
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (0, 2, 3, 4, 5, 6, 7, 8):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh.setStyleSheet(
            f"QHeaderView::section{{"
            f"  background:{_C_MUTED_BG};"
            f"  color:{_C_FIELD_LABEL};"
            f"  font-size:{Typography.SIZE_XS};"
            f"  font-weight:{Typography.WEIGHT_BOLD};"
            f"  letter-spacing:0.05em;"
            f"  border:none;border-bottom:1px solid {_C_BORDER};"
            f"  padding:{Spacing.XS}px {Spacing.SM - 2}px;"
            f"}}"
        )
        self.tabla.setStyleSheet(
            f"QTableWidget#tableView{{"
            f"  background:{_C_CARD_BG};"
            f"  alternate-background-color:{_C_MUTED_BG};"
            f"  color:{_C_BODY_TXT};"
            f"  gridline-color:{_C_BORDER};"
            f"  border:none;"
            f"  font-size:{Typography.SIZE_SM};"
            f"}}"
            f"QTableWidget#tableView::item{{"
            f"  padding:{Spacing.XS}px {Spacing.SM - 2}px;"
            f"  border-bottom:1px solid {_C_BORDER};"
            f"}}"
            f"QTableWidget#tableView::item:selected{{"
            f"  background:{Colors.PRIMARY.DARK};"
            f"  color:{Colors.NEUTRAL.WHITE};"
            f"}}"
        )
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setShowGrid(False)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.doubleClicked.connect(self._editar_fila)
        self.tabla.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabla.customContextMenuRequested.connect(self._menu_fila)
        self.tabla.setObjectName("tableView")

        self._cart_loading = LoadingIndicator("Actualizando carrito…", self)
        self._cart_loading.hide()
        cart_body.addWidget(self._cart_loading)
        cart_body.addWidget(self.tabla, 1)
        self._cart_empty = EmptyStateWidget(
            "Carrito vacío",
            "Escanee o use el buscador para agregar productos.",
            "🧺",
            self,
        )
        self._cart_empty.hide()
        cart_body.addWidget(self._cart_empty)

        # ── Mini action bar (Descuento / Impuestos / count) ─────────────────
        mini_bar = QFrame()
        mini_bar.setObjectName("cartMiniBar")
        mini_bar.setStyleSheet(
            f"QFrame#cartMiniBar{{"
            f"  background:transparent;"
            f"  border-top:1px solid {_C_BORDER};"
            f"}}"
        )
        mini_lay = QHBoxLayout(mini_bar)
        mini_lay.setContentsMargins(Spacing.SM + 2, Spacing.XS, Spacing.SM + 2, Spacing.XS)
        mini_lay.setSpacing(Spacing.LG)

        _link_btn_style = (
            "QPushButton{{background:transparent;border:none;text-align:left;"
            f"font-size:{Typography.SIZE_XS};"
            f"font-weight:{Typography.WEIGHT_BOLD};"
            "letter-spacing:0.03em;color:{c};}}"
            "QPushButton:hover{{text-decoration:underline;}}"
        )
        btn_desc_gral = QPushButton("%  Aplicar Descuento Gral.")
        btn_desc_gral.setFlat(True)
        btn_desc_gral.setCursor(Qt.PointingHandCursor)
        btn_desc_gral.setStyleSheet(_link_btn_style.format(c=Colors.PRIMARY_BASE))
        btn_desc_gral.clicked.connect(
            lambda: self._aplicar_descuento_global()
            if hasattr(self, '_aplicar_descuento_global') else None
        )

        btn_imp_gral = QPushButton("⚑  Ajustar Impuestos Gral.")
        btn_imp_gral.setFlat(True)
        btn_imp_gral.setCursor(Qt.PointingHandCursor)
        btn_imp_gral.setStyleSheet(_link_btn_style.format(c=Colors.WARNING_BASE))

        self._lbl_partidas_count = QLabel("0 Partidas en lista")
        self._lbl_partidas_count.setStyleSheet(
            f"font-size:{Typography.SIZE_XS};"
            f"font-weight:{Typography.WEIGHT_SEMIBOLD};"
            f"color:{_C_FIELD_LABEL};background:transparent;"
        )

        mini_lay.addWidget(btn_desc_gral)
        mini_lay.addWidget(btn_imp_gral)
        mini_lay.addStretch()
        mini_lay.addWidget(self._lbl_partidas_count)
        cart_lay_outer.addWidget(mini_bar)
        return cart_panel

    def _build_purchase_totals_footer(self) -> QFrame:
        """IVA toggle + subtotals footer. Sets up _chk_iva, lbl_total, etc."""
        footer_frame = QFrame()
        footer_frame.setObjectName("totalsFooterFrame")
        footer_frame.setStyleSheet(
            "QFrame#totalsFooterFrame{"
            f"  border:1px solid {Colors.NEUTRAL.SLATE_200};"
            f"  border-radius:{Borders.RADIUS_MD}px;"
            "}"
        )
        footer = QHBoxLayout(footer_frame)
        footer.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)
        footer.setSpacing(Spacing.SM)

        self._chk_iva = QCheckBox("IVA 16%")
        self._chk_iva.setToolTip(
            "Incluir IVA del 16% al total de la compra (Ley del IVA Mexico)")
        self._chk_iva.stateChanged.connect(lambda _: self._refresh_totals_display())
        self._lbl_subtotal_iva = QLabel("Subtotal: $0.00")
        self._lbl_subtotal_iva.setObjectName("caption")
        self._lbl_iva_monto = QLabel("IVA (16%): $0.00")
        self._lbl_iva_monto.setObjectName("caption")
        self._lbl_iva_monto.setStyleSheet(f"color:{Colors.INFO_BASE};")
        self._lbl_iva_monto.hide()
        sep_iva = QLabel("|")
        sep_iva.setObjectName("caption")
        sep_iva.hide()
        self._sep_iva = sep_iva
        self.lbl_total = QLabel("Total: $0.00")
        self.lbl_total.setObjectName("heading")
        footer.addWidget(self._chk_iva)
        footer.addSpacing(Spacing.SM)
        footer.addWidget(self._lbl_subtotal_iva)
        footer.addSpacing(Spacing.XS + 2)
        footer.addWidget(self._sep_iva)
        footer.addSpacing(Spacing.XS + 2)
        footer.addWidget(self._lbl_iva_monto)
        footer.addStretch()
        footer.addWidget(self.lbl_total)
        return footer_frame

    def _build_dynamic_action_button(self) -> QWidget:
        """Full-width primary action button + secondary draft/enviar buttons."""
        w = PurchaseDynamicActionBar()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(Spacing.XS)

        # Status badge + last edit (kept for existing update logic)
        self._lbl_estado_compra = QLabel("🔵  En captura")
        self._lbl_estado_compra.setStyleSheet(
            f"background:{Colors.INFO_BASE};"
            f"color:{Colors.NEUTRAL.WHITE};"
            f"border-radius:{Borders.RADIUS_FULL}px;"
            f"padding:{Spacing.XS - 1}px {Spacing.SM}px;"
            f"font-size:{Typography.SIZE_XS};"
            f"font-weight:{Typography.WEIGHT_BOLD};"
        )
        self._lbl_estado_compra.hide()
        self._lbl_ultima_edicion = QLabel("—")
        self._lbl_ultima_edicion.setObjectName("caption")
        self._lbl_ultima_edicion.setWordWrap(True)
        self._lbl_ultima_edicion.hide()

        # Secondary row: Borrador + Enviar a recepción
        sec_row = QHBoxLayout()
        sec_row.setSpacing(Spacing.XS)
        self._btn_draft_save_r = create_secondary_button(self, "💾 Borrador", "Guardar como borrador")
        self._btn_draft_save_r.clicked.connect(self._guardar_borrador)
        self._btn_draft_save_r.setMinimumHeight(28)
        self._btn_enviar_recepcion = create_success_button(
            self, "📨 Enviar a recepción", "Registrar y enviar a almacén")
        self._btn_enviar_recepcion.clicked.connect(self._enviar_a_recepcion)
        self._btn_enviar_recepcion.setMinimumHeight(28)
        self._btn_enviar_recepcion.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sec_row.addWidget(self._btn_draft_save_r)
        sec_row.addWidget(self._btn_enviar_recepcion, 1)
        lay.addLayout(sec_row)

        # Main action button — large, full-width, prominent
        self._btn_autorizar = create_success_button(self, "✓ Autorizar compra", "Autorizar y procesar compra")
        self._btn_autorizar.clicked.connect(self._procesar_compra)
        self._btn_autorizar.setMinimumHeight(40)
        self._btn_autorizar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_procesar = self._btn_autorizar
        lay.addWidget(self._btn_autorizar)

        # Hint text — stored as attr so _refresh_doctype_ui() can update it
        self._lbl_hint = QLabel("Flujo: Capturar → Generar PR → Aprobar PR → Generar PO → Procesar")
        self._lbl_hint.setAlignment(Qt.AlignCenter)
        self._lbl_hint.setStyleSheet(_hint_label_style())
        lay.addWidget(self._lbl_hint)

        return w

    def _build_quick_products_card(self) -> QFrame:
        """3×2 grid of emoji quick-add product buttons."""
        panel, body = _make_section_card("Productos Rápidos", panel_cls=PurchaseQuickProductsCard)
        self._quick_grid = QGridLayout()
        self._quick_grid.setSpacing(Spacing.XS)
        self._quick_grid_body = body
        body.addLayout(self._quick_grid)
        # Defer until the event loop is running so sucursal_id is final
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self._cargar_quick_products)
        return panel

    def _cargar_quick_products(self) -> None:
        """Populate quick-product grid from the 8 most frequently purchased products."""
        grid = self._quick_grid
        while grid.count():
            item = grid.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        frecuentes: list[dict] = []
        try:
            frecuentes = self._purchase_repo.get_productos_frecuentes(
                sucursal_id=self.sucursal_id, limit=8
            )
        except Exception:
            pass

        def _short(nombre: str, maxlen: int = 13) -> str:
            return nombre if len(nombre) <= maxlen else nombre[:maxlen - 1] + "…"

        if not frecuentes:
            lbl = QLabel("Realiza tu primera\ncompra para ver\nproductos frecuentes")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"color:{_C_HINT};font-size:{Typography.SIZE_XS};background:transparent;"
            )
            grid.addWidget(lbl, 0, 0, 1, 3)
        else:
            for idx, prod in enumerate(frecuentes):
                nombre = _short(prod.get("nombre") or "")
                btn = QPushButton(f"📦\n{nombre}")
                btn.setObjectName("secondaryBtn")
                btn.setFixedHeight(54)
                btn.setToolTip(prod.get("nombre") or "")
                pid = prod.get("producto_id")
                if pid:
                    btn.clicked.connect(lambda _checked, p=prod: self._add_quick_product(p))
                grid.addWidget(btn, idx // 3, idx % 3)

        # ⟳ Reload button always occupies the next free slot
        cfg_btn = QPushButton("⟳\nActualizar")
        cfg_btn.setObjectName("secondaryBtn")
        cfg_btn.setFixedHeight(54)
        cfg_btn.setToolTip("Recargar productos más comprados")
        cfg_btn.clicked.connect(self._cargar_quick_products)
        slot = len(frecuentes)
        grid.addWidget(cfg_btn, slot // 3, slot % 3)

    def _add_quick_product(self, prod: dict) -> None:
        """Fetch full product details then go through the standard _agregar_producto flow."""
        pid = prod.get("producto_id") or prod.get("id")
        if not pid:
            return
        full = None
        try:
            from repositories.productos import ProductosRepository
            full = ProductosRepository(self.container.db).get_by_id(int(pid))
        except Exception:
            pass
        if not full:
            full = {
                'id':           pid,
                'nombre':       prod.get("nombre", ""),
                'precio_compra': 0.0,
                'precio':       0.0,
                'unidad':       'pz',
                'existencia':   0,
            }
        self._agregar_producto(full)

    def _build_center_column(self) -> QWidget:
        """Center column: Captura Documental — Provider, Document, Product search."""
        center_w = PurchaseCapturePanel()
        center_w.setObjectName("purchaseCenterPanel")
        center_w.setStyleSheet(
            f"QWidget#purchaseCenterPanel{{background:{_C_PAGE_BG};}}"
            f"QWidget#centerInner{{background:{_C_PAGE_BG};}}"
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}"
            "QScrollBar:vertical{width:5px;background:transparent;}"
        )

        inner_w = QWidget()
        inner_w.setObjectName("centerInner")
        lay = QVBoxLayout(inner_w)
        lay.setSpacing(Spacing.SM)
        lay.setContentsMargins(Spacing.SM + 2, Spacing.SM, Spacing.SM + 2, Spacing.SM)

        # Doctype selector — in layout for widget lifecycle but hidden.
        # Doctype is driven by left column document selection, not a visible bar.
        self._hidden_doctype_toolbar = self._build_doctype_toolbar()
        lay.addWidget(self._hidden_doctype_toolbar)
        self._hidden_doctype_toolbar.hide()

        # FASE 6: Stepper — hidden initially (DIRECT); _refresh_doctype_ui() controls visibility
        self._hidden_stepper = self._build_stepper_bar()
        self._hidden_stepper.hide()
        lay.addWidget(self._hidden_stepper)

        lay.addWidget(self._build_provider_card())
        lay.addWidget(self._build_document_card())
        lay.addWidget(self._build_product_search_card())
        lay.addWidget(self._build_quick_products_card())

        # CxP alert banner
        self._cxp_alert_bar = QLabel("")
        self._cxp_alert_bar.setWordWrap(True)
        self._cxp_alert_bar.setObjectName("caption")
        self._cxp_alert_bar.setStyleSheet(
            f"background:{Colors.WARNING.BG_SOFT};"
            f"border:1px solid {Colors.WARNING.BORDER};"
            f"border-radius:{Borders.RADIUS_SM}px;"
            f"padding:{Spacing.XS + 1}px {Spacing.SM + 2}px;"
            f"color:{Colors.WARNING_BASE};"
            f"font-size:{Typography.SIZE_XS};"
        )
        self._cxp_alert_bar.hide()
        lay.addWidget(self._cxp_alert_bar)

        lay.addStretch()
        scroll.setWidget(inner_w)

        outer_lay = QVBoxLayout(center_w)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)
        outer_lay.addWidget(scroll, 1)

        return center_w

    def _build_tab_qr(self, parent: QWidget) -> None:
        """Tab madre con 4 sub-pestañas para el flujo de contenedores QR.

        Sub-pestañas:
          1) 🏷️ Generación etiqueta QR — identifica físicamente el contenedor.
          2) 🔗 Asignar compra — proveedor, comprador, factura, carrito de
             productos editable, método/forma de pago y sucursal destino.
          3) 📦 Recepción con QR — escanea el QR, captura cantidades recibidas,
             quién recibe y observaciones.
          4) 📚 Histórico — trazabilidad por contenedor con filtros.
        """
        self._ensure_qr_schema()

        lay = QVBoxLayout(parent)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        info_bar = QFrame()
        info_bar.setObjectName("qrFlowBanner")
        ib = QHBoxLayout(info_bar)
        ib.setContentsMargins(12, 6, 12, 6)
        ib.setSpacing(10)
        lbl_flow = QLabel(
            "🏷️  Identificar contenedor   →   🔗  Asignar compra   →   "
            "📦  Recibir   →   📚  Histórico"
        )
        lbl_flow.setObjectName("subheading")
        ib.addWidget(lbl_flow)
        ib.addStretch()
        lay.addWidget(info_bar)

        self._qr_subtabs = create_standard_tabs(self)
        lay.addWidget(self._qr_subtabs, 1)

        sub_etq = QWidget()
        self._qr_subtabs.addTab(sub_etq, "🏷️ Generación etiqueta QR")
        self._build_subtab_etiqueta(sub_etq)

        sub_asg = QWidget()
        self._qr_subtabs.addTab(sub_asg, "🔗 Asignar compra")
        self._build_subtab_asignar(sub_asg)

        sub_rec = QWidget()
        self._qr_subtabs.addTab(sub_rec, "📦 Recepción con QR")
        # Subtab builds RecepcionQRWidget wrapped with wrap_in_scroll_area (see _build_subtab_recepcion)
        self._build_subtab_recepcion(sub_rec)

        sub_hst = QWidget()
        self._qr_subtabs.addTab(sub_hst, "📚 Histórico")
        self._build_subtab_historico_qr(sub_hst)

        def _on_sub_change(idx):
            try:
                if idx == 1:
                    self._cargar_contenedores_pendientes()
                elif idx == 2:
                    self._cargar_contenedores_recepcion()
                elif idx == 3:
                    self._cargar_historico_qr()
            except (AttributeError, RuntimeError):
                pass
        self._qr_subtabs.currentChanged.connect(_on_sub_change)

    # ════════════════════════════════════════════════════════════════════════
    #   RECEPCIÓN CON QR — Enfoque por contenedor
    # ════════════════════════════════════════════════════════════════════════

    def _ensure_qr_schema(self) -> None:
        """Crea tablas para QR/contenedores si no existen. Idempotente."""
        try:
            db = self.container.db
            db.execute("""
                CREATE TABLE IF NOT EXISTS contenedores (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo          TEXT UNIQUE NOT NULL,
                    tipo            TEXT NOT NULL DEFAULT 'caja',
                    descripcion     TEXT,
                    sucursal_destino INTEGER,
                    proveedor_id    INTEGER,
                    comprador       TEXT,
                    folio_factura   TEXT,
                    fecha_factura   TEXT,
                    metodo_pago     TEXT,
                    forma_pago      TEXT,
                    plazo_dias      INTEGER DEFAULT 0,
                    vence_pago      TEXT,
                    total           REAL DEFAULT 0,
                    estado          TEXT DEFAULT 'generado',
                    fecha_creado    TEXT DEFAULT CURRENT_TIMESTAMP,
                    fecha_asignado  TEXT,
                    fecha_recibido  TEXT,
                    usuario_creado  TEXT,
                    usuario_asign   TEXT,
                    usuario_recibe  TEXT,
                    recibido_por    TEXT,
                    observaciones   TEXT,
                    compra_id       INTEGER
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS contenedor_productos (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    contenedor_id   INTEGER NOT NULL,
                    producto_id     INTEGER NOT NULL,
                    cantidad        REAL NOT NULL DEFAULT 0,
                    costo_unitario  REAL NOT NULL DEFAULT 0,
                    cantidad_recibida REAL DEFAULT NULL,
                    observaciones   TEXT,
                    FOREIGN KEY(contenedor_id) REFERENCES contenedores(id) ON DELETE CASCADE
                )
            """)
            for col_sql in [
                "ALTER TABLE contenedores ADD COLUMN comprador TEXT",
                "ALTER TABLE contenedores ADD COLUMN observaciones TEXT",
                "ALTER TABLE contenedores ADD COLUMN recibido_por TEXT",
                "ALTER TABLE contenedores ADD COLUMN sucursal_destino INTEGER",
                "ALTER TABLE contenedor_productos ADD COLUMN observaciones TEXT",
            ]:
                try:
                    db.execute(col_sql)
                except Exception:
                    pass
            try:
                db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("_ensure_qr_schema: %s", e)

    def _wrap(self, layout):
        w = QWidget()
        w.setLayout(layout)
        return w

    # ── Sub-pestaña 1: Generación etiqueta QR ──────────────────────────────
    def _build_subtab_etiqueta(self, parent: QWidget) -> None:
        lay = QHBoxLayout(parent); lay.setContentsMargins(8,8,8,8); lay.setSpacing(10)

        card_left = QGroupBox("📦 Identificación del contenedor")
        card_left.setObjectName("sectionCard")
        cl = QVBoxLayout(card_left); cl.setSpacing(10)
        cl.addWidget(create_caption(self,
            "Genera la etiqueta QR que identifica físicamente al contenedor. "
            "Los datos de compra y productos se asignan en la pestaña siguiente."))

        cl.addWidget(QLabel("Tipo de contenedor:"))
        types_row = QHBoxLayout(); types_row.setSpacing(6)
        self._qr_tipo_buttons: dict = {}
        self._qr_tipo_actual = "caja"
        for tipo, ico, lbl in [("caja","🟫","Caja"),("tarima","🛒","Tarima"),
                                ("hielera","🧊","Hielera"),("bulto","📦","Bulto")]:
            b = QPushButton(f"{ico}\n{lbl}")
            b.setCheckable(True); b.setMinimumHeight(56)
            b.setObjectName("qrTypeButton"); b.setProperty("variant","accent")
            if tipo == "caja": b.setChecked(True)
            b.clicked.connect(lambda _=False, t=tipo: self._qr_set_tipo(t))
            self._qr_tipo_buttons[tipo] = b
            types_row.addWidget(b)
        cl.addLayout(types_row)

        form = QFormLayout(); form.setSpacing(10)
        self.qr_codigo = QLineEdit(); self.qr_codigo.setReadOnly(True)
        self.qr_codigo.setObjectName("monoInput")
        btn_regen = create_secondary_button(self, "↻ Regenerar", "Genera nuevo ID")
        btn_regen.clicked.connect(self._qr_regenerar_codigo)
        row_id = QHBoxLayout(); row_id.addWidget(self.qr_codigo,1); row_id.addWidget(btn_regen)
        form.addRow("ID contenedor:", self._wrap(row_id))
        self.qr_descripcion = QLineEdit()
        self.qr_descripcion.setPlaceholderText('Ej: "Caja roja del proveedor" (opcional)')
        self.qr_descripcion.textChanged.connect(lambda _t: self._qr_actualizar_preview())
        form.addRow("Descripción:", self.qr_descripcion)
        cl.addLayout(form); cl.addStretch()

        btn_gen = create_primary_button(self, "📥 Generar QR + imprimir", "")
        btn_gen.clicked.connect(self._qr_generar_contenedor)
        cl.addWidget(btn_gen)

        card_right = QGroupBox("🏷️ Etiqueta generada")
        card_right.setObjectName("sectionCard"); card_right.setMaximumWidth(360)
        cr = QVBoxLayout(card_right); cr.setSpacing(10); cr.setAlignment(Qt.AlignTop)

        self.qr_preview_box = QFrame(); self.qr_preview_box.setObjectName("qrPreviewBox")
        pb = QHBoxLayout(self.qr_preview_box); pb.setContentsMargins(10,8,10,8)
        self.qr_preview_ic = QLabel("🟫"); self.qr_preview_ic.setObjectName("qrPreviewIcon")
        pb.addWidget(self.qr_preview_ic)
        col = QVBoxLayout(); col.setSpacing(2)
        self.qr_preview_id = QLabel("CTN-XXXX-000"); self.qr_preview_id.setObjectName("monoLabel")
        self.qr_preview_meta = QLabel("Caja"); self.qr_preview_meta.setObjectName("caption")
        col.addWidget(self.qr_preview_id); col.addWidget(self.qr_preview_meta)
        pb.addLayout(col,1)
        cr.addWidget(self.qr_preview_box)

        self.qr_preview_qr = QLabel("📷  QR")
        self.qr_preview_qr.setObjectName("qrPreviewArea")
        self.qr_preview_qr.setAlignment(Qt.AlignCenter)
        self.qr_preview_qr.setMinimumSize(220, 220)
        cr.addWidget(self.qr_preview_qr, 0, Qt.AlignCenter)

        self.qr_preview_status = QLabel("⏳ Pendiente de generar")
        self.qr_preview_status.setObjectName("statusBadge")
        self.qr_preview_status.setProperty("variant","warning")
        self.qr_preview_status.setAlignment(Qt.AlignCenter)
        cr.addWidget(self.qr_preview_status, 0, Qt.AlignCenter)

        row_btns = QHBoxLayout()
        btn_pdf = create_secondary_button(self, "💾 PDF", "Guardar etiqueta como PDF")
        btn_print = create_primary_button(self, "🖨 Imprimir", "Imprimir etiqueta")
        btn_pdf.clicked.connect(self._qr_exportar_pdf)
        btn_print.clicked.connect(self._qr_imprimir)
        row_btns.addWidget(btn_pdf); row_btns.addWidget(btn_print)
        cr.addLayout(row_btns)

        lay.addWidget(card_left, 1); lay.addWidget(card_right, 0)
        self._qr_regenerar_codigo()

    def _qr_set_tipo(self, tipo: str) -> None:
        self._qr_tipo_actual = tipo
        for t, b in self._qr_tipo_buttons.items():
            b.setChecked(t == tipo)
        ico = {"caja":"🟫","tarima":"🛒","hielera":"🧊","bulto":"📦"}.get(tipo,"📦")
        if hasattr(self,"qr_preview_ic"): self.qr_preview_ic.setText(ico)
        self._qr_actualizar_preview()

    def _qr_regenerar_codigo(self) -> None:
        suf = datetime.now().strftime("%y%m%d-%H%M%S")
        self.qr_codigo.setText(f"CTN-{suf}")
        self._qr_actualizar_preview()

    def _qr_actualizar_preview(self) -> None:
        if not hasattr(self, "qr_preview_id"): return
        self.qr_preview_id.setText(self.qr_codigo.text() or "CTN-XXXX-000")
        tipo_lbl = {"caja":"Caja","tarima":"Tarima","hielera":"Hielera",
                    "bulto":"Bulto"}.get(self._qr_tipo_actual,"Caja")
        desc = self.qr_descripcion.text().strip() if hasattr(self,"qr_descripcion") else ""
        self.qr_preview_meta.setText(f"{tipo_lbl}{(' · ' + desc) if desc else ''}")

    def _qr_generar_contenedor(self) -> None:
        codigo = (self.qr_codigo.text() or "").strip()
        if not codigo:
            QMessageBox.warning(self, "Datos faltantes", "Falta el ID del contenedor.")
            return
        try:
            db = self.container.db
            db.execute("""INSERT INTO contenedores
                (codigo, tipo, descripcion, estado, usuario_creado)
                VALUES (?,?,?,'generado',?)""",
                (codigo, self._qr_tipo_actual,
                 self.qr_descripcion.text().strip() or None,
                 self.usuario_actual or "Sistema"))
            db.commit()
            self.qr_preview_status.setText("✓ Generado · sin asignar")
            self.qr_preview_status.setProperty("variant","accent")
            self.qr_preview_status.style().unpolish(self.qr_preview_status)
            self.qr_preview_status.style().polish(self.qr_preview_status)
            try: Toast.success(self, f"Contenedor {codigo} generado").show()
            except Exception: pass
            try:
                bus = getattr(self.container, "event_bus", None)
                if bus and hasattr(bus, "publish"):
                    bus.publish("CONTENEDOR_GENERADO", {"codigo": codigo})
            except Exception: pass
            self._qr_imprimir()
            self.qr_descripcion.clear()
            self._qr_regenerar_codigo()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo generar:\n{e}")

    def _qr_exportar_pdf(self) -> None:
        QMessageBox.information(self, "PDF",
            "Exportar etiqueta a PDF (pendiente integración con QPrinter).")

    def _qr_imprimir(self) -> None:
        pass

    # ── Sub-pestaña 2: Asignar compra ──────────────────────────────────────
    def _build_subtab_asignar(self, parent: QWidget) -> None:
        lay = QHBoxLayout(parent); lay.setContentsMargins(8,8,8,8); lay.setSpacing(10)

        card_list = QGroupBox("📷 Escanear / Seleccionar contenedor")
        card_list.setObjectName("sectionCard"); card_list.setMaximumWidth(360)
        cl = QVBoxLayout(card_list); cl.setSpacing(8)
        scan_row = QHBoxLayout()
        self.qr_scan_input = QLineEdit()
        self.qr_scan_input.setPlaceholderText("📷 Escanear QR o teclear ID...")
        self.qr_scan_input.setObjectName("scanInput")
        self.qr_scan_input.returnPressed.connect(self._qr_cargar_por_codigo)
        btn_scan = create_primary_button(self, "→ Cargar", "")
        btn_scan.clicked.connect(self._qr_cargar_por_codigo)
        scan_row.addWidget(self.qr_scan_input,1); scan_row.addWidget(btn_scan)
        cl.addLayout(scan_row)
        cl.addWidget(QLabel("O selecciona de la lista:"))
        self.qr_filtro_cont = QLineEdit()
        self.qr_filtro_cont.setPlaceholderText("🔎 Filtrar por ID…")
        self.qr_filtro_cont.textChanged.connect(lambda _: self._cargar_contenedores_pendientes())
        cl.addWidget(self.qr_filtro_cont)
        self.tbl_pendientes = QTableWidget(0, 3)
        self.tbl_pendientes.setHorizontalHeaderLabels(["ID Contenedor","Tipo","Generado"])
        self.tbl_pendientes.horizontalHeader().setStretchLastSection(True)
        self.tbl_pendientes.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_pendientes.verticalHeader().setVisible(False)
        self.tbl_pendientes.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_pendientes.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_pendientes.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_pendientes.itemSelectionChanged.connect(self._on_contenedor_select)
        cl.addWidget(self.tbl_pendientes, 1)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        card_form = QGroupBox("🔗 Asignar datos comerciales"); card_form.setObjectName("sectionCard")
        cf = QVBoxLayout(card_form); cf.setSpacing(10)
        self.qr_asg_header = QLabel("⏳ Escanea o selecciona un contenedor para comenzar")
        self.qr_asg_header.setObjectName("qrAssignHeader")
        cf.addWidget(self.qr_asg_header)

        sub1 = QLabel("DATOS DEL PROVEEDOR Y COMPRADOR"); sub1.setObjectName("formSection")
        cf.addWidget(sub1)
        form_prov = QFormLayout(); form_prov.setSpacing(6)
        self.qr_proveedor = QComboBox(); self.qr_proveedor.setEditable(True)
        self._qr_cargar_proveedores_combo()
        form_prov.addRow("Proveedor:", self.qr_proveedor)
        self.qr_comprador = QLineEdit()
        self.qr_comprador.setPlaceholderText("Responsable de la compra")
        if self.usuario_actual: self.qr_comprador.setText(self.usuario_actual)
        form_prov.addRow("Comprador:", self.qr_comprador)
        self.qr_factura = QLineEdit(); self.qr_factura.setPlaceholderText("FAC-AAAA-NNNNN")
        self.qr_fecha_fact = QLineEdit(); self.qr_fecha_fact.setText(datetime.now().strftime("%Y-%m-%d"))
        row_ff = QHBoxLayout(); row_ff.addWidget(self.qr_factura,2)
        row_ff.addWidget(QLabel("Fecha:")); row_ff.addWidget(self.qr_fecha_fact,1)
        form_prov.addRow("No. Factura:", self._wrap(row_ff))
        cf.addLayout(form_prov)

        sub2 = QLabel("PRODUCTOS DEL CONTENEDOR · CARRITO"); sub2.setObjectName("formSection")
        cf.addWidget(sub2)
        from modulos.spj_product_search import ProductSearchWidget
        try:
            self.qr_buscador = ProductSearchWidget(
                db=self.container.db,
                placeholder="🔎 Buscar producto del catálogo por nombre, código o ID…",
                show_stock=False)
            sig = getattr(self.qr_buscador,"producto_seleccionado",None) or \
                  getattr(self.qr_buscador,"product_selected",None)
            if sig is not None: sig.connect(self._qr_agregar_producto_carrito)
            cf.addWidget(self.qr_buscador)
        except Exception:
            row_busc = QHBoxLayout()
            self.qr_buscador_input = QLineEdit()
            self.qr_buscador_input.setPlaceholderText("🔎 Buscar producto del catálogo…")
            btn_add = create_primary_button(self,"➕ Agregar","")
            btn_add.clicked.connect(self._qr_agregar_producto_manual)
            row_busc.addWidget(self.qr_buscador_input,1); row_busc.addWidget(btn_add)
            cf.addLayout(row_busc)

        self.tbl_qr_carrito = QTableWidget(0,7)
        self.tbl_qr_carrito.setHorizontalHeaderLabels(
            ["ID","Producto","Unidad","Volumen ✏","Costo ✏","Subtotal",""])
        h = self.tbl_qr_carrito.horizontalHeader()
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        for col in (0,2,3,4,5,6): h.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.tbl_qr_carrito.verticalHeader().setVisible(False)
        self.tbl_qr_carrito.setMinimumHeight(160)
        self.tbl_qr_carrito.itemChanged.connect(self._on_carrito_qr_changed)
        cf.addWidget(self.tbl_qr_carrito, 1)
        self._qr_carrito: list = []

        sub3 = QLabel("PAGO Y DESTINO"); sub3.setObjectName("formSection")
        cf.addWidget(sub3)
        form_pago = QFormLayout(); form_pago.setSpacing(6)
        self.qr_metodo_pago = QComboBox(); self.qr_metodo_pago.addItems(["Contado","Crédito"])
        self.qr_forma_pago = QComboBox()
        self.qr_forma_pago.addItems(["Efectivo","Transferencia","Cheque","Tarjeta"])
        row_mf = QHBoxLayout(); row_mf.addWidget(self.qr_metodo_pago,1)
        row_mf.addWidget(QLabel("Forma:")); row_mf.addWidget(self.qr_forma_pago,1)
        form_pago.addRow("Método:", self._wrap(row_mf))
        self.qr_plazo = QDoubleSpinBox(); self.qr_plazo.setRange(0,365); self.qr_plazo.setDecimals(0); self.qr_plazo.setSuffix(" días")
        self.qr_vence = QLineEdit(); self.qr_vence.setReadOnly(True)
        row_pv = QHBoxLayout(); row_pv.addWidget(self.qr_plazo,1)
        row_pv.addWidget(QLabel("Vence:")); row_pv.addWidget(self.qr_vence,1)
        self.qr_plazo.valueChanged.connect(self._qr_calcular_vencimiento)
        form_pago.addRow("Plazo:", self._wrap(row_pv))
        self.qr_sucursal_destino = QComboBox()
        try:
            for s in (self._prov_repo.get_sucursales_activas() or []):
                self.qr_sucursal_destino.addItem(str(s.get("nombre", "")), s.get("id"))
            for i in range(self.qr_sucursal_destino.count()):
                if self.qr_sucursal_destino.itemData(i) == self.sucursal_id:
                    self.qr_sucursal_destino.setCurrentIndex(i); break
        except Exception:
            self.qr_sucursal_destino.addItem("Sucursal Principal", 1)
        form_pago.addRow("Sucursal destino:", self.qr_sucursal_destino)
        cf.addLayout(form_pago)

        footer = QHBoxLayout()
        col_total = QVBoxLayout()
        l_lbl = QLabel("TOTAL CONTENEDOR"); l_lbl.setObjectName("caption")
        self.qr_total_lbl = QLabel("$0.00")
        self.qr_total_lbl.setObjectName("hero"); self.qr_total_lbl.setProperty("variant","success")
        col_total.addWidget(l_lbl); col_total.addWidget(self.qr_total_lbl)
        footer.addLayout(col_total); footer.addStretch()
        btn_guardar = create_success_button(self, "✓ Guardar y enviar a recepción", "")
        btn_guardar.clicked.connect(self._qr_guardar_asignacion)
        footer.addWidget(btn_guardar)
        cf.addLayout(footer)

        scroll.setWidget(card_form)
        lay.addWidget(card_list, 0); lay.addWidget(scroll, 1)
        self._contenedor_seleccionado_id = None

    def _qr_cargar_proveedores_combo(self) -> None:
        try:
            self.qr_proveedor.clear()
            for p in (self._prov_repo.get_activos() or []):
                self.qr_proveedor.addItem(str(p.get("nombre", "")), p.get("id"))
        except Exception:
            pass

    def _cargar_contenedores_pendientes(self) -> None:
        if not hasattr(self,"tbl_pendientes"): return
        try:
            f = (self.qr_filtro_cont.text() or "").strip()
            sql = ("SELECT id, codigo, tipo, fecha_creado FROM contenedores "
                   "WHERE estado='generado'")
            params: list = []
            if f: sql += " AND codigo LIKE ?"; params.append(f"%{f}%")
            sql += " ORDER BY fecha_creado DESC LIMIT 200"
            rows = self.container.db.execute(sql, params).fetchall()
            self.tbl_pendientes.setRowCount(0)
            ico_map = {"caja":"🟫","tarima":"🛒","hielera":"🧊","bulto":"📦"}
            for r in rows:
                cid = r["id"] if hasattr(r,"keys") else r[0]
                cod = r["codigo"] if hasattr(r,"keys") else r[1]
                tp = r["tipo"] if hasattr(r,"keys") else r[2]
                fc = r["fecha_creado"] if hasattr(r,"keys") else r[3]
                row = self.tbl_pendientes.rowCount()
                self.tbl_pendientes.insertRow(row)
                it_id = QTableWidgetItem(cod); it_id.setData(Qt.UserRole, cid)
                self.tbl_pendientes.setItem(row, 0, it_id)
                self.tbl_pendientes.setItem(row, 1, QTableWidgetItem(f"{ico_map.get(tp,'📦')} {tp}"))
                self.tbl_pendientes.setItem(row, 2, QTableWidgetItem(str(fc or "")[:16]))
        except Exception as e:
            logger.debug("_cargar_contenedores_pendientes: %s", e)

    def _on_contenedor_select(self) -> None:
        sel = self.tbl_pendientes.currentRow()
        if sel < 0: return
        it = self.tbl_pendientes.item(sel, 0)
        if not it: return
        codigo = it.text()
        if hasattr(self,"qr_scan_input"): self.qr_scan_input.setText(codigo)
        self._qr_cargar_por_codigo()

    def _qr_cargar_por_codigo(self) -> None:
        codigo = (self.qr_scan_input.text() or "").strip()
        if not codigo: return
        try:
            r = self.container.db.execute(
                "SELECT id, codigo, tipo, descripcion, estado FROM contenedores WHERE codigo=?",
                (codigo,)).fetchone()
            if not r:
                QMessageBox.warning(self,"No encontrado",
                    f"No existe un contenedor con código '{codigo}'.\n"
                    f"Genéralo primero en la pestaña 'Generación etiqueta QR'.")
                return
            est = r["estado"] if hasattr(r,"keys") else r[4]
            if est != "generado":
                if not confirm_action(self,"Contenedor ya asignado",
                    f"El contenedor '{codigo}' tiene estado '{est}'.\n"
                    f"¿Deseas reabrir su asignación?", "Reabrir","Cancelar"): return
            self._contenedor_seleccionado_id = r["id"] if hasattr(r,"keys") else r[0]
            tp = r["tipo"] if hasattr(r,"keys") else r[2]
            desc = r["descripcion"] if hasattr(r,"keys") else r[3]
            ico = {"caja":"🟫","tarima":"🛒","hielera":"🧊","bulto":"📦"}.get(tp,"📦")
            desc_sfx = f"  ·  {desc}" if desc else ""
            self.qr_asg_header.setText(f"{ico}  {codigo}   ·   {(tp or 'caja').title()}{desc_sfx}")
            self._qr_carrito.clear()
            try:
                rows = self.container.db.execute("""
                    SELECT cp.producto_id, cp.cantidad, cp.costo_unitario,
                           p.nombre, COALESCE(p.unidad,'pz') AS unidad
                    FROM contenedor_productos cp
                    JOIN productos p ON p.id = cp.producto_id
                    WHERE cp.contenedor_id=?
                """, (self._contenedor_seleccionado_id,)).fetchall()
                for pr in rows:
                    self._qr_carrito.append({
                        "producto_id": pr["producto_id"] if hasattr(pr,"keys") else pr[0],
                        "cantidad":    float(pr["cantidad"] if hasattr(pr,"keys") else pr[1] or 0),
                        "costo":       float(pr["costo_unitario"] if hasattr(pr,"keys") else pr[2] or 0),
                        "nombre":      pr["nombre"] if hasattr(pr,"keys") else pr[3],
                        "unidad":      pr["unidad"] if hasattr(pr,"keys") else pr[4],
                    })
            except Exception: pass
            self._qr_refrescar_carrito_tabla()
            self.qr_scan_input.clear()
        except Exception as e:
            QMessageBox.critical(self,"Error", str(e))

    def _qr_agregar_producto_carrito(self, producto: dict) -> None:
        if not self._contenedor_seleccionado_id:
            QMessageBox.warning(self,"Selecciona contenedor",
                "Primero elige un contenedor de la lista."); return
        pid = producto.get("id") or producto.get("producto_id")
        for it in self._qr_carrito:
            if it["producto_id"] == pid:
                it["cantidad"] += 1
                self._qr_refrescar_carrito_tabla(); return
        item = {"producto_id": pid, "nombre": producto.get("nombre",""),
                "unidad": producto.get("unidad","pz") or "pz",
                "cantidad": 1.0,
                "costo": float(producto.get("precio_compra") or producto.get("costo") or 0)}
        self._qr_carrito.append(item)
        self._qr_refrescar_carrito_tabla()

    def _qr_agregar_producto_manual(self) -> None:
        txt = (self.qr_buscador_input.text() or "").strip()
        if not txt: return
        try:
            row = self.container.db.execute("""
                SELECT id, nombre, COALESCE(unidad,'pz') AS unidad,
                       COALESCE(precio_compra, 0) AS costo
                FROM productos WHERE nombre LIKE ? OR codigo_interno=? OR barcode=? LIMIT 1
            """, (f"%{txt}%", txt, txt)).fetchone()
            if row:
                self._qr_agregar_producto_carrito(dict(row))
                self.qr_buscador_input.clear()
        except Exception: pass

    def _qr_refrescar_carrito_tabla(self) -> None:
        self.tbl_qr_carrito.blockSignals(True)
        self.tbl_qr_carrito.setRowCount(0)
        for idx, it in enumerate(self._qr_carrito):
            r = self.tbl_qr_carrito.rowCount()
            self.tbl_qr_carrito.insertRow(r)
            for col, val, editable in [
                (0, str(it["producto_id"]), False),
                (1, it["nombre"], False),
                (2, it["unidad"], False),
                (3, f"{it['cantidad']:.2f}", True),
                (4, f"{it['costo']:.2f}", True),
                (5, f"${it['cantidad']*it['costo']:.2f}", False)]:
                cell = QTableWidgetItem(val)
                if not editable: cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                if col in (3,4,5): cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tbl_qr_carrito.setItem(r, col, cell)
            btn = create_danger_button(self,"🗑","Quitar del carrito"); btn.setFixedWidth(36)
            btn.clicked.connect(lambda _=False, i=idx: self._qr_quitar_producto(i))
            self.tbl_qr_carrito.setCellWidget(r, 6, btn)
        self.tbl_qr_carrito.blockSignals(False)
        self._qr_actualizar_total()

    def _qr_quitar_producto(self, idx: int) -> None:
        try:
            self._qr_carrito.pop(idx); self._qr_refrescar_carrito_tabla()
        except Exception: pass

    def _on_carrito_qr_changed(self, item: QTableWidgetItem) -> None:
        try:
            row = item.row(); col = item.column()
            if col not in (3, 4) or row >= len(self._qr_carrito): return
            val_str = (item.text() or "").replace("$","").replace(",","").strip()
            try: val = float(val_str)
            except Exception: val = 0.0
            if val < 0: val = 0
            if col == 3: self._qr_carrito[row]["cantidad"] = val
            else: self._qr_carrito[row]["costo"] = val
            it = self._qr_carrito[row]
            sub_item = self.tbl_qr_carrito.item(row, 5)
            if sub_item:
                self.tbl_qr_carrito.blockSignals(True)
                sub_item.setText(f"${it['cantidad']*it['costo']:.2f}")
                self.tbl_qr_carrito.blockSignals(False)
            self._qr_actualizar_total()
        except Exception as e:
            logger.debug("_on_carrito_qr_changed: %s", e)

    def _qr_actualizar_total(self) -> None:
        total = sum(it["cantidad"]*it["costo"] for it in self._qr_carrito)
        if hasattr(self,"qr_total_lbl"): self.qr_total_lbl.setText(f"${total:,.2f}")

    def _qr_calcular_vencimiento(self) -> None:
        from datetime import timedelta
        try:
            base = datetime.now(); d = int(self.qr_plazo.value())
            self.qr_vence.setText((base + timedelta(days=d)).strftime("%Y-%m-%d"))
        except Exception: pass

    def _qr_guardar_asignacion(self) -> None:
        if not self._contenedor_seleccionado_id:
            QMessageBox.warning(self,"Atención","Selecciona o escanea un contenedor primero."); return
        if not self._qr_carrito:
            QMessageBox.warning(self,"Atención","Agrega al menos un producto al carrito."); return
        prov_id = self.qr_proveedor.currentData()
        if not prov_id:
            QMessageBox.warning(self,"Atención","Selecciona un proveedor."); return
        try:
            db = self.container.db
            total = sum(it["cantidad"]*it["costo"] for it in self._qr_carrito)
            db.execute("""UPDATE contenedores SET
                proveedor_id=?, comprador=?, folio_factura=?, fecha_factura=?,
                metodo_pago=?, forma_pago=?, plazo_dias=?, vence_pago=?,
                sucursal_destino=?, total=?, estado='asignado',
                fecha_asignado=CURRENT_TIMESTAMP, usuario_asign=?
                WHERE id=?""",
                (prov_id,
                 self.qr_comprador.text().strip() or self.usuario_actual or None,
                 self.qr_factura.text().strip() or None,
                 self.qr_fecha_fact.text().strip() or None,
                 self.qr_metodo_pago.currentText(),
                 self.qr_forma_pago.currentText(),
                 int(self.qr_plazo.value()),
                 self.qr_vence.text().strip() or None,
                 self.qr_sucursal_destino.currentData(),
                 total, self.usuario_actual or "Sistema",
                 self._contenedor_seleccionado_id))
            db.execute("DELETE FROM contenedor_productos WHERE contenedor_id=?",
                       (self._contenedor_seleccionado_id,))
            for it in self._qr_carrito:
                db.execute("""INSERT INTO contenedor_productos
                    (contenedor_id, producto_id, cantidad, costo_unitario)
                    VALUES (?,?,?,?)""",
                    (self._contenedor_seleccionado_id, it["producto_id"],
                     float(it["cantidad"]), float(it["costo"])))
            db.commit()
            try: Toast.success(self,"Contenedor asignado · listo para recepción").show()
            except Exception: pass
            try:
                bus = getattr(self.container,"event_bus", None)
                if bus and hasattr(bus,"publish"):
                    bus.publish("CONTENEDOR_ASIGNADO",
                                {"id": self._contenedor_seleccionado_id})
            except Exception: pass
            self._qr_carrito.clear()
            self.tbl_qr_carrito.setRowCount(0)
            self._qr_actualizar_total()
            self._contenedor_seleccionado_id = None
            self.qr_asg_header.setText("⏳ Escanea o selecciona un contenedor para comenzar")
            self.qr_factura.clear()
            self._cargar_contenedores_pendientes()
        except Exception as e:
            QMessageBox.critical(self,"Error", f"No se pudo guardar:\n{e}")

    # ── Sub-pestaña 3: Recepción con QR ────────────────────────────────────
    def _build_subtab_recepcion(self, parent: QWidget) -> None:
        from PyQt5.QtWidgets import QTextEdit
        lay = QHBoxLayout(parent); lay.setContentsMargins(8,8,8,8); lay.setSpacing(10)

        card_list = QGroupBox("📋 Contenedores asignados · pendientes de recibir")
        card_list.setObjectName("sectionCard"); card_list.setMaximumWidth(340)
        cl = QVBoxLayout(card_list); cl.setSpacing(8)
        scan_row = QHBoxLayout()
        self.qr_recv_scan = QLineEdit()
        self.qr_recv_scan.setPlaceholderText("📷 Escanear QR del contenedor…")
        self.qr_recv_scan.setObjectName("scanInput")
        self.qr_recv_scan.setProperty("variant","success")
        self.qr_recv_scan.returnPressed.connect(self._qr_recv_cargar)
        btn_recv_scan = create_primary_button(self,"→ Cargar","")
        btn_recv_scan.clicked.connect(self._qr_recv_cargar)
        scan_row.addWidget(self.qr_recv_scan,1); scan_row.addWidget(btn_recv_scan)
        cl.addLayout(scan_row)
        cl.addWidget(QLabel("O selecciona de la lista:"))
        self.qr_recv_filtro = QLineEdit()
        self.qr_recv_filtro.setPlaceholderText("🔎 Filtrar por ID, proveedor…")
        self.qr_recv_filtro.textChanged.connect(lambda _: self._cargar_contenedores_recepcion())
        cl.addWidget(self.qr_recv_filtro)
        self.tbl_recv_list = QTableWidget(0,3)
        self.tbl_recv_list.setHorizontalHeaderLabels(["ID","Proveedor","Total"])
        self.tbl_recv_list.horizontalHeader().setStretchLastSection(True)
        self.tbl_recv_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_recv_list.verticalHeader().setVisible(False)
        self.tbl_recv_list.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_recv_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_recv_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_recv_list.itemSelectionChanged.connect(self._on_recv_list_select)
        cl.addWidget(self.tbl_recv_list, 1)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        card_recv = QGroupBox("✅ Validar recepción"); card_recv.setObjectName("sectionCard")
        cr = QVBoxLayout(card_recv); cr.setSpacing(10)
        self.qr_recv_header = QLabel("⏳ Escanea o selecciona un contenedor asignado")
        self.qr_recv_header.setObjectName("qrRecvHeader")
        cr.addWidget(self.qr_recv_header)
        self.qr_recv_meta = QLabel("Proveedor — · Factura — · Comprador — · Total —")
        self.qr_recv_meta.setObjectName("caption"); self.qr_recv_meta.setWordWrap(True)
        cr.addWidget(self.qr_recv_meta)
        sub_tbl = QLabel("PRODUCTOS DEL CONTENEDOR · CAPTURA DE RECEPCIÓN")
        sub_tbl.setObjectName("formSection")
        cr.addWidget(sub_tbl)
        self.tbl_recv_items = QTableWidget(0, 6)
        self.tbl_recv_items.setHorizontalHeaderLabels(
            ["ID","Producto","Unidad","Esperado","Recibido ✏","Diferencia"])
        h2 = self.tbl_recv_items.horizontalHeader()
        h2.setSectionResizeMode(1, QHeaderView.Stretch)
        for col in (0,2,3,4,5): h2.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.tbl_recv_items.verticalHeader().setVisible(False)
        self.tbl_recv_items.setMinimumHeight(180)
        self.tbl_recv_items.itemChanged.connect(self._on_recv_items_changed)
        cr.addWidget(self.tbl_recv_items, 1)
        sub_who = QLabel("RECEPCIÓN"); sub_who.setObjectName("formSection")
        cr.addWidget(sub_who)
        form_who = QFormLayout(); form_who.setSpacing(6)
        self.qr_recv_recibe = QLineEdit()
        self.qr_recv_recibe.setPlaceholderText("Nombre de quien recibe")
        if self.usuario_actual: self.qr_recv_recibe.setText(self.usuario_actual)
        form_who.addRow("Recibe:", self.qr_recv_recibe)
        self.qr_recv_obs = QTextEdit(); self.qr_recv_obs.setMaximumHeight(70)
        self.qr_recv_obs.setPlaceholderText(
            "Observaciones (faltantes, daños, lote, temperatura, etc.)…")
        form_who.addRow("Observaciones:", self.qr_recv_obs)
        cr.addLayout(form_who)
        footer = QHBoxLayout()
        self.qr_recv_status = QLabel("⏳ Sin datos"); self.qr_recv_status.setObjectName("statusBadge")
        footer.addWidget(self.qr_recv_status); footer.addStretch()
        btn_confirmar = create_success_button(self,
            "✓ Confirmar recepción e ingresar al inventario","")
        btn_confirmar.clicked.connect(self._qr_confirmar_recepcion)
        footer.addWidget(btn_confirmar)
        cr.addLayout(footer)
        scroll.setWidget(card_recv)
        lay.addWidget(card_list,0); lay.addWidget(scroll,1)
        self._contenedor_recepcion_id = None
        self._po_recepcion_id = None

    def _cargar_contenedores_recepcion(self) -> None:
        if not hasattr(self, "tbl_recv_list"):
            return
        try:
            f = (self.qr_recv_filtro.text() or "").strip()
            self.tbl_recv_list.setRowCount(0)

            # ── POs en estado PARA_RECEPCION ──────────────────────────────────
            try:
                po_sql = """
                    SELECT oc.id, oc.folio, COALESCE(p.nombre,'—') AS proveedor,
                           COALESCE(oc.total, 0) AS total
                    FROM ordenes_compra oc
                    LEFT JOIN proveedores p ON p.id = oc.proveedor_id
                    WHERE oc.estado = 'PARA_RECEPCION'
                """
                po_params: list = []
                if f:
                    po_sql += " AND (oc.folio LIKE ? OR p.nombre LIKE ?)"
                    po_params += [f"%{f}%", f"%{f}%"]
                po_sql += " ORDER BY oc.fecha_actualizacion DESC LIMIT 100"
                po_rows = self.container.db.execute(po_sql, po_params).fetchall()
                for r in po_rows:
                    po_id   = r["id"]    if hasattr(r, "keys") else r[0]
                    folio   = r["folio"] if hasattr(r, "keys") else r[1]
                    prov    = r["proveedor"] if hasattr(r, "keys") else r[2]
                    tot     = r["total"] if hasattr(r, "keys") else r[3]
                    row = self.tbl_recv_list.rowCount()
                    self.tbl_recv_list.insertRow(row)
                    it = QTableWidgetItem(f"[PO] {folio}")
                    it.setData(Qt.UserRole, None)        # not a container
                    it.setData(Qt.UserRole + 1, po_id)   # PO id
                    it.setData(Qt.UserRole + 2, "PO")    # source type
                    self.tbl_recv_list.setItem(row, 0, it)
                    self.tbl_recv_list.setItem(row, 1, QTableWidgetItem(str(prov)))
                    tot_it = QTableWidgetItem(f"${float(tot or 0):,.2f}")
                    tot_it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.tbl_recv_list.setItem(row, 2, tot_it)
            except Exception as _pe:
                logger.debug("_cargar_contenedores_recepcion POs: %s", _pe)

            # ── Contenedores asignados ────────────────────────────────────────
            sql = """
                SELECT c.id, c.codigo, COALESCE(p.nombre,'—') AS proveedor,
                       COALESCE(c.total, 0) AS total
                FROM contenedores c
                LEFT JOIN proveedores p ON p.id = c.proveedor_id
                WHERE c.estado='asignado'
            """
            params: list = []
            if f:
                sql += " AND (c.codigo LIKE ? OR p.nombre LIKE ?)"
                params += [f"%{f}%", f"%{f}%"]
            sql += " ORDER BY c.fecha_asignado DESC LIMIT 200"
            rows = self.container.db.execute(sql, params).fetchall()
            for r in rows:
                cid = r["id"]     if hasattr(r, "keys") else r[0]
                cod = r["codigo"] if hasattr(r, "keys") else r[1]
                prov = r["proveedor"] if hasattr(r, "keys") else r[2]
                tot  = r["total"] if hasattr(r, "keys") else r[3]
                row = self.tbl_recv_list.rowCount()
                self.tbl_recv_list.insertRow(row)
                it = QTableWidgetItem(cod)
                it.setData(Qt.UserRole, cid)
                it.setData(Qt.UserRole + 2, "CTN")
                self.tbl_recv_list.setItem(row, 0, it)
                self.tbl_recv_list.setItem(row, 1, QTableWidgetItem(str(prov)))
                tot_it = QTableWidgetItem(f"${float(tot or 0):,.2f}")
                tot_it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tbl_recv_list.setItem(row, 2, tot_it)
        except Exception as e:
            logger.debug("_cargar_contenedores_recepcion: %s", e)

    def _on_recv_list_select(self) -> None:
        sel = self.tbl_recv_list.currentRow()
        if sel < 0:
            return
        it = self.tbl_recv_list.item(sel, 0)
        if not it:
            return
        source_type = it.data(Qt.UserRole + 2) or "CTN"
        if source_type == "PO":
            po_id = it.data(Qt.UserRole + 1)
            self._cargar_po_en_recepcion(po_id)
        else:
            self.qr_recv_scan.setText(it.text())
            self._qr_recv_cargar()

    def _cargar_po_en_recepcion(self, po_id: int) -> None:
        """Load a PO's line items into the reception validation table."""
        try:
            po_repo = getattr(self.container, 'purchase_order_repo', None)
            if not po_repo:
                return
            po = po_repo.get_by_id(po_id)
            if not po:
                return
            prov_row = self.container.db.execute(
                "SELECT nombre FROM proveedores WHERE id=?",
                (po.get("proveedor_id", 0),)
            ).fetchone()
            prov_nombre = prov_row[0] if prov_row else "—"
            self._contenedor_recepcion_id = None
            self._po_recepcion_id = po_id
            self.qr_recv_header.setText(f"📋  PO {po.get('folio', po_id)}")
            self.qr_recv_meta.setText(
                f"<b>{prov_nombre}</b>  ·  Folio: {po.get('folio', '—')}  ·  "
                f"Total: ${float(po.get('total', 0)):,.2f}")
            items = po.get("items", [])
            self.tbl_recv_items.blockSignals(True)
            self.tbl_recv_items.setRowCount(0)
            for item in items:
                prod_id = item.get("producto_id") or item.get("product_id", "")
                nombre  = item.get("nombre", str(prod_id))
                unidad  = item.get("unidad", "pz")
                esp     = float(item.get("cantidad", 0))
                recib   = float(item.get("recibido", esp))
                diff    = recib - esp
                row = self.tbl_recv_items.rowCount()
                self.tbl_recv_items.insertRow(row)
                c0 = QTableWidgetItem(str(prod_id)); c0.setFlags(c0.flags() & ~Qt.ItemIsEditable)
                c1 = QTableWidgetItem(nombre);       c1.setFlags(c1.flags() & ~Qt.ItemIsEditable)
                c2 = QTableWidgetItem(unidad);       c2.setFlags(c2.flags() & ~Qt.ItemIsEditable)
                c3 = QTableWidgetItem(f"{esp:.2f}"); c3.setFlags(c3.flags() & ~Qt.ItemIsEditable)
                c3.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                c4 = QTableWidgetItem(f"{recib:.2f}")
                c4.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tbl_recv_items.setItem(row, 0, c0)
                self.tbl_recv_items.setItem(row, 1, c1)
                self.tbl_recv_items.setItem(row, 2, c2)
                self.tbl_recv_items.setItem(row, 3, c3)
                self.tbl_recv_items.setItem(row, 4, c4)
                self._set_diff_cell(row, diff)
            self.tbl_recv_items.blockSignals(False)
            self._qr_recv_actualizar_status()
        except Exception as e:
            logger.warning("_cargar_po_en_recepcion: %s", e)

    def _qr_recv_cargar(self) -> None:
        codigo = (self.qr_recv_scan.text() or "").strip()
        if not codigo: return
        try:
            r = self.container.db.execute("""
                SELECT c.id, c.codigo, c.tipo, c.estado, c.total,
                       c.folio_factura, c.comprador,
                       COALESCE(p.nombre,'(sin proveedor)') AS proveedor
                FROM contenedores c
                LEFT JOIN proveedores p ON p.id = c.proveedor_id
                WHERE c.codigo=?
            """, (codigo,)).fetchone()
            if not r:
                QMessageBox.warning(self,"No encontrado", f"No existe el contenedor '{codigo}'.")
                return
            est = r["estado"] if hasattr(r,"keys") else r[3]
            if est == "generado":
                QMessageBox.warning(self,"Sin asignar",
                    f"El contenedor '{codigo}' aún no tiene compra asignada.\n"
                    f"Asígnalo primero en la pestaña 'Asignar compra'.")
                return
            self._contenedor_recepcion_id = r["id"] if hasattr(r,"keys") else r[0]
            self._po_recepcion_id = None  # loading a container clears PO context
            tp = r["tipo"] if hasattr(r,"keys") else r[2]
            tot = r["total"] if hasattr(r,"keys") else r[4]
            fact = r["folio_factura"] if hasattr(r,"keys") else r[5]
            compr = r["comprador"] if hasattr(r,"keys") else r[6]
            prov = r["proveedor"] if hasattr(r,"keys") else r[7]
            ico = {"caja":"🟫","tarima":"🛒","hielera":"🧊","bulto":"📦"}.get(tp,"📦")
            self.qr_recv_header.setText(f"{ico}  {codigo}   ·   {(tp or 'caja').title()}")
            self.qr_recv_meta.setText(
                f"<b>{prov}</b>  ·  Factura: {fact or '—'}  ·  "
                f"Comprador: {compr or '—'}  ·  Total: ${float(tot or 0):,.2f}")
            rows = self.container.db.execute("""
                SELECT cp.producto_id, cp.cantidad, cp.costo_unitario,
                       COALESCE(cp.cantidad_recibida, cp.cantidad) AS recibida,
                       p.nombre, COALESCE(p.unidad,'pz') AS unidad
                FROM contenedor_productos cp
                JOIN productos p ON p.id = cp.producto_id
                WHERE cp.contenedor_id=?
            """, (self._contenedor_recepcion_id,)).fetchall()
            self.tbl_recv_items.blockSignals(True)
            self.tbl_recv_items.setRowCount(0)
            for pr in rows:
                row = self.tbl_recv_items.rowCount()
                self.tbl_recv_items.insertRow(row)
                pid = pr["producto_id"] if hasattr(pr,"keys") else pr[0]
                esp = float(pr["cantidad"] if hasattr(pr,"keys") else pr[1] or 0)
                recib = float(pr["recibida"] if hasattr(pr,"keys") else pr[3] or esp)
                nombre = pr["nombre"] if hasattr(pr,"keys") else pr[4]
                unidad = pr["unidad"] if hasattr(pr,"keys") else pr[5]
                diff = recib - esp
                c0 = QTableWidgetItem(str(pid)); c0.setFlags(c0.flags() & ~Qt.ItemIsEditable)
                self.tbl_recv_items.setItem(row, 0, c0)
                c1 = QTableWidgetItem(nombre); c1.setFlags(c1.flags() & ~Qt.ItemIsEditable)
                self.tbl_recv_items.setItem(row, 1, c1)
                c2 = QTableWidgetItem(unidad); c2.setFlags(c2.flags() & ~Qt.ItemIsEditable)
                self.tbl_recv_items.setItem(row, 2, c2)
                c3 = QTableWidgetItem(f"{esp:.2f}"); c3.setFlags(c3.flags() & ~Qt.ItemIsEditable)
                c3.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tbl_recv_items.setItem(row, 3, c3)
                c4 = QTableWidgetItem(f"{recib:.2f}")
                c4.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tbl_recv_items.setItem(row, 4, c4)
                self._set_diff_cell(row, diff)
            self.tbl_recv_items.blockSignals(False)
            self._qr_recv_actualizar_status()
            self.qr_recv_scan.clear()
        except Exception as e:
            QMessageBox.critical(self,"Error", str(e))

    def _set_diff_cell(self, row: int, diff: float) -> None:
        if abs(diff) < 0.001:
            txt, variant = "✓ Match", "success"
        elif diff < 0:
            txt, variant = f"− {abs(diff):.2f}", "warning"
        else:
            txt, variant = f"+ {diff:.2f}", "info"
        item = QTableWidgetItem(txt)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        item.setData(Qt.UserRole, variant)
        self.tbl_recv_items.setItem(row, 5, item)

    def _on_recv_items_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 4: return
        try:
            esp_item = self.tbl_recv_items.item(item.row(), 3)
            esp = float((esp_item.text() if esp_item else "0").replace(",",""))
            recib = float((item.text() or "0").replace(",","") or 0)
            if recib < 0: recib = 0
            diff = recib - esp
            self.tbl_recv_items.blockSignals(True)
            item.setText(f"{recib:.2f}")
            self._set_diff_cell(item.row(), diff)
            self.tbl_recv_items.blockSignals(False)
            self._qr_recv_actualizar_status()
        except Exception as e:
            logger.debug("_on_recv_items_changed: %s", e)

    def _qr_recv_actualizar_status(self) -> None:
        total_items = self.tbl_recv_items.rowCount()
        match = corto = sobre = 0
        for r in range(total_items):
            esp_it = self.tbl_recv_items.item(r, 3)
            rec_it = self.tbl_recv_items.item(r, 4)
            if not esp_it or not rec_it: continue
            try:
                esp = float((esp_it.text() or "0").replace(",",""))
                rec = float((rec_it.text() or "0").replace(",",""))
                d = rec - esp
                if abs(d) < 0.001: match += 1
                elif d < 0: corto += 1
                else: sobre += 1
            except Exception: pass
        partes = [f"✓ {match} match"]
        if corto: partes.append(f"− {corto} corto")
        if sobre: partes.append(f"+ {sobre} sobre")
        self.qr_recv_status.setText("  ·  ".join(partes))

    def _qr_confirmar_recepcion(self) -> None:
        # If a PO is loaded (not a container), delegate to PO reception
        if self._po_recepcion_id and not self._contenedor_recepcion_id:
            self._confirmar_recepcion_po()
            return
        if not self._contenedor_recepcion_id:
            QMessageBox.warning(self,"Atención","Escanea o selecciona un contenedor o PO primero."); return
        if self.tbl_recv_items.rowCount() == 0:
            QMessageBox.warning(self,"Atención","El contenedor no tiene productos."); return
        if not (self.qr_recv_recibe.text() or "").strip():
            QMessageBox.warning(self,"Atención","Indica quién recibe el contenedor."); return
        hay_diferencias = False
        items_recib = []
        for r in range(self.tbl_recv_items.rowCount()):
            try:
                pid = int(self.tbl_recv_items.item(r, 0).text())
                esp = float((self.tbl_recv_items.item(r, 3).text() or "0").replace(",",""))
                rec = float((self.tbl_recv_items.item(r, 4).text() or "0").replace(",",""))
                items_recib.append((pid, rec, esp))
                if abs(rec - esp) > 0.001: hay_diferencias = True
            except Exception: pass
        if hay_diferencias:
            if not confirm_action(self,"Diferencias detectadas",
                "Hay diferencias entre lo esperado y lo recibido.\n"
                "¿Confirmar de todos modos? (se guardan las observaciones).",
                "Confirmar","Cancelar"): return
        try:
            db = self.container.db
            estado_final = "diferencia" if hay_diferencias else "recibido"
            db.execute("""UPDATE contenedores SET
                estado=?, fecha_recibido=CURRENT_TIMESTAMP,
                usuario_recibe=?, recibido_por=?, observaciones=?
                WHERE id=?""",
                (estado_final, self.usuario_actual or "Sistema",
                 self.qr_recv_recibe.text().strip(),
                 self.qr_recv_obs.toPlainText().strip() or None,
                 self._contenedor_recepcion_id))
            for pid, rec, _esp in items_recib:
                db.execute(
                    "UPDATE contenedor_productos SET cantidad_recibida=? "
                    "WHERE contenedor_id=? AND producto_id=?",
                    (rec, self._contenedor_recepcion_id, pid))
                try:
                    db.execute(
                        "UPDATE productos SET existencia=COALESCE(existencia,0)+? WHERE id=?",
                        (rec, pid))
                except Exception: pass
            db.commit()
            try: Toast.success(self, f"Contenedor recibido · estado: {estado_final}").show()
            except Exception: pass
            try:
                bus = getattr(self.container,"event_bus", None)
                if bus and hasattr(bus,"publish"):
                    bus.publish("CONTENEDOR_RECIBIDO",
                                {"id": self._contenedor_recepcion_id,
                                 "estado": estado_final})
            except Exception: pass
            self._contenedor_recepcion_id = None
            self.qr_recv_header.setText("⏳ Escanea o selecciona un contenedor asignado")
            self.qr_recv_meta.setText("Proveedor — · Factura — · Comprador — · Total —")
            self.tbl_recv_items.setRowCount(0)
            self.qr_recv_obs.clear()
            self.qr_recv_status.setText("⏳ Sin datos")
            self._cargar_contenedores_recepcion()
        except Exception as e:
            QMessageBox.critical(self,"Error", f"No se pudo confirmar:\n{e}")

    def _confirmar_recepcion_po(self) -> None:
        """Confirm reception of a PO: register stock IN and transition PO state."""
        po_id = self._po_recepcion_id
        if not po_id:
            return
        if self.tbl_recv_items.rowCount() == 0:
            QMessageBox.warning(self, "Atención", "La PO no tiene productos.")
            return
        if not (self.qr_recv_recibe.text() or "").strip():
            QMessageBox.warning(self, "Atención", "Indica quién recibe la mercancía.")
            return
        hay_diferencias = False
        items_recib = []
        for r in range(self.tbl_recv_items.rowCount()):
            try:
                pid = int(self.tbl_recv_items.item(r, 0).text())
                esp = float((self.tbl_recv_items.item(r, 3).text() or "0").replace(",", ""))
                rec = float((self.tbl_recv_items.item(r, 4).text() or "0").replace(",", ""))
                items_recib.append((pid, rec, esp))
                if abs(rec - esp) > 0.001:
                    hay_diferencias = True
            except Exception:
                pass
        if hay_diferencias:
            if not confirm_action(
                self, "Diferencias detectadas",
                "Hay diferencias entre lo esperado y lo recibido.\n"
                "¿Confirmar de todos modos?",
                "Confirmar", "Cancelar",
            ):
                return
        try:
            usuario = self.usuario_actual or "Sistema"
            svc = getattr(self.container, 'inventory_service', None)
            po_repo = getattr(self.container, 'purchase_order_repo', None)
            po = po_repo.get_by_id(po_id) if po_repo else None
            if not po:
                QMessageBox.critical(self, "Error", "PO no encontrada.")
                return
            sucursal_id = po.get("sucursal_id", self.sucursal_id or 1)
            folio = po.get("folio", str(po_id))
            warnings: list[str] = []
            if svc:
                for pid, rec, _esp in items_recib:
                    if rec <= 0:
                        continue
                    try:
                        svc.add_stock(
                            product_id=pid,
                            branch_id=sucursal_id,
                            qty=rec,
                            reference_type="RECEPCION_PO",
                            reference_id=folio,
                            operation_id=f"{folio}_{pid}",
                            user=usuario,
                            notes=f"Recepción PO {folio}",
                        )
                        if po_repo:
                            po_repo.update_item_received(po_id, pid, rec)
                    except Exception as _ie:
                        warnings.append(str(_ie))
            # Fully received → CERRADA (closed); with differences → PARCIAL for follow-up
            new_estado = "PARCIAL" if hay_diferencias else "CERRADA"
            if po_repo:
                po_repo.update_estado(po_id, new_estado)
            obs = (self.qr_recv_obs.toPlainText() or "").strip()
            try:
                from core.services.auto_audit import audit_write
                audit_write(
                    self.container,
                    modulo="COMPRAS",
                    accion="PO_RECIBIDA",
                    entidad="ordenes_compra",
                    entidad_id=folio,
                    usuario=usuario,
                    detalles=f"PO {folio} recibida por {self.qr_recv_recibe.text().strip()} · {obs}",
                    before={"estado": "PARA_RECEPCION"},
                    after={"estado": new_estado},
                    sucursal_id=sucursal_id,
                )
            except Exception:
                pass
            msg = f"PO {folio} · {'cerrada ✓' if new_estado == 'CERRADA' else 'recepción parcial — estado: PARCIAL'}"
            if warnings:
                msg += f"\nAvisos: {'; '.join(warnings)}"
            Toast.success(self, "✓ Recepción confirmada", msg)
            self._po_recepcion_id = None
            self.qr_recv_header.setText("⏳ Escanea o selecciona un contenedor asignado")
            self.qr_recv_meta.setText("Proveedor — · Factura — · Comprador — · Total —")
            self.tbl_recv_items.setRowCount(0)
            self.qr_recv_obs.clear()
            self.qr_recv_status.setText("⏳ Sin datos")
            self._cargar_contenedores_recepcion()
            self._cargar_docs_erp()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo confirmar recepción PO:\n{e}")

    # ── Sub-pestaña 4: Histórico ───────────────────────────────────────────
    def _build_subtab_historico_qr(self, parent: QWidget) -> None:
        lay = QVBoxLayout(parent); lay.setContentsMargins(8,8,8,8); lay.setSpacing(8)
        tb = QHBoxLayout(); tb.setSpacing(6)
        self.qr_hist_filtro = QLineEdit()
        self.qr_hist_filtro.setPlaceholderText("🔎 ID contenedor, proveedor, factura…")
        self.qr_hist_filtro.setMaximumWidth(260)
        self.qr_hist_estado = QComboBox()
        self.qr_hist_estado.addItem("Todos los estados", "")
        for e_val, e_lbl in [("generado","🏷️ Sin asignar"),("asignado","🔗 Asignados"),
                              ("recibido","✓ Recibidos"),("diferencia","⚠ Con diferencias")]:
            self.qr_hist_estado.addItem(e_lbl, e_val)
        btn_filtrar = create_secondary_button(self, "Filtrar", "")
        btn_filtrar.clicked.connect(self._cargar_historico_qr)
        btn_export = create_secondary_button(self, "📤 Exportar", "Exportar a CSV")
        btn_export.clicked.connect(self._qr_exportar_historico)
        tb.addWidget(self.qr_hist_filtro); tb.addWidget(self.qr_hist_estado)
        tb.addWidget(btn_filtrar); tb.addStretch(); tb.addWidget(btn_export)
        lay.addLayout(tb)

        self.tbl_qr_hist = QTableWidget(0, 9)
        self.tbl_qr_hist.setHorizontalHeaderLabels(
            ["Tipo","ID Contenedor","Proveedor","Factura","Volumen",
             "Costo total","Pago","Estado","Fecha"])
        h = self.tbl_qr_hist.horizontalHeader()
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        for col in (0,1,3,4,5,6,7,8): h.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.tbl_qr_hist.verticalHeader().setVisible(False)
        self.tbl_qr_hist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_qr_hist.setSelectionBehavior(QAbstractItemView.SelectRows)
        lay.addWidget(self.tbl_qr_hist, 1)
        QTimer.singleShot(150, self._cargar_historico_qr)

    def _cargar_historico_qr(self) -> None:
        if not hasattr(self,"tbl_qr_hist"): return
        try:
            f = (self.qr_hist_filtro.text() or "").strip()
            est = self.qr_hist_estado.currentData() or ""
            sql = """
                SELECT c.tipo, c.codigo,
                       COALESCE(p.nombre,'(sin asignar)') AS proveedor,
                       COALESCE(c.folio_factura,'—') AS factura,
                       c.total,
                       COALESCE(c.metodo_pago,'—') AS pago,
                       c.estado, COALESCE(c.fecha_asignado, c.fecha_creado) AS fecha
                FROM contenedores c
                LEFT JOIN proveedores p ON p.id = c.proveedor_id
                WHERE 1=1
            """
            params: list = []
            if f:
                sql += " AND (c.codigo LIKE ? OR p.nombre LIKE ? OR c.folio_factura LIKE ?)"
                params += [f"%{f}%"]*3
            if est:
                sql += " AND c.estado=?"; params.append(est)
            sql += " ORDER BY c.fecha_creado DESC LIMIT 500"
            rows = self.container.db.execute(sql, params).fetchall()
            self.tbl_qr_hist.setRowCount(0)
            ico_map = {"caja":"🟫","tarima":"🛒","hielera":"🧊","bulto":"📦"}
            est_map = {"generado":"🏷️ Sin asignar","asignado":"🔗 Asignado",
                       "recibido":"✓ Recibido","diferencia":"⚠ Diferencia"}
            for r in rows:
                row = self.tbl_qr_hist.rowCount()
                self.tbl_qr_hist.insertRow(row)
                tp = r["tipo"] if hasattr(r,"keys") else r[0]
                self.tbl_qr_hist.setItem(row, 0, QTableWidgetItem(ico_map.get(tp,"📦")))
                self.tbl_qr_hist.setItem(row, 1, QTableWidgetItem(
                    r["codigo"] if hasattr(r,"keys") else r[1]))
                self.tbl_qr_hist.setItem(row, 2, QTableWidgetItem(
                    r["proveedor"] if hasattr(r,"keys") else r[2]))
                self.tbl_qr_hist.setItem(row, 3, QTableWidgetItem(
                    r["factura"] if hasattr(r,"keys") else r[3]))
                self.tbl_qr_hist.setItem(row, 4, QTableWidgetItem("—"))
                tot = r["total"] if hasattr(r,"keys") else r[4]
                it_t = QTableWidgetItem(f"${float(tot or 0):,.2f}")
                it_t.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tbl_qr_hist.setItem(row, 5, it_t)
                self.tbl_qr_hist.setItem(row, 6, QTableWidgetItem(
                    r["pago"] if hasattr(r,"keys") else r[5]))
                est_v = r["estado"] if hasattr(r,"keys") else r[6]
                self.tbl_qr_hist.setItem(row, 7, QTableWidgetItem(est_map.get(est_v, est_v)))
                fch = r["fecha"] if hasattr(r,"keys") else r[7]
                self.tbl_qr_hist.setItem(row, 8, QTableWidgetItem(str(fch or "")[:16]))
        except Exception as e:
            logger.debug("_cargar_historico_qr: %s", e)

    def _qr_exportar_historico(self) -> None:
        try:
            import csv
            path, _ = QFileDialog.getSaveFileName(self,"Exportar histórico",
                "historico_qr.csv","CSV (*.csv)")
            if not path: return
            with open(path,"w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                hdr = [self.tbl_qr_hist.horizontalHeaderItem(c).text()
                       for c in range(self.tbl_qr_hist.columnCount())]
                w.writerow(hdr)
                for r in range(self.tbl_qr_hist.rowCount()):
                    w.writerow([self.tbl_qr_hist.item(r,c).text()
                                if self.tbl_qr_hist.item(r,c) else ""
                                for c in range(self.tbl_qr_hist.columnCount())])
            try: Toast.success(self,"Histórico exportado").show()
            except Exception: pass
        except Exception as e:
            QMessageBox.critical(self,"Error", str(e))

    def _build_tab_qr_legacy(self, parent: QWidget) -> None:
        from modulos.recepcion_qr_widget import RecepcionQRWidget
        lay = QVBoxLayout(parent)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        hdr = QHBoxLayout()
        hdr.addWidget(create_subheading(self, "Recepción con QR / Asignar compra"))
        hdr.addStretch()
        btn_reload = create_secondary_button(self, "🔄 Recargar", "Recargar pestaña de recepción QR")
        hdr.addWidget(btn_reload)
        lay.addLayout(hdr)

        info = create_caption(
            self,
            "Escanea QR de recepción, valida diferencias y confirma ingreso al inventario.",
        )
        lay.addWidget(info)
        self._qr_loading = LoadingIndicator("Cargando recepción con QR…", self)
        lay.addWidget(self._qr_loading)
        self._qr_empty = EmptyStateWidget(
            "Recepción QR no disponible",
            "No fue posible inicializar el widget de recepción en este momento.",
            "📦",
            self,
        )
        self._qr_empty.hide()
        lay.addWidget(self._qr_empty)

        try:
            self._recv_qr = RecepcionQRWidget(
                conexion=self.container.db,
                sucursal_id=self.sucursal_id,
                usuario=self.usuario_actual or "Sistema",
                parent=parent,
            )
            lay.addWidget(wrap_in_scroll_area(self._recv_qr, self), 1)
            self._qr_empty.hide()
            self._qr_loading.hide()
            def _reload_qr():
                if hasattr(self._recv_qr, "_recargar_listas"):
                    try:
                        self._recv_qr._recargar_listas()
                    except AttributeError:
                        pass
            btn_reload.clicked.connect(_reload_qr)
        except (ImportError, AttributeError, RuntimeError) as e:
            logger.warning("_build_tab_qr: %s", e)
            self._qr_empty.show()
            self._qr_loading.hide()

    # ── Phase 8: Toolbar Documental ERP ──────────────────────────────────────

    def _build_documental_toolbar(self) -> QWidget:
        """
        Left ERP panel: documental workflow toolbar (Phase 8).
        Top section: PR/PO document list + detail card + action buttons.
        Bottom section: provider quick-select (preserves existing logic).
        Width: 260px.
        """
        sidebar = PurchaseDocumentToolbar()
        sidebar.setObjectName("documentalToolbar")
        sidebar.setMinimumWidth(260)
        sidebar.setMaximumWidth(320)
        sidebar.setStyleSheet(
            f"QFrame#documentalToolbar{{"
            f"  background:{_C_CARD_BG};"
            f"  border-right:1px solid {_C_BORDER};"
            f"}}"
        )
        root_lay = QVBoxLayout(sidebar)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # ── State ─────────────────────────────────────────────────────────────
        self._selected_doc_id     = None
        self._selected_doc_type   = None   # 'PR' | 'PO'
        self._selected_doc_estado = None
        self._docs_erp_cache: list[dict] = []
        self._doc_filter_active   = "all"

        # ── Header strip — "Toolbar Documental ERP" ──────────────────────────
        hdr_frame = QFrame()
        hdr_frame.setObjectName("toolbarHeaderStrip")
        hdr_frame.setFixedHeight(34)
        hdr_frame.setStyleSheet(
            f"QFrame#toolbarHeaderStrip{{"
            f"  background:{_C_CARD_HDR_BG};"
            f"  border-bottom:1px solid {_C_BORDER};"
            f"}}"
        )
        hdr_lay = QHBoxLayout(hdr_frame)
        hdr_lay.setContentsMargins(Spacing.SM + 2, 0, Spacing.XS, 0)
        hdr = QLabel("📁  DOCUMENTOS ERP")
        hdr.setStyleSheet(
            f"color:{Colors.NEUTRAL.WHITE};"
            f"font-size:{Typography.SIZE_XS};"
            f"font-weight:{Typography.WEIGHT_BOLD};"
            "letter-spacing:0.1em;background:transparent;"
        )
        hdr_lay.addWidget(hdr)
        hdr_lay.addStretch()

        # Collapse / expand toggle
        self._btn_collapse_doc = QPushButton("◀")
        self._btn_collapse_doc.setFixedSize(24, 24)
        self._btn_collapse_doc.setCursor(Qt.PointingHandCursor)
        self._btn_collapse_doc.setToolTip("Ocultar / mostrar toolbar documental")
        self._btn_collapse_doc.setStyleSheet(
            f"QPushButton{{"
            f"  background:transparent;"
            f"  color:{Colors.NEUTRAL.WHITE};"
            f"  border:none;"
            f"  font-size:{Typography.SIZE_SM};"
            f"  font-weight:{Typography.WEIGHT_BOLD};"
            f"}}"
            f"QPushButton:hover{{"
            f"  background:{_C_BORDER};"
            f"  border-radius:{Borders.RADIUS_SM}px;"
            f"}}"
        )
        self._btn_collapse_doc.clicked.connect(self._toggle_documental_toolbar)
        hdr_lay.addWidget(self._btn_collapse_doc)
        root_lay.addWidget(hdr_frame)

        # Save references for collapse logic
        self._doc_toolbar_widget = sidebar
        self._doc_toolbar_header_label = hdr
        self._doc_toolbar_collapsed = False

        # ── Scrollable content ────────────────────────────────────────────────
        scroll_w = QWidget()
        scroll_w.setStyleSheet("background:transparent;")
        inner = QVBoxLayout(scroll_w)
        inner.setContentsMargins(Spacing.SM + 2, Spacing.SM, Spacing.SM + 2, Spacing.XS)
        inner.setSpacing(Spacing.SM)

        # Section title "DOCUMENTOS"
        sec_title = QLabel("DOCUMENTOS")
        sec_title.setStyleSheet(_section_label_style(_C_FIELD_LABEL))
        inner.addWidget(sec_title)

        # ── Quick actions: Nueva Compra Directa | Nueva PR ────────────────────
        new_actions_row = QHBoxLayout()
        new_actions_row.setSpacing(Spacing.XS)
        self._btn_nueva_compra_direct = create_secondary_button(
            self, "🛒 Nueva Compra", "Iniciar nueva compra directa (efecto inmediato en inventario)")
        self._btn_nueva_compra_direct.setFixedHeight(28)
        self._btn_nueva_compra_direct.clicked.connect(self._nueva_compra_directa)
        self._btn_nueva_pr_doc = create_primary_button(
            self, "✚ Nueva PR", "Nueva solicitud de compra (requiere aprobación)")
        self._btn_nueva_pr_doc.setFixedHeight(28)
        self._btn_nueva_pr_doc.clicked.connect(self._nueva_pr_flow)
        new_actions_row.addWidget(self._btn_nueva_compra_direct, 1)
        new_actions_row.addWidget(self._btn_nueva_pr_doc, 1)
        inner.addLayout(new_actions_row)

        # ── Filter chips — vertical nav (matches HTML) ────────────────────────
        self._doc_filter_chips: dict[str, QPushButton] = {}
        nav = QVBoxLayout()
        nav.setSpacing(2)
        chip_defs = [
            ("all",          "Todos"),
            ("pr_pend",      "PR pendientes"),
            ("pr_aprobadas", "PR aprobadas"),
            ("po_abiertas",  "PO abiertas"),
            ("rec_parc",     "Recepciones parciales"),
        ]
        for key, label in chip_defs:
            btn = QPushButton(label)
            btn.setObjectName(f"docNavItem_{key}")
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setChecked(key == "all")
            btn.setStyleSheet(self._doc_chip_style(key == "all"))
            btn.clicked.connect(lambda _checked, k=key: self._on_doc_filter_changed(k))
            self._doc_filter_chips[key] = btn
            nav.addWidget(btn)
        inner.addLayout(nav)

        # ── Document list (hidden by default; used when filter selected) ─────
        self._doc_erp_list = QListWidget()
        self._doc_erp_list.setObjectName("docErpList")
        self._doc_erp_list.setMaximumHeight(160)
        self._doc_erp_list.setStyleSheet(
            f"QListWidget#docErpList{{"
            f"  background:{_C_PAGE_BG};"
            f"  border:1px solid {_C_BORDER};"
            f"  border-radius:{Borders.RADIUS_SM}px;"
            f"  font-size:{Typography.SIZE_XS};"
            f"  color:{_C_BODY_TXT};outline:none;"
            f"}}"
            f"QListWidget#docErpList::item{{"
            f"  padding:{Spacing.XS}px {Spacing.SM - 2}px;"
            f"  border-bottom:1px solid {_C_BORDER};"
            f"}}"
            f"QListWidget#docErpList::item:selected{{"
            f"  background:{Colors.PRIMARY.DARK};"
            f"  color:{Colors.NEUTRAL.WHITE};"
            f"  border-left:3px solid {Colors.PRIMARY_BASE};"
            f"}}"
        )
        self._doc_erp_list.itemClicked.connect(self._on_doc_item_clicked)
        inner.addWidget(self._doc_erp_list)

        self._doc_list_empty_lbl = QLabel("Sin documentos en esta categoría")
        self._doc_list_empty_lbl.setAlignment(Qt.AlignCenter)
        self._doc_list_empty_lbl.setObjectName("caption")
        self._doc_list_empty_lbl.setStyleSheet(
            f"color:{_C_HINT};"
            f"padding:{Spacing.XS + 2}px;"
            f"font-size:{Typography.SIZE_XS};"
            "background:transparent;"
        )
        self._doc_list_empty_lbl.hide()
        inner.addWidget(self._doc_list_empty_lbl)

        # ── Detail / summary card ─────────────────────────────────────────────
        self._doc_detail_card = QFrame()
        self._doc_detail_card.setObjectName("docDetailCard")
        self._doc_detail_card.setStyleSheet(
            f"QFrame#docDetailCard{{"
            f"  background:{_C_MUTED_BG};"
            f"  border:1px solid {_C_BORDER};"
            f"  border-radius:{Borders.RADIUS_MD}px;"
            f"}}"
        )
        card_lay = QVBoxLayout(self._doc_detail_card)
        card_lay.setContentsMargins(Spacing.SM + 2, Spacing.SM, Spacing.SM + 2, Spacing.SM)
        card_lay.setSpacing(Spacing.XS + 2)

        # Folio + estado badge
        folio_row = QHBoxLayout()
        folio_col = QVBoxLayout(); folio_col.setSpacing(0)
        folio_col.addWidget(_make_field_label("Folio"))
        self._doc_lbl_folio = QLabel("—")
        self._doc_lbl_folio.setStyleSheet(
            f"font-size:{Typography.SIZE_SM};"
            f"font-weight:{Typography.WEIGHT_BOLD};"
            f"color:{_C_HEADER_TXT};background:transparent;"
        )
        folio_col.addWidget(self._doc_lbl_folio)
        folio_row.addLayout(folio_col)
        folio_row.addStretch()
        self._doc_lbl_estado_badge = QLabel("")
        self._doc_lbl_estado_badge.setAlignment(Qt.AlignCenter)
        self._doc_lbl_estado_badge.setStyleSheet(
            f"font-size:{Typography.SIZE_XS};"
            f"font-weight:{Typography.WEIGHT_BOLD};"
            f"border-radius:{Borders.RADIUS_SM}px;"
            f"padding:{Spacing.XS}px {Spacing.SM}px;background:transparent;"
        )
        folio_row.addWidget(self._doc_lbl_estado_badge)
        card_lay.addLayout(folio_row)

        # 2-col info grid
        info_grid = QGridLayout()
        info_grid.setSpacing(Spacing.XS + 2)
        info_grid.setColumnStretch(0, 1)
        info_grid.setColumnStretch(1, 1)

        def _info_field(row, col, label_txt, attr, span=1):
            box = QVBoxLayout(); box.setSpacing(0)
            box.addWidget(_make_field_label(label_txt))
            v = QLabel("—")
            v.setObjectName("caption")
            v.setWordWrap(True)
            v.setStyleSheet(
                f"font-size:{Typography.SIZE_XS};"
                f"color:{_C_BODY_TXT};background:transparent;"
            )
            setattr(self, attr, v)
            box.addWidget(v)
            info_grid.addLayout(box, row, col, 1, span)

        _info_field(0, 0, "Tipo",        "_doc_lbl_tipo_doc")
        _info_field(0, 1, "Fecha",       "_doc_lbl_fecha")
        _info_field(1, 0, "Sucursal",    "_doc_lbl_sucursal")
        _info_field(1, 1, "Vencimiento", "_doc_lbl_vence")
        _info_field(2, 0, "Solicita / Resp.", "_doc_lbl_solicitante", span=2)
        _info_field(3, 0, "Proveedor",   "_doc_lbl_proveedor_doc", span=2)
        card_lay.addLayout(info_grid)

        # Separator
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"border:none;border-top:1px solid {_C_BORDER};")
        card_lay.addWidget(sep)

        # Prioridad + Monto row
        monto_row = QHBoxLayout()
        pri_col = QVBoxLayout(); pri_col.setSpacing(0)
        pri_col.addWidget(_make_field_label("Prioridad"))
        self._doc_lbl_prioridad = QLabel("—")
        self._doc_lbl_prioridad.setStyleSheet(
            f"font-size:{Typography.SIZE_SM};"
            f"font-weight:{Typography.WEIGHT_BOLD};"
            f"color:{Colors.DANGER_BASE};background:transparent;"
        )
        pri_col.addWidget(self._doc_lbl_prioridad)
        monto_col = QVBoxLayout(); monto_col.setSpacing(0)
        m_lbl = _make_field_label("Monto"); m_lbl.setAlignment(Qt.AlignRight)
        monto_col.addWidget(m_lbl)
        self._doc_lbl_monto = QLabel("$0.00")
        self._doc_lbl_monto.setAlignment(Qt.AlignRight)
        self._doc_lbl_monto.setStyleSheet(
            f"font-size:{Typography.SIZE_XXL};"
            f"font-weight:{Typography.WEIGHT_BOLD};"
            f"color:{Colors.SUCCESS_BASE};background:transparent;"
            "letter-spacing:-0.02em;"
        )
        monto_col.addWidget(self._doc_lbl_monto)
        monto_row.addLayout(pri_col)
        monto_row.addStretch()
        monto_row.addLayout(monto_col)
        card_lay.addLayout(monto_row)

        self._doc_detail_card.hide()
        inner.addWidget(self._doc_detail_card)

        # ── Action buttons grid (2 cols, 3 rows) ─────────────────────────────
        self._doc_acciones_frame = QFrame()
        self._doc_acciones_frame.setObjectName("docAccionesFrame")
        accs = QGridLayout(self._doc_acciones_frame)
        accs.setContentsMargins(0, Spacing.XS, 0, 0)
        accs.setSpacing(Spacing.XS)

        self._btn_aprobar_pr = create_success_button(self, "✓ Aprobar PR", "Aprobar solicitud")
        self._btn_aprobar_pr.setFixedHeight(30)
        self._btn_aprobar_pr.setEnabled(False)
        self._btn_aprobar_pr.setObjectName("btnAprobarPR")
        self._btn_aprobar_pr.clicked.connect(self._accion_aprobar_pr)

        self._btn_rechazar_pr = create_danger_button(self, "✗ Rechazar", "Rechazar solicitud")
        self._btn_rechazar_pr.setFixedHeight(30)
        self._btn_rechazar_pr.setEnabled(False)
        self._btn_rechazar_pr.setObjectName("btnRechazarPR")
        self._btn_rechazar_pr.clicked.connect(self._accion_rechazar_pr)

        self._btn_editar_doc = create_secondary_button(self, "✏ Editar", "Editar documento")
        self._btn_editar_doc.setFixedHeight(30)
        self._btn_editar_doc.setEnabled(False)
        self._btn_editar_doc.setObjectName("btnEditarDoc")
        self._btn_editar_doc.clicked.connect(self._accion_editar_doc)

        self._btn_conv_po = create_primary_button(self, "→ Conv. a PO", "Convertir a Orden de Compra")
        self._btn_conv_po.setFixedHeight(30)
        self._btn_conv_po.setEnabled(False)
        self._btn_conv_po.setObjectName("btnConvPO")
        self._btn_conv_po.clicked.connect(self._accion_convertir_a_po)

        self._btn_enviar_rec_doc = create_success_button(
            self, "↗ Enviar a Recepción", "Enviar a recepción física")
        self._btn_enviar_rec_doc.setFixedHeight(32)
        self._btn_enviar_rec_doc.setEnabled(False)
        self._btn_enviar_rec_doc.setObjectName("btnEnviarRecDoc")
        self._btn_enviar_rec_doc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_enviar_rec_doc.clicked.connect(self._accion_enviar_recepcion_doc)

        accs.addWidget(self._btn_aprobar_pr,     0, 0)
        accs.addWidget(self._btn_rechazar_pr,    0, 1)
        accs.addWidget(self._btn_editar_doc,     1, 0)
        accs.addWidget(self._btn_conv_po,        1, 1)
        accs.addWidget(self._btn_enviar_rec_doc, 2, 0, 1, 2)

        self._doc_acciones_frame.hide()
        inner.addWidget(self._doc_acciones_frame)

        # Refresh button
        btn_rf = create_secondary_button(self, "↺ Actualizar documentos", "Recargar lista")
        btn_rf.setFixedHeight(26)
        btn_rf.clicked.connect(self._cargar_docs_erp)
        inner.addWidget(btn_rf)
        inner.addStretch()

        # ── Hidden widgets — kept for backward-compat with business logic ─────
        self._sidebar_prov_search = QLineEdit()
        self._sidebar_prov_search.hide()
        self._sidebar_prov_list = QListWidget()
        self._sidebar_prov_list.hide()
        self._sidebar_prov_list.itemClicked.connect(self._seleccionar_proveedor_sidebar)
        self._sidebar_templates_list = QListWidget()
        self._sidebar_templates_list.hide()
        self._sidebar_templates_list.itemDoubleClicked.connect(
            self._cargar_plantilla_sidebar
        )
        self._poblar_plantillas_sidebar()
        self._sidebar_recent_list = QListWidget()
        self._sidebar_recent_list.hide()
        self._lbl_recientes_empty = QLabel("")
        self._lbl_recientes_empty.hide()

        # Wrap content in QScrollArea
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(scroll_w)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sa.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}"
            f"QScrollBar:vertical{{width:{Spacing.XS}px;background:transparent;}}"
        )
        self._doc_toolbar_scroll = sa
        root_lay.addWidget(sa, 1)

        # Apply action-button styles after widget creation
        self._refresh_doc_btn_styles()

        QTimer.singleShot(350, self._cargar_docs_erp)
        return sidebar

    def _toggle_documental_toolbar(self) -> None:
        """Collapse / expand the left ERP documental toolbar to a rail strip.

        Moves the QSplitter handle so the center + right columns expand to
        absorb the freed width — `setMaximumWidth` alone is ignored by the
        splitter's saved sizes.
        """
        if not hasattr(self, '_doc_toolbar_widget'):
            return
        collapsed = getattr(self, '_doc_toolbar_collapsed', False)
        splitter = getattr(self, '_tradicional_splitter', None)
        RAIL_W = 34

        if collapsed:
            # ── Expand back ────────────────────────────────────────────────
            self._doc_toolbar_widget.setMinimumWidth(260)
            self._doc_toolbar_widget.setMaximumWidth(320)
            if hasattr(self, '_doc_toolbar_scroll'):
                self._doc_toolbar_scroll.show()
            if hasattr(self, '_doc_toolbar_header_label'):
                self._doc_toolbar_header_label.setText("📁  DOCUMENTOS ERP")
            self._btn_collapse_doc.setText("◀")
            self._btn_collapse_doc.setToolTip("Ocultar toolbar documental")
            if splitter is not None:
                prev = getattr(self, '_doc_toolbar_prev_sizes', None)
                if prev and len(prev) == 3:
                    splitter.setSizes(prev)
                else:
                    # Best-effort default
                    total = sum(splitter.sizes()) or 1140
                    left = 285
                    rest = total - left
                    splitter.setSizes([left, int(rest * 4 / 9), rest - int(rest * 4 / 9)])
            self._doc_toolbar_collapsed = False
        else:
            # ── Collapse to a thin rail ────────────────────────────────────
            if splitter is not None:
                self._doc_toolbar_prev_sizes = splitter.sizes()
            self._doc_toolbar_widget.setMinimumWidth(RAIL_W)
            self._doc_toolbar_widget.setMaximumWidth(RAIL_W)
            if hasattr(self, '_doc_toolbar_scroll'):
                self._doc_toolbar_scroll.hide()
            if hasattr(self, '_doc_toolbar_header_label'):
                self._doc_toolbar_header_label.setText("")
            self._btn_collapse_doc.setText("▶")
            self._btn_collapse_doc.setToolTip("Mostrar toolbar documental")
            if splitter is not None:
                sizes = splitter.sizes()
                if len(sizes) == 3:
                    freed = sizes[0] - RAIL_W
                    # Split freed width between center (4u) and right (5u)
                    add_c = int(freed * 4 / 9)
                    add_r = freed - add_c
                    splitter.setSizes([RAIL_W, sizes[1] + add_c, sizes[2] + add_r])
            self._doc_toolbar_collapsed = True

    def _doc_chip_style(self, active: bool) -> str:
        """Vertical nav-item style for documental filters (matches HTML reference)."""
        if active:
            return (
                f"QPushButton{{"
                f"  font-size:{Typography.SIZE_SM};"
                f"  font-weight:{Typography.WEIGHT_SEMIBOLD};"
                f"  text-align:left;"
                f"  padding:{Spacing.XS}px {Spacing.SM + 2}px;"
                f"  border-radius:{Borders.RADIUS_SM}px;"
                f"  background:{Colors.PRIMARY.DARK};"
                f"  color:{Colors.NEUTRAL.WHITE};"
                f"  border:1px solid {Colors.PRIMARY_BASE};"
                f"}}"
            )
        return (
            f"QPushButton{{"
            f"  font-size:{Typography.SIZE_SM};"
            f"  font-weight:{Typography.WEIGHT_MEDIUM};"
            f"  text-align:left;"
            f"  padding:{Spacing.XS}px {Spacing.SM + 2}px;"
            f"  border-radius:{Borders.RADIUS_SM}px;"
            f"  background:transparent;"
            f"  color:{_C_BODY_TXT};"
            f"  border:1px solid transparent;"
            f"}}"
            f"QPushButton:hover{{"
            f"  background:{_C_MUTED_BG};"
            f"  color:{_C_HEADER_TXT};"
            f"}}"
        )

    def _refresh_doc_btn_styles(self) -> None:
        """Set variant property on documental action buttons; QSS handles visual state."""
        _BTN_VARIANTS = {
            '_btn_aprobar_pr':  'success',
            '_btn_rechazar_pr': 'danger',
            '_btn_editar_doc':  'warning',
            '_btn_conv_po':     'primary',
            # _btn_enviar_rec_doc is create_success_button — no variant override needed
        }
        for attr, variant in _BTN_VARIANTS.items():
            btn = getattr(self, attr, None)
            if btn is None:
                continue
            btn.setProperty("variant", variant)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ── Phase 8 helpers ───────────────────────────────────────────────────────

    def _get_purchase_request_uc(self):
        """Return canonical PR UC from container or construct one lazily."""
        uc = getattr(self.container, 'uc_purchase_request', None)
        if uc is not None:
            return uc
        uc = getattr(self.container, 'purchase_request_uc', None)
        if uc is not None:
            return uc
        from application.purchases.purchase_request_uc import PurchaseRequestUC
        return PurchaseRequestUC(self.container)

    def _get_purchase_order_uc(self):
        """Return canonical PO UC from container or construct one lazily."""
        uc = getattr(self.container, 'uc_purchase_order', None)
        if uc is not None:
            return uc
        uc = getattr(self.container, 'purchase_order_uc', None)
        if uc is not None:
            return uc
        from application.purchases.purchase_order_uc import PurchaseOrderUC
        return PurchaseOrderUC(self.container)

    def _cargar_docs_erp(self) -> None:
        """Load PR/PO documents into cache from UCs or DB fallback.

        Uses PurchaseRequestUC and PurchaseOrderUC through container helpers.
        """
        docs: list[dict] = []
        try:
            pr_uc = self._get_purchase_request_uc()

            pend = pr_uc.listar_pendientes(self.sucursal_id) or []
            aprob = pr_uc.listar_aprobadas(self.sucursal_id) or []
            for d in pend:
                d['_tipo'] = 'PR'; d['_categoria'] = 'pr_pend'
                docs.append(d)
            for d in aprob:
                d['_tipo'] = 'PR'; d['_categoria'] = 'pr_aprobadas'
                docs.append(d)
        except Exception as e:
            logger.debug("_cargar_docs_erp PR: %s", e)
            try:
                rows = self.container.db.execute(
                    "SELECT id, folio, estado, proveedor_nombre, total,"
                    "       fecha_creacion, sucursal_id, usuario, notas"
                    " FROM purchase_requests"
                    " WHERE sucursal_id=? AND estado NOT IN ('CANCELADA','CONVERTIDA_A_PO')"
                    " ORDER BY fecha_creacion DESC LIMIT 40",
                    (self.sucursal_id,),
                ).fetchall()
                for r in rows:
                    def _v(i, k):
                        return r[i] if not hasattr(r, 'keys') else r.get(k)
                    estado = str(_v(2, 'estado') or '').upper()
                    cat = 'pr_pend' if estado == 'PENDIENTE_APROBACION' else 'pr_aprobadas'
                    docs.append({
                        'id':              _v(0, 'id'),
                        'folio':           _v(1, 'folio'),
                        'estado':          estado,
                        'proveedor_nombre': _v(3, 'proveedor_nombre'),
                        'total':           float(_v(4, 'total') or 0),
                        'fecha_creacion':  str(_v(5, 'fecha_creacion') or '')[:10],
                        'sucursal_id':     _v(6, 'sucursal_id'),
                        'usuario':         _v(7, 'usuario'),
                        'notas':           _v(8, 'notas'),
                        '_tipo':           'PR',
                        '_categoria':      cat,
                    })
            except Exception as e2:
                logger.debug("_cargar_docs_erp PR fallback: %s", e2)

        try:
            po_uc = self._get_purchase_order_uc()
            abiertas = po_uc.listar_abiertas(self.sucursal_id) or []
            for d in abiertas:
                d['_tipo'] = 'PO'; d['_categoria'] = 'po_abiertas'
                docs.append(d)
        except Exception as e:
            logger.debug("_cargar_docs_erp PO: %s", e)
            try:
                rows = self.container.db.execute(
                    "SELECT id, folio, estado, proveedor_id, total,"
                    "       fecha_creacion, sucursal_id, usuario, notas"
                    " FROM ordenes_compra"
                    " WHERE estado IN ('ABIERTA','PARCIAL','borrador','pendiente')"
                    " ORDER BY fecha_creacion DESC LIMIT 20",
                ).fetchall()
                for r in rows:
                    def _pv(i, k):
                        return r[i] if not hasattr(r, 'keys') else r.get(k)
                    docs.append({
                        'id':              _pv(0, 'id'),
                        'folio':           _pv(1, 'folio'),
                        'estado':          str(_pv(2, 'estado') or '').upper(),
                        'proveedor_nombre': str(_pv(3, 'proveedor_id') or ''),
                        'total':           float(_pv(4, 'total') or 0),
                        'fecha_creacion':  str(_pv(5, 'fecha_creacion') or '')[:10],
                        'sucursal_id':     _pv(6, 'sucursal_id'),
                        'usuario':         _pv(7, 'usuario'),
                        'notas':           _pv(8, 'notas'),
                        '_tipo':           'PO',
                        '_categoria':      'po_abiertas',
                    })
            except Exception as e2:
                logger.debug("_cargar_docs_erp PO fallback: %s", e2)

        self._docs_erp_cache = docs
        self._poblar_lista_docs()
        self._actualizar_chips_contadores()

    def _actualizar_chips_contadores(self) -> None:
        """Update filter chip labels with live counts."""
        counts = {'all': len(self._docs_erp_cache)}
        for cat in ('pr_pend', 'pr_aprobadas', 'po_abiertas', 'rec_parc'):
            counts[cat] = sum(1 for d in self._docs_erp_cache if d.get('_categoria') == cat)
        labels = {
            'all':          f"Todos ({counts['all']})",
            'pr_pend':      f"PR pend. ({counts['pr_pend']})",
            'pr_aprobadas': f"PR aprobadas ({counts['pr_aprobadas']})",
            'po_abiertas':  f"PO abiertas ({counts['po_abiertas']})",
            'rec_parc':     f"Rec. parciales ({counts['rec_parc']})",
        }
        for key, lbl in labels.items():
            btn = self._doc_filter_chips.get(key)
            if btn:
                btn.setText(lbl)

    def _poblar_lista_docs(self) -> None:
        """Fill the ERP document list based on active filter."""
        if not hasattr(self, '_doc_erp_list'):
            return
        cat = self._doc_filter_active
        docs = (
            self._docs_erp_cache
            if cat == 'all'
            else [d for d in self._docs_erp_cache if d.get('_categoria') == cat]
        )
        self._doc_erp_list.blockSignals(True)
        self._doc_erp_list.clear()
        if not docs:
            self._doc_erp_list.hide()
            self._doc_list_empty_lbl.show()
            self._doc_erp_list.blockSignals(False)
            return
        self._doc_list_empty_lbl.hide()
        self._doc_erp_list.show()

        _ESTADO_COLORS = {
            "PENDIENTE_APROBACION": Colors.WARNING_BASE,
            "APROBADA":             Colors.SUCCESS_BASE,
            "RECHAZADA":            Colors.DANGER_BASE,
            "CONVERTIDA_A_PO":      Colors.PRIMARY_BASE,
            "BORRADOR":             Colors.NEUTRAL.SLATE_400,
            "ABIERTA":              Colors.PRIMARY_BASE,
            "PARCIAL":              Colors.WARNING_BASE,
            "RECIBIDA":             Colors.SUCCESS_BASE,
            "CERRADA":              Colors.NEUTRAL.SLATE_500,
            "CANCELADA":            Colors.DANGER_BASE,
        }

        for doc in docs:
            tipo   = doc.get('_tipo', '?')
            folio  = str(doc.get('folio') or doc.get('id') or '—')
            estado = str(doc.get('estado') or '').upper()
            prov   = str(doc.get('proveedor_nombre') or '—')[:22]
            total  = float(doc.get('total') or 0)
            fecha  = str(doc.get('fecha_creacion') or '')[:10]
            icon   = '📋' if tipo == 'PR' else '📦'
            color  = _ESTADO_COLORS.get(estado, Colors.NEUTRAL.SLATE_400)
            line1  = f"{icon} {folio}"
            line2  = f"   {prov}  ${total:,.0f}"
            item   = QListWidgetItem(f"{line1}\n{line2}")
            item.setData(Qt.UserRole,     doc.get('id'))
            item.setData(Qt.UserRole + 1, tipo)
            item.setData(Qt.UserRole + 2, doc)
            item.setToolTip(
                f"{tipo}: {folio}\nEstado: {estado}\n"
                f"Proveedor: {prov}\nTotal: ${total:,.2f}\nFecha: {fecha}"
            )
            self._doc_erp_list.addItem(item)
        self._doc_erp_list.blockSignals(False)

    def _on_doc_filter_changed(self, key: str) -> None:
        """Handle filter chip click."""
        self._doc_filter_active = key
        for k, btn in self._doc_filter_chips.items():
            btn.setChecked(k == key)
            btn.setStyleSheet(self._doc_chip_style(k == key))
        self._poblar_lista_docs()

    def _on_doc_item_clicked(self, item: QListWidgetItem) -> None:
        """Populate detail card and enable context-sensitive action buttons."""
        doc = item.data(Qt.UserRole + 2)
        if not doc:
            return
        self._selected_doc_id     = item.data(Qt.UserRole)
        self._selected_doc_type   = item.data(Qt.UserRole + 1)
        self._selected_doc_estado = str(doc.get('estado') or '').upper()
        self._refresh_doc_detail(doc)
        self._refresh_doc_acciones()
        # FASE 7: update stepper to reflect selected document's workflow position
        self._refresh_stepper_for_doc(self._selected_doc_estado, self._selected_doc_type or '')

    def _refresh_doc_detail(self, doc: dict) -> None:
        """Populate the detail card with selected document data."""
        tipo    = doc.get('_tipo', '?')
        folio   = str(doc.get('folio') or doc.get('id') or '—')
        estado  = str(doc.get('estado') or '').upper()
        prov    = str(doc.get('proveedor_nombre') or '—')
        total   = float(doc.get('total') or 0)
        fecha   = str(doc.get('fecha_creacion') or '')[:10]
        suc     = str(doc.get('sucursal_nombre') or doc.get('sucursal_id') or '—')
        solic   = str(doc.get('usuario') or doc.get('solicitante') or '—')
        prior   = str(doc.get('prioridad') or doc.get('priority') or '')

        # Folio + tipo
        self._doc_lbl_folio.setText(f"{'📋' if tipo == 'PR' else '📦'} {folio}")

        # Estado badge color
        _BADGE_STYLES = {
            "PENDIENTE_APROBACION": (Colors.WARNING_BASE,  f"{Colors.WARNING_BASE}22"),
            "APROBADA":             (Colors.SUCCESS_BASE,  f"{Colors.SUCCESS_BASE}22"),
            "RECHAZADA":            (Colors.DANGER_BASE,   f"{Colors.DANGER_BASE}22"),
            "CONVERTIDA_A_PO":      (Colors.PRIMARY_BASE,  f"{Colors.PRIMARY_BASE}22"),
            "BORRADOR":             (Colors.NEUTRAL.SLATE_500, Colors.NEUTRAL.SLATE_100),
            "ABIERTA":              (Colors.PRIMARY_BASE,  f"{Colors.PRIMARY_BASE}22"),
            "PARCIAL":              (Colors.WARNING_BASE,  f"{Colors.WARNING_BASE}22"),
            "RECIBIDA":             (Colors.SUCCESS_BASE,  f"{Colors.SUCCESS_BASE}22"),
            "CANCELADA":            (Colors.DANGER_BASE,   f"{Colors.DANGER_BASE}22"),
        }
        fg, bg = _BADGE_STYLES.get(estado, (Colors.NEUTRAL.SLATE_500, Colors.NEUTRAL.SLATE_100))
        short_estado = {
            "PENDIENTE_APROBACION": "PENDIENTE",
            "CONVERTIDA_A_PO":      "CONV.PO",
        }.get(estado, estado)
        self._doc_lbl_estado_badge.setText(short_estado)
        self._doc_lbl_estado_badge.setStyleSheet(
            f"font-size:{Typography.SIZE_XS};"
            f"font-weight:{Typography.WEIGHT_BOLD};"
            f"border-radius:{Borders.RADIUS_SM}px;"
            f"padding:{Spacing.XS - 2}px {Spacing.XS + 2}px;"
            f"background:{bg};color:{fg};"
        )

        self._doc_lbl_fecha.setText(fecha or "—")
        self._doc_lbl_sucursal.setText(suc)
        self._doc_lbl_solicitante.setText(solic[:24] or "—")
        self._doc_lbl_proveedor_doc.setText(prov[:28])
        self._doc_lbl_monto.setText(f"${total:,.2f}")

        if prior:
            self._doc_lbl_prioridad.setText(prior.upper())
            self._doc_lbl_prioridad.show()
        else:
            self._doc_lbl_prioridad.hide()

        self._doc_detail_card.show()
        self._doc_acciones_frame.show()

    def _refresh_doc_acciones(self) -> None:
        """Enable/disable action buttons based on selected document state + permissions."""
        if not hasattr(self, '_btn_aprobar_pr'):
            return
        tipo   = self._selected_doc_type
        estado = self._selected_doc_estado or ''

        puede_aprobar  = tipo == 'PR' and estado == 'PENDIENTE_APROBACION'
        puede_rechazar = tipo == 'PR' and estado == 'PENDIENTE_APROBACION'
        puede_editar   = tipo == 'PR' and estado in ('BORRADOR',)
        puede_conv_po  = tipo == 'PR' and estado == 'APROBADA'
        puede_enviar   = tipo == 'PO' and estado in ('ABIERTA', 'PARCIAL', 'abierta', 'parcial')

        # Permission guard
        if not self._tiene_permiso("admin") and not self._tiene_permiso("compras_aprobar"):
            puede_aprobar = puede_rechazar = puede_conv_po = False

        self._btn_aprobar_pr.setEnabled(puede_aprobar)
        self._btn_rechazar_pr.setEnabled(puede_rechazar)
        self._btn_editar_doc.setEnabled(puede_editar)
        self._btn_conv_po.setEnabled(puede_conv_po)
        self._btn_enviar_rec_doc.setEnabled(puede_enviar)
        self._refresh_doc_btn_styles()

    def _accion_aprobar_pr(self) -> None:
        """Approve selected PR."""
        pr_id = self._selected_doc_id
        if not pr_id:
            return
        try:
            # PurchaseRequestUC via canonical helper
            uc = self._get_purchase_request_uc()
            result = uc.aprobar(pr_id, self.usuario_actual or "sistema")
            if result.ok:
                Toast.success(self, "✓ PR Aprobada",
                              f"Folio: {result.folio} aprobado")
                self._cargar_docs_erp()
            else:
                QMessageBox.warning(self, "Error al aprobar", result.error or "No se pudo aprobar")
        except Exception as e:
            logger.warning("_accion_aprobar_pr: %s", e)
            QMessageBox.critical(self, "Error", str(e))

    def _accion_rechazar_pr(self) -> None:
        """Reject selected PR with a reason dialog."""
        pr_id = self._selected_doc_id
        if not pr_id:
            return
        motivo, ok = QInputDialog.getText(
            self, "Rechazar PR",
            "Motivo del rechazo (requerido):",
            QLineEdit.Normal, ""
        )
        if not ok or not motivo.strip():
            return
        try:
            # PurchaseRequestUC via canonical helper
            uc = self._get_purchase_request_uc()
            result = uc.rechazar(pr_id, self.usuario_actual or "sistema", motivo.strip())
            if result.ok:
                Toast.info(self, "✗ PR Rechazada",
                           f"Folio: {result.folio} rechazado — {motivo[:40]}")
                self._cargar_docs_erp()
            else:
                QMessageBox.warning(self, "Error al rechazar", result.error or "No se pudo rechazar")
        except Exception as e:
            logger.warning("_accion_rechazar_pr: %s", e)
            QMessageBox.critical(self, "Error", str(e))

    def _accion_editar_doc(self) -> None:
        """Load selected PR/PO data into the center form for editing."""
        pr_id = self._selected_doc_id
        if not pr_id or self._selected_doc_type != 'PR':
            return
        try:
            uc  = self._get_purchase_request_uc()
            doc = uc.get_pr(pr_id)
            if not doc:
                QMessageBox.warning(self, "No encontrado", f"PR {pr_id} no encontrada"); return

            # Load provider
            prov_id   = doc.get('proveedor_id')
            prov_nom  = str(doc.get('proveedor_nombre') or '')
            if prov_id:
                self._proveedor_id_selected = prov_id
                if hasattr(self, 'txt_proveedor'):
                    self.txt_proveedor.setText(prov_nom)
                if hasattr(self, '_lbl_prov_status'):
                    self._lbl_prov_status.setText(f"✔ {prov_nom}")
                    self._lbl_prov_status.setStyleSheet(
                        f"color:{Colors.SUCCESS_BASE};"
                    )

            # Load document ref
            if doc.get('doc_ref') and hasattr(self, 'txt_factura'):
                self.txt_factura.setText(str(doc['doc_ref']))

            # Load items into cart
            items_raw = doc.get('items') or []
            pr_repo = getattr(self.container, 'purchase_request_repo', None)
            if not items_raw and pr_repo and hasattr(pr_repo, 'get_items'):
                items_raw = pr_repo.get_items(pr_id) or []

            if items_raw:
                if self.carrito_compra and not confirm_action(
                    self, "Cargar PR",
                    f"¿Reemplazar el carrito actual con {len(items_raw)} ítem(s) de la PR?",
                    "Reemplazar", "Cancelar"
                ):
                    return
                self.carrito_compra.clear()
                for it in items_raw:
                    qty  = float(it.get('cantidad')       or 0)
                    cost = float(it.get('precio_unitario') or 0)
                    self.carrito_compra.append({
                        'producto_id':   it.get('producto_id'),
                        'nombre':        str(it.get('nombre') or ''),
                        'unidad':        str(it.get('unidad') or 'kg'),
                        'cantidad':      qty,
                        'costo_unitario':cost,
                        'descuento':     float(it.get('descuento') or 0),
                        'subtotal':      round(qty * cost, 4),
                    })
                self._refresh_tabla()

            Toast.info(self, "📋 PR cargada",
                       f"Folio {doc.get('folio',pr_id)} cargado en el formulario")
            self._refresh_stepper()
        except Exception as e:
            logger.warning("_accion_editar_doc: %s", e)
            QMessageBox.critical(self, "Error al cargar PR", str(e))

    def _accion_convertir_a_po(self) -> None:
        """Convert selected approved PR to a PO."""
        pr_id = self._selected_doc_id
        if not pr_id:
            return
        try:
            # PurchaseRequestUC via canonical helper
            uc     = self._get_purchase_request_uc()
            result = uc.convertir_a_po(pr_id, self.usuario_actual or "sistema")
            if result.ok:
                po_folio = str(result.po_folio if hasattr(result, 'po_folio') else result.folio or '')
                Toast.success(self, "📦 PO Generada",
                              f"PR convertida → PO {po_folio}" if po_folio else "PO generada")
                self._cargar_docs_erp()
            else:
                QMessageBox.warning(self, "Error", result.error or "No se pudo convertir a PO")
        except Exception as e:
            logger.warning("_accion_convertir_a_po: %s", e)
            QMessageBox.critical(self, "Error", str(e))

    def _accion_enviar_recepcion_doc(self) -> None:
        """Mark selected PO as PARA_RECEPCION and navigate to QR reception subtab."""
        po_id = self._selected_doc_id
        if not po_id:
            return
        try:
            uc     = self._get_purchase_order_uc()
            result = uc.enviar_a_recepcion(po_id, self.usuario_actual or "sistema")
            if result.ok:
                po_folio = getattr(result, 'po_folio', None) or getattr(result, 'folio', str(po_id))
                Toast.success(self, "↗ Enviada a recepción",
                              f"PO {po_folio} · aparece en lista de recepción")
                self._cargar_docs_erp()
                # Switch to QR tab → "Recepción con QR" subtab (index 2)
                if hasattr(self, '_tabs'):
                    self._tabs.setCurrentIndex(1)
                    QTimer.singleShot(80, self._navegar_a_recepcion_qr)
            else:
                QMessageBox.warning(self, "Error", result.error or "No se pudo enviar a recepción")
        except Exception as e:
            logger.warning("_accion_enviar_recepcion_doc: %s", e)
            QMessageBox.critical(self, "Error", str(e))

    def _navegar_a_recepcion_qr(self) -> None:
        """Switch to 'Recepción con QR' subtab (index 2) within the QR tab."""
        try:
            if hasattr(self, '_qr_subtabs'):
                self._qr_subtabs.setCurrentIndex(2)
                self._cargar_contenedores_recepcion()
        except Exception as e:
            logger.debug("_navegar_a_recepcion_qr: %s", e)

    # ── Right summary panel ───────────────────────────────────────────────────

    def _build_summary_panel(self) -> QWidget:
        """Right column: items table (flex-1) + totals footer (fixed) + action button."""
        panel = PurchaseItemsAndTotalsPanel()
        panel.setObjectName("purchaseRightPanel")
        panel.setStyleSheet(
            f"QFrame#purchaseRightPanel{{background:{_C_PAGE_BG};}}"
        )
        panel.setMinimumWidth(420)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(Spacing.XS, Spacing.XS, Spacing.XS, Spacing.XS)
        lay.setSpacing(Spacing.XS)

        # Items panel — gets a min height so cart is always usable; stretches.
        items_panel = self._build_purchase_items_panel()
        items_panel.setMinimumHeight(240)
        items_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(items_panel, 1)

        # ── Totals footer card ───────────────────────────────────────────────
        totals_card = PurchaseTotalsFooter()
        totals_card.setObjectName("sectionCard")
        totals_card.setStyleSheet(
            f"QFrame#sectionCard{{"
            f"  background:{_C_CARD_BG};"
            f"  border:1px solid {_C_BORDER};"
            f"  border-radius:{Borders.RADIUS_MD}px;"
            f"}}"
        )
        tc_lay = QVBoxLayout(totals_card)
        tc_lay.setContentsMargins(Spacing.SM + 2, Spacing.XS + 2, Spacing.SM + 2, Spacing.XS + 2)
        tc_lay.setSpacing(Spacing.XS)

        def _fv(initial="$0.00", color=None) -> QLabel:
            l = QLabel(initial)
            l.setObjectName("caption")
            base = (
                f"font-family:'JetBrains Mono','Consolas',monospace;"
                f"font-size:{Typography.SIZE_SM};"
                f"font-weight:{Typography.WEIGHT_SEMIBOLD};"
                "background:transparent;"
            )
            l.setStyleSheet(base + (f"color:{color};" if color else ""))
            return l

        # Totals 2-col grid
        tgrid = QGridLayout()
        tgrid.setSpacing(Spacing.XS)
        tgrid.setColumnStretch(0, 1)
        tgrid.setColumnStretch(1, 1)

        self._sum_subtotal_lbl  = _fv()
        self._sum_descuento_lbl = _fv(color=Colors.WARNING_BASE)
        self._sum_iva_lbl       = _fv(color=Colors.INFO_BASE)
        self._sum_iva_lbl.hide()
        self._sum_flete_lbl     = _fv()
        self._sum_otros_lbl     = _fv()
        self._sum_items_lbl     = QLabel("0 productos");   self._sum_items_lbl.setObjectName("caption")
        self._sum_peso_lbl      = QLabel("Peso est.: —");   self._sum_peso_lbl.setObjectName("caption")
        self._sum_costo_kg_lbl  = QLabel("Costo/kg: —");    self._sum_costo_kg_lbl.setObjectName("caption")

        tgrid.addWidget(_make_field_label("Subtotal"),         0, 0)
        tgrid.addWidget(_make_field_label("Descuento"),        0, 1)
        tgrid.addWidget(self._sum_subtotal_lbl,                1, 0)
        tgrid.addWidget(self._sum_descuento_lbl,               1, 1)
        tgrid.addWidget(_make_field_label("Impuestos (IVA)"),  2, 0)
        tgrid.addWidget(_make_field_label("Flete / Otros"),    2, 1)
        tgrid.addWidget(self._sum_iva_lbl,                     3, 0)
        tgrid.addWidget(self._sum_flete_lbl,                   3, 1)
        tc_lay.addLayout(tgrid)

        # IVA checkbox (hidden but required by existing logic)
        self._chk_iva = QCheckBox("IVA 16%")
        self._chk_iva.stateChanged.connect(lambda _: self._refresh_totals_display())
        self._chk_iva.hide()
        self._lbl_subtotal_iva = QLabel(""); self._lbl_subtotal_iva.hide()
        self._lbl_iva_monto = self._sum_iva_lbl
        sep_iva = QLabel(""); sep_iva.hide()
        self._sep_iva = sep_iva
        tc_lay.addWidget(self._chk_iva)

        # Cargo spinboxes (hidden — exist for business logic)
        self._spin_flete = QDoubleSpinBox(); self._spin_flete.setRange(0, 999999)
        self._spin_flete.setDecimals(2); self._spin_flete.setPrefix("$ ")
        self._spin_flete.valueChanged.connect(self._refresh_totals_display)
        self._spin_flete.hide()
        self._spin_otros = QDoubleSpinBox(); self._spin_otros.setRange(0, 999999)
        self._spin_otros.setDecimals(2); self._spin_otros.setPrefix("$ ")
        self._spin_otros.valueChanged.connect(self._refresh_totals_display)
        self._spin_otros.hide()

        # Validation labels (hidden)
        self._val_prov_lbl    = QLabel("⚠ Proveedor"); self._val_prov_lbl.hide()
        self._val_prod_lbl    = QLabel("⚠ Productos"); self._val_prod_lbl.hide()
        self._val_total_v_lbl = QLabel("⚠ Total cero"); self._val_total_v_lbl.hide()
        for l in (self._val_prov_lbl, self._val_prod_lbl, self._val_total_v_lbl):
            l.setObjectName("caption")

        # Separator
        sep_line = QFrame(); sep_line.setFrameShape(QFrame.HLine)
        sep_line.setStyleSheet(f"border:none;border-top:1px solid {_C_BORDER};")
        tc_lay.addWidget(sep_line)

        # ── Total + payment row ─────────────────────────────────────────────
        total_pay_row = QHBoxLayout()
        total_pay_row.setSpacing(Spacing.SM)

        total_col = QVBoxLayout()
        total_col.setSpacing(2)
        lbl_total_hdr = _make_field_label("Total Documento")
        self.lbl_total = QLabel("$0.00")
        self.lbl_total.setStyleSheet(
            f"font-family:'JetBrains Mono','Consolas',monospace;"
            f"font-size:{Typography.SIZE_XXL};"
            f"font-weight:{Typography.WEIGHT_BOLD};"
            f"color:{Colors.ACCENT_BASE};"
            "background:transparent;letter-spacing:-0.02em;"
        )
        self._sum_total_lbl = self.lbl_total
        total_col.addWidget(lbl_total_hdr)
        total_col.addWidget(self.lbl_total)
        total_col.addWidget(self._sum_costo_kg_lbl)
        total_pay_row.addLayout(total_col, 1)

        pay_col = QGridLayout()
        pay_col.setSpacing(Spacing.XS)
        pay_col.setColumnStretch(0, 1)
        pay_col.setColumnStretch(1, 1)

        self.cmb_pago = create_combo(self)
        for label, data in _PAGO_ITEMS:
            self.cmb_pago.addItem(label, data)
        self._cmb_condicion_pago = create_combo(self)
        self._cmb_condicion_pago.addItems(["Liquidado", "Crédito", "Parcial"])
        self._spin_plazo_dias = QSpinBox()
        self._spin_plazo_dias.setRange(0, 365)
        self._spin_plazo_dias.setSuffix(" días")
        self._spin_plazo_dias.setValue(30)
        self._spin_plazo_dias.setObjectName("standardInput")
        self._lbl_vence_el = QLabel("—")
        self._lbl_vence_el.setObjectName("caption")
        self._lbl_vence_el.setStyleSheet(
            f"font-size:{Typography.SIZE_XS};color:{_C_BODY_TXT};background:transparent;"
        )

        pay_col.addWidget(_make_field_label("Método / Forma"), 0, 0, 1, 2)
        pay_col.addWidget(self.cmb_pago,                       1, 0, 1, 2)
        pay_col.addWidget(_make_field_label("Plazo"),          2, 0)
        pay_col.addWidget(_make_field_label("Vence"),          2, 1)
        pay_col.addWidget(self._spin_plazo_dias,               3, 0)
        pay_col.addWidget(self._lbl_vence_el,                  3, 1)

        self._cmb_condicion_pago.currentTextChanged.connect(self._on_condicion_changed)
        self._spin_plazo_dias.valueChanged.connect(self._on_plazo_changed)

        total_pay_row.addLayout(pay_col, 1)
        tc_lay.addLayout(total_pay_row)
        lay.addWidget(totals_card)

        # Main action button — full width, large
        lay.addWidget(self._build_dynamic_action_button())

        # ── Wrap in QScrollArea so the column always reaches its action button
        # even when the cart table grows or the window height is short.
        scroll = QScrollArea()
        scroll.setObjectName("rightColScroll")
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea#rightColScroll{{"
            f"  background:{_C_PAGE_BG};border:none;"
            f"}}"
            f"QScrollBar:vertical{{"
            f"  width:{Spacing.SM}px;background:transparent;"
            f"}}"
            f"QScrollBar::handle:vertical{{"
            f"  background:{_C_BORDER};"
            f"  border-radius:{Borders.RADIUS_SM - 1}px;"
            f"}}"
        )
        return scroll

    def _poblar_sidebar_proveedores(self) -> None:
        """Populates sidebar provider list from _proveedores_cache."""
        if not hasattr(self, '_sidebar_prov_list'):
            return
        search = getattr(self, '_sidebar_prov_search', None)
        txt = search.text().strip().lower() if search else ""
        self._sidebar_prov_list.blockSignals(True)
        self._sidebar_prov_list.clear()
        for prov in self._proveedores_cache:
            if txt and txt not in prov['nombre'].lower():
                continue
            item = QListWidgetItem(prov['nombre'])
            item.setData(Qt.UserRole, prov['id'])
            credito = prov.get('condicion_pago', prov.get('credito', ''))
            if credito:
                item.setToolTip(f"{prov['nombre']}\n{credito}")
            # Highlight currently selected provider
            if prov['id'] == self._proveedor_id_selected:
                item.setSelected(True)
            self._sidebar_prov_list.addItem(item)
        self._sidebar_prov_list.blockSignals(False)

    def _filtrar_sidebar_proveedores(self, _=None) -> None:
        if not hasattr(self, '_sidebar_filter_timer'):
            self._sidebar_filter_timer = QTimer(self)
            self._sidebar_filter_timer.setSingleShot(True)
            self._sidebar_filter_timer.timeout.connect(self._poblar_sidebar_proveedores)
        self._sidebar_filter_timer.start(200)

    def _seleccionar_proveedor_sidebar(self, item: QListWidgetItem) -> None:
        """Click on sidebar provider: delegates to canonical _seleccionar_proveedor."""
        prov_id = item.data(Qt.UserRole)
        if prov_id is not None:
            self._seleccionar_proveedor(prov_id, item.text())

    def _cargar_info_proveedor(self, prov_id: int) -> None:
        """Show RFC / address / phone under provider field after selection.

        La columna de condición de pago varía entre instancias:
        - condicion_pago  (nombre antiguo, algunas DBs)
        - condiciones_pago (nombre migración 047, plural)
        Se usa SELECT * y se extrae por clave para evitar OperationalError.
        """
        if not hasattr(self, '_lbl_prov_info'):
            return
        try:
            row = self.container.db.execute(
                "SELECT * FROM proveedores WHERE id=?", (prov_id,)
            ).fetchone()
            if not row:
                self._lbl_prov_info.hide()
                return

            # Normalize to plain dict regardless of row_factory
            if hasattr(row, 'keys'):
                data = {k: row[k] for k in row.keys()}
            elif hasattr(row, '_fields'):
                data = row._asdict()
            else:
                data = dict(row) if isinstance(row, dict) else {}

            def _k(*keys):
                for k in keys:
                    v = data.get(k)
                    if v is not None and str(v).strip():
                        return str(v).strip()
                return ""

            rfc  = _k('rfc')
            dirs = _k('direccion')
            tel  = _k('telefono')
            cond = _k('condicion_pago', 'condiciones_pago')
            cred = _k('credito_disponible', 'limite_credito', 'credito')

            # Populate individual display labels
            if hasattr(self, '_lbl_rfc'):
                self._lbl_rfc.setText(rfc or "—")
            if hasattr(self, '_lbl_tel'):
                self._lbl_tel.setText(tel or "—")
            if hasattr(self, '_lbl_dir'):
                self._lbl_dir.setText(dirs[:60] if dirs else "—")
            if hasattr(self, '_lbl_cred_disp'):
                self._lbl_cred_disp.setText(cred or "—")
            if hasattr(self, '_cmb_cond_prov') and cond:
                idx = self._cmb_cond_prov.findText(cond, Qt.MatchContains)
                if idx < 0:
                    self._cmb_cond_prov.insertItem(0, cond)
                    idx = 0
                self._cmb_cond_prov.setCurrentIndex(idx)

            # Keep _lbl_prov_info for backward compat (hidden)
            parts = []
            if rfc:  parts.append(f"RFC: {rfc}")
            if dirs: parts.append(dirs[:48])
            if tel:  parts.append(f"Tel: {tel}")
            if cond: parts.append(cond)
            info = "  ·  ".join(parts)
            if info:
                self._lbl_prov_info.setText(info)
                self._lbl_prov_info.show()
            else:
                self._lbl_prov_info.hide()
        except Exception:
            self._lbl_prov_info.hide()

    # ── E-1: Workflow stepper ─────────────────────────────────────────────────

    def _build_stepper_bar(self) -> QWidget:
        """Horizontal 4-step ERP stepper: Proveedor → Productos → Condición → Autorizar."""
        bar = QWidget()
        bar.setObjectName("stepperBar")
        bar.setFixedHeight(44)
        bar.setStyleSheet("background:transparent;")
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        self._stepper_labels: list[QLabel] = []
        steps = ["① Proveedor", "② Productos", "③ Condición", "④ Autorizar"]
        for i, txt in enumerate(steps):
            lbl = QLabel(txt)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFixedHeight(32)
            lbl.setObjectName(f"stepperStep_{i}")
            lbl.setStyleSheet(self._stepper_style("idle"))
            self._stepper_labels.append(lbl)
            h.addWidget(lbl, 1)
            if i < len(steps) - 1:
                arrow = QLabel("›")
                arrow.setAlignment(Qt.AlignCenter)
                arrow.setFixedWidth(16)
                arrow.setStyleSheet(
                    f"color:{Colors.NEUTRAL.SLATE_300};"
                    f"font-size:{Typography.SIZE_XXL};"
                    "background:transparent;"
                )
                h.addWidget(arrow)
        return bar

    def _stepper_style(self, state: str) -> str:
        """Style sheet for stepper labels — state: 'idle' | 'active' | 'done'."""
        base = (
            f"font-size:{Typography.SIZE_SM};"
            f"border-radius:{Borders.RADIUS_SM}px;"
            f"padding:0 {Spacing.MD}px;"
        )
        if state == "active":
            return (
                base
                + f"font-weight:{Typography.WEIGHT_BOLD};"
                + f"background:{Colors.PRIMARY_BASE};"
                + f"color:{Colors.NEUTRAL.WHITE};"
            )
        if state == "done":
            return (
                base
                + f"font-weight:{Typography.WEIGHT_SEMIBOLD};"
                + f"background:{Colors.SUCCESS.BG_SOFT};"
                + f"color:{Colors.SUCCESS_BASE};"
                + f"border:1px solid {Colors.SUCCESS.BORDER};"
            )
        return (
            base
            + f"font-weight:{Typography.WEIGHT_SEMIBOLD};"
            + f"background:{_C_MUTED_BG};"
            + f"color:{_C_HINT};"
        )

    def _refresh_stepper(self) -> None:
        """Update stepper colours based on current form completion state."""
        if not hasattr(self, '_stepper_labels') or not self._stepper_labels:
            return
        done_style   = self._stepper_style("done")
        active_style = self._stepper_style("active")
        idle_style   = self._stepper_style("idle")

        s1 = bool(self._proveedor_id_selected)
        s2 = bool(self.carrito_compra)
        s3 = bool(hasattr(self, '_cmb_condicion_pago'))  # field exists = filled
        if not s1:   active = 0
        elif not s2: active = 1
        elif not s3: active = 2
        else:        active = 3

        states = [s1, s2, s3, active == 3]
        for i, (lbl, done) in enumerate(zip(self._stepper_labels, states)):
            if i == active and not done:
                lbl.setStyleSheet(active_style)
            elif done and i < active:
                lbl.setStyleSheet(done_style)
            elif i == 3 and s1 and s2:
                lbl.setStyleSheet(active_style)
            else:
                lbl.setStyleSheet(idle_style)

    def _refresh_stepper_for_doc(self, estado: str, tipo: str) -> None:
        """Update stepper to reflect the selected document's workflow position.

        Maps document state → step index so the stepper reads like a timeline:
          ① Proveedor → ② Productos → ③ Condición → ④ Autorizar

        Only updates if the stepper is currently visible (PR/PO doc type active).
        Called from _on_doc_item_clicked() when the user selects a PR or PO.
        """
        if not hasattr(self, '_stepper_labels') or not self._stepper_labels:
            return
        if not hasattr(self, '_hidden_stepper') or not self._hidden_stepper.isVisible():
            return

        _STATE_TO_STEP: dict[str, int] = {
            "BORRADOR":             0,   # ① just created
            "CANCELADA":            0,   # ① reset
            "RECHAZADA":            1,   # ② needs re-edit
            "PENDIENTE_APROBACION": 2,   # ③ submitted, awaiting approval
            "APROBADA":             3,   # ④ approved
            "CONVERTIDA_A_PO":      3,   # ④ converted (all done)
            "ABIERTA":              3,   # ④ PO open
            "PARCIAL":              3,   # ④ PO partial receipt
            "RECIBIDA":             3,   # ④ PO fully received
            "CERRADA":              3,   # ④ PO closed
        }
        active = _STATE_TO_STEP.get(estado.upper() if estado else "", 0)

        _base = (
            f"font-size:{Typography.SIZE_SM};"
            f"border-radius:{Borders.RADIUS_SM}px;"
            f"padding:0 {Spacing.MD}px;"
        )
        done_style = (
            _base
            + f"font-weight:{Typography.WEIGHT_SEMIBOLD};"
            + f"background:{Colors.SUCCESS.BG_SOFT};"
            + f"color:{Colors.SUCCESS_BASE};"
            + f"border:1px solid {Colors.SUCCESS.BORDER};"
        )
        active_style = (
            _base
            + f"font-weight:{Typography.WEIGHT_BOLD};"
            + f"background:{Colors.PRIMARY_BASE};"
            + f"color:{Colors.NEUTRAL.WHITE};"
        )
        idle_style = (
            _base
            + f"font-weight:{Typography.WEIGHT_SEMIBOLD};"
            + f"background:{_C_MUTED_BG};"
            + f"color:{_C_HINT};"
        )

        for i, lbl in enumerate(self._stepper_labels):
            if i < active:
                lbl.setStyleSheet(done_style)
            elif i == active:
                lbl.setStyleSheet(active_style)
            else:
                lbl.setStyleSheet(idle_style)

    # ── E-2: File attachment ──────────────────────────────────────────────────

    def _adjuntar_factura(self) -> None:
        """Open file dialog to attach a PDF or image to this purchase."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Adjuntar factura / remisión",
            os.path.expanduser("~"),
            "Documentos (*.pdf *.png *.jpg *.jpeg *.webp *.xml);;Todos los archivos (*)",
        )
        if not path:
            return
        self._adjunto_path = path
        short = os.path.basename(path)
        if len(short) > 28:
            short = short[:25] + "…"
        if hasattr(self, '_lbl_adjunto'):
            self._lbl_adjunto.setText(f"📎 {short}")
            self._lbl_adjunto.setStyleSheet(
                f"color:{Colors.SUCCESS_BASE};font-size:{Typography.SIZE_XS};")
        Toast.success(self, "📎 Adjunto", f"Archivo: {short}")

    # ── E-3: Recent purchases in sidebar ─────────────────────────────────────

    def _cargar_recientes_proveedor(self, prov_id: int) -> None:
        """Load last 5 purchases from this provider into the sidebar list.

        Note: _sidebar_recent_list has no layout parent so it must never be
        shown directly (show() on a parentless widget creates a floating window).
        Items are stored in it for internal use; display happens via tooltip or
        future integration.
        """
        if not hasattr(self, '_sidebar_recent_list'):
            return
        self._sidebar_recent_list.clear()
        try:
            rows = self.container.db.execute(
                """SELECT id, folio, fecha, total, estado
                   FROM compras
                   WHERE proveedor_id=? AND sucursal_id=?
                   ORDER BY fecha DESC, id DESC LIMIT 5""",
                (prov_id, self.sucursal_id),
            ).fetchall()
            if not rows:
                return
            for r in rows:
                r_id    = r[0] if not hasattr(r, 'keys') else r['id']
                folio   = str(r[1] if not hasattr(r, 'keys') else r.get('folio', r_id))
                fecha   = str(r[2] if not hasattr(r, 'keys') else r.get('fecha', ''))[:10]
                total   = float(r[3] if not hasattr(r, 'keys') else r.get('total', 0) or 0)
                estado  = str(r[4] if not hasattr(r, 'keys') else r.get('estado', ''))
                txt = (f"${total:,.0f}  {fecha}\n"
                       f"{folio[-16:]}  [{estado}]")
                item = QListWidgetItem(txt)
                item.setData(Qt.UserRole, r_id)
                item.setToolTip(f"Folio: {folio} — Haz clic para ver detalle")
                self._sidebar_recent_list.addItem(item)
        except Exception as e:
            logger.debug("_cargar_recientes_proveedor: %s", e)

    def _abrir_reciente_sidebar(self, item: QListWidgetItem) -> None:
        """Click on recent purchase in sidebar → open detail dialog."""
        compra_id = item.data(Qt.UserRole)
        if compra_id:
            self._ver_detalle_compra(compra_id)

    def _auto_seleccionar_doc(self, folio: str) -> None:
        """Auto-select a document in the ERP list by folio (called after PR/PO creation)."""
        if not hasattr(self, '_doc_erp_list'):
            return
        for i in range(self._doc_erp_list.count()):
            item = self._doc_erp_list.item(i)
            if not item:
                continue
            doc = item.data(Qt.UserRole + 2)
            if doc and str(doc.get('folio', '')) == folio:
                self._doc_erp_list.setCurrentItem(item)
                self._on_doc_item_clicked(item)
                return

    # ── E-4: CxP / pending invoice alert ─────────────────────────────────────

    def _cargar_alertas_cxp(self, prov_id: int) -> None:
        """Show a warning banner if this provider has open credit/pending purchases."""
        if not hasattr(self, '_cxp_alert_bar'):
            return
        try:
            row = self.container.db.execute(
                """SELECT COUNT(*), COALESCE(SUM(total), 0)
                   FROM compras
                   WHERE proveedor_id=? AND sucursal_id=?
                     AND estado IN ('credito', 'pendiente')""",
                (prov_id, self.sucursal_id),
            ).fetchone()
            count = int(row[0] or 0)
            monto = float(row[1] or 0)
            if count > 0 and self._tiene_permiso("ver_totales"):
                self._cxp_alert_bar.setText(
                    f"⚠  Este proveedor tiene {count} compra(s) pendiente(s) "
                    f"por ${monto:,.2f} — verifica antes de continuar.")
                self._cxp_alert_bar.show()
            else:
                self._cxp_alert_bar.hide()
        except Exception as e:
            logger.debug("_cargar_alertas_cxp: %s", e)
            self._cxp_alert_bar.hide()

    def _poblar_plantillas_sidebar(self) -> None:
        """Loads purchase templates from DB into the sidebar list."""
        if not hasattr(self, '_sidebar_templates_list'):
            return
        self._sidebar_templates_list.clear()
        try:
            rows = self.container.db.execute(
                "SELECT id, nombre FROM plantillas_compra ORDER BY nombre LIMIT 20"
            ).fetchall()
            for r in rows:
                pid  = r[0] if not hasattr(r, 'keys') else r['id']
                name = r[1] if not hasattr(r, 'keys') else r['nombre']
                item = QListWidgetItem(f"📋 {name}")
                item.setData(Qt.UserRole, pid)
                self._sidebar_templates_list.addItem(item)
            if not rows:
                ph = QListWidgetItem("(Sin plantillas)")
                ph.setFlags(Qt.NoItemFlags)
                self._sidebar_templates_list.addItem(ph)
        except Exception as e:
            logger.warning("_cargar_plantillas_sidebar: %s", e)
            ph = QListWidgetItem("(Sin plantillas)")
            ph.setFlags(Qt.NoItemFlags)
            self._sidebar_templates_list.addItem(ph)

    def _cargar_plantilla_sidebar(self, item: QListWidgetItem) -> None:
        """Double-click template: load its items into the cart."""
        tpl_id = item.data(Qt.UserRole)
        if not tpl_id:
            return
        try:
            rows = self.container.db.execute("""
                SELECT ti.producto_id, p.nombre, ti.cantidad,
                       ti.costo_unitario, p.precio_compra
                FROM plantillas_compra_items ti
                JOIN productos p ON p.id = ti.producto_id
                WHERE ti.plantilla_id = ?
            """, (tpl_id,)).fetchall()
            if not rows:
                Toast.success(self, "📋 Plantilla vacía", "La plantilla no tiene ítems."); return
            if self.carrito_compra:
                if not confirm_action(
                    self, "Cargar plantilla",
                    f"¿Agregar {len(rows)} ítem(s) al carrito actual?",
                    "Agregar", "Cancelar"
                ):
                    return
            for r in rows:
                def _v(i, k): return r[i] if not hasattr(r,'keys') else r.get(k)
                pid = _v(0,'producto_id'); nombre = str(_v(1,'nombre') or '')
                cantidad = float(_v(2,'cantidad') or 1)
                costo    = float(_v(3,'costo_unitario') or 0)
                costo_h  = float(_v(4,'precio_compra') or costo)
                self.carrito_compra.append({
                    'producto_id': pid, 'nombre': nombre,
                    'cantidad': cantidad, 'costo_unitario': costo,
                    'subtotal': round(cantidad * costo, 4),
                    'precio_historico': costo_h,
                })
            self._refresh_tabla()
            Toast.success(self, "📋 Plantilla cargada", f"{len(rows)} ítem(s) agregados")
        except (TypeError, KeyError, IndexError) as e:
            logger.warning("_cargar_plantilla_sidebar: %s", e)

    def _actualizar_panel_validacion(self) -> None:
        """Updates validation state labels in the right summary panel."""
        if not hasattr(self, '_val_prov_lbl'):
            return
        ok_s  = f"color:{Colors.SUCCESS_BASE};"
        war_s = f"color:{Colors.WARNING_BASE};"
        if self._proveedor_id_selected:
            self._val_prov_lbl.setText("✔ Proveedor")
            self._val_prov_lbl.setStyleSheet(ok_s)
        else:
            self._val_prov_lbl.setText("⚠ Proveedor")
            self._val_prov_lbl.setStyleSheet(war_s)
        n = len(self.carrito_compra)
        if n > 0:
            self._val_prod_lbl.setText(f"✔ Productos ({n})")
            self._val_prod_lbl.setStyleSheet(ok_s)
        else:
            self._val_prod_lbl.setText("⚠ Productos")
            self._val_prod_lbl.setStyleSheet(war_s)
        total = sum(i['subtotal'] for i in self.carrito_compra)
        if total > 0:
            self._val_total_v_lbl.setText("✔ Total")
            self._val_total_v_lbl.setStyleSheet(ok_s)
        else:
            self._val_total_v_lbl.setText("⚠ Total cero")
            self._val_total_v_lbl.setStyleSheet(war_s)

    def _on_condicion_changed(self, condicion: str) -> None:
        """Enable/disable plazo spinbox based on payment condition."""
        es_credito = condicion.lower() != "liquidado"
        if hasattr(self, '_spin_plazo_dias'):
            self._spin_plazo_dias.setEnabled(es_credito)
        self._on_plazo_changed()

    def _on_plazo_changed(self, _=None) -> None:
        """Recalculate and display due date based on plazo."""
        if not hasattr(self, '_lbl_vence_el'):
            return
        condicion = self._cmb_condicion_pago.currentText().lower() if hasattr(self, '_cmb_condicion_pago') else "liquidado"
        if condicion == "liquidado":
            self._lbl_vence_el.setText("Vence: N/A")
        else:
            plazo = self._spin_plazo_dias.value() if hasattr(self, '_spin_plazo_dias') else 30
            vence = QDate.currentDate().addDays(plazo)
            self._lbl_vence_el.setText(f"Vence: {vence.toString('dd/MMM/yyyy')}")

    def _ir_a_recepcion_tras_compra(self) -> None:
        """After a direct purchase is saved, switch to QR reception tab."""
        try:
            if hasattr(self, '_tabs'):
                self._tabs.setCurrentIndex(1)
        except Exception:
            pass

    def _enviar_a_recepcion(self) -> None:
        """Process purchase then switch to QR reception tab."""
        if not self.carrito_compra:
            QMessageBox.warning(self, "Aviso", "El carrito está vacío."); return
        self._resolver_proveedor_desde_texto()
        if not self._proveedor_id_selected:
            QMessageBox.warning(self, "Aviso", "Selecciona un proveedor válido."); return
        self._procesar_compra()
        if hasattr(self, '_tabs') and self.carrito_compra == []:
            self._tabs.setCurrentIndex(1)

    # ── Phase 5: Document-type toolbar ───────────────────────────────────────

    def _build_doctype_toolbar(self) -> QWidget:
        """
        Barra de selección de tipo de documento: Compra Directa | Solicitud PR | Orden PO.
        Permite elegir si el carrito generará una compra directa, una solicitud de
        compra (PR) o una orden de compra (PO). Sin efecto en el flujo QR.
        """
        bar = QFrame()
        bar.setObjectName("doctypeToolbar")
        bar.setFixedHeight(40)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, Spacing.XS - 2, 0, Spacing.XS - 2)
        lay.setSpacing(Spacing.XS)

        lbl = _make_field_label("Tipo de documento")
        lay.addWidget(lbl)
        lay.addSpacing(Spacing.XS)

        # Container with subtle background, mimics the HTML pill-group
        group = QFrame()
        group.setObjectName("doctypeGroup")
        group.setStyleSheet(
            f"QFrame#doctypeGroup{{"
            f"  background:{_C_MUTED_BG};"
            f"  border:1px solid {_C_BORDER};"
            f"  border-radius:{Borders.RADIUS_SM}px;"
            f"}}"
        )
        group_lay = QHBoxLayout(group)
        group_lay.setContentsMargins(2, 2, 2, 2)
        group_lay.setSpacing(2)

        self._doctype_buttons: dict[str, QPushButton] = {}
        for doc_type, icon, label, tooltip in [
            ("DIRECT", "🛒", "Compra Directa",
             "Registra compra con efecto inmediato en inventario"),
            ("PR",     "📋", "Solicitud (PR)",
             "Crea solicitud pendiente de aprobación · Sin efecto en inventario"),
            ("PO",     "📦", "Orden de Compra",
             "Convierte PR aprobada en Orden de Compra · Sin efecto directo en inventario"),
        ]:
            btn = QPushButton(f"{icon} {label}")
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(28)
            btn.setChecked(doc_type == self._doc_type)
            btn.clicked.connect(lambda _chk, dt=doc_type: self._on_doctype_changed(dt))
            self._doctype_buttons[doc_type] = btn
            group_lay.addWidget(btn)

        lay.addWidget(group)
        lay.addStretch()
        self._apply_doctype_button_styles()
        return bar

    def _on_doctype_changed(self, doc_type: str) -> None:
        if self._doc_type == doc_type:
            return
        self._doc_type = doc_type
        for dt, btn in self._doctype_buttons.items():
            btn.setChecked(dt == doc_type)
        self._apply_doctype_button_styles()
        self._refresh_doctype_ui()

    def _apply_doctype_button_styles(self) -> None:
        active = (
            f"QPushButton{{"
            f"  background:{Colors.PRIMARY_BASE};"
            f"  color:{Colors.NEUTRAL.WHITE};"
            f"  border:1px solid {Colors.PRIMARY_BASE};"
            f"  border-radius:{Borders.RADIUS_SM - 1}px;"
            f"  font-size:{Typography.SIZE_SM};"
            f"  font-weight:{Typography.WEIGHT_SEMIBOLD};"
            f"  padding:{Spacing.XS - 2}px {Spacing.MD - 2}px;"
            f"}}"
        )
        idle = (
            f"QPushButton{{"
            f"  background:{Colors.NEUTRAL.SLATE_100};"
            f"  color:{_C_BODY_TXT};"
            f"  border:1px solid transparent;"
            f"  border-radius:{Borders.RADIUS_SM - 1}px;"
            f"  font-size:{Typography.SIZE_SM};"
            f"  font-weight:{Typography.WEIGHT_MEDIUM};"
            f"  padding:{Spacing.XS - 2}px {Spacing.MD - 2}px;"
            f"}}"
            f"QPushButton:hover{{"
            f"  background:{_C_BORDER};"
            f"  color:{_C_HEADER_TXT};"
            f"}}"
        )
        for dt, btn in getattr(self, '_doctype_buttons', {}).items():
            btn.setStyleSheet(active if dt == self._doc_type else idle)

    def _refresh_doctype_ui(self) -> None:
        """Actualiza badge, texto/color del botón principal, stepper y hint según doc type."""
        _cfg = {
            #  badge_txt         badge_color           btn_txt              btn_tip
            #  show_enviar  btn_color              btn_hover
            #  show_stepper  hint_txt
            "DIRECT": (
                "🔵  En captura",      Colors.INFO_BASE,
                "✓ Autorizar compra",  "Autorizar y procesar compra (F10)",    True,
                Colors.SUCCESS_BASE,   Colors.SUCCESS_HOVER,
                False,
                "Flujo: Capturar → Autorizar → Registra en inventario inmediatamente",
            ),
            "PR": (
                "📋  Solicitud PR",    Colors.WARNING_BASE,
                "📋 Crear solicitud",  "Guardar solicitud pendiente de aprobación",  False,
                Colors.PRIMARY_BASE,   Colors.PRIMARY_HOVER,
                True,
                "Flujo: Crear solicitud → Aprobar PR → Convertir a Orden de Compra",
            ),
            "PO": (
                "📦  Orden de Compra", Colors.SUCCESS_BASE,
                "📦 Ver instrucciones", "Ver instrucciones para generar Orden de Compra", False,
                Colors.WARNING_BASE,   Colors.WARNING_HOVER,
                True,
                "Flujo: PR aprobada → Orden de compra → Recepción con QR",
            ),
        }
        (badge_txt, badge_color, btn_txt, btn_tip, show_enviar,
         btn_color, btn_hover, show_stepper, hint_txt) = _cfg.get(
            self._doc_type, _cfg["DIRECT"])

        if hasattr(self, '_lbl_estado_compra'):
            self._lbl_estado_compra.setText(badge_txt)
            self._lbl_estado_compra.setStyleSheet(
                f"background:{badge_color};color:{Colors.NEUTRAL.WHITE};"
                f"border-radius:{Borders.RADIUS_FULL}px;"
                f"padding:{Spacing.XS - 1}px {Spacing.SM}px;"
                f"font-size:{Typography.SIZE_SM};"
                f"font-weight:{Typography.WEIGHT_BOLD};"
            )
        if hasattr(self, '_btn_autorizar'):
            self._btn_autorizar.setText(btn_txt)
            self._btn_autorizar.setToolTip(btn_tip)
            self._btn_autorizar.setStyleSheet(
                f"QPushButton{{background:{btn_color};color:white;"
                f"border-radius:{Borders.RADIUS_MD}px;font-size:13px;font-weight:700;"
                f"letter-spacing:0.05em;border:none;}}"
                f"QPushButton:hover{{background:{btn_hover};}}"
                f"QPushButton:disabled{{background:{Colors.NEUTRAL.SLATE_400};"
                f"color:{Colors.NEUTRAL.SLATE_600};}}"
            )
        if hasattr(self, '_btn_enviar_recepcion'):
            self._btn_enviar_recepcion.setVisible(show_enviar)
        if hasattr(self, '_hidden_stepper'):
            self._hidden_stepper.setVisible(show_stepper)
        if hasattr(self, '_lbl_hint'):
            self._lbl_hint.setText(hint_txt)

    # ── Nueva Compra / Nueva PR ───────────────────────────────────────────────

    def _nueva_compra_directa(self) -> None:
        """Inicia una nueva compra directa: limpia el formulario y activa modo DIRECT."""
        self._reset_form_for_new_doc()
        self._on_doctype_changed("DIRECT")

    def _nueva_pr_flow(self) -> None:
        """Inicia una nueva solicitud de compra (PR): limpia el formulario y activa modo PR."""
        self._reset_form_for_new_doc()
        self._on_doctype_changed("PR")
        from PyQt5.QtCore import QTimer
        if hasattr(self, 'txt_proveedor'):
            QTimer.singleShot(50, self.txt_proveedor.setFocus)

    def _reset_form_for_new_doc(self) -> None:
        """Limpia carrito y campos del proveedor para iniciar un nuevo documento."""
        self.carrito_compra.clear()
        self._refresh_tabla()
        self._proveedor_id_selected = None
        if hasattr(self, 'txt_proveedor'):
            self.txt_proveedor.clear()
        for attr in ('_inp_rfc', '_inp_tel', '_inp_dir', '_inp_cred'):
            if hasattr(self, attr):
                getattr(self, attr).clear()
        if hasattr(self, '_lbl_prov_status'):
            self._lbl_prov_status.setText("Sin proveedor seleccionado")
            self._lbl_prov_status.setStyleSheet(
                f"color:{Colors.WARNING_BASE};"
                f"font-size:{Typography.SIZE_XS};background:transparent;"
            )
        if hasattr(self, '_lbl_prov_info'):
            self._lbl_prov_info.hide()
        if hasattr(self, '_cxp_alert_bar'):
            self._cxp_alert_bar.hide()
        self._actualizar_panel_validacion()
        self._refresh_stepper()

    def _procesar_como_pr(self, proveedor_id: int, proveedor_nom: str) -> None:
        """
        Crea una Purchase Request y la envía a aprobación con los ítems del carrito.
        Delega a TraditionalPurchaseUC con document_type=PR.
        NO afecta inventario, GL ni CxP.
        """
        from application.purchases.commands import RegisterPurchaseCommand, PurchaseItemCommand
        from application.purchases.states import DocumentType, PRState
        try:
            subtotal    = sum(i['subtotal'] for i in self.carrito_compra)
            iva_activo  = hasattr(self, '_chk_iva') and self._chk_iva.isChecked()
            iva_monto   = round(subtotal * self._get_iva_rate(), 2) if iva_activo else 0.0
            total       = subtotal + iva_monto
            pago        = self.cmb_pago.currentData() or "CONTADO"
            branch_dest = (self.cmb_sucursal_destino.currentData()
                           if hasattr(self, 'cmb_sucursal_destino')
                           else self.sucursal_id) or self.sucursal_id
            condicion   = (self._cmb_condicion_pago.currentText().lower()
                           if hasattr(self, '_cmb_condicion_pago') else "liquidado")
            plazo       = (self._spin_plazo_dias.value()
                           if hasattr(self, '_spin_plazo_dias') else 0)
            moneda      = (self._cmb_moneda.currentData()
                           if hasattr(self, '_cmb_moneda') else "MXN")

            cmd = RegisterPurchaseCommand(
                proveedor_id=proveedor_id,
                proveedor_nombre=proveedor_nom,
                sucursal_id=branch_dest,
                usuario=self.usuario_actual,
                items=[
                    PurchaseItemCommand(
                        product_id=i['producto_id'],
                        qty=i['cantidad'],
                        unit_cost=i['costo_unitario'],
                        nombre=i['nombre'],
                    )
                    for i in self.carrito_compra
                ],
                metodo_pago=pago,
                subtotal=subtotal,
                iva_monto=iva_monto,
                total=total,
                document_type=DocumentType.PR,
                pr_estado_inicial=PRState.PENDIENTE_APROBACION,
                condicion_pago=condicion,
                plazo_dias=plazo,
                moneda=moneda,
                doc_ref=self.txt_factura.text().strip() if hasattr(self, 'txt_factura') else "",
                notas="\n".join(filter(None, [
                    f"Solicitante: {self.txt_solicitante.text().strip()}" if hasattr(self, 'txt_solicitante') and self.txt_solicitante.text().strip() else "",
                    self.txt_notas.toPlainText().strip() if hasattr(self, 'txt_notas') else "",
                ])),
            )
            uc = getattr(self.container, 'uc_compra_tradicional', None)
            if uc is None:
                from application.purchases.traditional_purchase_uc import TraditionalPurchaseUC
                uc = TraditionalPurchaseUC(self.container)
            result = uc.execute(cmd)
            if result.ok:
                Toast.success(
                    self, "📋 Solicitud enviada",
                    f"Folio: {result.folio} · Pendiente de aprobación",
                )
                # Clear cart — PR is committed, form should be clean
                self.carrito_compra.clear()
                self._refresh_tabla()
                self._actualizar_panel_validacion()
                # Refresh documental toolbar list so the new PR appears
                self._cargar_docs_erp()
                # Auto-select the newly created PR so toolbar buttons activate
                _new_folio = result.folio
                QTimer.singleShot(120, lambda f=_new_folio: self._auto_seleccionar_doc(f))
            else:
                QMessageBox.critical(self, "Error al crear solicitud", result.error)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            logger.error("_procesar_como_pr: %s", e)

    # ── Providers ────────────────────────────────────────────────────────────
    def _cargar_sucursales_compra(self) -> None:
        """Carga sucursales activas. La del usuario corriente queda seleccionada por defecto."""
        try:
            self.cmb_sucursal_destino.clear()
            rows = self.container.db.execute(
                "SELECT id, nombre FROM sucursales WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            if rows:
                for r in rows:
                    pid  = r['id']     if hasattr(r,'keys') else r[0]
                    name = r['nombre'] if hasattr(r,'keys') else r[1]
                    self.cmb_sucursal_destino.addItem(str(name), pid)
                # Select the user's current branch by default
                for i in range(self.cmb_sucursal_destino.count()):
                    if self.cmb_sucursal_destino.itemData(i) == self.sucursal_id:
                        self.cmb_sucursal_destino.setCurrentIndex(i)
                        break
            else:
                # No sucursales table or empty — add default
                self.cmb_sucursal_destino.addItem("Sucursal Principal", 1)
        except Exception:
            self.cmb_sucursal_destino.clear()
            self.cmb_sucursal_destino.addItem("Sucursal Principal", 1)

    def cargar_proveedores(self) -> None:
        try:
            prev_id = self._proveedor_id_selected
            rows = self.container.db.execute(
                "SELECT id, nombre FROM proveedores WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            self._proveedores_cache = [
                {"id": r['id'], "nombre": r['nombre']}
                for r in rows
            ]
            self._prov_model.setStringList([p["nombre"] for p in self._proveedores_cache])
            if prev_id:
                for p in self._proveedores_cache:
                    if p["id"] == prev_id:
                        self.txt_proveedor.setText(p["nombre"])
                        self._proveedor_id_selected = prev_id
                        break
            self._poblar_sidebar_proveedores()
        except Exception as e:
            logger.debug("cargar_proveedores: %s", e)

    def _on_completer_activated(self, nombre: str) -> None:
        """Fired when user picks a provider from the QCompleter dropdown."""
        for p in self._proveedores_cache:
            if p["nombre"] == nombre:
                self._seleccionar_proveedor(p["id"], nombre)
                return

    def _seleccionar_proveedor(self, prov_id: int, nombre: str) -> None:
        """Canonical entry point for all provider-selection paths.

        Sets _proveedor_id_selected and loads RFC / phone / address /
        credit conditions / CxP alerts / validation panel.
        No dialogs are opened.
        """
        self._proveedor_id_selected = prov_id
        if hasattr(self, 'txt_proveedor'):
            self.txt_proveedor.setText(nombre)
        if hasattr(self, '_lbl_prov_status'):
            self._lbl_prov_status.setText(f"✔ {nombre}")
            self._lbl_prov_status.setStyleSheet(f"color:{Colors.SUCCESS_BASE};")
        self._cargar_info_proveedor(prov_id)
        self._cargar_recientes_proveedor(prov_id)
        self._cargar_alertas_cxp(prov_id)
        self._actualizar_panel_validacion()
        self._refresh_stepper()
        self._poblar_sidebar_proveedores()

    def _resolver_proveedor_desde_texto(self) -> None:
        """Fallback: resolves provider from plain text when user tabs out."""
        txt = (self.txt_proveedor.text() or "").strip().lower()
        for p in self._proveedores_cache:
            if p["nombre"].strip().lower() == txt:
                self._seleccionar_proveedor(p["id"], p["nombre"])
                return
        # No match — clear selection
        self._proveedor_id_selected = None
        if hasattr(self, "_lbl_prov_status"):
            if txt:
                self._lbl_prov_status.setText("⚠ Proveedor no reconocido")
                self._lbl_prov_status.setStyleSheet(f"color:{Colors.DANGER_BASE};")
            else:
                self._lbl_prov_status.setText("⚠ Sin proveedor seleccionado")
                self._lbl_prov_status.setStyleSheet(f"color:{Colors.WARNING_BASE};")
        if hasattr(self, '_lbl_prov_info'):
            self._lbl_prov_info.hide()
        self._actualizar_panel_validacion()

    # ── Cart management ───────────────────────────────────────────────────────
    def _agregar_producto(self, prod: dict) -> None:
        """Agrega producto al carrito con dialog único (cantidad + costo + preview)."""
        nombre     = prod.get('nombre', '')
        costo_hist = float(prod.get('precio_compra', 0) or 0)

        # Already in cart → add extra quantity via same dialog
        for i, item in enumerate(self.carrito_compra):
            if item['producto_id'] == prod['id']:
                dlg = _DialogItemCompra(
                    nombre, costo_hist,
                    cantidad=1.0,
                    costo=item['costo_unitario'],
                    modo="add",
                    parent=self,
                )
                dlg.setWindowTitle(f"Agregar más: {nombre} (ya en carrito)")
                if dlg.exec_() == QDialog.Accepted:
                    self.carrito_compra[i]['cantidad'] += dlg.cantidad
                    self.carrito_compra[i]['subtotal'] = round(
                        self.carrito_compra[i]['cantidad'] *
                        self.carrito_compra[i]['costo_unitario'], 4)
                    self._refresh_tabla()
                return

        dlg = _DialogItemCompra(nombre, costo_hist, modo="add", parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return

        cantidad = dlg.cantidad
        costo    = dlg.costo

        # Audit price variance
        if costo_hist > 0 and costo > 0:
            variacion = abs(costo - costo_hist) / costo_hist * 100
            if variacion >= _PRICE_VARIANCE_THRESHOLD:
                dir_txt = "▲ SUBIÓ" if costo > costo_hist else "▼ BAJÓ"
                try:
                    audit_write(self.container, modulo="COMPRAS",
                                accion="VARIACION_PRECIO", entidad="productos",
                                entidad_id=str(prod['id']),
                                usuario=self.usuario_actual,
                                detalles=f"{nombre}: ${costo_hist:.2f}→${costo:.2f} ({dir_txt} {variacion:.1f}%)",
                                before={"precio_compra": costo_hist},
                                after={"precio_compra": costo},
                                sucursal_id=self.sucursal_id)
                except Exception:
                    pass

        self.carrito_compra.append({
            'producto_id':      prod['id'],
            'nombre':           nombre,
            'cantidad':         cantidad,
            'costo_unitario':   costo,
            'subtotal':         round(cantidad * costo, 4),
            'precio_historico': costo_hist,
            'unidad':           prod.get('unidad', 'kg'),
            'descuento_pct':    0.0,
            'iva_pct':          16.0 if (hasattr(self, '_chk_iva') and self._chk_iva.isChecked()) else 0.0,
        })
        self._refresh_tabla()
        self._buscador.clear()

    def _editar_fila(self, index) -> None:
        """Doble clic: edita cantidad y costo del ítem con el dialog compacto."""
        tbl_row = index.row()
        id_item = self.tabla.item(tbl_row, 0)
        cart_idx = id_item.data(Qt.UserRole) if id_item is not None else tbl_row
        if cart_idx is None or cart_idx < 0 or cart_idx >= len(self.carrito_compra):
            return
        item = self.carrito_compra[cart_idx]
        dlg = _DialogItemCompra(
            item['nombre'],
            item.get('precio_historico', 0.0),
            cantidad=item['cantidad'],
            costo=item['costo_unitario'],
            modo="edit",
            parent=self,
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        before_snap = {
            "cantidad":      item['cantidad'],
            "costo_unitario": item['costo_unitario'],
            "subtotal":      item['subtotal'],
        }
        self.carrito_compra[cart_idx]['cantidad']       = dlg.cantidad
        self.carrito_compra[cart_idx]['costo_unitario'] = dlg.costo
        self.carrito_compra[cart_idx]['subtotal']       = round(dlg.cantidad * dlg.costo, 4)
        try:
            audit_write(self.container, modulo="COMPRAS",
                        accion="ITEM_EDITADO_CARRITO", entidad="carrito",
                        entidad_id=str(item['producto_id']),
                        usuario=self.usuario_actual,
                        detalles=f"{item['nombre']}: qty {before_snap['cantidad']:.3f}→{dlg.cantidad:.3f}  "
                                 f"costo ${before_snap['costo_unitario']:.4f}→${dlg.costo:.4f}",
                        before=before_snap,
                        after={"cantidad": dlg.cantidad, "costo_unitario": dlg.costo,
                               "subtotal": self.carrito_compra[cart_idx]['subtotal']},
                        sucursal_id=self.sucursal_id)
        except Exception:
            pass
        self._refresh_tabla()

    def _menu_fila(self, pos) -> None:
        """Clic derecho: menú contextual por fila."""
        tbl_row = self.tabla.rowAt(pos.y())
        if tbl_row < 0:
            return
        id_item  = self.tabla.item(tbl_row, 0)
        cart_idx = id_item.data(Qt.UserRole) if id_item is not None else tbl_row
        if cart_idx is None or cart_idx < 0 or cart_idx >= len(self.carrito_compra):
            return
        menu = QMenu(self)
        act_edit = menu.addAction("✏️ Editar cantidad / costo")
        act_del  = menu.addAction("🗑 Eliminar del carrito")
        act = menu.exec_(QCursor.pos())
        if act == act_edit:
            self.tabla.doubleClicked.emit(self.tabla.model().index(tbl_row, 0))
        elif act == act_del:
            self.carrito_compra.pop(cart_idx)
            self._refresh_tabla()

    def _limpiar_carrito(self) -> None:
        if not self.carrito_compra:
            return
        if confirm_action(self, "Limpiar", "¿Limpiar todo el carrito?",
                          "Limpiar", "Cancelar"):
            self.carrito_compra.clear()
            self._refresh_tabla()
            self._clear_draft()

    def _refresh_tabla(self) -> None:
        """Reconstruye la tabla del carrito con botones de eliminar por fila."""
        if hasattr(self, "_cart_loading"):
            self._cart_loading.show()
        filtro = ""
        if hasattr(self, "_trad_filter"):
            filtro = self._trad_filter.values().get("search", "").lower().strip()

        # Pre-collect visible rows (avoids N insertRow() layout reflows)
        visible = [
            (orig_row, item)
            for orig_row, item in enumerate(self.carrito_compra)
            if not filtro or filtro in item['nombre'].lower()
        ]

        self.tabla.setRowCount(len(visible))   # single resize — one reflow only
        total = 0.0
        for row, (orig_row, item) in enumerate(visible):
            # Columns: ID(0) | Producto(1) | Unidad(2) | Cant.(3) | Costo Unit.(4) | Desc%(5) | IVA%(6) | Subtotal(7) | del(8)
            vals = [
                str(item['producto_id']),
                item['nombre'],
                item.get('unidad', 'kg'),
                f"{item['cantidad']:.3f}",
                f"${item['costo_unitario']:.4f}",
                f"{item.get('descuento_pct', 0):.1f}%",
                f"{item.get('iva_pct', 0):.0f}%",
                f"${item['subtotal']:.2f}",
            ]
            for col, val in enumerate(vals):
                it = QTableWidgetItem(val)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if col == 0:
                    it.setData(Qt.UserRole, orig_row)  # map visible→carrito index
                self.tabla.setItem(row, col, it)
            btn_del = create_danger_button(self, "✕", "Eliminar producto del carrito")
            btn_del.setFixedWidth(36)
            btn_del.clicked.connect(lambda _, r=orig_row: self._eliminar_fila(r))
            self.tabla.setCellWidget(row, 8, btn_del)
            total += item['subtotal']

        n_items = len(self.carrito_compra)
        self._refresh_totals_display(subtotal=total)
        if hasattr(self, "_lbl_cart_count"):
            self._lbl_cart_count.setText(
                f"{n_items} ítem{'s' if n_items != 1 else ''}" if n_items else "0 ítems")
        if hasattr(self, "_cart_empty"):
            self._cart_empty.setVisible(len(visible) == 0)
        if hasattr(self, "_cart_loading"):
            self._cart_loading.hide()
        self._refresh_stepper()

    def _eliminar_fila(self, row: int) -> None:
        if 0 <= row < len(self.carrito_compra):
            item = self.carrito_compra[row]
            try:
                audit_write(self.container, modulo="COMPRAS",
                            accion="ITEM_ELIMINADO_CARRITO", entidad="carrito",
                            entidad_id=str(item['producto_id']),
                            usuario=self.usuario_actual,
                            detalles=f"Eliminado: {item['nombre']} "
                                     f"qty={item['cantidad']:.3f} "
                                     f"costo=${item['costo_unitario']:.4f}",
                            before={"nombre": item['nombre'],
                                    "cantidad": item['cantidad'],
                                    "costo_unitario": item['costo_unitario']},
                            after={},
                            sucursal_id=self.sucursal_id)
            except Exception:
                pass
            self.carrito_compra.pop(row)
            self._refresh_tabla()

    def _refresh_totals_display(self, subtotal: float | None = None) -> None:
        """Recalcula y muestra subtotal, IVA y total en el panel de footer."""
        if subtotal is None:
            subtotal = sum(i['subtotal'] for i in self.carrito_compra)
        iva_activo = (hasattr(self, '_chk_iva') and self._chk_iva.isChecked())
        iva_monto  = round(subtotal * self._get_iva_rate(), 2) if iva_activo else 0.0
        total      = subtotal + iva_monto
        # Add flete and otros cargos
        flete = self._spin_flete.value() if hasattr(self, '_spin_flete') else 0.0
        otros = self._spin_otros.value() if hasattr(self, '_spin_otros') else 0.0
        total = total + flete + otros
        if hasattr(self, 'lbl_total'):
            self.lbl_total.setText(f"Total: ${total:,.2f}")
        if hasattr(self, '_lbl_subtotal_iva'):
            self._lbl_subtotal_iva.setText(f"Subtotal: ${subtotal:,.2f}")
        if hasattr(self, '_lbl_iva_monto'):
            self._lbl_iva_monto.setText(f"IVA (16%): ${iva_monto:,.2f}")
            self._lbl_iva_monto.setVisible(iva_activo)
        if hasattr(self, '_sep_iva'):
            self._sep_iva.setVisible(iva_activo)
        # Mirror values to the right summary panel
        if hasattr(self, '_sum_subtotal_lbl'):
            self._sum_subtotal_lbl.setText(f"Subtotal:  ${subtotal:,.2f}")
        if hasattr(self, '_sum_iva_lbl'):
            self._sum_iva_lbl.setText(f"IVA (16%):  ${iva_monto:,.2f}")
            self._sum_iva_lbl.setVisible(iva_activo)
        if hasattr(self, '_sum_flete_lbl'):
            self._sum_flete_lbl.setText(f"Flete:  ${flete:,.2f}")
        if hasattr(self, '_sum_otros_lbl'):
            self._sum_otros_lbl.setText(f"Otros:  ${otros:,.2f}")
        if hasattr(self, '_sum_total_lbl'):
            self._sum_total_lbl.setText(f"TOTAL:  ${total:,.2f}")
        if hasattr(self, '_sum_items_lbl'):
            n = len(self.carrito_compra)
            self._sum_items_lbl.setText(f"{n} producto{'s' if n != 1 else ''}")
        # Update peso estimado
        qty_kg = sum(i.get('cantidad', 0) for i in self.carrito_compra)
        if hasattr(self, '_sum_peso_lbl'):
            self._sum_peso_lbl.setText(f"Peso est.: {qty_kg:,.2f} kg")
        if hasattr(self, '_sum_costo_kg_lbl'):
            if qty_kg > 0 and total > 0:
                self._sum_costo_kg_lbl.setText(f"Costo/kg: ${total / qty_kg:,.2f}")
            else:
                self._sum_costo_kg_lbl.setText("Costo/kg: —")
        # Update ultima edicion timestamp
        import datetime as _dt
        if hasattr(self, '_lbl_ultima_edicion'):
            ts = _dt.datetime.now().strftime("%d/%m/%Y %H:%M")
            user = getattr(self, 'usuario_actual', 'Sistema')
            self._lbl_ultima_edicion.setText(f"Última edición: {user}  {ts}")
        self._actualizar_panel_validacion()

    def _eliminar_seleccionados(self) -> None:
        """Elimina las filas seleccionadas del carrito (multi-select support)."""
        orig_rows: set[int] = set()
        for idx in self.tabla.selectedIndexes():
            id_item = self.tabla.item(idx.row(), 0)
            if id_item is not None:
                orig = id_item.data(Qt.UserRole)
                if orig is not None:
                    orig_rows.add(orig)
        if not orig_rows:
            return
        if not confirm_action(
            self, "Eliminar seleccionados",
            f"¿Eliminar {len(orig_rows)} ítem(s) del carrito?",
            "Eliminar", "Cancelar",
        ):
            return
        for row in sorted(orig_rows, reverse=True):
            if 0 <= row < len(self.carrito_compra):
                self.carrito_compra.pop(row)
        self._refresh_tabla()

    # ── Draft helpers ─────────────────────────────────────────────────────────

    def _build_draft_dict(self) -> dict:
        """Snapshot of the current cart and form state for serialisation."""
        return {
            "carrito":          self.carrito_compra,
            "proveedor_id":     self._proveedor_id_selected,
            "proveedor_nombre": self.txt_proveedor.text().strip()
                                if hasattr(self, 'txt_proveedor') else "",
            "factura":          self.txt_factura.text().strip()
                                if hasattr(self, 'txt_factura') else "",
            "pago":             self.cmb_pago.currentData()
                                if hasattr(self, 'cmb_pago') else None,
            "iva_activo":       self._chk_iva.isChecked()
                                if hasattr(self, '_chk_iva') else False,
            "adjunto_path":     getattr(self, '_adjunto_path', ""),
            "saved_at":         datetime.now().isoformat(),
        }

    def _restore_draft_dict(self, draft: dict) -> None:
        """Apply a loaded draft dict to the UI."""
        self.carrito_compra = draft.get("carrito", [])
        prov_nombre = draft.get("proveedor_nombre", "")
        if prov_nombre and hasattr(self, 'txt_proveedor'):
            self.txt_proveedor.setText(prov_nombre)
            self._proveedor_id_selected = draft.get("proveedor_id")
            self._resolver_proveedor_desde_texto()
        factura = draft.get("factura", "")
        if factura and hasattr(self, 'txt_factura'):
            self.txt_factura.setText(factura)
        pago_data = draft.get("pago")
        if pago_data and hasattr(self, 'cmb_pago'):
            for i in range(self.cmb_pago.count()):
                if self.cmb_pago.itemData(i) == pago_data:
                    self.cmb_pago.setCurrentIndex(i)
                    break
        if hasattr(self, '_chk_iva'):
            self._chk_iva.setChecked(bool(draft.get("iva_activo", False)))
        adjunto = draft.get("adjunto_path", "")
        if adjunto and os.path.exists(adjunto):
            self._adjunto_path = adjunto
            short = os.path.basename(adjunto)
            if hasattr(self, '_lbl_adjunto'):
                self._lbl_adjunto.setText(f"📎 {short[:28]}")
                self._lbl_adjunto.setStyleSheet(
                    f"color:{Colors.SUCCESS_BASE};font-size:{Typography.SIZE_XS};")
        self._refresh_tabla()

    def _auto_save_draft(self) -> None:
        """Silent periodic auto-save — writes to DB if cart is non-empty."""
        if not self.carrito_compra or not self.usuario_actual:
            return
        try:
            data_json = json.dumps(self._build_draft_dict(), default=str)
            self._purchase_repo.save_draft(
                self.usuario_actual, self.sucursal_id, data_json)
            logger.debug("Auto-guardado borrador: %d ítem(s)", len(self.carrito_compra))
        except Exception as e:
            logger.debug("_auto_save_draft: %s", e)

    def _clear_draft(self) -> None:
        """Delete draft from DB and legacy JSON file."""
        try:
            if self.usuario_actual:
                self._purchase_repo.delete_draft(self.usuario_actual, self.sucursal_id)
        except Exception as e:
            logger.debug("_clear_draft DB: %s", e)
        try:
            if os.path.exists(_DRAFT_PATH):
                os.remove(_DRAFT_PATH)
        except Exception:
            pass

    def _check_pending_draft(self) -> None:
        """Non-blocking check on login: notify user if a draft awaits recovery."""
        if not self.usuario_actual or self.carrito_compra:
            return
        if not self._tiene_permiso("borrador"):
            return
        try:
            result = self._purchase_repo.load_draft(self.usuario_actual, self.sucursal_id)
            if not result:
                return
            data_json, _ = result
            draft = json.loads(data_json)
            n = len(draft.get("carrito", []))
            if n == 0:
                return
            total_b  = sum(i.get("subtotal", 0) for i in draft.get("carrito", []))
            saved_at = str(draft.get("saved_at", ""))[:16]
            Toast.info(
                self, "📂 Borrador pendiente",
                f"{n} ítem(s) · ${total_b:,.2f} del {saved_at}. "
                "Usa 'Recuperar' para restaurar.",
            )
        except Exception as e:
            logger.debug("_check_pending_draft: %s", e)

    def _guardar_borrador(self) -> None:
        """Guarda el carrito actual como borrador (DB primario, JSON de respaldo)."""
        if not self.carrito_compra:
            QMessageBox.information(self, "Borrador", "El carrito está vacío."); return
        draft = self._build_draft_dict()
        data_json = json.dumps(draft, ensure_ascii=False, default=str)
        saved = False
        # Primary: DB (per user+branch)
        if self.usuario_actual:
            try:
                self._purchase_repo.save_draft(
                    self.usuario_actual, self.sucursal_id, data_json)
                saved = True
            except Exception as e:
                logger.warning("_guardar_borrador DB: %s", e)
        # Secondary: JSON file (legacy fallback)
        try:
            with open(_DRAFT_PATH, "w", encoding="utf-8") as f:
                f.write(data_json)
            saved = True
        except Exception as e:
            if not saved:
                QMessageBox.critical(self, "Error al guardar borrador", str(e))
                return
        Toast.success(
            self, "💾 Borrador guardado",
            f"{len(self.carrito_compra)} ítem(s) · "
            f"${sum(i['subtotal'] for i in self.carrito_compra):,.2f}",
        )

    def _cargar_borrador(self) -> None:
        """Carga el borrador (DB primario, JSON de respaldo), reemplazando el carrito."""
        draft = None
        # Primary: DB
        if self.usuario_actual:
            try:
                result = self._purchase_repo.load_draft(self.usuario_actual, self.sucursal_id)
                if result:
                    draft = json.loads(result[0])
            except Exception as e:
                logger.warning("_cargar_borrador DB: %s", e)
        # Secondary: JSON file
        if draft is None and os.path.exists(_DRAFT_PATH):
            try:
                with open(_DRAFT_PATH, "r", encoding="utf-8") as f:
                    draft = json.load(f)
            except Exception as e:
                QMessageBox.critical(self, "Error al leer borrador", str(e)); return

        if not draft or not draft.get("carrito"):
            QMessageBox.information(self, "Borrador", "No hay borrador guardado."); return

        saved_at = str(draft.get("saved_at", ""))[:16]
        n        = len(draft["carrito"])
        total_b  = sum(i.get("subtotal", 0) for i in draft["carrito"])
        if not confirm_action(
            self, "Recuperar borrador",
            f"¿Cargar el borrador del {saved_at}?\n"
            f"{n} ítem(s) · ${total_b:,.2f}\n\n"
            "El carrito actual se reemplazará.",
            "Cargar borrador", "Cancelar",
        ):
            return
        self._restore_draft_dict(draft)
        Toast.success(self, "📂 Borrador recuperado",
                      f"{len(self.carrito_compra)} ítem(s) cargados")

    # ── Process purchase ─────────────────────────────────────────────────────
    def _procesar_compra(self) -> None:
        if not self.carrito_compra:
            QMessageBox.warning(self, "Aviso", "El carrito está vacío.")
            return
        self._resolver_proveedor_desde_texto()
        if not self._proveedor_id_selected:
            QMessageBox.warning(self, "Aviso", "Selecciona un proveedor válido de la lista sugerida.")
            return

        proveedor_id  = self._proveedor_id_selected
        proveedor_nom = self.txt_proveedor.text().strip()

        # ── Phase 5: route by document type ──────────────────────────────────
        doc_type = getattr(self, '_doc_type', 'DIRECT')
        if doc_type == "PR":
            self._procesar_como_pr(proveedor_id, proveedor_nom)
            return
        if doc_type == "PO":
            QMessageBox.information(
                self, "Orden de Compra",
                "Para generar una Orden de Compra:\n\n"
                "1. Selecciona 'Solicitud (PR)' y crea la solicitud con los productos.\n"
                "2. Envíala a aprobación (panel de administración).\n"
                "3. Una vez aprobada, el sistema la convierte en PO automáticamente.\n\n"
                "Selecciona 'Solicitud (PR)' para continuar.",
            )
            return
        # ── DIRECT: flujo original sin cambios ────────────────────────────────

        doc_ref  = self.txt_factura.text().strip() or "Sin Ref"
        pago     = self.cmb_pago.currentData() or "CONTADO"
        # Recompute subtotal from qty×unit_cost to match UC validation (avoids float drift)
        subtotal = round(sum(
            float(i['cantidad']) * float(i['costo_unitario'])
            for i in self.carrito_compra
        ), 2)
        iva_activo = hasattr(self, '_chk_iva') and self._chk_iva.isChecked()
        iva_monto  = round(subtotal * self._get_iva_rate(), 2) if iva_activo else 0.0
        total      = round(subtotal + iva_monto, 2)

        # Check for recipes among purchased items
        items_con_receta = self._detectar_recetas()

        # Show detailed summary dialog before processing
        if not self._mostrar_resumen_compra(
            proveedor_nom, doc_ref, pago,
            subtotal, iva_monto, total, items_con_receta,
        ):
            return

        try:
            # ── Delegate to application use case (clean architecture) ─────────
            from application.use_cases.registrar_compra_uc import (
                RegistrarCompraUC, DatosCompraDTO, ItemCompraDTO,
            )
            branch_dest = (self.cmb_sucursal_destino.currentData()
                           if hasattr(self, 'cmb_sucursal_destino')
                           else self.sucursal_id) or self.sucursal_id
            condicion = (self._cmb_condicion_pago.currentText().lower()
                         if hasattr(self, '_cmb_condicion_pago') else "liquidado")
            plazo     = (self._spin_plazo_dias.value()
                         if hasattr(self, '_spin_plazo_dias') else 0)
            moneda    = (self._cmb_moneda.currentText()
                         if hasattr(self, '_cmb_moneda') else "MXN")
            datos_uc = DatosCompraDTO(
                proveedor_id=proveedor_id,
                proveedor_nombre=proveedor_nom,
                sucursal_id=branch_dest,
                usuario=self.usuario_actual,
                items=[
                    ItemCompraDTO(
                        product_id=i['producto_id'],
                        qty=i['cantidad'],
                        unit_cost=i['costo_unitario'],
                        nombre=i['nombre'],
                    )
                    for i in self.carrito_compra
                ],
                metodo_pago=pago,
                doc_ref=doc_ref,
                subtotal=subtotal,
                iva_monto=iva_monto,
                total=total,
                condicion_pago=condicion,
                plazo_dias=plazo,
                moneda=moneda,
            )
            resultado = RegistrarCompraUC(self.container).execute(datos_uc)
            if not resultado.ok:
                QMessageBox.critical(self, "Error al procesar", resultado.error)
                return

            folio              = resultado.folio
            recetas_procesadas = resultado.recetas_procesadas

            # Audit is written inside RegistrarCompraUC.execute() — nothing extra needed here.

            detail = f"Folio: {folio}"
            if recetas_procesadas:
                detail += f" · Recetas: {', '.join(recetas_procesadas)}"
            Toast.success(self, "✅ Compra registrada", detail)
            # C-3: surface non-fatal finance warnings without blocking the flow
            if resultado.warnings:
                from PyQt5.QtWidgets import QMessageBox as _MB
                _MB.warning(
                    self, "Aviso — Registro financiero",
                    "La compra fue guardada y el inventario actualizado,\n"
                    "pero el registro financiero tuvo un problema:\n\n"
                    + "\n".join(f"• {w}" for w in resultado.warnings)
                    + "\n\nContacta al administrador si el saldo no cuadra.",
                )

            # E-5: offer quick print of reception ticket
            self._ofrecer_impresion_recepcion(folio)

            # Clear UI and draft
            self.carrito_compra.clear()
            self._refresh_tabla()
            self.txt_factura.clear()

            self._adjunto_path = ""
            if hasattr(self, '_lbl_adjunto'):
                self._lbl_adjunto.setText("Sin archivo")
                self._lbl_adjunto.setStyleSheet(
                    f"color:{Colors.NEUTRAL.SLATE_500};")
            self._clear_draft()
            self._refresh_stepper()
            # Refresh KPI bar non-blocking
            QTimer.singleShot(300, self._refresh_stats)
            # Navigate to QR reception tab so the user can validate physical receipt
            QTimer.singleShot(400, self._ir_a_recepcion_tras_compra)

        except Exception as e:
            QMessageBox.critical(self, "Error al procesar", str(e))
            logger.error("_procesar_compra: %s", e)

    # ── E-5: Quick reception ticket print ────────────────────────────────────

    def _ofrecer_impresion_recepcion(self, folio: str) -> None:
        """After a purchase is registered, offer to print the reception ticket."""
        reply = QMessageBox.question(
            self, "Imprimir comprobante",
            f"Compra {folio} registrada.\n\n¿Deseas imprimir el comprobante de recepción?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            compra_dict = self._purchase_repo.get_purchase_full(
                self.container.db.execute(
                    "SELECT id FROM compras WHERE folio=? LIMIT 1", (folio,)
                ).fetchone()[0]
            )
            if not compra_dict:
                return
            prov_nombre = self._purchase_repo.get_provider_name(
                compra_dict.get("proveedor_id", 0))
            items = self._purchase_repo.get_purchase_detail_items(compra_dict["id"])
            html = self._generar_html_recepcion(compra_dict, items, prov_nombre)

            from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
            from PyQt5.QtGui import QTextDocument
            printer = QPrinter(QPrinter.HighResolution)
            printer.setPageSize(QPrinter.A5)
            if QPrintDialog(printer, self).exec_() == QPrintDialog.Accepted:
                doc = QTextDocument()
                doc.setHtml(html)
                doc.print_(printer)
        except Exception as e:
            logger.warning("_ofrecer_impresion_recepcion: %s", e)

    def _generar_html_recepcion(self, compra: dict, items: list,
                                proveedor_nombre: str) -> str:
        """Compact A5 reception ticket HTML."""
        folio   = compra.get('folio', compra.get('id', ''))
        fecha   = str(compra.get('fecha', ''))[:16]
        total   = float(compra.get('total', 0) or 0)
        estado  = str(compra.get('estado', '')).upper()
        cond    = str(compra.get('condicion_pago', '')).capitalize()
        adjunto = getattr(self, '_adjunto_path', "")
        adjunto_html = (
            f"<p style='font-size:9px;color:#666;'>📎 {os.path.basename(adjunto)}</p>"
            if adjunto else ""
        )
        rows_html = "".join(
            f"<tr>"
            f"<td style='padding:2px 4px;border-bottom:1px solid #eee;'>{it['nombre']}</td>"
            f"<td style='text-align:right;padding:2px 4px;border-bottom:1px solid #eee;'>"
            f"{it['cantidad']:.3f}</td>"
            f"<td style='text-align:right;padding:2px 4px;border-bottom:1px solid #eee;'>"
            f"${it['subtotal']:.2f}</td>"
            f"</tr>"
            for it in items
        )
        return f"""
        <html><body style='font-family:Arial,sans-serif;font-size:11px;margin:16px;'>
          <h2 style='text-align:center;margin:0;font-size:14px;'>COMPROBANTE DE RECEPCIÓN</h2>
          <p style='text-align:center;color:#666;margin:2px 0;font-size:10px;'>
            {folio} · {fecha}</p>
          <hr style='border:none;border-top:1px solid #ccc;margin:6px 0;'>
          <p><b>Proveedor:</b> {proveedor_nombre}</p>
          <p><b>Estado:</b> {estado} &nbsp;&nbsp; <b>Condición:</b> {cond}</p>
          {adjunto_html}
          <table width='100%' style='border-collapse:collapse;margin-top:8px;'>
            <thead><tr style='background:#f5f5f5;'>
              <th style='text-align:left;padding:3px 4px;'>Producto</th>
              <th style='text-align:right;padding:3px 4px;'>Cant.</th>
              <th style='text-align:right;padding:3px 4px;'>Subtotal</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
          </table>
          <hr style='border:none;border-top:1px solid #ccc;margin:8px 0;'>
          <p style='text-align:right;font-size:13px;font-weight:bold;'>
            TOTAL: ${total:,.2f}</p>
          <p style='text-align:center;font-size:9px;color:#999;margin-top:16px;'>
            Generado por SPJ POS · {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
        </body></html>
        """

    def _mostrar_resumen_compra(self, proveedor: str, doc_ref: str,
                                pago: str,
                                subtotal: float, iva_monto: float, total: float,
                                items_receta: list) -> bool:
        """
        Muestra diálogo de resumen antes de procesar la compra.
        Retorna True si el usuario confirma, False si cancela.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle("Confirmar Compra")
        dlg.setMinimumWidth(500)
        lay = QVBoxLayout(dlg)

        # Summary HTML
        rows = ""
        for it in self.carrito_compra:
            rows += (f"<tr><td>{it['nombre']}</td>"
                     f"<td align='right'>{it['cantidad']:.3f}</td>"
                     f"<td align='right'>${it['costo_unitario']:.4f}</td>"
                     f"<td align='right'>${it['subtotal']:.2f}</td></tr>")

        receta_aviso = ""
        if items_receta:
            nombres = ", ".join(i['nombre'] for i in items_receta)
            receta_aviso = (f"<p style='background:{Colors.WARNING_BASE}22;border-left:3px solid "
                            f"{Colors.WARNING_BASE};padding:6px 10px;border-radius:0 4px 4px 0;'>"
                            f"<b>⚠ Productos con receta:</b> {nombres}<br>"
                            f"Se procesará la producción automáticamente.</p>")

        iva_row = ""
        if iva_monto > 0:
            iva_row = (f"<p style='margin:2px 0;'>"
                       f"Subtotal sin IVA: ${subtotal:,.2f} &nbsp;|&nbsp; "
                       f"<span style='color:{Colors.INFO_BASE};'>"
                       f"IVA (16%): ${iva_monto:,.2f}</span></p>")

        html = f"""<html><body style='font-family:sans-serif;font-size:12px;'>
        <h3 style='margin-bottom:8px;'>Resumen de Compra</h3>
        <p><b>Proveedor:</b> {proveedor} &nbsp;|&nbsp;
           <b>Ref:</b> {doc_ref} &nbsp;|&nbsp;
           <b>Pago:</b> {pago}</p>
        <table width='100%' cellspacing='0' style='border-collapse:collapse;font-size:12px;'>
        <tr style='background:{Colors.PRIMARY_BASE};color:#fff;'>
          <th align='left' style='padding:6px 8px;'>Producto</th>
          <th style='padding:6px 8px;'>Cantidad</th>
          <th style='padding:6px 8px;'>Costo Unit.</th>
          <th style='padding:6px 8px;'>Subtotal</th></tr>
        {rows}
        </table>
        <hr style='margin:10px 0;'>
        {iva_row}
        <p style='font-size:15px;font-weight:bold;color:{Colors.SUCCESS_BASE};margin:4px 0;'>
          Total a pagar: ${total:,.2f}</p>
        {receta_aviso}
        </body></html>"""

        browser = QTextBrowser()
        browser.setHtml(html)
        browser.setMinimumHeight(300)
        lay.addWidget(browser)

        btn_row = QHBoxLayout()
        btn_cancel = create_secondary_button(self, "✕ Cancelar", "Cancelar y cerrar")
        btn_ok = create_success_button(self, "✅ Confirmar y Procesar", "Confirmar edición de compra")
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_cancel); btn_row.addStretch(); btn_row.addWidget(btn_ok)
        lay.addLayout(btn_row)

        return dlg.exec_() == QDialog.Accepted

    def _detectar_recetas(self) -> list[dict]:
        """Retorna los ítems del carrito que tienen receta registrada (batch query)."""
        if not self.carrito_compra:
            return []
        ids = [it['producto_id'] for it in self.carrito_compra]
        ph  = ",".join("?" * len(ids))
        try:
            rows = self.container.db.execute(
                f"""SELECT DISTINCT c FROM (
                        SELECT producto_id      AS c FROM recetas
                        WHERE  producto_id      IN ({ph}) AND (activa=1 OR activo=1)
                        UNION
                        SELECT producto_base_id AS c FROM recetas
                        WHERE  producto_base_id IN ({ph}) AND (activa=1 OR activo=1)
                    )""",
                ids + ids
            ).fetchall()
            ids_con_receta = {r[0] for r in rows}
            return [it for it in self.carrito_compra
                    if it['producto_id'] in ids_con_receta]
        except Exception:
            return []

    def _procesar_recetas(self, items: list[dict]) -> list[str]:
        """Ejecuta la receta de cada producto comprado que la tenga."""
        nombres = []
        for item in items:
            try:
                # Use RecipeEngine if available
                engine = getattr(self.container, 'recipe_engine', None)
                if engine and hasattr(engine, 'ejecutar_receta'):
                    engine.ejecutar_receta(
                        producto_id=item['producto_id'],
                        cantidad=item['cantidad'],
                        usuario=self.usuario_actual,
                        sucursal_id=self.sucursal_id,
                    )
                    nombres.append(item['nombre'])
                else:
                    # Fallback: query receta_componentes (m000 schema), then product_recipe_components
                    receta = self.container.db.execute("""
                        SELECT rc.producto_id AS insumo_id,
                               COALESCE(rc.cantidad, 0) AS cantidad_insumo,
                               p.nombre AS insumo_nombre
                        FROM receta_componentes rc
                        JOIN recetas r ON r.id = rc.receta_id
                        JOIN productos p ON p.id = rc.producto_id
                        WHERE (r.producto_base_id=? OR r.producto_id=?)
                          AND (r.activo=1 OR r.activa=1)
                    """, (item['producto_id'], item['producto_id'])).fetchall()
                    if not receta:
                        receta = self.container.db.execute("""
                            SELECT rc.component_product_id AS insumo_id,
                                   COALESCE(rc.cantidad, 0) AS cantidad_insumo,
                                   p.nombre AS insumo_nombre
                            FROM product_recipe_components rc
                            JOIN product_recipes r ON r.id = rc.recipe_id
                            JOIN productos p ON p.id = rc.component_product_id
                            WHERE r.base_product_id=? AND r.is_active=1
                        """, (item['producto_id'],)).fetchall()
                    if receta:
                        _app = getattr(self.container, 'app_service', None)
                        for comp in receta:
                            consumo = float(comp['cantidad_insumo'] or 0) * item['cantidad']
                            if consumo > 0:
                                if _app:
                                    _app.registrar_salida_produccion(
                                        producto_id=comp['insumo_id'],
                                        cantidad=consumo,
                                        usuario=getattr(self, 'usuario_actual', ''),
                                        sucursal_id=self.sucursal_id)
                                else:
                                    self.container.db.execute(
                                        "UPDATE productos SET existencia=existencia-? WHERE id=?",
                                        (consumo, comp['insumo_id']))
                        try: self.container.db.commit()
                        except Exception: pass
                        nombres.append(item['nombre'])
            except Exception as e:
                logger.warning("_procesar_recetas %s: %s", item['nombre'], e)
        return nombres

    def _on_tab_change(self, idx: int) -> None:
        if idx == 2:  # Historial tab
            self._cargar_historial_compras()

    def _build_tab_historial(self, parent: QWidget) -> None:
        """Tab historial: 2-column layout — main table | right KPI sidebar."""
        outer = QHBoxLayout(parent)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Left: filters + table + pagination + inline detail ────────────────
        left_w = QWidget()
        lay = QVBoxLayout(left_w)
        lay.setContentsMargins(8, 8, 8, 8)
        outer.addWidget(left_w, 1)

        # ── Right: KPI sidebar ────────────────────────────────────────────────
        outer.addWidget(self._build_hist_kpi_sidebar())

        # Toolbar row
        hdr = QHBoxLayout()
        hdr.addWidget(create_subheading(self, "Historial de Compras"))
        hdr.addStretch()
        _today = QDate.currentDate()
        self._hist_desde = QDateEdit(QDate(_today.year(), _today.month(), 1))
        self._hist_desde.setCalendarPopup(True)
        self._hist_hasta = QDateEdit(_today)
        self._hist_hasta.setCalendarPopup(True)
        btn_ref = create_primary_button(self, "🔄", "Actualizar historial")
        btn_ref.clicked.connect(self._cargar_historial_compras)
        btn_export = create_secondary_button(self, "📥 CSV", "Exportar a CSV")
        btn_export.clicked.connect(self._exportar_historial_csv)
        self._btn_export_csv = btn_export
        hdr.addWidget(QLabel("Desde:"))
        hdr.addWidget(self._hist_desde)
        hdr.addWidget(QLabel("Hasta:"))
        hdr.addWidget(self._hist_hasta)
        hdr.addWidget(btn_ref)
        hdr.addWidget(btn_export)
        lay.addLayout(hdr)

        # Quick date presets
        preset_row = QHBoxLayout()
        preset_row.setSpacing(4)
        _lbl_pre = QLabel("Período:")
        _lbl_pre.setObjectName("caption")
        preset_row.addWidget(_lbl_pre)
        for label, days in [("Hoy", 0), ("7 días", 7), ("Este mes", -1),
                             ("Trim.", -3), ("Año", -12)]:
            btn = create_secondary_button(self, label, f"Ver {label}")
            btn.clicked.connect(lambda _, d=days: self._hist_set_preset(d))
            preset_row.addWidget(btn)
        preset_row.addStretch()
        lay.addLayout(preset_row)

        self._hist_filter = FilterBar(
            self,
            placeholder="Buscar folio, proveedor o usuario…",
            combo_filters={
                "estado":    ["completada", "credito", "pendiente", "parcial", "cancelada"],
                "tipo_doc":  ["directa", "con po"],         # Phase 7
                "po_estado": ["ABIERTA", "PARCIAL", "RECIBIDA", "CERRADA", "CANCELADA"],  # Phase 9
            },
        )
        self._hist_filter.filters_changed.connect(self._hist_filter_changed)
        lay.addWidget(self._hist_filter)
        self._hist_loading = LoadingIndicator("Cargando historial…", self)
        self._hist_loading.hide()
        lay.addWidget(self._hist_loading)

        # Main table — 9 cols: Folio|Fecha|Proveedor|Usuario|Total|Cond.Pago|Estado|TipoDoc|⋯
        self._tbl_hist = QTableWidget()
        self._tbl_hist.setColumnCount(9)
        self._tbl_hist.setHorizontalHeaderLabels(
            ["Folio", "Fecha", "Proveedor", "Usuario", "Total",
             "Cond. Pago", "Estado", "Tipo Doc", ""])
        hh = self._tbl_hist.horizontalHeader()
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(5, QHeaderView.Fixed)
        hh.setSectionResizeMode(6, QHeaderView.Fixed)
        self._tbl_hist.setColumnWidth(5, 90)
        self._tbl_hist.setColumnWidth(6, 110)
        for c in (0, 1, 3, 4, 7, 8):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._tbl_hist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_hist.setAlternatingRowColors(True)
        self._tbl_hist.verticalHeader().setVisible(False)
        self._tbl_hist.setObjectName("tableView")
        self._tbl_hist.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_hist.itemSelectionChanged.connect(self._on_hist_row_selected)
        lay.addWidget(self._tbl_hist)
        self._hist_empty = EmptyStateWidget(
            "Sin compras",
            "No se encontraron compras para el rango y filtros seleccionados.",
            "📭", self,
        )
        self._hist_empty.hide()
        lay.addWidget(self._hist_empty)

        # Pagination
        pag_row = QHBoxLayout()
        self._btn_pag_prev = create_secondary_button(self, "◀ Anterior", "Página anterior")
        self._btn_pag_next = create_secondary_button(self, "Siguiente ▶", "Página siguiente")
        self._lbl_pagina   = QLabel("Pág. 1")
        self._lbl_pagina.setObjectName("caption")
        self._hist_page    = 0
        self._hist_page_size = 100
        self._btn_pag_prev.clicked.connect(self._hist_pag_prev)
        self._btn_pag_next.clicked.connect(self._hist_pag_next)
        pag_row.addWidget(self._btn_pag_prev)
        pag_row.addWidget(self._lbl_pagina)
        pag_row.addWidget(self._btn_pag_next)
        pag_row.addStretch()
        self.lbl_hist_total_compras = QLabel("Total: $0.00")
        self.lbl_hist_total_compras.setObjectName("badgeSuccess")
        self.lbl_hist_num_compras = QLabel("0 compras")
        self.lbl_hist_num_compras.setObjectName("badgeInfo")
        pag_row.addWidget(self.lbl_hist_total_compras)
        pag_row.addWidget(self.lbl_hist_num_compras)
        lay.addLayout(pag_row)

        # Inline detail panel (shown on row selection)
        self._hist_detail_panel = QGroupBox("📄 Detalle de compra")
        self._hist_detail_panel.setObjectName("styledGroup")
        det_lay = QVBoxLayout(self._hist_detail_panel)
        det_lay.setContentsMargins(8, 6, 8, 6)
        self._hist_detail_header = QLabel("")
        self._hist_detail_header.setObjectName("caption")
        det_lay.addWidget(self._hist_detail_header)
        self._tbl_hist_detail = QTableWidget()
        self._tbl_hist_detail.setColumnCount(4)
        self._tbl_hist_detail.setHorizontalHeaderLabels(
            ["Producto", "Cantidad", "Costo Unit.", "Subtotal"])
        dh = self._tbl_hist_detail.horizontalHeader()
        dh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            dh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._tbl_hist_detail.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_hist_detail.verticalHeader().setVisible(False)
        self._tbl_hist_detail.setAlternatingRowColors(True)
        self._tbl_hist_detail.setObjectName("tableView")
        self._tbl_hist_detail.setMaximumHeight(160)
        det_lay.addWidget(self._tbl_hist_detail)

        # Phase 7 — mini documento-timeline (visible solo cuando la compra tiene PO asociada)
        self._hist_timeline_bar = QFrame()
        self._hist_timeline_bar.setObjectName("histTimelineBar")
        self._hist_timeline_bar.setFixedHeight(54)
        self._hist_timeline_bar.setStyleSheet(
            f"background:transparent;"
            f"border:1px solid {Colors.NEUTRAL.SLATE_200};border-radius:6px;"
        )
        self._hist_timeline_lay = QHBoxLayout(self._hist_timeline_bar)
        self._hist_timeline_lay.setContentsMargins(12, 6, 12, 6)
        self._hist_timeline_lay.setSpacing(4)
        self._hist_timeline_bar.hide()
        det_lay.addWidget(self._hist_timeline_bar)

        self._hist_detail_panel.hide()
        lay.addWidget(self._hist_detail_panel)

    def _on_hist_loader_error(self, msg: str) -> None:
        """Called when the history background thread fails — surfaces error to user."""
        logger.warning("_hist_loader error: %s", msg)
        if hasattr(self, "_hist_loading"):
            self._hist_loading.hide()
        try:
            from modulos.ui_components import Toast
            Toast.error(self, "Error al cargar historial", msg)
        except Exception:
            QMessageBox.warning(self, "Error al cargar historial", msg)

    def _hist_filter_changed(self, _=None) -> None:
        """Resets pagination to page 1 before reloading filtered history."""
        self._hist_page = 0
        self._cargar_historial_compras()

    def _cargar_historial_compras(self) -> None:
        """Inicia carga asíncrona del historial. El thread emite loaded → _poblar_historial."""
        if not hasattr(self, '_tbl_hist'):
            return
        self._tbl_hist.setRowCount(0)
        if hasattr(self, "_hist_loading"):
            self._hist_loading.show()
        # Kill any previous loader that may still be running
        if hasattr(self, '_hist_loader') and self._hist_loader.isRunning():
            self._hist_loader.quit()
            self._hist_loader.wait(200)
        try:
            desde = self._hist_desde.date().toString("yyyy-MM-dd")
            hasta = self._hist_hasta.date().toString("yyyy-MM-dd") + " 23:59:59"
        except Exception:
            desde, hasta = "2000-01-01", "2099-12-31 23:59:59"
        self._hist_loader = _HistorialLoader(
            self.container.db, self.sucursal_id, desde, hasta, _HIST_LIMIT)
        self._hist_loader.loaded.connect(self._poblar_historial)
        self._hist_loader.error.connect(self._on_hist_loader_error)
        self._hist_loader.start()

    def _poblar_historial(self, all_rows: list) -> None:
        """Recibe filas del thread de carga, aplica filtros y paginación, renderiza tabla."""
        if not hasattr(self, '_tbl_hist'):
            return
        try:
            filtros   = self._hist_filter.values() if hasattr(self, "_hist_filter") else {}
            estado    = (filtros.get("estado")   or "").strip().lower()
            search    = (filtros.get("search")   or "").strip().lower()
            tipo_doc  = (filtros.get("tipo_doc") or "").strip().lower()   # Phase 7
            po_estado = (filtros.get("po_estado") or "").strip().upper()  # Phase 9
            rows = list(all_rows)
            if estado:
                rows = [r for r in rows if str(r[5] or "").strip().lower() == estado]
            if po_estado:
                rows = [r for r in rows if str(r[10] if len(r) > 10 else "").strip().upper() == po_estado]
            if search:
                rows = [r for r in rows if
                        search in str(r[0] or "").lower() or
                        search in str(r[2] or "").lower() or
                        search in str(r[3] or "").lower()]
            if tipo_doc == "directa":
                rows = [r for r in rows if not (len(r) > 9 and int(r[9] or 0))]
            elif tipo_doc == "con po":
                rows = [r for r in rows if len(r) > 9 and int(r[9] or 0)]

            # Pagination
            total_rows = len(rows)
            page_size  = getattr(self, '_hist_page_size', 100)
            page       = getattr(self, '_hist_page', 0)
            max_page   = max(0, (total_rows - 1) // page_size) if total_rows > 0 else 0
            self._hist_page = min(page, max_page)  # clamp
            offset = self._hist_page * page_size
            rows   = rows[offset: offset + page_size]

            if hasattr(self, '_lbl_pagina'):
                self._lbl_pagina.setText(f"Pág. {self._hist_page + 1}/{max_page + 1}")
            if hasattr(self, '_btn_pag_prev'):
                self._btn_pag_prev.setEnabled(self._hist_page > 0)
            if hasattr(self, '_btn_pag_next'):
                self._btn_pag_next.setEnabled(self._hist_page < max_page)

            # Cache for pagination navigation without re-querying DB
            self._hist_all_rows = list(all_rows)
        except Exception as e:
            logger.debug("_poblar_historial filter/page: %s", e)
            rows = []

        # ── Render table ──────────────────────────────────────────────────────
        ocultar_totales = self._usuario_rol in _ROLES_SIN_TOTALES

        self._tbl_hist.setRowCount(len(rows))
        total_periodo = 0.0
        for ri, r in enumerate(rows):
            estado_raw   = str(r[5] or "").strip().lower()
            monto        = float(r[4] or 0)
            cond_raw     = str(r[7] if len(r) > 7 else "liquidado").strip().lower()
            total_str    = "—" if ocultar_totales else f"${monto:,.2f}"
            vals = [
                str(r[0] or ""), str(r[1] or "")[:16],
                str(r[2] or ""), str(r[3] or ""),
                total_str,
            ]
            cid_      = r[6]
            pnm_      = str(r[2] or "")
            po_id     = int(r[9] or 0) if len(r) > 9 else 0        # Phase 7
            po_estado = str(r[10] or "") if len(r) > 10 else ""     # Phase 9
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci == 4:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if ci == 0:
                    it.setData(Qt.UserRole,     cid_)       # compra_id for inline detail
                    it.setData(Qt.UserRole + 1, po_id)      # po_id for timeline (Phase 7)
                    it.setData(Qt.UserRole + 2, po_estado)  # po_estado for CSV export (Phase 9)
                self._tbl_hist.setItem(ri, ci, it)
            # col 5 — Cond. Pago chip
            self._tbl_hist.setCellWidget(ri, 5, _make_cond_chip(cond_raw, self))
            # col 6 — Estado chip
            self._tbl_hist.setCellWidget(ri, 6, _make_status_chip(estado_raw, self))
            # col 7 — Tipo Doc badge (Phase 7), tooltip con PO estado si existe
            if po_id:
                tip = f"PO #{po_id}"
                if po_estado:
                    tip += f" · {po_estado}"
                tipo_badge = create_badge(self, "📦 PO", "primary")
                tipo_badge.setToolTip(tip)
            else:
                tipo_badge = create_badge(self, "🛒 Directa", "neutral")
            self._tbl_hist.setCellWidget(ri, 7, tipo_badge)
            total_periodo += monto
            # col 8 — Ver btn
            btn_det = create_secondary_button(self, "🔍 Ver",
                                              "Ver detalles de esta compra")
            btn_det.clicked.connect(
                lambda _, cid=cid_, pnm=pnm_:
                    self._ver_detalle_compra(cid, pnm))
            self._tbl_hist.setCellWidget(ri, 8, btn_det)

        total_display = "—" if ocultar_totales else f"${total_periodo:,.2f}"
        self.lbl_hist_total_compras.setText(f"Total período: {total_display}")
        self.lbl_hist_num_compras.setText(f"{len(rows)} compra(s)")
        if hasattr(self, "_hist_empty"):
            self._hist_empty.setVisible(len(rows) == 0)
        if hasattr(self, "_hist_loading"):
            self._hist_loading.hide()
        self._actualizar_hist_kpi_sidebar(list(all_rows))

    # ── History KPI sidebar ────────────────────────────────────────────────────

    def _build_hist_kpi_sidebar(self) -> "QWidget":
        """Right KPI sidebar for history tab (190 px fixed)."""
        from PyQt5.QtWidgets import QScrollArea
        panel = QFrame()
        panel.setFixedWidth(190)
        panel.setFrameShape(QFrame.StyledPanel)
        panel.setStyleSheet(
            f"QFrame{{background:transparent;"
            f"border-left:1px solid {Colors.NEUTRAL.SLATE_200};}}"
        )
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 12, 10, 12)
        lay.setSpacing(8)

        def _section(title: str) -> QLabel:
            lbl = QLabel(title)
            lbl.setStyleSheet(
                f"font-size:10px;font-weight:700;color:{Colors.NEUTRAL.SLATE_500};"
                f"text-transform:uppercase;letter-spacing:0.5px;"
                f"border-bottom:1px solid {Colors.NEUTRAL.SLATE_200};padding-bottom:4px;"
            )
            return lbl

        def _kpi(label: str, init: str = "—") -> QLabel:
            lbl = QLabel(f"<b>{init}</b><br><span style='font-size:10px;"
                         f"color:{Colors.NEUTRAL.SLATE_500};'>{label}</span>")
            lbl.setStyleSheet("font-size:14px;padding:4px 0;")
            lbl.setTextFormat(Qt.RichText)
            return lbl

        lay.addWidget(_section("📊 PERÍODO"))
        self._kpi_total_periodo    = _kpi("Total comprado")
        self._kpi_num_compras      = _kpi("N° compras")
        self._kpi_ticket_prom      = _kpi("Ticket promedio")
        lay.addWidget(self._kpi_total_periodo)
        lay.addWidget(self._kpi_num_compras)
        lay.addWidget(self._kpi_ticket_prom)

        lay.addWidget(_section("📋 POR ESTADO"))
        self._kpi_completadas  = _kpi("Completadas",  "0  $0")
        self._kpi_credito      = _kpi("Crédito",      "0  $0")
        self._kpi_pendientes   = _kpi("Pendientes",   "0  $0")
        self._kpi_canceladas   = _kpi("Canceladas",   "0  $0")
        for w in (self._kpi_completadas, self._kpi_credito,
                  self._kpi_pendientes, self._kpi_canceladas):
            lay.addWidget(w)

        lay.addWidget(_section("📅 ESTE MES"))
        self._kpi_mes_compras    = _kpi("Compras mes",       "—")
        self._kpi_mes_recibido   = _kpi("Recibido mes",      "—")
        self._kpi_mes_pendiente  = _kpi("Pendiente mes",     "—")
        self._kpi_proveedores    = _kpi("Proveedores activos","—")
        for w in (self._kpi_mes_compras, self._kpi_mes_recibido,
                  self._kpi_mes_pendiente, self._kpi_proveedores):
            lay.addWidget(w)

        lay.addWidget(_section("⚠ ALERTAS"))
        self._kpi_alertas_lbl = QLabel("—")
        self._kpi_alertas_lbl.setWordWrap(True)
        self._kpi_alertas_lbl.setStyleSheet(
            f"font-size:11px;color:{Colors.NEUTRAL.SLATE_600};"
        )
        lay.addWidget(self._kpi_alertas_lbl)

        lay.addStretch()
        return panel

    def _actualizar_hist_kpi_sidebar(self, all_rows: list) -> None:
        """Compute and display KPIs from the full (unfiltered) result set."""
        if not hasattr(self, "_kpi_total_periodo"):
            return
        ocultar = self._usuario_rol in _ROLES_SIN_TOTALES

        totales: dict[str, float] = {}
        counts:  dict[str, int]   = {}
        grand_total = 0.0
        for r in all_rows:
            estado = str(r[5] or "").strip().lower()
            monto  = float(r[4] or 0)
            totales[estado] = totales.get(estado, 0.0) + monto
            counts[estado]  = counts.get(estado, 0) + 1
            grand_total += monto

        n_total = len(all_rows)
        ticket_prom = grand_total / n_total if n_total else 0.0

        def _fmt(v: float) -> str:
            return "—" if ocultar else f"${v:,.2f}"

        def _set_kpi(widget: QLabel, label: str, value: str) -> None:
            widget.setText(
                f"<b>{value}</b><br>"
                f"<span style='font-size:10px;color:{Colors.NEUTRAL.SLATE_500};'>{label}</span>"
            )

        _set_kpi(self._kpi_total_periodo, "Total comprado", _fmt(grand_total))
        _set_kpi(self._kpi_num_compras,   "N° compras",     str(n_total))
        _set_kpi(self._kpi_ticket_prom,   "Ticket promedio", _fmt(ticket_prom))

        def _estado_text(key: str) -> str:
            c = counts.get(key, 0)
            t = totales.get(key, 0.0)
            return f"{c}  {_fmt(t)}"

        _set_kpi(self._kpi_completadas, "Completadas",
                 _estado_text("completada"))
        _set_kpi(self._kpi_credito,     "Crédito",
                 _estado_text("crédito"))
        _set_kpi(self._kpi_pendientes,  "Pendientes",
                 _estado_text("pendiente"))
        _set_kpi(self._kpi_canceladas,  "Canceladas",
                 _estado_text("cancelada"))

        # Month-specific KPIs — via repository (no direct SQL in UI)
        if hasattr(self, "_kpi_mes_compras"):
            try:
                from datetime import date as _date
                _today = _date.today()
                _mes_desde = f"{_today.year}-{_today.month:02d}-01"
                _mes_hasta = f"{_today.year}-{_today.month:02d}-31 23:59:59"
                kpis = self._purchase_repo.get_monthly_kpis(
                    self.sucursal_id, _mes_desde, _mes_hasta)

                def _set_kpi_mes(widget, label, value):
                    widget.setText(
                        f"<b>{value}</b><br>"
                        f"<span style='font-size:10px;color:{Colors.NEUTRAL.SLATE_500};'>{label}</span>"
                    )

                _set_kpi_mes(self._kpi_mes_compras,   "Compras mes",         _fmt(kpis["total"]))
                _set_kpi_mes(self._kpi_mes_recibido,  "Recibido mes",        str(kpis["count"]))
                _set_kpi_mes(self._kpi_mes_pendiente, "Pendiente mes",       _fmt(kpis["pending_total"]))
                _set_kpi_mes(self._kpi_proveedores,   "Proveedores activos", str(kpis["provider_count"]))
            except Exception as _e:
                logger.debug("month KPIs: %s", _e)

        # Overdue / pending alerts
        alerts = []
        pend_count = counts.get("pendiente", 0)
        if pend_count:
            alerts.append(f"⚠ {pend_count} compra(s) pendiente(s)")
        cred_count = counts.get("crédito", 0)
        if cred_count:
            alerts.append(f"💳 {cred_count} en crédito")
        self._kpi_alertas_lbl.setText("\n".join(alerts) if alerts else "✔ Sin alertas")
        alert_color = Colors.WARNING_BASE if alerts else Colors.SUCCESS_BASE
        self._kpi_alertas_lbl.setStyleSheet(
            f"font-size:11px;color:{alert_color};"
        )

    def _hist_set_preset(self, days: int) -> None:
        """Set history date range from a quick preset button.

        days=0  → today only
        days=7  → last 7 days
        days=-1 → start of current month
        days=-3 → start of current quarter
        days=-12 → start of current year
        """
        today = QDate.currentDate()
        if days == 0:
            desde = today
            hasta = today
        elif days == 7:
            desde = today.addDays(-6)
            hasta = today
        elif days == -1:
            desde = QDate(today.year(), today.month(), 1)
            hasta = today
        elif days == -3:
            quarter_month = ((today.month() - 1) // 3) * 3 + 1
            desde = QDate(today.year(), quarter_month, 1)
            hasta = today
        elif days == -12:
            desde = QDate(today.year(), 1, 1)
            hasta = today
        else:
            desde = today.addDays(-days)
            hasta = today

        if hasattr(self, "_hist_desde"):
            self._hist_desde.setDate(desde)
        if hasattr(self, "_hist_hasta"):
            self._hist_hasta.setDate(hasta)
        self._hist_filter_changed()

    def _on_hist_row_selected(self) -> None:
        """Show inline purchase detail when a history row is selected."""
        if not hasattr(self, "_tbl_hist") or not hasattr(self, "_hist_detail_panel"):
            return
        sel = self._tbl_hist.selectedItems()
        if not sel:
            self._hist_detail_panel.setVisible(False)
            return
        row = self._tbl_hist.currentRow()
        # compra_id is stored in column 0 UserRole (set during _poblar_historial)
        id_item = self._tbl_hist.item(row, 0)
        if id_item is None:
            self._hist_detail_panel.setVisible(False)
            return
        compra_id = id_item.data(Qt.UserRole)
        if compra_id is None:
            # Fallback: try to parse from folio column text (best-effort)
            self._hist_detail_panel.setVisible(False)
            return
        po_id = id_item.data(Qt.UserRole + 1) or 0   # Phase 7
        try:
            items = self._purchase_repo.get_purchase_detail_items(compra_id)
            tbl = self._tbl_hist_detail
            tbl.setRowCount(len(items))
            for ri, it in enumerate(items):
                nombre = it["nombre"]
                qty, costo, subtotal = it["cantidad"], it["costo_unitario"], it["subtotal"]
                vals = [
                    str(nombre or ""),
                    f"{float(qty or 0):,.3f}",
                    f"${float(costo or 0):,.2f}",
                    f"${float(subtotal or 0):,.2f}",
                ]
                for ci, v in enumerate(vals):
                    cell = QTableWidgetItem(v)
                    cell.setFlags(Qt.ItemIsEnabled)
                    if ci > 0:
                        cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    tbl.setItem(ri, ci, cell)
            folio_compra = str(self._tbl_hist.item(row, 0).text() if self._tbl_hist.item(row, 0) else "")
            self._hist_detail_panel.setTitle(
                f"Detalle compra #{compra_id}  ({len(items)} producto(s))"
            )
            self._hist_detail_panel.setVisible(True)
            # Phase 7 — timeline
            self._refresh_hist_timeline(int(po_id), folio_compra)
        except Exception as exc:
            logger.debug("_on_hist_row_selected: %s", exc)
            self._hist_detail_panel.setVisible(False)

    def _refresh_hist_timeline(self, po_id: int, compra_folio: str) -> None:
        """
        FASE 9 — Full documental lifecycle timeline in the history detail panel.

        Chain: [PR?] → [Aprobada?] → [PO] → [Recepción] → [CXP] → [🛒 Compra]

        Uses repository only — no SQL in UI layer.
        Gracefully degrades: if repo unavailable, shows minimal PO node.
        """
        bar = getattr(self, '_hist_timeline_bar', None)
        lay = getattr(self, '_hist_timeline_lay', None)
        if bar is None or lay is None:
            return

        # Clear previous widgets
        while lay.count():
            child = lay.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not po_id:
            bar.hide()
            return

        def _node(icon: str, label: str, sublabel: str,
                  done: bool, active: bool = False) -> QFrame:
            """Build a timeline node using design tokens only."""
            if done:
                bg     = f"{Colors.SUCCESS_BASE}22"
                border = f"{Colors.SUCCESS_BASE}60"
                txt    = Colors.SUCCESS_BASE
            elif active:
                bg     = f"{Colors.PRIMARY_BASE}22"
                border = f"{Colors.PRIMARY_BASE}60"
                txt    = Colors.PRIMARY_BASE
            else:
                bg     = Colors.NEUTRAL.SLATE_100
                border = Colors.NEUTRAL.SLATE_300
                txt    = Colors.NEUTRAL.SLATE_400
            f = QFrame()
            f.setStyleSheet(
                f"background:{bg};border:1px solid {border};"
                f"border-radius:5px;padding:2px 6px;"
            )
            fl = QVBoxLayout(f)
            fl.setContentsMargins(4, 2, 4, 2)
            fl.setSpacing(0)
            top = QLabel(f"{icon} <b>{label}</b>")
            top.setStyleSheet(f"font-size:11px;color:{txt};")
            top.setTextFormat(Qt.RichText)
            sub = QLabel(sublabel)
            sub.setStyleSheet(f"font-size:9px;color:{Colors.NEUTRAL.SLATE_500};")
            fl.addWidget(top)
            fl.addWidget(sub)
            return f

        def _arrow() -> QLabel:
            lbl = QLabel("→")
            lbl.setStyleSheet(f"color:{Colors.NEUTRAL.SLATE_400};font-size:16px;")
            lbl.setAlignment(Qt.AlignCenter)
            return lbl

        # ── 1. Fetch PO via repo only (no SQL fallback) ───────────────────────
        po_repo = getattr(self.container, 'purchase_order_repo', None)
        po = po_repo.get_by_id(po_id) if po_repo else None
        if po is None:
            lay.addWidget(_node("📦", f"PO-{po_id}", "Orden de Compra",
                                done=False, active=True))
            lay.addStretch()
            bar.show()
            return

        po_folio  = po.get("folio") or f"PO-{po_id}"
        po_estado = str(po.get("estado") or "ABIERTA").upper()
        pr_id     = int(po.get("pr_id") or 0)

        po_recibida = po_estado in ("RECIBIDA", "CERRADA")
        po_parcial  = po_estado == "PARCIAL"

        # ── 2. Fetch PR via repo only (no SQL fallback) ───────────────────────
        pr          = None
        pr_folio    = ""
        aprobado_por = ""
        pr_estado_raw = ""
        if pr_id:
            pr_repo = getattr(self.container, 'purchase_request_repo', None)
            pr = pr_repo.get_by_id(pr_id) if pr_repo else None
            if pr:
                pr_folio      = pr.get("folio") or f"PR-{pr_id}"
                aprobado_por  = pr.get("aprobado_por") or ""
                pr_estado_raw = str(pr.get("estado") or "BORRADOR").upper()

        # ── 3. Build timeline ─────────────────────────────────────────────────

        # Node: PR (if linked)
        if pr_folio:
            pr_done = pr_estado_raw in ("APROBADA", "CONVERTIDA_A_PO")
            lay.addWidget(_node(
                "📋", pr_folio, f"PR · {pr_estado_raw.lower() or 'solicitud'}",
                done=pr_done, active=not pr_done,
            ))
            lay.addWidget(_arrow())

        # Node: APROBACIÓN (if PR was approved)
        if aprobado_por:
            lay.addWidget(_node("✓", "Aprobada", f"por {aprobado_por}",
                                done=True, active=False))
            lay.addWidget(_arrow())

        # Node: PO
        lay.addWidget(_node(
            "📦", po_folio, f"PO · {po_estado.lower()}",
            done=po_recibida, active=not po_recibida,
        ))
        lay.addWidget(_arrow())

        # Node: RECEPCIÓN
        rec_done   = po_recibida
        rec_active = po_parcial
        rec_sub    = ("Recibida completa" if rec_done
                      else "Recepción parcial" if rec_active
                      else "Pendiente de recepción")
        lay.addWidget(_node("📥", "Recepción", rec_sub,
                            done=rec_done, active=rec_active))

        # Node: Compra registrada (always when PO exists)
        if compra_folio:
            lay.addWidget(_arrow())
            lay.addWidget(_node("🛒", compra_folio, "Compra registrada",
                                done=True, active=False))

        # Node: CXP — shown as pending indicator when PO fully received.
        # No CxP repo lookup here — presence shown structurally, not data-driven.
        if po_recibida:
            lay.addWidget(_arrow())
            lay.addWidget(_node("💳", "CXP", "Por conciliar",
                                done=False, active=False))

        lay.addStretch()
        bar.show()

    def _ver_detalle_compra(self, compra_id: int, proveedor_nombre: str = "") -> None:
        """Muestra el detalle completo de una compra: recibo + timeline + acciones."""
        try:
            compra_dict = self._purchase_repo.get_purchase_full(compra_id)
            if not compra_dict:
                return
            raw_items = self._purchase_repo.get_purchase_detail_items(compra_id)
            # Normalise to the key names _generar_html_compra expects
            items = [
                {"nombre": it["nombre"], "cantidad": it["cantidad"],
                 "costo_unitario": it["costo_unitario"], "subtotal": it["subtotal"]}
                for it in raw_items
            ]

            if not proveedor_nombre:
                proveedor_nombre = self._purchase_repo.get_provider_name(
                    compra_dict.get("proveedor_id", 0))

            html = self._generar_html_compra(compra_dict, items, proveedor_nombre)

            from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
            from PyQt5.QtGui import QTextDocument

            dlg = QDialog(self)
            dlg.setWindowTitle(f"Compra {compra_dict.get('folio', compra_id)}")
            dlg.setMinimumSize(520, 580)
            lay_d = QVBoxLayout(dlg)
            lay_d.setSpacing(8)

            # Timeline
            timeline_html = self._generar_timeline_html(compra_dict)
            tl_browser = QTextBrowser()
            tl_browser.setHtml(timeline_html)
            tl_browser.setMaximumHeight(90)
            tl_browser.setFrameShape(QFrame.NoFrame)
            lay_d.addWidget(tl_browser)

            # Receipt
            browser = QTextBrowser()
            browser.setHtml(html)
            lay_d.addWidget(browser)

            # Actions
            btn_row = QHBoxLayout()
            estado_actual = str(compra_dict.get('estado', '')).lower()

            btn_print  = create_primary_button(self, "🖨️ Imprimir",
                                               "Imprimir comprobante de compra")
            btn_close2 = create_secondary_button(self, "Cerrar", "Cerrar vista previa")

            def _do_print2():
                printer = QPrinter(QPrinter.HighResolution)
                if QPrintDialog(printer, dlg).exec_() == QPrintDialog.Accepted:
                    doc = QTextDocument()
                    doc.setHtml(html)
                    doc.print_(printer)

            btn_print.clicked.connect(_do_print2)
            btn_close2.clicked.connect(dlg.accept)
            btn_row.addWidget(btn_print)

            # Conditional action buttons based on status + role
            if estado_actual not in ("cancelada",) and self._tiene_permiso("cancelar"):
                btn_cancel_oc = create_danger_button(
                    self, "🚫 Cancelar compra",
                    "Cancelar esta compra (requiere motivo y PIN — auditado)")
                btn_cancel_oc.clicked.connect(
                    lambda _, cid=compra_dict.get('id', compra_id), d=dlg:
                        self._cancelar_compra(cid, d))
                btn_row.addWidget(btn_cancel_oc)

            if estado_actual == "cancelada" and self._tiene_permiso("reabrir"):
                btn_reabrir = create_secondary_button(
                    self, "🔄 Reabrir compra",
                    "Reabrir esta compra como pendiente (requiere PIN)")
                btn_reabrir.clicked.connect(
                    lambda _, cid=compra_dict.get('id', compra_id), d=dlg:
                        self._reabrir_compra(cid, d))
                btn_row.addWidget(btn_reabrir)

            btn_row.addStretch()
            btn_row.addWidget(btn_close2)
            lay_d.addLayout(btn_row)
            dlg.exec_()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _generar_timeline_html(self, compra: dict) -> str:
        """Genera HTML de línea de tiempo del ciclo de vida de la compra."""
        estado = str(compra.get('estado', '')).lower()
        fecha  = str(compra.get('fecha', ''))[:16]
        usuario = compra.get('usuario', '—')

        steps = [
            ("Creada",    True,  fecha),
            ("Procesada", True,  fecha),
            ("Completada", estado in ("completada", "completa", "credito", "parcial"), ""),
            ("Cancelada",  estado == "cancelada", ""),
        ]
        # For cancelled → show as terminal red step
        if estado == "cancelada":
            steps[2] = ("Completada", False, "")
            steps[3] = ("Cancelada",  True,  "")

        items_html = ""
        for label, active, ts in steps:
            if label == "Cancelada" and estado != "cancelada":
                continue
            color   = Colors.SUCCESS_BASE if active else Colors.NEUTRAL.SLATE_300
            dot_bg  = color
            txt_col = Colors.NEUTRAL.SLATE_700 if active else Colors.NEUTRAL.SLATE_400
            ts_txt  = f"<br><small style='color:#888;'>{ts}</small>" if ts else ""
            items_html += (
                f"<td align='center' style='padding:4px 16px;'>"
                f"<span style='display:inline-block;width:14px;height:14px;"
                f"border-radius:50%;background:{dot_bg};'></span>"
                f"<br><span style='color:{txt_col};font-size:11px;'>{label}</span>"
                f"{ts_txt}</td>"
                f"<td style='border-top:2px solid {color};width:40px;vertical-align:middle;'"
                f"></td>"
            )
        # Remove trailing separator
        items_html = items_html.rstrip()

        return (f"<html><body style='font-family:sans-serif;'>"
                f"<table border='0' cellspacing='0' cellpadding='0' "
                f"style='margin:6px auto;'><tr>{items_html}</tr></table>"
                f"<p style='text-align:center;font-size:10px;color:#888;margin:0;'>"
                f"Operador: {usuario}</p>"
                f"</body></html>")

    def _cancelar_compra(self, compra_id: int, dlg_padre: QDialog) -> None:
        """Cancela una compra. Requiere: motivo + PIN de supervisor (si configurado)."""
        state = self._purchase_repo.get_purchase_state(compra_id)
        if not state:
            return
        estado_actual = state["estado"]
        folio         = state["folio"]

        if estado_actual == "cancelada":
            QMessageBox.information(self, "Aviso", "Esta compra ya está cancelada.")
            return

        svc = getattr(self.container, 'purchase_service', None)
        reversal_available = (svc is not None
                              and hasattr(svc, 'cancel_purchase_with_reversal'))

        inv_note = ("El inventario ingresado SERÁ revertido automáticamente."
                    if reversal_available else
                    "El inventario ingresado NO se revierte automáticamente.")

        conf = _ConfirmDestructiveDialog(
            "Cancelar Compra",
            f"¿Cancelar la compra {folio}?\n\n"
            "Esta acción se registrará en el audit log y no puede deshacerse.\n"
            f"{inv_note}",
            accion_label="Cancelar compra",
            require_reason=True,
            parent=self,
        )
        if conf.exec_() != QDialog.Accepted:
            return

        motivo = conf.motivo
        # PIN de supervisor (sólo si configurado en DB)
        if not _PINDialog.verificar(self.container.db, f"Cancelar compra {folio}", self):
            return

        try:
            rev_warnings: list = []
            if reversal_available:
                rev_warnings = svc.cancel_purchase_with_reversal(
                    compra_id=compra_id,
                    user=self.usuario_actual,
                    branch_id=self.sucursal_id,
                    folio=folio,
                )
            else:
                self._purchase_repo.cancel_purchase(compra_id)

            try:
                audit_write(
                    self.container,
                    modulo="COMPRAS",
                    accion="COMPRA_CANCELADA",
                    entidad="compras",
                    entidad_id=str(compra_id),
                    usuario=self.usuario_actual,
                    detalles=(f"Folio {folio} | Motivo: {motivo}"
                              + (f" | Reversión parcial: {rev_warnings}" if rev_warnings else "")),
                    before={"estado": estado_actual},
                    after={"estado": "cancelada",
                           "inventario_revertido": reversal_available,
                           "rev_warnings": rev_warnings},
                    sucursal_id=self.sucursal_id,
                )
            except Exception:
                pass

            Toast.success(self, "✓ Compra cancelada", f"Folio {folio}")
            if rev_warnings:
                from PyQt5.QtWidgets import QMessageBox as _MB
                _MB.warning(
                    self, "Reversión parcial",
                    "La compra fue cancelada pero algunos ítems no pudieron\n"
                    "revertirse por stock insuficiente:\n\n"
                    + "\n".join(f"• {w}" for w in rev_warnings),
                )
            dlg_padre.accept()
            QTimer.singleShot(0, self._cargar_historial_compras)
        except Exception as e:
            QMessageBox.critical(self, "Error al cancelar", str(e))

    def _reabrir_compra(self, compra_id: int, dlg_padre: QDialog) -> None:
        """
        Reabre una compra cancelada como 'pendiente'.
        IMPORTANTE: No revierte inventario automáticamente — el supervisor
        debe verificar manualmente el estado del inventario.
        Requiere PIN de supervisor.
        """
        state = self._purchase_repo.get_purchase_state(compra_id)
        if not state:
            return

        folio  = state["folio"]
        estado = state["estado"]

        if estado != "cancelada":
            QMessageBox.information(self, "Aviso",
                "Solo se pueden reabrir compras con estado 'cancelada'.")
            return

        conf = _ConfirmDestructiveDialog(
            "Reabrir Compra",
            f"¿Reabrir la compra {folio}?\n\n"
            "⚠ El inventario fue revertido al cancelar esta compra.\n"
            "Volver a abrir NO readmite el inventario automáticamente —\n"
            "deberás registrar una nueva entrada si es necesario.\n"
            "La compra quedará en estado PENDIENTE.",
            accion_label="Reabrir como pendiente",
            require_reason=True,
            parent=self,
        )
        if conf.exec_() != QDialog.Accepted:
            return

        if not _PINDialog.verificar(self.container.db, f"Reabrir compra {folio}", self):
            return

        try:
            self._purchase_repo.reopen_purchase(compra_id)
            try:
                audit_write(
                    self.container,
                    modulo="COMPRAS",
                    accion="COMPRA_REABIERTA",
                    entidad="compras",
                    entidad_id=str(compra_id),
                    usuario=self.usuario_actual,
                    detalles=f"Folio {folio} | Motivo: {conf.motivo}",
                    before={"estado": "cancelada"},
                    after={"estado": "pendiente"},
                    sucursal_id=self.sucursal_id,
                )
            except Exception:
                pass
            Toast.success(self, "🔄 Compra reabierta", f"Folio {folio} → Pendiente")
            dlg_padre.accept()
            QTimer.singleShot(0, self._cargar_historial_compras)
        except Exception as e:
            QMessageBox.critical(self, "Error al reabrir", str(e))

    def _hist_pag_prev(self) -> None:
        if self._hist_page > 0:
            self._hist_page -= 1
            if hasattr(self, '_hist_all_rows'):
                self._poblar_historial(self._hist_all_rows)
            else:
                self._cargar_historial_compras()

    def _hist_pag_next(self) -> None:
        self._hist_page += 1
        if hasattr(self, '_hist_all_rows'):
            self._poblar_historial(self._hist_all_rows)
        else:
            self._cargar_historial_compras()

    def _generar_html_compra(self, compra: dict, items: list,
                              proveedor_nombre: str = "") -> str:
        """Genera el ticket HTML de una compra para impresión."""
        prov_display = proveedor_nombre or f"ID {compra.get('proveedor_id','?')}"
        rows_html = ""
        for idx, it in enumerate(items):
            # Print HTML — fixed colors intentional; theme CSS does not apply to print output
            bg_row = "#f8fafc" if idx % 2 == 0 else "#ffffff"
            rows_html += (
                f"<tr style='background:{bg_row};'>"
                f"<td style='padding:4px 6px;'>{it.get('nombre','')}</td>"
                f"<td align='right' style='padding:4px 6px;font-family:monospace;'>"
                f"{float(it.get('cantidad',0)):.3f}</td>"
                f"<td align='right' style='padding:4px 6px;font-family:monospace;'>"
                f"${float(it.get('costo_unitario',0)):.4f}</td>"
                f"<td align='right' style='padding:4px 6px;font-family:monospace;'>"
                f"${float(it.get('subtotal',0)):.2f}</td></tr>"
            )
        ref = compra.get('observaciones') or compra.get('factura') or '—'
        return f"""
        <html><body style='font-family:sans-serif;font-size:12px;margin:0;padding:0;'>
        <h3 style='text-align:center;margin:8px 0 4px;'>RECIBO DE COMPRA</h3>
        <hr style='margin:4px 0 8px;'>
        <table width='100%' border='0' cellspacing='0' cellpadding='0'
               style='font-size:12px;margin-bottom:8px;'>
          <tr><td><b>Folio:</b></td><td style='font-family:monospace;'>{compra.get('folio','?')}</td></tr>
          <tr><td><b>Fecha:</b></td><td style='font-family:monospace;'>{str(compra.get('fecha',''))[:16]}</td></tr>
          <tr><td><b>Proveedor:</b></td><td>{prov_display}</td></tr>
          <tr><td><b>Referencia:</b></td><td style='font-family:monospace;'>{ref}</td></tr>
          <tr><td><b>Usuario:</b></td><td>{compra.get('usuario','?')}</td></tr>
          <tr><td><b>Condición:</b></td><td>{str(compra.get('estado','?')).upper()}</td></tr>
        </table>
        <table width='100%' border='0' cellspacing='0'
               style='border-collapse:collapse;font-size:12px;'>
          <tr style='background:{Colors.PRIMARY_BASE};color:#fff;'>
            <th align='left'  style='padding:5px 6px;'>Producto</th>
            <th align='right' style='padding:5px 6px;'>Cant.</th>
            <th align='right' style='padding:5px 6px;'>Costo</th>
            <th align='right' style='padding:5px 6px;'>Subtotal</th>
          </tr>
          {rows_html}
        </table>
        <hr style='margin:8px 0 4px;'>
        <p style='font-size:14px;font-weight:bold;color:{Colors.SUCCESS_BASE};margin:4px 0;'>
          Total: ${float(compra.get('total',0)):,.2f}</p>
        </body></html>"""

    def _on_refresh(self, event_type: str, data: dict) -> None:
        """EventBus handler: refresh product search, providers, stats and history."""
        if hasattr(self, '_buscador'):
            self._buscador.set_db(self.container.db)
        self.cargar_proveedores()
        QTimer.singleShot(0, self._refresh_stats)
        if hasattr(self, '_tbl_hist') and self._tabs.currentIndex() == 2:
            self._cargar_historial_compras()
        # FASE 8: when a PO receipt is confirmed, refresh the documental sidebar
        # so the PO state (PARCIAL / RECIBIDA) is reflected immediately.
        # Small delay (50 ms) ensures DB writes from ReceivePOAdapter are visible.
        if event_type == "RECEPCION_CONFIRMADA" and data.get("source") == "PO":
            QTimer.singleShot(50, self._cargar_docs_erp)

    def _exportar_historial_csv(self) -> None:
        """Exporta el historial de compras a CSV.

        FASE 9: lee del cache _hist_all_rows (datos completos de BD),
        aplica los mismos filtros activos, incluye Tipo Doc y Estado PO.
        """
        import csv, os
        all_rows = getattr(self, '_hist_all_rows', None)
        if not all_rows:
            QMessageBox.information(self, "Exportar", "No hay datos para exportar.")
            return

        # Aplicar los mismos filtros que _poblar_historial
        filtros  = self._hist_filter.values() if hasattr(self, "_hist_filter") else {}
        estado   = (filtros.get("estado")   or "").strip().lower()
        search   = (filtros.get("search")   or "").strip().lower()
        tipo_doc = (filtros.get("tipo_doc") or "").strip().lower()
        po_est   = (filtros.get("po_estado") or "").strip().upper()

        rows = list(all_rows)
        if estado:
            rows = [r for r in rows if str(r[5] or "").strip().lower() == estado]
        if po_est:
            rows = [r for r in rows if str(r[10] if len(r) > 10 else "").strip().upper() == po_est]
        if search:
            rows = [r for r in rows if
                    search in str(r[0] or "").lower() or
                    search in str(r[2] or "").lower() or
                    search in str(r[3] or "").lower()]
        if tipo_doc == "directa":
            rows = [r for r in rows if not (len(r) > 9 and int(r[9] or 0))]
        elif tipo_doc == "con po":
            rows = [r for r in rows if len(r) > 9 and int(r[9] or 0)]

        if not rows:
            QMessageBox.information(self, "Exportar", "No hay datos para exportar con los filtros actuales.")
            return

        default_name = f"compras_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar historial de compras", default_name, "CSV (*.csv)")
        if not path:
            return

        ocultar_totales = self._usuario_rol in _ROLES_SIN_TOTALES
        try:
            headers = [
                "Folio", "Fecha", "Proveedor", "Usuario", "Total",
                "Cond. Pago", "Estado", "Tipo Doc", "PO #", "Estado PO",
            ]
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for r in rows:
                    po_id    = int(r[9] or 0) if len(r) > 9 else 0
                    po_est_r = str(r[10] or "") if len(r) > 10 else ""
                    total    = "—" if ocultar_totales else str(r[4] or "")
                    tipo     = f"PO #{po_id}" if po_id else "Directa"
                    writer.writerow([
                        r[0] or "", r[1] or "", r[2] or "", r[3] or "",
                        total,
                        r[7] or "" if len(r) > 7 else "",  # condicion_pago
                        r[5] or "",                          # estado
                        tipo, po_id or "", po_est_r,
                    ])
            Toast.success(self, "✅ Exportado",
                          f"{os.path.basename(path)} · {len(rows)} registros")
        except Exception as e:
            QMessageBox.critical(self, "Error al exportar", str(e))

    def _fallback_compra_directa(self, proveedor_id, doc_ref, pago, total,
                                  items) -> str:
        """Safety stub: direct DB fallback is disabled for Phase 5.

        Compra directa debe pasar por RegistrarCompraUC → PurchaseService para
        mantener una única ruta de inventario, CxP, asientos, lotes y auditoría.
        Este método permanece solo por compatibilidad con referencias antiguas y
        no debe ser llamado desde el flujo principal.
        """
        raise RuntimeError(
            "Fallback directo deshabilitado: usa RegistrarCompraUC/PurchaseService."
        )
        return f"""
        <html><body style='font-family:sans-serif;font-size:12px;margin:0;padding:0;'>
        <h3 style='text-align:center;margin:8px 0 4px;'>RECIBO DE COMPRA</h3>
        <hr style='margin:4px 0 8px;'>
        <table width='100%' border='0' cellspacing='0' cellpadding='0'
               style='font-size:12px;margin-bottom:8px;'>
          <tr><td><b>Folio:</b></td><td style='font-family:monospace;'>{compra.get('folio','?')}</td></tr>
          <tr><td><b>Fecha:</b></td><td style='font-family:monospace;'>{str(compra.get('fecha',''))[:16]}</td></tr>
          <tr><td><b>Proveedor:</b></td><td>{prov_display}</td></tr>
          <tr><td><b>Referencia:</b></td><td style='font-family:monospace;'>{ref}</td></tr>
          <tr><td><b>Usuario:</b></td><td>{compra.get('usuario','?')}</td></tr>
          <tr><td><b>Condición:</b></td><td>{str(compra.get('estado','?')).upper()}</td></tr>
        </table>
        <table width='100%' border='0' cellspacing='0'
               style='border-collapse:collapse;font-size:12px;'>
          <tr style='background:{Colors.PRIMARY_BASE};color:#fff;'>
            <th align='left'  style='padding:5px 6px;'>Producto</th>
            <th align='right' style='padding:5px 6px;'>Cant.</th>
            <th align='right' style='padding:5px 6px;'>Costo</th>
            <th align='right' style='padding:5px 6px;'>Subtotal</th>
          </tr>
          {rows_html}
        </table>
        <hr style='margin:8px 0 4px;'>
        <p style='font-size:14px;font-weight:bold;color:{Colors.SUCCESS_BASE};margin:4px 0;'>
          Total: ${float(compra.get('total',0)):,.2f}</p>
        </body></html>"""

    def _on_refresh(self, event_type: str, data: dict) -> None:
        """EventBus handler: refresh product search, providers, stats and history."""
        if hasattr(self, '_buscador'):
            self._buscador.set_db(self.container.db)
        self.cargar_proveedores()
        QTimer.singleShot(0, self._refresh_stats)
        if hasattr(self, '_tbl_hist') and self._tabs.currentIndex() == 2:
            self._cargar_historial_compras()
        # FASE 8: when a PO receipt is confirmed, refresh the documental sidebar
        # so the PO state (PARCIAL / RECIBIDA) is reflected immediately.
        # Small delay (50 ms) ensures DB writes from ReceivePOAdapter are visible.
        if event_type == "RECEPCION_CONFIRMADA" and data.get("source") == "PO":
            QTimer.singleShot(50, self._cargar_docs_erp)

    def _exportar_historial_csv(self) -> None:
        """Exporta el historial de compras a CSV.

        FASE 9: lee del cache _hist_all_rows (datos completos de BD),
        aplica los mismos filtros activos, incluye Tipo Doc y Estado PO.
        """
        import csv, os
        all_rows = getattr(self, '_hist_all_rows', None)
        if not all_rows:
            QMessageBox.information(self, "Exportar", "No hay datos para exportar.")
            return

        # Aplicar los mismos filtros que _poblar_historial
        filtros  = self._hist_filter.values() if hasattr(self, "_hist_filter") else {}
        estado   = (filtros.get("estado")   or "").strip().lower()
        search   = (filtros.get("search")   or "").strip().lower()
        tipo_doc = (filtros.get("tipo_doc") or "").strip().lower()
        po_est   = (filtros.get("po_estado") or "").strip().upper()

        rows = list(all_rows)
        if estado:
            rows = [r for r in rows if str(r[5] or "").strip().lower() == estado]
        if po_est:
            rows = [r for r in rows if str(r[10] if len(r) > 10 else "").strip().upper() == po_est]
        if search:
            rows = [r for r in rows if
                    search in str(r[0] or "").lower() or
                    search in str(r[2] or "").lower() or
                    search in str(r[3] or "").lower()]
        if tipo_doc == "directa":
            rows = [r for r in rows if not (len(r) > 9 and int(r[9] or 0))]
        elif tipo_doc == "con po":
            rows = [r for r in rows if len(r) > 9 and int(r[9] or 0)]

        if not rows:
            QMessageBox.information(self, "Exportar", "No hay datos para exportar con los filtros actuales.")
            return

        default_name = f"compras_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar historial de compras", default_name, "CSV (*.csv)")
        if not path:
            return

        ocultar_totales = self._usuario_rol in _ROLES_SIN_TOTALES
        try:
            headers = [
                "Folio", "Fecha", "Proveedor", "Usuario", "Total",
                "Cond. Pago", "Estado", "Tipo Doc", "PO #", "Estado PO",
            ]
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for r in rows:
                    po_id    = int(r[9] or 0) if len(r) > 9 else 0
                    po_est_r = str(r[10] or "") if len(r) > 10 else ""
                    total    = "—" if ocultar_totales else str(r[4] or "")
                    tipo     = f"PO #{po_id}" if po_id else "Directa"
                    writer.writerow([
                        r[0] or "", r[1] or "", r[2] or "", r[3] or "",
                        total,
                        r[7] or "" if len(r) > 7 else "",  # condicion_pago
                        r[5] or "",                          # estado
                        tipo, po_id or "", po_est_r,
                    ])
            Toast.success(self, "✅ Exportado",
                          f"{os.path.basename(path)} · {len(rows)} registros")
        except Exception as e:
            QMessageBox.critical(self, "Error al exportar", str(e))

    def _fallback_compra_directa(self, proveedor_id, doc_ref, pago, total,
                                  items) -> str:
        """Safety stub: direct DB fallback is disabled for Phase 5.

        Compra directa debe pasar por RegistrarCompraUC → PurchaseService para
        mantener una única ruta de inventario, CxP, asientos, lotes y auditoría.
        Este método permanece solo por compatibilidad con referencias antiguas y
        no debe ser llamado desde el flujo principal.
        """
        raise RuntimeError(
            "Fallback directo deshabilitado: usa RegistrarCompraUC/PurchaseService."
        )