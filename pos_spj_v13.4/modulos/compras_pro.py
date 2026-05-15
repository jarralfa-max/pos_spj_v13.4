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
from modulos.spj_refresh_mixin import RefreshMixin
from core.services.auto_audit import audit_write
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QFrame,
    QLabel, QComboBox, QLineEdit, QPushButton, QDoubleSpinBox, QSpinBox, QCompleter,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QMenu, QSizePolicy, QCheckBox, QListWidget, QListWidgetItem,
    QDialog, QShortcut, QTextBrowser, QDateEdit, QFileDialog,
)
from PyQt5.QtCore import Qt, QTimer, QThread, QStringListModel, QDate, pyqtSignal
from PyQt5.QtGui import QCursor, QKeySequence
from datetime import datetime
import json, logging, os

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
                       COALESCE(c.moneda,'MXN') AS moneda
                FROM compras c
                LEFT JOIN proveedores p ON p.id=c.proveedor_id
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
        # Update ProductSearchWidget db ref (same connection, already live)
        if hasattr(self, '_buscador'):
            self._buscador.set_db(self.container.db)

    def set_usuario_actual(self, usuario: str, rol: str = "") -> None:
        self.usuario_actual = usuario
        self._usuario_rol = rol.upper().strip()
        QTimer.singleShot(0, self._aplicar_permisos_ui)
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

        # ── Stats bar ─────────────────────────────────────────────────────────
        root.addWidget(self._crear_stats_compras())

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

        self._tabs.currentChanged.connect(self._on_tab_change)
        self._normalizar_botones_ui()

    def _normalizar_botones_ui(self) -> None:
        """Normaliza botones propios del módulo (excluye RecepcionQRWidget)."""
        _recv = getattr(self, '_recv_qr', None)
        for btn in self.findChildren(QPushButton):
            if btn.minimumWidth() and btn.minimumWidth() <= 40:
                continue
            # Don't touch buttons that belong to the embedded QR widget
            if _recv is not None and _recv.isAncestorOf(btn):
                continue
            btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
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
        """3-column ERP layout: Provider Sidebar | Main Form + Cart | Financial Summary"""
        outer = QHBoxLayout(parent)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Left: provider list + templates ──────────────────────────────────
        outer.addWidget(self._build_provider_sidebar())

        # ── Center: document header + search + cart + IVA row ─────────────────
        center_w = QWidget()
        center_w.setObjectName("purchaseCenterPanel")
        center_lay = QVBoxLayout(center_w)
        center_lay.setSpacing(8)
        center_lay.setContentsMargins(8, 6, 8, 6)
        outer.addWidget(center_w, 1)

        # ── Right: summary + payment + actions ────────────────────────────────
        outer.addWidget(self._build_summary_panel())

        lay = center_lay  # alias so body below builds into the center panel

        # ── Encabezado del documento ──────────────────────────────────────────
        grp_doc = QGroupBox("📄 Datos del Documento")
        grp_doc.setObjectName("styledGroup")
        form = QFormLayout(grp_doc)
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._proveedor_id_selected = None
        self._proveedores_cache = []
        self.txt_proveedor = QLineEdit()
        self.txt_proveedor.setPlaceholderText("Buscar proveedor…")
        self.txt_proveedor.setMinimumWidth(280)
        self._prov_model = QStringListModel(self)
        self._prov_completer = QCompleter(self._prov_model, self)
        self._prov_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._prov_completer.setFilterMode(Qt.MatchContains)
        self.txt_proveedor.setCompleter(self._prov_completer)
        self.txt_proveedor.editingFinished.connect(self._resolver_proveedor_desde_texto)
        self._lbl_prov_status = QLabel("⚠ Sin proveedor seleccionado")
        self._lbl_prov_status.setObjectName("caption")
        self._lbl_prov_status.setStyleSheet(f"color:{Colors.WARNING_BASE};")

        self._lbl_prov_info = QLabel("")
        self._lbl_prov_info.setObjectName("caption")
        self._lbl_prov_info.setWordWrap(True)
        self._lbl_prov_info.hide()

        self.txt_factura = QLineEdit()
        self.txt_factura.setPlaceholderText("Ej. FAC-001 / REM-00129 (opcional)")

        self._date_factura = QDateEdit(QDate.currentDate())
        self._date_factura.setCalendarPopup(True)
        self._date_factura.setDisplayFormat("dd/MMM/yyyy")

        self.cmb_sucursal_destino = QComboBox()
        self.cmb_sucursal_destino.setToolTip(
            "Sucursal a la que ingresará el inventario de esta compra")
        self._cargar_sucursales_compra()

        self._cmb_moneda = QComboBox()
        for code, label in [("MXN", "MXN — Peso Mexicano"), ("USD", "USD — Dólar"), ("EUR", "EUR — Euro")]:
            self._cmb_moneda.addItem(label, code)

        form.addRow("Proveedor:*", self.txt_proveedor)
        form.addRow("", self._lbl_prov_status)
        form.addRow("", self._lbl_prov_info)
        form.addRow("No. Factura/Remisión:", self.txt_factura)
        form.addRow("Fecha factura:", self._date_factura)
        form.addRow("Moneda:", self._cmb_moneda)
        form.addRow("Sucursal destino:*", self.cmb_sucursal_destino)
        lay.addWidget(grp_doc)

        # ── Buscador con scanner ──────────────────────────────────────────────
        from modulos.spj_product_search import ProductSearchWidget
        self._buscador = ProductSearchWidget(
            db=self.container.db,
            placeholder="🔍 Buscar por nombre, código interno, ID o escanear barcode...",
            show_stock=True,
        )
        self._buscador.producto_seleccionado.connect(self._agregar_producto)
        lay.addWidget(self._buscador)
        self._trad_filter = FilterBar(self, placeholder="Filtrar carrito por nombre de producto…")
        self._trad_filter.filters_changed.connect(lambda _v: self._refresh_tabla())
        lay.addWidget(self._trad_filter)

        # ── Carrito editable ──────────────────────────────────────────────────
        self._grp_cart = QGroupBox("🛒 Carrito  —  doble clic: editar  ·  clic derecho: opciones")
        self._grp_cart.setObjectName("styledGroup")
        cart_lay = QVBoxLayout(self._grp_cart)

        self.tabla = QTableWidget()
        self.tabla.setColumnCount(9)
        self.tabla.setHorizontalHeaderLabels(
            ["ID", "Producto", "Unidad", "Cant.", "Costo Unit.", "Desc%", "IVA%", "Subtotal", ""])
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (0, 2, 3, 4, 5, 6, 7, 8):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.doubleClicked.connect(self._editar_fila)
        self.tabla.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabla.customContextMenuRequested.connect(self._menu_fila)
        self.tabla.setObjectName("tableView")
        self._cart_loading = LoadingIndicator("Actualizando carrito…", self)
        self._cart_loading.hide()
        cart_lay.addWidget(self._cart_loading)
        cart_lay.addWidget(self.tabla)
        self._cart_empty = EmptyStateWidget(
            "Carrito vacío",
            "Agrega productos o ajusta el filtro del carrito.",
            "🧺",
            self,
        )
        self._cart_empty.hide()
        cart_lay.addWidget(self._cart_empty)

        # Cart toolbar
        cart_tb = QHBoxLayout()
        btn_clear = create_danger_button(self, "🗑 Limpiar todo", "Vaciar carrito de compras")
        btn_clear.clicked.connect(self._limpiar_carrito)
        btn_del_sel = create_danger_button(self, "🗑 Eliminar selec.",
                                           "Eliminar filas seleccionadas del carrito")
        btn_del_sel.clicked.connect(self._eliminar_seleccionados)
        btn_draft_save = create_secondary_button(self, "💾 Borrador",
                                                 "Guardar carrito como borrador")
        btn_draft_load = create_secondary_button(self, "📂 Recuperar",
                                                 "Cargar último borrador guardado")
        btn_draft_save.clicked.connect(self._guardar_borrador)
        btn_draft_load.clicked.connect(self._cargar_borrador)
        self._btn_draft_save = btn_draft_save
        self._btn_draft_load = btn_draft_load
        self._btn_del_sel    = btn_del_sel
        self._lbl_cart_count = QLabel("0 ítems")
        self._lbl_cart_count.setObjectName("caption")
        cart_tb.addWidget(btn_clear)
        cart_tb.addWidget(btn_del_sel)
        cart_tb.addSpacing(8)
        cart_tb.addWidget(btn_draft_save)
        cart_tb.addWidget(btn_draft_load)
        cart_tb.addSpacing(8)
        cart_tb.addWidget(self._lbl_cart_count)
        cart_tb.addStretch()
        cart_lay.addLayout(cart_tb)
        lay.addWidget(self._grp_cart)

        # ── Footer: IVA toggle + subtotals (payment moved to right panel) ─────
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self._chk_iva = QCheckBox("IVA 16%")
        self._chk_iva.setToolTip(
            "Incluir IVA del 16% al total de la compra (Ley del IVA México)")
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
        footer.addSpacing(16)
        footer.addWidget(self._lbl_subtotal_iva)
        footer.addSpacing(8)
        footer.addWidget(self._sep_iva)
        footer.addSpacing(8)
        footer.addWidget(self._lbl_iva_monto)
        footer.addStretch()
        footer.addWidget(self.lbl_total)
        lay.addLayout(footer)

        QShortcut(QKeySequence(Qt.Key_F10), parent, self._procesar_compra)

    def _build_tab_qr(self, parent: QWidget) -> None:
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

    # ── Left provider sidebar ─────────────────────────────────────────────────
    def _build_provider_sidebar(self) -> QWidget:
        """Left ERP sidebar: quick-access provider list + purchase templates."""
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(
            f"background:{Colors.NEUTRAL.SLATE_50};"
            "border-right:1px solid rgba(0,0,0,0.08);"
        )
        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        def _sec_lbl(txt: str) -> QLabel:
            lbl = QLabel(txt)
            lbl.setStyleSheet(
                f"font-size:10px;font-weight:700;letter-spacing:0.8px;"
                f"color:{Colors.NEUTRAL.SLATE_500};"
                "background:transparent;border:none;padding:2px 0;"
            )
            return lbl

        lay.addWidget(_sec_lbl("🏢 PROVEEDORES"))

        self._sidebar_prov_search = QLineEdit()
        self._sidebar_prov_search.setPlaceholderText("Buscar proveedor…")
        self._sidebar_prov_search.setObjectName("styledInput")
        self._sidebar_prov_search.textChanged.connect(self._filtrar_sidebar_proveedores)
        lay.addWidget(self._sidebar_prov_search)

        _list_style = (
            "QListWidget{"
            "  border:1px solid rgba(0,0,0,0.1);border-radius:4px;"
            "  background:white;font-size:11px;outline:none;"
            "}"
            "QListWidget::item{padding:5px 8px;border-bottom:1px solid rgba(0,0,0,0.04);}"
            f"QListWidget::item:selected{{background:{Colors.PRIMARY_BASE}22;"
            f"  color:{Colors.PRIMARY_BASE};"
            f"  border-left:3px solid {Colors.PRIMARY_BASE};}}"
            "QListWidget::item:hover{background:#F8FAFC;}"
        )
        self._sidebar_prov_list = QListWidget()
        self._sidebar_prov_list.setStyleSheet(_list_style)
        self._sidebar_prov_list.itemClicked.connect(self._seleccionar_proveedor_sidebar)
        lay.addWidget(self._sidebar_prov_list, 1)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("border:none;border-top:1px solid rgba(0,0,0,0.08);")
        lay.addWidget(sep)

        lay.addWidget(_sec_lbl("📋 PLANTILLAS"))
        self._sidebar_templates_list = QListWidget()
        self._sidebar_templates_list.setMaximumHeight(100)
        self._sidebar_templates_list.setStyleSheet(_list_style)
        self._sidebar_templates_list.itemDoubleClicked.connect(self._cargar_plantilla_sidebar)
        self._poblar_plantillas_sidebar()
        lay.addWidget(self._sidebar_templates_list)

        return sidebar

    def _build_summary_panel(self) -> QWidget:
        """Right ERP panel: live financial summary + validation + payment + actions."""
        panel = QFrame()
        panel.setFixedWidth(230)
        panel.setStyleSheet(
            f"background:{Colors.NEUTRAL.SLATE_50};"
            "border-left:1px solid rgba(0,0,0,0.08);"
        )
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)

        # ── A. Status badge + last edit ───────────────────────────────────────
        self._lbl_estado_compra = QLabel("🔵  En captura")
        self._lbl_estado_compra.setStyleSheet(
            f"background:{Colors.INFO_BASE};color:white;border-radius:10px;"
            "padding:3px 8px;font-size:11px;font-weight:700;"
        )
        lay.addWidget(self._lbl_estado_compra)

        self._lbl_ultima_edicion = QLabel("—")
        self._lbl_ultima_edicion.setObjectName("caption")
        self._lbl_ultima_edicion.setWordWrap(True)
        lay.addWidget(self._lbl_ultima_edicion)

        # ── B. Financial summary group ────────────────────────────────────────
        sum_grp = QGroupBox("📊 Resumen")
        sum_grp.setObjectName("styledGroup")
        sum_lay = QVBoxLayout(sum_grp)
        sum_lay.setSpacing(4)
        sum_lay.setContentsMargins(8, 8, 8, 8)

        self._sum_items_lbl = QLabel("0 productos")
        self._sum_items_lbl.setObjectName("caption")
        sum_lay.addWidget(self._sum_items_lbl)

        self._sum_peso_lbl = QLabel("Peso est.: — kg")
        self._sum_peso_lbl.setObjectName("caption")
        sum_lay.addWidget(self._sum_peso_lbl)

        _hsep = lambda: (lambda f: (f.setFrameShape(QFrame.HLine),
                                     f.setStyleSheet("border:none;border-top:1px solid rgba(0,0,0,0.08);margin:2px 0;"),
                                     f)[2])(QFrame())
        sum_lay.addWidget(_hsep())

        self._sum_subtotal_lbl = QLabel("Subtotal:  $0.00")
        self._sum_subtotal_lbl.setObjectName("caption")
        sum_lay.addWidget(self._sum_subtotal_lbl)

        self._sum_iva_lbl = QLabel("IVA (16%):  $0.00")
        self._sum_iva_lbl.setObjectName("caption")
        self._sum_iva_lbl.setStyleSheet(f"color:{Colors.INFO_BASE};")
        self._sum_iva_lbl.hide()
        sum_lay.addWidget(self._sum_iva_lbl)

        self._sum_descuento_lbl = QLabel("Descuento:  $0.00")
        self._sum_descuento_lbl.setObjectName("caption")
        sum_lay.addWidget(self._sum_descuento_lbl)

        self._sum_flete_lbl = QLabel("Flete:  $0.00")
        self._sum_flete_lbl.setObjectName("caption")
        sum_lay.addWidget(self._sum_flete_lbl)

        self._sum_otros_lbl = QLabel("Otros cargos:  $0.00")
        self._sum_otros_lbl.setObjectName("caption")
        sum_lay.addWidget(self._sum_otros_lbl)

        sum_lay.addWidget(_hsep())

        self._sum_total_lbl = QLabel("TOTAL:  $0.00")
        self._sum_total_lbl.setObjectName("statsKpiValue")
        self._sum_total_lbl.setProperty("variant", "success")
        sum_lay.addWidget(self._sum_total_lbl)

        self._sum_costo_kg_lbl = QLabel("Costo/kg: —")
        self._sum_costo_kg_lbl.setObjectName("caption")
        sum_lay.addWidget(self._sum_costo_kg_lbl)

        lay.addWidget(sum_grp)

        # ── C. Flete and Otros cargos spinboxes ──────────────────────────────
        cargo_grp = QGroupBox("📦 Cargos adicionales")
        cargo_grp.setObjectName("styledGroup")
        cargo_form = QFormLayout(cargo_grp)
        cargo_form.setSpacing(4)
        cargo_form.setContentsMargins(8, 6, 8, 6)

        self._spin_flete = QDoubleSpinBox()
        self._spin_flete.setRange(0, 999999)
        self._spin_flete.setDecimals(2)
        self._spin_flete.setPrefix("$ ")
        self._spin_flete.valueChanged.connect(self._refresh_totals_display)
        cargo_form.addRow("Flete:", self._spin_flete)

        self._spin_otros = QDoubleSpinBox()
        self._spin_otros.setRange(0, 999999)
        self._spin_otros.setDecimals(2)
        self._spin_otros.setPrefix("$ ")
        self._spin_otros.valueChanged.connect(self._refresh_totals_display)
        cargo_form.addRow("Otros:", self._spin_otros)

        lay.addWidget(cargo_grp)

        # ── D. Validation indicators ──────────────────────────────────────────
        val_grp = QGroupBox("✓ Estado")
        val_grp.setObjectName("styledGroup")
        val_lay = QVBoxLayout(val_grp)
        val_lay.setSpacing(3)
        val_lay.setContentsMargins(6, 6, 6, 6)

        self._val_prov_lbl    = QLabel("⚠ Proveedor")
        self._val_prod_lbl    = QLabel("⚠ Productos")
        self._val_total_v_lbl = QLabel("⚠ Total cero")
        for lbl in (self._val_prov_lbl, self._val_prod_lbl, self._val_total_v_lbl):
            lbl.setObjectName("caption")
            val_lay.addWidget(lbl)
        lay.addWidget(val_grp)

        # ── E. Stretch ────────────────────────────────────────────────────────
        lay.addStretch()

        # ── F. Payment section ────────────────────────────────────────────────
        pay_grp = QGroupBox("💳 Pago")
        pay_grp.setObjectName("styledGroup")
        pay_form = QFormLayout(pay_grp)
        pay_form.setSpacing(4)
        pay_form.setContentsMargins(8, 6, 8, 6)

        self.cmb_pago = create_combo(self)
        for label, data in _PAGO_ITEMS:
            self.cmb_pago.addItem(label, data)
        pay_form.addRow("Método:", self.cmb_pago)

        self._cmb_condicion_pago = QComboBox()
        self._cmb_condicion_pago.addItems(["Liquidado", "Crédito", "Parcial"])
        pay_form.addRow("Condición:", self._cmb_condicion_pago)

        self._spin_plazo_dias = QSpinBox()
        self._spin_plazo_dias.setRange(0, 365)
        self._spin_plazo_dias.setSuffix(" días")
        self._spin_plazo_dias.setValue(30)
        pay_form.addRow("Plazo:", self._spin_plazo_dias)

        self._lbl_vence_el = QLabel("Vence: —")
        self._lbl_vence_el.setObjectName("caption")
        pay_form.addRow("", self._lbl_vence_el)

        self._cmb_condicion_pago.currentTextChanged.connect(self._on_condicion_changed)
        self._spin_plazo_dias.valueChanged.connect(self._on_plazo_changed)

        lay.addWidget(pay_grp)

        # ── G. Action buttons ─────────────────────────────────────────────────
        self._btn_draft_save_r = create_secondary_button(self, "💾 Borrador", "Guardar como borrador")
        self._btn_draft_save_r.clicked.connect(self._guardar_borrador)
        lay.addWidget(self._btn_draft_save_r)

        self._btn_autorizar = create_primary_button(self, "✓ Autorizar compra", "Autorizar y procesar compra")
        self._btn_autorizar.clicked.connect(self._procesar_compra)
        self._btn_autorizar.setMinimumHeight(36)
        self._btn_autorizar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # Backward-compat alias
        self._btn_procesar = self._btn_autorizar
        lay.addWidget(self._btn_autorizar)

        self._btn_enviar_recepcion = create_success_button(
            self, "📨 Enviar a recepción", "Registrar y enviar a almacén")
        self._btn_enviar_recepcion.clicked.connect(self._enviar_a_recepcion)
        self._btn_enviar_recepcion.setMinimumHeight(36)
        self._btn_enviar_recepcion.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay.addWidget(self._btn_enviar_recepcion)

        return panel

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
        """Click on sidebar provider: populate form fields."""
        prov_id   = item.data(Qt.UserRole)
        prov_name = item.text()
        self._proveedor_id_selected = prov_id
        if hasattr(self, 'txt_proveedor'):
            self.txt_proveedor.setText(prov_name)
        if hasattr(self, '_lbl_prov_status'):
            self._lbl_prov_status.setText(f"✔ {prov_name}")
            self._lbl_prov_status.setStyleSheet(f"color:{Colors.SUCCESS_BASE};")
        self._cargar_info_proveedor(prov_id)
        self._actualizar_panel_validacion()

    def _cargar_info_proveedor(self, prov_id: int) -> None:
        """Show RFC / address / phone under provider field after selection."""
        if not hasattr(self, '_lbl_prov_info'):
            return
        try:
            row = self.container.db.execute(
                "SELECT rfc, direccion, telefono, condicion_pago"
                " FROM proveedores WHERE id=?",
                (prov_id,)
            ).fetchone()
            if not row:
                self._lbl_prov_info.hide()
                return
            def _get(idx, key):
                return str(row[idx] if not hasattr(row, 'keys') else (row.get(key) or "")).strip()
            parts = []
            rfc  = _get(0, 'rfc');       dirs = _get(1, 'direccion')
            tel  = _get(2, 'telefono');  cond = _get(3, 'condicion_pago')
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
        except (TypeError, KeyError, IndexError):
            self._lbl_prov_info.hide()

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
        except (TypeError, KeyError, OSError) as e:
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

    def _resolver_proveedor_desde_texto(self) -> None:
        txt = (self.txt_proveedor.text() or "").strip().lower()
        self._proveedor_id_selected = None
        for p in self._proveedores_cache:
            if p["nombre"].strip().lower() == txt:
                self._proveedor_id_selected = p["id"]
                self.txt_proveedor.setText(p["nombre"])
                if hasattr(self, "_lbl_prov_status"):
                    self._lbl_prov_status.setText(f"✔ {p['nombre']}")
                    self._lbl_prov_status.setStyleSheet(
                        f"color:{Colors.SUCCESS_BASE};")
                self._cargar_info_proveedor(p["id"])
                self._actualizar_panel_validacion()
                return
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
        doc_ref  = self.txt_factura.text().strip() or "Sin Ref"
        pago     = self.cmb_pago.currentData() or "CONTADO"
        subtotal = sum(i['subtotal'] for i in self.carrito_compra)
        iva_activo = hasattr(self, '_chk_iva') and self._chk_iva.isChecked()
        iva_monto  = round(subtotal * self._get_iva_rate(), 2) if iva_activo else 0.0
        total      = subtotal + iva_monto

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

            # Clear UI and draft
            self.carrito_compra.clear()
            self._refresh_tabla()
            self.txt_factura.clear()
            self._clear_draft()
            # Refresh KPI bar non-blocking
            QTimer.singleShot(300, self._refresh_stats)

        except Exception as e:
            QMessageBox.critical(self, "Error al procesar", str(e))
            logger.error("_procesar_compra: %s", e)

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
            combo_filters={"estado": [
                "completada", "credito", "pendiente", "parcial", "cancelada",
            ]},
        )
        self._hist_filter.filters_changed.connect(self._hist_filter_changed)
        lay.addWidget(self._hist_filter)
        self._hist_loading = LoadingIndicator("Cargando historial…", self)
        self._hist_loading.hide()
        lay.addWidget(self._hist_loading)

        # Main table — cols: Folio | Fecha | Proveedor | Usuario | Total | Cond.Pago | Estado | ⋯
        self._tbl_hist = QTableWidget()
        self._tbl_hist.setColumnCount(8)
        self._tbl_hist.setHorizontalHeaderLabels(
            ["Folio", "Fecha", "Proveedor", "Usuario", "Total", "Cond. Pago", "Estado", ""])
        hh = self._tbl_hist.horizontalHeader()
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(5, QHeaderView.Fixed)
        hh.setSectionResizeMode(6, QHeaderView.Fixed)
        self._tbl_hist.setColumnWidth(5, 90)
        self._tbl_hist.setColumnWidth(6, 110)
        for c in (0, 1, 3, 4, 7):
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
            filtros = self._hist_filter.values() if hasattr(self, "_hist_filter") else {}
            estado  = (filtros.get("estado") or "").strip().lower()
            search  = (filtros.get("search") or "").strip().lower()
            rows = list(all_rows)
            if estado:
                rows = [r for r in rows if str(r[5] or "").strip().lower() == estado]
            if search:
                rows = [r for r in rows if
                        search in str(r[0] or "").lower() or
                        search in str(r[2] or "").lower() or
                        search in str(r[3] or "").lower()]

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
            cid_ = r[6]; pnm_ = str(r[2] or "")
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci == 4:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if ci == 0:
                    it.setData(Qt.UserRole, cid_)  # store compra_id for inline detail
                self._tbl_hist.setItem(ri, ci, it)
            # col 5 — Cond. Pago chip (design system badge)
            self._tbl_hist.setCellWidget(ri, 5, _make_cond_chip(cond_raw, self))
            # col 6 — Estado chip (design system badge)
            self._tbl_hist.setCellWidget(ri, 6, _make_status_chip(estado_raw, self))
            total_periodo += monto
            btn_det = create_secondary_button(self, "🔍 Ver",
                                              "Ver detalles de esta compra")
            btn_det.clicked.connect(
                lambda _, cid=cid_, pnm=pnm_:
                    self._ver_detalle_compra(cid, pnm))
            self._tbl_hist.setCellWidget(ri, 7, btn_det)

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
            f"QFrame{{background:{Colors.NEUTRAL.SLATE_50};"
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
            self._hist_detail_panel.setTitle(
                f"Detalle compra #{compra_id}  ({len(items)} producto(s))"
            )
            self._hist_detail_panel.setVisible(True)
        except Exception as exc:
            logger.debug("_on_hist_row_selected: %s", exc)
            self._hist_detail_panel.setVisible(False)

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
            bg_row = Colors.NEUTRAL.SLATE_50 if idx % 2 == 0 else Colors.NEUTRAL.WHITE
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

    def _exportar_historial_csv(self) -> None:
        """Exporta las filas visibles del historial de compras a CSV."""
        import csv, os
        if not hasattr(self, '_tbl_hist') or self._tbl_hist.rowCount() == 0:
            QMessageBox.information(self, "Exportar", "No hay datos para exportar.")
            return
        default_name = f"compras_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar historial de compras", default_name, "CSV (*.csv)")
        if not path:
            return
        try:
            headers = ["Folio", "Fecha", "Proveedor", "Usuario", "Total", "Cond. Pago", "Estado"]
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for row in range(self._tbl_hist.rowCount()):
                    row_data = []
                    for col in range(7):  # cols 0-6; skip col 7 (action buttons)
                        item = self._tbl_hist.item(row, col)
                        if item is not None:
                            row_data.append(item.text())
                        else:
                            widget = self._tbl_hist.cellWidget(row, col)
                            row_data.append(widget.text().strip() if widget else "")
                    writer.writerow(row_data)
            Toast.success(self, "✅ Exportado", os.path.basename(path))
        except Exception as e:
            QMessageBox.critical(self, "Error al exportar", str(e))

    def _fallback_compra_directa(self, proveedor_id, doc_ref, pago, total,
                                  items) -> str:
        """Registro directo en BD cuando PurchaseService no está disponible."""
        from core.db.connection import transaction
        folio = f"C{datetime.now().strftime('%Y%m%d%H%M%S')}"
        db = self.container.db
        _condicion = (self._cmb_condicion_pago.currentText().lower()
                      if hasattr(self, '_cmb_condicion_pago') else "liquidado")
        _plazo     = (self._spin_plazo_dias.value()
                      if hasattr(self, '_spin_plazo_dias') else 0)
        _moneda    = (self._cmb_moneda.currentText()
                      if hasattr(self, '_cmb_moneda') else "MXN")
        with transaction(db):
            db.execute(
                """INSERT INTO compras (proveedor_id, sucursal_id, usuario,
                   total, estado, observaciones, forma_pago, factura, fecha,
                   condicion_pago, plazo_dias, moneda)
                   VALUES (?,?,?,?,?,?,?,?,datetime('now'),?,?,?)""",
                (proveedor_id, self.sucursal_id, self.usuario_actual,
                 total, "completada", doc_ref, pago, doc_ref,
                 _condicion, _plazo, _moneda))
            compra_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            for it in items:
                db.execute(
                    """INSERT INTO detalles_compra
                       (compra_id, producto_id, cantidad, costo_unitario, subtotal)
                       VALUES (?,?,?,?,?)""",
                    (compra_id, it['product_id'], it['qty'],
                     it['unit_cost'], it['qty'] * it['unit_cost']))
                _app = getattr(self.container, 'app_service', None)
                if _app:
                    _app.registrar_compra(
                        producto_id=it['product_id'], cantidad=it['qty'],
                        costo_unitario=it['unit_cost'],
                        usuario=self.usuario_actual,
                        sucursal_id=self.sucursal_id)
                else:
                    db.execute(
                        "UPDATE productos SET existencia=existencia+?, precio_compra=? WHERE id=?",
                        (it['qty'], it['unit_cost'], it['product_id']))
        return folio
