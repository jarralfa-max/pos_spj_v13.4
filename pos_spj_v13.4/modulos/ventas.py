# modulos/ventas.py
# MÓDULO DE VENTAS ENTERPRISE CON INYECCIÓN DE DEPENDENCIAS Y HAL (Hardware Abstraction Layer)

from modulos.spj_styles import spj_btn, apply_btn_styles
from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import (
    create_primary_button, create_success_button, create_danger_button,
    create_secondary_button, create_warning_button, apply_tooltip,
    PageHeader, Toast,
)
import logging
import os
import sqlite3
import time
try:
    import serial
    HAS_SERIAL_MODULE = True
except ImportError:
    serial = None
    HAS_SERIAL_MODULE = False
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

from modulos.spj_phone_widget import PhoneWidget
from core.services.auto_audit import audit_write
from core.services.stock_reservation_service import StockReservationService
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QMessageBox, QHBoxLayout,
    QFrame, QTableWidget, QTableWidgetItem, QSplitter,
    QGroupBox, QSizePolicy, QAction, QGridLayout,
    QAbstractItemView, QDialog, QCheckBox, QFormLayout, QDoubleSpinBox,
    QHeaderView, QRadioButton, QScrollArea, QListWidget, QListWidgetItem,
    QInputDialog, QGraphicsDropShadowEffect, QDialogButtonBox, QCompleter, QSpinBox
)
from PyQt5.QtCore import Qt, QDateTime, QTimer, pyqtSignal, QLocale, QPropertyAnimation, QRect, QUrl, QSize, QStringListModel
from PyQt5.QtGui import QIcon, QDoubleValidator, QPixmap, QImage, QColor, QTextDocument, QFont, QPalette, QBrush, QPainter
from PyQt5.QtPrintSupport import QPrinter

# Importación de la clase base y utilidades
from .base import ModuloBase

logger = logging.getLogger("spj.ventas") 

# Importar configuración de temas
try:
    from config import TEMAS, configuraciones_POR_DEFECTO, GestorTemas
except ImportError:
    TEMAS = {}
    configuraciones_POR_DEFECTO = {'tema': 'Oscuro'}
    
    class GestorTemas:
        def __init__(self, conexion):
            # Accept AppContainer or direct db connection
            if hasattr(conexion, 'db'):
                self.container = conexion
                self.conexion  = conexion.db
            else:
                self.container = None
                self.conexion  = conexion
            self.temas = TEMAS
        
        def obtener_tema_actual(self):
            return "Oscuro"
        
        def aplicar_tema(self, widget, nombre_tema):
            return False

# v13.4: hardware_utils eliminado — PrinterService es la fuente única de impresión
# safe_serial_read para báscula está en hardware/scale_reader.py
HAS_ESC_POS = HAS_WIN32 = HAS_SERIAL = HAS_QRCODE = False
try:
    from hardware.scale_reader import safe_serial_read
except ImportError:
    def safe_serial_read(*a, **kw): return 0.0

# Constantes de configuración
SERIAL_PORT = "COM3"
SERIAL_BAUD = 9600
TICKETS_FOLDER = "TICKETS"
LOGO_TICKET_PATH = "logo.png"

os.makedirs(TICKETS_FOLDER, exist_ok=True)
os.makedirs("imagenes_productos", exist_ok=True)

# ==============================================================================
# 1. WIDGET DE TARJETA DE PRODUCTO INTERACTIVO
# ==============================================================================


from PyQt5.QtCore import QObject, QEvent

class _ScanContextFilter(QObject):
    """
    Event filter that updates the scan context when a field gains/loses focus.
    Used instead of monkey-patching focusInEvent (which breaks SIP/PyQt5).
    """
    def __init__(self, module, context_name: str, parent=None):
        super().__init__(parent)
        self._module       = module
        self._context_name = context_name   # "producto" or "cliente"

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.FocusIn:
            self._module._set_scan_context(self._context_name, obj)
        elif event.type() == QEvent.FocusOut:
            self._module._set_scan_context("auto", None)
        return False  # Never consume the event — always pass through

class _FKeyButton(QPushButton):
    """QPushButton with an F-key shortcut badge painted inside the button, right side."""

    def __init__(self, text: str = "", fkey: str = "", parent=None):
        super().__init__(text, parent)
        self._fkey = fkey

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._fkey:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bw, bh = 24, 14
        margin = 5
        rx = self.width() - bw - margin
        ry = (self.height() - bh) // 2
        badge_rect = QRect(rx, ry, bw, bh)
        # Badge background — semi-transparent dark pill
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 55))
        p.drawRoundedRect(badge_rect, 4, 4)
        # Badge text
        p.setPen(QColor(255, 255, 255, 200))
        f = p.font()
        f.setPointSize(7)
        f.setBold(True)
        p.setFont(f)
        p.drawText(badge_rect, Qt.AlignCenter, self._fkey)
        p.end()


