# modulos/inventario_local.py — SPJ POS v13.5
# Enterprise Inventory Control Workspace
"""
Inventory is the RESULT of movements — not a freely editable value.

Architecture:
  - audit-safe workflows enforced at UI level
  - movement-driven operations (entry / adjustment / transfer)
  - severity-classified stock health system
  - operational insights panel with live movement feed
  - role-based action visibility
  - zero inline cell editing
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QDialog, QDialogButtonBox, QComboBox,
    QTextEdit, QLineEdit, QScrollArea, QSizePolicy, QFileDialog, QSplitter, QTabWidget,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor

from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import (
    LoadingIndicator, EmptyStateWidget, PageHeader, Toast, apply_tooltip,
)
from modulos.spj_refresh_mixin import RefreshMixin
from modulos.kpi_card import KPICard
from backend.infrastructure.db.repositories.inventory_repository import InventoryRepository
from backend.application.queries.inventory_query_service import InventoryQueryService
from backend.application.services.inventory_application_service import InventoryApplicationService
from core.events.event_bus import (
    VENTA_COMPLETADA, PRODUCTO_ACTUALIZADO, PRODUCTO_CREADO,
    AJUSTE_INVENTARIO, COMPRA_REGISTRADA,
    PRODUCCION_COMPLETADA, PRODUCCION_REGISTRADA, INVENTARIO_ACTUALIZADO,
    get_bus,
)

logger = logging.getLogger("spj.inventario")


def _to_business_inventory_error(exc: Exception) -> str:
    msg = str(exc or "")
    up = msg.upper()
    if "INSUFICIENTE" in up or "STOCK" in up:
        return "No hay stock suficiente para completar la operación."
    if "PERMISO" in up or "DENIED" in up:
        return "No tiene permisos para ejecutar esta acción en inventario."
    return "No se pudo completar la operación de inventario. Verifique los datos e intente de nuevo."

# ── Semantic stock health ─────────────────────────────────────────────────────

_HEALTH_CRITICAL = "SIN STOCK"
_HEALTH_LOW      = "BAJO MÍN."
_HEALTH_OK       = "SALUDABLE"
_HEALTH_NA       = "—"

_HEALTH_COLOR = {
    _HEALTH_CRITICAL: Colors.DANGER.BASE,
    _HEALTH_LOW:      Colors.WARNING.BASE,
    _HEALTH_OK:       Colors.SUCCESS.BASE,
    _HEALTH_NA:       Colors.NEUTRAL.SLATE_500,
}

_HEALTH_BG = {
    _HEALTH_CRITICAL: Colors.DANGER.BG_SOFT,
    _HEALTH_LOW:      Colors.WARNING.BG_SOFT,
    _HEALTH_OK:       Colors.SUCCESS.BG_SOFT,
    _HEALTH_NA:       Colors.NEUTRAL.SLATE_100,
}

_ADJUSTMENT_REASONS = [
    "Conteo físico — diferencia real",
    "Merma / deterioro de producto",
    "Error de captura en recepción",
    "Corrección por venta no registrada",
    "Devolución no procesada",
    "Revisión periódica de inventario",
    "Robo / extravío confirmado",
    "Ajuste por producción interna",
    "Otro (especificar en observación)",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _card_frame(parent=None, object_name: str = "kpiCard") -> QFrame:
    f = QFrame(parent)
    f.setObjectName(object_name)
    return f


def _section_lbl(text: str, parent=None) -> QLabel:
    lbl = QLabel(text.upper(), parent)
    lbl.setObjectName("sectionLabel")
    lbl.setStyleSheet(
        f"color: {Colors.NEUTRAL.SLATE_500};"
        f" font-size: {Typography.SIZE_XS};"
        f" font-weight: {Typography.WEIGHT_SEMIBOLD};"
        f" letter-spacing: 0.1em;"
        f" background: transparent; border: none;"
    )
    return lbl


def _divider(parent=None) -> QFrame:
    ln = QFrame(parent)
    ln.setFrameShape(QFrame.HLine)
    ln.setFixedHeight(1)
    ln.setStyleSheet("background: rgba(148,163,184,0.15); border: none;")
    return ln


def _health_badge(status: str, parent=None) -> QLabel:
    color = _HEALTH_COLOR.get(status, Colors.NEUTRAL.SLATE_500)
    bg    = _HEALTH_BG.get(status, Colors.NEUTRAL.SLATE_100)
    lbl = QLabel(status, parent)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet(
        f"color: {color}; background: {bg};"
        f" font-size: {Typography.SIZE_XS}; font-weight: {Typography.WEIGHT_BOLD};"
        f" border-radius: {Borders.RADIUS_FULL}px; padding: 2px 8px; border: none;"
    )
    return lbl


def _classify_stock(stock: float, minimo: float) -> str:
    if stock <= 0:
        return _HEALTH_CRITICAL
    if stock <= max(minimo, 1):
        return _HEALTH_LOW
    return _HEALTH_OK


# ── KPI hero card ─────────────────────────────────────────────────────────────
# Alias for backward compatibility
_InvKPICard = KPICard


# ── Audit movement row ────────────────────────────────────────────────────────

class _MovRow(QFrame):
    """Single movement entry in the audit feed."""

    _TYPE_META = {
        "ENTRADA":         ("↑", Colors.SUCCESS.BASE),
        "AJUSTE":          ("⚖", Colors.INFO.BASE),
        "AJUSTE_POSITIVO": ("↑", Colors.SUCCESS.BASE),
        "AJUSTE_NEGATIVO": ("↓", Colors.DANGER.BASE),
        "VENTA":           ("↓", Colors.WARNING.BASE),
        "COMPRA":          ("↑", Colors.SUCCESS.BASE),
        "TRASPASO":        ("→", Colors.PRIMARY.BASE),
        "MERMA":           ("✕", Colors.DANGER.BASE),
    }

    def __init__(self, mov: dict, parent=None):
        super().__init__(parent)
        mtype = str(mov.get("movement_type", mov.get("tipo", ""))).upper()
        arrow, color = self._TYPE_META.get(mtype, ("●", Colors.NEUTRAL.SLATE_500))
        qty   = float(mov.get("quantity", mov.get("cantidad", 0)))
        user  = str(mov.get("usuario", "—"))
        ts    = str(mov.get("created_at", mov.get("fecha", "")))[:16]
        prod  = str(mov.get("nombre", mov.get("producto", "")))

        self.setObjectName("actFeedItem")
        self.setStyleSheet(
            "QFrame#actFeedItem { background: transparent; border: none;"
            " border-bottom: 1px solid rgba(148,163,184,0.1); }"
            "QFrame#actFeedItem QLabel { background: transparent; border: none; }"
        )

        lyt = QHBoxLayout(self)
        lyt.setContentsMargins(0, 6, 0, 6)
        lyt.setSpacing(8)

        dot = QLabel(arrow)
        dot.setFixedWidth(18)
        dot.setAlignment(Qt.AlignCenter)
        dot.setStyleSheet(f"color: {color}; font-weight: 700; font-size: 12px;")
        lyt.addWidget(dot, 0, alignment=Qt.AlignVCenter)

        info = QVBoxLayout()
        info.setSpacing(0)

        lbl_prod = QLabel(prod or mtype.capitalize())
        lbl_prod.setStyleSheet(
            f"font-size: {Typography.SIZE_SM}; font-weight: {Typography.WEIGHT_SEMIBOLD};"
        )
        info.addWidget(lbl_prod)

        lbl_sub = QLabel(f"{user}  ·  {ts}")
        lbl_sub.setStyleSheet(
            f"font-size: {Typography.SIZE_XS}; color: {Colors.NEUTRAL.SLATE_500};"
        )
        info.addWidget(lbl_sub)
        lyt.addLayout(info, 1)

        sign = "+" if qty >= 0 else ""
        lbl_qty = QLabel(f"{sign}{qty:.2f}")
        lbl_qty.setStyleSheet(
            f"font-size: {Typography.SIZE_SM}; font-weight: {Typography.WEIGHT_BOLD};"
            f" color: {Colors.SUCCESS.BASE if qty >= 0 else Colors.DANGER.BASE};"
        )
        lyt.addWidget(lbl_qty, 0, alignment=Qt.AlignVCenter)


# ── Insights panel ────────────────────────────────────────────────────────────

class _InsightsPanel(QFrame):
    """Right-side collapsible operational insights: alerts + movement feed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dashDelivCard")
        self.setMinimumWidth(240)
        self.setMaximumWidth(300)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        root.setSpacing(Spacing.MD)

        # ── Alerts ────────────────────────────────────────────────────────────
        root.addWidget(_section_lbl("Alertas de stock"))
        root.addWidget(_divider(self))

        self._alerts_lyt = QVBoxLayout()
        self._alerts_lyt.setSpacing(4)
        root.addLayout(self._alerts_lyt)

        self._lbl_no_alerts = QLabel("Sin alertas críticas", self)
        self._lbl_no_alerts.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_500}; font-size: {Typography.SIZE_SM}; padding: 4px 0;"
        )
        self._lbl_no_alerts.hide()
        root.addWidget(self._lbl_no_alerts)

        root.addSpacing(Spacing.SM)

        # ── Recent movements ──────────────────────────────────────────────────
        root.addWidget(_section_lbl("Movimientos recientes"))
        root.addWidget(_divider(self))

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumHeight(180)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 4px; background: transparent; }"
            "QScrollBar::handle:vertical { background: rgba(148,163,184,0.3);"
            " border-radius: 2px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        self._mov_container = QWidget()
        self._mov_lyt = QVBoxLayout(self._mov_container)
        self._mov_lyt.setSpacing(0)
        self._mov_lyt.setContentsMargins(0, 0, 0, 0)
        self._mov_lyt.addStretch()
        scroll.setWidget(self._mov_container)
        root.addWidget(scroll, 1)

        self._lbl_no_mov = QLabel("Sin movimientos recientes.", self)
        self._lbl_no_mov.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_500}; font-size: {Typography.SIZE_SM}; padding: 4px 0;"
        )
        self._lbl_no_mov.hide()
        root.addWidget(self._lbl_no_mov)

    def refresh(self, query_service: InventoryQueryService, sucursal_id: int) -> None:
        self._refresh_alerts(query_service, sucursal_id)
        self._refresh_movements(query_service, sucursal_id)

    def _refresh_alerts(self, query_service: InventoryQueryService, sucursal_id: int) -> None:
        while self._alerts_lyt.count():
            item = self._alerts_lyt.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        alertas = []
        try:
            for product in query_service.list_stock_rows(sucursal_id):
                stock = float(product[3] or 0)
                minimum = float(product[4] or 0)
                if stock <= minimum:
                    health = _HEALTH_CRITICAL if stock <= 0 else _HEALTH_LOW
                    alertas.append((str(product[1]), stock, str(product[5] or ""), health))
                if len(alertas) >= 8:
                    break
        except Exception:
            logger.exception("Error al cargar alertas de inventario")

        if not alertas:
            self._lbl_no_alerts.show()
            return

        self._lbl_no_alerts.hide()
        for nombre, stock, unidad, health in alertas:
            row = QFrame(self)
            row.setStyleSheet("QFrame { background: transparent; border: none; } QLabel { background: transparent; border: none; }")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 3, 0, 3)
            rl.setSpacing(6)

            badge = _health_badge(health, row)
            badge.setFixedWidth(72)
            rl.addWidget(badge, 0, alignment=Qt.AlignVCenter)

            lbl = QLabel(f"{nombre}  {stock:.1f} {unidad}", row)
            lbl.setStyleSheet(
                f"font-size: {Typography.SIZE_SM};"
                f" color: {'#ef4444' if health == _HEALTH_CRITICAL else Colors.WARNING.BASE};"
            )
            lbl.setWordWrap(True)
            rl.addWidget(lbl, 1)
            self._alerts_lyt.addWidget(row)

    def _refresh_movements(self, query_service: InventoryQueryService, sucursal_id: int) -> None:
        while self._mov_lyt.count() > 1:
            item = self._mov_lyt.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        movs = query_service.list_feed_movements(sucursal_id, limit=12)

        if not movs:
            self._lbl_no_mov.show()
            return

        self._lbl_no_mov.hide()
        for i, m in enumerate(movs):
            self._mov_lyt.insertWidget(i, _MovRow(m, self._mov_container))


