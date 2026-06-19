
# modulos/delivery.py — SPJ POS v7  DELIVERY UI COMPLETO
from __future__ import annotations
import logging
import os
import uuid
from modulos.spj_phone_widget import PhoneWidget

# ── Address Autocomplete — async infrastructure ───────────────────────────────
# All geocoding HTTP I/O is moved off the Qt main thread via QRunnable workers.
# The UI layer only knows about _AddrWorker and _AddrSignals — it has zero
# knowledge of Mapbox, Nominatim, or any HTTP client.

from core.cache.address_cache import AddressCache as _AddressCache

# Module-level shared cache (survives dialog re-opens, persists for session).
_addr_cache: _AddressCache = _AddressCache(
    max_size=int(os.environ.get("GEOCODING_CACHE_SIZE", "200")),
    ttl=int(os.environ.get("GEOCODING_CACHE_TTL", "3600")),
)

# Minimum characters before firing a geocoding request (per product spec).
_ADDR_MIN_CHARS: int = int(os.environ.get("DELIVERY_MIN_SEARCH_CHARS", "5"))
# Debounce interval in ms — configurable via env.
_ADDR_DEBOUNCE_MS: int = int(os.environ.get("DELIVERY_SEARCH_DEBOUNCE_MS", "400"))

from modulos.spj_styles import spj_btn, apply_btn_styles
from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.kpi_card import KPICard
from modulos.ui_components import (
    create_primary_button, create_success_button, create_danger_button,
    create_secondary_button, create_warning_button, create_input, create_combo,
    create_card, apply_tooltip, LoadingIndicator, EmptyStateWidget,
    PageHeader, Toast,
)
from modulos.spj_refresh_mixin import RefreshMixin
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QComboBox, QLineEdit, QGroupBox, QFormLayout,
    QMessageBox, QHeaderView, QSplitter, QTextEdit, QDialog, QDialogButtonBox,
    QSpinBox, QDoubleSpinBox, QFrame, QListWidget, QListWidgetItem,
    QRadioButton, QButtonGroup, QTimeEdit, QDateEdit, QAbstractItemView,
    QApplication,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QRunnable, QThreadPool, QObject, pyqtSlot, QTime, QDate
from PyQt5.QtGui import QFont, QColor
from core.db.connection import get_connection
from core.services.delivery_service import DeliveryService
from core.delivery.domain.state_machine import DeliveryStateMachine
from core.services.order_badge_service import OrderBadgeService
from core.delivery.application.query_service import DeliveryQueryService as _DeliveryQueryService
from core.utils.delivery_ui_filters import (
    infer_workflow_for_ui as _infer_workflow_for_ui_fn,
    matches_operational_tab as _matches_operational_tab_fn,
    matches_scheduled_window as _matches_scheduled_window_fn,
)
from core.services.driver_service import DriverService
from frontend.desktop.components.product_search_box import ProductSearchBox
from frontend.desktop.components.search_selector import SearchOption
from backend.application.queries.product_query_service import ProductQueryService as _ProductQueryService
logger = logging.getLogger("spj.delivery")


class _AddrSignals(QObject):
    """Cross-thread signal carrier for address autocomplete results.

    Carries the request_id so stale results from superseded queries are
    silently discarded in the UI thread without race conditions.
    """
    results = pyqtSignal(list, str)   # (suggestions, request_id)


class _AddrWorker(QRunnable):
    """Executes one geocoding call in QThreadPool (off-UI-thread).

    Each worker instance holds a unique request_id. The UI compares this
    against _pending_request_id; mismatches are dropped, preventing
    stale-result flicker when the user types faster than the API responds.
    """

    def __init__(
        self,
        query: str,
        request_id: str,
        geocoding_fn,
        signals: _AddrSignals,
        limit: int = 6,
    ) -> None:
        super().__init__()
        self._query       = query
        self._request_id  = request_id
        self._geocoding_fn = geocoding_fn
        self._signals     = signals
        self._limit       = limit
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self) -> None:
        try:
            data = self._geocoding_fn(self._query) or []
        except Exception as exc:
            logger.debug("_AddrWorker error req=%s: %s", self._request_id[:8], exc)
            data = []
        self._signals.results.emit(data[:self._limit], self._request_id)



# ── Canonical action policy — imported from domain layer (no duplication here) ──
from core.delivery.application.action_policy import DeliveryActionPolicy as _CanonicalActionPolicy
from core.delivery.domain.value_objects import (
    DeliveryStatus as _DeliveryStatus,
    FulfillmentType as _FulfillmentType,
    PaymentStatus as _PaymentStatus,
    DeliveryAction as _DeliveryAction,
    UnitCode as _UnitCode,
    LEGACY_STATUS_MAP as _LEGACY_STATUS_MAP,
    WEIGHABLE_UNITS as _WEIGHABLE_UNITS,
    UNIT_LABELS_ES as _UNIT_LABELS_ES,
)
from core.delivery.application.kanban_config import KANBAN_COLUMNS as _KANBAN_COLUMNS
from core.delivery.application.quantity_formatter import QuantityFormatter as _QuantityFormatter

# Build reverse map: legacy DB status string → kanban column index (0-3)
_STATUS_TO_COL: dict[str, int] = {}
for _col_idx, (_col_title, _col_statuses) in enumerate(_KANBAN_COLUMNS):
    for _ds in _col_statuses:
        for _legacy, _canonical in _LEGACY_STATUS_MAP.items():
            if _canonical == _ds:
                _STATUS_TO_COL[_legacy] = _col_idx
        _STATUS_TO_COL[_ds.value] = _col_idx

_KANBAN_COL_COLORS = [
    Colors.WARNING_BASE,   # Pendiente
    Colors.PRIMARY_BASE,   # Preparación
    Colors.ACCENT_BASE,    # En reparto / Para entregar
    Colors.SUCCESS_BASE,   # Entrega
]

# Build ESTADOS and ESTADO_COLOR from the domain enum (single source of truth).
_STATUS_COLOR_MAP: dict[_DeliveryStatus, str] = {
    _DeliveryStatus.PENDING: Colors.WARNING_BASE,
    _DeliveryStatus.PREPARING: Colors.PRIMARY_BASE,
    _DeliveryStatus.IN_TRANSIT: Colors.ACCENT_BASE,
    _DeliveryStatus.DELIVERED: Colors.SUCCESS_BASE,
    _DeliveryStatus.CANCELLED: Colors.DANGER_BASE,
    _DeliveryStatus.READY_FOR_PICKUP: Colors.ACCENT_BASE,
    _DeliveryStatus.READY_FOR_DISPATCH: Colors.ACCENT_BASE,
    _DeliveryStatus.ASSIGNED: Colors.PRIMARY_BASE,
}
ESTADOS = list(_LEGACY_STATUS_MAP.keys())
ESTADO_COLOR = {legacy: _STATUS_COLOR_MAP.get(canonical, Colors.TEXT_SECONDARY)
                for legacy, canonical in _LEGACY_STATUS_MAP.items()}

# Canonical action metadata for legacy state machine action keys
_ACTION_METADATA = {
    "preparacion":         ("▶",  "Preparar",            "success"),
    "cancelado":           ("✖",  "Cancelar pedido",      "danger"),
    "ajustar_peso":        ("⚖️", "Ajustar peso",         "warning"),
    "ajustar_cantidad":    ("✏️", "Ajustar cantidad",     "warning"),
    "en_ruta":             ("🛵", "En Ruta",              "primary"),
    "asignar":             ("👤", "Asignar repartidor",   "primary"),
    "entregado":           ("✅", "Marcar entregado",     "success"),
    "notificar_wa":        ("📲", "Notificar por WA",     "secondary"),
    "imprimir":            ("🖨️", "Imprimir ticket",      "secondary"),
    "reactivar":           ("♻️", "Reactivar pedido",     "warning"),
    "activar_programado":  ("▶",  "Activar ahora",        "success"),
    "reprogramar":         ("🗓️", "Reprogramar",          "warning"),
}


def _get_card_actions(pedido: dict) -> list[dict]:
    """Single route for card action buttons — used by Kanban AND list.

    Delegates to delivery_service.get_valid_actions when available so that the
    domain state machine drives which actions appear.  Metadata (icon, label,
    style) comes from _ACTION_METADATA; the label for weight/quantity adjustment
    is resolved from the order items' units so it is never hardcoded.
    """
    estado = (pedido.get("estado") or "pendiente").strip().lower()
    order_context = {
        "estado": estado,
        "workflow_type": pedido.get("workflow_type", ""),
        "adjustment_pending": bool(int(pedido.get("adjustment_pending") or 0)),
        "scheduled_at": pedido.get("scheduled_at"),
        "delivery_type": pedido.get("delivery_type", ""),
        "responsable": pedido.get("responsable", ""),
    }
    action_keys: list[str] = []
    try:
        action_keys = DeliveryStateMachine().get_valid_actions(order_context)
    except Exception:
        pass

    # Determine if items are weighable to swap label
    items = pedido.get("items") or []
    has_weighable = any(
        _LEGACY_STATUS_MAP.get(  # reuse map as sanity check; here just unit lookup
            str(it.get("unidad") or "").lower(), None
        ) is None and str(it.get("unidad") or "").lower() in {u.value for u in _WEIGHABLE_UNITS}
        for it in items
    ) if items else True  # fallback: assume weighable when no item data

    result = []
    for key in action_keys:
        icon, label, style = _ACTION_METADATA.get(key, ("", key, "secondary"))
        if key == "ajustar_peso":
            label = "Ajustar peso" if has_weighable else "Ajustar cantidad"
        result.append({"icon": icon, "label": label, "key": key, "style": style})
    return result


# Keep for legacy callers that still reference the old class name
class DeliveryActionPolicy:
    @classmethod
    def get_actions(cls, estado: str, *, workflow_type: str = "", adjustment_pending: bool = False) -> list:
        return _get_card_actions({"estado": estado, "workflow_type": workflow_type, "adjustment_pending": adjustment_pending})


def _matches_operational_tab(pedido: dict, tab_key: str | None) -> bool:
    return _matches_operational_tab_fn(pedido, tab_key)


def _matches_scheduled_window(pedido: dict, window_key: str) -> bool:
    return _matches_scheduled_window_fn(pedido, window_key)

class AsignarDriverDialog(QDialog):
    def __init__(self, pedido_id, conexion, parent=None):
        super().__init__(parent)
        self.pedido_id = pedido_id
        self.conexion = conexion
        self.setWindowTitle(f"Asignar Repartidor — Pedido #{pedido_id}")
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.combo_driver = QComboBox()
        self._cargar_drivers()
        form.addRow("Repartidor:", self.combo_driver)
        self.spin_tiempo = QSpinBox()
        self.spin_tiempo.setRange(0, 480); self.spin_tiempo.setValue(0)
        self.spin_tiempo.setSuffix(" min")
        form.addRow("Tiempo estimado:", self.spin_tiempo)
        self.txt_notas = QTextEdit(); self.txt_notas.setMaximumHeight(80)
        self.txt_notas.setPlaceholderText("Instrucciones al repartidor...")
        form.addRow("Notas:", self.txt_notas)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _cargar_drivers(self):
        try:
            branch_id = int(getattr(self.parent(), "sucursal_id", 1) or 1)
            rows = self.parent().driver_service.list_active_drivers(branch_id) if hasattr(self.parent(), "driver_service") else []
            for r in rows:
                label = f"{r.get('nombre', '')} · {r.get('telefono', '')} · {r.get('vehiculo', '')}"
                self.combo_driver.addItem(label, r.get("id"))
            if self.combo_driver.count() == 0:
                self.combo_driver.addItem("Sin repartidores registrados", None)
        except Exception as e:
            self.combo_driver.addItem(f"Error: {e}", None)

    def get_data(self):
        return {
            "driver_id": self.combo_driver.currentData(),
            "tiempo": self.spin_tiempo.value(),
            "notas": self.txt_notas.toPlainText()
        }