class ProductCard(QFrame):
    """Operational retail product card — matches enterprise POS visual design."""
    product_selected = pyqtSignal(dict)

    CARD_W, CARD_H = 175, 198
    ZOOM_W, ZOOM_H = 182, 206   # ~4% hover/selected zoom
    IMG_H = 85
    _ZOOM_STEPS = 6             # frames for the zoom animation
    _ZOOM_INTERVAL_MS = 12      # ms per frame (~80 fps feel)

    def __init__(self, producto_data: dict, parent: QWidget = None):
        super().__init__(parent)
        self.producto       = producto_data
        self.is_selected    = False
        self._is_hovering   = False
        self.original_size  = QSize(self.CARD_W, self.CARD_H)
        self.zoom_size      = QSize(self.ZOOM_W, self.ZOOM_H)

        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.CARD_W, self.CARD_H)
        self.setFrameShape(QFrame.NoFrame)

        # Stock state classification
        existencia   = float(self.producto.get('existencia', 0))
        stock_minimo = float(self.producto.get('stock_minimo', 0))
        if existencia <= 0:
            self._stock_state = "out-of-stock"
        elif stock_minimo > 0 and existencia <= stock_minimo:
            self._stock_state = "critical-stock"
        elif stock_minimo > 0 and existencia <= stock_minimo * 2:
            self._stock_state = "low-stock"
        else:
            self._stock_state = ""

        base_class = f"product-card-{self._stock_state}" if self._stock_state else "product-card"
        self.setProperty("class", base_class)

        if self._stock_state == "out-of-stock":
            self.setCursor(Qt.ForbiddenCursor)

        # Subtle shadow
        self.shadow_effect = QGraphicsDropShadowEffect(self)
        self.shadow_effect.setBlurRadius(8)
        self.shadow_effect.setXOffset(0)
        self.shadow_effect.setYOffset(2)
        self.shadow_effect.setColor(QColor(0, 0, 0, 45))
        self.setGraphicsEffect(self.shadow_effect)

        # ── Layout: image on top, info below ─────────────────────────────
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # Image area (borderless, fills card width)
        self.lbl_imagen = QLabel()
        self.lbl_imagen.setAlignment(Qt.AlignCenter)
        self.lbl_imagen.setFixedSize(self.CARD_W, self.IMG_H)
        self.lbl_imagen.setObjectName("posProductImage")
        self.lbl_imagen.setProperty("class", "product-image")
        self._load_image()
        root_lay.addWidget(self.lbl_imagen)

        # Info area
        info_widget = QWidget()
        info_widget.setObjectName("posProductInfo")
        info_lay = QVBoxLayout(info_widget)
        info_lay.setContentsMargins(8, 6, 8, 6)
        info_lay.setSpacing(2)

        self.lbl_nombre = QLabel(self.producto['nombre'])
        self.lbl_nombre.setWordWrap(True)
        name_class = "product-name-dimmed" if self._stock_state == "out-of-stock" else "product-name"
        self.lbl_nombre.setProperty("class", name_class)
        self.lbl_nombre.setMaximumHeight(34)   # max 2 lines

        codigo = (self.producto.get('codigo', '')
                  or self.producto.get('codigo_barras', '')
                  or str(self.producto.get('id', '')))
        self.lbl_codigo = QLabel(f"Cód: {codigo}")
        self.lbl_codigo.setObjectName("posProductCode")

        self.lbl_precio = QLabel(
            f"${self.producto['precio']:.2f} /{self.producto['unidad']}")
        self.lbl_precio.setProperty("class", "product-price")

        # Stock label with state-aware text/color
        if self._stock_state == "out-of-stock":
            stock_txt = "⊘ Agotado"
            stock_cls = "product-stock-out"
        elif self._stock_state == "critical-stock":
            stock_txt = f"● Stock: {existencia:.2f} {self.producto['unidad']}"
            stock_cls = "product-stock-critical"
        elif self._stock_state == "low-stock":
            stock_txt = f"● Stock: {existencia:.2f} {self.producto['unidad']}"
            stock_cls = "product-stock-low"
        else:
            stock_txt = f"● Stock: {existencia:.2f} {self.producto['unidad']}"
            stock_cls = "product-stock"
        self.lbl_stock = QLabel(stock_txt)
        self.lbl_stock.setProperty("class", stock_cls)

        info_lay.addWidget(self.lbl_nombre)
        info_lay.addWidget(self.lbl_codigo)
        info_lay.addWidget(self.lbl_precio)
        info_lay.addWidget(self.lbl_stock)
        info_lay.addStretch(1)
        root_lay.addWidget(info_widget, 1)

        # ── Corner overlays (absolute-positioned over image) ──────────────

        # Star icon — top-right; filled gold when selected
        self._btn_star = QLabel("☆", self)
        self._btn_star.setObjectName("posProductStar")
        self._btn_star.setFixedSize(26, 26)
        self._btn_star.setAlignment(Qt.AlignCenter)

        # Stock badge — top-left (CRÍTICO / BAJO / AGOTADO)
        self._lbl_stock_badge = None
        if self._stock_state in ("out-of-stock", "critical-stock", "low-stock"):
            badge_txt = ("AGOTADO" if self._stock_state == "out-of-stock"
                         else ("CRÍTICO" if self._stock_state == "critical-stock" else "BAJO"))
            badge_obj = ("posOutOfStockBadge" if self._stock_state in ("out-of-stock", "critical-stock")
                         else "posLowStockBadge")
            self._lbl_stock_badge = QLabel(badge_txt, self)
            self._lbl_stock_badge.setObjectName(badge_obj)
            self._lbl_stock_badge.setAlignment(Qt.AlignCenter)
            self._lbl_stock_badge.setFixedHeight(20)
            self._lbl_stock_badge.adjustSize()

    def _position_overlays(self):
        """Position star and badge overlays over the image area."""
        if hasattr(self, '_btn_star'):
            self._btn_star.move(self.CARD_W - 30, 6)
            self._btn_star.raise_()
        if self._lbl_stock_badge:
            self._lbl_stock_badge.adjustSize()
            self._lbl_stock_badge.move(6, 6)
            self._lbl_stock_badge.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        self._position_overlays()

    def update_shadow_color(self):
        self.shadow_effect.setColor(QColor(0, 0, 0, 45))

    def _load_image(self):
        imagen_path = self.producto.get('imagen_path')
        if imagen_path and os.path.exists(imagen_path):
            pixmap = QPixmap(imagen_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    self.lbl_imagen.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.lbl_imagen.setPixmap(pixmap)
                return
        self.lbl_imagen.setText("📦\nSin Imagen")
        self.lbl_imagen.setProperty("class", "product-image-placeholder")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.product_selected.emit(self.producto)
            super().mousePressEvent(event)

    def set_selected(self, selected: bool):
        self.is_selected = selected
        if selected:
            self.setProperty("class", "product-card-selected")
            self.shadow_effect.setBlurRadius(20)
            self.shadow_effect.setColor(QColor(37, 99, 235, 90))
            self.shadow_effect.setXOffset(0)
            self.shadow_effect.setYOffset(3)
            self.animate_size(self.zoom_size)
            self.raise_()
            if hasattr(self, '_btn_star'):
                self._btn_star.setText("★")
                self._btn_star.setObjectName("posProductStarActive")
                self._btn_star.style().unpolish(self._btn_star)
                self._btn_star.style().polish(self._btn_star)
        else:
            base_class = f"product-card-{self._stock_state}" if self._stock_state else "product-card"
            self.setProperty("class", base_class)
            self.shadow_effect.setBlurRadius(8)
            self.shadow_effect.setColor(QColor(0, 0, 0, 45))
            self.shadow_effect.setXOffset(0)
            self.shadow_effect.setYOffset(2)
            if not self._is_hovering:
                self.animate_size(self.original_size)
            if hasattr(self, '_btn_star'):
                self._btn_star.setText("☆")
                self._btn_star.setObjectName("posProductStar")
                self._btn_star.style().unpolish(self._btn_star)
                self._btn_star.style().polish(self._btn_star)
        self.style().unpolish(self)
        self.style().polish(self)

    def enterEvent(self, event):
        self._is_hovering = True
        self.shadow_effect.setBlurRadius(18)
        self.shadow_effect.setColor(QColor(37, 99, 235, 70))
        self.setProperty("class", "product-card-hover" if not self.is_selected else "product-card-selected")
        self.style().unpolish(self)
        self.style().polish(self)
        self.animate_size(self.zoom_size)
        self.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovering = False
        if self.is_selected:
            self.shadow_effect.setBlurRadius(18)
            self.shadow_effect.setColor(QColor(37, 99, 235, 80))
            self.setProperty("class", "product-card-selected")
            # stay zoomed while selected
        else:
            base_class = f"product-card-{self._stock_state}" if self._stock_state else "product-card"
            self.setProperty("class", base_class)
            self.shadow_effect.setBlurRadius(8)
            self.shadow_effect.setColor(QColor(0, 0, 0, 45))
            self.animate_size(self.original_size)
        self.style().unpolish(self)
        self.style().polish(self)
        super().leaveEvent(event)

    def animate_size(self, target_size: QSize):
        """Smooth step-based size animation toward target_size."""
        self._zoom_target = target_size
        if not hasattr(self, '_zoom_timer'):
            self._zoom_timer = QTimer(self)
            self._zoom_timer.setInterval(self._ZOOM_INTERVAL_MS)
            self._zoom_timer.timeout.connect(self._step_zoom)
        self._zoom_timer.start()

    def _step_zoom(self):
        if not hasattr(self, '_zoom_target'):
            self._zoom_timer.stop()
            return
        cur_w, cur_h = self.width(), self.height()
        tgt_w, tgt_h = self._zoom_target.width(), self._zoom_target.height()
        diff_w = tgt_w - cur_w
        diff_h = tgt_h - cur_h
        if abs(diff_w) <= 1 and abs(diff_h) <= 1:
            self.setFixedSize(tgt_w, tgt_h)
            self._zoom_timer.stop()
            self._position_overlays()
            return
        step_w = max(1, abs(diff_w) // 2) * (1 if diff_w > 0 else -1)
        step_h = max(1, abs(diff_h) // 2) * (1 if diff_h > 0 else -1)
        self.setFixedSize(cur_w + step_w, cur_h + step_h)
        self._position_overlays()

# ==============================================================================
# 2. DIÁLOGO PARA SUSPENDER VENTA
# ==============================================================================
# (Se mantiene exactamente igual)
class DialogoSuspender(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Suspender Venta")
        self.setModal(True)
        self.setFixedSize(400, 150)
        self.nombre_venta = ""
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        titulo = QLabel("Asignar nombre a la venta suspendida:")
        titulo.setProperty("class", "dialog-title")
        layout.addWidget(titulo)
        
        self.txt_nombre = QLineEdit()
        self.txt_nombre.setPlaceholderText("Ej: Venta de Juan, Pedido especial, etc.")
        self.txt_nombre.setProperty("class", "dialog-input")
        layout.addWidget(self.txt_nombre)
        
        btn_layout = QHBoxLayout()
        btn_cancelar = QPushButton("Cancelar")
        btn_aceptar = QPushButton("Suspender Venta")
        btn_cancelar.setObjectName("secondaryBtn")
        btn_aceptar.setObjectName("primaryBtn")
        
        btn_layout.addWidget(btn_cancelar)
        btn_layout.addWidget(btn_aceptar)
        layout.addLayout(btn_layout)
        
        btn_aceptar.clicked.connect(self.aceptar)
        btn_cancelar.clicked.connect(self.reject)
        
    def aceptar(self):
        nombre = self.txt_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Advertencia", "Debe ingresar un nombre para la venta en espera.")
            return
        self.nombre_venta = nombre
        self.accept()
        
    def get_nombre_venta(self) -> str:
        return self.nombre_venta

# ==============================================================================
# 3. DIÁLOGO DE PAGO MODAL
# ==============================================================================
# (Se mantiene exactamente igual)
class DialogoPago(QDialog):
    def __init__(self, total_a_pagar: float, parent: QWidget = None,
                 loyalty_balance: Dict = None, loyalty_preview_provider=None):
        super().__init__(parent)
        self.setWindowTitle("Cobrar")
        self.setModal(True)
        self.setMinimumSize(460, 400)
        self.resize(500, 460)
        # ISSUE 4 FIX: objectName para que el QSS global pueda estilizar el diálogo
        self.setObjectName("paymentDialog")
        self.total_a_pagar = float(total_a_pagar) if total_a_pagar is not None else 0.0
        self.total_original = self.total_a_pagar
        self.efectivo_recibido = 0.0
        self.cambio = 0.0
        self.forma_pago = "Efectivo"
        self.saldo_credito = 0.0
        self._loyalty = loyalty_balance or {}
        self._loyalty_preview_provider = loyalty_preview_provider
        self.puntos_a_canjear = 0
        self.descuento_puntos = 0.0
        self.init_ui()
        self.conectar_eventos()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 14, 16, 14)

        # ── Header: Total prominente ────────────────────────────────────────
        header = QFrame()
        header.setObjectName("paymentHeader")
        hdr_lay = QVBoxLayout(header)
        hdr_lay.setContentsMargins(12, 10, 12, 10)
        hdr_lay.setSpacing(2)
        lbl_caption = QLabel("TOTAL A COBRAR")
        lbl_caption.setObjectName("paymentCaption")
        lbl_caption.setAlignment(Qt.AlignCenter)
        self.lbl_total = QLabel(f"${self.total_a_pagar:.2f}")
        self.lbl_total.setObjectName("paymentTotalAmount")
        self.lbl_total.setAlignment(Qt.AlignCenter)
        hdr_lay.addWidget(lbl_caption)
        hdr_lay.addWidget(self.lbl_total)
        layout.addWidget(header)

        # ── Form ────────────────────────────────────────────────────────────
        form_layout = QFormLayout()
        form_layout.setSpacing(8)
        form_layout.setContentsMargins(0, 4, 0, 4)
        form_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.cmb_forma_pago = QComboBox()
        self.cmb_forma_pago.addItems(["Efectivo", "Tarjeta", "Transferencia", "Crédito", "Pago Mixto", "Mercado Pago"])
        self.cmb_forma_pago.setObjectName("paymentCombo")
        self.cmb_forma_pago.setMinimumHeight(32)
        form_layout.addRow("Forma de pago:", self.cmb_forma_pago)

        self.txt_recibido = QDoubleSpinBox()
        self.txt_recibido.setRange(0.00, 99999.00)
        self.txt_recibido.setDecimals(2)
        self.txt_recibido.setValue(self.total_a_pagar)
        self.txt_recibido.setSingleStep(10.0)
        self.txt_recibido.setPrefix("$ ")
        self.txt_recibido.setMinimumHeight(36)
        self.txt_recibido.setObjectName("paymentSpinbox")
        self.txt_recibido.lineEdit().setReadOnly(False)
        form_layout.addRow("Monto recibido:", self.txt_recibido)
        
        self.lbl_cambio = QLabel("Cambio: $0.00")
        self.lbl_cambio.setObjectName("paymentChange")
        form_layout.addRow("", self.lbl_cambio)

        # v13.4 Fase 2: Sección de canje de puntos
        self._loyalty_widget = QWidget()
        _loy_lay = QVBoxLayout(self._loyalty_widget)
        _loy_lay.setContentsMargins(0, 0, 0, 0)
        _loy_lay.setSpacing(3)
        pts = self._loyalty.get("puntos_disponibles", self._loyalty.get("puntos", 0))
        valor = self._loyalty.get("descuento_maximo", self._loyalty.get("valor_canje", 0))
        puede = self._loyalty.get("enabled", self._loyalty.get("puede_canjear", False))

        _loy_header = QHBoxLayout()
        self._lbl_puntos = QLabel(f"⭐ {pts} puntos disponibles (=${valor:.2f})")
        self._lbl_puntos.setProperty("class", "text-bold")
        _loy_header.addWidget(self._lbl_puntos)
        _loy_lay.addLayout(_loy_header)

        _loy_row = QHBoxLayout()
        self._chk_canjear = QCheckBox("Usar puntos")
        self._chk_canjear.setEnabled(puede)
        self._chk_canjear.toggled.connect(self._toggle_canje)
        self._spin_puntos = QSpinBox()
        self._spin_puntos.setRange(0, pts)
        self._spin_puntos.setValue(pts)
        self._spin_puntos.setEnabled(False)
        self._spin_puntos.setSuffix(" pts")
        self._spin_puntos.valueChanged.connect(self._recalcular_canje)
        self._lbl_desc_puntos = QLabel("")
        self._lbl_desc_puntos.setProperty("class", "text-success")
        _loy_row.addWidget(self._chk_canjear)
        _loy_row.addWidget(self._spin_puntos)
        _loy_row.addWidget(self._lbl_desc_puntos)
        _loy_lay.addLayout(_loy_row)

        if not puede and pts > 0:
            mn = self._loyalty.get("min_puntos_canje", 100)
            _loy_lay.addWidget(QLabel(f"Mínimo {mn} puntos para canjear"))
        self._loyalty_widget.setVisible(pts > 0)
        form_layout.addRow("", self._loyalty_widget)
        
        self.txt_saldo_credito = QDoubleSpinBox()
        self.txt_saldo_credito.setRange(0.00, 99999.00)
        self.txt_saldo_credito.setDecimals(2)
        self.txt_saldo_credito.setValue(self.total_a_pagar)
        self.txt_saldo_credito.setProperty("class", "payment-spinbox")
        form_layout.addRow("Saldo Adeudado:", self.txt_saldo_credito)
        self.txt_saldo_credito.hide()

        # Pago mixto (efectivo + tarjeta)
        self._mixto_widget = QWidget()
        _ml = QHBoxLayout(self._mixto_widget)
        _ml.setContentsMargins(0, 0, 0, 0)
        _ml.addWidget(QLabel("Efectivo:"))
        self.spin_efectivo_mixto = QDoubleSpinBox()
        self.spin_efectivo_mixto.setRange(0, 99999); self.spin_efectivo_mixto.setDecimals(2)
        self.spin_efectivo_mixto.valueChanged.connect(self._recalcular_mixto)
        _ml.addWidget(self.spin_efectivo_mixto)
        _ml.addWidget(QLabel("Tarjeta:"))
        self.spin_tarjeta_mixto = QDoubleSpinBox()
        self.spin_tarjeta_mixto.setRange(0, 99999); self.spin_tarjeta_mixto.setDecimals(2)
        self.spin_tarjeta_mixto.valueChanged.connect(self._recalcular_mixto)
        _ml.addWidget(self.spin_tarjeta_mixto)
        self.lbl_mixto_diff = QLabel("")
        self.lbl_mixto_diff.setProperty("class", "text-danger caption")
        _ml.addWidget(self.lbl_mixto_diff)
        self._mixto_widget.hide()
        form_layout.addRow("", self._mixto_widget)
        
        layout.addLayout(form_layout)
        layout.addStretch(1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setObjectName("paymentCancelBtn")
        self.btn_cancelar.setMinimumHeight(36)
        self.btn_aceptar = QPushButton("💰 Confirmar Pago")
        self.btn_aceptar.setObjectName("paymentConfirmBtn")
        self.btn_aceptar.setMinimumHeight(40)
        btn_layout.addWidget(self.btn_cancelar)
        btn_layout.addWidget(self.btn_aceptar, 2)
        layout.addLayout(btn_layout)

        self.calcular_cambio()
        
    def conectar_eventos(self):
        self.txt_recibido.valueChanged.connect(self.calcular_cambio)
        self.cmb_forma_pago.currentTextChanged.connect(self.cambiar_forma_pago)
        self.btn_aceptar.clicked.connect(self.accept)
        self.btn_cancelar.clicked.connect(self.reject)

    def showEvent(self, event):
        """v13.4: Auto-focus y select all en campo de efectivo."""
        super().showEvent(event)
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(50, lambda: (
            self.txt_recibido.setFocus(),
            self.txt_recibido.selectAll()))
        
    def cambiar_forma_pago(self, forma_pago):
        try:
            from core.services.sales.payment_policy import PaymentPolicy
            self.forma_pago = PaymentPolicy.normalize_payment_method(forma_pago)
        except Exception:
            self.forma_pago = forma_pago
        forma_pago = self.forma_pago
        if forma_pago == "Efectivo":
            self.txt_recibido.setEnabled(True)
            self.txt_recibido.setValue(self.total_a_pagar)
            self.lbl_cambio.show()
            self.txt_saldo_credito.hide()
        elif forma_pago == "Crédito":
            self.txt_recibido.setEnabled(False)
            self.lbl_cambio.hide()
            self.txt_saldo_credito.show()
            self.txt_saldo_credito.setValue(self.total_a_pagar)
        elif forma_pago == "Mercado Pago":
            self.txt_recibido.setEnabled(False)
            self.txt_recibido.setValue(self.total_a_pagar)
            self.lbl_cambio.hide()
            self.txt_saldo_credito.hide()
            self._mixto_widget.hide()
            # Mostrar info: se generará link al confirmar
            self.lbl_mp_info = getattr(self, 'lbl_mp_info', None)
            if not self.lbl_mp_info:
                from PyQt5.QtWidgets import QLabel
                self.lbl_mp_info = QLabel("🔗 Se generará link de pago al confirmar")
                self.lbl_mp_info.setProperty("class", "text-info caption-bold")
                self.layout().insertWidget(self.layout().count()-1, self.lbl_mp_info)
            self.lbl_mp_info.show()
        elif forma_pago == "Pago Mixto":
            self.txt_recibido.setEnabled(False)
            self.lbl_cambio.hide()
            self.txt_saldo_credito.hide()
            self._mixto_widget.show()
            self.spin_efectivo_mixto.setValue(round(self.total_a_pagar * 0.5, 2))
            self.spin_tarjeta_mixto.setValue(round(self.total_a_pagar * 0.5, 2))
        else:
            self.txt_recibido.setEnabled(False)
            self.txt_recibido.setValue(self.total_a_pagar)
            self.lbl_cambio.hide()
            self.txt_saldo_credito.hide()
            self._mixto_widget.hide()
        if hasattr(self,'lbl_mp_info') and self.lbl_mp_info and forma_pago != 'Mercado Pago':
            self.lbl_mp_info.hide()
        self.calcular_cambio()

    def calcular_cambio(self):
        self.efectivo_recibido = self.txt_recibido.value()
        try:
            from core.services.sales.payment_policy import PaymentPolicy
            validation = PaymentPolicy.validate_payment(
                total=self.total_a_pagar,
                method=self.forma_pago,
                amount_paid=self.efectivo_recibido,
                cash=self.spin_efectivo_mixto.value() if hasattr(self, "spin_efectivo_mixto") else 0.0,
                card=self.spin_tarjeta_mixto.value() if hasattr(self, "spin_tarjeta_mixto") else 0.0,
            )
            self.cambio = float(validation.get("change", 0.0))
            ok = bool(validation.get("ok", True))
        except Exception:
            ok = True
            self.cambio = round(self.efectivo_recibido - self.total_a_pagar, 2) if self.forma_pago == "Efectivo" else 0.0
        if self.forma_pago == "Efectivo":
            self.lbl_cambio.setText(f"Cambio: ${self.cambio:.2f}")
            if not ok or self.cambio < 0:
                self.btn_aceptar.setEnabled(False)
                self.lbl_cambio.setProperty("class", "payment-change-negative")
            else:
                self.btn_aceptar.setEnabled(True)
                self.lbl_cambio.setProperty("class", "payment-change")
        else:
            self.efectivo_recibido = self.total_a_pagar
            self.cambio = 0.0
            self.btn_aceptar.setEnabled(True)

    def _recalcular_mixto(self):
        if self.forma_pago != "Pago Mixto":
            return
        ef = self.spin_efectivo_mixto.value()
        ta = self.spin_tarjeta_mixto.value()
        try:
            from core.services.sales.payment_policy import PaymentPolicy
            v = PaymentPolicy.validate_mixed_payment(self.total_a_pagar, ef, ta)
            diff = float(v.get("diff", 0.0))
        except Exception:
            total = ef + ta
            diff = round(total - self.total_a_pagar, 2)
        if abs(diff) < 0.01:
            self.lbl_mixto_diff.setText("✅ Cuadra")
            self.lbl_mixto_diff.setProperty("class", "text-success caption")
            self.btn_aceptar.setEnabled(True)
        elif diff > 0:
            self.lbl_mixto_diff.setText(f"Sobran ${diff:.2f}")
            self.lbl_mixto_diff.setProperty("class", "text-warning caption")
            self.btn_aceptar.setEnabled(True)
        else:
            self.lbl_mixto_diff.setText(f"Faltan ${abs(diff):.2f}")
            self.lbl_mixto_diff.setProperty("class", "text-danger caption")
            self.btn_aceptar.setEnabled(False)

    def _toggle_canje(self, checked: bool):
        """v13.4 Fase 0 hotfix: Activa/desactiva el canje de puntos de fidelidad."""
        if not hasattr(self, "_spin_puntos"):
            return
        self._spin_puntos.setEnabled(checked)
        if checked:
            self._recalcular_canje(self._spin_puntos.value())
        else:
            self.descuento_puntos = 0.0
            self.puntos_a_canjear = 0
            self.total_a_pagar = self.total_original
            self._lbl_desc_puntos.setText("")
            self.lbl_total.setText(f"Total a pagar: ${self.total_a_pagar:.2f}")
            if hasattr(self, "txt_recibido"):
                self.txt_recibido.setValue(self.total_a_pagar)
            self.calcular_cambio()

    def _recalcular_canje(self, value: int):
        """v13.4 Fase 0 hotfix: Recalcula descuento al modificar puntos a canjear."""
        if not hasattr(self, "_chk_canjear") or not self._chk_canjear.isChecked():
            return
        descuento = 0.0
        if callable(self._loyalty_preview_provider):
            try:
                preview = self._loyalty_preview_provider(value, self.total_original) or {}
                descuento = float(preview.get("descuento", 0.0))
            except Exception:
                descuento = 0.0
        else:
            descuento = 0.0
        descuento = min(round(descuento, 2), self.total_original)
        self.descuento_puntos = descuento
        self.puntos_a_canjear = value
        self.total_a_pagar = round(self.total_original - descuento, 2)
        self._lbl_desc_puntos.setText(f"-${descuento:.2f}")
        self.lbl_total.setText(f"Total a pagar: ${self.total_a_pagar:.2f}")
        if hasattr(self, "txt_recibido"):
            self.txt_recibido.setValue(self.total_a_pagar)
        self.calcular_cambio()

    def get_datos_pago(self) -> Dict[str, Any]:
        try:
            from core.services.sales.payment_policy import PaymentPolicy
            payload = PaymentPolicy.build_payment_breakdown(
                total=self.total_a_pagar,
                method=self.forma_pago,
                amount_paid=self.efectivo_recibido,
                cash=self.spin_efectivo_mixto.value() if self.forma_pago == "Pago Mixto" else 0.0,
                card=self.spin_tarjeta_mixto.value() if self.forma_pago == "Pago Mixto" else 0.0,
                saldo_credito=self.txt_saldo_credito.value() if self.forma_pago == "Crédito" else 0.0,
            )
        except Exception:
            payload = {
                "forma_pago": self.forma_pago,
                "total_pagado": self.total_a_pagar,
                "efectivo_recibido": self.efectivo_recibido,
                "monto_tarjeta_mixto": 0.0,
                "cambio": self.cambio,
                "saldo_credito": self.txt_saldo_credito.value() if self.forma_pago == "Crédito" else 0.0,
            }
        payload.update({
            "puntos_canjeados": self.puntos_a_canjear,
            "descuento_puntos": self.descuento_puntos,
        })
        return payload

# ==============================================================================
# 4. DIÁLOGO PARA AGREGAR CLIENTE
# ==============================================================================
class DialogoAgregarCliente(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agregar Cliente")
        self.setModal(True)
        self.setFixedSize(500, 400)
        self.cliente_data = {}
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        titulo = QLabel("Agregar Nuevo Cliente")
        titulo.setProperty("class", "client-dialog-title")
        layout.addWidget(titulo)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        
        # v13.4: Campo para ID de tarjeta de fidelidad
        self.txt_tarjeta_id = QLineEdit()
        self.txt_tarjeta_id.setPlaceholderText("Escanear QR de tarjeta o escribir ID")
        self.txt_tarjeta_id.setProperty("class", "client-dialog-input")
        form_layout.addRow("ID Tarjeta:", self.txt_tarjeta_id)
        
        self.txt_nombre = QLineEdit()
        self.txt_nombre.setPlaceholderText("Nombre completo del cliente")
        self.txt_nombre.setProperty("class", "client-dialog-input")
        form_layout.addRow("Nombre*:", self.txt_nombre)
        
        self.txt_telefono = PhoneWidget()
        self.txt_telefono.setPlaceholderText("Número de teléfono")
        self.txt_telefono.setProperty("class", "client-dialog-input")
        form_layout.addRow("Teléfono:", self.txt_telefono)
        
        self.txt_email = QLineEdit()
        self.txt_email.setPlaceholderText("Correo electrónico")
        self.txt_email.setProperty("class", "client-dialog-input")
        form_layout.addRow("Email:", self.txt_email)
        
        self.txt_direccion = QLineEdit()
        self.txt_direccion.setPlaceholderText("Dirección completa")
        self.txt_direccion.setProperty("class", "client-dialog-input")
        form_layout.addRow("Dirección:", self.txt_direccion)
        
        self.chk_tarjeta = QCheckBox("Generar tarjeta de fidelidad")
        self.chk_tarjeta.setChecked(True)
        self.chk_tarjeta.setProperty("class", "client-dialog-checkbox")
        form_layout.addRow("", self.chk_tarjeta)
        
        layout.addLayout(form_layout)
        layout.addStretch(1)
        
        btn_layout = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_layout.setProperty("class", "client-dialog-buttons")
        btn_layout.accepted.connect(self.validar_y_aceptar)
        btn_layout.rejected.connect(self.reject)
        
        layout.addWidget(btn_layout)
        
    def validar_y_aceptar(self):
        nombre = self.txt_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Validación", "El nombre del cliente es obligatorio.")
            return
        
        # v13.4: Parsear tarjeta ID — extraer solo el ID, no el contenido completo
        tarjeta_raw = self.txt_tarjeta_id.text().strip()
        tarjeta_id = ""
        if tarjeta_raw:
            import re
            # Formatos: TF-ABC123 → ABC123, CLT-42-Juan → 42, solo código → código
            m = re.match(r'^(?:TF|TAR|CARD)-(.+)$', tarjeta_raw, re.IGNORECASE)
            if m:
                tarjeta_id = m.group(1).strip()
            elif re.match(r'^CLT-(\d+)', tarjeta_raw, re.IGNORECASE):
                tarjeta_id = re.match(r'^CLT-(\d+)', tarjeta_raw, re.IGNORECASE).group(1)
            else:
                tarjeta_id = tarjeta_raw
            
        self.cliente_data = {
            'nombre': nombre,
            'telefono': self.txt_telefono.get_e164().strip(),
            'email': self.txt_email.text().strip(),
            'direccion': self.txt_direccion.text().strip(),
            'generar_tarjeta': self.chk_tarjeta.isChecked(),
            'tarjeta_id': tarjeta_id,
        }
        self.accept()
        
    def get_cliente_data(self):
        return self.cliente_data

# ==============================================================================
# 4b. DIÁLOGO ASIGNAR TARJETA 
# ==============================================================================
class _DialogoAsignarTarjeta(QDialog):
    def __init__(self, tarjeta, conexion, parent=None):
        super().__init__(parent)
        self.tarjeta   = tarjeta
        self.conexion  = conexion
        self.resultado: dict = {}
        self.setWindowTitle("Tarjeta no asignada")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(18, 18, 18, 18)

        titulo = QLabel(f"💳 Tarjeta {self.tarjeta.numero}")
        titulo.setProperty("class", "dialog-title")
        layout.addWidget(titulo)

        info = QLabel(f"Estado: {self.tarjeta.estado.capitalize()}  |  "
                      f"Puntos: {self.tarjeta.puntos_actuales}")
        layout.addWidget(info)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        grp_a = QGroupBox("A) Asignar a cliente existente")
        lay_a = QHBoxLayout(grp_a)
        self.txt_buscar_cliente = QLineEdit()
        self.txt_buscar_cliente.setPlaceholderText("Nombre o teléfono…")
        self.btn_buscar_c = QPushButton("Buscar")
        self.btn_buscar_c.clicked.connect(self._buscar_cliente_existente)
        lay_a.addWidget(self.txt_buscar_cliente)
        lay_a.addWidget(self.btn_buscar_c)
        layout.addWidget(grp_a)

        self.lbl_cliente_encontrado = QLabel("")
        self.lbl_cliente_encontrado.setVisible(False)
        layout.addWidget(self.lbl_cliente_encontrado)

        self.btn_asignar_existente = QPushButton("✅ Asignar a este cliente")
        self.btn_asignar_existente.setEnabled(False)
        self.btn_asignar_existente.clicked.connect(self._asignar_existente)
        layout.addWidget(self.btn_asignar_existente)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        layout.addWidget(sep2)

        grp_b = QGroupBox("B) Crear cliente rápido")
        lay_b = QFormLayout(grp_b)
        self.txt_nombre_rapido   = QLineEdit()
        from modulos.spj_phone_widget import PhoneWidget as _PW
        self.txt_telefono_rapido = _PW(default_country="+52")
        self.txt_nombre_rapido.setPlaceholderText("Nombre completo *")
        lay_b.addRow("Nombre:", self.txt_nombre_rapido)
        lay_b.addRow("Teléfono:", self.txt_telefono_rapido)
        layout.addWidget(grp_b)

        self.btn_crear_rapido = QPushButton("➕ Crear y asignar")
        self.btn_crear_rapido.clicked.connect(self._crear_y_asignar)
        layout.addWidget(self.btn_crear_rapido)

        self.btn_cancelar = QPushButton("✖ Cancelar (continuar sin tarjeta)")
        self.btn_cancelar.clicked.connect(self.reject)
        layout.addWidget(self.btn_cancelar)

        self._cliente_id_sel = None

    def _buscar_cliente_existente(self):
        texto = self.txt_buscar_cliente.text().strip()
        if not texto:
            return
        try:
            from repositories.cliente_repository import ClienteRepository
            cli_repo = ClienteRepository(self.conexion)
            rows = cli_repo.buscar(texto, limit=5)
        except Exception:
            rows = []
        if not rows:
            self.lbl_cliente_encontrado.setText("❌ No encontrado")
            self.lbl_cliente_encontrado.setVisible(True)
            self._cliente_id_sel = None
            self.btn_asignar_existente.setEnabled(False)
            return
        if len(rows) == 1:
            self._seleccionar_cliente(rows[0])
        else:
            items = [f"{r['nombre']} — {r.get('telefono','')}" for r in rows]
            item, ok = QInputDialog.getItem(self, "Seleccionar cliente", "Múltiples resultados:", items, 0, False)
            if ok:
                idx = items.index(item)
                self._seleccionar_cliente(rows[idx])

    def _seleccionar_cliente(self, row):
        # row may be a dict (from ClienteRepository.buscar) or a tuple (legacy)
        if isinstance(row, dict):
            self._cliente_id_sel = row['id']
            self.lbl_cliente_encontrado.setText(f"✓ {row['nombre']}  {row.get('telefono','')}")
        else:
            self._cliente_id_sel = row[0]
            self.lbl_cliente_encontrado.setText(f"✓ {row[1]}  {row[2] or ''}")
        self.lbl_cliente_encontrado.setVisible(True)
        self.btn_asignar_existente.setEnabled(True)

    def _asignar_existente(self):
        if not self._cliente_id_sel: return
        self.resultado = {'cliente_id': self._cliente_id_sel, 'nuevo': False}
        self.accept()

    def _crear_y_asignar(self):
        nombre = self.txt_nombre_rapido.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Error", "El nombre es obligatorio")
            return
        telefono = self.txt_telefono_rapido.get_e164().strip()
        import uuid as _uuid
        qr_code = _uuid.uuid4().hex[:12].upper()
        try:
            from repositories.cliente_repository import ClienteRepository
            cli_repo = ClienteRepository(self.conexion)
            cliente_id = cli_repo.crear(
                nombre=nombre, telefono=telefono or "", codigo_fidelidad=qr_code
            )
            self.resultado = {'cliente_id': cliente_id, 'nuevo': True}
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo crear cliente: {exc}")

# ==============================================================================
# 5a. DIALOGO DE AUTORIZACION PROTEGIDA (descuentos, overrides, etc.)
# ==============================================================================

class _AuthDiscountDialog(QDialog):
    """Enterprise authorization dialog for protected POS operations.

    Replaces raw QInputDialog for PIN entry — provides structured reason
    capture and supervisor PIN in a single, auditable dialog.
    """
    def __init__(self, operacion: str, detalles: str,
                 requiere_pin: bool = True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Autorización Requerida")
        self.setModal(True)
        self.setMinimumWidth(380)
        self._pin: str = ""
        self._motivo: str = ""
        self._requiere_pin = requiere_pin
        self._build_ui(operacion, detalles)

    def _build_ui(self, operacion: str, detalles: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 14, 16, 14)

        hdr = QFrame()
        hdr.setObjectName("authDialogHeader")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(10, 8, 10, 8)
        hdr_lay.setSpacing(8)
        lbl_icon = QLabel("🔒")
        lbl_icon.setObjectName("authDialogIcon")
        lbl_title = QLabel(operacion)
        lbl_title.setObjectName("authDialogTitle")
        hdr_lay.addWidget(lbl_icon)
        hdr_lay.addWidget(lbl_title)
        hdr_lay.addStretch(1)
        layout.addWidget(hdr)

        lbl_det = QLabel(detalles)
        lbl_det.setWordWrap(True)
        lbl_det.setObjectName("authDialogDetail")
        layout.addWidget(lbl_det)

        form = QFormLayout()
        form.setSpacing(8)
        form.setContentsMargins(0, 4, 0, 4)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.txt_motivo = QLineEdit()
        self.txt_motivo.setPlaceholderText("Motivo de la operación...")
        self.txt_motivo.setObjectName("authDialogInput")
        form.addRow("Motivo:", self.txt_motivo)

        if self._requiere_pin:
            self.txt_pin = QLineEdit()
            self.txt_pin.setEchoMode(QLineEdit.Password)
            self.txt_pin.setPlaceholderText("PIN del supervisor")
            self.txt_pin.setMaxLength(8)
            self.txt_pin.setObjectName("authDialogInput")
            self.txt_pin.returnPressed.connect(self._aceptar)
            form.addRow("PIN supervisor:", self.txt_pin)

        layout.addLayout(form)
        layout.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.setMinimumHeight(34)
        btn_ok = QPushButton("✓  Autorizar")
        btn_ok.setObjectName("primaryBtn")
        btn_ok.setMinimumHeight(36)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok, 2)
        layout.addLayout(btn_row)

        btn_ok.clicked.connect(self._aceptar)
        btn_cancel.clicked.connect(self.reject)

    def _aceptar(self):
        if self._requiere_pin:
            pin_field = getattr(self, 'txt_pin', None)
            if not pin_field or not pin_field.text().strip():
                QMessageBox.warning(self, "PIN Requerido",
                                    "Ingresa el PIN de supervisor.")
                return
            self._pin = pin_field.text().strip()
        self._motivo = self.txt_motivo.text().strip()
        self.accept()

    @property
    def pin(self) -> str:
        return self._pin

    @property
    def motivo(self) -> str:
        return self._motivo


# ==============================================================================
# 5. MODULO PRINCIPAL DE VENTAS ENTERPRISE
# ==============================================================================

class ModuloVentas(ModuloBase):
    """Módulo principal de Punto de Venta con báscula automática, temas heredados y Arquitectura Enterprise."""

    # 🛠️ FIX ENTERPRISE: Recibe container en lugar de conexion cruda
    def __init__(self, container, parent: QWidget = None):
        super().__init__(container.db, parent)
        
        self.container = container
        self.conexion = container.db  # alias legacy — usar repos para SQL nuevo
        
        # Estructuras de Venta
        self.compra_actual: List[Dict[str, Any]] = []
        self._ticket_html_cache: str = ""   # cache del último ticket generado
        self._ultima_venta_id: int = 0      # venta_id de la última venta completada
        self.cliente_actual: Optional[Dict[str, Any]] = None
        self.producto_seleccionado: Optional[Dict[str, Any]] = None
        self._selected_card: Optional[ProductCard] = None
        self.totales = {"subtotal": 0.0, "impuestos": 0.0, "total_final": 0.0}
        
        # Gestión de Ventas en Espera
        self.ventas_en_espera: Dict[str, Dict[str, Any]] = {}
        self._ultima_venta_id: int | None = None
        self._ticket_html_cache: str = ""
        self._tiempo_inicio_venta: float | None = None
        
        # Modelo para QCompleter
        self.completer_model = None  # QCompleter removed
        self.productos_cache = []
        
        # Control de báscula
        self.peso_actual = 0.0
        self.peso_estable = 0.0
        self.lecturas_peso = []
        self.bascula_conectada = False
        self.bascula = None
        self.producto_pendiente = None
        self.peso_inicial = 0.0
        self.monitoreo_inicio = 0
        
        self.sucursal_id     = 1
        self.sucursal_nombre = "Principal"
        self._stock_reservas = StockReservationService(self.conexion, branch_id=self.sucursal_id)
        self._reserva_activa_id: Optional[int] = None

        self._theme_initialized = False
        self.gestor_temas = GestorTemas(self.conexion)

        # ── Customer autocomplete ─────────────────────────────────────────
        # Debounce timer: fires 180ms after last keystroke to query DB
        self._cliente_debounce = QTimer(self)
        self._cliente_debounce.setSingleShot(True)
        self._cliente_debounce.setInterval(180)
        self._cliente_debounce.timeout.connect(self._actualizar_sugerencias_cliente)
        self._cliente_completer_model = None   # QStringListModel, lazy-init
        self._cliente_completer = None         # QCompleter, lazy-init

        # ── SCANNER listener ──────────────────────────────────────────────
        self._scanner_buffer: str = ""
        self._scanner_timer  = QTimer(self)
        self._scanner_timer.setSingleShot(True)
        self._scanner_timer.setInterval(80)
        self._scanner_timer.timeout.connect(self._procesar_buffer_scanner)
        self._scanner_minlen: int = 3
        # Contexto de scanner: "producto" | "cliente" | "auto"
        # Determina qué buscar al recibir un código escaneado.
        # Se actualiza automáticamente según el campo que tenga foco.
        self._scan_context: str = "auto"

        # ── Hardware config ────────────────────────────────────────────────
        self._hw_impresora_habilitada = False
        self._hw_cajon_habilitado     = False
        self._hw_bascula_habilitada   = False
        self._hw_impresora_cfg: Dict   = {}
        self._hw_cajon_cfg: Dict       = {}
        self._hw_bascula_cfg: Dict     = {}
        self._cargar_hardware_config()
        self._actualizar_banner_impresora()
        
        # Timers
        self.timer_bascula = QTimer(self)
        self.timer_bascula.setInterval(500)
        
        # Inicialización de la interfaz
        self.init_ui()
        self.conectar_eventos()
        self.cargar_productos_interactivos()
        self.inicializar_completer()
        
        try:
            self.conectar_eventos_sistema()
        except Exception as e:
            logger.warning(f"⚠️ No se pudieron conectar eventos del sistema: {e}")
        
        self.inicializar_bascula()
        self.aplicar_tema_desde_config()

    def aplicar_tema_desde_config(self):
        try:
            tema_actual = self.gestor_temas.obtener_tema_actual()
            self._theme_initialized = True
            logger.info(f"✅ Tema '{tema_actual}' aplicado correctamente")
        except Exception as e:
            logger.error(f"❌ Error aplicando tema: {e}")

    @property
    def _cli_repo(self):
        return getattr(self.container, 'cliente_repo', None)

    @property
    def _prod_repo(self):
        return getattr(self.container, 'producto_repo', None)

    @property
    def _product_catalog_qs(self):
        svc = getattr(self, "_product_catalog_query_service", None)
        if svc is None:
            try:
                from core.services.sales.product_catalog_query_service import ProductCatalogQueryService
                svc = ProductCatalogQueryService(self.conexion)
            except Exception:
                svc = None
            self._product_catalog_query_service = svc
        return svc

    @property
    def _customer_lookup_svc(self):
        svc = getattr(self, "_customer_lookup_service", None)
        if svc is None:
            try:
                from core.services.sales.customer_lookup_service import CustomerLookupService
                svc = CustomerLookupService(self.conexion)
            except Exception:
                svc = None
            self._customer_lookup_service = svc
        return svc

    def set_usuario_actual(self, usuario: str, rol: str) -> None:
        """Activa/desactiva botones según el rol del usuario logueado."""
        self.usuario_actual = usuario
        # Devolución solo para gerente y admin (permiso ventas.cancelar)
        roles_con_devolucion = {"admin", "gerente"}
        if hasattr(self, "btn_devolucion"):
            self.btn_devolucion.setEnabled(rol.lower() in roles_con_devolucion)

    def set_sucursal(self, sucursal_id: int, sucursal_nombre: str):
        self.sucursal_id     = sucursal_id
        self.sucursal_nombre = sucursal_nombre
        self._stock_reservas = StockReservationService(self.conexion, branch_id=self.sucursal_id)
        if hasattr(self, "lbl_estado_terminal"):
            status_text = f"Terminal: ❌ No disponible  |  🏪 {sucursal_nombre}"
            self.lbl_estado_terminal.setText(status_text)
            if hasattr(self, '_btn_terminal_hw'):
                self._btn_terminal_hw.setText(f"💳 {sucursal_nombre}")
                self._btn_terminal_hw.setToolTip(status_text)
        # v13.4: Recargar productos con stock de la sucursal correcta
        try:
            self.cargar_productos_interactivos()
        except Exception:
            pass
        logger.info(f"✅ Ventas → sucursal activa: {sucursal_nombre} (id={sucursal_id})")

    def inicializar_completer(self):
        """Completer removed — real-time search handles this without popup."""
        pass

    def actualizar_completer_model(self):
        try:
            catalog_qs = self._product_catalog_qs
            prod_repo = self._prod_repo
            if catalog_qs:
                rows = catalog_qs.list_visible_products(branch_id=getattr(self, "sucursal_id", 1))
                productos = [(p['nombre'], p.get('codigo_barras', '')) for p in rows]
            elif prod_repo:
                productos = [(p['nombre'], p.get('codigo_barras', '')) for p in prod_repo.get_all()]
            else:
                cursor = self.conexion.cursor()
                cursor.execute("SELECT nombre, COALESCE(codigo_barras,'') FROM productos WHERE COALESCE(oculto,0) = 0")
                productos = cursor.fetchall()
            sugerencias = []
            for nombre, codigo in productos:
                sugerencias.append(nombre)
                if codigo:
                    sugerencias.append(codigo)
            self.completer_model.setStringList(sugerencias)
            self.productos_cache = productos
        except Exception as e:
            logger.error("Error actualizando completer: %s", e)

    def conectar_eventos(self):
        self.txt_busqueda.returnPressed.connect(self.buscar_productos)
        self.btn_buscar.clicked.connect(self.buscar_productos)
        self.btn_limpiar_busqueda.clicked.connect(self.limpiar_busqueda_productos)
        self.txt_busqueda.textChanged.connect(self.buscar_productos_en_tiempo_real)
        self.txt_cliente.returnPressed.connect(self.buscar_cliente)
        self.btn_buscar_cliente.clicked.connect(self.buscar_cliente)
        # Discount removal via table click (cellClicked is reliable for NoEditTriggers tables)
        self.tabla_compra.cellClicked.connect(self._on_cart_cell_clicked)
        # Real-time autocomplete: any keystroke (even 1 char) triggers debounced DB search
        self.txt_cliente.textChanged.connect(self._cliente_textchanged)
        self.btn_agregar_cliente.clicked.connect(self.agregar_cliente)
        self.btn_limpiar_cliente.clicked.connect(self.limpiar_cliente)
        self.btn_cobrar.clicked.connect(self.procesar_pago)
        self.btn_cancelar.clicked.connect(self.cancelar_venta)
        self.btn_devolucion.clicked.connect(self.abrir_devolucion)
        self.btn_suspender.clicked.connect(self.suspender_venta)
        self.btn_reanudar.clicked.connect(self.mostrar_ventas_espera)
        self.timer_bascula.timeout.connect(self.leer_peso)
        
    def conectar_eventos_sistema(self):
        try:
            if hasattr(self.main_window, 'registrar_evento'):
                self.main_window.registrar_evento('producto_creado', self.on_productos_actualizados)
                self.main_window.registrar_evento('producto_actualizado', self.on_productos_actualizados)
                self.main_window.registrar_evento('producto_eliminado', self.on_productos_actualizados)
                self.main_window.registrar_evento('inventario_actualizado', self.on_productos_actualizados)
        except Exception as e:
            pass

    def desconectar_eventos_sistema(self):
        try:
            if hasattr(self.main_window, 'desregistrar_evento'):
                self.main_window.desregistrar_evento('producto_creado', self.on_productos_actualizados)
                self.main_window.desregistrar_evento('producto_actualizado', self.on_productos_actualizados)
                self.main_window.desregistrar_evento('producto_eliminado', self.on_productos_actualizados)
                self.main_window.desregistrar_evento('inventario_actualizado', self.on_productos_actualizados)
        except Exception: pass
            
    def on_productos_actualizados(self, datos):
        self.cargar_productos_interactivos()
        # completer model update skipped

    def init_ui(self):
        self.setWindowTitle("Punto de Venta - Sistema Avanzado")
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── CASHIER INFO BAR ─────────────────────────────────────────────────
        cashier_bar = QFrame()
        cashier_bar.setObjectName("posCashierBar")
        cashier_bar.setFixedHeight(48)
        cb_layout = QHBoxLayout(cashier_bar)
        cb_layout.setContentsMargins(12, 4, 12, 4)
        cb_layout.setSpacing(10)

        self._lbl_pos_title = QLabel("🛒 Punto de Venta")
        self._lbl_pos_title.setObjectName("posCashierTitle")
        cb_layout.addWidget(self._lbl_pos_title)

        self._lbl_cashier_meta = QLabel("")
        self._lbl_cashier_meta.setObjectName("posCashierMeta")
        cb_layout.addWidget(self._lbl_cashier_meta)
        cb_layout.addStretch(1)

        self._lbl_status_badge = QLabel("● Abierto")
        self._lbl_status_badge.setObjectName("posStatusBadge")
        cb_layout.addWidget(self._lbl_status_badge)

        cb_layout.addSpacing(8)

        self._btn_bascula_hw = QPushButton("⚖ Báscula")
        self._btn_bascula_hw.setObjectName("posHWBtn")
        self._btn_bascula_hw.setToolTip("Estado de la báscula")
        cb_layout.addWidget(self._btn_bascula_hw)

        self._btn_terminal_hw = QPushButton("💳 Terminal")
        self._btn_terminal_hw.setObjectName("posHWBtn")
        self._btn_terminal_hw.setToolTip("Estado de la terminal de pago")
        cb_layout.addWidget(self._btn_terminal_hw)

        self._btn_corte_z = QPushButton("📋 Corte Z")
        self._btn_corte_z.setObjectName("posCorteBtn")
        self._btn_corte_z.setToolTip("Realizar corte de caja (Corte Z)")
        self._btn_corte_z.clicked.connect(self._ir_a_caja)
        cb_layout.addWidget(self._btn_corte_z)

        root_layout.addWidget(cashier_bar)

        body = QWidget(self)
        main_layout = QHBoxLayout(body)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        root_layout.addWidget(body, 1)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setProperty("class", "main-splitter")
        splitter.setHandleWidth(3)

        # ── LEFT PANEL: PRODUCTS ─────────────────────────────────────────────
        panel_izquierdo = QWidget()
        layout_izquierdo = QVBoxLayout(panel_izquierdo)
        layout_izquierdo.setSpacing(6)
        layout_izquierdo.setContentsMargins(5, 5, 5, 5)

        # ── SEARCH ROW ───────────────────────────────────────────────────────
        search_row = QFrame()
        search_row.setObjectName("posSearchFrame")
        search_layout = QHBoxLayout(search_row)
        search_layout.setContentsMargins(8, 6, 8, 6)
        search_layout.setSpacing(6)

        # Barcode icon button (visual cue)
        btn_barcode = QPushButton("▦")
        btn_barcode.setObjectName("posBarcodeBtn")
        btn_barcode.setFixedSize(36, 36)
        btn_barcode.setToolTip("Scanner de código de barras activo")
        search_layout.addWidget(btn_barcode)

        self.txt_busqueda = QLineEdit()
        self.txt_busqueda.setPlaceholderText("Escanear código o escribir nombre del producto...")
        self.txt_busqueda.setObjectName("posSearchInput")
        self.txt_busqueda.setProperty("class", "search-input")
        self.txt_busqueda.setToolTip(
            "Campo activo para PRODUCTOS\n"
            "Cuando este campo tenga foco, el scanner agrega productos al carrito.")
        self._filter_busqueda = _ScanContextFilter(self, "producto", self.txt_busqueda)
        self.txt_busqueda.installEventFilter(self._filter_busqueda)
        self._search_frame = search_row
        search_layout.addWidget(self.txt_busqueda, 1)

        self.btn_buscar = QPushButton("Buscar")
        self.btn_buscar.setMinimumWidth(72)
        self.btn_buscar.setObjectName("searchBtn")
        self.btn_limpiar_busqueda = QPushButton("✕")
        self.btn_limpiar_busqueda.setToolTip("Limpiar búsqueda")
        self.btn_limpiar_busqueda.setFixedSize(32, 32)
        self.btn_limpiar_busqueda.setObjectName("deleteBtn")

        # Persistent scanner state badge — ACTIVO / CLIENTE / LIBRE
        self._lbl_scan_state = QLabel("LIBRE")
        self._lbl_scan_state.setObjectName("posScanStateWaiting")
        self._lbl_scan_state.setFixedHeight(22)
        self._lbl_scan_state.setToolTip(
            "Estado del scanner.\n"
            "ACTIVO → El scanner agrega productos al carrito.\n"
            "CLIENTE → El scanner carga cliente o tarjeta.\n"
            "LIBRE → Sin campo activo.")

        search_layout.addWidget(self.btn_buscar)
        search_layout.addWidget(self.btn_limpiar_busqueda)
        search_layout.addWidget(self._lbl_scan_state)
        layout_izquierdo.addWidget(search_row)

        # Scanner result notification — shown briefly after each scan event
        self.lbl_scanner_notif = QLabel("")
        self.lbl_scanner_notif.setObjectName("posScannerNotif")
        self.lbl_scanner_notif.setWordWrap(False)
        self.lbl_scanner_notif.setFixedHeight(24)
        self.lbl_scanner_notif.hide()
        layout_izquierdo.addWidget(self.lbl_scanner_notif)

        # ── CATEGORY ROW (pills + view toggles) ─────────────────────────────
        category_row_frame = QFrame()
        category_row_frame.setObjectName("posCategoryRow")
        cat_row_lay = QHBoxLayout(category_row_frame)
        cat_row_lay.setContentsMargins(4, 4, 4, 4)
        cat_row_lay.setSpacing(4)

        # Scrollable pill area
        self._category_scroll = QScrollArea()
        self._category_scroll.setObjectName("posCategoryScroll")
        self._category_scroll.setWidgetResizable(True)
        self._category_scroll.setFixedHeight(32)
        self._category_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._category_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._category_container = QWidget()
        self._category_layout = QHBoxLayout(self._category_container)
        self._category_layout.setContentsMargins(0, 0, 0, 0)
        self._category_layout.setSpacing(4)
        self._category_layout.addStretch(1)
        self._category_scroll.setWidget(self._category_container)
        self._pos_categoria_activa = ""
        self._pos_category_buttons = {}
        cat_row_lay.addWidget(self._category_scroll, 1)

        # View toggle buttons — icon-only, visually distinct from category pills
        self._btn_view_grid = QPushButton("⊞")
        self._btn_view_grid.setObjectName("posViewIconBtn")
        self._btn_view_grid.setFixedSize(28, 28)
        self._btn_view_grid.setToolTip("Vista de cuadrícula")
        self._btn_view_grid.setCheckable(True)
        self._btn_view_grid.setChecked(True)

        self._btn_view_list = QPushButton("☰")
        self._btn_view_list.setObjectName("posViewIconBtn")
        self._btn_view_list.setFixedSize(28, 28)
        self._btn_view_list.setToolTip("Vista de lista (próximamente)")
        self._btn_view_list.setEnabled(False)

        cat_row_lay.addWidget(self._btn_view_grid)
        cat_row_lay.addWidget(self._btn_view_list)
        layout_izquierdo.addWidget(category_row_frame)

        # Product grid
        group_productos = QGroupBox()
        group_productos.setProperty("class", "products-group")
        productos_layout = QVBoxLayout(group_productos)
        productos_layout.setContentsMargins(4, 4, 4, 4)

        self.scroll_area_productos = QScrollArea()
        self.scroll_area_productos.setWidgetResizable(True)
        self.scroll_area_productos.setProperty("class", "products-scroll")
        self.scroll_area_productos.setMinimumHeight(300)

        self.scroll_content = QWidget()
        self.grid_productos = QGridLayout(self.scroll_content)
        self.grid_productos.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.grid_productos.setSpacing(10)
        self.grid_productos.setContentsMargins(10, 10, 10, 10)
        self.scroll_area_productos.setWidget(self.scroll_content)
        productos_layout.addWidget(self.scroll_area_productos)
        layout_izquierdo.addWidget(group_productos, 1)

        # API-compat orphaned labels — status is mirrored to HW buttons in header bar
        self.lbl_estado_bascula = QLabel("⚖ Báscula: ❌ No conectada")
        self.lbl_estado_terminal = QLabel("💳 Terminal: ❌ No disponible")

        # ── RIGHT PANEL: CART & CHECKOUT ─────────────────────────────────────
        panel_derecho = QWidget()
        panel_derecho.setMinimumWidth(380)
        panel_derecho.setMaximumWidth(600)
        layout_derecho = QVBoxLayout(panel_derecho)
        layout_derecho.setSpacing(0)
        layout_derecho.setContentsMargins(0, 0, 0, 0)

        # ── CART HEADER BAR ──────────────────────────────────────────────────
        cart_header = QFrame()
        cart_header.setObjectName("posCartHeader")
        cart_header.setFixedHeight(42)
        ch_lay = QHBoxLayout(cart_header)
        ch_lay.setContentsMargins(14, 0, 10, 0)
        ch_lay.setSpacing(4)
        lbl_cart_title = QLabel("CARRITO DE COMPRA")
        lbl_cart_title.setObjectName("posCartHeaderTitle")
        ch_lay.addWidget(lbl_cart_title)
        ch_lay.addStretch(1)
        btn_cart_menu = QPushButton("⋮")
        btn_cart_menu.setObjectName("posCartIconBtn")
        btn_cart_menu.setFixedSize(28, 28)
        btn_cart_menu.setToolTip("Opciones del carrito")
        btn_cart_clear = QPushButton("🗑")
        btn_cart_clear.setObjectName("posCartIconBtn")
        btn_cart_clear.setFixedSize(28, 28)
        btn_cart_clear.setToolTip("Vaciar carrito")
        btn_cart_clear.clicked.connect(self.cancelar_venta)
        ch_lay.addWidget(btn_cart_menu)
        ch_lay.addWidget(btn_cart_clear)
        layout_derecho.addWidget(cart_header)

        # ── CART TABLE — flexible, absorbs all available vertical space ───────
        self._carrito_group = QGroupBox()
        self._carrito_group.setObjectName("posCartGroup")
        self._carrito_group.setProperty("class", "venta-group")
        self._carrito_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._carrito_group.setMinimumHeight(160)
        carrito_layout = QVBoxLayout(self._carrito_group)
        carrito_layout.setContentsMargins(0, 0, 0, 0)
        carrito_layout.setSpacing(0)

        self.tabla_compra = QTableWidget()
        self.tabla_compra.setProperty("class", "tabla-carrito")
        self.tabla_compra.setObjectName("posCartTable")
        self.tabla_compra.setColumnCount(7)
        self.tabla_compra.setHorizontalHeaderLabels(
            ["Producto", "Cant.", "Precio", "Desc.", "Total", "", ""])
        self.tabla_compra.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_compra.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_compra.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tabla_compra.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 48px rows — tall enough for 2-line product cells (name + code)
        self.tabla_compra.verticalHeader().setDefaultSectionSize(48)
        self.tabla_compra.verticalHeader().setMinimumSectionSize(48)
        self.tabla_compra.verticalHeader().setVisible(False)
        self.tabla_compra.setColumnWidth(1, 46)
        self.tabla_compra.setColumnWidth(2, 58)
        self.tabla_compra.setColumnWidth(3, 52)
        self.tabla_compra.setColumnWidth(4, 62)
        self.tabla_compra.setColumnWidth(5, 30)
        self.tabla_compra.setColumnWidth(6, 30)
        self.tabla_compra.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabla_compra.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.tabla_compra.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed)
        self.tabla_compra.setMinimumHeight(3 * 48 + 28)
        self.tabla_compra.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tabla_compra.setFrameShape(QFrame.NoFrame)
        # ISSUE 1 FIX: Padding inferior para que la última fila no quede tapada por el panel de totales
        self.tabla_compra.setContentsMargins(0, 0, 0, 4)
        carrito_layout.addWidget(self.tabla_compra, 1)

        # Empty-cart placeholder
        self._lbl_cart_empty = QLabel(
            "Carrito vacío\n\n"
            "• Escanea un código de barras\n"
            "• Selecciona un producto del catálogo\n"
            "• Escribe el nombre en el buscador"
        )
        self._lbl_cart_empty.setObjectName("posCartEmpty")
        self._lbl_cart_empty.setAlignment(Qt.AlignCenter)
        self._lbl_cart_empty.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._lbl_cart_empty.show()
        self.tabla_compra.hide()
        carrito_layout.addWidget(self._lbl_cart_empty, 1)

        self.lbl_info_carrito = QLabel("")
        self.lbl_info_carrito.setMaximumHeight(0)
        self.lbl_info_carrito.setVisible(False)
        layout_derecho.addWidget(self._carrito_group, 1)

        # ── CLIENT SECTION (compact display; txt_cliente hidden for scanner) ──
        group_cliente = QFrame()
        group_cliente.setObjectName("posClientFrame")
        group_cliente.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        cliente_layout = QVBoxLayout(group_cliente)
        cliente_layout.setContentsMargins(12, 6, 12, 6)
        cliente_layout.setSpacing(3)

        # Section label
        _lbl_cliente_sec = QLabel("Cliente")
        _lbl_cliente_sec.setObjectName("posClientSectionLabel")
        cliente_layout.addWidget(_lbl_cliente_sec)

        # Hidden scanner field — scanner targets this when context = "cliente"
        self.txt_cliente = QLineEdit()
        self.txt_cliente.setPlaceholderText("💳 Escanear tarjeta o buscar cliente...")
        self.txt_cliente.setProperty("class", "client-input")
        self.txt_cliente.setToolTip(
            "Campo activo para CLIENTES / TARJETAS\n"
            "Cuando este campo tenga foco, el scanner carga el cliente por tarjeta o ID.")
        self._filter_cliente = _ScanContextFilter(self, "cliente", self.txt_cliente)
        self.txt_cliente.installEventFilter(self._filter_cliente)
        self.txt_cliente.setVisible(False)
        self.txt_cliente.setMaximumHeight(0)

        # Search row (shown when Cambiar is clicked)
        self._client_search_row = QFrame()
        self._client_search_row.setObjectName("posClientSearchRow")
        _csr_lay = QHBoxLayout(self._client_search_row)
        _csr_lay.setContentsMargins(0, 0, 0, 0)
        _csr_lay.setSpacing(4)
        self.btn_buscar_cliente = QPushButton("🔍")
        self.btn_buscar_cliente.setFixedSize(32, 28)
        self.btn_buscar_cliente.setObjectName("searchBtn")
        self.btn_agregar_cliente = QPushButton("➕")
        self.btn_agregar_cliente.setFixedSize(32, 28)
        self.btn_agregar_cliente.setObjectName("addBtn")
        self.btn_limpiar_cliente = QPushButton("✕")
        self.btn_limpiar_cliente.setFixedSize(32, 28)
        self.btn_limpiar_cliente.setObjectName("deleteBtn")
        _csr_lay.addWidget(self.txt_cliente)
        _csr_lay.addWidget(self.btn_buscar_cliente)
        _csr_lay.addWidget(self.btn_agregar_cliente)
        _csr_lay.addWidget(self.btn_limpiar_cliente)
        self._client_search_row.setVisible(False)
        cliente_layout.addWidget(self._client_search_row)

        # Display row — name + pts + Cambiar button
        self._client_display_row = QFrame()
        self._client_display_row.setObjectName("posClientDisplayRow")
        _cdr_lay = QHBoxLayout(self._client_display_row)
        _cdr_lay.setContentsMargins(0, 0, 0, 0)
        _cdr_lay.setSpacing(6)

        _lbl_client_icon = QLabel("👤")
        _lbl_client_icon.setObjectName("posClientIcon")
        _lbl_client_icon.setFixedWidth(18)

        self.lbl_nombre_cliente = QLabel("Público General")
        self.lbl_nombre_cliente.setObjectName("posClientName")
        self.lbl_puntos_cliente = QLabel("+ 0 pts")
        self.lbl_puntos_cliente.setProperty("class", "client-info-highlight")
        self.lbl_telefono_cliente = QLabel("Tel: —")
        self.lbl_telefono_cliente.setProperty("class", "client-info")
        self.lbl_email_cliente = QLabel("")
        self.lbl_email_cliente.setProperty("class", "client-info")
        self.lbl_email_cliente.setVisible(False)

        self._lbl_loyalty_tier = QLabel("")
        self._lbl_loyalty_tier.setObjectName("posLoyaltyTierBadge")
        self._lbl_loyalty_tier.hide()

        _cdr_lay.addWidget(_lbl_client_icon)
        _cdr_lay.addWidget(self.lbl_nombre_cliente)
        _cdr_lay.addWidget(self._lbl_loyalty_tier)
        _cdr_lay.addStretch(1)
        btn_cambiar_cliente = QPushButton("Cambiar")
        btn_cambiar_cliente.setObjectName("posClientChangeBtn")
        btn_cambiar_cliente.setFixedHeight(24)
        btn_cambiar_cliente.setToolTip("Buscar o cambiar el cliente de esta venta")
        def _toggle_client_search():
            visible = not self._client_search_row.isVisible()
            self._client_search_row.setVisible(visible)
            self.txt_cliente.setVisible(visible)
            self.txt_cliente.setMaximumHeight(16777215 if visible else 0)
            self._client_display_row.setVisible(not visible)
            if visible:
                self.txt_cliente.setFocus()
                self.txt_cliente.selectAll()
        btn_cambiar_cliente.clicked.connect(_toggle_client_search)
        _cdr_lay.addWidget(btn_cambiar_cliente)
        cliente_layout.addWidget(self._client_display_row)

        # Second info line: pts + tel
        _info2_lay = QHBoxLayout()
        _info2_lay.setContentsMargins(0, 0, 0, 0)
        _info2_lay.setSpacing(8)
        _info2_lay.addWidget(self.lbl_puntos_cliente)
        _info2_lay.addWidget(self.lbl_telefono_cliente)
        _info2_lay.addStretch(1)
        cliente_layout.addLayout(_info2_lay)
        layout_derecho.addWidget(group_cliente)

        # ── TOTALS BREAKDOWN ──────────────────────────────────────────────────
        totals_card = QFrame()
        totals_card.setObjectName("posTotalsCard")
        totals_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        totals_layout = QVBoxLayout(totals_card)
        totals_layout.setContentsMargins(12, 8, 12, 8)
        totals_layout.setSpacing(4)

        row_sub = QHBoxLayout()
        row_sub.setSpacing(4)
        lbl_sub_label = QLabel("Subtotal")
        lbl_sub_label.setObjectName("posTotalsRowLabel")
        self._lbl_subtotal_val = QLabel("$0.00")
        self._lbl_subtotal_val.setObjectName("posTotalsRowValue")
        self._lbl_subtotal_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_sub.addWidget(lbl_sub_label)
        row_sub.addStretch(1)
        row_sub.addWidget(self._lbl_subtotal_val)
        totals_layout.addLayout(row_sub)

        self._row_discount_widget = QWidget()
        row_disc = QHBoxLayout(self._row_discount_widget)
        row_disc.setContentsMargins(0, 0, 0, 0)
        row_disc.setSpacing(4)
        self._lbl_descuento_label = QLabel("Descuento")
        self._lbl_descuento_label.setObjectName("posDiscountLabel")
        self._lbl_descuento_val = QLabel("")
        self._lbl_descuento_val.setObjectName("posDiscountValue")
        self._lbl_descuento_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_disc.addWidget(self._lbl_descuento_label)
        row_disc.addStretch(1)
        row_disc.addWidget(self._lbl_descuento_val)
        self._row_discount_widget.setVisible(False)
        totals_layout.addWidget(self._row_discount_widget)

        # IVA row — hidden until present
        self._row_iva_widget = QWidget()
        row_iva = QHBoxLayout(self._row_iva_widget)
        row_iva.setContentsMargins(0, 0, 0, 0)
        row_iva.setSpacing(4)
        lbl_iva_label = QLabel("IVA (16%)")
        lbl_iva_label.setObjectName("posTotalsRowLabel")
        self._lbl_iva_val = QLabel("$0.00")
        self._lbl_iva_val.setObjectName("posTotalsRowValue")
        self._lbl_iva_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_iva.addWidget(lbl_iva_label)
        row_iva.addStretch(1)
        row_iva.addWidget(self._lbl_iva_val)
        self._row_iva_widget.setVisible(False)
        totals_layout.addWidget(self._row_iva_widget)

        divider = QFrame()
        divider.setObjectName("posTotalsDivider")
        divider.setFrameShape(QFrame.HLine)
        divider.setFixedHeight(1)
        totals_layout.addWidget(divider)

        # TOTAL row: LEFT [⚖ peso] [pts] [comision?] ── stretch ── RIGHT [TOTAL]
        row_total = QHBoxLayout()
        row_total.setSpacing(6)

        # ── Báscula card (shown only when scale is active) ────────────────
        card_peso = QFrame()
        card_peso.setObjectName("posIndicatorCard")
        card_peso.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        _cp_lay = QVBoxLayout(card_peso)
        _cp_lay.setContentsMargins(6, 3, 6, 3)
        _cp_lay.setSpacing(0)
        _lbl_bsc = QLabel("⚖ Báscula")
        _lbl_bsc.setObjectName("posIndicatorTitle")
        _lbl_bsc.setAlignment(Qt.AlignCenter)
        self.lbl_peso_bascula = QLabel("0.000 kg")
        self.lbl_peso_bascula.setObjectName("posIndicatorValue")
        self.lbl_peso_bascula.setAlignment(Qt.AlignCenter)
        _cp_lay.addWidget(_lbl_bsc)
        _cp_lay.addWidget(self.lbl_peso_bascula)
        card_peso.setVisible(False)
        self._card_peso = card_peso
        row_total.addWidget(card_peso)

        # ── "Puntos a ganar" mini card ────────────────────────────────────
        _pts_card = QFrame()
        _pts_card.setObjectName("posPtsGainCard")
        _pts_card_lay = QVBoxLayout(_pts_card)
        _pts_card_lay.setContentsMargins(6, 3, 6, 3)
        _pts_card_lay.setSpacing(0)
        _lbl_pts_title = QLabel("Puntos a ganar")
        _lbl_pts_title.setObjectName("posPtsGainTitle")
        _lbl_pts_title.setAlignment(Qt.AlignCenter)
        self.lbl_puntos_venta = QLabel("+0 pts")
        self.lbl_puntos_venta.setObjectName("posPtsGainValue")
        self.lbl_puntos_venta.setAlignment(Qt.AlignCenter)
        _pts_card_lay.addWidget(_lbl_pts_title)
        _pts_card_lay.addWidget(self.lbl_puntos_venta)
        row_total.addWidget(_pts_card)

        # ── Comisión card (shown only when commissions config is active) ──
        card_comision = QFrame()
        card_comision.setObjectName("posIndicatorCard")
        card_comision.setVisible(False)
        _cc_lay = QVBoxLayout(card_comision)
        _cc_lay.setContentsMargins(6, 3, 6, 3)
        _cc_lay.setSpacing(0)
        _lbl_com_title = QLabel("Comisión")
        _lbl_com_title.setObjectName("posIndicatorTitle")
        _lbl_com_title.setAlignment(Qt.AlignCenter)
        self.lbl_comision_turno = QLabel("")
        self.lbl_comision_turno.setObjectName("posIndicatorValue")
        self.lbl_comision_turno.setAlignment(Qt.AlignCenter)
        _cc_lay.addWidget(_lbl_com_title)
        _cc_lay.addWidget(self.lbl_comision_turno)
        self._card_comision = card_comision
        row_total.addWidget(card_comision)

        # ── Stretch pushes TOTAL to the right ────────────────────────────
        row_total.addStretch(1)

        # ── TOTAL label + value ───────────────────────────────────────────
        lbl_total_label = QLabel("TOTAL")
        lbl_total_label.setObjectName("posGrandTotalLabel")
        self.lbl_total = QLabel("$0.00")
        self.lbl_total.setObjectName("posGrandTotalValue")
        self.lbl_total.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_total.addWidget(lbl_total_label)
        row_total.addSpacing(8)
        row_total.addWidget(self.lbl_total)
        totals_layout.addLayout(row_total)

        layout_derecho.addWidget(totals_card)

        self._banner_sin_impresora = QLabel(
            "⚠️  Sin impresora configurada — los tickets se guardarán en PDF (carpeta TICKETS/)")
        self._banner_sin_impresora.setProperty("class", "banner-warning caption")
        self._banner_sin_impresora.setWordWrap(True)
        self._banner_sin_impresora.setVisible(False)
        layout_derecho.addWidget(self._banner_sin_impresora)

        # ── DISCOUNT BUTTONS ─────────────────────────────────────────────────
        desc_frame = QFrame()
        desc_frame.setObjectName("posDiscountBar")
        desc_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        desc_lay = QHBoxLayout(desc_frame)
        desc_lay.setContentsMargins(8, 5, 8, 5)
        desc_lay.setSpacing(5)
        # ISSUE 3 FIX: Descuentos → ROJO BRILLANTE (#ef4444) según tokens semánticos
        # variant="danger" activa el selector QPushButton[variant="danger"] del QSS global
        for pct in [5, 10, 15, 20]:
            btn_d = QPushButton(f"{pct}%")
            btn_d.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn_d.setMinimumHeight(30)
            btn_d.setToolTip(f"Aplicar {pct}% de descuento al ítem seleccionado")
            btn_d.setObjectName("posDiscountBtn")
            btn_d.setProperty("variant", "danger")
            btn_d.clicked.connect(lambda _, p=pct: self._descuento_rapido(p))
            desc_lay.addWidget(btn_d)
        # ISSUE 3 FIX: "Personalizado" → AZUL (variant=primary = editar/configurar)
        btn_custom = QPushButton("Personalizado")
        btn_custom.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn_custom.setMinimumHeight(30)
        btn_custom.setToolTip("Descuento personalizado")
        btn_custom.setObjectName("posDiscountCustomBtn")
        btn_custom.setProperty("variant", "primary")
        btn_custom.clicked.connect(lambda: self._descuento_custom())
        desc_lay.addWidget(btn_custom)
        layout_derecho.addWidget(desc_frame)

        # ── PRIMARY TRANSACTION ACTIONS ──────────────────────────────────────
        group_acciones = QFrame()
        group_acciones.setObjectName("posCobrarFrame")
        group_acciones.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        acciones_layout = QVBoxLayout(group_acciones)
        acciones_layout.setContentsMargins(8, 6, 8, 6)
        acciones_layout.setSpacing(5)

        # COBRAR — dominant full-width green button with F9 badge inside
        self.btn_cobrar = _FKeyButton("💳  COBRAR  $0.00", "F9", self)
        self.btn_cobrar.setObjectName("btnCobrarPOS")
        self.btn_cobrar.setProperty("class", "success")
        self.btn_cobrar.setProperty("fill_parent", True)
        self.btn_cobrar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_cobrar.setMinimumHeight(48)
        self.btn_cobrar.setToolTip("Procesar el pago de la venta (F9)")
        acciones_layout.addWidget(self.btn_cobrar)

        # Row 1: Suspender | Reanudar | Cancelar (F-key badge inside each button)
        row_secondary = QHBoxLayout()
        row_secondary.setSpacing(4)
        self.btn_suspender = _FKeyButton("⏸ Suspender", "F6", self)
        self.btn_suspender.setObjectName("warningBtn")
        self.btn_suspender.setProperty("class", "warning")
        self.btn_suspender.setToolTip("Suspender venta (F6)")
        self.btn_reanudar = _FKeyButton("▶ Reanudar (0)", "F7", self)
        self.btn_reanudar.setObjectName("posActionBtn")
        self.btn_reanudar.setProperty("class", "primary")
        self.btn_reanudar.setToolTip("Reanudar venta suspendida (F7)")
        self.btn_cancelar = _FKeyButton("✕ Cancelar", "F8", self)
        self.btn_cancelar.setObjectName("dangerBtn")
        self.btn_cancelar.setProperty("class", "danger")
        self.btn_cancelar.setToolTip("Cancelar venta (F8)")
        for _b in (self.btn_suspender, self.btn_reanudar, self.btn_cancelar):
            _b.setProperty("fill_parent", True)
            _b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            _b.setMinimumHeight(34)
            row_secondary.addWidget(_b)
        acciones_layout.addLayout(row_secondary)

        layout_derecho.addWidget(group_acciones)

        # ── UTILITY ACTIONS ROW ───────────────────────────────────────────────
        group_utilidad = QFrame()
        group_utilidad.setObjectName("posUtilBar")
        group_utilidad.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        utilidad_layout = QHBoxLayout(group_utilidad)
        utilidad_layout.setContentsMargins(8, 4, 8, 4)
        utilidad_layout.setSpacing(4)

        self.btn_devolucion = _FKeyButton("↩ Devolución", "F10", self)
        self.btn_devolucion.setObjectName("posUtilBtn")
        self.btn_devolucion.setEnabled(False)
        self.btn_devolucion.setToolTip("Cancelar o devolver una venta anterior (requiere permiso) — F10")
        self.btn_factura = _FKeyButton("🧾 Factura", "F11", self)
        self.btn_factura.setObjectName("posUtilBtn")
        self.btn_factura.setEnabled(False)
        self.btn_factura.setToolTip("Generar CFDI de la última venta — F11")
        self.btn_factura.clicked.connect(self._generar_factura)
        self.btn_reimprimir = _FKeyButton("🖨️ Reimpr.", "F12", self)
        self.btn_reimprimir.setObjectName("posUtilBtn")
        self.btn_reimprimir.setEnabled(False)
        self.btn_reimprimir.setToolTip("Reimprimir el ticket de la última venta — F12")
        self.btn_reimprimir.clicked.connect(self._reimprimir_ultima_venta)

        for _b in (self.btn_devolucion, self.btn_factura, self.btn_reimprimir):
            _b.setProperty("fill_parent", True)
            _b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            _b.setMinimumHeight(30)
            utilidad_layout.addWidget(_b)

        layout_derecho.addWidget(group_utilidad)

        splitter.addWidget(panel_izquierdo)
        splitter.addWidget(panel_derecho)
        splitter.setStretchFactor(0, 1)   # left panel absorbs extra width on maximize
        splitter.setStretchFactor(1, 0)   # right panel holds preferred width
        splitter.setSizes([620, 460])
        main_layout.addWidget(splitter)
        self._normalizar_botones_principales()
        self._pos_ui_ready = True          # guard for resizeEvent / recalcular_grid
        QTimer.singleShot(0, self._cargar_categorias)

    def _normalizar_botones_principales(self):
        """
        Evita que botones se estiren al ancho completo en layouts verticales.
        Excluye botones marcados con la propiedad 'fill_parent' para que las
        acciones primarias (cobrar, suspender, etc.) llenen su QGroupBox.
        """
        for btn in self.findChildren(QPushButton):
            if btn.property("fill_parent"):
                continue
            # Preserve compact icon-buttons already configured at 40px.
            if btn.minimumWidth() and btn.minimumWidth() <= 45:
                continue
            if btn.maximumWidth() == 16777215:
                btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            if btn.minimumHeight() < 32:
                btn.setMinimumHeight(32)

    # ── RESPONSIVE LAYOUT ────────────────────────────────────────────────────

    def resizeEvent(self, event):
        """Debounced grid reflow on window resize / maximize."""
        super().resizeEvent(event)
        # Ignore resize events that arrive before init_ui() finishes
        if not getattr(self, '_pos_ui_ready', False):
            return
        if not hasattr(self, '_grid_resize_timer'):
            self._grid_resize_timer = QTimer(self)
            self._grid_resize_timer.setSingleShot(True)
            self._grid_resize_timer.timeout.connect(self._recalcular_grid)
        self._grid_resize_timer.start(150)   # 150 ms debounce — no paint storms

    def _recalcular_grid(self):
        """Reflow product grid columns after resize without losing filter state."""
        if not getattr(self, '_pos_ui_ready', False):
            return
        if not hasattr(self, 'scroll_area_productos'):
            return
        try:
            filtro = self.txt_busqueda.text().strip() if hasattr(self, 'txt_busqueda') else ''
            cat = getattr(self, '_pos_categoria_activa', '')
            self._selected_card = None  # cards rebuilt; reset selection reference
            self.cargar_productos_interactivos(filtro, categoria=cat)
        except RuntimeError:
            pass

    # ── NAVIGATION ───────────────────────────────────────────────────────────

    def _ir_a_caja(self):
        """Navega al módulo de Caja/Cortes Z a través de la ventana principal."""
        try:
            top = self.window()
            if hasattr(top, 'manejar_navegacion'):
                top.manejar_navegacion("CAJA")
        except Exception as e:
            logger.debug("_ir_a_caja: %s", e)

    def _set_bascula_status(self, text: str):
        """Update status label and mirror abbreviated text to HW button."""
        self.lbl_estado_bascula.setText(text)
        if hasattr(self, '_btn_bascula_hw'):
            short = text.replace("Báscula: ", "⚖ ").replace("Basic: ", "⚖ ")
            self._btn_bascula_hw.setText(short)
            self._btn_bascula_hw.setToolTip(text)

    # ── CATEGORY TABS ────────────────────────────────────────────────────────

    def _cargar_categorias(self) -> None:
        """Load unique product categories from DB and build the tab bar."""
        # Guard: layout may be gone if widget is torn down before timer fires
        try:
            if not hasattr(self, '_category_layout'):
                return
            self._category_layout.count()   # raises RuntimeError if C++ object deleted
        except RuntimeError:
            return

        categorias = [""]  # "" = Todos
        try:
            catalog_qs = self._product_catalog_qs
            prod_repo = self._prod_repo
            if catalog_qs:
                categorias += catalog_qs.get_categories()
            elif prod_repo:
                categorias += prod_repo.get_categories()
            else:
                rows = self.conexion.execute(
                    "SELECT DISTINCT COALESCE(categoria,'') FROM productos "
                    "WHERE COALESCE(oculto,0)=0 AND COALESCE(activo,1)=1 "
                    "AND categoria IS NOT NULL AND categoria != '' "
                    "ORDER BY categoria"
                ).fetchall()
                for row in rows:
                    cat = row[0] if not hasattr(row, 'keys') else row['COALESCE(categoria,\'\')']
                    if cat:
                        categorias.append(cat)
        except Exception as e:
            logger.debug("_cargar_categorias: %s", e)

        # Remove all existing buttons (except stretch)
        while self._category_layout.count() > 1:
            item = self._category_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
        self._pos_category_buttons.clear()

        labels = {cat: ("Todos" if cat == "" else cat) for cat in categorias}
        for cat in categorias:
            btn = QPushButton(labels[cat])
            btn.setObjectName("posCategoryBtn")
            btn.setCheckable(False)
            btn.setProperty("active", cat == self._pos_categoria_activa)
            btn.clicked.connect(lambda checked=False, c=cat: self._filtrar_por_categoria(c))
            self._category_layout.insertWidget(self._category_layout.count() - 1, btn)
            self._pos_category_buttons[cat] = btn

    def _filtrar_por_categoria(self, categoria: str) -> None:
        """Filter the product grid by category. '' means show all."""
        self._pos_categoria_activa = categoria
        for cat, btn in self._pos_category_buttons.items():
            btn.setProperty("active", cat == categoria)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        filtro_texto = self.txt_busqueda.text().strip()
        self.cargar_productos_interactivos(filtro_texto, categoria=categoria)

    # ── CASHIER INFO ─────────────────────────────────────────────────────────

    def set_cajero_info(self, caja: str = "", cajero: str = "",
                        turno: str = "", estado: str = "Abierto") -> None:
        """Update the cashier info bar (called from main_window after login)."""
        if not hasattr(self, '_lbl_cashier_meta'):
            return
        parts = [p for p in [caja, cajero, turno] if p]
        self._lbl_cashier_meta.setText("  |  ".join(parts))
        if hasattr(self, '_lbl_status_badge'):
            self._lbl_status_badge.setText(f"● {estado}")

    def limpiar_busqueda_productos(self):
        self.txt_busqueda.clear()
        cat = getattr(self, '_pos_categoria_activa', '')
        self.cargar_productos_interactivos(categoria=cat)

    def buscar_productos_en_tiempo_real(self, texto: str):
        if len(texto.strip()) >= 2:
            cat = getattr(self, '_pos_categoria_activa', '')
            self.cargar_productos_interactivos(texto.strip(), categoria=cat)

    def cargar_productos_interactivos(self, filtro: str = "", categoria: str = ""):
        for i in reversed(range(self.grid_productos.count())):
            widget = self.grid_productos.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        try:
            catalog_qs = self._product_catalog_qs
            if catalog_qs:
                productos = catalog_qs.list_visible_products(
                    branch_id=self.sucursal_id, filtro=filtro, categoria=categoria
                )
            else:
                cursor = self.conexion.cursor()
                # DEPRECATED fallback: SQL directo legacy
                query = """
                    SELECT p.id, p.nombre, p.precio,
                           COALESCE(bi.quantity, p.existencia, 0) as stock_sucursal,
                           p.unidad, p.categoria,
                           p.stock_minimo, p.imagen_path, p.es_compuesto, p.es_subproducto,
                           COALESCE(p.codigo_barras,'') as codigo_barras,
                           COALESCE(p.codigo,'') as codigo
                    FROM productos p
                    LEFT JOIN branch_inventory bi ON bi.product_id=p.id AND bi.branch_id=?
                    WHERE p.oculto = 0 AND COALESCE(p.activo,1) = 1
                """
                params = [self.sucursal_id]
                if filtro:
                    query += """ AND (p.nombre LIKE ? OR p.id = ? OR p.categoria LIKE ?
                                 OR COALESCE(p.codigo_barras,'') = ? OR COALESCE(p.codigo,'') = ?)"""
                    params += [f'%{filtro}%', filtro, f'%{filtro}%', filtro, filtro]
                if categoria:
                    query += " AND COALESCE(p.categoria,'') = ?"
                    params.append(categoria)
                query += " ORDER BY p.nombre"
                cursor.execute(query, params)
                productos = cursor.fetchall()

            # Responsive column count: fill available viewport width with fixed-width cards
            _spacing = self.grid_productos.spacing()
            _card_cell = ProductCard.CARD_W + _spacing   # card fixed width + one gap
            _vp_w = self.scroll_area_productos.viewport().width()
            if _vp_w < 40:
                # Viewport not yet laid out; approximate from scroll area minus scrollbar
                _vp_w = max(300, self.scroll_area_productos.width() - 22)
            col_count = max(2, _vp_w // _card_cell)

            for i, producto in enumerate(productos):
                if isinstance(producto, dict):
                    producto_data = producto
                else:
                    producto_data = {
                        'id': producto[0],
                        'nombre': producto[1],
                        'precio': float(producto[2]),
                        'existencia': float(producto[3]),
                        'unidad': producto[4],
                        'categoria': producto[5],
                        'stock_minimo': float(producto[6]),
                        'imagen_path': producto[7],
                        'es_compuesto': producto[8],
                        'es_subproducto': producto[9],
                        'codigo_barras': producto[10],
                        'codigo': producto[11]
                    }

                card = ProductCard(producto_data)
                card.product_selected.connect(self.seleccionar_producto)

                row = i // col_count
                col = i % col_count
                self.grid_productos.addWidget(card, row, col)

        except sqlite3.Error as e:
            self.mostrar_mensaje("Error", f"Error al cargar productos: {str(e)}", QMessageBox.Critical)

    def buscar_productos(self):
        filtro = self.txt_busqueda.text().strip()
        self.cargar_productos_interactivos(filtro)

    def seleccionar_producto(self, producto: Dict[str, Any]):
        if self._selected_card:
            self._selected_card.set_selected(False)
            
        self._selected_card = self.sender()
        if self._selected_card:
            self._selected_card.set_selected(True)
            
        self.producto_seleccionado = producto
        unidad = producto['unidad'].lower()
        
        if any(peso_keyword in unidad for peso_keyword in ['kg', 'kilogramo', 'kilo', 'gramo', 'gr']):
            if self._hw_bascula_habilitada and getattr(self, 'bascula_conectada', False):
                self.iniciar_monitoreo_peso(producto)
            else:
                self._solicitar_peso_manual_producto(producto)
        else:
            self.agregar_producto_por_unidad(producto)

    def _solicitar_peso_manual_producto(self, producto: Dict[str, Any]):
        """Direct manual weight entry — used when scale is disabled or not connected."""
        nombre = producto.get('nombre', '')
        unidad = producto.get('unidad', 'kg')
        cantidad, ok = QInputDialog.getDouble(
            self,
            f"Peso manual — {nombre}",
            f"Báscula no activa. Ingresa el peso ({unidad}):",
            value=0.500,
            min=0.001,
            max=9999.0,
            decimals=3,
        )
        if ok and cantidad > 0:
            self.agregar_producto_directo(producto, cantidad)
        else:
            self.limpiar_seleccion_producto()

    def _actualizar_banner_impresora(self) -> None:
        """Shows/hides the 'no printer' warning banner."""
        if not hasattr(self, '_banner_sin_impresora'):
            return
        tiene_impresora = self._hw_impresora_habilitada
        # v13.4: check via PrinterService
        ps = getattr(self.container, 'printer_service', None) if hasattr(self, 'container') else None
        if ps and ps.has_ticket_printer():
            tiene_impresora = True
        self._banner_sin_impresora.setVisible(not tiene_impresora)

    def _cargar_hardware_config(self) -> None:
        """Load hardware config from DB. Uses 'activo' column (not 'habilitado')."""
        try:
            rows = self.conexion.execute(
                "SELECT tipo, COALESCE(activo,1) as activo, configuraciones FROM hardware_config"
            ).fetchall()
            for row in rows:
                tipo     = row[0] if not hasattr(row, 'keys') else row['tipo']
                hab      = row[1] if not hasattr(row, 'keys') else row['activo']
                cfg_json = row[2] if not hasattr(row, 'keys') else row['configuraciones']
                try:
                    cfg = json.loads(cfg_json) if cfg_json else {}
                except Exception:
                    cfg = {}
                if tipo in ("impresora", "ticket"):
                    self._hw_impresora_habilitada = bool(hab)
                    self._hw_impresora_cfg        = cfg
                elif tipo == "cajon":
                    self._hw_cajon_habilitado = bool(hab)
                    self._hw_cajon_cfg        = cfg
                elif tipo == "scanner":
                    self._scanner_minlen = int(cfg.get("min_len", 3))
                    debounce = int(cfg.get("debounce_ms", 80))
                    self._scanner_timer.setInterval(debounce)
                elif tipo == "bascula":
                    self._hw_bascula_habilitada = bool(hab)
                    self._hw_bascula_cfg = cfg
            import logging
            logging.getLogger(__name__).debug(
                "HW config loaded: impresora=%s cajon=%s",
                self._hw_impresora_habilitada, self._hw_cajon_habilitado)
            self._actualizar_banner_impresora()
        except Exception as _e:
            import logging
            logging.getLogger(__name__).warning("_cargar_hardware_config: %s", _e)

    def keyPressEvent(self, event) -> None:
        """
        Captura keystrokes del módulo POS.

        Lógica de contexto:
          - Si un QLineEdit tiene foco (txt_busqueda o txt_cliente), le entrega
            los caracteres directamente y actualiza _scan_context.
          - Si ninguno tiene foco (foco en tabla, botones, etc.), acumula en
            el buffer de scanner HID y lo procesa al recibir Enter.
        """
        from PyQt5.QtWidgets import QLineEdit as _QLE
        key  = event.key()
        text = event.text()

        # ── Detectar qué campo tiene foco y actualizar contexto ──────────────
        focused = self.focusWidget()

        if isinstance(focused, _QLE):
            # El foco está en un campo de texto: dejar que Qt maneje el evento
            # normalmente. Pero si es un scanner (Enter rápido), procesar buffer.
            if key in (Qt.Key_Return, Qt.Key_Enter):
                buf = self._scanner_buffer.strip()
                if buf:
                    self._scanner_timer.stop()
                    self._scanner_buffer = ""
                    # Usar el contexto del campo activo
                    if focused is self.txt_cliente:
                        self._scan_context = "cliente"
                    elif focused is self.txt_busqueda:
                        self._scan_context = "producto"
                    self._procesar_scanner_con_codigo(buf)
                    return
                # Enter normal en un campo — procesar su acción
                super().keyPressEvent(event)
                return

            if text and text.isprintable():
                # Acumular en buffer de scanner (para detección de velocidad HID)
                self._scanner_buffer += text
                self._scanner_timer.start()
                # Actualizar contexto según campo activo
                if focused is self.txt_cliente:
                    self._scan_context = "cliente"
                elif focused is self.txt_busqueda:
                    self._scan_context = "producto"
                # Dejar caer al handler normal de Qt (escribe en el campo)
                super().keyPressEvent(event)
                return
            super().keyPressEvent(event)
            return

        # ── Sin foco en QLineEdit: modo scanner puro ─────────────────────────
        # El scanner HID escribe sin que ningún campo esté activo.
        # Acumular en buffer y procesar en modo "auto" al recibir Enter.
        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
            if self._scanner_buffer:
                self._scanner_timer.stop()
                codigo = self._scanner_buffer.strip()
                self._scanner_buffer = ""
                self._procesar_scanner_con_codigo(codigo)
            else:
                super().keyPressEvent(event)
            return

        if text and text.isprintable():
            self._scanner_buffer += text
            self._scanner_timer.start()
            return

        super().keyPressEvent(event)

    def _procesar_buffer_scanner(self) -> None:
        """Alias llamado por el timer HID — delega a _procesar_scanner_con_codigo."""
        codigo = self._scanner_buffer.strip()
        self._scanner_buffer = ""
        if not codigo or len(codigo) < self._scanner_minlen:
            return
        self._procesar_scanner_con_codigo(codigo)

    def _procesar_scanner_con_codigo(self, codigo: str) -> None:
        """
        Procesa un código escaneado usando el contexto activo:

        _scan_context == "producto":
            Busca solo en productos (barcode/código interno).
            Si no encuentra, busca en txt_busqueda.

        _scan_context == "cliente":
            Busca solo en clientes y tarjetas de fidelidad.
            Si no encuentra, filtra en txt_cliente.

        _scan_context == "auto":
            Orden inteligente: producto → tarjeta → UUID contenedor → búsqueda.
        """
        if not codigo or len(codigo) < self._scanner_minlen:
            return

        ctx = self._scan_context
        # Fase 2 — helper para telemetría de escaneo sin romper el flujo
        def _log_scan(tipo: str, accion: str, cliente_id=None, producto_id=None):
            try:
                from core.services.qr_parser_service import QRParserService
                usuario = getattr(self, 'usuario_actual', '')
                suc_id  = getattr(self, 'sucursal_id', 1)
                QRParserService.log_scan_raw(
                    self.conexion, codigo, tipo, accion,
                    cliente_id=cliente_id, producto_id=producto_id,
                    sucursal_id=suc_id, usuario=usuario)
            except Exception:
                pass

        try:
            # ════════════════════════════════════════════════════════════════
            # CONTEXTO CLIENTE — el foco estaba en el campo "Cliente"
            # ════════════════════════════════════════════════════════════════
            if ctx == "cliente":
                # v13.4 Fase 1.5: Usar QRParserService para separar client_id de nombre
                qr_svc = getattr(self.container, 'qr_parser', None) if hasattr(self, 'container') else None
                if qr_svc:
                    from core.services.qr_parser_service import QRType
                    qr_result = qr_svc.parse_client_qr(codigo)

                    if qr_result.valid and qr_result.client_id:
                        # QR parseado correctamente → cargar cliente con ID separado
                        puntos = 0
                        nivel = "Bronce"
                        try:
                            _cli = self._cli_repo
                            _row = _cli.get_by_id(qr_result.client_id) if _cli else None
                            if _row:
                                puntos = int(_row.get('puntos', 0) or 0)
                                nivel = _row.get('nivel', 'Bronce') or 'Bronce'
                        except Exception:
                            pass
                        self._cargar_cliente_en_venta(
                            cliente_id=qr_result.client_id,
                            nombre=qr_result.nombre,
                            telefono="",
                            puntos=puntos,
                            nivel=nivel)
                        _log_scan(qr_result.tipo, "cliente_cargado",
                                  cliente_id=qr_result.client_id)
                        return

                    if qr_result.tipo == QRType.TARJETA and qr_result.valid:
                        self._cargar_cliente_en_venta(
                            cliente_id=qr_result.client_id,
                            nombre=qr_result.nombre,
                            puntos=0, nivel="Bronce")
                        _log_scan("tarjeta", "cliente_cargado",
                                  cliente_id=qr_result.client_id)
                        return

                # Fallback: búsqueda tradicional
                # 1a. Resolver tarjeta vía LoyaltyService (sin SQL UI)
                ls = getattr(self.container, 'loyalty_service', None) if hasattr(self, 'container') else None
                row_tarj = ls.resolve_scan(codigo) if ls else {"found": False}
                if row_tarj.get('found'):
                    self._cargar_cliente_en_venta(
                        cliente_id=row_tarj['cliente_id'],
                        nombre=row_tarj['nombre'],
                        telefono=row_tarj.get('telefono', '') or "",
                        puntos=int(row_tarj.get('puntos', 0) or 0),
                        nivel=row_tarj.get('nivel', 'Bronce') or 'Bronce',
                    )
                    _log_scan('tarjeta', 'cliente_cargado', cliente_id=row_tarj['cliente_id'])
                    return

                # 1b. Buscar cliente por ID, teléfono o código QR
                _cli = self._cli_repo
                row_cli = _cli.get_by_scanner(codigo) if _cli else None
                if row_cli:
                    self._cargar_cliente_en_venta(
                        cliente_id=row_cli['id'],
                        nombre=row_cli['nombre'],
                        telefono=row_cli.get('telefono', '') or "",
                        puntos=int(row_cli.get('puntos', 0) or 0),
                        nivel=row_cli.get('nivel', 'Bronce') or 'Bronce',
                    )
                    _log_scan("client_id", "cliente_cargado",
                              cliente_id=row_cli['id'])
                    return

                # 1c. No encontrado — Flujo dual Fase 2 (Plan Maestro SPJ v13.4):
                # Si el código tiene formato de tarjeta (TF-/TAR-/CARD-) →
                # abrir DialogoAgregarCliente con tarjeta_id precargado.
                # Si no, poner en txt_cliente para búsqueda manual.
                import re as _re2
                _es_tarjeta = bool(_re2.match(
                    r'^(TF|TAR|CARD)-[A-Za-z0-9]+$', codigo, _re2.IGNORECASE))
                if _es_tarjeta:
                    _log_scan("tarjeta", "cliente_no_encontrado")
                    self._abrir_nuevo_cliente_con_tarjeta(codigo)
                    return
                _log_scan("busqueda", "cliente_no_encontrado")
                if hasattr(self, 'txt_cliente'):
                    self.txt_cliente.clear()
                    self.txt_cliente.setText(codigo)
                self._mostrar_notif_scanner(
                    f"🔍 Cliente no encontrado: {codigo}", "search")
                return

            # ════════════════════════════════════════════════════════════════
            # CONTEXTO PRODUCTO — el foco estaba en "Buscar Producto"
            # ════════════════════════════════════════════════════════════════
            if ctx == "producto":
                _prod = self._prod_repo
                row_prod = _prod.get_by_barcode(codigo) if _prod else None
                if row_prod:
                    self.agregar_al_carrito(dict(row_prod))
                    self._mostrar_notif_scanner(
                        f"📦 {row_prod['nombre']}", "product")
                    _log_scan("producto", "producto_agregado",
                              producto_id=row_prod['id'])
                    if hasattr(self, 'txt_busqueda'):
                        self.txt_busqueda.clear()
                    return
                # Not found → populate search field
                _log_scan("producto", "producto_no_encontrado")
                if hasattr(self, 'txt_busqueda'):
                    self.txt_busqueda.setText(codigo)
                    self.buscar_productos()
                self._mostrar_notif_scanner(
                    f"🔍 Producto no encontrado: {codigo}", "search")
                return

            # ════════════════════════════════════════════════════════════════
            # CONTEXTO AUTO — sin foco en campo específico
            # Orden: producto → tarjeta → UUID contenedor → búsqueda
            # ════════════════════════════════════════════════════════════════
            # ── 1. Producto ──────────────────────────────────────────────────
            _prod = self._prod_repo
            row_prod = _prod.get_by_barcode(codigo) if _prod else None
            if row_prod:
                self.agregar_al_carrito(dict(row_prod))
                self._mostrar_notif_scanner(f"📦 {row_prod['nombre']}", "product")
                _log_scan("producto", "producto_agregado",
                          producto_id=row_prod['id'])
                return
            # ── 2. Tarjeta de fidelidad (sin SQL UI) ─────────────────────────
            ls = getattr(self.container, 'loyalty_service', None) if hasattr(self, 'container') else None
            row_tarj = ls.resolve_scan(codigo) if ls else {"found": False}
            if row_tarj.get('found'):
                self._cargar_cliente_en_venta(
                    cliente_id=row_tarj['cliente_id'],
                    nombre=row_tarj['nombre'],
                    telefono=row_tarj.get('telefono', '') or "",
                    puntos=int(row_tarj.get('puntos', 0) or 0),
                    nivel=row_tarj.get('nivel', 'Bronce') or 'Bronce',
                )
                _log_scan('tarjeta', 'cliente_cargado', cliente_id=row_tarj['cliente_id'])
                return

            # ── 3. UUID contenedor ───────────────────────────────────────────
            import re as _re
            if _re.match(
                r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}'
                r'-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$', codigo
            ):
                try:
                    row_c = self.conexion.execute(
                        "SELECT uuid_qr, descripcion FROM trazabilidad_qr WHERE uuid_qr=? LIMIT 1",
                        (codigo,)).fetchone()
                    if row_c:
                        self._mostrar_notif_scanner(
                            f"📦 Contenedor: {row_c['descripcion'] or codigo[:8]}...",
                            "container")
                        _log_scan("contenedor", "contenedor_escaneado")
                        return
                except Exception:
                    pass

            # ── 4. Sin coincidencia ──────────────────────────────────────────
            _log_scan("busqueda", "sin_coincidencia")
            if hasattr(self, 'txt_busqueda'):
                self.txt_busqueda.setText(codigo)
                self.buscar_productos()
            self._mostrar_notif_scanner(f"🔍 Buscando: {codigo}", "search")

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("_procesar_scanner_con_codigo: %s", e)

        # Fallback idéntico eliminado — self.conexion == container.db, misma conexión.
        # Si el bloque principal falla, el fallback fallaría igual. Ver bloque try anterior.

    def _set_scan_context(self, context: str, active_field) -> None:
        """
        Cambia el contexto del scanner y actualiza el estilo visual de los campos.
        
        context: "producto" | "cliente" | "auto"
        active_field: el QLineEdit activo, o None para limpiar estilos
        """
        self._scan_context = context

        # v13.4: Usar clases CSS en lugar de estilos inline
        for field in (getattr(self,'txt_busqueda',None), getattr(self,'txt_cliente',None)):
            if field is None: continue
            
            # Remover clases previas
            field.setProperty("class", "")
            
            if field is active_field:
                if context == "producto":
                    field.setProperty("class", "input-scanner-success")
                    field.setPlaceholderText("🟢 SCANNER ACTIVO — Escanear producto...")
                elif context == "cliente":
                    field.setProperty("class", "input-scanner-primary")
                    field.setPlaceholderText("🔵 SCANNER ACTIVO — Escanear tarjeta o cliente...")
            else:
                field.setProperty("class", "input-scanner-base")
                # Restore original placeholder
                if field is getattr(self, 'txt_busqueda', None):
                    field.setPlaceholderText("Escanear código o escribir nombre del producto...")
                elif field is getattr(self, 'txt_cliente', None):
                    field.setPlaceholderText("💳 Escanear tarjeta o buscar cliente...")
        
        # Update persistent scanner state badge
        badge = getattr(self, '_lbl_scan_state', None)
        if badge:
            if context == "producto":
                badge.setText("● ACTIVO")
                badge.setObjectName("posScanStateActive")
            elif context == "cliente":
                badge.setText("● CLIENTE")
                badge.setObjectName("posScanStatePrimary")
            else:
                badge.setText("LIBRE")
                badge.setObjectName("posScanStateWaiting")
            badge.style().unpolish(badge)
            badge.style().polish(badge)

        # Highlight search frame border when product field is active
        sf = getattr(self, '_search_frame', None)
        if sf:
            sf.setProperty("focused", context == "producto")
            sf.style().unpolish(sf)
            sf.style().polish(sf)

        # Forzar actualización de estilos
        for field in (getattr(self,'txt_busqueda',None), getattr(self,'txt_cliente',None)):
            if field:
                field.style().unpolish(field)
                field.style().polish(field)

    def _cargar_cliente_en_venta(
        self,
        cliente_id: int,
        nombre: str,
        telefono: str = "",
        puntos: int = 0,
        nivel: str = "Bronce",
    ) -> None:
        """
        Carga un cliente en la venta activa.
        Actualiza el campo txt_cliente, la etiqueta de cliente,
        y emite notificación del scanner con nivel de fidelidad.
        """
        try:
            # Update txt_cliente display
            if hasattr(self, 'txt_cliente'):
                self.txt_cliente.setText(nombre)

            # Use existing set_cliente_venta if available
            if hasattr(self, 'set_cliente_venta'):
                self.set_cliente_venta(
                    cliente_id=cliente_id,
                    nombre=nombre,
                    telefono=telefono,
                )
            else:
                # Fallback: set attributes directly
                self.cliente_actual_id   = cliente_id
                self.cliente_actual_nombre = nombre
                if hasattr(self, 'lbl_cliente'):
                    self.lbl_cliente.setText(f"👤 {nombre}")
                if hasattr(self, 'lbl_cliente_nombre'):
                    self.lbl_cliente_nombre.setText(nombre)

            # Show notification with loyalty level
            nivel_icons = {"Bronce": "🥉", "Plata": "🥈", "Oro": "🥇",
                           "Diamante": "💎", "Platino": "🏆"}
            icon = nivel_icons.get(nivel, "⭐")
            pts_txt = f" — {puntos:,} pts" if puntos > 0 else ""
            self._mostrar_notif_scanner(
                f"{icon} {nombre} ({nivel}){pts_txt}", "card")

            # Switch to display mode
            if hasattr(self, '_client_search_row'):
                self._client_search_row.setVisible(False)
                self.txt_cliente.setVisible(False)
                self.txt_cliente.setMaximumHeight(0)
            if hasattr(self, '_client_display_row'):
                self._client_display_row.setVisible(True)

            # Refresh totals (in case discount rules apply to this client)
            if hasattr(self, '_actualizar_totales'):
                try: self._actualizar_totales()
                except Exception: pass
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("_cargar_cliente_en_venta: %s", e)

    def _mostrar_notif_scanner(self, mensaje: str, tipo: str = "product") -> None:
        """Muestra una notificación visual del resultado del scanner."""
        try:
            clases_css = {
                "product":   "badge-scanner-success",
                "card":      "badge-scanner-warning",
                "container": "badge-scanner-info",
                "search":    "badge-scanner-secondary",
            }
            clase = clases_css.get(tipo, "badge-scanner-default")
            if hasattr(self, 'lbl_scanner_notif'):
                self.lbl_scanner_notif.setText(mensaje)
                self.lbl_scanner_notif.setProperty("class", f"{clase} badge")
                self.lbl_scanner_notif.show()
                # Auto-hide after 3s
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(3000, lambda: (
                    self.lbl_scanner_notif.hide()
                    if hasattr(self, 'lbl_scanner_notif') else None))
        except Exception:
            pass

    
    def _abrir_nuevo_cliente_con_tarjeta(self, codigo: str) -> None:
        """
        Flujo dual Fase 2 — tarjeta de fidelidad escaneada pero sin cliente registrado.
        Abre DialogoAgregarCliente con el campo tarjeta_id precargado.
        Si el usuario confirma, registra el cliente y lo vincula a la tarjeta.
        """
        try:
            self._mostrar_notif_scanner(
                f"🪪 Tarjeta nueva — registra el cliente: {codigo}", "card")
            dialogo = DialogoAgregarCliente(self)
            dialogo.txt_tarjeta_id.setText(codigo)
            dialogo.txt_tarjeta_id.setReadOnly(True)   # evitar edición accidental
            if dialogo.exec_() == QDialog.Accepted:
                cliente_data = dialogo.get_cliente_data()
                self.guardar_nuevo_cliente(cliente_data)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("_abrir_nuevo_cliente_con_tarjeta: %s", e)

    def _cargar_tarjeta_desde_scanner(self, tarjeta_row) -> None:
        """
        Carga automáticamente la tarjeta de fidelidad en la venta activa.
        Muestra el diálogo de confirmación de tarjeta (lógica existente).
        """
        try:
            numero          = tarjeta_row[1]
            puntos          = tarjeta_row[2]
            estado          = tarjeta_row[3]
            cliente_id      = tarjeta_row[4]
            cliente_nombre  = tarjeta_row[5] or "Cliente"

            if estado == "bloqueada":
                QMessageBox.warning(
                    self, "Tarjeta Bloqueada",
                    f"La tarjeta {numero} está bloqueada."
                )
                return

            # Notificar en barra de búsqueda
            if hasattr(self, 'txt_busqueda'):
                self.txt_busqueda.setText(f"💳 {cliente_nombre} — {puntos} pts")
                QTimer.singleShot(2500, lambda: self.txt_busqueda.clear())

            # Si la venta tiene lógica de tarjeta ya implementada, usarla
            if hasattr(self, 'procesar_tarjeta_escaneo'):
                self.procesar_tarjeta_escaneo(numero)
            else:
                # Asociar cliente a la venta activa si es posible
                if cliente_id and hasattr(self, 'cliente_actual'):
                    self.cliente_actual = {
                        'id':       cliente_id,
                        'nombre':   cliente_nombre,
                        'telefono': tarjeta_row[6],
                        'puntos':   tarjeta_row[8],
                        'saldo':    tarjeta_row[9],
                    }
                Toast.success(
                    self,
                    "💳 Tarjeta cargada",
                    f"{cliente_nombre} · {numero} · {puntos} pts",
                )
        except Exception as exc:
            logger.warning("_cargar_tarjeta_desde_scanner: %s", exc)

    def procesar_tarjeta_escaneo(self, numero_o_qr: str) -> None:
        try:
            from core.services.card_batch_engine import CardBatchEngine
            eng = CardBatchEngine(self.conexion, self.usuario_actual or "cajero")
            tarjeta = eng.buscar_tarjeta(numero_o_qr)

            if not tarjeta:
                QMessageBox.warning(self, "Tarjeta", f"Tarjeta '{numero_o_qr}' no encontrada en el sistema.")
                return

            if tarjeta.estado == "bloqueada":
                QMessageBox.warning(self, "Tarjeta Bloqueada",
                    f"Tarjeta {tarjeta.numero} está bloqueada.\nMotivo: No disponible en este momento.")
                return

            if tarjeta.estado == "asignada" and tarjeta.id_cliente:
                _cli = self._cli_repo
                row = _cli.get_by_id(tarjeta.id_cliente) if _cli else None
                if row and row.get('activo', 1):
                    self.cliente_actual = {
                        'id': row['id'], 'nombre': row['nombre'],
                        'telefono': row.get('telefono', ''), 'email': row.get('email', ''),
                        'direccion': row.get('direccion', ''), 'rfc': row.get('rfc', ''),
                        'puntos': row.get('puntos', 0), 'codigo_qr': row.get('codigo_qr', ''),
                        'saldo': row.get('saldo', 0.0) or 0.0,
                    }
                    self._actualizar_ui_cliente()
                    if hasattr(self, 'lbl_puntos_cliente'):
                        self.lbl_puntos_cliente.setText(f"Puntos: {row.get('puntos',0)} | Nivel: {tarjeta.nivel}")
                    return

            dialogo = _DialogoAsignarTarjeta(tarjeta, self.conexion, self)
            if dialogo.exec_() == QDialog.Accepted:
                resultado = dialogo.resultado
                if resultado and resultado.get('cliente_id'):
                    cliente_id = resultado['cliente_id']
                    eng.asignar_tarjeta(tarjeta.id, cliente_id, motivo="asignacion_en_venta")
                    _cli = self._cli_repo
                    row = _cli.get_by_id(cliente_id) if _cli else None
                    if row:
                        self.cliente_actual = {
                            'id': row['id'], 'nombre': row['nombre'],
                            'telefono': row.get('telefono', ''), 'email': row.get('email', ''),
                            'direccion': row.get('direccion', ''), 'rfc': row.get('rfc', ''),
                            'puntos': row.get('puntos', 0), 'codigo_qr': row.get('codigo_qr', ''),
                            'saldo': row.get('saldo', 0.0) or 0.0,
                        }
                        self._actualizar_ui_cliente()
        except ImportError:
            Toast.info(self, "Tarjeta", "Motor de tarjetas no disponible en esta versión.")
        except Exception as exc:
            QMessageBox.critical(self, "Error Tarjeta", str(exc))

    def _actualizar_ui_cliente(self) -> None:
        if not self.cliente_actual: return
        # Delegate to the canonical update method
        self.actualizar_info_cliente()

    def _descuento_rapido(self, pct: float) -> None:
        """Aplica descuento % al ítem — validado por DiscountGuard financiero."""
        row = self.tabla_compra.currentRow() if hasattr(self, 'tabla_compra') else -1
        if row < 0:
            if self.compra_actual:
                row = len(self.compra_actual) - 1
            else:
                Toast.info(self, "Aviso", "Selecciona un ítem del carrito primero.")
                return
        if not (0 <= row < len(self.compra_actual)):
            return

        item = self.compra_actual[row]
        precio_orig   = item.get('precio_original', item['precio_unitario'])
        nuevo_precio  = round(precio_orig * (1 - pct / 100), 4)
        producto_id   = item.get('id', 0)
        rol_usuario   = getattr(self, 'rol_usuario', 'cajero') or 'cajero'

        # ── DiscountGuard: validación financiera antes de aplicar ─────────
        guard = getattr(getattr(self, 'container', None), 'discount_guard', None)
        if guard:
            permitido, mensaje, requiere_pin = guard.validar_descuento(
                producto_id   = producto_id,
                precio_original       = precio_orig,
                precio_con_descuento  = nuevo_precio,
                descuento_pct         = pct,
                rol_usuario           = rol_usuario,
            )
            if not permitido:
                QMessageBox.critical(self, "Descuento Bloqueado", mensaje)
                return
            if requiere_pin:
                dlg = _AuthDiscountDialog(
                    "Descuento Protegido",
                    f"Se requiere autorización de gerente.\n\n{mensaje}",
                    requiere_pin=True,
                    parent=self,
                )
                if dlg.exec_() != QDialog.Accepted:
                    return
                if not guard.solicitar_pin_gerente(self.conexion, dlg.pin):
                    QMessageBox.warning(self, "PIN Incorrecto",
                        "PIN de gerente incorrecto. Descuento no aplicado.")
                    return
        # ── Aplicar descuento ────────────────────────────────────────────────
        self.compra_actual[row]['precio_unitario'] = nuevo_precio
        self.compra_actual[row]['precio_original'] = precio_orig
        self.compra_actual[row]['descuento_pct']   = pct
        self.compra_actual[row]['total'] = round(nuevo_precio * item['cantidad'], 2)
        self.actualizar_tabla_compra()
        self.calcular_totales()

    def _descuento_custom(self) -> None:
        """Descuento personalizado en % o monto fijo."""
        from PyQt5.QtWidgets import QInputDialog
        row = self.tabla_compra.currentRow() if hasattr(self, 'tabla_compra') else -1
        if row < 0 and self.compra_actual:
            row = len(self.compra_actual) - 1
        if row < 0:
            Toast.info(self, "Aviso", "Selecciona un ítem primero.")
            return
        pct, ok = QInputDialog.getDouble(
            self, "Descuento personalizado",
            "Ingresa el porcentaje de descuento (0–100):",
            0, 0, 100, 1)
        if ok and pct > 0:
            self._descuento_rapido(pct)

    def _actualizar_comision_turno(self):
        """Actualiza el widget de comision del turno (si esta habilitado)."""
        try:
            cs = getattr(self.container, 'comisiones_service', None)
            if not cs:
                self.lbl_comision_turno.setVisible(False)
                if hasattr(self, '_card_comision'):
                    self._card_comision.setVisible(False)
                return
            usuario = self.obtener_usuario_actual()
            cfg = cs.get_config(usuario)
            if not cfg or not cfg.get('activo'):
                self.lbl_comision_turno.setVisible(False)
                if hasattr(self, '_card_comision'):
                    self._card_comision.setVisible(False)
                return
            datos = cs.get_comision_turno(usuario)
            monto  = float(datos.get('comision', 0))
            ventas = int(datos.get('ventas', 0))
            self.lbl_comision_turno.setText(
                f"${monto:.2f}  ({ventas} vtas)")
            self.lbl_comision_turno.setVisible(True)
            if hasattr(self, '_card_comision'):
                self._card_comision.setVisible(True)
        except Exception:
            pass

    def _abrir_cajon(self) -> None:
        """🛠️ FIX ENTERPRISE: Delega al HardwareService si existe, sino usa legacy."""
        if hasattr(self.container, 'hardware_service'):
            if self.container.hardware_service.open_cash_drawer():
                return
        
        # Legacy Fallback (cajón — no usa PrinterService)
        if not self._hw_cajon_habilitado: return
        try:
            metodo = self._hw_cajon_cfg.get("metodo", "escpos")
            if metodo == "escpos":
                from escpos.printer import Usb
                pulse = bytes([0x10, 0x14, 0x01, 0x00, 0x05])
                puerto = self._hw_cajon_cfg.get("puerto", "USB")
                if puerto == "USB":
                    try:
                        p = Usb(0x04b8, 0x0202)
                        p._raw(pulse)
                    except Exception: pass
            elif metodo == "serial" and HAS_SERIAL:
                import serial as _ser
                puerto_s = self._hw_cajon_cfg.get("puerto_serial", "COM4")
                baud     = int(self._hw_cajon_cfg.get("baud", 9600))
                try:
                    with _ser.Serial(puerto_s, baud, timeout=0.5) as s:
                        s.write(bytes([0x10, 0x14, 0x01, 0x00, 0x05]))
                except Exception: pass
        except Exception as exc:
            logger.debug("abrir_cajon (legacy): %s", exc)

    def _imprimir_ticket_consolidado(self, datos_ticket: dict) -> None:
        """
        Impresión de ticket unificada (v13.4 Fase 1):
        1. PrinterService → ESC/POS con logo, QR, formato completo
        2. PDF de auditoría siempre
        """
        # ── Ruta 1: PrinterService unificado (ESC/POS) ────────────────────────
        printer_svc = getattr(self.container, 'printer_service', None)
        if printer_svc and printer_svc.has_ticket_printer():
            try:
                job_id = printer_svc.print_ticket(datos_ticket)
                if job_id:
                    self.guardar_ticket_pdf(datos_ticket)
                    return
            except Exception as _e:
                logger.warning("PrinterService: %s", _e)
        else:
            QMessageBox.critical(
                self,
                "Impresión térmica no configurada",
                "No hay impresora térmica ESC/POS configurada.",
            )
            logger.warning("Ticket térmico cancelado: no hay impresora ESC/POS configurada.")

        # ── Ruta 4: PDF de auditoría (siempre) ───────────────────────────────
        try:
            self.guardar_ticket_pdf(datos_ticket)
        except Exception as _e:
            import logging; logging.getLogger(__name__).debug("PDF ticket: %s", _e)

    def _imprimir_ticket_hardware(self, ticket_data: dict) -> None:
        """v13.4: Delega a PrinterService."""
        try:
            ps = getattr(self.container, 'printer_service', None)
            if ps and ps.has_ticket_printer():
                ps.print_ticket(ticket_data)
        except Exception as exc:
            logger.debug("imprimir_ticket_hw: %s", exc)

    def inicializar_bascula(self):
        self.bascula_conectada = False
        # v13.4: Solo conectar báscula si está activa en configuración de hardware
        if not self._hw_bascula_habilitada:
            if hasattr(self, 'lbl_estado_bascula'):
                self._set_bascula_status("Báscula: ⚪ Desactivada")
            if hasattr(self, 'lbl_peso_bascula'):
                self.lbl_peso_bascula.setText("Peso: —")
            return
        self._set_bascula_status("Báscula: ⏳ Conectando...")
        self.lbl_peso_bascula.setText("Peso: 0.000 kg")
        self.timer_bascula.start()

    def leer_peso(self):
        """Lee peso priorizando HAL y mantiene fallback serial legacy."""
        try:
            hw = getattr(self.container, 'hardware_service', None)
            if hw:
                # API unificada del HAL: intenta báscula y puede sanear fallback manual.
                # Evita reciclar peso previo cuando no hay lectura nueva.
                peso = hw.get_weight(0.0)
                if peso > 0:
                    self.peso_actual = peso
                    self.lbl_peso_bascula.setText(f"Peso: {peso:.3f} kg")
                    self._set_bascula_status("Báscula: ✅ Conectada (HAL)")
                    if self.producto_pendiente:
                        self.procesar_peso_para_producto(peso)
                    return
        except Exception:
            pass

        # Legacy Fallback — solo si báscula está habilitada en config hardware
        if not self._hw_bascula_habilitada:
            return
        if not HAS_SERIAL_MODULE or serial is None:
            self._set_bascula_status("Báscula: ⚠️ Serial no disponible")
            return
        try:
            if not self.bascula:
                puerto = self._hw_bascula_cfg.get("puerto", "COM3")
                try:
                    baud = int(self._hw_bascula_cfg.get("baud", 9600))
                except Exception:
                    baud = 9600
                self.bascula = serial.Serial(puerto, baud, timeout=0.2)
                self._set_bascula_status("Báscula: ✅ Conectada")

            self.bascula.write(b'P\r\n')
            datos = self.bascula.readline().decode('utf-8', errors='ignore').strip()

            peso = self.extraer_peso_de_respuesta(datos)
            if peso is not None:
                self.peso_actual = peso
                self.lbl_peso_bascula.setText(f"Peso: {peso:.3f} kg")
                if self.producto_pendiente:
                    self.procesar_peso_para_producto(peso)
        except Exception as e:
            self.bascula = None
            self._set_bascula_status("Báscula: ❌ Desconectada")
                
    def iniciar_monitoreo_peso(self, producto: Dict[str, Any]):
        # BUG FIX: no iniciar si la báscula está deshabilitada en config hardware
        if not self._hw_bascula_habilitada:
            return
        self.producto_pendiente = producto
        self.lecturas_estables = []
        self.peso_inicial = 0
        self.lecturas_peso = [self.peso_actual]
        self.monitoreo_inicio = time.time()

        if not self.timer_bascula.isActive():
            self.timer_bascula.start()

    def procesar_peso_para_producto(self, peso: float):
        if not hasattr(self, 'producto_pendiente') or not self.producto_pendiente:
            return

        if not hasattr(self, 'lecturas_estables'):
            self.lecturas_estables = []

        self.lecturas_estables.append(peso)
        if len(self.lecturas_estables) > 4:
            self.lecturas_estables.pop(0)

        variacion = max(self.lecturas_estables) - min(self.lecturas_estables)

        if len(self.lecturas_estables) >= 2 and variacion <= 0.005:
            peso_neto = peso - self.peso_inicial
            if peso_neto > 0.010:
                self.agregar_producto_directo(self.producto_pendiente, peso_neto)
                self.finalizar_monitoreo_peso()
                self.lecturas_estables = []

                
    def finalizar_monitoreo_peso(self):
        if hasattr(self, 'producto_pendiente'): del self.producto_pendiente
        if hasattr(self, 'peso_inicial'): del self.peso_inicial
        if hasattr(self, 'monitoreo_inicio'): del self.monitoreo_inicio
        self.lecturas_peso = []

    def extraer_peso_de_respuesta(self, respuesta: str) -> Optional[float]:
        import re
        if not respuesta: return None
        try:
            patrones = [
                r'[STUS\s]*([+-]?\d+\.\d+)\s*[kK][gG]',
                r'([+-]?\d+\.\d+)',
                r'(\d{3,4})',
            ]
            for patron in patrones:
                coincidencia = re.search(patron, respuesta)
                if coincidencia:
                    peso_str = coincidencia.group(1)
                    if '.' not in peso_str:
                        if len(peso_str) >= 3:
                            peso = float(peso_str) / 1000.0
                        else:
                            peso = float(peso_str)
                    else:
                        peso = float(peso_str)
                    return abs(peso)
            return None
        except (ValueError, AttributeError):
            return None
    
    def preguntar_peso_manual(self):
        if hasattr(self, 'producto_pendiente') and self.producto_pendiente:
            respuesta = QMessageBox.question(
                self, "Peso No Detectado",
                f"No se detectó un peso estable para {self.producto_pendiente['nombre']}.\n\n"
                f"¿Desea ingresar el peso manualmente?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if respuesta == QMessageBox.Yes:
                cantidad, ok = QInputDialog.getDouble(
                    self, "Peso Manual", 
                    f"Ingrese el peso para {self.producto_pendiente['nombre']} (kg):",
                    value=0.100, min=0.001, max=9999.0, decimals=3
                )
                if ok and cantidad > 0:
                    self.agregar_producto_directo(self.producto_pendiente, cantidad)
            self.finalizar_monitoreo_peso()
            
    def agregar_producto_por_unidad(self, producto: Dict[str, Any]):
        cantidad, ok = QInputDialog.getDouble(
            self, "Cantidad", 
            f"Ingrese la cantidad para {producto['nombre']}:",
            value=1.0, min=0.001, max=9999.0, decimals=3
        )
        if ok and cantidad > 0:
            self.agregar_producto_directo(producto, cantidad)
        else:
            self.limpiar_seleccion_producto()

    def agregar_producto_directo(self, producto: Dict[str, Any], cantidad: float):
        def _stock_msg(prod: Dict[str, Any]) -> str:
            missing = prod.get("missing_components") or []
            if missing:
                lines = [f"No se puede vender {prod.get('nombre','este producto')}.\n", "Faltantes:"]
                for m in missing[:6]:
                    comp = m.get("component_name") or m.get("nombre") or "Componente"
                    req = m.get("required_qty")
                    ava = m.get("available_qty")
                    und = m.get("unit") or prod.get("unidad") or ""
                    lines.append(f"- {comp}: necesitas {req} {und}, disponible {ava} {und}")
                mx = prod.get("max_sellable")
                if mx is not None:
                    lines.append(f"\nMáximo vendible: {mx}")
                return "\n".join(lines)
            avail_msg = prod.get("availability_message")
            if avail_msg:
                return str(avail_msg)
            return f"Stock insuficiente. Disponible: {prod['existencia']:.2f} {prod['unidad']}"

        if cantidad <= 0:
            QMessageBox.warning(self, "Advertencia", "La cantidad debe ser mayor a cero.")
            self.limpiar_seleccion_producto()
            return
            
        if cantidad > producto['existencia']:
            QMessageBox.warning(self, "Stock Insuficiente",
                _stock_msg(producto))
            self.limpiar_seleccion_producto()
            return
            
        for item in self.compra_actual:
            if item['id'] == producto['id']:
                respuesta = QMessageBox.question(
                    self, "Producto Duplicado", 
                    f"El producto '{producto['nombre']}' ya está en el carrito.\n\n"
                    f"¿Desea modificar la cantidad existente?",
                    QMessageBox.Yes | QMessageBox.No
                )
                
                if respuesta == QMessageBox.Yes:
                    for i, item in enumerate(self.compra_actual):
                        if item['id'] == producto['id']:
                            nueva_cantidad = item['cantidad'] + cantidad
                            if nueva_cantidad > producto['existencia']:
                                QMessageBox.warning(
                                    self, "Stock Insuficiente",
                                    _stock_msg(producto)
                                )
                                break
                                
                            item['cantidad'] = nueva_cantidad
                            item['total'] = round(nueva_cantidad * item['precio_unitario'], 2)
                            self.actualizar_tabla_compra()
                            self.mostrar_mensaje("Éxito", f"Cantidad actualizada: {nueva_cantidad:.3f} {producto['unidad']}")
                            break
                else:
                    total_item = round(cantidad * producto['precio'], 2)
                    import uuid as _uuid_mod
                    item_compra = {
                        'id': producto['id'],
                        'nombre': f"{producto['nombre']} (adicional)",
                        'cantidad': cantidad,
                        'unidad': producto['unidad'],
                        'precio_unitario': producto['precio'],
                        'total': total_item,
                        '_uid': _uuid_mod.uuid4().hex,  # ISSUE 2 FIX
                        'fulfillment_mode': producto.get('fulfillment_mode'),
                        'component_movements': producto.get('component_movements'),
                        'missing_components': producto.get('missing_components'),
                        'max_sellable': producto.get('max_sellable'),
                        'availability_message': producto.get('availability_message'),
                    }
                # Verificar stock antes de agregar al carrito
                # v13.4: Delegado a inventory_service para mantener abstracción de capa
                try:
                    _inv = getattr(self.container, 'inventory_service', None)
                    if _inv:
                        stock_actual = float(_inv.get_stock_sucursal(
                            producto['id'], self.sucursal_id) or 0)
                    else:
                        stock_actual = float(producto.get('existencia', 0))
                    if stock_actual <= 0 and not producto.get('es_compuesto', 0):
                        resp = QMessageBox.question(
                            self, "⚠️ Sin stock",
                            f"'{producto['nombre']}' no tiene existencia disponible.\n"
                            f"¿Deseas agregarlo de todas formas?",
                            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                        )
                        if resp != QMessageBox.Yes:
                            return
                except Exception:
                    pass  # No bloquea si falla la consulta

                if not self._tiempo_inicio_venta:
                    import time
                    self._tiempo_inicio_venta = time.time()
                self.compra_actual.append(item_compra)
                self.actualizar_tabla_compra()
                    
                self.limpiar_seleccion_producto()
                return
                
        total_item = round(cantidad * producto['precio'], 2)
        import uuid as _uuid_mod
        item_compra = {
            'id': producto['id'],
            'nombre': producto['nombre'],
            'cantidad': cantidad,
            'unidad': producto['unidad'],
            'precio_unitario': producto['precio'],
            'total': total_item,
            'codigo': producto.get('codigo', '') or producto.get('codigo_barras', ''),
            # ISSUE 2 FIX: Identificador estable para que el descuento pertenezca
            # al ítem, no al índice de fila. Sobrevive cualquier pop/reordenamiento.
            '_uid': _uuid_mod.uuid4().hex,
            'fulfillment_mode': producto.get('fulfillment_mode'),
            'component_movements': producto.get('component_movements'),
            'missing_components': producto.get('missing_components'),
            'max_sellable': producto.get('max_sellable'),
            'availability_message': producto.get('availability_message'),
        }

        self.compra_actual.append(item_compra)
        self.actualizar_tabla_compra()
        self.limpiar_seleccion_producto()

    def limpiar_seleccion_producto(self):
        if self._selected_card:
            self._selected_card.set_selected(False)
            self._selected_card = None
        self.producto_seleccionado = None

    def actualizar_tabla_compra(self):
        has_items = bool(self.compra_actual)
        self.tabla_compra.setVisible(has_items)
        if hasattr(self, '_lbl_cart_empty'):
            self._lbl_cart_empty.setVisible(not has_items)

        self.tabla_compra.setRowCount(len(self.compra_actual))

        for row, item in enumerate(self.compra_actual):
            # Column 0: 2-line cell — name (bold) + code (muted small)
            cell_w = QWidget()
            cell_lay = QVBoxLayout(cell_w)
            cell_lay.setContentsMargins(6, 4, 4, 4)
            cell_lay.setSpacing(1)
            lbl_name = QLabel(item['nombre'])
            lbl_name.setObjectName("posCartItemName")
            codigo = (item.get('codigo', '') or item.get('codigo_barras', '')
                      or str(item.get('id', '')))
            lbl_code = QLabel(f"Código: {codigo}")
            lbl_code.setObjectName("posCartItemCode")
            mode_raw = str(item.get("fulfillment_mode") or "").upper().strip()
            mode_map = {
                "DIRECTO": "DIRECTO",
                "COMBINACION": "COMPUESTO",
                "COMPUESTO": "COMPUESTO",
                "VIRTUAL": "VIRTUAL",
            }
            mode_tag = mode_map.get(mode_raw, "DIRECTO")
            lbl_mode = QLabel(f"Modo: {mode_tag}")
            lbl_mode.setObjectName("posCartItemCode")
            cell_lay.addWidget(lbl_name)
            cell_lay.addWidget(lbl_code)
            cell_lay.addWidget(lbl_mode)
            comp_moves = item.get("component_movements") or []
            if comp_moves:
                comp_lines = ["Descontará estos componentes:"]
                for cm in comp_moves[:6]:
                    nm = cm.get("component_name") or cm.get("nombre") or "Componente"
                    qt = cm.get("qty") or cm.get("quantity") or cm.get("cantidad") or 0
                    un = cm.get("unit") or item.get("unidad") or ""
                    comp_lines.append(f"- {nm}: -{qt} {un}")
                cell_w.setToolTip("\n".join(comp_lines))
            elif item.get("availability_message"):
                cell_w.setToolTip(str(item.get("availability_message")))
            self.tabla_compra.setCellWidget(row, 0, cell_w)

            cantidad_item = QTableWidgetItem(f"{item['cantidad']:.3f}")
            cantidad_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabla_compra.setItem(row, 1, cantidad_item)

            precio_item = QTableWidgetItem(f"${item['precio_unitario']:.2f}")
            precio_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabla_compra.setItem(row, 2, precio_item)

            # Descuento — clicable via cellClicked (col 3)
            # ISSUE 2 FIX: Almacenar _uid del ítem en UserRole para que el clic
            # encuentre el ítem correcto aunque cambie el índice de fila.
            desc_pct = float(item.get('descuento_pct', 0))
            if desc_pct > 0:
                disc_item = QTableWidgetItem(f"-{desc_pct:.0f}%")
                disc_item.setForeground(QBrush(QColor(Colors.DANGER_HOVER)))
                disc_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                disc_item.setToolTip("Clic para quitar el descuento")
                disc_item.setData(Qt.UserRole, item.get('_uid', ''))
                self.tabla_compra.removeCellWidget(row, 3)
                self.tabla_compra.setItem(row, 3, disc_item)
            else:
                self.tabla_compra.removeCellWidget(row, 3)
                self.tabla_compra.setItem(row, 3, QTableWidgetItem("$0.00"))

            total_item = QTableWidgetItem(f"${item['total']:.2f}")
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabla_compra.setItem(row, 4, total_item)

            # Col 5: edit button
            btn_modificar = QPushButton("✏")
            btn_modificar.setToolTip("Modificar cantidad")
            btn_modificar.setFixedSize(28, 28)
            btn_modificar.setObjectName("cartEditBtn")
            btn_modificar.clicked.connect(lambda checked, r=row: self.modificar_cantidad_producto(r))
            self.tabla_compra.setCellWidget(row, 5, btn_modificar)

            # Col 6: delete ×
            btn_eliminar = QPushButton("×")
            btn_eliminar.setToolTip("Eliminar producto")
            btn_eliminar.setFixedSize(28, 28)
            btn_eliminar.setObjectName("cartDeleteBtn")
            btn_eliminar.clicked.connect(lambda checked, r=row: self.eliminar_producto_carrito(r))
            self.tabla_compra.setCellWidget(row, 6, btn_eliminar)

        # ISSUE 1 FIX: Desplazar al último ítem para que siempre sea visible
        if self.compra_actual:
            self.tabla_compra.scrollToBottom()

        self.calcular_totales()

    def _on_cart_cell_clicked(self, row: int, col: int) -> None:
        """Handles click on cart table cells. Column 3 = discount badge (remove on click).
        ISSUE 2 FIX: Usa _uid almacenado en UserRole para identificar el ítem de forma
        estable, independientemente de su posición actual en la tabla."""
        if col != 3:
            return
        # Recuperar el _uid del ítem desde la celda (immune a reordenamiento)
        cell = self.tabla_compra.item(row, 3)
        uid = cell.data(Qt.UserRole) if cell else None
        if uid:
            self._quitar_descuento_por_uid(uid)
        elif 0 <= row < len(self.compra_actual):
            # Fallback para ítems legacy sin _uid
            if float(self.compra_actual[row].get('descuento_pct', 0)) > 0:
                self._quitar_descuento_item(row)

    def _quitar_descuento_por_uid(self, uid: str) -> None:
        """ISSUE 2 FIX: Quita el descuento buscando por _uid, no por índice de fila."""
        for item in self.compra_actual:
            if item.get('_uid') == uid:
                precio_original = item.get('precio_original', item['precio_unitario'])
                item['precio_unitario'] = precio_original
                item['descuento_pct'] = 0
                item['total'] = round(item['cantidad'] * precio_original, 2)
                self.actualizar_tabla_compra()
                return

    def _quitar_descuento_item(self, row: int):
        """Quita el descuento de un item del carrito y restaura el precio original."""
        if not (0 <= row < len(self.compra_actual)):
            return
        item = self.compra_actual[row]
        # Restore the original (pre-discount) price that was saved when the discount was applied
        precio_original = item.get('precio_original', item['precio_unitario'])
        item['precio_unitario'] = precio_original
        item['descuento_pct'] = 0
        item['total'] = round(item['cantidad'] * precio_original, 2)
        # cellClicked handler: table is not being destroyed mid-signal, safe to rebuild now
        self.actualizar_tabla_compra()

    def modificar_cantidad_producto(self, row: int):
        if 0 <= row < len(self.compra_actual):
            producto = self.compra_actual[row]
            cantidad_actual = producto['cantidad']
            
            cantidad, ok = QInputDialog.getDouble(
                self, "Modificar Cantidad", 
                f"Ingrese la nueva cantidad para {producto['nombre']}:",
                value=cantidad_actual, min=0.001, max=9999.0, decimals=3
            )
            
            if ok and cantidad > 0:
                stock_disponible = self.obtener_stock_producto(producto['id'])
                if cantidad > stock_disponible:
                    QMessageBox.warning(self, "Stock Insuficiente",
                        f"Stock insuficiente. Disponible: {stock_disponible:.2f} {producto['unidad']}")
                    return
                    
                producto['cantidad'] = cantidad
                producto['total'] = round(cantidad * producto['precio_unitario'], 2)
                self.actualizar_tabla_compra()

    def obtener_stock_producto(self, producto_id: int) -> float:
        """Stock disponible = físico - reservado activo."""
        try:
            return float(self._stock_reservas.stock_disponible(producto_id))
        except Exception:
            return 0.0

    def eliminar_producto_carrito(self, row: int):
        if 0 <= row < len(self.compra_actual):
            producto = self.compra_actual[row]['nombre']
            self.compra_actual.pop(row)
            # Defer table rebuild so the delete button widget is not destroyed while
            # its own clicked signal is still being dispatched.
            QTimer.singleShot(0, self.actualizar_tabla_compra)
            self.mostrar_mensaje("Éxito", f"Producto '{producto}' eliminado del carrito.")

    def calcular_totales(self):
        # IVA: carnes y alimentos basicos = 0% en Mexico (LIVA Art. 2-A)
        # Delegado a ConfigService — sin SQL directo en UI
        try:
            tasa_iva = float(self.container.config_service.get('tasa_iva', 0.0) or 0.0)
        except Exception:
            tasa_iva = 0.0
        try:
            from core.services.sales.cart_calculator import CartCalculator
            resumen = CartCalculator.calculate(
                items=self.compra_actual,
                iva_rate=tasa_iva,
            )
        except Exception:
            resumen = {
                'precio_base': sum(item['cantidad'] * item['precio_unitario'] for item in self.compra_actual),
                'descuento_lineas': 0.0,
                'subtotal': sum(item['total'] for item in self.compra_actual),
                'impuestos': 0.0,
                'total_final': sum(item['total'] for item in self.compra_actual),
                'puntos_preview': 0,
            }

        self.totales = {
            'subtotal': resumen['subtotal'],
            'impuestos': resumen['impuestos'],
            'total_final': resumen['total_final']
        }
        precio_base = resumen['precio_base']
        descuento_total = resumen['descuento_lineas']
        total_final = resumen['total_final']

        # Update breakdown labels
        if hasattr(self, '_lbl_subtotal_val'):
            self._lbl_subtotal_val.setText(f"${precio_base:.2f}")
        if hasattr(self, '_row_discount_widget'):
            if descuento_total > 0.001:
                self._lbl_descuento_val.setText(f"-${descuento_total:.2f}")
                # Build discount description from discounted items
                desc_items = [
                    f"{item['nombre'][:12]} {item['descuento_pct']:.0f}%"
                    for item in self.compra_actual
                    if item.get('descuento_pct', 0) > 0
                ]
                if desc_items:
                    self._lbl_descuento_label.setText(
                        f"Descuento ({', '.join(desc_items[:2])})")
                else:
                    self._lbl_descuento_label.setText("Descuento")
                self._row_discount_widget.setVisible(True)
            else:
                self._row_discount_widget.setVisible(False)

        # Grand total label — keep backward-compatible "$X.XX" format
        self.lbl_total.setText(f"${total_final:.2f}")

        # COBRAR button shows amount
        if hasattr(self, 'btn_cobrar'):
            if total_final > 0:
                self.btn_cobrar.setText(f"💰 COBRAR  ${total_final:.2f}")
            else:
                self.btn_cobrar.setText("💰 COBRAR")

        puntos_venta = int(resumen.get('puntos_preview', total_final))
        self.lbl_puntos_venta.setText(f"+ {puntos_venta} pts")

    def _cliente_textchanged(self, text: str) -> None:
        """Debounce handler: restart the 180ms timer on every keystroke."""
        if text.strip():
            self._cliente_debounce.start()
        else:
            self._cliente_debounce.stop()

    def _actualizar_sugerencias_cliente(self) -> None:
        """Query DB for matching customers and populate the QCompleter popup.
        ISSUE 5 FIX: Funciona desde 1 carácter con MatchContains en cualquier parte
        del nombre/teléfono. setMinimumContentsLength(1) asegura que el popup
        aparezca con texto parcial."""
        from PyQt5.QtWidgets import QCompleter
        from PyQt5.QtCore import QStringListModel
        texto = self.txt_cliente.text().strip()
        # ISSUE 5 FIX: Disparar con 1+ caracteres (antes podía requerir más)
        if len(texto) < 1:
            return
        try:
            _cli = self._cli_repo
            rows = _cli.buscar(texto, limit=12) if _cli else []
        except Exception:
            return
        suggestions = [
            f"{r['nombre']}  ·  {r['telefono']}" if r.get('telefono') else r['nombre']
            for r in rows
        ]
        if self._cliente_completer_model is None:
            self._cliente_completer_model = QStringListModel(self)
            self._cliente_completer = QCompleter(self._cliente_completer_model, self)
            self._cliente_completer.setCaseSensitivity(Qt.CaseInsensitive)
            # ISSUE 5 FIX: MatchContains → busca en cualquier parte del texto
            self._cliente_completer.setFilterMode(Qt.MatchContains)
            self._cliente_completer.setCompletionMode(QCompleter.PopupCompletion)
            self._cliente_completer.setMaxVisibleItems(10)
            # ISSUE 5 FIX: Activar popup desde 1 carácter
            self._cliente_completer.setMinimumContentsLength(1)
            self.txt_cliente.setCompleter(self._cliente_completer)
            self._cliente_completer.activated.connect(self._seleccionar_cliente_autocomplete)
        self._cliente_completer_model.setStringList(suggestions)
        if suggestions:
            self._cliente_completer.complete()

    def _seleccionar_cliente_autocomplete(self, text: str) -> None:
        """Called when user picks a suggestion; extract name and run DB lookup."""
        nombre = text.split("  ·  ")[0].strip()
        self.txt_cliente.setText(nombre)
        # Stop the debounce timer so it doesn't re-trigger search
        self._cliente_debounce.stop()
        self.buscar_cliente()

    def buscar_cliente(self):
        termino = self.txt_cliente.text().strip()
        if not termino:
            self.limpiar_cliente()
            return

        try:
            lookup = self._customer_lookup_svc
            _cli = self._cli_repo
            if lookup:
                clientes = lookup.buscar_cliente(termino, limit=1)
            else:
                clientes = _cli.buscar(termino, limit=1) if _cli else []
            cliente = clientes[0] if clientes else None

            if cliente:
                self.cliente_actual = {
                    'id': cliente['id'], 'nombre': cliente['nombre'],
                    'telefono': cliente.get('telefono', ''),
                    'email': cliente.get('email', ''),
                    'direccion': cliente.get('direccion', ''),
                    'rfc': cliente.get('rfc', ''),
                    'puntos': cliente.get('puntos', 0),
                    'codigo_qr': cliente.get('codigo_qr', ''),
                    'saldo': cliente.get('saldo', 0.0) or 0.0,
                }
                self.actualizar_info_cliente()
                self.txt_cliente.clear()
            else:
                self.limpiar_cliente()
                respuesta = QMessageBox.question(
                    self, "Cliente No Encontrado", 
                    f"¿Desea agregar '{termino}' como nuevo cliente?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if respuesta == QMessageBox.Yes:
                    self.agregar_cliente_con_nombre(termino)
        except sqlite3.Error as e:
            self.mostrar_mensaje("Error", f"Error al buscar cliente: {str(e)}", QMessageBox.Critical)

    def actualizar_info_cliente(self):
        if self.cliente_actual:
            self.lbl_nombre_cliente.setText(self.cliente_actual['nombre'])
            self.lbl_telefono_cliente.setText(f"Tel: {self.cliente_actual['telefono'] or '—'}")
            self.lbl_email_cliente.setText(self.cliente_actual.get('email') or '')
            puntos = self.cliente_actual.get('puntos', 0)
            self.lbl_puntos_cliente.setText(f"+ {puntos} pts")
            # Update loyalty tier badge
            if hasattr(self, '_lbl_loyalty_tier'):
                nivel = (self.cliente_actual.get('nivel_fidelidad', '')
                         or self.cliente_actual.get('nivel', ''))
                if nivel:
                    self._lbl_loyalty_tier.setText(nivel)
                    self._lbl_loyalty_tier.setProperty("tier", nivel)
                    self._lbl_loyalty_tier.style().unpolish(self._lbl_loyalty_tier)
                    self._lbl_loyalty_tier.style().polish(self._lbl_loyalty_tier)
                    self._lbl_loyalty_tier.show()
                else:
                    self._lbl_loyalty_tier.hide()
            # Switch to display mode (hide search row, show display row)
            if hasattr(self, '_client_search_row'):
                self._client_search_row.setVisible(False)
                self.txt_cliente.setVisible(False)
                self.txt_cliente.setMaximumHeight(0)
            if hasattr(self, '_client_display_row'):
                self._client_display_row.setVisible(True)
        else:
            self.limpiar_cliente()

    def agregar_cliente(self):
        dialogo = DialogoAgregarCliente(self)
        if dialogo.exec_() == QDialog.Accepted:
            cliente_data = dialogo.get_cliente_data()
            self.guardar_nuevo_cliente(cliente_data)

    def agregar_cliente_con_nombre(self, nombre: str):
        dialogo = DialogoAgregarCliente(self)
        dialogo.txt_nombre.setText(nombre)
        if dialogo.exec_() == QDialog.Accepted:
            cliente_data = dialogo.get_cliente_data()
            self.guardar_nuevo_cliente(cliente_data)

    def guardar_nuevo_cliente(self, cliente_data: Dict[str, Any]):
        try:
            tarjeta_id = cliente_data.get('tarjeta_id', '')

            # Si se proporcionó tarjeta, verificar si ya está asignada a otro cliente
            if tarjeta_id:
                existing = self.conexion.execute(
                    "SELECT c.id, c.nombre FROM clientes c "
                    "JOIN tarjetas_fidelidad t ON t.id_cliente = c.id "
                    "WHERE t.codigo = ? AND t.activa = 1 LIMIT 1",
                    (tarjeta_id,)
                ).fetchone()
                if existing:
                    eid = existing['id'] if hasattr(existing, 'keys') else existing[0]
                    enombre = existing['nombre'] if hasattr(existing, 'keys') else existing[1]
                    self.seleccionar_cliente(eid)
                    self.mostrar_mensaje("Info", f"Tarjeta ya asignada a: {enombre}")
                    return

            codigo_qr = tarjeta_id or (
                f"CLI_{datetime.now().strftime('%Y%m%d%H%M%S')}" if cliente_data['generar_tarjeta'] else None)

            _cli = self._cli_repo
            if _cli:
                cliente_id = _cli.crear(
                    nombre=cliente_data['nombre'],
                    telefono=cliente_data.get('telefono', ''),
                    email=cliente_data.get('email', ''),
                    direccion=cliente_data.get('direccion', ''),
                    codigo_fidelidad=codigo_qr,
                )
            else:
                cursor = self.conexion.cursor()
                cursor.execute(
                    "INSERT INTO clientes (nombre, telefono, email, direccion, puntos, codigo_qr, activo) "
                    "VALUES (?, ?, ?, ?, 0, ?, 1)",
                    (cliente_data['nombre'], cliente_data.get('telefono', ''),
                     cliente_data.get('email', ''), cliente_data.get('direccion', ''), codigo_qr),
                )
                cliente_id = cursor.lastrowid
                self.conexion.commit()

            # Asignar tarjeta de fidelidad si se proporcionó código
            if tarjeta_id:
                try:
                    self.conexion.execute(
                        "INSERT OR IGNORE INTO tarjetas_fidelidad "
                        "(codigo, id_cliente, nivel, activa, fecha_emision) "
                        "VALUES (?, ?, 'Bronce', 1, datetime('now'))",
                        (tarjeta_id, cliente_id),
                    )
                    try:
                        self.conexion.commit()
                    except Exception:
                        pass
                except Exception:
                    pass

            self.cliente_actual = {
                'id': cliente_id, 'nombre': cliente_data['nombre'],
                'telefono': cliente_data.get('telefono', ''),
                'email': cliente_data.get('email', ''),
                'direccion': cliente_data.get('direccion', ''),
                'puntos': 0, 'codigo_qr': codigo_qr, 'saldo': 0.0,
            }
            self.actualizar_info_cliente()
            self.mostrar_mensaje("Éxito", f"Cliente '{cliente_data['nombre']}' agregado.")
        except Exception as e:
            self.mostrar_mensaje("Error", f"Error al guardar cliente: {str(e)}", QMessageBox.Critical)

    def limpiar_cliente(self):
        self.cliente_actual = None
        self.lbl_nombre_cliente.setText("Público General")
        self.lbl_telefono_cliente.setText("Tel: —")
        self.lbl_email_cliente.setText("")
        self.lbl_puntos_cliente.setText("+ 0 pts")
        self.txt_cliente.clear()
        if hasattr(self, '_lbl_loyalty_tier'):
            self._lbl_loyalty_tier.hide()
        # Restore display-only mode
        if hasattr(self, '_client_search_row'):
            self._client_search_row.setVisible(False)
            self.txt_cliente.setVisible(False)
            self.txt_cliente.setMaximumHeight(0)
        if hasattr(self, '_client_display_row'):
            self._client_display_row.setVisible(True)

    def suspender_venta(self):
        if not self.compra_actual:
            QMessageBox.warning(self, "Advertencia", "No hay productos en el carrito para suspender.")
            return
            
        nombre_venta = ""
        if not self.cliente_actual:
            dialogo = DialogoSuspender(self)
            if dialogo.exec_() == QDialog.Accepted:
                nombre_venta = dialogo.get_nombre_venta()
            else: return
        else:
            nombre_venta = f"Venta - {self.cliente_actual['nombre']}"

        # Reservar stock disponible para evitar sobreventa entre terminales
        try:
            reserva_id = self._stock_reservas.reservar(
                f"SUSP-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                self.compra_actual,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Stock insuficiente", str(exc))
            return
            
        venta_id = f"venta_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.ventas_en_espera[venta_id] = {
            'nombre': nombre_venta, 'cliente': self.cliente_actual,
            'compra': self.compra_actual.copy(), 'totales': self.totales.copy(),
            'timestamp': datetime.now(),
            'reserva_id': reserva_id,
        }
        try:
            from core.events.event_bus import get_bus
            from core.events.domain_events import VENTA_SUSPENDIDA, STOCK_RESERVADO
            get_bus().publish(VENTA_SUSPENDIDA, {"venta_id": venta_id, "reserva_id": reserva_id, "sucursal_id": self.sucursal_id})
            get_bus().publish(STOCK_RESERVADO, {"venta_id": venta_id, "reserva_id": reserva_id, "sucursal_id": self.sucursal_id})
        except Exception:
            pass
        self.btn_reanudar.setText(f"▶️ Reanudar ({len(self.ventas_en_espera)})")
        self.mostrar_mensaje("Éxito", f"Venta '{nombre_venta}' suspendida.")
        self.cancelar_venta(silent=True)

    def mostrar_ventas_espera(self):
        if not self.ventas_en_espera:
            Toast.info(self, "Ventas en Espera", "No hay ventas suspendidas.")
            return
            
        ventas_lista = [f"{v['nombre']} - ${v['totales']['total_final']:.2f}" for v in self.ventas_en_espera.values()]
        item, ok = QInputDialog.getItem(self, "Reanudar Venta", "Seleccione la venta a reanudar:", ventas_lista, 0, False)
        
        if ok and item:
            for venta_id, venta_data in self.ventas_en_espera.items():
                if f"{venta_data['nombre']} - ${venta_data['totales']['total_final']:.2f}" == item:
                    self.reanudar_venta(venta_id)
                    break

    def reanudar_venta(self, venta_id: str):
        if venta_id in self.ventas_en_espera:
            venta_data = self.ventas_en_espera.pop(venta_id)
            self.cancelar_venta(silent=True)
            self.compra_actual = venta_data['compra'].copy()
            self._reserva_activa_id = venta_data.get('reserva_id')
            self.cliente_actual = venta_data['cliente']
            self.totales = venta_data['totales'].copy()
            self.actualizar_tabla_compra()
            if self.cliente_actual: self.actualizar_info_cliente()
            else: self.limpiar_cliente()
            self.btn_reanudar.setText(f"▶️ Reanudar ({len(self.ventas_en_espera)})")
            self.mostrar_mensaje("Éxito", f"Venta '{venta_data['nombre']}' reanudada.")

    def procesar_pago(self):
        if not self.compra_actual:
            QMessageBox.warning(self, "Advertencia", "No hay productos en el carrito.")
            return

        # ── Validar que la caja esté abierta ──────────────────────────────
        try:
            usuario = self.obtener_usuario_actual()
            fin_svc = getattr(self.container, 'finance_service', None)
            if fin_svc:
                turno = fin_svc.get_estado_turno(self.sucursal_id, usuario)
                if not turno:
                    QMessageBox.warning(
                        self, "Caja Cerrada",
                        "No hay un turno de caja abierto para este usuario.\n\n"
                        "Ve al módulo de Caja y abre tu turno antes de vender.")
                    return
        except Exception:
            pass  # If check fails, allow sale (graceful degradation)

        total_a_pagar = self.totales['total_final']
        loyalty_preview = {}
        loyalty_svc = getattr(self.container, 'loyalty_service', None)
        cliente_id = self.cliente_actual['id'] if self.cliente_actual else None
        if cliente_id and loyalty_svc and getattr(loyalty_svc, "enabled", False):
            try:
                loyalty_preview = loyalty_svc.preview_redemption(
                    cliente_id=cliente_id,
                    subtotal=float(total_a_pagar),
                ) or {}
            except Exception as _lp_e:
                logger.debug("preview_redemption: %s", _lp_e)

        def _preview_provider(puntos: int, subtotal: float):
            if not (cliente_id and loyalty_svc and getattr(loyalty_svc, "enabled", False)):
                return {}
            return loyalty_svc.preview_redemption(
                cliente_id=cliente_id,
                subtotal=float(subtotal),
                puntos_solicitados=int(max(0, puntos)),
            )

        from presentation.sales.dialogs.payment_dialog import DialogoPago as PaymentDialog
        dialogo = PaymentDialog(
            total_a_pagar,
            self,
            loyalty_balance=loyalty_preview,
            loyalty_preview_provider=_preview_provider,
        )
        if dialogo.exec_() == QDialog.Accepted:
            datos_pago = dialogo.get_datos_pago()

            # ── POST-DIALOG: validate credit only when credit payment chosen ──
            # This runs AFTER the user selects the payment method, so we only
            # block credit sales — cash/card/transfer flow through unrestricted.
            from core.services.payment_normalization import is_credit_sale, is_mercado_pago
            if is_credit_sale(datos_pago.get('forma_pago')):
                if not self.cliente_actual:
                    QMessageBox.critical(
                        self, "Cliente requerido",
                        "Debe seleccionar un cliente para procesar una venta a crédito.\n\n"
                        "Asigne un cliente y vuelva a intentarlo, o elija otro método de pago."
                    )
                    return
                _ccs = getattr(self.container, 'customer_credit_service', None)
                _financed = float(datos_pago.get('saldo_credito') or datos_pago.get('total_pagado', 0))
                if _ccs and _financed > 0:
                    try:
                        _ok, _msg = _ccs.validate_credit(self.cliente_actual['id'], _financed)
                        if not _ok:
                            QMessageBox.critical(
                                self, "Crédito insuficiente",
                                f"{_msg}\n\nLa venta a crédito no puede procesarse.\n"
                                "Puede elegir otro método de pago."
                            )
                            return
                    except Exception as _cv_e:
                        logger.warning("validate_credit: %s", _cv_e)
                elif not _ccs:
                    # Fallback: read credit fields via ClienteRepository
                    try:
                        _cli = self._cli_repo
                        _cdata = _cli.get_by_id(self.cliente_actual['id']) if _cli else None
                        if _cdata:
                            _used = float(_cdata.get('credit_balance', 0) or 0)
                            _limit = float(_cdata.get('credit_limit', 0) or 0)
                            if _limit > 0 and (_used + _financed) > _limit:
                                _disp = max(0.0, _limit - _used)
                                QMessageBox.critical(
                                    self, "Crédito insuficiente",
                                    f"Crédito insuficiente para '{self.cliente_actual['nombre']}':\n"
                                    f"  Disponible: ${_disp:,.2f}  |  Requerido: ${_financed:,.2f}\n\n"
                                    "Puede elegir otro método de pago."
                                )
                                return
                    except Exception as _fbe:
                        logger.warning("credit fallback check: %s", _fbe)

            self.finalizar_venta(datos_pago)

    def finalizar_venta(self, datos_pago: Dict[str, Any]):
        """🚀 LÓGICA ENTERPRISE: Delegación total de cálculos y auditorías al Contenedor Central."""
        try:
            usuario = self.obtener_usuario_actual()
            cliente_id = self.cliente_actual['id'] if self.cliente_actual else None
            from core.services.payment_normalization import is_mercado_pago

            carrito_limpio = [
                {
                    'product_id': item['id'],
                    'qty': item['cantidad'],
                    'unit_price': item['precio_unitario'],
                    'es_compuesto': item.get('es_compuesto', 0)
                }
                for item in self.compra_actual
            ]

            # Fase 7: MercadoPago pendiente NO ejecuta venta definitiva.
            if is_mercado_pago(datos_pago.get('forma_pago')):
                mp = getattr(self.container, 'mercado_pago_service', None)
                sales_svc = getattr(self.container, 'sales_service', None)
                if not mp or not sales_svc:
                    raise RuntimeError("Servicio de MercadoPago no disponible.")

                pending = sales_svc.create_pending_payment_sale(
                    branch_id=self.sucursal_id,
                    user=usuario,
                    items=carrito_limpio,
                    client_id=cliente_id,
                    notes=f"Venta pendiente MP. Cajero: {usuario}.",
                    total=float(self.totales.get('total_final', 0.0)),
                )
                folio_pend = pending.get("folio", "")
                result = mp.crear_link(
                    total=float(self.totales.get('total_final', 0.0)),
                    pedido_id=folio_pend or int(datetime.now().timestamp()),
                    descripcion=f"Venta pendiente {folio_pend} — {self.container.config_service.get('nombre_empresa','SPJ POS') if hasattr(self.container,'config_service') else 'SPJ POS'}"
                )
                link = result.get('link') if isinstance(result, dict) else result
                link = link or (result.get('url', '') if isinstance(result, dict) else "")
                if not link:
                    raise RuntimeError("No se pudo generar link de pago MercadoPago.")

                self._ultimo_mp_pending = {
                    "estado": "pendiente_pago",
                    "folio": folio_pend,
                    "url_pago": link,
                }
                QMessageBox.information(
                    self,
                    "Mercado Pago pendiente",
                    f"Se generó link de pago para la venta pendiente {folio_pend}.\n\n{link}\n\n"
                    "La venta no se marcó como completada hasta confirmar el pago."
                )
                self.cancelar_venta(silent=True)
                return

            # ── Guardrail: detectar ítems por debajo del costo (delegado al UC) ─
            try:
                _uc_check = getattr(self.container, 'uc_venta', None)
                if _uc_check:
                    from core.use_cases.venta import ItemCarrito as _IC
                    _ic_items = [_IC(
                        producto_id=it['id'], cantidad=float(it['cantidad']),
                        precio_unit=float(it['precio_unitario']),
                        nombre=it.get('nombre', ''),
                    ) for it in self.compra_actual]
                    alertas = _uc_check.validar_precios_bajo_costo(_ic_items)
                    if alertas:
                        lines = [
                            f"• {a['nombre']}: ${a['precio_venta']:.2f} (costo ${a['costo']:.2f})"
                            for a in alertas
                        ]
                        resp = QMessageBox.warning(
                            self, "⚠️ Venta por debajo del costo",
                            "Los siguientes productos se venden con pérdida:\n\n"
                            + "\n".join(lines)
                            + "\n\n¿Continuar de todas formas?",
                            QMessageBox.Yes | QMessageBox.No
                        )
                        if resp != QMessageBox.Yes:
                            return
            except Exception:
                pass  # No bloquea la venta si la validación falla

            # Fase 2: entrada canónica obligatoria vía ProcesarVentaUC
            _r = self._procesar_venta_via_uc(
                carrito_limpio=carrito_limpio,
                datos_pago=datos_pago,
                cliente_id=cliente_id,
                usuario=usuario,
            )
            folio = _r.folio
            self._ultima_venta_id = _r.venta_id
            self.btn_factura.setEnabled(bool(_r.venta_id))
            self.btn_reimprimir.setEnabled(bool(_r.venta_id))
            if _r.ticket_html:
                self._ticket_html_cache = _r.ticket_html

            self._abrir_cajon()

            # ── v13.4 Fase 2: Actualizar display de puntos de fidelización ─────
            # NOTA ARQUITECTURA: La acreditación de puntos ya es realizada por:
            #   1. ProcesarVentaUC.ejecutar() (paso 4, cuando _uc está activo)
            #   2. wiring.py _loyalty_venta handler en VENTA_COMPLETADA (priority=50)
            # NO llamar loyalty.acreditar_venta() aquí para evitar triple acreditación.
            # Solo actualizamos el display consultando el saldo actualizado.
            puntos_resultado = {"estrellas_ganadas": 0, "saldo_actual": 0,
                                "mensaje_gamificacion": ""}
            try:
                loyalty = getattr(self.container, 'loyalty_service', None)
                if loyalty and cliente_id:
                    # Si el resultado del UC tiene datos de puntos, usarlos directamente
                    _uc_pts = getattr(_r, 'puntos_ganados', None) if '_r' in dir() else None
                    if _uc_pts is not None:
                        puntos_resultado = {
                            "estrellas_ganadas": getattr(_r, 'puntos_ganados', 0),
                            "saldo_actual": getattr(_r, 'puntos_totales', 0),
                            "mensaje_gamificacion": "",
                        }
                    else:
                        # Fallback: consultar saldo sin acreditar
                        _saldo_query = loyalty.saldo(cliente_id)
                        puntos_resultado["saldo_actual"] = _saldo_query
                    # Actualizar display de puntos en UI
                    saldo = puntos_resultado.get("saldo_actual", 0)
                    _pts_ganados = puntos_resultado.get('estrellas_ganadas', 0)
                    if _pts_ganados > 0:
                        self.lbl_puntos_venta.setText(
                            f"⭐ +{_pts_ganados} | Saldo: {saldo}")
                    else:
                        self.lbl_puntos_venta.setText(f"⭐ Saldo: {saldo}")
            except Exception as _loyalty_e:
                logger.debug("Loyalty display post-venta: %s", _loyalty_e)

            # ── v13.4 Fase 3: Tesorería Central ──────────────────────────────
            # Movida a handler _treasury_venta en core/events/wiring.py (VENTA_COMPLETADA,
            # priority=20). La UI ya no llama directamente al treasury_service.
            # El handler ya excluye Mercado Pago y Crédito automáticamente.

            # Build ticket data BEFORE cancelar_venta clears compra_actual
            _items_snapshot = list(self.compra_actual)
            _totales_snapshot = dict(self.totales)
            datos_ticket = {
                'folio':    folio,
                'venta_id': folio,
                'fecha':    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'cajero':   usuario,
                'cliente':  self.cliente_actual['nombre'] if self.cliente_actual else 'Público General',
                'items':    _items_snapshot,
                'totales':  _totales_snapshot,
                'pago':     datos_pago,
                'logo_path': LOGO_TICKET_PATH,
                'empresa':  getattr(self.container, '_nombre_empresa', 'SPJ POS'),
                'puntos_ganados': puntos_resultado.get('estrellas_ganadas', 0),
                'puntos_totales': puntos_resultado.get('saldo_actual', 0),
                'mensaje_psicologico': (
                    puntos_resultado.get('mensaje_gamificacion')
                    or '¡Gracias por su compra!'),
            }
            # Print ticket — single consolidated path
            self._imprimir_ticket_consolidado(datos_ticket)

            Toast.success(
                self,
                f"✅ Venta #{folio} completada",
                f"Total: ${self.totales['total_final']:.2f}",
            )
            if self._reserva_activa_id:
                self._stock_reservas.liberar(self._reserva_activa_id, motivo="confirmada")
                try:
                    from core.events.event_bus import get_bus
                    from core.events.domain_events import (
                        VENTA_CONFIRMADA_RESERVA, STOCK_DESCONTADO_RESERVA, STOCK_ACTUALIZADO,
                    )
                    get_bus().publish(VENTA_CONFIRMADA_RESERVA, {"reserva_id": self._reserva_activa_id, "sucursal_id": self.sucursal_id, "folio": folio})
                    get_bus().publish(STOCK_DESCONTADO_RESERVA, {"reserva_id": self._reserva_activa_id, "sucursal_id": self.sucursal_id, "folio": folio})
                except Exception:
                    pass
                self._reserva_activa_id = None
            # Fase 6: la UI no publica eventos de negocio de inventario.
            # Solo refresca vista local de productos.
            try:
                self.cargar_productos_interactivos()
            except Exception:
                pass
            self.cancelar_venta(silent=True)
            self._actualizar_comision_turno()
            self._tiempo_inicio_venta = None  # reset timer

        except PermissionError as e:
            QMessageBox.warning(self, "Acceso Denegado", str(e))
        except ValueError as e:
            QMessageBox.warning(self, "Aviso de Venta", str(e))
        except Exception as e:
            logger.error(f"Fallo crítico en UI de ventas: {str(e)}")
            QMessageBox.critical(
                self, "Error al procesar venta",
                "No se pudo completar la venta. Verifique stock, pagos y datos del cliente, e intente nuevamente."
            )

    def generar_ticket(self, venta_id: int, datos_pago: Dict[str, Any]):
        try:
            ticket_data = {
                'venta_id': venta_id,
                'fecha': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'cajero': self.obtener_usuario_actual(),
                'cliente': self.cliente_actual['nombre'] if self.cliente_actual else 'Público General',
                'items': self.compra_actual,
                'totales': self.totales,
                'pago': datos_pago,
                'logo_path': LOGO_TICKET_PATH
            }
            # v13.4: PrinterService en vez de safe_print_ticket
            ps = getattr(self.container, 'printer_service', None)
            if ps and ps.has_ticket_printer():
                ps.print_ticket(ticket_data)
            self.guardar_ticket_pdf(ticket_data)
        except Exception as e:
            logger.error("Error generando ticket: %s", e)

    def _procesar_venta_via_uc(self, carrito_limpio, datos_pago, cliente_id, usuario):
        """
        Fase 2: punto único desde POS UI para crear ventas.
        Prohíbe bypass directo a SalesService desde la vista.
        """
        _uc = getattr(self.container, 'uc_venta', None)
        if _uc is None:
            raise RuntimeError(
                "ProcesarVentaUC no disponible en AppContainer. "
                "La UI de ventas no puede ejecutar ventas sin UC canónico."
            )

        from core.use_cases.venta import ItemCarrito, DatosPago as _DP
        _items_uc = [ItemCarrito(
            producto_id=it['product_id'],
            cantidad=float(it['qty']),
            precio_unit=float(it['unit_price']),
            nombre=it.get('name', ''),
            es_compuesto=int(it.get('es_compuesto', 0)),
        ) for it in carrito_limpio]
        _dp = _DP(
            forma_pago=datos_pago['forma_pago'],
            monto_pagado=(
                datos_pago['efectivo_recibido']
                if datos_pago['forma_pago'] == 'Efectivo'
                else self.totales['total_final']
            ),
            cliente_id=cliente_id,
            descuento_global=float(datos_pago.get('descuento', 0)),
            puntos_canjeados=int(datos_pago.get('puntos_canjeados', 0) or 0),
            descuento_puntos=float(datos_pago.get('descuento_puntos', 0.0) or 0.0),
            notas=f"Venta POS Mostrador. Cajero: {usuario}.",
            sucursal_id=self.sucursal_id,
            usuario=usuario,
        )
        _r = _uc.ejecutar(_items_uc, _dp, self.sucursal_id, usuario)
        if not _r.ok:
            raise RuntimeError(_r.error)
        return _r

    def guardar_ticket_pdf(self, ticket_data: Dict[str, Any]):
        try:
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            filename = f"ticket_venta_{ticket_data['venta_id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            filepath = os.path.join(TICKETS_FOLDER, filename)
            printer.setOutputFileName(filepath)
            
            doc = QTextDocument()
            html = self.generar_html_ticket(ticket_data)
            doc.setHtml(html)
            doc.print_(printer)
        except Exception as e:
            logger.error("Error guardando PDF: %s", e)

    def generar_html_ticket(self, ticket_data: Dict[str, Any]) -> str:
        """
        v13.4: Genera HTML usando la PLANTILLA del diseñador de tickets.
        Sustituye {{variables}} con datos reales de la venta.
        Si no hay plantilla guardada, usa template por defecto.
        """
        folio    = ticket_data.get('folio', ticket_data.get('venta_id', ''))
        fecha    = ticket_data.get('fecha', '')
        cajero   = ticket_data.get('cajero', '')
        cliente  = ticket_data.get('cliente', 'Público General')
        empresa  = ticket_data.get('empresa', 'SPJ POS')
        items    = ticket_data.get('items', [])
        totales  = ticket_data.get('totales', {})
        pago     = ticket_data.get('pago', {})

        subtotal    = float(totales.get('subtotal', 0))
        total_final = float(totales.get('total_final', subtotal))
        forma_pago  = pago.get('forma_pago', '')
        recibido    = float(pago.get('efectivo_recibido', total_final))
        cambio      = float(pago.get('cambio', 0))

        # ── Leer configuración completa desde BD ─────────────────────────
        logo_html = ""
        qr_html = ""
        barcode_html = ""
        font_family = "Courier New"
        font_size = 12
        paper_w = 80
        plantilla = ""
        empresa_dir = ""
        empresa_tel = ""

        try:
            _cs = getattr(self.container, 'config_service', None)
            def _cfg(k, d=""):
                if _cs:
                    v = _cs.get(k, d)
                    return v if v else d
                r = self.container.db.execute("SELECT valor FROM configuraciones WHERE clave=?", (k,)).fetchone()
                return r[0] if r and r[0] else d

            # Plantilla del diseñador
            plantilla = _cfg('ticket_template_html', '')

            # Datos empresa
            empresa = _cfg('nombre_empresa', empresa)
            empresa_dir = _cfg('direccion', '')
            empresa_tel = _cfg('telefono_empresa', '')

            # Logo
            logo_b64 = _cfg('ticket_logo_b64', '')
            if logo_b64:
                logo_w = _cfg('ticket_logo_width', '150')
                logo_pos = _cfg('ticket_logo_pos', 'Centrado')
                align = {"Centrado": "center", "Izquierda": "left", "Derecha": "right"}.get(logo_pos, "center")
                logo_html = f'<div style="text-align:{align};margin-bottom:4px;"><img src="{logo_b64}" width="{logo_w}px"></div>'

            # QR
            if _cfg('ticket_qr_enabled', '0') == '1':
                qr_url = _cfg('ticket_qr_url', '')
                qr_size = _cfg('ticket_qr_size', '80')
                qr_content = qr_url or folio
                try:
                    import io as _io, base64 as _b64
                    import qrcode as _qrc
                    qr = _qrc.QRCode(version=1, box_size=3, border=1)
                    qr.add_data(qr_content); qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")
                    buf = _io.BytesIO(); img.save(buf, format='PNG')
                    qr_b64 = _b64.b64encode(buf.getvalue()).decode()
                    qr_html = f'<div style="text-align:center;margin:4px 0;"><img src="data:image/png;base64,{qr_b64}" width="{qr_size}px"></div>'
                except Exception:
                    pass

            # Barcode
            if _cfg('ticket_bc_enabled', '0') == '1':
                bc_type = _cfg('ticket_bc_type', 'Code128')
                barcode_html = f'<div style="text-align:center;font-family:monospace;font-size:9px;margin:4px 0;">||||||||||||| {folio} |||||||||||||<br><small>{bc_type}</small></div>'

            # Font / Paper
            font_family = _cfg('ticket_font_family', 'Courier New')
            try:
                font_size = int(_cfg('ticket_font_size', '12'))
            except Exception:
                font_size = 12
            try:
                paper_w = int(_cfg('ticket_paper_width', '80'))
            except Exception:
                paper_w = 80
        except Exception:
            pass

        # ── Construir items_html ──────────────────────────────────────────
        filas = ""
        for item in items:
            nombre   = str(item.get('nombre', ''))
            cantidad = float(item.get('cantidad', item.get('qty', 0)))
            unidad   = str(item.get('unidad', 'pz'))
            precio   = float(item.get('precio_unitario', item.get('unit_price', 0)))
            total_it = float(item.get('total', item.get('subtotal', cantidad * precio)))
            filas += (f"<tr><td>{nombre}</td>"
                      f"<td>{cantidad:.3f} {unidad}</td>"
                      f"<td style='text-align:right'>${total_it:.2f}</td></tr>")

        # Pago extra
        pago_extra = ""
        if forma_pago == 'Efectivo':
            pago_extra = f"Recibido: ${recibido:.2f} | Cambio: ${cambio:.2f}"
        elif 'dito' in forma_pago:
            pago_extra = f"Saldo adeudado: ${float(pago.get('saldo_credito', total_final)):.2f}"

        # ── Sustitución de variables en plantilla ─────────────────────────
        if plantilla:
            variables = {
                'folio': folio,
                'fecha': fecha,
                'cajero': cajero,
                'cliente_nombre': cliente,
                'total': f"${total_final:.2f}",
                'subtotal': f"${subtotal:.2f}",
                'descuento': f"${float(totales.get('descuento', 0)):.2f}",
                'forma_pago': forma_pago,
                'cambio': f"${cambio:.2f}",
                'puntos_ganados': str(ticket_data.get('puntos_ganados', 0)),
                'puntos_totales': str(ticket_data.get('puntos_totales', 0)),
                'mensaje_psicologico': ticket_data.get('mensaje_psicologico', '¡Gracias por su compra!'),
                'logo': logo_html,
                'qr_code': qr_html,
                'barcode': barcode_html,
                'nombre_empresa': empresa,
                'direccion': empresa_dir,
                'telefono': empresa_tel,
                'items_html': filas,
            }
            html_body = plantilla
            for k, v in variables.items():
                html_body = html_body.replace('{{' + k + '}}', str(v))

            # Envolver con font settings
            html = f"""<html><head><meta charset='utf-8'><style>
            body {{ font-family:'{font_family}',monospace; font-size:{font_size}px;
                   margin:5px; max-width:{paper_w * 3}px; }}
            table {{ width:100%; border-collapse:collapse; font-size:{max(font_size-1,9)}px; }}
            th {{ padding:3px; text-align:left; border-bottom:1px solid #ccc; }}
            td {{ padding:2px 3px; vertical-align:top; }}
            hr {{ border:none; border-top:1px dashed #000; margin:6px 0; }}
            </style></head><body>{html_body}</body></html>"""
            return html

        # ── Fallback: template por defecto (sin diseñador) ────────────────
        html = f"""<html><head><meta charset='utf-8'><style>
        body{{font-family:'{font_family}',monospace;font-size:{font_size}px;margin:10px;max-width:{paper_w*3}px;}}
        .center{{text-align:center;}} .bold{{font-weight:bold;}}
        .sep{{border-top:1px dashed #000;margin:6px 0;}}
        table{{width:100%;border-collapse:collapse;font-size:{max(font_size-1,9)}px;}}
        th{{background:#f0f0f0;padding:3px;text-align:left;}}
        td{{padding:2px 3px;vertical-align:top;}}
        .right{{text-align:right;}} .total-row{{font-weight:bold;font-size:{font_size+1}px;}}
        </style></head><body>
        <div class='center'>
        {logo_html}
        <div class='bold' style='font-size:{font_size+3}px;'>{empresa}</div>
        <div>{empresa_dir}</div>
        <div>Tel: {empresa_tel}</div>
        <div>Folio: <b>{folio}</b></div>
        <div>{fecha}</div>
        <div>Cajero: {cajero} | Cliente: {cliente}</div></div>
        <div class='sep'></div>
        <table><thead><tr><th>Producto</th><th>Cant</th><th class='right'>Total</th></tr></thead>
        <tbody>{filas}</tbody></table>
        <div class='sep'></div>
        <div class='right'>
        <p>Subtotal: ${subtotal:.2f}</p>
        <p class='total-row'>TOTAL: ${total_final:.2f}</p>
        <p>Pago: {forma_pago}</p>
        <p>{pago_extra}</p></div>
        <div class='sep'></div>
        {qr_html}
        {barcode_html}
        <div class='center'><p>¡Gracias por su compra!</p></div>
        </body></html>"""
        return html

    def cancelar_venta(self, silent: bool = False):
        if not silent and self.compra_actual:
            respuesta = QMessageBox.question(self, "Confirmar", "¿Cancelar la venta actual?", QMessageBox.Yes | QMessageBox.No)
            if respuesta == QMessageBox.No: return
                
        self.compra_actual.clear()
        if self._reserva_activa_id:
            try:
                self._stock_reservas.liberar(self._reserva_activa_id, motivo="cancelada")
                from core.events.event_bus import get_bus
                from core.events.domain_events import VENTA_SUSPENDIDA_CANCELADA, STOCK_RESERVA_LIBERADA
                get_bus().publish(VENTA_SUSPENDIDA_CANCELADA, {"reserva_id": self._reserva_activa_id, "sucursal_id": self.sucursal_id})
                get_bus().publish(STOCK_RESERVA_LIBERADA, {"reserva_id": self._reserva_activa_id, "sucursal_id": self.sucursal_id})
            except Exception:
                pass
            self._reserva_activa_id = None
        self.limpiar_seleccion_producto()
        self.limpiar_cliente()
        self.actualizar_tabla_compra()
        self.calcular_totales()
        if not silent: self.mostrar_mensaje("Información", "Venta cancelada.")

    def showEvent(self, event):
        """Auto-focus en campo de búsqueda al mostrar el módulo."""
        super().showEvent(event)
        try:
            self.txt_busqueda.setFocus()
            self.txt_busqueda.selectAll()
        except Exception:
            pass

    def _generar_factura(self) -> None:
        """Abre el diálogo para generar CFDI de la última venta."""
        from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit, QComboBox,
                                      QDialogButtonBox, QVBoxLayout, QLabel, QMessageBox)
        if not hasattr(self, '_ultima_venta_id') or not self._ultima_venta_id:
            QMessageBox.warning(self, "Aviso", "Primero realiza una venta."); return

        dlg = QDialog(self); dlg.setWindowTitle("🧾 Generar CFDI"); dlg.setMinimumWidth(400)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"Venta #{self._ultima_venta_id} — Datos del receptor"))
        form = QFormLayout()
        txt_rfc    = QLineEdit("XAXX010101000")
        txt_nombre = QLineEdit("PUBLICO EN GENERAL")
        cmb_uso    = QComboBox()
        for code, label in [("S01","Sin efectos fiscales"),("G01","Adquisición de mercancias"),
                             ("G03","Gastos en general"),("D01","Honorarios médicos"),
                             ("CP01","Pagos")]:
            cmb_uso.addItem(f"{code} — {label}", code)
        form.addRow("RFC receptor:", txt_rfc)
        form.addRow("Nombre:", txt_nombre)
        form.addRow("Uso CFDI:", cmb_uso)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() != QDialog.Accepted: return

        try:
            cfdi_svc = getattr(self.container, 'cfdi_service', None)
            if not cfdi_svc:
                QMessageBox.warning(self, "CFDI", "Servicio CFDI no disponible."); return
            result = cfdi_svc.generar_cfdi(
                venta_id       = self._ultima_venta_id,
                cliente_rfc    = txt_rfc.text().strip().upper(),
                cliente_nombre = txt_nombre.text().strip(),
                cliente_uso_cfdi = cmb_uso.currentData(),
            )
            if result.get("error") and not result.get("xml"):
                QMessageBox.critical(self, "Error CFDI", result["error"]); return

            msg = (f"✅ CFDI generado\n\n"
                   f"Folio: {result['folio']}\n"
                   f"UUID: {result['uuid'][:18]}...\n"
                   f"Estado: {'Timbrado' if result['timbrado'] else 'Borrador (sin PAC)'}\n")
            if result.get("error"):
                msg += f"\n⚠️ Aviso: {result['error']}"
            QMessageBox.information(self, "CFDI", msg)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def closeEvent(self, event):
        self.timer_bascula.stop()
        self.desconectar_eventos_sistema()
        if hasattr(self, 'bascula') and self.bascula and self.bascula.is_open:
            self.bascula.close()
        super().closeEvent(event)

    def registrar_actualizacion(self, tipo_evento='', detalles=None, usuario=None):
        try:
            if tipo_evento in ('precio_actualizado','producto_actualizado','stock_actualizado'):
                if hasattr(self,'actualizar_datos'): self.actualizar_datos()
        except Exception: pass

    def changeEvent(self, event):
        if event.type() == event.PaletteChange:
            self.aplicar_tema_desde_config()
        super().changeEvent(event)

    # ── Devolución / Cancelación ─────────────────────────────────────────────
    def _reimprimir_ultima_venta(self) -> None:
        """Reimprime ticket térmico (ESC/POS) de la última venta."""
        vid = getattr(self, '_ultima_venta_id', None)
        if not vid:
            QMessageBox.warning(self, "Sin venta", "No hay venta reciente para reimprimir.")
            return
        try:
            db = self.container.db
            venta = db.execute(
                "SELECT folio, fecha, usuario, forma_pago, efectivo_recibido, cambio, total "
                "FROM ventas WHERE id=?", (vid,)).fetchone()
            if not venta:
                QMessageBox.warning(self, "No encontrada", f"Venta ID {vid} no encontrada."); return
            items_raw = db.execute(
                "SELECT p.nombre, dv.cantidad, dv.precio_unitario, dv.subtotal, "
                "COALESCE(p.unidad,'pz') as unidad "
                "FROM detalles_venta dv JOIN productos p ON p.id=dv.producto_id "
                "WHERE dv.venta_id=?", (vid,)).fetchall()
            items = [{'nombre':r[0],'cantidad':float(r[1]),'precio_unitario':float(r[2]),
                      'total':float(r[3]),'unidad':r[4]} for r in items_raw]
            total = float(venta[6] or 0)
            datos_ticket = {
                'folio':    venta[0], 'venta_id': venta[0],
                'fecha':    str(venta[1] or '')[:16],
                'cajero':   venta[2] or self.obtener_usuario_actual(),
                'cliente':  'Público General',
                'items':    items,
                'totales':  {'subtotal': total, 'impuestos': 0, 'total_final': total},
                'pago':     {'forma_pago': venta[3] or 'Efectivo',
                             'efectivo_recibido': float(venta[4] or total),
                             'cambio': float(venta[5] or 0)},
                'empresa':  getattr(self.container, '_nombre_empresa', 'SPJ POS'),
                'logo_path': LOGO_TICKET_PATH,
            }
            # Fase 10: Reimpresión térmica separada de PDF de auditoría.
            ps = getattr(self.container, 'printer_service', None)
            if not ps or not ps.has_ticket_printer():
                QMessageBox.critical(self, "Impresión térmica no configurada",
                                     "No hay impresora térmica ESC/POS configurada.")
                return
            ps.print_ticket(datos_ticket)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _guardar_pdf_auditoria_ultima_venta(self) -> None:
        """Genera PDF de auditoría de la última venta sin requerir impresora térmica."""
        vid = getattr(self, '_ultima_venta_id', None)
        if not vid:
            QMessageBox.warning(self, "Sin venta", "No hay venta reciente para PDF.")
            return
        try:
            db = self.container.db
            venta = db.execute(
                "SELECT folio, fecha, usuario, forma_pago, efectivo_recibido, cambio, total "
                "FROM ventas WHERE id=?", (vid,)).fetchone()
            if not venta:
                QMessageBox.warning(self, "No encontrada", f"Venta ID {vid} no encontrada.")
                return
            ticket_data = {
                'folio': venta[0], 'venta_id': venta[0], 'fecha': str(venta[1] or '')[:16],
                'cajero': venta[2] or self.obtener_usuario_actual(), 'cliente': 'Público General',
                'items': [], 'totales': {'subtotal': float(venta[6] or 0), 'total_final': float(venta[6] or 0)},
                'pago': {'forma_pago': venta[3] or 'Efectivo', 'efectivo_recibido': float(venta[4] or 0), 'cambio': float(venta[5] or 0)},
            }
            self.guardar_ticket_pdf(ticket_data)
            QMessageBox.information(self, "PDF auditoría", "PDF de auditoría generado correctamente.")
        except Exception as e:
            QMessageBox.critical(self, "Error PDF", str(e))

    def abrir_devolucion(self) -> None:
        """Abre el diálogo de devolución/cancelación de venta anterior."""
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
            QPushButton, QTableWidget, QTableWidgetItem,
            QHeaderView, QAbstractItemView, QMessageBox,
            QGroupBox, QFormLayout, QComboBox
        )
        from PyQt5.QtCore import Qt
        dlg = QDialog(self)
        dlg.setWindowTitle("↩ Devolución / Cancelación de Venta")
        dlg.setMinimumWidth(620); dlg.setMinimumHeight(480)
        lay = QVBoxLayout(dlg)

        grp = QGroupBox("Buscar venta a devolver")
        sf = QFormLayout(grp)
        txt_folio = QLineEdit()
        txt_folio.setPlaceholderText("Folio VNT-… o ID")
        txt_folio.setProperty("class", "standardInput")
        sf.addRow("Folio / ID:", txt_folio)
        lay.addWidget(grp)

        lbl_info = QLabel("Ingresa el folio y presiona Buscar")
        lbl_info.setProperty("class", "text-secondary caption")
        lay.addWidget(lbl_info)

        tbl = QTableWidget(0, 4)
        tbl.setHorizontalHeaderLabels(["Producto","Cant.","Precio","Subtotal"])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setProperty("class", "standardTable")
        lay.addWidget(tbl)

        cmb_motivo = QComboBox()
        cmb_motivo.addItems(["Producto defectuoso","Error de cajero","Cliente arrepentido","Otro"])
        cmb_motivo.setProperty("class", "standardCombobox")
        lay.addWidget(QLabel("Motivo:"))
        lay.addWidget(cmb_motivo)

        btn_bar = QHBoxLayout()
        btn_buscar = create_primary_button(dlg, "🔍 Buscar", "Buscar venta por folio")
        btn_cancel = create_danger_button(dlg, "❌ Cancelar venta", "Cancelar venta completa")
        btn_cancel.setEnabled(False)
        btn_cerrar = create_secondary_button(dlg, "Cerrar", "Cerrar diálogo")
        btn_cerrar.clicked.connect(dlg.reject)
        btn_bar.addWidget(btn_buscar)
        btn_bar.addWidget(btn_cancel)
        btn_bar.addStretch()
        btn_bar.addWidget(btn_cerrar)
        lay.addLayout(btn_bar)

        _vid = [None]

        def _buscar():
            folio = txt_folio.text().strip()
            if not folio: return
            db = self.container.db
            row = db.execute(
                "SELECT id,folio,total,estado FROM ventas WHERE folio=? OR CAST(id AS TEXT)=?",
                (folio, folio)
            ).fetchone()
            if not row:
                lbl_info.setText("❌ Venta no encontrada"); btn_cancel.setEnabled(False); return
            _vid[0] = row['id']
            lbl_info.setText(f"✅ {row['folio']} — Total ${float(row['total']):.2f} — {row['estado']}")
            items = db.execute(
                "SELECT nombre,cantidad,precio_unitario,(cantidad*precio_unitario) "
                "FROM detalles_venta WHERE venta_id=?", (row['id'],)
            ).fetchall()
            tbl.setRowCount(0)
            for i, it in enumerate(items):
                tbl.insertRow(i)
                for j, v in enumerate(it):
                    tbl.setItem(i, j, QTableWidgetItem(f"{float(v):.2f}" if j > 0 else str(v)))
            btn_cancel.setEnabled(row['estado'] not in ('cancelada','revertida'))

        def _cancelar():
            # v13.4: Verificar permiso antes de cancelar venta
            try:
                from core.permissions import verificar_permiso
                if not verificar_permiso(self.container, "ventas.cancelar", dlg):
                    return
            except Exception: pass
            vid = _vid[0]
            if not vid: return
            motivo = cmb_motivo.currentText()
            if QMessageBox.question(dlg, "Confirmar",
                    f"¿Cancelar esta venta?\nMotivo: {motivo}",
                    QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return
            try:
                from core.services.sales_reversal_service import SalesReversalService
                branch_id = int(getattr(self, "sucursal_id", 1) or 1)
                usuario = (getattr(self, "usuario_actual", "") or getattr(self, "usuario", "") or "").strip()
                if not usuario:
                    raise ValueError("Usuario no identificado para cancelar venta.")
                SalesReversalService(self.container.db, branch_id=branch_id).cancel_sale(
                    vid, usuario
                )
            except Exception as e:
                # Hardening Fase 0:
                # ❌ Nunca caer a UPDATE directo de estado (rompe reversa contable/inventario).
                # ✔  Fallar explícitamente para preservar integridad.
                QMessageBox.critical(
                    dlg,
                    "Error de cancelación",
                    ("No se pudo cancelar con reversa segura.\n"
                     "La venta NO fue alterada.\n\n"
                     f"Detalle: {e}")
                )
                return
            Toast.success(self, "✅ Venta cancelada", "La devolución se aplicó correctamente.")
            dlg.accept()

        btn_buscar.clicked.connect(_buscar)
        btn_cancel.clicked.connect(_cancelar)
        dlg.exec_()