# ── Audited adjustment dialog ─────────────────────────────────────────────────

class _AuditAdjustDialog(QDialog):
    """
    Enterprise-grade audited inventory adjustment.
    Requires: reason category + mandatory observation.
    Enforces movement-driven stock change — no silent mutations.
    """

    def __init__(self, prod_id: int, nombre: str, stock_actual: float,
                 unidad: str, parent=None):
        super().__init__(parent)
        self.prod_id = prod_id
        self.stock_actual = stock_actual

        self.setWindowTitle("Ajuste de Inventario — Operación Auditada")
        self.setMinimumWidth(440)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setSpacing(Spacing.MD)
        root.setContentsMargins(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)

        # Header
        lbl_title = QLabel("Ajuste de Inventario")
        lbl_title.setStyleSheet(
            f"font-size: 16px; font-weight: {Typography.WEIGHT_BOLD};"
            f" background: transparent; border: none;"
        )
        root.addWidget(lbl_title)

        lbl_prod = QLabel(f"Producto: {nombre}  ·  Stock sistema: {stock_actual:.3f} {unidad}")
        lbl_prod.setStyleSheet(
            f"font-size: {Typography.SIZE_SM}; color: {Colors.NEUTRAL.SLATE_500};"
            f" background: transparent; border: none;"
        )
        root.addWidget(lbl_prod)
        root.addWidget(_divider(self))

        # Reason
        root.addWidget(QLabel("Motivo del ajuste *"))
        self.cmb_motivo = QComboBox(self)
        self.cmb_motivo.addItems(_ADJUSTMENT_REASONS)
        self.cmb_motivo.setObjectName("inputField")
        root.addWidget(self.cmb_motivo)

        # Physical count
        lbl_cnt = QLabel("Conteo físico real *")
        root.addWidget(lbl_cnt)

        cnt_row = QHBoxLayout()
        self.spin_nuevo = QuantityInput(self)
        self.spin_nuevo.setValue(stock_actual)
        self.spin_nuevo.setObjectName("inputField")
        self.spin_nuevo.setSuffix(f"  {unidad}")
        self.spin_nuevo.valueChanged.connect(self._update_variance)
        cnt_row.addWidget(self.spin_nuevo)

        self.lbl_variance = QLabel("")
        self.lbl_variance.setStyleSheet(
            f"font-size: {Typography.SIZE_SM}; font-weight: {Typography.WEIGHT_BOLD};"
            f" background: transparent; border: none;"
        )
        cnt_row.addWidget(self.lbl_variance)
        root.addLayout(cnt_row)

        # Observation
        root.addWidget(QLabel("Observación (mínimo 10 caracteres) *"))
        self.txt_obs = QTextEdit(self)
        self.txt_obs.setFixedHeight(72)
        self.txt_obs.setPlaceholderText(
            "Describa la causa del ajuste. Esta observación quedará en el registro de auditoría."
        )
        self.txt_obs.setObjectName("inputField")
        root.addWidget(self.txt_obs)

        # Warning notice
        notice = QLabel(
            "⚠  Este ajuste quedará registrado en el libro de movimientos de inventario "
            "con su usuario, timestamp y razón. No es reversible."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(
            f"color: {Colors.WARNING.BASE}; font-size: {Typography.SIZE_XS};"
            f" background: transparent; border: none; padding: 4px 0;"
        )
        root.addWidget(notice)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self
        )
        btns.button(QDialogButtonBox.Ok).setText("Confirmar Ajuste")
        btns.button(QDialogButtonBox.Ok).setObjectName("primaryBtn")
        btns.button(QDialogButtonBox.Cancel).setObjectName("secondaryBtn")
        btns.accepted.connect(self._validate_and_accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self._update_variance(stock_actual)

    def _update_variance(self, nuevo: float) -> None:
        delta = nuevo - self.stock_actual
        sign  = "+" if delta >= 0 else ""
        color = Colors.SUCCESS.BASE if delta >= 0 else Colors.DANGER.BASE
        if abs(delta) < 0.001:
            self.lbl_variance.setText("Sin variación")
            self.lbl_variance.setStyleSheet(
                f"color: {Colors.NEUTRAL.SLATE_500}; background: transparent; border: none;"
            )
        else:
            self.lbl_variance.setText(f"Variación: {sign}{delta:.3f}")
            self.lbl_variance.setStyleSheet(
                f"color: {color}; font-weight: 700; background: transparent; border: none;"
            )

    def _validate_and_accept(self) -> None:
        obs = self.txt_obs.toPlainText().strip()
        nuevo = self.spin_nuevo.value()
        if len(obs) < 10:
            QMessageBox.warning(
                self, "Observación insuficiente",
                "Ingrese al menos 10 caracteres de observación para auditoría."
            )
            return
        if abs(nuevo - self.stock_actual) < 0.001:
            QMessageBox.information(self, "Sin cambio", "El conteo es igual al stock sistema.")
            return
        self.accept()

    @property
    def resultado(self) -> dict:
        motivo = self.cmb_motivo.currentText()
        obs    = self.txt_obs.toPlainText().strip()
        return {
            "cantidad_nueva": self.spin_nuevo.value(),
            "motivo":         f"{motivo} — {obs}",
        }


# ── Stock entry dialog ────────────────────────────────────────────────────────

class _StockEntryDialog(QDialog):
    """Audited stock entry (receiving merchandise)."""

    def __init__(self, prod_id: int, nombre: str, unidad: str, parent=None):
        super().__init__(parent)
        self.prod_id = prod_id

        self.setWindowTitle("Entrada de Mercancía")
        self.setMinimumWidth(380)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setSpacing(Spacing.MD)
        root.setContentsMargins(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)

        lbl_title = QLabel("Entrada de Mercancía")
        lbl_title.setStyleSheet(
            f"font-size: 16px; font-weight: {Typography.WEIGHT_BOLD};"
            f" background: transparent; border: none;"
        )
        root.addWidget(lbl_title)

        lbl_prod = QLabel(f"Producto: {nombre}")
        lbl_prod.setStyleSheet(
            f"font-size: {Typography.SIZE_SM}; color: {Colors.NEUTRAL.SLATE_500};"
            f" background: transparent; border: none;"
        )
        root.addWidget(lbl_prod)
        root.addWidget(_divider(self))

        root.addWidget(QLabel(f"Cantidad a ingresar ({unidad}) *"))
        self.spin_qty = QuantityInput(self)
        self.spin_qty.setMinimum(0.001)
        self.spin_qty.setObjectName("inputField")
        root.addWidget(self.spin_qty)

        root.addWidget(QLabel("Costo unitario (opcional)"))
        self.spin_costo = MoneyInput(self)
        self.spin_costo.setObjectName("inputField")
        root.addWidget(self.spin_costo)

        root.addWidget(QLabel("Referencia / nota"))
        self.txt_ref = QLineEdit(self)
        self.txt_ref.setPlaceholderText("Folio de compra, remisión, etc.")
        self.txt_ref.setObjectName("inputField")
        root.addWidget(self.txt_ref)

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self
        )
        btns.button(QDialogButtonBox.Ok).setText("Registrar Entrada")
        btns.button(QDialogButtonBox.Ok).setObjectName("successBtn")
        btns.button(QDialogButtonBox.Cancel).setObjectName("secondaryBtn")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    @property
    def resultado(self) -> dict:
        return {
            "cantidad":   self.spin_qty.value(),
            "costo_unit": self.spin_costo.value(),
            "referencia": self.txt_ref.text().strip(),
        }