class NuevoPedidoDialog(QDialog):
    """Diálogo completo para ingresar un pedido delivery manualmente.

    Equivalente a un pedido WhatsApp pero capturado por el operador:
    cliente (búsqueda en BD), productos con cantidades/precios,
    forma y condición de entrega (urgente / hora / programado).
    """

    def __init__(self, delivery_service: DeliveryService, conexion, parent=None):
        super().__init__(parent)
        self.delivery_service = delivery_service
        self.conexion = conexion
        self._selected_coords = None
        self._items: list = []          # [{nombre, cantidad, precio, subtotal, unidad, producto_id}]
        self._cliente_id: int | None = None
        self._current_prod_data: dict = {}

        self.setWindowTitle("📦 Nuevo Pedido Delivery")
        self.setMinimumSize(760, 640)
        self.setWindowModality(Qt.ApplicationModal)

        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

        # ── SECCIÓN CLIENTE ───────────────────────────────────────────────
        grp_cl = QGroupBox("👤 Cliente")
        cl = QHBoxLayout(grp_cl)
        cl.setSpacing(6)
        self.txt_buscar_cliente = QLineEdit()
        self.txt_buscar_cliente.setPlaceholderText("Buscar por nombre o teléfono…")
        btn_buscar_cl = create_secondary_button(self, "🔍", "Buscar cliente en la base de datos")
        btn_buscar_cl.setFixedWidth(36)
        self.txt_nombre_cliente = QLineEdit()
        self.txt_nombre_cliente.setPlaceholderText("Nombre completo")
        self.txt_tel_cliente = QLineEdit()
        self.txt_tel_cliente.setPlaceholderText("+52 55 …")
        self.txt_tel_cliente.setFixedWidth(140)
        cl.addWidget(QLabel("Buscar:"))
        cl.addWidget(self.txt_buscar_cliente, 2)
        cl.addWidget(btn_buscar_cl)
        cl.addWidget(QLabel("Nombre:"))
        cl.addWidget(self.txt_nombre_cliente, 2)
        cl.addWidget(QLabel("Tel:"))
        cl.addWidget(self.txt_tel_cliente)
        root.addWidget(grp_cl)

        btn_buscar_cl.clicked.connect(self._buscar_cliente)
        self.txt_buscar_cliente.returnPressed.connect(self._buscar_cliente)

        # ── SECCIÓN DIRECCIÓN ──────────────────────────────────────────────
        grp_dir = QGroupBox("📍 Dirección de entrega")
        dl = QVBoxLayout(grp_dir)
        dl.setSpacing(4)
        self.txt_direccion = QLineEdit()
        self.txt_direccion.setPlaceholderText("Escribe la dirección (mín. 4 caracteres para autocompletar con OSM)")
        self.lst_sugerencias = QListWidget()
        self.lst_sugerencias.setMaximumHeight(80)
        self.lst_sugerencias.hide()
        dl.addWidget(self.txt_direccion)
        dl.addWidget(self.lst_sugerencias)
        root.addWidget(grp_dir)

        # ── SECCIÓN PRODUCTOS ──────────────────────────────────────────────
        grp_prod = QGroupBox("🛒 Productos del pedido")
        pl = QVBoxLayout(grp_prod)
        pl.setSpacing(4)

        # Unit labels from canonical map — never hardcode string "kg" in UI
        from core.delivery.domain.value_objects import UNIT_LABELS_ES, UnitCode as _UC
        _unit_labels = [UNIT_LABELS_ES.get(u, u.value) for u in _UC]

        # Product SearchSelector — routes queries through ProductQueryService (no SQL in UI)
        self._search_results_cache: dict = {}
        self.prod_search = ProductSearchBox(self, provider=self._search_products_provider)
        self.prod_search.setMaximumHeight(110)
        pl.addWidget(self.prod_search)

        add_row = QHBoxLayout()
        self.spin_cant = QDoubleSpinBox()
        self.spin_cant.setRange(0, 9999)
        self.spin_cant.setValue(0)
        self.spin_cant.setDecimals(3)
        self.spin_cant.setFixedWidth(80)
        self.cmb_unidad = QComboBox()
        self.cmb_unidad.addItems(_unit_labels)
        self.cmb_unidad.setFixedWidth(68)
        self.spin_precio = QDoubleSpinBox()
        self.spin_precio.setRange(0, 999999)
        self.spin_precio.setDecimals(2)
        self.spin_precio.setPrefix("$")
        self.spin_precio.setFixedWidth(100)
        btn_add_prod = create_success_button(self, "➕ Agregar", "Agregar producto al pedido")
        btn_add_prod.setFixedWidth(100)

        add_row.addWidget(QLabel("Cant:"))
        add_row.addWidget(self.spin_cant)
        add_row.addWidget(self.cmb_unidad)
        add_row.addWidget(QLabel("Precio:"))
        add_row.addWidget(self.spin_precio)
        add_row.addWidget(btn_add_prod)
        pl.addLayout(add_row)

        # Items table
        self.tbl_items = QTableWidget(0, 5)
        self.tbl_items.setHorizontalHeaderLabels(["Producto", "Cant.", "Unidad", "Precio/u", "Subtotal"])
        self.tbl_items.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_items.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_items.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_items.setMinimumHeight(90)
        self.tbl_items.setMaximumHeight(180)
        self.tbl_items.verticalHeader().setVisible(False)
        pl.addWidget(self.tbl_items)

        items_foot = QHBoxLayout()
        btn_rm = create_danger_button(self, "✕ Quitar", "Quitar producto seleccionado")
        btn_rm.setFixedWidth(80)
        btn_rm.clicked.connect(self._quitar_item)
        self.lbl_total_prod = QLabel("Total: $0.00")
        self.lbl_total_prod.setStyleSheet(
            f"font-size:13px; font-weight:bold; color:{Colors.SUCCESS_BASE};"
        )
        items_foot.addWidget(btn_rm)
        items_foot.addStretch()
        items_foot.addWidget(self.lbl_total_prod)
        pl.addLayout(items_foot)
        root.addWidget(grp_prod)

        # ── CONDICIÓN DE ENTREGA  +  PAGO ─────────────────────────────────
        mid_row = QHBoxLayout()

        grp_cond = QGroupBox("🕐 Condición de entrega")
        condl = QVBoxLayout(grp_cond)
        self.rb_urgente    = QRadioButton("🚨 Urgente (lo antes posible)")
        self.rb_hora       = QRadioButton("⏰ A una hora específica:")
        self.rb_programado = QRadioButton("📅 Fecha programada:")
        self.rb_urgente.setChecked(True)
        self._bg_cond = QButtonGroup(self)
        for rb in (self.rb_urgente, self.rb_hora, self.rb_programado):
            self._bg_cond.addButton(rb)
        self.time_edit = QTimeEdit(QTime.currentTime().addSecs(3600))
        self.time_edit.setEnabled(False)
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setEnabled(False)
        self.rb_hora.toggled.connect(self.time_edit.setEnabled)
        self.rb_programado.toggled.connect(self.date_edit.setEnabled)
        condl.addWidget(self.rb_urgente)
        hora_row = QHBoxLayout()
        hora_row.addWidget(self.rb_hora)
        hora_row.addWidget(self.time_edit)
        hora_row.addStretch()
        condl.addLayout(hora_row)
        prog_row = QHBoxLayout()
        prog_row.addWidget(self.rb_programado)
        prog_row.addWidget(self.date_edit)
        prog_row.addStretch()
        condl.addLayout(prog_row)
        condl.addStretch()

        grp_pago = QGroupBox("💳 Forma de pago")
        pagol = QFormLayout(grp_pago)
        self.cmb_pago = QComboBox()
        self.cmb_pago.addItems([
            "Efectivo al entregar",
            "Tarjeta al entregar",
            "Transferencia",
            "MercadoPago (link)",
            "Anticipo + saldo",
            "Ya pagado (online)",
            "Sin cobro",
        ])
        self.spin_anticipo = QDoubleSpinBox()
        self.spin_anticipo.setRange(0, 999999)
        self.spin_anticipo.setDecimals(2)
        self.spin_anticipo.setPrefix("$")
        self.lbl_saldo = QLabel("Saldo: $0.00")
        self.lbl_saldo.setStyleSheet(f"color:{Colors.WARNING_BASE}; font-weight:bold;")
        pagol.addRow("Método:", self.cmb_pago)
        pagol.addRow("Anticipo:", self.spin_anticipo)
        pagol.addRow("", self.lbl_saldo)

        mid_row.addWidget(grp_cond, 3)
        mid_row.addWidget(grp_pago, 2)
        root.addLayout(mid_row)

        # ── NOTAS + SUCURSAL ─────────────────────────────────────────────
        extra = QHBoxLayout()
        self.txt_notas = QLineEdit()
        self.txt_notas.setPlaceholderText("Notas para el repartidor: referencias, instrucciones especiales…")
        self.combo_sucursal = QComboBox()
        self.combo_sucursal.addItems(["Sucursal Principal", "Sucursal 2", "Sucursal 3"])
        extra.addWidget(QLabel("Notas:"))
        extra.addWidget(self.txt_notas, 3)
        extra.addWidget(QLabel("Sucursal:"))
        extra.addWidget(self.combo_sucursal)
        root.addLayout(extra)

        # ── BOTONES ──────────────────────────────────────────────────────
        btns_box = QDialogButtonBox()
        btn_crear = create_success_button(self, "✓ Crear Pedido", "Guardar y enviar el pedido")
        btn_crear.setMinimumWidth(130)
        btns_box.addButton(btn_crear, QDialogButtonBox.AcceptRole)
        btns_box.addButton("Cancelar", QDialogButtonBox.RejectRole)
        btns_box.rejected.connect(self.reject)
        btn_crear.clicked.connect(self._validar_y_aceptar)
        root.addWidget(btns_box)

        # ── WIRING ───────────────────────────────────────────────────────
        btn_add_prod.clicked.connect(self._agregar_item)
        self.prod_search.selected.connect(self._on_product_selected)
        self.spin_anticipo.valueChanged.connect(self._actualizar_saldo)

        # Address debounce + request-ID cancellation
        self._pending_query: str = ""
        self._pending_request_id: str = ""       # stale results are discarded
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_ADDR_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._do_search)
        self.txt_direccion.textChanged.connect(self._on_dir_changed)
        self.lst_sugerencias.itemClicked.connect(self._tomar_sugerencia)

    # ── CLIENT SEARCH ─────────────────────────────────────────────────────
    def _buscar_cliente(self) -> None:
        q = self.txt_buscar_cliente.text().strip()
        if not q:
            return
        try:
            rows = _DeliveryQueryService(self.conexion).search_customers(q)
        except Exception:
            rows = []
        if not rows:
            QMessageBox.information(self, "Sin resultados", f"No se encontró cliente: «{q}»")
            return
        if len(rows) == 1:
            self._set_cliente(*rows[0])
        else:
            dlg = QDialog(self)
            dlg.setWindowTitle("Seleccionar cliente")
            dlg.setMinimumWidth(420)
            lay = QVBoxLayout(dlg)
            lst = QListWidget()
            for r in rows:
                wi = QListWidgetItem(f"{r[1]}  |  {r[2]}")
                wi.setData(Qt.UserRole, r)
                lst.addItem(wi)
            lay.addWidget(lst)
            bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            bb.accepted.connect(dlg.accept)
            bb.rejected.connect(dlg.reject)
            lay.addWidget(bb)
            lst.itemDoubleClicked.connect(lambda _: dlg.accept())
            if dlg.exec_() == QDialog.Accepted and lst.currentItem():
                self._set_cliente(*lst.currentItem().data(Qt.UserRole))

    def _set_cliente(self, cid, nombre, telefono, direccion="") -> None:
        self._cliente_id = cid
        self.txt_nombre_cliente.setText(nombre)
        self.txt_tel_cliente.setText(telefono)
        if direccion and not self.txt_direccion.text().strip():
            self.txt_direccion.setText(direccion)

    # ── PRODUCT SEARCH — routed through ProductQueryService (no SQL in UI) ──────
    def _search_products_provider(self, q: str) -> list[SearchOption]:
        if len(q) < 2:
            return []
        try:
            results = _ProductQueryService.from_connection(self.conexion).search_products(q)
        except Exception:
            logger.exception("Product search failed query=%r", q)
            return []
        self._search_results_cache = {r.id: r for r in results}
        return [
            SearchOption(
                id=r.id,
                label=r.label,
                subtitle=f"${r.metadata.get('price', 0):.2f} / {r.metadata.get('unit', '')}",
            )
            for r in results
        ]

    def _on_product_selected(self, option: SearchOption) -> None:
        r = self._search_results_cache.get(option.id)
        meta = r.metadata if r is not None else {}
        self._current_prod_data = {
            "id": option.id,
            "nombre": option.label,
            "precio": meta.get("price", 0),
            "unidad": meta.get("unit", ""),
        }
        self.spin_precio.setValue(float(meta.get("price", 0) or 0))
        unit_label = str(meta.get("unit", ""))
        idx = self.cmb_unidad.findText(unit_label)
        if idx >= 0:
            self.cmb_unidad.setCurrentIndex(idx)
        self.prod_search.set_selected_label(option.label)

    def _agregar_item(self) -> None:
        nombre = (
            self._current_prod_data.get("nombre")
            or self.prod_search._search_box.text().strip()
        )
        if not nombre:
            QMessageBox.warning(self, "Producto requerido", "Escribe el nombre del producto.")
            return
        cant    = self.spin_cant.value()
        precio  = self.spin_precio.value()
        unidad  = self.cmb_unidad.currentText()
        subtot  = round(cant * precio, 2)
        self._items.append({
            "nombre": nombre,
            "cantidad": cant,
            "precio": precio,
            "subtotal": subtot,
            "unidad": unidad,
            "producto_id": self._current_prod_data.get("id"),
        })
        self._refresh_items_table()
        self.prod_search.clear()
        self.spin_cant.setValue(0)
        self.spin_precio.setValue(0)
        self._current_prod_data = {}

    def _quitar_item(self) -> None:
        row = self.tbl_items.currentRow()
        if 0 <= row < len(self._items):
            self._items.pop(row)
            self._refresh_items_table()

    def _refresh_items_table(self) -> None:
        self.tbl_items.setRowCount(0)
        total = 0.0
        for i, it in enumerate(self._items):
            self.tbl_items.insertRow(i)
            self.tbl_items.setItem(i, 0, QTableWidgetItem(it["nombre"]))
            self.tbl_items.setItem(i, 1, QTableWidgetItem(f"{it['cantidad']:.3g}"))
            self.tbl_items.setItem(i, 2, QTableWidgetItem(it["unidad"]))
            self.tbl_items.setItem(i, 3, QTableWidgetItem(f"${it['precio']:.2f}"))
            sub = QTableWidgetItem(f"${it['subtotal']:.2f}")
            sub.setForeground(QColor(Colors.SUCCESS_BASE))
            self.tbl_items.setItem(i, 4, sub)
            total += it["subtotal"]
        self.lbl_total_prod.setText(f"Total: ${total:,.2f}")
        self._actualizar_saldo()

    def _actualizar_saldo(self) -> None:
        total = sum(it["subtotal"] for it in self._items)
        saldo = total - self.spin_anticipo.value()
        self.lbl_saldo.setText(f"Saldo: ${saldo:,.2f}")

    def _get_condicion(self) -> str:
        if self.rb_urgente.isChecked():
            return "URGENTE"
        if self.rb_hora.isChecked():
            return f"Entrega a las {self.time_edit.time().toString('HH:mm')}"
        return f"Programado: {self.date_edit.date().toString('dd/MM/yyyy')}"

    def _validar_y_aceptar(self) -> None:
        nombre = self.txt_nombre_cliente.text().strip() or self.txt_buscar_cliente.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Cliente requerido", "Ingresa o busca el nombre del cliente.")
            return
        if not self.txt_direccion.text().strip():
            QMessageBox.warning(self, "Dirección requerida", "Ingresa la dirección de entrega.")
            return

        # Stock pre-flight: warn if any item with producto_id has insufficient available stock
        sin_stock = []
        try:
            from core.services.inventory_balance_service import InventoryBalanceService
            _inv_svc = InventoryBalanceService(self.conexion)
            sucursal_id = self.combo_sucursal.currentIndex() + 1
            for it in self._items:
                pid = it.get("producto_id")
                if not pid:
                    continue
                available = float(_inv_svc.get_available_stock(
                    product_id=pid, branch_id=sucursal_id
                ))
                if available < it["cantidad"]:
                    sin_stock.append(
                        f"• {it['nombre']}: solicitado {it['cantidad']:.3g}, disponible {available:.3g}"
                    )
        except Exception:
            pass  # stock check is advisory — never block order creation on service error

        if sin_stock:
            resp = QMessageBox.question(
                self,
                "Stock insuficiente",
                "Los siguientes productos no tienen suficiente stock:\n\n"
                + "\n".join(sin_stock)
                + "\n\n¿Crear el pedido de todas formas?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if resp != QMessageBox.Yes:
                return

        self.accept()

    # ── ADDRESS AUTOCOMPLETE (async, Mapbox-backed) ───────────────────────
    def _on_dir_changed(self, text: str) -> None:
        self._pending_query = text
        self._selected_coords = None
        if len(text.strip()) < _ADDR_MIN_CHARS:
            self.lst_sugerencias.clear()
            self.lst_sugerencias.hide()
            self._debounce.stop()
            return
        self._debounce.start()

    def _do_search(self) -> None:
        q = self._pending_query
        if len(q.strip()) < _ADDR_MIN_CHARS:
            return

        # Cache hit — no worker needed
        cache_key = f"ac:{q.lower()}:6"
        cached = _addr_cache.get(cache_key)
        if cached is not None:
            logger.debug("addr cache HIT q=%r", q[:40])
            self._show_addr_results(cached)
            return

        # Issue async worker with unique request ID
        req_id = uuid.uuid4().hex
        self._pending_request_id = req_id
        logger.debug("addr worker start req=%s q=%r", req_id[:8], q[:40])

        sigs = _AddrSignals()
        sigs.results.connect(self._on_addr_results)
        worker = _AddrWorker(
            query=q,
            request_id=req_id,
            geocoding_fn=self.delivery_service.autocomplete_address,
            signals=sigs,
            limit=6,
        )
        QThreadPool.globalInstance().start(worker)

    def _on_addr_results(self, results: list, request_id: str) -> None:
        # Discard stale responses from superseded keystrokes
        if request_id != self._pending_request_id:
            logger.debug("addr stale result discarded req=%s", request_id[:8])
            return
        if results:
            cache_key = f"ac:{self._pending_query.lower()}:6"
            _addr_cache.put(cache_key, results)
        self._show_addr_results(results)

    def _show_addr_results(self, results: list) -> None:
        self.lst_sugerencias.clear()
        for item in results:
            w = QListWidgetItem(item.get("label", ""))
            w.setData(Qt.UserRole, item)
            self.lst_sugerencias.addItem(w)
        self.lst_sugerencias.setVisible(self.lst_sugerencias.count() > 0)

    def _tomar_sugerencia(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole) or {}
        self.txt_direccion.setText(data.get("label", ""))
        self._selected_coords = data
        self.lst_sugerencias.hide()

    # ── DATA EXTRACTION ───────────────────────────────────────────────────
    def get_data(self) -> dict:
        nombre   = self.txt_nombre_cliente.text().strip() or self.txt_buscar_cliente.text().strip()
        condicion = self._get_condicion()
        notas    = self.txt_notas.text().strip()
        if condicion != "URGENTE":
            notas = f"{condicion}. {notas}".strip(". ")
        total = sum(it["subtotal"] for it in self._items)
        return {
            "cliente_id":    self._cliente_id,
            "cliente":       nombre,
            "cliente_tel":   self.txt_tel_cliente.text().strip(),
            "direccion":     self.txt_direccion.text().strip(),
            "coords":        self._selected_coords,
            "items":         list(self._items),
            "total":         total,
            "pago_metodo":   self.cmb_pago.currentText(),
            "anticipo":      self.spin_anticipo.value(),
            "condicion":     condicion,
            "notas":         notas,
            "sucursal_id":   self.combo_sucursal.currentIndex() + 1,
        }

class TarjetaPedido(QFrame):
    accion_requerida = pyqtSignal(int, str)  # pedido_id, accion
    def __init__(self, pedido: dict, parent=None):
        super().__init__(parent)
        self.pedido = pedido
        def _status_es(raw: str) -> str:
            return {
                "pendiente": "Pendiente",
                "preparacion": "Preparación",
                "en_ruta": "En ruta",
                "entregado": "Entregado",
                "cancelado": "Cancelado",
                "programado": "Programado",
                "scheduled": "Programado",
            }.get((raw or "").strip().lower(), raw or "Pendiente")
        def _origin_es(raw: str) -> str:
            return {
                "whatsapp": "WhatsApp",
                "counter": "Mostrador",
                "quote": "Cotización",
                "scheduled": "Programado",
            }.get((raw or "").strip().lower(), "Mostrador")
        def _workflow_es(raw: str) -> str:
            return {
                "counter": "Mostrador",
                "delivery": "Reparto",
                "scheduled": "Programado",
            }.get((raw or "").strip().lower(), "Reparto")
        self.setFrameShape(QFrame.StyledPanel)
        color = ESTADO_COLOR.get(pedido.get("estado","pendiente"), Colors.TEXT_SECONDARY)
        self.setObjectName("cardPedido")
        # Estilo dinámico solo para borde de estado y fondo
        self.setStyleSheet(f"""
            QFrame#cardPedido {{
                border-left: 4px solid {color};
                border-radius: {Borders.RADIUS_MD}px;
                padding: {Spacing.SM}px;
                margin: {Spacing.XS}px;
            }}
        """)
        layout = QHBoxLayout(self)
        info = QVBoxLayout()
        
        folio = str(pedido.get("folio") or f"#{pedido.get('id','')}")
        titulo = QLabel(f"<b>📦 {folio}</b>")
        titulo.setObjectName("subheading")
        cliente = QLabel(f"Cliente: {pedido.get('cliente_nombre','N/A')}  |  Tel: {pedido.get('cliente_tel','')}")
        cliente.setObjectName("caption")
        origen_txt = f"Origen: {_origin_es(str(pedido.get('source') or pedido.get('origen') or 'whatsapp'))}"
        flujo_txt = f"Flujo: {_workflow_es(str(pedido.get('workflow_type') or 'delivery'))}"
        total = float(pedido.get("total") or pedido.get("monto_total") or 0.0)
        total_txt = f"Total: ${total:,.2f}"
        direccion = str(pedido.get("direccion") or "Sin dirección")
        short_dir = direccion if len(direccion) <= 58 else f"{direccion[:58]}…"
        driver_txt = f"Repartidor: {pedido.get('driver_nombre','Sin asignar')}"
        driver_lbl = QLabel(driver_txt)
        driver_lbl.setObjectName("textMuted")
        row_meta = QLabel(f"{origen_txt}  ·  {flujo_txt}  ·  {total_txt}")
        row_meta.setObjectName("caption")
        row_addr = QLabel(f"Dirección: {short_dir}")
        row_addr.setObjectName("textMuted")
        estado_lbl = QLabel(_status_es(str(pedido.get("estado",""))))
        estado_lbl.setObjectName("badge")
        estado_lbl.setStyleSheet(f"color: {color}; font-weight: bold;")
        if bool(int(pedido.get("adjustment_pending") or 0)):
            ajuste_lbl = QLabel("Ajuste pendiente")
            ajuste_lbl.setObjectName("badge")
            ajuste_lbl.setStyleSheet(f"color:{Colors.DANGER_BASE}; font-weight:600;")
        else:
            ajuste_lbl = None
        
        info.addWidget(titulo)
        info.addWidget(cliente)
        info.addWidget(row_meta)
        info.addWidget(row_addr)
        info.addWidget(driver_lbl)
        info.addWidget(estado_lbl)
        if ajuste_lbl:
            info.addWidget(ajuste_lbl)
        layout.addLayout(info, 1)
        # Vertical action buttons — driven by DeliveryActionPolicy (no hardcoded logic here)
        btns = QVBoxLayout()
        btns.setSpacing(3)
        btns.setContentsMargins(4, 0, 0, 0)
        estado = pedido.get("estado","pendiente")
        pid = self.pedido["id"]

        _style_factory = {
            "success":   create_success_button,
            "primary":   create_primary_button,
            "warning":   create_warning_button,
            "danger":    create_danger_button,
            "secondary": create_secondary_button,
        }

        # Single route for all card actions — same function used by list view
        actions = _get_card_actions(pedido)
        for action in actions:
            icon_text = action.get("icon", "")
            tooltip = action.get("label", "")
            accion = action.get("key", "")
            style = action.get("style", "secondary")
            factory = _style_factory.get(style, create_secondary_button)
            b = factory(self, icon_text, tooltip)
            b.setFixedWidth(36)
            b.setToolTip(tooltip)
            b.clicked.connect(lambda _, p=pid, a=accion: self.accion_requerida.emit(p, a))
            btns.addWidget(b)

        btns.addStretch()
        layout.addLayout(btns)


class PesoRealDialog(QDialog):
    """Professional weight-adjustment dialog for variable-weight delivery items.

    Shown when the operator presses "Preparar" on an order that contains
    variable-weight items (kg, g, lb …).  The dialog:
      - lists all variable-weight items with their requested quantity
      - lets the operator enter the actual prepared weight
      - shows qty diff (units) and new subtotal in real-time
      - flags tolerance exceeded (±0.2 units by default) in warning orange
      - confirms before accepting when tolerance is exceeded

    Theme-aware: uses Colors tokens, no hardcoded colours.
    """

    # Emitted after the user confirms — payload: list of {item_id, prepared_qty, reason}
    adjustments_confirmed = pyqtSignal(list)

    def __init__(self, items: list, tolerance_units: float = 0.2, parent=None):
        """
        Parameters
        ----------
        items:
            List of dicts from delivery_service.get_order_items() — must contain
            at minimum: id, nombre, cantidad, precio_unitario, unidad
        tolerance_units:
            Absolute tolerance in units (kg/u/etc) before warning is shown.
        """
        super().__init__(parent)
        self._tolerance_units = float(tolerance_units)
        self._items = items

        # Title reflects unit type: weighable → "Ajustar peso", countable → "Ajustar cantidad"
        _has_weighable = any(
            str(it.get("unidad") or "").lower() in {u.value for u in _WEIGHABLE_UNITS}
            for it in items
        )
        self.setWindowTitle("Ajustar peso real" if _has_weighable else "Ajustar cantidad")
        self.setMinimumSize(620, 400)
        self.setWindowModality(Qt.ApplicationModal)

        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(14, 14, 14, 14)

        # ── Header ──────────────────────────────────────────────────────────
        hdr = QLabel("Ingresa el peso real preparado para cada producto:")
        hdr.setStyleSheet(
            f"font-size:13px; font-weight:600; color:{Colors.TEXT_PRIMARY};"
        )
        root.addWidget(hdr)
        self._tol_lbl = QLabel(f"Tolerancia: ±{self._tolerance_units:.1f} unidades")
        self._tol_lbl.setObjectName("caption")
        root.addWidget(self._tol_lbl)

        # ── Try to load HardwareService for scale reading ────────────────────
        self._hw_service = None
        try:
            from core.services.hardware_service import HardwareService
            self._hw_service = HardwareService()
        except Exception:
            pass

        # ── Items table ──────────────────────────────────────────────────────
        has_scale = self._hw_service is not None
        n_cols = 7 if has_scale else 6
        self.tbl = QTableWidget(len(items), n_cols)
        headers = ["Producto", "Solicitado", "Unidad", "Peso real", "Diferencia", "Nuevo subtotal"]
        if has_scale:
            headers.append("📡")
        self.tbl.setHorizontalHeaderLabels(headers)
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, n_cols):
            hh.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionMode(QAbstractItemView.NoSelection)
        self.tbl.setStyleSheet(
            "QTableWidget { border:1px solid palette(mid); border-radius:6px; }"
        )

        self._spin_widgets: list = []  # QDoubleSpinBox per row
        self._diff_labels:  list = []  # QLabel diff per row
        self._sub_labels:   list = []  # QLabel subtotal per row

        for row, item in enumerate(items):
            nombre   = item.get("nombre", "")
            req_qty  = float(item.get("cantidad") or 0)
            unit     = item.get("unidad") or ""
            price    = float(item.get("precio_unitario") or 0)

            self.tbl.setItem(row, 0, QTableWidgetItem(nombre))
            self.tbl.setItem(row, 1, QTableWidgetItem(f"{req_qty:.3g}"))
            self.tbl.setItem(row, 2, QTableWidgetItem(unit))

            spin = QDoubleSpinBox()
            spin.setRange(0.001, 99999)
            spin.setDecimals(3)
            # Try to pre-fill from scale on dialog open (single item: auto-read)
            scale_val = 0.0
            if has_scale and len(items) == 1:
                try:
                    scale_val = self._hw_service.read_scale()
                except Exception:
                    pass
            spin.setValue(scale_val if scale_val > 0 else req_qty)
            spin.setSuffix(f" {unit}")
            spin.setStyleSheet(
                f"border:1px solid {Colors.PRIMARY_BASE}; border-radius:4px; padding:2px;"
            )
            self.tbl.setCellWidget(row, 3, spin)

            diff_lbl = QLabel("±0.000")
            diff_lbl.setAlignment(Qt.AlignCenter)
            self.tbl.setCellWidget(row, 4, diff_lbl)

            sub_lbl = QLabel(f"${req_qty * price:.2f}")
            sub_lbl.setAlignment(Qt.AlignCenter)
            sub_lbl.setStyleSheet(f"color:{Colors.SUCCESS_BASE}; font-weight:bold;")
            self.tbl.setCellWidget(row, 5, sub_lbl)

            if has_scale:
                btn_scale = QPushButton("📡")
                btn_scale.setToolTip("Leer peso de la báscula")
                btn_scale.setFixedWidth(34)
                btn_scale.setStyleSheet("font-size:14px; border:none; padding:2px;")
                btn_scale.clicked.connect(lambda _, r=row, s=spin: self._leer_bascula(r, s))
                self.tbl.setCellWidget(row, 6, btn_scale)

            self._spin_widgets.append(spin)
            self._diff_labels.append(diff_lbl)
            self._sub_labels.append(sub_lbl)

            # Capture row index for lambda — critical Python closure detail
            spin.valueChanged.connect(lambda v, r=row: self._on_spin_changed(r))

        root.addWidget(self.tbl)

        # ── Warning label ────────────────────────────────────────────────────
        self._warn_lbl = QLabel("")
        self._warn_lbl.setStyleSheet(
            f"color:{Colors.WARNING_BASE}; font-weight:bold; font-size:11px;"
        )
        self._warn_lbl.setWordWrap(True)
        root.addWidget(self._warn_lbl)

        # ── Reason ───────────────────────────────────────────────────────────
        reason_row = QHBoxLayout()
        reason_row.addWidget(QLabel("Motivo del ajuste:"))
        self.txt_reason = QLineEdit()
        self.txt_reason.setPlaceholderText(
            "Ej.: peso en báscula, merma, porción estándar…"
        )
        reason_row.addWidget(self.txt_reason, 3)
        root.addLayout(reason_row)

        # ── Buttons ──────────────────────────────────────────────────────────
        btn_ok = create_success_button(self, "✓ Confirmar pesos", "")
        btn_ok.setMinimumWidth(160)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setFixedWidth(100)
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._on_confirm)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        root.addLayout(btn_row)

        self._update_all_diffs()

    # ── Slots ──────────────────────────────────────────────────────────────

    def _leer_bascula(self, row: int, spin: QDoubleSpinBox) -> None:
        """Lee el peso de la báscula y actualiza el spin de la fila dada."""
        if self._hw_service is None:
            return
        try:
            peso = self._hw_service.read_scale()
        except Exception as exc:
            logger.warning("_leer_bascula: %s", exc)
            peso = 0.0
        if peso > 0:
            spin.setValue(peso)
        else:
            QMessageBox.information(
                self, "Sin lectura",
                "La báscula no devolvió un peso válido.\n"
                "Verifica que el producto esté sobre la báscula y que esté encendida."
            )

    def _on_spin_changed(self, row: int) -> None:
        item      = self._items[row]
        req_qty   = float(item.get("cantidad") or 0)
        price     = float(item.get("precio_unitario") or 0)
        prep_qty  = self._spin_widgets[row].value()
        unit      = item.get("unidad") or ""

        diff = prep_qty - req_qty
        sign = "+" if diff >= 0 else ""
        self._diff_labels[row].setText(f"{sign}{diff:.3g} {unit}")

        exceeded = abs(diff) > self._tolerance_units
        diff_color = Colors.WARNING_BASE if exceeded else Colors.SUCCESS_BASE
        self._diff_labels[row].setStyleSheet(f"color:{diff_color}; font-weight:bold;")
        self._sub_labels[row].setText(f"${prep_qty * price:,.2f}")

        self._update_warnings()

    def _update_all_diffs(self) -> None:
        for row in range(len(self._items)):
            self._on_spin_changed(row)

    def _update_warnings(self) -> None:
        warnings = []
        for row, item in enumerate(self._items):
            req_qty = float(item.get("cantidad") or 0)
            if not req_qty:
                continue
            prep_qty = self._spin_widgets[row].value()
            diff_units = abs(prep_qty - req_qty)
            if diff_units > self._tolerance_units:
                warnings.append(
                    f"⚠️ {item.get('nombre','?')}: diferencia {diff_units:.3g} "
                    f"(tolerancia ±{self._tolerance_units:.1f})"
                )
        self._warn_lbl.setText("\n".join(warnings))

    def _on_confirm(self) -> None:
        exceeded_items = []
        for row, item in enumerate(self._items):
            req_qty = float(item.get("cantidad") or 0)
            prep = self._spin_widgets[row].value()
            if abs(prep - req_qty) > self._tolerance_units:
                exceeded_items.append(item.get("nombre", f"ítem {row+1}"))

        if exceeded_items:
            resp = QMessageBox.question(
                self,
                "Ajuste fuera de tolerancia",
                f"Los siguientes productos exceden la tolerancia permitida "
                f"(±{self._tolerance_units:.1f} unidades):\n"
                + "\n".join(f"  • {n}" for n in exceeded_items)
                + "\n\nEl ajuste supera la tolerancia permitida.\n"
                  "Se enviará una solicitud al cliente por WhatsApp.\n"
                  "El pedido quedará bloqueado hasta que el cliente acepte o rechace.\n\n"
                  "¿Confirmar de todas formas?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if resp != QMessageBox.Yes:
                return

        self.accept()

    def get_adjustments(self) -> list:
        """Return list of {item_id, prepared_qty, adjustment_reason}."""
        reason = self.txt_reason.text().strip()
        return [
            {
                "item_id":          item["id"],
                "item_name":        item.get("nombre", ""),
                "prepared_qty":     self._spin_widgets[row].value(),
                "requested_qty":    float(item.get("cantidad") or 0),
                "unit_price":       float(item.get("precio_unitario") or 0),
                "unit":             item.get("unidad") or "",
                "adjustment_reason": reason,
            }
            for row, item in enumerate(self._items)
        ]


class ModuloDelivery(QWidget, RefreshMixin):
    def __init__(self, conexion_o_container, usuario="admin", parent=None):
        super().__init__(parent)
        # Accept either AppContainer or direct db connection
        if hasattr(conexion_o_container, 'db'):
            self.container = conexion_o_container
            self.conexion  = conexion_o_container.db
        else:
            self.container = None
            self.conexion  = conexion_o_container
        self.usuario = usuario
        self.sucursal_id: int = 0
        self.sucursal_nombre: str = ""
        self.rol: str = ""
        self.delivery_service = DeliveryService(self.conexion)
        self.driver_service = DriverService(self.conexion)
        self._pedidos_cache = []
        self._seen_notification_keys: set[str] = set()
        self._last_notif_rowid: int = 0
        self._init_ui()
        self._init_tables()
        # Wire toast channel so notification service can show toasts
        try:
            from notifications.toast_channel import set_toast_fn
            _lvl_map = {
                "info": Toast.info, "success": Toast.success,
                "warning": Toast.warning, "error": Toast.warning,
            }
            set_toast_fn(
                lambda parent, title, body, level="info":
                    _lvl_map.get(level, Toast.info)(self, title, body),
                self,
            )
        except Exception:
            pass
        # EventBus: reactive reload on pedido events
        try:
            from core.events.event_bus import get_bus
            _bus = get_bus()
            for event in ("PEDIDO_NUEVO", "PEDIDO_ACTUALIZADO",
                          "VENTA_COMPLETADA", "DELIVERY_UPDATE"):
                try:
                    _bus.subscribe(
                        event,
                        lambda _p, _s=self: (
                            _s.cargar_pedidos()
                            if _s.isVisible() else None
                        ),
                        label=f"delivery.refresh.{event}",
                        priority=-1
                    )
                except Exception:
                    pass
        except Exception:
            pass  # EventBus not available — timers are the fallback

        # 5-min fallback refresh (UI data sync)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.cargar_pedidos)
        self.refresh_timer.start(300_000)

        # 2-min background WA pull (off the critical read path)
        self._wa_pull_timer = QTimer(self)
        self._wa_pull_timer.timeout.connect(self._pull_wa_orders_bg)
        self._wa_pull_timer.start(120_000)
        # 10s inbox polling for visual+sound notifications (deduped by dedupe_key/id)
        self._notif_timer = QTimer(self)
        self._notif_timer.timeout.connect(self._poll_delivery_notifications)
        self._notif_timer.start(10_000)

        self._last_wa_sync_error = ""
        self._last_aux_error = ""
        QTimer.singleShot(0, self._initial_sync_whatsapp_orders)
        QTimer.singleShot(10, self.cargar_pedidos)


    def _pull_wa_orders_bg(self) -> None:
        """Pull pending WhatsApp orders in background and refresh if new data arrives."""
        if not self.isVisible():
            return
        try:
            before = len(self._pedidos_cache)
            self.delivery_service.pull_orders_from_whatsapp()
            after_check = self.delivery_service.list_orders()
            if len(after_check) != before:
                QTimer.singleShot(0, lambda: self.cargar_pedidos(silent=True))
        except Exception as exc:
            logger.debug("_pull_wa_orders_bg: %s", exc)
            self._last_wa_sync_error = str(exc)

    def _initial_sync_whatsapp_orders(self) -> None:
        """Attempt an initial WA sync before first visual load; never break UI."""
        try:
            self.delivery_service.pull_orders_from_whatsapp()
            self._last_wa_sync_error = ""
        except Exception as exc:
            self._last_wa_sync_error = str(exc)
            logger.debug("_initial_sync_whatsapp_orders: %s", exc)

    def _set_empty_state_message(self, title: str, message: str) -> None:
        try:
            self._empty.lbl_title.setText(title)
            self._empty.lbl_message.setText(message)
        except Exception:
            pass

    def _count_pending_whatsapp_sales(self) -> int:
        """Best-effort diagnostic count: ventas WA pending that may still require sync."""
        return _DeliveryQueryService(self.conexion).count_pending_whatsapp_sales()

    # ── Interfaz de sesión — compatible con SessionManager ────────────────
    def set_sesion(self, usuario: str, rol: str) -> None:
        self.usuario = usuario
        if hasattr(self, "_on_sesion_change"):
            try: self._on_sesion_change(usuario, rol)
            except Exception: pass

    def set_usuario_actual(self, usuario: str, rol: str) -> None:
        self.set_sesion(usuario, rol)

    def set_sucursal(self, sucursal_id: int, sucursal_nombre: str = "") -> None:
        self.sucursal_id = sucursal_id
        self.sucursal_nombre = sucursal_nombre

    def cerrar_sesion(self) -> None:
        self.usuario = ""


    def _init_ui(self):
        layout = QVBoxLayout(self)
        # Header
        header = QHBoxLayout()
        title = QLabel("🚚 Pedidos y Entregas"); title.setObjectName("heading")
        self._lbl_wa_status = QLabel("WhatsApp: verificando…")
        self._lbl_wa_status.setObjectName("caption")
        self._lbl_oper_context = QLabel("")
        self._lbl_oper_context.setObjectName("caption")
        btn_nuevo = create_success_button(self, "+ Nuevo Pedido", "Crear nuevo pedido de delivery")
        btn_nuevo.clicked.connect(self.nuevo_pedido)
        btn_driver = create_secondary_button(self, "Gestionar Repartidores", "Administrar repartidores disponibles")
        btn_driver.clicked.connect(self.gestionar_drivers)
        # v13.30: Corte de caja por repartidor
        btn_corte = create_warning_button(self, "💰 Corte Repartidor", "Corte de caja: cuánto efectivo debe entregar cada repartidor")
        btn_corte.clicked.connect(self._corte_repartidor)
        btn_hist = create_secondary_button(self, "📋 Historial", "Historial de cortes y entregas")
        btn_hist.clicked.connect(self._historial_cortes)

        self.btn_auto_assign = create_primary_button(self, "🤖 Auto-Asignar", "Asigna automáticamente todos los pedidos pendientes al repartidor disponible más cercano")
        self.btn_auto_assign.clicked.connect(self._auto_asignar_todos)
        # Configurable: se deshabilita si feature_flag 'delivery_auto_asign' está off
        try:
            habilitado = self.container.feature_flag_service.is_enabled('delivery_auto_asign', 1) if hasattr(self.container, 'feature_flag_service') else True
            self.btn_auto_assign.setVisible(habilitado)
        except Exception:
            pass
        btn_refresh = create_secondary_button(self, "🔄 Actualizar", "Recargar lista de pedidos")
        btn_refresh.clicked.connect(self.cargar_pedidos)
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)
        title_box.addWidget(title)
        title_box.addWidget(self._lbl_oper_context)
        header.addLayout(title_box)
        header.addStretch()
        header.addWidget(self._lbl_wa_status)
        header.addWidget(btn_nuevo); header.addWidget(btn_driver)
        header.addWidget(btn_corte); header.addWidget(btn_hist)
        header.addWidget(self.btn_auto_assign); header.addWidget(btn_refresh)
        layout.addLayout(header)

        # ── KPI Stats bar ─────────────────────────────────────────────────
        self._kpi: dict = {}
        kpi_defs = [
            ("nuevos", "Nuevos", "🆕", "warning"),
            ("preparacion", "En preparación", "👨‍🍳", "info"),
            ("reparto", "Reparto", "🛵", "primary"),
            ("programados", "Programados", "🗓️", "primary"),
            ("ajustes", "Ajustes pendientes", "⚖️", "danger"),
            ("retrasados", "Retrasados", "⏰", "danger"),
        ]
        kpi_row = QWidget(self)
        kpi_bar = QHBoxLayout(kpi_row)
        kpi_bar.setContentsMargins(0, 0, 0, 0)
        kpi_bar.setSpacing(Spacing.SM)
        for key, title_txt, icono, variant in kpi_defs:
            card = KPICard(title_txt, "—", icono, variant)
            self._kpi[key] = card
            kpi_bar.addWidget(card)
        self._wire_kpi_interactions()
        layout.addWidget(kpi_row)

        # ── Quick-filter status tabs (Todos | Nuevos | En proceso | Listos | Entregados) ──
        self._filter_tab_defs = [
            ("Todos", None, Colors.TEXT_SECONDARY),
            ("Mostrador", "counter", Colors.INFO_BASE),
            ("Reparto", "delivery", Colors.ACCENT_BASE),
            ("Programados", "scheduled", Colors.WARNING_BASE),
            ("Ajustes pendientes", "ajustes", Colors.DANGER_BASE),
            ("Historial", "historial", Colors.SUCCESS_BASE),
        ]
        self._filter_tab_btns: dict = {}
        tabs_bar = QHBoxLayout()
        tabs_bar.setSpacing(4)
        for tab_label, _tab_estado, tab_color in self._filter_tab_defs:
            tb = QPushButton(tab_label)
            tb.setCheckable(True)
            tb.setFixedHeight(28)
            tb.setStyleSheet(
                f"QPushButton {{ border:1px solid {tab_color}; border-radius:5px;"
                f" padding:2px 10px; color:{tab_color}; background:transparent; font-size:11px; }}"
                f"QPushButton:checked {{ background:{tab_color}; color:#000; font-weight:600; }}"
            )
            tb.clicked.connect(lambda _c, lbl=tab_label: self._on_filter_tab(lbl))
            self._filter_tab_btns[tab_label] = tb
            tabs_bar.addWidget(tb)
        self._filter_tab_btns["Todos"].setChecked(True)
        self._scheduled_window_combo = create_combo(
            self,
            ["Hoy", "Mañana", "Esta semana", "Próximos 30 días", "Todos"],
            "Ventana de pedidos programados",
        )
        self._scheduled_window_combo.setFixedHeight(28)
        self._scheduled_window_combo.hide()
        self._scheduled_window_combo.currentTextChanged.connect(lambda _t: self.cargar_pedidos(silent=True))
        tabs_bar.addWidget(self._scheduled_window_combo)
        tabs_bar.addStretch()
        self.lbl_stats = QLabel()
        self.lbl_stats.setObjectName("caption")
        tabs_bar.addWidget(self.lbl_stats)
        layout.addLayout(tabs_bar)

        # Hidden combo drives the actual query — tabs sync into it
        self.combo_filtro = create_combo(
            self,
            [
                "Todos", "counter", "delivery", "scheduled", "ajustes", "historial",
                "pendiente", "preparacion", "en_ruta", "entregado", "cancelado",
            ],
            "Seleccionar estado para filtrar"
        )
        self.combo_filtro.hide()
        self.combo_filtro.currentTextChanged.connect(self.cargar_pedidos)
        # ── Filtros rápidos (Fase 9) ───────────────────────────────────────
        filtros_row = QHBoxLayout()
        filtros_row.setSpacing(6)
        self._txt_busqueda = create_input(self, "Buscar folio, cliente o teléfono")
        self._txt_busqueda.setClearButtonEnabled(True)
        self._txt_busqueda.textChanged.connect(lambda _t: self.cargar_pedidos(silent=True))
        self._flt_estado = QComboBox()
        self._flt_estado.setPlaceholderText("Estado")
        for _lbl, _val in [("Todos", None), ("Pendiente", "pendiente"), ("Preparación", "preparacion"), ("En ruta", "en_ruta"), ("Entregado", "entregado"), ("Cancelado", "cancelado")]:
            self._flt_estado.addItem(_lbl, _val)
        self._flt_estado.currentIndexChanged.connect(lambda _i: self.cargar_pedidos(silent=True))
        self._flt_flujo = QComboBox()
        self._flt_flujo.setPlaceholderText("Flujo")
        for _lbl, _val in [("Todos", None), ("Mostrador", "counter"), ("Delivery", "delivery"), ("Programado", "scheduled")]:
            self._flt_flujo.addItem(_lbl, _val)
        self._flt_flujo.currentIndexChanged.connect(lambda _i: self.cargar_pedidos(silent=True))
        self._flt_origen = QComboBox()
        self._flt_origen.setPlaceholderText("Origen")
        for _lbl, _val in [("Todos", None), ("WhatsApp", "whatsapp"), ("Mostrador", "counter"), ("Cotización", "quote"), ("Programado", "scheduled")]:
            self._flt_origen.addItem(_lbl, _val)
        self._flt_origen.currentIndexChanged.connect(lambda _i: self.cargar_pedidos(silent=True))
        self._flt_fecha = QDateEdit(QDate.currentDate())
        self._flt_fecha.setCalendarPopup(True)
        self._flt_fecha.setDisplayFormat("yyyy-MM-dd")
        self._flt_fecha.dateChanged.connect(lambda _d: self.cargar_pedidos(silent=True))
        self._flt_fecha_activo = QPushButton("Fecha")
        self._flt_fecha_activo.setCheckable(True)
        self._flt_fecha_activo.setChecked(False)
        self._flt_fecha_activo.toggled.connect(lambda _v: self.cargar_pedidos(silent=True))
        self._flt_ajustes = QPushButton("Solo ajustes pendientes")
        self._flt_ajustes.setCheckable(True)
        self._flt_ajustes.setChecked(False)
        self._flt_ajustes.toggled.connect(lambda _v: self.cargar_pedidos(silent=True))
        filtros_row.addWidget(self._txt_busqueda, 3)
        filtros_row.addWidget(self._flt_estado, 1)
        filtros_row.addWidget(self._flt_flujo, 1)
        filtros_row.addWidget(self._flt_origen, 1)
        filtros_row.addWidget(self._flt_fecha_activo, 0)
        filtros_row.addWidget(self._flt_fecha, 1)
        filtros_row.addWidget(self._flt_ajustes, 0)
        layout.addLayout(filtros_row)
        self._loading = LoadingIndicator("Cargando pedidos delivery…", self)
        self._loading.hide()
        layout.addWidget(self._loading)
        self._empty = EmptyStateWidget(
            "Sin pedidos",
            "No hay pedidos de delivery para el filtro seleccionado.",
            "🛵",
            self,
        )
        self._empty.hide()
        layout.addWidget(self._empty)

        # ── Toggle Lista / Kanban ─────────────────────────────────────────
        self._vista_actual = "lista"
        toggle_bar = QHBoxLayout()
        toggle_bar.setSpacing(0)

        self._btn_vista_lista = QPushButton("≡  Lista")
        self._btn_vista_lista.setFixedHeight(28)
        self._btn_vista_lista.setCheckable(True)
        self._btn_vista_lista.setChecked(True)
        self._btn_vista_lista.setStyleSheet(self._qss_toggle_activo())
        self._btn_vista_lista.clicked.connect(lambda: self._toggle_vista("lista"))

        self._btn_vista_kanban = QPushButton("⊞  Kanban")
        self._btn_vista_kanban.setFixedHeight(28)
        self._btn_vista_kanban.setCheckable(True)
        self._btn_vista_kanban.setChecked(False)
        self._btn_vista_kanban.setStyleSheet(self._qss_toggle_inactivo())
        self._btn_vista_kanban.clicked.connect(lambda: self._toggle_vista("kanban"))

        toggle_bar.addWidget(self._btn_vista_lista)
        toggle_bar.addWidget(self._btn_vista_kanban)
        toggle_bar.addStretch()
        layout.addLayout(toggle_bar)

        # ── Stacked: index 0 = Lista, index 1 = Kanban ────────────────────
        from PyQt5.QtWidgets import QStackedWidget as _SW
        self._stack = _SW()

        # — Lista —
        self._stack.addWidget(self._build_lista_view())

        # — Kanban —
        kanban_widget = QWidget()
        kanban_layout = QVBoxLayout(kanban_widget)
        kanban_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Horizontal)
        # self.columnas is keyed by column index (0-3), not by legacy status string.
        # Use _STATUS_TO_COL to find the column for any legacy DB status value.
        self.columnas = {}
        from PyQt5.QtWidgets import QScrollArea
        for col_idx, (col_title, _col_statuses) in enumerate(_KANBAN_COLUMNS):
            col_widget = QWidget()
            col_layout = QVBoxLayout(col_widget)
            col_layout.setContentsMargins(0, 0, 0, 0)
            col_layout.setSpacing(0)
            color = _KANBAN_COL_COLORS[col_idx]
            titulo = QLabel(col_title)
            titulo.setObjectName("subheading")
            titulo.setStyleSheet(
                f"color: {color}; font-weight: bold; padding: {Spacing.SM};"
                f" border-bottom: 2px solid {color};")
            col_layout.addWidget(titulo)
            scroll_content = QWidget()
            self.columnas[col_idx] = QVBoxLayout(scroll_content)
            self.columnas[col_idx].setContentsMargins(4, 4, 4, 4)
            self.columnas[col_idx].setSpacing(4)
            self.columnas[col_idx].addStretch()
            scroll_area = QScrollArea()
            scroll_area.setWidget(scroll_content)
            scroll_area.setWidgetResizable(True)
            scroll_area.setFrameShape(QFrame.NoFrame)
            scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            col_layout.addWidget(scroll_area, 1)
            splitter.addWidget(col_widget)
        kanban_layout.addWidget(splitter)
        self._stack.addWidget(kanban_widget)

        layout.addWidget(self._stack, 1)

        # ── Botón de mapa de repartidores ─────────────────────────────────
        btn_mapa = create_success_button(self, "🗺️ Ver Mapa de Repartidores", "Ver ubicación de repartidores en tiempo real")
        btn_mapa.setObjectName("btnMapa")
        btn_mapa.setStyleSheet(f"margin-top: {Spacing.SM};")
        btn_mapa.clicked.connect(self._abrir_mapa)
        layout.addWidget(btn_mapa)

    def _abrir_mapa(self):
        """Abre el mapa Leaflet de repartidores en una ventana flotante."""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("🗺️ Mapa de Repartidores en Tiempo Real")
        dlg.resize(820, 560)
        lay = QVBoxLayout(dlg)

        try:
            from PyQt5.QtWebEngineWidgets import QWebEngineView
            view = QWebEngineView()
            # Build drivers data + pedidos geolocalizados
            try:
                rows = _DeliveryQueryService(self.conexion).get_driver_locations()
                drivers_js = str(rows)
            except Exception:
                drivers_js = "[]"
            pedidos_js = str([
                {
                    "id": p.get("id"),
                    "cliente": p.get("cliente_nombre", ""),
                    "direccion": p.get("direccion", ""),
                    "estado": p.get("estado", "pendiente"),
                    "lat": float(p.get("lat") or 20.967),
                    "lng": float(p.get("lng") or -89.623),
                }
                for p in (self._pedidos_cache or [])
                if p.get("lat") is not None and p.get("lng") is not None
            ])

            html = f"""<!DOCTYPE html><html><head>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>body{{margin:0}}#map{{height:100vh}}</style>
</head><body><div id="map"></div><script>
var map = L.map('map').setView([20.967, -89.623], 13);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
    {{attribution:'© OpenStreetMap'}}).addTo(map);
var drivers = {drivers_js};
var pedidos = {pedidos_js};
var icon = L.icon({{iconUrl:'https://cdn-icons-png.flaticon.com/32/3050/3050553.png',iconSize:[32,32]}});
drivers.forEach(function(d){{
    L.marker([d.lat,d.lng],{{icon:icon}}).addTo(map)
     .bindPopup('<b>' + d.name + '</b>').openPopup();
}});
pedidos.forEach(function(p){{
    L.circleMarker([p.lat,p.lng],{{radius:8,color:'#ef4444'}}).addTo(map)
      .bindPopup('Pedido #' + p.id + '<br/>' + p.estado + '<br/>' + p.cliente + '<br/>' + p.direccion);
}});
if(drivers.length===0){{
    L.marker([20.967,-89.623]).addTo(map)
     .bindPopup('Sin repartidores activos').openPopup();
}}
</script></body></html>"""
            view.setHtml(html)
            lay.addWidget(view)
        except ImportError:
            from PyQt5.QtWidgets import QLabel
            lbl = QLabel(
                "⚠️ PyQtWebEngine no instalado.\n\n"
                "Para ver el mapa instala:\n  pip install PyQtWebEngine")
            lbl.setObjectName("caption")
            lay.addWidget(lbl)

        dlg.exec_()

    # ═══════════════════════════════════════════════════════════════════════
    # TOGGLE LISTA / KANBAN
    # ═══════════════════════════════════════════════════════════════════════
    @staticmethod
    def _qss_toggle_activo() -> str:
        return (f"background:{Colors.PRIMARY_BASE}; color:white; border:1px solid {Colors.PRIMARY_BASE};"
                f" border-radius:5px; padding:3px 14px; font-weight:600; font-size:12px;")

    @staticmethod
    def _qss_toggle_inactivo() -> str:
        return (f"background:transparent; color:{Colors.NEUTRAL.SLATE_400};"
                f" border:1px solid {Colors.NEUTRAL.SLATE_700};"
                f" border-radius:5px; padding:3px 14px; font-size:12px;")

    def _toggle_vista(self, vista: str) -> None:
        self._vista_actual = vista
        self._stack.setCurrentIndex(0 if vista == "lista" else 1)
        self._btn_vista_lista.setChecked(vista == "lista")
        self._btn_vista_kanban.setChecked(vista == "kanban")
        self._btn_vista_lista.setStyleSheet(
            self._qss_toggle_activo() if vista == "lista" else self._qss_toggle_inactivo())
        self._btn_vista_kanban.setStyleSheet(
            self._qss_toggle_activo() if vista == "kanban" else self._qss_toggle_inactivo())

    # ── Filter tab helpers ────────────────────────────────────────────────
    def _on_filter_tab(self, tab_label: str) -> None:
        for lbl, btn in self._filter_tab_btns.items():
            btn.setChecked(lbl == tab_label)
        self._scheduled_window_combo.setVisible(tab_label == "Programados")
        estado_map = {lbl: e for lbl, e, _ in self._filter_tab_defs}
        target = estado_map.get(tab_label)
        target_txt = "Todos" if target is None else target
        idx = self.combo_filtro.findText(target_txt)
        if idx >= 0:
            self.combo_filtro.setCurrentIndex(idx)
        else:
            QTimer.singleShot(0, lambda: self.cargar_pedidos(silent=True))

    def _wire_kpi_interactions(self) -> None:
        """Make KPI cards clickable to filter operational tabs."""
        from PyQt5.QtCore import Qt as _Qt
        mapping = {
            "nuevos": "Todos",
            "preparacion": "Todos",
            "reparto": "Reparto",
            "programados": "Programados",
            "ajustes": "Ajustes pendientes",
            "retrasados": "Historial",
        }
        for key, card in self._kpi.items():
            card.setCursor(_Qt.PointingHandCursor)
            tab_label = mapping.get(key, "Todos")
            card.mousePressEvent = (lambda _event, lbl=tab_label: self._on_filter_tab(lbl))

    def _get_branch_id_for_counts(self) -> int:
        try:
            return int(getattr(self, "sucursal_id", 1) or 1)
        except Exception:
            return 1

    def _update_filter_tabs(self, pedidos: list, counts_estado: dict) -> None:
        """Refresh badge numbers on tab buttons after each load.

        For operational tabs we compute counts from workflow/status context.
        For legacy status tabs we keep `counts_estado`.
        """
        estado_map = {lbl: e for lbl, e, _ in self._filter_tab_defs}
        total = len(pedidos)
        for tab_label, btn in self._filter_tab_btns.items():
            tab_key = estado_map.get(tab_label)
            if tab_key is None:
                n = total
            elif tab_key in ESTADOS:
                n = counts_estado.get(tab_key, 0)
            else:
                n = sum(1 for p in pedidos if _matches_operational_tab(p, tab_key))
            btn.setText(f"{tab_label} ({n})" if n else tab_label)

    def _update_kpi(self, pedidos: list) -> None:
        """Update KPI stat cards with persistent + in-memory operational counts."""
        from datetime import date as _date
        hoy = _date.today().isoformat()
        counts = OrderBadgeService(self.conexion).get_badge_counts(
            branch_id=self._get_branch_id_for_counts()
        )
        nuevos = sum(1 for p in pedidos if str(p.get("estado") or "").lower() == "pendiente")
        preparacion = sum(1 for p in pedidos if str(p.get("estado") or "").lower() == "preparacion")
        reparto = sum(1 for p in pedidos if str(p.get("estado") or "").lower() == "en_ruta")
        programados = int(counts.get("orders_scheduled", 0))
        ajustes = int(counts.get("adjustments_pending", 0))
        retrasados = sum(
            1 for p in pedidos
            if str(p.get("estado") or "").lower() in ("pendiente", "preparacion", "en_ruta")
            and str(p.get("fecha_actualizacion") or p.get("fecha", ""))[:10] < hoy
        )
        self._kpi["nuevos"].set_valor(str(nuevos))
        self._kpi["preparacion"].set_valor(str(preparacion))
        self._kpi["reparto"].set_valor(str(reparto))
        self._kpi["programados"].set_valor(str(programados))
        self._kpi["ajustes"].set_valor(str(ajustes))
        self._kpi["retrasados"].set_valor(str(retrasados))

    # ═══════════════════════════════════════════════════════════════════════
    # VISTA LISTA + PANEL DETALLE
    # ═══════════════════════════════════════════════════════════════════════
    def _build_lista_view(self) -> QWidget:
        """Construye la vista Lista: panel izquierdo (lista) + panel derecho (detalle)."""
        widget = QWidget()
        splitter = QSplitter(Qt.Horizontal, widget)
        outer = QHBoxLayout(widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)

        # ── Panel izquierdo — lista de pedidos ───────────────────────────
        left = QWidget()
        left.setMinimumWidth(240)
        left.setMaximumWidth(280)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        self._lst_pedidos = QListWidget()
        self._lst_pedidos.setObjectName("listaPedidos")
        self._lst_pedidos.setStyleSheet("""
            QListWidget { border:none; }
            QListWidget::item { border-bottom:1px solid palette(mid); padding:0; }
            QListWidget::item:selected { background:palette(highlight); }
            QListWidget::item:hover { background:palette(midlight); }
        """)
        self._lst_pedidos.currentRowChanged.connect(self._on_lista_seleccion)
        left_lay.addWidget(self._lst_pedidos)
        splitter.addWidget(left)

        # ── Panel derecho — detalle ──────────────────────────────────────
        self._detalle_widget = QWidget()
        detalle_lay = QVBoxLayout(self._detalle_widget)
        detalle_lay.setContentsMargins(16, 12, 16, 12)
        detalle_lay.setSpacing(10)

        # — Cabecera del pedido —
        self._det_header = QLabel("Selecciona un pedido")
        self._det_header.setObjectName("heading")
        self._det_header.setWordWrap(True)
        detalle_lay.addWidget(self._det_header)

        grp_general = QGroupBox("General")
        grp_general_lay = QVBoxLayout(grp_general)
        self._det_sub = QLabel("")
        self._det_sub.setObjectName("caption")
        self._det_sub.setWordWrap(True)
        grp_general_lay.addWidget(self._det_sub)
        detalle_lay.addWidget(grp_general)

        # — Productos —
        grp_items = QGroupBox("Productos del pedido")
        grp_items_lay = QVBoxLayout(grp_items)
        self._det_tabla = QTableWidget(0, 6)
        self._det_tabla.setHorizontalHeaderLabels(["Producto","Solicitado","Preparado","Precio","Subtotal","Estado ajuste"])
        self._det_tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._det_tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self._det_tabla.setMinimumHeight(80)
        self._det_tabla.setMaximumHeight(220)
        self._det_tabla.verticalHeader().setVisible(False)
        grp_items_lay.addWidget(self._det_tabla)
        detalle_lay.addWidget(grp_items)

        # — Notas —
        self._det_notas = QLabel("")
        self._det_notas.setObjectName("textMuted")
        self._det_notas.setWordWrap(True)
        detalle_lay.addWidget(self._det_notas)

        # — Conversación WhatsApp —
        grp_wa = QGroupBox("Conversación WhatsApp")
        grp_wa_lay = QVBoxLayout(grp_wa)
        grp_wa_lay.setContentsMargins(6, 6, 6, 6)
        self._det_wa_txt = QTextEdit()
        self._det_wa_txt.setReadOnly(True)
        self._det_wa_txt.setMaximumHeight(110)
        self._det_wa_txt.setPlaceholderText("Sin conversación registrada")
        self._det_wa_txt.setStyleSheet(
            "font-size:11px; border:none; border-radius:6px;"
        )
        grp_wa_lay.addWidget(self._det_wa_txt)
        detalle_lay.addWidget(grp_wa)

        # — Totales —
        grp_tot = QGroupBox("Totales")
        grp_tot_lay = QVBoxLayout(grp_tot)
        self._det_total = QLabel("")
        self._det_total.setObjectName("subheading")
        grp_tot_lay.addWidget(self._det_total)
        detalle_lay.addWidget(grp_tot)

        # — Historial —
        grp_hist = QGroupBox("Historial")
        grp_hist_lay = QVBoxLayout(grp_hist)
        self._det_historial = QTextEdit()
        self._det_historial.setReadOnly(True)
        self._det_historial.setMaximumHeight(120)
        self._det_historial.setPlaceholderText("Sin historial disponible")
        grp_hist_lay.addWidget(self._det_historial)
        detalle_lay.addWidget(grp_hist)

        # — Acciones contextuales —
        self._det_acciones_layout = QHBoxLayout()
        self._det_acciones_layout.setSpacing(8)
        detalle_lay.addLayout(self._det_acciones_layout)

        detalle_lay.addStretch()
        splitter.addWidget(self._detalle_widget)
        splitter.setSizes([260, 700])
        return widget

    def _on_lista_seleccion(self, row: int) -> None:
        """Popula el panel de detalle cuando el usuario selecciona una fila."""
        if row < 0 or row >= len(self._pedidos_cache):
            return
        self._seleccionar_pedido(self._pedidos_cache[row])

    def _safe_load_order_items(self, order_id, sale_id=None):
        """Carga ítems del pedido con degradación segura por diferencias de esquema."""
        return _DeliveryQueryService(self.conexion).load_order_items(order_id, sale_id)

    def _safe_load_order_history(self, order_id, current_status: str = ""):
        """Carga historial de pedido con fallback legacy."""
        return _DeliveryQueryService(self.conexion).load_order_history(order_id, current_status)

    def _safe_load_whatsapp_conversation(self, order_id, pedido: dict) -> str:
        """Carga conversación WA si existe en DB ERP; si no, entrega fallback no intrusivo."""
        return _DeliveryQueryService(self.conexion).load_whatsapp_conversation(order_id, pedido)

    def _seleccionar_pedido(self, pedido: dict) -> None:
        """Rellena el panel de detalle con los datos del pedido seleccionado."""
        pid    = pedido.get("id", "")
        estado = pedido.get("estado", "pendiente")
        color  = ESTADO_COLOR.get(estado, Colors.TEXT_SECONDARY)

        self._det_header.setText(
            f"<span style='color:{color};font-weight:bold;'>#{pid}</span>"
            f"  —  {pedido.get('cliente_nombre','N/A')}"
        )
        self._det_sub.setText(
            f"Folio: {pedido.get('folio') or pid}\n"
            f"Origen: {pedido.get('source') or pedido.get('origen') or 'whatsapp'}  ·  "
            f"Flujo: {pedido.get('workflow_type') or 'delivery'}\n"
            f"Estado: {estado}  ·  Sucursal: {pedido.get('sucursal_nombre') or self.sucursal_nombre}\n"
            f"📍 {pedido.get('direccion','Sin dirección')}\n"
            f"📞 {pedido.get('cliente_tel','')}  ·  🛵 {pedido.get('driver_nombre','Sin repartidor')}"
        )

        # Cargar ítems desde BD con fallback seguro
        self._det_tabla.setRowCount(0)
        rows = self._safe_load_order_items(pid, pedido.get("venta_id"))
        for i, r in enumerate(rows):
            self._det_tabla.insertRow(i)
            for j, val in enumerate(r):
                cell = QTableWidgetItem(
                    f"${val:.2f}" if j in (3, 4) and isinstance(val, (int, float)) else
                    f"{float(val):.3g}" if j in (1, 2) and val is not None and str(val) != "" else
                    ("Pendiente" if j == 5 and not val else str(val))
                )
                if j == 4:
                    cell.setForeground(QColor(Colors.SUCCESS_BASE))
                self._det_tabla.setItem(i, j, cell)

        notas = pedido.get("notas", "") or ""
        self._det_notas.setText(f"📝 {notas}" if notas else "Sin notas")

        # WA conversation panel
        self._det_wa_txt.clear()
        self._det_wa_txt.setPlainText(self._safe_load_whatsapp_conversation(pid, pedido))

        total = float(pedido.get("total") or 0)
        costo = float(pedido.get("costo_envio") or 0)
        self._det_total.setText(
            f"Total: <b>${total:.2f}</b>  ·  Envío: ${costo:.2f}"
            f"  ·  <span style='color:{color};'>{estado.upper()}</span>"
        )
        self._det_historial.clear()
        self._det_historial.setPlainText(self._safe_load_order_history(pid, estado))

        # Acciones contextuales
        # Limpiar acciones anteriores
        while self._det_acciones_layout.count():
            item = self._det_acciones_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        def _add_btn(label, fn, color_fn):
            b = color_fn(self, label, "")
            b.setFixedHeight(32)
            b.clicked.connect(lambda _, pid=pid, a=label: fn(pid, a))
            self._det_acciones_layout.addWidget(b)

        if bool(int(pedido.get("adjustment_pending") or 0)):
            bloqueo = QLabel("No puedes avanzar este pedido hasta que el cliente acepte o rechace el ajuste.")
            bloqueo.setObjectName("textMuted")
            bloqueo.setWordWrap(True)
            self._det_acciones_layout.addWidget(bloqueo)

        # Detail view action buttons — use same policy as kanban (no logic duplication)
        _style_factory = {
            "success": create_success_button, "primary": create_primary_button,
            "warning": create_warning_button, "danger": create_danger_button,
            "secondary": create_secondary_button,
        }
        # Single route — same function as Kanban cards
        for action in _get_card_actions(pedido):
            icon_text = action.get("icon", "")
            tooltip = action.get("label", "")
            accion = action.get("key", "")
            style = action.get("style", "secondary")
            factory = _style_factory.get(style, create_secondary_button)
            b = factory(self, f"{icon_text} {tooltip}", tooltip)
            b.setFixedHeight(32)
            b.clicked.connect(lambda _, p=pid, a=accion: self.ejecutar_accion(p, a))
            self._det_acciones_layout.addWidget(b)

        self._det_acciones_layout.addStretch()

    def _actualizar_lista_view(self, pedidos: list) -> None:
        """Repopula la QListWidget de la vista lista con los pedidos actuales."""
        def _status_es(raw: str) -> str:
            return {
                "pendiente": "Pendiente",
                "preparacion": "Preparación",
                "en_ruta": "En ruta",
                "entregado": "Entregado",
                "cancelado": "Cancelado",
                "programado": "Programado",
                "scheduled": "Programado",
            }.get((raw or "").strip().lower(), raw or "Pendiente")
        def _workflow_es(raw: str) -> str:
            return {
                "counter": "Mostrador",
                "delivery": "Reparto",
                "scheduled": "Programado",
            }.get((raw or "").strip().lower(), "Reparto")
        self._lst_pedidos.clear()
        for pedido in pedidos:
            estado = pedido.get("estado", "pendiente")
            color  = ESTADO_COLOR.get(estado, Colors.TEXT_SECONDARY)
            pid    = pedido.get("id", "")
            nombre = pedido.get("cliente_nombre", "N/A")
            total  = float(pedido.get("total") or pedido.get("monto_total") or 0)
            flujo  = _workflow_es(str(pedido.get("workflow_type") or "delivery"))
            tel    = str(pedido.get("cliente_tel") or "S/T")

            item = QListWidgetItem()
            item.setData(Qt.UserRole, pedido)
            item.setSizeHint(__import__('PyQt5.QtCore', fromlist=['QSize']).QSize(240, 90))

            # Widget tarjeta compacta
            card = QFrame()
            card.setStyleSheet(
                f"QFrame {{ border-left:3px solid {color};"
                f" background:transparent; padding:6px 10px; }}"
            )
            card_lay = QVBoxLayout(card)
            card_lay.setContentsMargins(8, 4, 8, 4)
            card_lay.setSpacing(2)

            row1 = QHBoxLayout()
            lbl_id = QLabel(f"<b>#{pid}</b>")
            lbl_id.setStyleSheet(f"color:{color}; font-size:11px;")
            lbl_total = QLabel(f"${total:,.2f}")
            lbl_total.setStyleSheet(f"color:{Colors.SUCCESS_BASE}; font-weight:bold; font-size:12px;")
            row1.addWidget(lbl_id)
            row1.addStretch()
            row1.addWidget(lbl_total)

            lbl_nombre = QLabel(nombre)
            lbl_nombre.setStyleSheet("font-weight:600; font-size:12px;")

            row2 = QHBoxLayout()
            lbl_meta = QLabel(f"Tel: {tel}  ·  Flujo: {flujo}")
            lbl_meta.setStyleSheet(f"color:{Colors.NEUTRAL.SLATE_500}; font-size:10px;")
            row2.addWidget(lbl_meta)
            row2.addStretch()

            row3 = QHBoxLayout()
            badge = QLabel(_status_es(str(estado)))
            badge.setStyleSheet(
                f"color:{color}; font-size:9px; font-weight:700;"
                f" border:1px solid {color}; border-radius:4px; padding:1px 5px;")
            if bool(int(pedido.get("adjustment_pending") or 0)):
                adj = QLabel("Ajuste pendiente")
                adj.setStyleSheet(
                    f"color:{Colors.DANGER_BASE}; font-size:9px; font-weight:700;"
                    f" border:1px solid {Colors.DANGER_BASE}; border-radius:4px; padding:1px 5px;")
                row3.addWidget(adj)
            row3.addStretch()
            row3.addWidget(badge)

            card_lay.addLayout(row1)
            card_lay.addWidget(lbl_nombre)
            card_lay.addLayout(row2)
            card_lay.addLayout(row3)

            self._lst_pedidos.addItem(item)
            self._lst_pedidos.setItemWidget(item, card)

    def _auto_asignar_todos(self):
        """Asigna automáticamente todos los pedidos pendientes sin repartidor."""
        try:
            from delivery.asignacion_repartidor import AsignacionRepartidor
            asign = AsignacionRepartidor(self.conexion)
            _qs = _DeliveryQueryService(self.conexion)
            pending_ids = _qs.get_pending_unassigned_order_ids(self.sucursal_id)
            if not pending_ids:
                Toast.info(self, "Auto-Asignación", "No hay pedidos pendientes sin repartidor.")
                return
            asignados = 0
            for order_id in pending_ids:
                rep_id = asign.asignar_automatico(order_id)
                if rep_id:
                    asignados += 1
            Toast.success(
                self, "✅ Auto-Asignación",
                f"{asignados}/{len(pending_ids)} pedidos asignados.",
            )
            QTimer.singleShot(0, lambda: self.cargar_pedidos(silent=True))
        except Exception as e:
            # [spj-dedup] from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", str(e))

    def _init_tables(self):
        # Schema creation/alteration moved to repositories and migrations.
        # Kept as a compatibility hook so legacy callers do not break.
        return
    def _refresh_operational_header(self) -> None:
        """Update contextual header: branch + WhatsApp status + last refresh."""
        from datetime import datetime as _dt
        branch_name = str(getattr(self, "sucursal_nombre", "") or "Sucursal actual")
        branch_id = self._get_branch_id_for_counts()
        counts = OrderBadgeService(self.conexion).get_badge_counts(branch_id=branch_id)
        unread = int(counts.get("notifications_unread", 0))
        wa_ok = "activo ●" if unread >= 0 else "sin datos"
        self._lbl_wa_status.setText(f"WhatsApp {wa_ok}")
        self._lbl_oper_context.setText(
            f"Sucursal: {branch_name} · Última act: {_dt.now().strftime('%H:%M:%S')}"
        )

    @staticmethod
    def _infer_workflow_for_ui(pedido: dict) -> str:
        return _infer_workflow_for_ui_fn(pedido)

    def _matches_advanced_filters(self, pedido: dict) -> bool:
        q = str(self._txt_busqueda.text() or "").strip().lower()
        if q:
            blob = " ".join([
                str(pedido.get("folio") or pedido.get("id") or ""),
                str(pedido.get("cliente_nombre") or ""),
                str(pedido.get("cliente_tel") or ""),
            ]).lower()
            if q not in blob:
                return False
        estado = self._flt_estado.currentData()
        if estado is not None and str(pedido.get("estado") or "").strip().lower() != estado:
            return False
        flujo = self._flt_flujo.currentData()
        if flujo is not None and self._infer_workflow_for_ui(pedido) != flujo:
            return False
        origen = self._flt_origen.currentData()
        if origen is not None:
            src = str(pedido.get("source") or pedido.get("origen") or "").strip().lower()
            if src != origen:
                return False
        if self._flt_ajustes.isChecked() and not bool(int(pedido.get("adjustment_pending") or 0)):
            return False
        if self._flt_fecha_activo.isChecked():
            d = self._flt_fecha.date().toString("yyyy-MM-dd")
            fecha_txt = str(pedido.get("fecha") or pedido.get("created_at") or pedido.get("fecha_solicitud") or "")
            if d not in fecha_txt:
                return False
        return True

    def cargar_pedidos(self, silent: bool = False):
        filtro = self.combo_filtro.currentText()
        scheduled_window_map = {
            "Hoy": "today",
            "Mañana": "tomorrow",
            "Esta semana": "week",
            "Próximos 30 días": "month",
            "Todos": "all",
        }
        scheduled_window = scheduled_window_map.get(self._scheduled_window_combo.currentText(), "all")
        if not silent:
            self._loading.show()
        kanban_visibles = 0
        lista_count = 0
        # Clear kanban columns (columnas is keyed by col_idx 0-3)
        for _col_idx, col_layout in self.columnas.items():
            while col_layout.count() > 1:
                item = col_layout.takeAt(0)
                if item.widget(): item.widget().deleteLater()
        try:
            filtro_repo = filtro if filtro in ESTADOS else None
            pedidos = self.delivery_service.list_orders(filtro_repo)
            self._pedidos_cache = pedidos

            # Build lista-view items
            lista_pedidos = [
                p for p in pedidos
                if _matches_operational_tab(p, None if filtro == "Todos" else filtro)
                and (filtro != "scheduled" or _matches_scheduled_window(p, scheduled_window))
                and self._matches_advanced_filters(p)
            ]
            lista_count = len(lista_pedidos)
            self._actualizar_lista_view(lista_pedidos)

            counts = {e: 0 for e in ESTADOS}
            for p in pedidos:
                estado = p.get("estado", "pendiente")
                counts[estado] = counts.get(estado, 0) + 1
                if not _matches_operational_tab(p, None if filtro == "Todos" else filtro):
                    continue
                if filtro == "scheduled" and not _matches_scheduled_window(p, scheduled_window):
                    continue
                if not self._matches_advanced_filters(p):
                    continue
                col_idx = _STATUS_TO_COL.get(estado)
                if col_idx is not None:
                    card = TarjetaPedido(p)
                    card.accion_requerida.connect(self.ejecutar_accion)
                    self.columnas[col_idx].insertWidget(self.columnas[col_idx].count() - 1, card)
                    kanban_visibles += 1

            self.lbl_stats.setText(
                f"Pedidos activos: {sum(counts.get(e, 0) for e in ['pendiente', 'preparacion', 'en_ruta'])} · Total cargados: {len(lista_pedidos)}"
            )
            logger.info("Delivery load: raw=%s filtered=%s filtro=%s", len(pedidos), len(lista_pedidos), filtro)
            self._safe_update_filter_tabs(pedidos, counts)
            self._safe_update_kpi(pedidos)
            self._safe_refresh_operational_header()
            self._safe_poll_delivery_notifications()
            # Empty-state diagnostic (non-intrusive).
            if lista_count == 0:
                pending_wa_sales = self._count_pending_whatsapp_sales()
                if pending_wa_sales > 0 and len(pedidos) == 0:
                    self._set_empty_state_message(
                        "Sin pedidos importados",
                        "Hay pedidos WhatsApp en ventas pendientes de importar. Pulsa Actualizar.",
                    )
                elif self._last_wa_sync_error:
                    self._set_empty_state_message(
                        "Sin conexión a WhatsApp",
                        "No se pudo consultar el microservicio WhatsApp. Se mostrarán pedidos ya importados.",
                    )
                else:
                    self._set_empty_state_message(
                        "Sin pedidos",
                        "No hay pedidos para el filtro seleccionado.",
                    )
                self._empty.setVisible(True)
            else:
                self._empty.setVisible(False)
        except Exception as e:
            logger.error("cargar_pedidos: %s", e)
            self._last_aux_error = str(e)
            self._set_empty_state_message(
                "Error de carga",
                "No se pudieron cargar algunos datos auxiliares. Intenta actualizar.",
            )
            self._empty.setVisible(True)
        finally:
            if not silent:
                self._loading.hide()

    def _poll_delivery_notifications(self) -> None:
        """Show in-module alerts for new delivery-related inbox notifications.

        Sound is emitted only once per new dedupe key (or inbox row id fallback).
        """
        branch_id = self._get_branch_id_for_counts()
        rows = _DeliveryQueryService(self.conexion).get_notification_inbox(
            branch_id, self._last_notif_rowid
        )
        if rows is None:
            return
        if not rows:
            return
        for r in rows:
            notif_id = int(r[0] or 0)
            title = str(r[1] or "Notificación de pedidos")
            body = str(r[2] or "")
            notif_type = str(r[3] or "").lower()
            dedupe_key = str(r[4] or "").strip() or f"inbox:{notif_id}"
            order_id = r[5]
            self._last_notif_rowid = max(self._last_notif_rowid, notif_id)
            if dedupe_key in self._seen_notification_keys:
                continue
            self._seen_notification_keys.add(dedupe_key)
            # Keep alert surface focused on requested delivery events
            is_delivery_event = any(k in notif_type for k in (
                "delivery", "pedido", "scheduled", "ajuste", "anticipo", "cotizacion"
            )) or ("pedido" in title.lower())
            if not is_delivery_event:
                continue
            Toast.info(self, title, body or "Tienes una notificación nueva.")
            try:
                from ui.sonido_alerta import SonidoAlerta
                SonidoAlerta.play_alert()
            except Exception:
                pass
            if order_id:
                logger.info("Notificación delivery recibida para pedido=%s dedupe=%s", order_id, dedupe_key)

    def ejecutar_accion(self, pedido_id: int, accion: str):
        try:
            if accion == "imprimir":
                from core.services.ticket_printer_service import TicketPrinterService
                printer = TicketPrinterService(self.conexion, preview_mode=True)
                printer.print_both(pedido_id)
                return
            elif accion == "reactivar":
                _qs = _DeliveryQueryService(self.conexion)
                order_raw = _qs.get_order_raw(pedido_id)
                if not order_raw:
                    return
                if order_raw.get("estado") not in ("entregado", "cancelado"):
                    QMessageBox.information(self, "Reactivar", "Solo pedidos entregados o cancelados pueden reactivarse.")
                    return
                reply = QMessageBox.question(
                    self, "Reactivar pedido",
                    f"¿Reactivar pedido #{pedido_id} como 'pendiente'?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    return
                self.delivery_service.update_status(pedido_id, "pendiente", usuario=self.usuario)
                QTimer.singleShot(0, lambda: self.cargar_pedidos(silent=True))
                return
            elif accion == "ver_detalle":
                # Show read-only detail dialog for delivered orders
                _qs = _DeliveryQueryService(self.conexion)
                order_raw = _qs.get_order_raw(pedido_id)
                if not order_raw:
                    return
                from PyQt5.QtWidgets import QTextEdit
                dlg_det = QDialog(self)
                dlg_det.setWindowTitle(f"Detalle Pedido #{pedido_id}")
                dlg_det.setMinimumSize(400, 300)
                v = QVBoxLayout(dlg_det)
                txt = QTextEdit()
                txt.setReadOnly(True)
                content = "\n".join(f"{k}: {v2}" for k, v2 in order_raw.items() if v2 is not None)
                txt.setPlainText(content)
                v.addWidget(txt)
                bb = QDialogButtonBox(QDialogButtonBox.Close)
                bb.rejected.connect(dlg_det.accept)
                v.addWidget(bb)
                dlg_det.exec_()
                return
            elif accion in ("preparacion", "preparar"):
                from core.services.reservation_service import ReservationService, VARIABLE_WEIGHT_UNITS
                from core.services.inventory_balance_service import InventoryBalanceService
                items = self.delivery_service.get_order_items(pedido_id)

                # Stock gate: must have valid reservation OR sufficient available stock
                _res_svc = ReservationService()
                _inv_svc = InventoryBalanceService(self.conexion)
                _sucursal = getattr(self, 'sucursal_id', 1)
                _reservas = _res_svc.get_reservations_for_operation(self.conexion, str(pedido_id))
                _bloqueados = []
                for _it in items:
                    _pid = _it.get("producto_id")
                    if not _pid:
                        continue
                    _qty = float(_it.get("cantidad") or 0)
                    if _qty <= 0:
                        continue
                    _res_qty = sum(
                        float(r.get("reserved_qty", 0)) for r in _reservas
                        if r.get("product_id") == _pid and not r.get("released")
                    )
                    if _res_qty < _qty:
                        try:
                            _avail = float(_inv_svc.get_available_stock(_pid, _sucursal))
                        except Exception as _exc:
                            import logging as _log
                            _log.getLogger("spj.delivery.ui").exception(
                                "No se pudo consultar stock producto=%s sucursal=%s: %s",
                                _pid, _sucursal, _exc,
                            )
                            _avail = 0.0
                        if _avail < _qty:
                            _bloqueados.append(
                                f"• {_it.get('nombre','Producto')}: "
                                f"disponible={_avail:.2f}, requerido={_qty:.2f}"
                            )
                if _bloqueados:
                    QMessageBox.critical(
                        self, "Stock insuficiente",
                        "No se puede preparar el pedido por stock insuficiente:\n\n"
                        + "\n".join(_bloqueados)
                        + "\n\nRevisa el inventario antes de continuar."
                    )
                    return

                # Check for variable-weight items before marking as "preparacion"
                var_items = [
                    it for it in items
                    if ReservationService.is_variable_weight(it.get("unidad", ""))
                ]
                if var_items:
                    dlg_peso = PesoRealDialog(var_items, parent=self)
                    if dlg_peso.exec_() != QDialog.Accepted:
                        return
                    adjustments = dlg_peso.get_adjustments()
                    for adj in adjustments:
                        try:
                            self.delivery_service.adjust_item_weight(
                                order_id=pedido_id,
                                item_id=adj["item_id"],
                                prepared_qty=adj["prepared_qty"],
                                prepared_by=self.usuario,
                                adjustment_reason=adj.get("adjustment_reason", ""),
                                unit=adj.get("unit") or "",
                            )
                        except Exception as exc:
                            logger.warning("adjust_item_weight item=%s: %s", adj["item_id"], exc)
                    Toast.success(
                        self, "Peso registrado",
                        f"{len(adjustments)} ítem(s) ajustados. Pedido en preparación."
                    )

                self.delivery_service.update_status(
                    pedido_id, "preparacion", usuario=self.usuario
                )
                QTimer.singleShot(0, lambda: self.cargar_pedidos(silent=True))
                return
            elif accion == "ajustar_peso":
                _order_raw = _DeliveryQueryService(self.conexion).get_order_raw(pedido_id) or {}
                estado_actual = str(_order_raw.get("estado") or "").strip().lower()
                if estado_actual != "preparacion":
                    QMessageBox.warning(
                        self,
                        "Acción no permitida",
                        "Solo puedes ajustar peso cuando el pedido está en estado Preparación.",
                    )
                    return
                from core.services.reservation_service import ReservationService
                items = self.delivery_service.get_order_items(pedido_id)
                var_items = [it for it in items if ReservationService.is_variable_weight(it.get("unidad", ""))]
                if not var_items:
                    QMessageBox.information(
                        self, "Sin ítems de peso variable",
                        "Este pedido no tiene productos de peso variable.")
                    return
                dlg_peso = PesoRealDialog(var_items, parent=self)
                if dlg_peso.exec_() != QDialog.Accepted:
                    return
                for adj in dlg_peso.get_adjustments():
                    try:
                        self.delivery_service.adjust_item_weight(
                            order_id=pedido_id,
                            item_id=adj["item_id"],
                            prepared_qty=adj["prepared_qty"],
                            prepared_by=self.usuario,
                            adjustment_reason=adj.get("adjustment_reason", ""),
                            unit=adj.get("unit") or "",
                        )
                    except Exception as exc:
                        logger.warning("adjust_item_weight item=%s: %s", adj["item_id"], exc)
                Toast.success(self, "Peso ajustado", "Pesos actualizados correctamente.")
                QTimer.singleShot(0, lambda: self.cargar_pedidos(silent=True))
                return
            elif accion == "activar_programado":
                self.delivery_service.activate_scheduled_order(pedido_id, usuario=self.usuario)
                Toast.success(self, "Pedido activado", "El pedido programado ya está en flujo operativo.")
                QTimer.singleShot(0, lambda: self.cargar_pedidos(silent=True))
                return
            elif accion == "reprogramar":
                QMessageBox.information(
                    self,
                    "Reprogramar",
                    "La reprogramación avanzada se habilitará en la siguiente fase del módulo.",
                )
                return
            elif accion == "ver_forecast":
                QMessageBox.information(
                    self,
                    "Forecast",
                    "La vista de forecast operativo se habilitará en la siguiente fase del módulo.",
                )
                return
            elif accion == "notificar_wa":
                _row = _DeliveryQueryService(self.conexion).get_order_raw(pedido_id) or {}
                if not _row.get("cliente_tel"):
                    QMessageBox.warning(self, "Sin teléfono", "El pedido no tiene teléfono de cliente."); return
                self._notificar_whatsapp(pedido_id, _row.get("estado", ""), {})
                Toast.success(self, "WhatsApp", f"Notificación enviada a {_row.get('cliente_tel','')}")
                return
            elif accion == "link_pago":
                _row = _DeliveryQueryService(self.conexion).get_order_raw(pedido_id) or {}
                folio = (_row.get("folio") or f"DEL-{pedido_id}")
                total = float(_row.get("total") or 0)

                # Try MercadoPago first; fall back to generic URL
                link = None
                try:
                    from services.mercado_pago_service import MercadoPagoService
                    mp = MercadoPagoService(self.conexion)
                    link = mp.crear_link(
                        total=total,
                        pedido_id=pedido_id,
                        descripcion=f"Delivery #{folio}",
                        cliente_email="cliente@spjpos.mx",
                    )
                except Exception as exc:
                    logger.debug("MercadoPago link_pago: %s", exc)

                if not link:
                    link = f"https://pay.spjpos.mx/delivery/{folio}"

                dlg_link = QDialog(self)
                dlg_link.setWindowTitle("💳 Link de pago")
                dlg_link.setMinimumWidth(480)
                lay_link = QVBoxLayout(dlg_link)
                lay_link.addWidget(
                    QLabel(f"<b>Pedido #{pedido_id} — {folio}</b><br>Total: <b>${total:,.2f}</b>")
                )
                txt_link = QLineEdit(link)
                txt_link.setReadOnly(True)
                txt_link.selectAll()
                txt_link.setStyleSheet(
                    f"border:1px solid {Colors.PRIMARY_BASE}; border-radius:4px; padding:4px;"
                )
                lay_link.addWidget(txt_link)
                bbs = QDialogButtonBox(QDialogButtonBox.Ok)
                bbs.accepted.connect(dlg_link.accept)
                lay_link.addWidget(bbs)
                dlg_link.exec_()
                QApplication.clipboard().setText(link)
                Toast.success(self, "Link copiado", "Link de pago copiado al portapapeles.")
                return
            elif accion == "asignar":
                dlg = AsignarDriverDialog(pedido_id, self.conexion, self)
                if dlg.exec_() != QDialog.Accepted: return
                data = dlg.get_data()
                if not data["driver_id"]:
                    QMessageBox.warning(self,"Sin repartidor","Primero registra repartidores."); return
                self.delivery_service.assign_driver(
                    pedido_id,
                    driver_id=data["driver_id"],
                    tiempo_estimado=str(data.get("tiempo") or ""),
                    notas=data.get("notas") or "",
                    usuario=self.usuario,
                )
            elif accion in ("en_ruta","entregado","cancelado"):
                fecha_col = "fecha_entrega" if accion == "entregado" else "fecha_asignacion"
                
                # If delivered, capture payment method and amount
                pago_metodo = ""
                pago_monto  = 0.0
                if accion == "entregado":
                    dlg_pago = QDialog(self)
                    dlg_pago.setWindowTitle("Registrar Cobro de Entrega")
                    dlg_pago.setMinimumWidth(320)
                    lay_pago = QVBoxLayout(dlg_pago)
                    form_pago = QFormLayout()
                    
                    # Get order total via query service (no SQL in UI)
                    total_pedido = _DeliveryQueryService(self.conexion).get_order_total(pedido_id)
                    
                    cmb_metodo = QComboBox()
                    cmb_metodo.addItems(["Efectivo","Tarjeta","Transferencia","Ya pagado (online)","Sin cobro"])
                    spin_monto = QDoubleSpinBox()
                    spin_monto.setRange(0, 99999); spin_monto.setDecimals(2)
                    spin_monto.setValue(total_pedido); spin_monto.setPrefix("$")
                    form_pago.addRow("Método de cobro:", cmb_metodo)
                    form_pago.addRow("Monto cobrado:", spin_monto)
                    lay_pago.addLayout(form_pago)
                    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
                    btns.accepted.connect(dlg_pago.accept)
                    btns.rejected.connect(dlg_pago.reject)
                    lay_pago.addWidget(btns)
                    
                    if dlg_pago.exec_() != QDialog.Accepted:
                        return
                    pago_metodo = cmb_metodo.currentText()
                    pago_monto  = spin_monto.value()
                
                try:
                    self.delivery_service.update_status(
                        pedido_id,
                        accion,
                        usuario=self.usuario,
                        responsable=(self.usuario if accion == "entregado" else ""),
                        pago_metodo=pago_metodo,
                        pago_monto=pago_monto,
                    )
                except ValueError as ve:
                    msg = str(ve)
                    if "ajuste" in msg.lower() and "pendiente" in msg.lower():
                        QMessageBox.warning(
                            self,
                            "Pedido bloqueado por ajuste pendiente",
                            "No puedes avanzar este pedido hasta que el cliente acepte o rechace el ajuste.",
                        )
                    else:
                        QMessageBox.warning(self, "Acción no permitida", msg)
                    return

                # Audit the delivery completion
                if accion == "entregado":
                    try:
                        from core.services.auto_audit import audit_write
                        audit_write(
                            self.container if hasattr(self,'container') else None,
                            modulo="DELIVERY", accion="ENTREGA_COMPLETADA",
                            entidad="delivery_orders", entidad_id=str(pedido_id),
                            usuario=getattr(self,'usuario_actual','Sistema'),
                            sucursal_id=getattr(self,'sucursal_id',1),
                            detalles=f"Cobrado: ${pago_monto:.2f} via {pago_metodo}"
                        )
                    except Exception:
                        pass
            QTimer.singleShot(0, lambda: self.cargar_pedidos(silent=True))
            # Publicar evento para recarga reactiva en otros módulos
            try:
                from core.events.event_bus import get_bus
                get_bus().publish("PEDIDO_ACTUALIZADO", {
                    "pedido_id": pedido_id, "accion": accion,
                    "sucursal_id": getattr(self, 'sucursal_id', 1)
                })
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self,"Error",str(e))

    def _notificar_whatsapp(self, pedido_id, accion, data):
        try:
            _order = _DeliveryQueryService(self.conexion).get_order_raw(pedido_id) or {}
            tel = _order.get("cliente_tel") or ""
            nombre = _order.get("cliente_nombre") or ""
            if not tel:
                return
            from integrations.whatsapp_service import WhatsAppService
            wa = WhatsAppService(self.conexion)
            if accion == "en_ruta":
                dr = data.get("repartidor", "Repartidor")
                wa.notificar_delivery_en_camino(tel, nombre, str(pedido_id), dr, data.get("tiempo", 30))
            elif accion == "entregado":
                wa.notificar_delivery_entregado(tel, nombre, str(pedido_id))
        except Exception as e:
            logger.debug("WA notify: %s", e)

    def nuevo_pedido(self):
        dlg = NuevoPedidoDialog(self.delivery_service, self.conexion, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        data = dlg.get_data()
        if not data["direccion"]:
            QMessageBox.warning(self, "Dirección requerida", "Ingresa la dirección de entrega.")
            return
        try:
            order_id = self.delivery_service.create_order({
                "cliente_id":    data.get("cliente_id"),
                "cliente_nombre": data["cliente"],
                "cliente_tel":   data.get("cliente_tel", ""),
                "direccion":     data["direccion"],
                "coords":        data.get("coords"),
                "notas":         data.get("notas", ""),
                "total":         data.get("total", 0),
                "pago_metodo":   data.get("pago_metodo", ""),
                "sucursal_id":   data.get("sucursal_id", 1),
                "items":         data.get("items") or [],
            }, usuario=self.usuario)

            QTimer.singleShot(0, lambda: self.cargar_pedidos(silent=True))
            Toast.success(self, "Pedido creado", "Pedido de delivery creado exitosamente.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def gestionar_drivers(self):
        dlg = GestorDriversDialog(self.conexion, self, driver_service=self.driver_service)
        dlg.exec_()
        QTimer.singleShot(0, self._initial_sync_whatsapp_orders)
        QTimer.singleShot(10, self.cargar_pedidos)

    # ── v13.30: Corte de caja por repartidor ──────────────────────────────────

    def _corte_repartidor(self):
        """Muestra resumen financiero del repartidor y registra corte de caja."""
        from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QTableWidget,
                                      QTableWidgetItem, QAbstractItemView)

        dlg = QDialog(self)
        dlg.setWindowTitle("💰 Corte de Caja — Repartidor")
        dlg.setMinimumSize(700, 520)
        lay = QVBoxLayout(dlg)

        # Selector de repartidor
        form = QFormLayout()
        cmb_driver = QComboBox()
        for r in _DeliveryQueryService(self.conexion).get_active_drivers():
            cmb_driver.addItem(r[1], r[0])
        form.addRow("Repartidor:", cmb_driver)
        lay.addLayout(form)

        # Tabla de entregas pendientes de corte
        lbl_info = QLabel("Entregas completadas sin corte:")
        lbl_info.setObjectName("subheading")
        lay.addWidget(lbl_info)

        tbl = QTableWidget()
        tbl.setColumnCount(6)
        tbl.setHorizontalHeaderLabels(["ID", "Cliente", "Total", "Método", "Cobrado", "Fecha"])
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        hh = tbl.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        tbl.setObjectName("tableView")
        lay.addWidget(tbl)

        # Resumen financiero
        grp_resumen = QGroupBox("Resumen del turno")
        grp_resumen.setObjectName("styledGroup")
        rf = QFormLayout(grp_resumen)
        lbl_entregas = QLabel("0")
        lbl_entregas.setObjectName("textPrimary")
        
        lbl_efectivo = QLabel("$0.00")
        lbl_efectivo.setObjectName("textDanger")
        lbl_efectivo.setStyleSheet(f"font-size: {Typography.SIZE_LG}; font-weight: bold;")
        
        lbl_tarjeta  = QLabel("$0.00")
        lbl_tarjeta.setObjectName("textPrimary")
        
        lbl_transfer = QLabel("$0.00")
        lbl_transfer.setObjectName("textPrimary")
        
        lbl_total    = QLabel("$0.00")
        lbl_total.setObjectName("heading")
        lbl_total.setStyleSheet(f"font-weight: bold;")
        
        rf.addRow("Entregas:", lbl_entregas)
        rf.addRow("Efectivo cobrado:", lbl_efectivo)
        rf.addRow("Tarjeta:", lbl_tarjeta)
        rf.addRow("Transferencia:", lbl_transfer)
        rf.addRow("Total cobrado:", lbl_total)

        # Efectivo que entrega el repartidor
        spin_entregado = QDoubleSpinBox()
        spin_entregado.setRange(0, 99999); spin_entregado.setDecimals(2)
        spin_entregado.setPrefix("$ ")
        spin_entregado.setObjectName("inputField")
        rf.addRow("Efectivo entregado:", spin_entregado)
        
        lbl_diferencia = QLabel("$0.00")
        lbl_diferencia.setObjectName("textPrimary")
        lbl_diferencia.setStyleSheet(f"font-weight: bold;")
        rf.addRow("Diferencia:", lbl_diferencia)
        txt_notas_corte = QLineEdit()
        txt_notas_corte.setPlaceholderText("Notas del corte (opcional)")
        txt_notas_corte.setObjectName("inputField")
        rf.addRow("Notas:", txt_notas_corte)
        lay.addWidget(grp_resumen)

        # Datos internos
        _data = {"efectivo": 0.0, "tarjeta": 0.0, "transfer": 0.0, "entregas": 0,
                 "order_ids": [], "turno_inicio": ""}

        def _cargar_entregas():
            driver_id = cmb_driver.currentData()
            if not driver_id:
                return
            from backend.application.queries.driver_settlement_query_service import DriverSettlementQueryService
            svc = DriverSettlementQueryService(self.conexion)
            sucursal_id = getattr(self, 'sucursal_id', 0)
            rows = svc.list_pending_orders_for_driver(driver_id, sucursal_id)
            summary = svc.get_payment_summary(rows)

            tbl.setRowCount(len(rows))
            ids = []
            inicio = ""
            for i, r in enumerate(rows):
                vals = [r["id"], r["cliente_nombre"], r["total"], r["pago_metodo"], r["pago_monto"], r["fecha_entrega"]]
                for j, v in enumerate(vals):
                    tbl.setItem(i, j, QTableWidgetItem(str(v) if v else ""))
                ids.append(r["id"])
                fecha = str(r.get("fecha_entrega") or "")
                if fecha and (not inicio or fecha < inicio):
                    inicio = fecha

            _data["efectivo"] = summary["efectivo"]
            _data["tarjeta"] = summary["tarjeta"]
            _data["transfer"] = summary["transfer"]
            _data["entregas"] = len(rows)
            _data["order_ids"] = ids
            _data["turno_inicio"] = inicio

            lbl_entregas.setText(str(len(rows)))
            lbl_efectivo.setText(f"${summary['efectivo']:.2f}")
            lbl_tarjeta.setText(f"${summary['tarjeta']:.2f}")
            lbl_transfer.setText(f"${summary['transfer']:.2f}")
            lbl_total.setText(f"${summary['total']:.2f}")
            spin_entregado.setValue(summary["efectivo"])
            _actualizar_diferencia()

        def _actualizar_diferencia():
            entregado = spin_entregado.value()
            esperado = _data["efectivo"]
            diff = entregado - esperado
            lbl_diferencia.setText(f"${diff:.2f}")
            # Mantener solo el color dinámico, eliminar tamaño de fuente hardcodeado
            if abs(diff) < 0.01:
                lbl_diferencia.setStyleSheet(f"color: {Colors.SUCCESS_BASE}; font-weight: bold;")
            elif diff < 0:
                lbl_diferencia.setStyleSheet(f"color: {Colors.DANGER_BASE}; font-weight: bold;")
            else:
                lbl_diferencia.setStyleSheet(f"color: {Colors.WARNING_BASE}; font-weight: bold;")

        cmb_driver.currentIndexChanged.connect(lambda: _cargar_entregas())
        spin_entregado.valueChanged.connect(lambda: _actualizar_diferencia())
        if cmb_driver.count() > 0:
            _cargar_entregas()

        # Botones
        btns = QDialogButtonBox()
        btn_registrar = create_success_button(dlg, "✅ Registrar Corte", "Registrar corte de caja del repartidor")
        btn_registrar.setObjectName("btnRegistrarCorte")
        # Eliminar estilos hardcodeados - usar clases CSS del sistema
        btns.addButton(btn_registrar, QDialogButtonBox.AcceptRole)
        btns.addButton("Cancelar", QDialogButtonBox.RejectRole)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        def _registrar_corte():
            driver_id = cmb_driver.currentData()
            if not driver_id or _data["entregas"] == 0:
                QMessageBox.warning(dlg, "Aviso", "No hay entregas para hacer corte.")
                return
            entregado = spin_entregado.value()
            try:
                from backend.application.use_cases.settle_delivery_driver_use_case import (
                    SettleDeliveryDriverCommand, SettleDeliveryDriverUseCase,
                )
                from core.events.event_bus import get_bus
                cmd = SettleDeliveryDriverCommand(
                    driver_id=driver_id,
                    driver_nombre=cmb_driver.currentText(),
                    order_ids=list(_data["order_ids"]),
                    efectivo_entregado=entregado,
                    efectivo_cobrado=_data["efectivo"],
                    tarjeta_cobrado=_data["tarjeta"],
                    transfer_cobrado=_data["transfer"],
                    notas=txt_notas_corte.text().strip(),
                    usuario=getattr(self, 'usuario', 'Sistema'),
                    sucursal_id=getattr(self, 'sucursal_id', 0),
                    turno_inicio=_data["turno_inicio"],
                )
                result = SettleDeliveryDriverUseCase(
                    db=self.conexion,
                    publisher=lambda evt, payload: get_bus().publish(evt, payload),
                ).execute(cmd)

                cut_id = result["cut_id"]
                diferencia = result["diferencia"]

                # Auditar
                try:
                    from core.services.auto_audit import audit_write
                    audit_write(
                        self.container if hasattr(self, 'container') else None,
                        modulo="DELIVERY", accion="CORTE_REPARTIDOR",
                        entidad="delivery_driver_cuts", entidad_id=str(cut_id),
                        usuario=getattr(self, 'usuario', 'Sistema'),
                        sucursal_id=getattr(self, 'sucursal_id', 0),
                        detalles=(f"Repartidor: {cmb_driver.currentText()} | "
                                  f"Entregas: {_data['entregas']} | "
                                  f"Efectivo: ${_data['efectivo']:.2f} | "
                                  f"Entregado: ${entregado:.2f} | "
                                  f"Diferencia: ${diferencia:.2f}")
                    )
                except Exception:
                    pass

                msg = (f"Corte registrado exitosamente.\n\n"
                       f"Repartidor: {cmb_driver.currentText()}\n"
                       f"Entregas: {_data['entregas']}\n"
                       f"Efectivo cobrado: ${_data['efectivo']:.2f}\n"
                       f"Efectivo entregado: ${entregado:.2f}\n"
                       f"Diferencia: ${diferencia:.2f}")
                if abs(diferencia) > 0.01:
                    msg += f"\n\n⚠️ DIFERENCIA DE ${abs(diferencia):.2f}"
                QMessageBox.information(dlg, "✅ Corte Registrado", msg)
                dlg.accept()
            except Exception as e:
                QMessageBox.critical(dlg, "Error", str(e))

        btn_registrar.clicked.connect(_registrar_corte)
        dlg.exec_()

    def _historial_cortes(self):
        """Muestra historial de cortes de caja de repartidores."""
        from PyQt5.QtWidgets import QDialog, QTableWidget, QTableWidgetItem, QAbstractItemView

        dlg = QDialog(self)
        dlg.setWindowTitle("📋 Historial de Cortes — Delivery")
        dlg.setMinimumSize(800, 450)
        lay = QVBoxLayout(dlg)

        tbl = QTableWidget()
        tbl.setColumnCount(10)
        tbl.setHorizontalHeaderLabels([
            "ID", "Repartidor", "Fecha", "Entregas",
            "Efectivo", "Tarjeta", "Transfer", "Entregado",
            "Diferencia", "Usuario"
        ])
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setAlternatingRowColors(True)
        hh = tbl.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        lay.addWidget(tbl)

        rows = _DeliveryQueryService(self.conexion).get_driver_cut_history()
        tbl.setRowCount(len(rows))
        if not rows:
            empty = QLabel("No hay cortes registrados aún.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setObjectName("textMuted")
            lay.addWidget(empty)
        for i, r in enumerate(rows):
            for j, v in enumerate(r):
                val = v
                if j in (4, 5, 6, 7, 8) and v is not None:
                    val = f"${float(v):.2f}"
                item = QTableWidgetItem(str(val) if val is not None else "")
                # Color diferencia
                if j == 8 and v is not None:
                    diff = float(v)
                    if abs(diff) > 0.01:
                        item.setForeground(QColor(Colors.DANGER_HOVER) if diff < 0 else QColor(Colors.WARNING_HOVER))
                    else:
                        item.setForeground(QColor(Colors.SUCCESS_BASE))
                tbl.setItem(i, j, item)

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setObjectName("secondaryBtn")
        btn_cerrar.clicked.connect(dlg.accept)
        lay.addWidget(btn_cerrar)
        dlg.exec_()

class GestorDriversDialog(QDialog):
    """Gestionar repartidores desde DriverService/DriverRepository canónico."""

    def __init__(self, conn, parent=None, driver_service=None):
        super().__init__(parent)
        self.conn = conn
        self.driver_service = driver_service or DriverService(conn)
        self.setWindowTitle("Gestionar Repartidores")
        self.setMinimumSize(680, 480)
        self._build_ui()
        self._cargar()

    def _build_ui(self):
        from PyQt5.QtWidgets import (QFormLayout, QLineEdit, QComboBox, QLabel,
                                      QHBoxLayout, QHeaderView, QAbstractItemView)
        from modulos.spj_phone_widget import PhoneWidget
        lay = QVBoxLayout(self)

        # Tabla
        self.tabla = QTableWidget(); self.tabla.setColumnCount(5)
        self.tabla.setHorizontalHeaderLabels(["ID","Nombre","Teléfono WA","Sucursales","Activo"])
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tabla.setColumnHidden(0, True)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        lay.addWidget(self.tabla)

        # Form para agregar/editar
        form = QFormLayout()
        self.txt_nombre  = QLineEdit(); self.txt_nombre.setPlaceholderText("Nombre completo")
        self.txt_tel     = PhoneWidget(default_country="+52")
        self.txt_suc     = QLineEdit(); self.txt_suc.setPlaceholderText("ID sucursal principal, ej: 1")
        self.cmb_activo  = QComboBox(); self.cmb_activo.addItems(["Activo","Inactivo"])
        form.addRow("Nombre:",       self.txt_nombre)
        form.addRow("Teléfono WA:",  self.txt_tel)
        form.addRow("Sucursal:",   self.txt_suc)
        form.addRow("Estado:",       self.cmb_activo)
        lay.addLayout(form)

        # Botones
        btn_row = QHBoxLayout()
        self.btn_add    = create_success_button(self, "➕ Agregar", "Agregar nuevo repartidor")
        self.btn_edit   = create_warning_button(self, "✏️ Guardar edición", "Guardar cambios del repartidor seleccionado"); self.btn_edit.setEnabled(False)
        self.btn_delete = create_danger_button(self, "🗑️ Eliminar", "Eliminar repartidor seleccionado"); self.btn_delete.setEnabled(False)
        btn_cerrar      = create_secondary_button(self, "Cerrar", "Cerrar ventana")
        btn_cerrar.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_add); btn_row.addWidget(self.btn_edit)
        btn_row.addWidget(self.btn_delete); btn_row.addStretch(); btn_row.addWidget(btn_cerrar)
        lay.addLayout(btn_row)

        self.btn_add.clicked.connect(self._agregar)
        self.btn_edit.clicked.connect(self._guardar_edicion)
        self.btn_delete.clicked.connect(self._eliminar)
        self.tabla.itemSelectionChanged.connect(self._on_select)

    def _cargar(self):
        try:
            rows = [
                (
                    r.get("id"), r.get("nombre", ""), r.get("telefono", ""),
                    r.get("sucursal_id", 1), r.get("activo", 1),
                )
                for r in self.driver_service.list_drivers()
            ]
            self.tabla.setRowCount(0)
            for i, r in enumerate(rows):
                self.tabla.insertRow(i)
                from PyQt5.QtWidgets import QTableWidgetItem
                for j, v in enumerate(r):
                    self.tabla.setItem(i, j, QTableWidgetItem(str(v) if v is not None else ""))
                # Color inactive
                if not int(r[4]):
                    for j in range(5):
                        it = self.tabla.item(i, j)
                        if it: it.setForeground(__import__('PyQt5.QtGui',fromlist=['QColor']).QColor('#aaa'))
        except Exception as e:
            import logging; logging.getLogger("spj.delivery").warning("cargar drivers: %s", e)

    def _on_select(self):
        rows = self.tabla.selectedItems()
        has = bool(rows)
        self.btn_edit.setEnabled(has); self.btn_delete.setEnabled(has)
        if has:
            row = self.tabla.currentRow()
            self.txt_nombre.setText(self.tabla.item(row,1).text() if self.tabla.item(row,1) else "")
            self.txt_tel.set_phone(self.tabla.item(row,2).text() if self.tabla.item(row,2) else "")
            self.txt_suc.setText(   self.tabla.item(row,3).text() if self.tabla.item(row,3) else "")
            activo_val = self.tabla.item(row,4).text() if self.tabla.item(row,4) else "1"
            self.cmb_activo.setCurrentIndex(0 if activo_val == "1" else 1)

    def _validar(self):
        import re as _re
        nombre = self.txt_nombre.text().strip()
        tel    = self.txt_tel.get_e164().strip()
        if not nombre:
            QMessageBox.warning(self,"Aviso","El nombre es obligatorio."); return False
        # v13.30: Validar dígitos locales (10 para MX)
        digitos = _re.sub(r'\D', '', self.txt_tel.get_number())
        if tel and len(digitos) != 10:
            QMessageBox.warning(self,"Teléfono inválido",
                "El número debe tener 10 dígitos.\nEl código de país se agrega automáticamente."); return False
        return True

    def _agregar(self):
        if not self._validar(): return
        tel = self.txt_tel.get_e164().strip()
        suc = int(self.txt_suc.text().strip() or 1)
        activo = 1 if self.cmb_activo.currentIndex()==0 else 0
        self.driver_service.create_driver({
            "nombre": self.txt_nombre.text().strip(),
            "telefono": tel,
            "sucursal_id": suc,
            "activo": activo,
        })
        self._limpiar_form(); self._cargar()

    def _guardar_edicion(self):
        if not self._validar(): return
        row = self.tabla.currentRow()
        driver_id = int(self.tabla.item(row,0).text())
        tel = self.txt_tel.get_e164().strip()
        suc = int(self.txt_suc.text().strip() or 1)
        activo = 1 if self.cmb_activo.currentIndex()==0 else 0
        self.driver_service.update_driver(driver_id, {
            "nombre": self.txt_nombre.text().strip(),
            "telefono": tel,
            "sucursal_id": suc,
            "activo": activo,
        })
        self._limpiar_form(); self._cargar()

    def _eliminar(self):
        # [spj-dedup] from PyQt5.QtWidgets import QMessageBox
        row = self.tabla.currentRow()
        driver_id = int(self.tabla.item(row,0).text())
        nombre    = self.tabla.item(row,1).text()
        if QMessageBox.question(self,"Confirmar",
            f"¿Eliminar al repartidor {nombre}?",
            QMessageBox.Yes|QMessageBox.No) != QMessageBox.Yes: return
        self.driver_service.deactivate_driver(driver_id)
        self._limpiar_form(); self._cargar()

    def _limpiar_form(self):
        self.txt_nombre.clear(); self.txt_tel.set_phone(""); self.txt_suc.clear()
        self.cmb_activo.setCurrentIndex(0)
        self.btn_edit.setEnabled(False); self.btn_delete.setEnabled(False)
        self.tabla.clearSelection()