# ── Movement history dialog ───────────────────────────────────────────────────

class _MovHistoryDialog(QDialog):
    """Read-only audit trail for a single product."""

    def __init__(self, prod_id: int, nombre: str, query_service: InventoryQueryService, sucursal_id: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Historial de Movimientos — {nombre}")
        self.setMinimumSize(600, 400)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)

        lbl = QLabel(f"Producto: {nombre}  ·  Auditoría de movimientos")
        lbl.setStyleSheet(
            f"font-size: {Typography.SIZE_MD}; font-weight: {Typography.WEIGHT_SEMIBOLD};"
            f" background: transparent; border: none;"
        )
        root.addWidget(lbl)
        root.addWidget(_divider(self))

        tabla = QTableWidget(self)
        tabla.setColumnCount(6)
        tabla.setHorizontalHeaderLabels(
            ["Fecha", "Tipo", "Cantidad", "Usuario", "Referencia", "Op. ID"]
        )
        tabla.setObjectName("tableView")
        tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        tabla.verticalHeader().setVisible(False)
        tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        tabla.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        tabla.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        tabla.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        tabla.setAlternatingRowColors(True)

        rows = query_service.list_product_history(prod_id, sucursal_id, limit=100)


        for i, r in enumerate(rows):
            tabla.insertRow(i)
            for j, v in enumerate(r):
                item = QTableWidgetItem(str(v or ""))
                if j == 2:
                    qty = float(v or 0)
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    color = QColor(Colors.SUCCESS.BASE) if qty >= 0 else QColor(Colors.DANGER.BASE)
                    item.setForeground(color)
                tabla.setItem(i, j, item)

        root.addWidget(tabla)

        close_btn = QPushButton("Cerrar")
        close_btn.setObjectName("secondaryBtn")
        close_btn.clicked.connect(self.accept)
        root.addWidget(close_btn, 0, Qt.AlignRight)


# ── Main module ───────────────────────────────────────────────────────────────

class ModuloInventarioLocal(QWidget, RefreshMixin):
    """
    Enterprise Inventory Control Workspace — SPJ POS v13.5.

    Stock changes are ONLY permitted through audited movement operations.
    No inline cell editing. No silent stock mutations.
    """

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self._inventory_dirty = False   # True when data may be stale (missed events while hidden)
        try:
            self._init_refresh(container, [
                VENTA_COMPLETADA, PRODUCTO_ACTUALIZADO, PRODUCTO_CREADO,
                AJUSTE_INVENTARIO, COMPRA_REGISTRADA,
                PRODUCCION_REGISTRADA, PRODUCCION_COMPLETADA,
                INVENTARIO_ACTUALIZADO,
            ])
        except Exception:
            logger.exception("No se pudo inicializar refresh de inventario")

        self.container      = container
        self.sucursal_id    = 1
        self.usuario_actual = ""
        self._inventory_repository = InventoryRepository(container.db)
        self._inventory_query = InventoryQueryService(repository=self._inventory_repository)
        self._inventory_app = InventoryApplicationService(repository=self._inventory_repository)

        self._prod_data: list[dict] = []  # cached for export

        self.init_ui()

    # ── Session ───────────────────────────────────────────────────────────────

    def set_sucursal(self, sucursal_id: int, nombre_sucursal: str = "") -> None:
        self.sucursal_id = sucursal_id
        if nombre_sucursal:
            self._page_header.set_subtitle(
                f"Control de inventario · {nombre_sucursal}"
            )
        self.cargar_datos()

    def set_usuario_actual(self, usuario: str, rol: str = "") -> None:
        self.usuario_actual = usuario

    def _on_refresh(self, event_type: str, data: dict) -> None:
        """
        Called by RefreshMixin in the Qt main thread after debounce.

        Filters events by sucursal_id when possible so branch B does not
        trigger a reload in branch A.  If the module is hidden, marks it
        dirty so showEvent() will reload it when it becomes visible again.
        """
        # Sucursal filter: skip events from a different branch
        event_suc = data.get("sucursal_id")
        if event_suc is not None and int(event_suc) != int(self.sucursal_id):
            logger.debug(
                "Inventario: event %s from sucursal %s skipped (active=%s)",
                event_type, event_suc, self.sucursal_id,
            )
            return

        if not self.isVisible():
            # Module is behind another tab — mark dirty, reload on show
            self._inventory_dirty = True
            logger.debug(
                "Inventario: module hidden, marked dirty for event %s", event_type
            )
            return

        try:
            logger.debug(
                "Inventario: refreshing for event %s sucursal=%s",
                event_type, self.sucursal_id,
            )
            self._inventory_dirty = False
            self.cargar_datos()
        except Exception:
            logger.exception("No se pudo refrescar inventario por evento %s", event_type)

    def showEvent(self, event):
        """Reload data when module becomes visible if it missed events while hidden."""
        super().showEvent(event)
        if getattr(self, "_inventory_dirty", False):
            self._inventory_dirty = False
            logger.debug("Inventario: became visible with dirty flag — reloading")
            try:
                self.cargar_datos()
            except Exception:
                logger.exception("Inventario: showEvent reload failed")

    # ── UI construction ───────────────────────────────────────────────────────

    def init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        self._page_header = PageHeader(
            self,
            title="📦 Inventario",
            subtitle="Control de inventario por sucursal",
            with_separator=True,
        )
        root.addWidget(self._page_header)

        # ── Body ──────────────────────────────────────────────────────────────
        body = QWidget(self)
        body_lyt = QVBoxLayout(body)
        body_lyt.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.LG)
        body_lyt.setSpacing(Spacing.MD)
        root.addWidget(body, 1)

        # KPI Hero Row
        body_lyt.addWidget(self._build_kpi_row())

        # Action Bar
        body_lyt.addWidget(self._build_action_bar())

        # Loading indicator
        self._loading = LoadingIndicator("Cargando inventario…", body)
        self._loading.hide()
        body_lyt.addWidget(self._loading)

        # Workspace: tabs + insights
        workspace = QHBoxLayout()
        workspace.setSpacing(Spacing.MD)

        # Left: tabs
        table_col = QVBoxLayout()
        table_col.setSpacing(Spacing.SM)
        table_col.addWidget(self._build_inventory_tabs())
        self._empty_state = EmptyStateWidget(
            "Sin productos",
            "No se encontraron productos para los filtros aplicados.",
            "📭",
            body,
        )
        self._empty_state.hide()
        table_col.addWidget(self._empty_state)

        self.lbl_total = QLabel("", body)
        self.lbl_total.setObjectName("caption")
        table_col.addWidget(self.lbl_total)

        workspace.addLayout(table_col, 3)

        # Right: insights
        self._insights = _InsightsPanel(body)
        workspace.addWidget(self._insights, 0)

        body_lyt.addLayout(workspace, 1)

        self.cargar_datos()

    def _build_kpi_row(self) -> QWidget:
        container = QWidget(self)
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        container.setMinimumHeight(116)
        lyt = QHBoxLayout(container)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(Spacing.MD)

        self._kpi_click_mode = "none"
        self._kpi_bajo    = _InvKPICard("Stock bajo",             "—", "⚠️", "warning")
        self._kpi_sin     = _InvKPICard("Sin stock físico",       "—", "🚨", "danger")
        self._kpi_virtual = _InvKPICard("Stock virtual",          "Pendiente", "🧩", "info")
        self._kpi_res     = _InvKPICard("Reservados",             "—", "🔒", "primary")
        self._kpi_mov     = _InvKPICard("Movimientos hoy",        "—", "📋", "success")
        for key, card in (
            ("stock_bajo", self._kpi_bajo),
            ("sin_stock_fisico", self._kpi_sin),
            ("virtual_disponible", self._kpi_virtual),
            ("reservados", self._kpi_res),
            ("mov_hoy", self._kpi_mov),
        ):
            btn = QPushButton()
            btn.setFlat(True)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setMinimumHeight(108)
            btn.clicked.connect(lambda _, k=key: self._on_kpi_click(k))
            bl = QHBoxLayout(btn); bl.setContentsMargins(0, 0, 0, 0); bl.addWidget(card)
            lyt.addWidget(btn)

        return container

    def _build_inventory_tabs(self) -> QTabWidget:
        self._tabs_inv = QTabWidget(self)
        self._tab_exist = QWidget()
        self._tab_disp = QWidget()
        self._tab_virtual = QWidget()
        self._tab_mov = QWidget()
        self._tab_res = QWidget()
        self._tab_aj = QWidget()
        self._tab_aud = QWidget()

        self._tabs_inv.addTab(self._tab_exist, "Existencias")
        self._tabs_inv.addTab(self._tab_disp, "Disponibilidad")
        self._tabs_inv.addTab(self._tab_virtual, "Stock virtual (pendiente)")
        self._tabs_inv.addTab(self._tab_mov, "Movimientos")
        self._tabs_inv.addTab(self._tab_res, "Reservas")
        self._tabs_inv.addTab(self._tab_aj, "Ajustes")
        self._tabs_inv.addTab(self._tab_aud, "Auditoría")

        le = QVBoxLayout(self._tab_exist)
        le.setContentsMargins(0, 0, 0, 0)
        le.addWidget(self._build_table())

        ld = QVBoxLayout(self._tab_disp)
        ld.setContentsMargins(0, 0, 0, 0)
        ld.addWidget(self._build_disponibilidad_table())

        lv = QVBoxLayout(self._tab_virtual)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(self._build_virtual_table())

        lm = QVBoxLayout(self._tab_mov)
        lm.setContentsMargins(0, 0, 0, 0)
        lm.addWidget(self._build_movimientos_table())

        lr = QVBoxLayout(self._tab_res)
        lbl_res = QLabel("Reservas: vista en preparación (sin mezclar físico y virtual).")
        lbl_res.setObjectName("caption")
        lr.addWidget(lbl_res)

        la = QVBoxLayout(self._tab_aj)
        lbl_aj = QLabel("Ajustes: use el botón ⚖ Ajuste para registrar movimientos auditados.")
        lbl_aj.setObjectName("caption")
        la.addWidget(lbl_aj)

        lau = QVBoxLayout(self._tab_aud)
        lbl_aud = QLabel("Auditoría: use 📋 Historial para revisar trazabilidad por producto.")
        lbl_aud.setObjectName("caption")
        lau.addWidget(lbl_aud)

        return self._tabs_inv

    def _build_disponibilidad_table(self) -> QTableWidget:
        self.tabla_disponibilidad = QTableWidget(self)
        self.tabla_disponibilidad.setColumnCount(7)
        self.tabla_disponibilidad.setHorizontalHeaderLabels([
            "Producto", "Stock físico", "Reservado", "Disponible físico",
            "Disponible virtual", "Disponible venta", "Modo"
        ])
        self.tabla_disponibilidad.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabla_disponibilidad.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_disponibilidad.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_disponibilidad.verticalHeader().setVisible(False)
        self.tabla_disponibilidad.setObjectName("tableView")
        return self.tabla_disponibilidad

    def _build_virtual_table(self) -> QTableWidget:
        self.tabla_virtual = QTableWidget(self)
        self.tabla_virtual.setColumnCount(8)
        self.tabla_virtual.setHorizontalHeaderLabels([
            "Producto vendible", "Stock físico", "Disponible virtual", "Receta usada",
            "Componentes requeridos", "Máx vendible", "Componente limitante", "Sucursal"
        ])
        self.tabla_virtual.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabla_virtual.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_virtual.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_virtual.verticalHeader().setVisible(False)
        self.tabla_virtual.setObjectName("tableView")
        return self.tabla_virtual

    def _build_movimientos_table(self) -> QTableWidget:
        self.tabla_movimientos = QTableWidget(self)
        self.tabla_movimientos.setColumnCount(8)
        self.tabla_movimientos.setHorizontalHeaderLabels([
            "Fecha", "Producto", "Tipo movimiento", "Cantidad", "Sucursal", "Referencia", "Usuario", "Origen"
        ])
        hh = self.tabla_movimientos.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.tabla_movimientos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_movimientos.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_movimientos.verticalHeader().setVisible(False)
        self.tabla_movimientos.setObjectName("tableView")
        return self.tabla_movimientos

    def _build_action_bar(self) -> QWidget:
        bar = QFrame(self)
        bar.setObjectName("dashChartCard")
        lyt = QHBoxLayout(bar)
        lyt.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        lyt.setSpacing(Spacing.SM)

        # Search
        self._search = QLineEdit(bar)
        self._search.setPlaceholderText("Buscar producto, SKU o categoría…")
        self._search.setObjectName("inputField")
        self._search.setMinimumWidth(220)
        self._search.textChanged.connect(self._on_search)
        lyt.addWidget(self._search, 2)

        # Category filter
        self._cmb_cat = QComboBox(bar)
        self._cmb_cat.addItem("Todas las categorías")
        self._cmb_cat.setObjectName("inputField")
        self._cmb_cat.setMinimumWidth(150)
        self._cmb_cat.currentIndexChanged.connect(lambda _: self._apply_filters())
        lyt.addWidget(self._cmb_cat, 1)

        # Status filter
        self._cmb_estado = QComboBox(bar)
        self._cmb_estado.addItems([
            "Todos los estados",
            "Sin stock (crítico)",
            "Bajo mínimo",
            "Saludable",
        ])
        self._cmb_estado.setObjectName("inputField")
        self._cmb_estado.currentIndexChanged.connect(lambda _: self._apply_filters())
        lyt.addWidget(self._cmb_estado)

        lyt.addSpacing(Spacing.SM)

        # Refresh
        btn_ref = QPushButton("↻")
        btn_ref.setObjectName("secondaryBtn")
        btn_ref.setFixedWidth(34)
        btn_ref.setCursor(Qt.PointingHandCursor)
        apply_tooltip(btn_ref, "Refrescar inventario")
        btn_ref.clicked.connect(self.cargar_datos)
        lyt.addWidget(btn_ref)

        # Operational actions
        btn_entrada = QPushButton("↑  Entrada")
        btn_entrada.setObjectName("successBtn")
        btn_entrada.setCursor(Qt.PointingHandCursor)
        apply_tooltip(btn_entrada, "Registrar entrada de mercancía")
        btn_entrada.clicked.connect(self._accion_entrada)
        lyt.addWidget(btn_entrada)

        btn_ajuste = QPushButton("⚖  Ajuste")
        btn_ajuste.setObjectName("warningBtn")
        btn_ajuste.setCursor(Qt.PointingHandCursor)
        apply_tooltip(btn_ajuste, "Registrar ajuste de inventario auditado")
        btn_ajuste.clicked.connect(self._accion_ajuste)
        lyt.addWidget(btn_ajuste)

        btn_hist = QPushButton("📋  Historial")
        btn_hist.setObjectName("secondaryBtn")
        btn_hist.setCursor(Qt.PointingHandCursor)
        apply_tooltip(btn_hist, "Ver historial de movimientos del producto")
        btn_hist.clicked.connect(self._accion_historial)
        lyt.addWidget(btn_hist)

        lyt.addSpacing(Spacing.SM)

        btn_csv = QPushButton("↓ CSV")
        btn_csv.setObjectName("secondaryBtn")
        btn_csv.setCursor(Qt.PointingHandCursor)
        apply_tooltip(btn_csv, "Exportar inventario a CSV")
        btn_csv.clicked.connect(lambda: self._exportar("csv"))
        lyt.addWidget(btn_csv)

        btn_xlsx = QPushButton("↓ Excel")
        btn_xlsx.setObjectName("secondaryBtn")
        btn_xlsx.setCursor(Qt.PointingHandCursor)
        apply_tooltip(btn_xlsx, "Exportar inventario a Excel")
        btn_xlsx.clicked.connect(lambda: self._exportar("xlsx"))
        lyt.addWidget(btn_xlsx)

        return bar

    def _build_table(self) -> QTableWidget:
        self.tabla = QTableWidget(self)
        self.tabla.setColumnCount(7)
        self.tabla.setHorizontalHeaderLabels([
            "Producto", "Categoría", "Stock actual",
            "Stock mín.", "Estado", "Unidad", "Último movimiento",
        ])

        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(6, QHeaderView.ResizeToContents)

        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setObjectName("tableView")
        self.tabla.setShowGrid(False)

        return self.tabla

    # ── Data loading ──────────────────────────────────────────────────────────

    def cargar_datos(self) -> None:
        if hasattr(self, "_loading"):
            self._loading.show()
        try:
            self._do_cargar()
        finally:
            if hasattr(self, "_loading"):
                self._loading.hide()

    def _do_cargar(self) -> None:
        self._prod_data = []

        rows = self._inventory_query.list_stock_rows(self.sucursal_id)
        _last_mov = self._inventory_query.get_last_movement_map(self.sucursal_id)


        self.tabla.setRowCount(0)
        self.tabla_disponibilidad.setRowCount(0)
        self.tabla_virtual.setRowCount(0)

        for i, r in enumerate(rows):
            prod_id  = int(r[0])
            nombre   = str(r[1] or "")
            cat      = str(r[2] or "")
            stock    = float(r[3] or 0)
            minimo   = float(r[4] or 0)
            unidad   = str(r[5] or "")
            health   = _classify_stock(stock, minimo)
            last_mov = _last_mov.get(prod_id, "—")

            self._prod_data.append({
                "id": prod_id, "nombre": nombre, "categoria": cat,
                "stock": stock, "stock_minimo": minimo,
                "unidad": unidad, "health": health, "last_mov": last_mov,
            })

            self.tabla.insertRow(i)

            # Col 0: Nombre (stores prod_id in UserRole)
            it0 = QTableWidgetItem(nombre)
            it0.setData(Qt.UserRole, prod_id)
            self.tabla.setItem(i, 0, it0)

            # Col 1: Categoría
            self.tabla.setItem(i, 1, QTableWidgetItem(cat))

            # Col 2: Stock
            it_stock = QTableWidgetItem(f"{stock:.3f}")
            it_stock.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if health == _HEALTH_CRITICAL:
                it_stock.setForeground(QColor(Colors.DANGER.BASE))
            elif health == _HEALTH_LOW:
                it_stock.setForeground(QColor(Colors.WARNING.BASE))
            self.tabla.setItem(i, 2, it_stock)

            # Col 3: Mínimo
            it_min = QTableWidgetItem(f"{minimo:.1f}")
            it_min.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabla.setItem(i, 3, it_min)

            # Col 4: Estado (text — badge styling via row color)
            it_estado = QTableWidgetItem(health)
            it_estado.setTextAlignment(Qt.AlignCenter)
            estado_color = _HEALTH_COLOR.get(health, Colors.NEUTRAL.SLATE_500)
            it_estado.setForeground(QColor(estado_color))
            self.tabla.setItem(i, 4, it_estado)

            # Col 5: Unidad
            self.tabla.setItem(i, 5, QTableWidgetItem(unidad))

            # Col 6: Último movimiento
            self.tabla.setItem(i, 6, QTableWidgetItem(last_mov))

        availability_by_id = {
            int(row["product_id"]): row
            for row in self._inventory_query.list_availability_rows(self.sucursal_id)
        }
        self.tabla_disponibilidad.setRowCount(0)
        for row_idx, product in enumerate(self._prod_data):
            availability = availability_by_id.get(product["id"], {})
            physical = float(availability.get("physical_stock", product["stock"]) or 0.0)
            reserved = float(availability.get("reserved", 0.0) or 0.0)
            available = float(availability.get("physical_available", max(0.0, physical - reserved)) or 0.0)
            sale_available = float(availability.get("sale_available", available) or 0.0)
            mode = str(availability.get("mode") or ("DIRECTO" if sale_available > 0 else "NO DISPONIBLE"))
            self.tabla_disponibilidad.insertRow(row_idx)
            for j, v in enumerate([
                product["nombre"], f"{physical:.3f}", f"{reserved:.3f}",
                f"{available:.3f}", "Pendiente", f"{sale_available:.3f}", mode,
            ]):
                self.tabla_disponibilidad.setItem(row_idx, j, QTableWidgetItem(v))

        self.tabla_virtual.setRowCount(1)
        self.tabla_virtual.setItem(0, 0, QTableWidgetItem("Stock virtual pendiente de implementación."))
        for c in range(1, 8):
            self.tabla_virtual.setItem(0, c, QTableWidgetItem("Pendiente"))
        self._cargar_movimientos_tab()

        count = len(rows)
        self.lbl_total.setText(
            f"{count} productos  ·  "
            f"{sum(1 for p in self._prod_data if p['health']==_HEALTH_CRITICAL)} sin stock  ·  "
            f"{sum(1 for p in self._prod_data if p['health']==_HEALTH_LOW)} bajo mínimo"
        )

        if hasattr(self, "_empty_state"):
            self._empty_state.setVisible(count == 0)

        self._refresh_kpis(None)
        self._populate_categories()

        if hasattr(self, "_insights"):
            try:
                self._insights.refresh(self._inventory_query, self.sucursal_id)
            except Exception:
                logger.exception("No se pudo refrescar panel de insights de inventario")

    def _cargar_movimientos_tab(self) -> None:
        self.tabla_movimientos.setRowCount(0)
        rows = self._inventory_query.list_recent_movements(branch_id=self.sucursal_id, limit=200)
        for i, r in enumerate(rows):
            self.tabla_movimientos.insertRow(i)
            for j, v in enumerate(r):
                self.tabla_movimientos.setItem(i, j, QTableWidgetItem(str(v or "")))

    def _refresh_kpis(self, db) -> None:
        del db
        data = self._inventory_query.get_operational_kpis(
            branch_id=self.sucursal_id, product_data=self._prod_data
        )
        self._kpi_bajo.set_valor(str(data.get("stock_bajo", 0)))
        self._kpi_sin.set_valor(str(data.get("sin_stock_fisico", 0)))
        virtual_value = data.get("virtual_disponible")
        self._kpi_virtual.set_valor("Pendiente" if virtual_value is None else str(virtual_value))
        self._kpi_res.set_valor(f"{float(data.get('reservados', 0) or 0):.3f}")
        self._kpi_mov.set_valor(str(data.get("mov_hoy", 0)))

    def _on_kpi_click(self, key: str) -> None:
        self._kpi_click_mode = key
        if key == "virtual_disponible":
            self._tabs_inv.setCurrentWidget(self._tab_virtual)
            return
        if key == "mov_hoy":
            self._tabs_inv.setCurrentWidget(self._tab_mov)
            return
        self._tabs_inv.setCurrentWidget(self._tab_exist)
        self._apply_filters()

    def _populate_categories(self) -> None:
        current = self._cmb_cat.currentText()
        self._cmb_cat.blockSignals(True)
        self._cmb_cat.clear()
        self._cmb_cat.addItem("Todas las categorías")
        cats = sorted({p["categoria"] for p in self._prod_data if p["categoria"]})
        self._cmb_cat.addItems(cats)
        idx = self._cmb_cat.findText(current)
        if idx >= 0:
            self._cmb_cat.setCurrentIndex(idx)
        self._cmb_cat.blockSignals(False)

    # ── Filter / search ───────────────────────────────────────────────────────

    def _on_search(self, _text: str) -> None:
        self._apply_filters()

    def _apply_filters(self) -> None:
        query    = self._search.text().strip().lower()
        cat_sel  = self._cmb_cat.currentText()
        est_sel  = self._cmb_estado.currentIndex()  # 0=all 1=critical 2=low 3=ok

        _ESTADO_MAP = {
            1: _HEALTH_CRITICAL,
            2: _HEALTH_LOW,
            3: _HEALTH_OK,
        }
        health_filter = _ESTADO_MAP.get(est_sel, None)

        for row in range(self.tabla.rowCount()):
            nombre = (self.tabla.item(row, 0).text() if self.tabla.item(row, 0) else "").lower()
            cat    = (self.tabla.item(row, 1).text() if self.tabla.item(row, 1) else "").lower()
            estado = (self.tabla.item(row, 4).text() if self.tabla.item(row, 4) else "")

            match_q = (not query) or (query in nombre) or (query in cat)
            match_c = (cat_sel == "Todas las categorías") or (cat == cat_sel.lower())
            match_e = (health_filter is None) or (estado == health_filter)

            match_kpi = True
            if getattr(self, "_kpi_click_mode", "none") == "stock_bajo":
                match_kpi = (estado == _HEALTH_LOW)
            elif getattr(self, "_kpi_click_mode", "none") == "sin_stock_fisico":
                match_kpi = (estado == _HEALTH_CRITICAL)
            self.tabla.setRowHidden(row, not (match_q and match_c and match_e and match_kpi))

    # ── Operational actions ───────────────────────────────────────────────────

    def _selected_product(self) -> dict | None:
        row = self.tabla.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Sin selección", "Seleccione un producto en la tabla.")
            return None
        it = self.tabla.item(row, 0)
        if not it:
            return None
        prod_id = it.data(Qt.UserRole)
        for p in self._prod_data:
            if p["id"] == prod_id:
                return p
        return None

    def _accion_entrada(self) -> None:
        """Stock entry — audited, movement-driven."""
        try:
            from core.permissions import verificar_permiso
            if not verificar_permiso(self.container, "INVENTARIO.entrada", self):
                return
        except Exception:
            logger.exception("No se pudo verificar permiso INVENTARIO.entrada")
            return

        prod = self._selected_product()
        if not prod:
            return

        dlg = _StockEntryDialog(
            prod["id"], prod["nombre"], prod["unidad"], self
        )
        if dlg.exec_() != QDialog.Accepted:
            return

        r = dlg.resultado
        try:
            operation_id = f"inventory-entry-{uuid.uuid4()}"
            result = self._inventory_app.increase_stock(
                product_id=prod["id"],
                branch_id=self.sucursal_id,
                quantity=r["cantidad"],
                unit=prod["unidad"],
                reason=r["referencia"] or "Entrada manual de inventario",
                operation_id=operation_id,
                source_module="inventory_ui",
                reference_type="INVENTORY_ENTRY",
                reference_id=r["referencia"] or None,
                user_name=self.usuario_actual or "sistema",
            )
            if not result.success:
                raise Exception(result.message)
            Toast.success(
                self, "Entrada registrada",
                f"+{r['cantidad']:.3f} {prod['unidad']} → {prod['nombre']}"
            )
            self.cargar_datos()
        except Exception as e:
            logger.exception("INVENTARIO.entrada")
            QMessageBox.critical(self, "Error en entrada", _to_business_inventory_error(e))

    def _accion_ajuste(self) -> None:
        """Audited inventory adjustment — requires reason + observation."""
        try:
            from core.permissions import verificar_permiso
            if not verificar_permiso(self.container, "INVENTARIO.ajustar", self):
                return
        except Exception:
            logger.exception("No se pudo verificar permiso INVENTARIO.ajustar")
            return

        prod = self._selected_product()
        if not prod:
            return

        dlg = _AuditAdjustDialog(
            prod["id"], prod["nombre"], prod["stock"], prod["unidad"], self
        )
        if dlg.exec_() != QDialog.Accepted:
            return

        r = dlg.resultado
        try:
            operation_id = f"inventory-adjust-{uuid.uuid4()}"
            result = self._inventory_app.adjust_stock(
                product_id=prod["id"],
                branch_id=self.sucursal_id,
                new_quantity=r["cantidad_nueva"],
                unit=prod["unidad"],
                reason=r["motivo"],
                operation_id=operation_id,
                source_module="inventory_ui",
                reference_type="INVENTORY_ADJUSTMENT",
                reference_id=None,
                user_name=self.usuario_actual or "sistema",
            )
            if not result.success:
                raise Exception(result.message)
            Toast.success(
                self, "Ajuste registrado",
                f"Stock ajustado a {r['cantidad_nueva']:.3f} — op. {result.operation_id[:8]}"
            )
            self.cargar_datos()
        except Exception as e:
            logger.exception("INVENTARIO.ajustar")
            QMessageBox.critical(self, "Error en ajuste", _to_business_inventory_error(e))

    def _accion_historial(self) -> None:
        """Open read-only movement audit trail for selected product."""
        prod = self._selected_product()
        if not prod:
            return
        dlg = _MovHistoryDialog(
            prod["id"], prod["nombre"],
            self._inventory_query, self.sucursal_id, self
        )
        dlg.exec_()

    # ── Legacy compatibility ──────────────────────────────────────────────────

    def abrir_dialogo_ajuste(self) -> None:
        """Legacy entry point — delegates to audited workflow."""
        self._accion_ajuste()

    # ── Export ────────────────────────────────────────────────────────────────

    def _exportar(self, fmt: str) -> None:
        headers = ["ID", "Producto", "Categoría", "Stock", "Stock Mín.", "Unidad", "Estado", "Último Mov."]
        rows = [
            [
                str(p["id"]), p["nombre"], p["categoria"],
                f"{p['stock']:.3f}", f"{p['stock_minimo']:.1f}",
                p["unidad"], p["health"], p["last_mov"],
            ]
            for p in self._prod_data
        ]

        if fmt == "csv":
            path, _ = QFileDialog.getSaveFileName(
                self, "Exportar inventario CSV", "inventario.csv", "CSV (*.csv)"
            )
            if not path:
                return
            try:
                import csv
                with open(path, "w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow(headers)
                    csv.writer(f).writerows(rows)
                Toast.success(self, "Exportado", path)
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Exportar inventario Excel", "inventario.xlsx", "Excel (*.xlsx)"
            )
            if not path:
                return
            try:
                import openpyxl
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.append(headers)
                for row in rows:
                    ws.append(row)
                wb.save(path)
                Toast.success(self, "Exportado", path)
            except ImportError:
                path2 = path.replace(".xlsx", ".csv")
                import csv
                with open(path2, "w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow(headers)
                    csv.writer(f).writerows(rows)
                Toast.info(self, "Guardado como CSV", f"openpyxl no instalado — {path2}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
