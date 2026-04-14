# modulos/ventas.py
# MÓDULO DE VENTAS ENTERPRISE CON INYECCIÓN DE DEPENDENCIAS Y HAL (Hardware Abstraction Layer)

from modulos.spj_styles import spj_btn, apply_btn_styles
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
from PyQt5.QtGui import QIcon, QDoubleValidator, QPixmap, QImage, QColor, QTextDocument, QFont, QPalette
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog

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

class ProductCard(QFrame):
    """Widget interactivo que respeta completamente los temas del sistema."""
    product_selected = pyqtSignal(dict) 

    # 🛠️ FIX ENTERPRISE: Recibe producto_data, no el container
    def __init__(self, producto_data: dict, parent: QWidget = None):
        super().__init__(parent)
        self.producto = producto_data
        self.is_selected = False
        self._is_hovering = False
        self.original_size = QSize(160, 220)
        self.zoom_size = QSize(170, 230)
        
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.original_size)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        
        self.setProperty("class", "product-card")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)

        self.lbl_imagen = QLabel()
        self.lbl_imagen.setAlignment(Qt.AlignCenter)
        self.lbl_imagen.setFixedSize(140, 120)
        self.lbl_imagen.setProperty("class", "product-image")
        self._load_image()
        
        self.lbl_nombre = QLabel(self.producto['nombre'])
        self.lbl_nombre.setAlignment(Qt.AlignCenter)
        self.lbl_nombre.setWordWrap(True)
        self.lbl_nombre.setProperty("class", "product-name")
        
        self.lbl_precio = QLabel(f"${self.producto['precio']:.2f} / {self.producto['unidad']}")
        self.lbl_precio.setAlignment(Qt.AlignCenter)
        self.lbl_precio.setProperty("class", "product-price")
        
        existencia = self.producto.get('existencia', 0)
        self.lbl_stock = QLabel(f"Stock: {existencia:.2f}")
        self.lbl_stock.setAlignment(Qt.AlignCenter)
        self.lbl_stock.setProperty("class", "product-stock")

        layout.addWidget(self.lbl_imagen)
        layout.addWidget(self.lbl_nombre)
        layout.addWidget(self.lbl_precio)
        layout.addWidget(self.lbl_stock)
        layout.addStretch(1)
        
        self.shadow_effect = QGraphicsDropShadowEffect(self)
        self.shadow_effect.setBlurRadius(15)
        self.shadow_effect.setXOffset(2)
        self.shadow_effect.setYOffset(2)
        self.update_shadow_color()
        self.setGraphicsEffect(self.shadow_effect)

    def update_shadow_color(self):
        text_color = QColor(255, 255, 255)
        try:
            text_color = self.palette().color(QPalette.Text)
        except:
            pass
            
        brightness = text_color.red() * 0.299 + text_color.green() * 0.587 + text_color.blue() * 0.114
        
        if brightness > 128:
            self.shadow_effect.setColor(QColor(0, 0, 0, 60))
        else:
            self.shadow_effect.setColor(QColor(0, 0, 0, 100))

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
        else:
            self.setProperty("class", "product-card")
        self.style().unpolish(self)
        self.style().polish(self)
        
    def enterEvent(self, event):
        self._is_hovering = True
        self.animate_size(self.zoom_size)
        self.setProperty("class", "product-card-hover")
        self.style().unpolish(self)
        self.style().polish(self)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovering = False
        self.animate_size(self.original_size)
        if self.is_selected:
            self.setProperty("class", "product-card-selected")
        else:
            self.setProperty("class", "product-card")
        self.style().unpolish(self)
        self.style().polish(self)
        super().leaveEvent(event)
        
    def animate_size(self, new_size):
        self.setFixedSize(new_size)

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
        btn_cancelar.setProperty("class", "cancel-button")
        btn_aceptar.setProperty("class", "accept-button")
        
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
                 loyalty_balance: Dict = None):
        super().__init__(parent)
        self.setWindowTitle("Procesar Pago")
        self.setModal(True)
        self.setFixedSize(520, 480)
        self.total_a_pagar = float(total_a_pagar) if total_a_pagar is not None else 0.0
        self.total_original = self.total_a_pagar
        self.efectivo_recibido = 0.0
        self.cambio = 0.0
        self.forma_pago = "Efectivo"
        self.saldo_credito = 0.0
        # v13.4 Fase 2: Loyalty redemption
        self._loyalty = loyalty_balance or {}
        self.puntos_a_canjear = 0
        self.descuento_puntos = 0.0
        self.init_ui()
        self.conectar_eventos()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        titulo = QLabel("PROCESAR PAGO")
        titulo.setProperty("class", "payment-title")
        layout.addWidget(titulo)
        
        self.lbl_total = QLabel(f"Total a pagar: ${self.total_a_pagar:.2f}")
        self.lbl_total.setProperty("class", "payment-total")
        self.lbl_total.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_total)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        
        self.cmb_forma_pago = QComboBox()
        self.cmb_forma_pago.addItems(["Efectivo", "Tarjeta", "Transferencia", "Crédito", "Pago Mixto", "Mercado Pago"])
        self.cmb_forma_pago.setProperty("class", "payment-combobox")
        form_layout.addRow("Forma de Pago:", self.cmb_forma_pago)
        
        self.txt_recibido = QDoubleSpinBox()
        self.txt_recibido.setRange(0.00, 99999.00)
        self.txt_recibido.setDecimals(2)
        self.txt_recibido.setValue(self.total_a_pagar)
        self.txt_recibido.setSingleStep(10.0)
        self.txt_recibido.setPrefix("$ ")
        self.txt_recibido.setMinimumHeight(36)
        self.txt_recibido.setStyleSheet("font-size:16px;font-weight:bold;")
        # v13.4: Select all on click so user can type directly
        self.txt_recibido.lineEdit().setReadOnly(False)
        self.txt_recibido.setProperty("class", "payment-spinbox")
        form_layout.addRow("💵 Monto Recibido:", self.txt_recibido)
        
        self.lbl_cambio = QLabel("Cambio: $0.00")
        self.lbl_cambio.setProperty("class", "payment-change")
        form_layout.addRow("", self.lbl_cambio)

        # v13.4 Fase 2: Sección de canje de puntos
        self._loyalty_widget = QWidget()
        _loy_lay = QVBoxLayout(self._loyalty_widget)
        _loy_lay.setContentsMargins(0, 0, 0, 0)
        _loy_lay.setSpacing(3)
        pts = self._loyalty.get("puntos", 0)
        valor = self._loyalty.get("valor_canje", 0)
        puede = self._loyalty.get("puede_canjear", False)

        _loy_header = QHBoxLayout()
        self._lbl_puntos = QLabel(f"⭐ {pts} puntos disponibles (=${valor:.2f})")
        self._lbl_puntos.setStyleSheet("font-weight:bold;")
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
        self._lbl_desc_puntos.setStyleSheet("font-weight:bold;")
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
        self.lbl_mixto_diff.setProperty("class", "text-danger")
        self.lbl_mixto_diff.setStyleSheet("font-size:11px;")
        _ml.addWidget(self.lbl_mixto_diff)
        self._mixto_widget.hide()
        form_layout.addRow("", self._mixto_widget)
        
        layout.addLayout(form_layout)
        layout.addStretch(1)
        
        btn_layout = QHBoxLayout()
        self.btn_cancelar = QPushButton("❌ Cancelar")
        self.btn_aceptar = QPushButton("✅ Confirmar Pago")
        self.btn_cancelar.setProperty("class", "payment-cancel-button")
        self.btn_aceptar.setProperty("class", "payment-accept-button")
        
        btn_layout.addWidget(self.btn_cancelar)
        btn_layout.addWidget(self.btn_aceptar)
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
        self.forma_pago = forma_pago
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
                self.lbl_mp_info.setProperty("class", "text-info")
                self.lbl_mp_info.setStyleSheet("font-size:11px;font-weight:bold;")
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
        if self.forma_pago == "Efectivo":
            self.cambio = round(self.efectivo_recibido - self.total_a_pagar, 2)
            self.lbl_cambio.setText(f"Cambio: ${self.cambio:.2f}")
            if self.cambio < 0:
                self.btn_aceptar.setEnabled(False)
                self.lbl_cambio.setProperty("class", "payment-change-negative")
            else:
                self.btn_aceptar.setEnabled(True)
                self.lbl_cambio.setProperty("class", "payment-change")
        else:
            self.efectivo_recibido = self.total_a_pagar
            self.cambio = 0.0
            self.btn_aceptar.setEnabled(True)

    def _toggle_canje(self, activado: bool):
        """v13.4 Fase 2: Activa/desactiva el canje de puntos de fidelidad."""
        if not hasattr(self, '_spin_puntos'):
            return
        self._spin_puntos.setEnabled(activado)
        if activado:
            self._recalcular_canje(self._spin_puntos.value())
        else:
            self.puntos_a_canjear = 0
            self.descuento_puntos = 0.0
            self._lbl_desc_puntos.setText("")
            # Recalcular total sin descuento de puntos
            self.total_a_pagar = self.total_original
            self.lbl_total.setText(f"Total a pagar: ${self.total_a_pagar:.2f}")
            self.calcular_cambio()

    def _recalcular_canje(self, puntos: int):
        """v13.4 Fase 2: Recalcula el descuento por canje de puntos."""
        if not hasattr(self, '_chk_canjear') or not self._chk_canjear.isChecked():
            return
        self.puntos_a_canjear = puntos
        valor_por_punto = self._loyalty.get("valor_por_punto", 0.01)  # $0.01 por punto default
        self.descuento_puntos = round(puntos * valor_por_punto, 2)
        self._lbl_desc_puntos.setText(f"-=${self.descuento_puntos:.2f}")
        # Aplicar descuento al total
        self.total_a_pagar = max(0.0, self.total_original - self.descuento_puntos)
        self.lbl_total.setText(f"Total a pagar: ${self.total_a_pagar:.2f}")
        self.calcular_cambio()

    def _recalcular_mixto(self):
        if self.forma_pago != "Pago Mixto":
            return
        ef = self.spin_efectivo_mixto.value()
        ta = self.spin_tarjeta_mixto.value()
        total = ef + ta
        diff = round(total - self.total_a_pagar, 2)
        if abs(diff) < 0.01:
            self.lbl_mixto_diff.setText("✅ Cuadra")
            self.lbl_mixto_diff.setProperty("class", "text-success")
            self.lbl_mixto_diff.setStyleSheet("font-size:11px;")
            self.btn_aceptar.setEnabled(True)
        elif diff > 0:
            self.lbl_mixto_diff.setText(f"Sobran ${diff:.2f}")
            self.lbl_mixto_diff.setProperty("class", "text-warning")
            self.lbl_mixto_diff.setStyleSheet("font-size:11px;")
            self.btn_aceptar.setEnabled(True)
        else:
            self.lbl_mixto_diff.setText(f"Faltan ${abs(diff):.2f}")
            self.lbl_mixto_diff.setProperty("class", "text-danger")
            self.lbl_mixto_diff.setStyleSheet("font-size:11px;")
            self.btn_aceptar.setEnabled(False)

    def get_datos_pago(self) -> Dict[str, Any]:
        return {
            "forma_pago": self.forma_pago,
            "total_pagado": self.total_a_pagar,
            "efectivo_recibido": (
                self.spin_efectivo_mixto.value()
                if self.forma_pago == "Pago Mixto"
                else self.efectivo_recibido
            ),
            "monto_tarjeta_mixto": (
                self.spin_tarjeta_mixto.value()
                if self.forma_pago == "Pago Mixto" else 0.0
            ),
            "cambio": self.cambio,
            "saldo_credito": self.txt_saldo_credito.value() if self.forma_pago == "Crédito" else 0.0
        }

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
        if not texto: return
        rows = self.conexion.execute(
            "SELECT id, nombre, telefono FROM clientes WHERE (nombre LIKE ? OR telefono LIKE ?) AND activo=1 LIMIT 5",
            (f"%{texto}%", f"%{texto}%")
        ).fetchall()
        if not rows:
            self.lbl_cliente_encontrado.setText("❌ No encontrado")
            self.lbl_cliente_encontrado.setVisible(True)
            self._cliente_id_sel = None
            self.btn_asignar_existente.setEnabled(False)
            return
        if len(rows) == 1:
            self._seleccionar_cliente(rows[0])
        else:
            items = [f"{r[1]} — {r[2] or ''}" for r in rows]
            item, ok = QInputDialog.getItem(self, "Seleccionar cliente", "Múltiples resultados:", items, 0, False)
            if ok:
                idx = items.index(item)
                self._seleccionar_cliente(rows[idx])

    def _seleccionar_cliente(self, row):
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
            cur = self.conexion.execute(
                "INSERT INTO clientes (nombre, telefono, codigo_qr, activo, puntos) VALUES (?,?,?,1,0)",
                (nombre, telefono or None, qr_code)
            )
            cliente_id = cur.lastrowid
            self.conexion.commit()
            self.resultado = {'cliente_id': cliente_id, 'nuevo': True}
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo crear cliente: {exc}")

# ==============================================================================
# 5. MODULO PRINCIPAL DE VENTAS ENTERPRISE
# ==============================================================================

class ModuloVentas(ModuloBase):
    """Módulo principal de Punto de Venta con báscula automática, temas heredados y Arquitectura Enterprise."""

    # 🛠️ FIX ENTERPRISE: Recibe container en lugar de conexion cruda
    def __init__(self, container, parent: QWidget = None):
        super().__init__(container.db, parent)
        
        self.container = container
        self.conexion = container.db  # Mantenemos compatibilidad con consultas legacy
        
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

        self._theme_initialized = False
        self.gestor_temas = GestorTemas(self.conexion)

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
        if hasattr(self, "lbl_estado_terminal"):
            self.lbl_estado_terminal.setText(f"Terminal: ❌ No disponible  |  🏪 {sucursal_nombre}")
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
        except sqlite3.Error as e:
            logger.error(f"Error actualizando completer: {e}")

    def conectar_eventos(self):
        self.txt_busqueda.returnPressed.connect(self.buscar_productos)
        self.btn_buscar.clicked.connect(self.buscar_productos)
        self.btn_limpiar_busqueda.clicked.connect(self.limpiar_busqueda_productos)
        self.txt_busqueda.textChanged.connect(self.buscar_productos_en_tiempo_real)
        self.txt_cliente.returnPressed.connect(self.buscar_cliente)
        self.btn_buscar_cliente.clicked.connect(self.buscar_cliente)
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
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.setProperty("class", "main-splitter")
        splitter.setHandleWidth(3)
        
        # --- PANEL IZQUIERDO (Productos) ---
        panel_izquierdo = QWidget()
        layout_izquierdo = QVBoxLayout(panel_izquierdo)
        layout_izquierdo.setSpacing(8)
        layout_izquierdo.setContentsMargins(5, 5, 5, 5)
        
        group_busqueda = QGroupBox("🔍 Buscar Producto")
        group_busqueda.setMaximumHeight(80)
        group_busqueda.setProperty("class", "search-group")
        busqueda_layout = QHBoxLayout(group_busqueda)
        busqueda_layout.setContentsMargins(8, 8, 8, 8)
        
        self.txt_busqueda = QLineEdit()
        self.txt_busqueda.setPlaceholderText("🔍 Escanear o escribir producto...")
        self.txt_busqueda.setProperty("class", "search-input")
        self.txt_busqueda.setToolTip(
            "Campo activo para PRODUCTOS\n"
            "Cuando este campo tenga foco, el scanner agrega productos al carrito.")

        # Scanner context signals
        # Use event filter instead of monkey-patching (avoids sipBadCatcherResult)
        self._filter_busqueda = _ScanContextFilter(self, "producto", self.txt_busqueda)
        self.txt_busqueda.installEventFilter(self._filter_busqueda)
        self.btn_buscar = QPushButton("Buscar")
        self.btn_buscar.setProperty("class", "search-button")
        self.btn_limpiar_busqueda = QPushButton("❌")
        self.btn_limpiar_busqueda.setToolTip("Limpiar búsqueda")
        self.btn_limpiar_busqueda.setFixedWidth(40)
        self.btn_limpiar_busqueda.setProperty("class", "icon-button")
        
        busqueda_layout.addWidget(self.txt_busqueda)
        busqueda_layout.addWidget(self.btn_buscar)
        busqueda_layout.addWidget(self.btn_limpiar_busqueda)
        layout_izquierdo.addWidget(group_busqueda)
        
        group_productos = QGroupBox("📦 Productos Disponibles")
        group_productos.setProperty("class", "products-group")
        productos_layout = QVBoxLayout(group_productos)
        
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
        
        status_layout = QHBoxLayout()
        self.lbl_estado_bascula = QLabel("Báscula: ❌ No conectada")
        self.lbl_estado_bascula.setProperty("class", "status-label")
        self.lbl_estado_terminal = QLabel("Terminal: ❌ No disponible")
        self.lbl_estado_terminal.setProperty("class", "status-label")
        status_layout.addWidget(self.lbl_estado_bascula)
        status_layout.addWidget(self.lbl_estado_terminal)
        status_layout.addStretch()
        layout_izquierdo.addLayout(status_layout)
        
        # --- PANEL DERECHO (Carrito y Acciones) ---
        panel_derecho = QWidget()
        panel_derecho.setMinimumWidth(420)
        layout_derecho = QVBoxLayout(panel_derecho)
        layout_derecho.setSpacing(8)
        layout_derecho.setContentsMargins(5, 5, 5, 5)
        
        group_cliente = QGroupBox("👤 Cliente")
        group_cliente.setProperty("class", "client-group")
        cliente_layout = QVBoxLayout(group_cliente)
        cliente_layout.setContentsMargins(6, 6, 6, 6)
        cliente_layout.setSpacing(3)
        
        self.txt_cliente = QLineEdit()
        self.txt_cliente.setPlaceholderText("💳 Escanear tarjeta o buscar cliente...")
        self.txt_cliente.setProperty("class", "client-input")
        self.txt_cliente.setToolTip(
            "Campo activo para CLIENTES / TARJETAS\n"
            "Cuando este campo tenga foco, el scanner carga el cliente por tarjeta o ID.")

        # Scanner context signals
        # Use event filter instead of monkey-patching (avoids sipBadCatcherResult)
        self._filter_cliente = _ScanContextFilter(self, "cliente", self.txt_cliente)
        self.txt_cliente.installEventFilter(self._filter_cliente)
        self.btn_buscar_cliente = QPushButton("🔍")
        self.btn_buscar_cliente.setFixedWidth(40)
        self.btn_buscar_cliente.setProperty("class", "icon-button")
        self.btn_agregar_cliente = QPushButton("➕")
        self.btn_agregar_cliente.setFixedWidth(40)
        self.btn_agregar_cliente.setProperty("class", "icon-button")
        self.btn_limpiar_cliente = QPushButton("❌")
        self.btn_limpiar_cliente.setFixedWidth(40)
        self.btn_limpiar_cliente.setProperty("class", "icon-button")
        
        busqueda_cliente_layout = QHBoxLayout()
        busqueda_cliente_layout.addWidget(self.txt_cliente)
        busqueda_cliente_layout.addWidget(self.btn_buscar_cliente)
        busqueda_cliente_layout.addWidget(self.btn_agregar_cliente)
        busqueda_cliente_layout.addWidget(self.btn_limpiar_cliente)
        cliente_layout.addLayout(busqueda_cliente_layout)
        
        self.lbl_nombre_cliente = QLabel("Público General")
        self.lbl_puntos_cliente = QLabel("Puntos: 0")
        self.lbl_telefono_cliente = QLabel("Teléfono: -")  
        self.lbl_email_cliente = QLabel("Email: -")        
        
        self.lbl_nombre_cliente.setProperty("class", "client-info-highlight")
        self.lbl_puntos_cliente.setProperty("class", "client-info-highlight")
        self.lbl_telefono_cliente.setProperty("class", "client-info")
        self.lbl_email_cliente.setProperty("class", "client-info")
        
        cliente_info_layout = QHBoxLayout()
        cliente_info_layout.addWidget(self.lbl_nombre_cliente)
        cliente_info_layout.addStretch()
        cliente_info_layout.addWidget(self.lbl_puntos_cliente)
        cliente_layout.addLayout(cliente_info_layout)
        
        cliente_info2_layout = QHBoxLayout()
        cliente_info2_layout.addWidget(self.lbl_telefono_cliente)
        cliente_info2_layout.addStretch()
        cliente_info2_layout.addWidget(self.lbl_email_cliente)
        cliente_layout.addLayout(cliente_info2_layout)
        
        layout_derecho.addWidget(group_cliente)
        
        group_carrito = QGroupBox("🛒 Carrito de Compra")
        group_carrito.setProperty("class", "venta-group")
        group_carrito.setMinimumHeight(200)
        carrito_layout = QVBoxLayout(group_carrito)
        carrito_layout.setContentsMargins(5, 5, 5, 5)

        self.tabla_compra = QTableWidget()
        self.tabla_compra.setProperty("class", "tabla-carrito")
        self.tabla_compra.setColumnCount(7)
        self.tabla_compra.setHorizontalHeaderLabels(
            ["Producto", "Cant.", "Precio", "Desc%", "Total", "", ""])
        self.tabla_compra.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_compra.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_compra.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.tabla_compra.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tabla_compra.verticalHeader().setDefaultSectionSize(34)
        self.tabla_compra.verticalHeader().setVisible(False)
        self.tabla_compra.setColumnWidth(0, 140)
        self.tabla_compra.setColumnWidth(1, 45) 
        self.tabla_compra.setColumnWidth(2, 55) 
        self.tabla_compra.setColumnWidth(3, 45)
        self.tabla_compra.setColumnWidth(4, 60) 
        self.tabla_compra.setColumnWidth(5, 28)
        self.tabla_compra.setColumnWidth(6, 28) 
        self.tabla_compra.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        carrito_layout.addWidget(self.tabla_compra)
        
        self.lbl_info_carrito = QLabel("")
        self.lbl_info_carrito.setAlignment(Qt.AlignCenter)
        self.lbl_info_carrito.setProperty("class", "info-label")
        carrito_layout.addWidget(self.lbl_info_carrito)
        
        layout_derecho.addWidget(group_carrito, 1)
    
        group_info_venta = QGroupBox("📊 Resumen")
        group_info_venta.setMaximumHeight(120)
        group_info_venta.setProperty("class", "venta-group")
        info_venta_layout = QGridLayout(group_info_venta)
        info_venta_layout.setContentsMargins(8, 8, 8, 8)
        
        self.lbl_peso_bascula = QLabel("Peso: 0.000 kg")
        self.lbl_total = QLabel("TOTAL: $0.00")
        self.lbl_puntos_venta = QLabel("Puntos: 0")
        
        self.lbl_peso_bascula.setProperty("class", "info-box")
        self.lbl_total.setProperty("class", "total-box")
        self.lbl_puntos_venta.setProperty("class", "info-box")
        
        self.lbl_peso_bascula.setAlignment(Qt.AlignCenter)
        self.lbl_total.setAlignment(Qt.AlignCenter)
        self.lbl_puntos_venta.setAlignment(Qt.AlignCenter)
        
        info_venta_layout.addWidget(self.lbl_peso_bascula, 0, 0)
        info_venta_layout.addWidget(self.lbl_total, 0, 1)
        info_venta_layout.addWidget(self.lbl_puntos_venta, 1, 0, 1, 2)

        # Widget de comisión del turno (configurable: se muestra si está habilitado)
        self.lbl_comision_turno = QLabel("💰 Comisión turno: $0.00")
        self.lbl_comision_turno.setAlignment(Qt.AlignCenter)
        self.lbl_comision_turno.setProperty("class", "badge-success")
        self.lbl_comision_turno.setStyleSheet(
            "font-weight:bold;font-size:13px;padding:6px;border-radius:4px;"
        )
        self.lbl_comision_turno.setVisible(False)   # se activa si tiene config
        info_venta_layout.addWidget(self.lbl_comision_turno, 2, 0, 1, 2)
        
        layout_derecho.addWidget(group_info_venta)

        group_acciones = QGroupBox("⚡ Acciones")
        group_acciones.setMaximumHeight(165)
        group_acciones.setProperty("class", "venta-group")
        acciones_layout = QGridLayout(group_acciones)
        acciones_layout.setContentsMargins(8, 8, 8, 8)
        acciones_layout.setVerticalSpacing(4)
        
        # ── Descuentos rápidos ───────────────────────────────────────────
        grp_desc = QGroupBox("⚡ Descuento rápido")
        grp_desc.setMaximumHeight(55)
        desc_lay = QHBoxLayout(grp_desc)
        desc_lay.setContentsMargins(6, 4, 6, 4)
        for pct in [5, 10, 15, 20]:
            btn_d = QPushButton(f"{pct}%")
            btn_d.setToolTip(f"Aplicar {pct}% de descuento al ítem seleccionado")
            btn_d.setStyleSheet("padding:3px 6px;font-size:11px;")
            btn_d.clicked.connect(lambda _, p=pct: self._descuento_rapido(p))
            desc_lay.addWidget(btn_d)
        btn_custom = QPushButton("Custom")
        btn_custom.setToolTip("Descuento personalizado")
        btn_custom.setProperty("class", "btn-accent")
        btn_custom.setStyleSheet("padding:3px 6px;font-size:11px;")
        btn_custom.clicked.connect(lambda: self._descuento_custom())
        desc_lay.addWidget(btn_custom)
        layout_derecho.addWidget(grp_desc)

        self.btn_factura = QPushButton("🧾 Factura")
        self.btn_factura.setToolTip("Generar CFDI de la última venta")
        self.btn_factura.setProperty("class", "btn-dark")
        self.btn_factura.setStyleSheet("padding:6px 10px;border-radius:4px;")
        self.btn_factura.setEnabled(False)
        self.btn_factura.clicked.connect(self._generar_factura)
        layout_derecho.addWidget(self.btn_factura)

        self.btn_reimprimir = QPushButton("🖨️ Reimprimir")
        self.btn_reimprimir.setToolTip("Reimprimir el ticket de la última venta")
        self.btn_reimprimir.setProperty("class", "btn-secondary")
        self.btn_reimprimir.setStyleSheet("padding:6px 10px;border-radius:4px;")
        self.btn_reimprimir.setEnabled(False)
        self.btn_reimprimir.clicked.connect(self._reimprimir_ultima_venta)
        layout_derecho.addWidget(self.btn_reimprimir)

        self._banner_sin_impresora = QLabel(
            "⚠️  Sin impresora configurada — los tickets se guardarán en PDF (carpeta TICKETS/)")
        self._banner_sin_impresora.setProperty("class", "banner-warning")
        self._banner_sin_impresora.setStyleSheet(
            "padding:5px 10px;border-radius:4px;font-size:11px;")
        self._banner_sin_impresora.setWordWrap(True)
        self._banner_sin_impresora.setVisible(False)
        layout_derecho.addWidget(self._banner_sin_impresora)

        self.btn_cobrar = QPushButton("💰 Cobrar")
        self.btn_suspender = QPushButton("⏸️ Suspender")
        self.btn_reanudar = QPushButton("▶️ Reanudar (0)")
        self.btn_cancelar = QPushButton("❌ Cancelar")
        
        button_height = 38
        self.btn_cobrar.setFixedHeight(button_height)
        self.btn_suspender.setFixedHeight(button_height)
        self.btn_reanudar.setFixedHeight(button_height)
        self.btn_cancelar.setFixedHeight(button_height)
        
        self.btn_cobrar.setProperty("class", "venta-button")
        self.btn_cancelar.setProperty("class", "venta-button")
        self.btn_suspender.setProperty("class", "venta-button")
        self.btn_reanudar.setProperty("class", "venta-button")

        self.btn_devolucion = QPushButton("↩ Devolución")
        self.btn_devolucion.setFixedHeight(button_height)
        self.btn_devolucion.setProperty("class", "venta-button")
        self.btn_devolucion.setToolTip(
            "Cancelar o devolver una venta anterior (requiere permiso)")
        self.btn_devolucion.setEnabled(False)   # se activa tras login con permiso

        acciones_layout.addWidget(self.btn_cobrar, 0, 0, 1, 2)
        acciones_layout.addWidget(self.btn_suspender, 1, 0)
        acciones_layout.addWidget(self.btn_reanudar, 1, 1)
        acciones_layout.addWidget(self.btn_cancelar, 2, 0)
        acciones_layout.addWidget(self.btn_devolucion, 2, 1)
        
        layout_derecho.addWidget(group_acciones)
        
        splitter.addWidget(panel_izquierdo)
        splitter.addWidget(panel_derecho)
        splitter.setSizes([600, 500])
        main_layout.addWidget(splitter)

    def limpiar_busqueda_productos(self):
        self.txt_busqueda.clear()
        self.cargar_productos_interactivos()

    def buscar_productos_en_tiempo_real(self, texto: str):
        if len(texto.strip()) >= 2:
            self.cargar_productos_interactivos(texto.strip())

    def cargar_productos_interactivos(self, filtro: str = ""):
        for i in reversed(range(self.grid_productos.count())):
            widget = self.grid_productos.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        
        try:
            cursor = self.conexion.cursor()
            # v13.4: Leer stock de branch_inventory para la sucursal activa
            # COALESCE: branch_inventory.quantity → productos.existencia → 0
            query = """
                SELECT p.id, p.nombre, p.precio,
                       COALESCE(bi.quantity, p.existencia, 0) as stock_sucursal,
                       p.unidad, p.categoria,
                       p.stock_minimo, p.imagen_path, p.es_compuesto, p.es_subproducto,
                       COALESCE(p.codigo_barras,'') as codigo_barras
                FROM productos p
                LEFT JOIN branch_inventory bi ON bi.product_id=p.id AND bi.branch_id=?
                WHERE p.oculto = 0 AND COALESCE(p.activo,1) = 1
            """
            params = [self.sucursal_id]
            if filtro:
                query += " AND (p.nombre LIKE ? OR p.id = ? OR p.categoria LIKE ? OR COALESCE(p.codigo_barras,'') = ?)"
                params += [f'%{filtro}%', filtro, f'%{filtro}%', filtro]
            
            query += " ORDER BY p.nombre"
            cursor.execute(query, params)
            productos = cursor.fetchall()
            
            col_count = 3
            for i, producto in enumerate(productos):
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
                    'codigo_barras': producto[10]
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
            self.iniciar_monitoreo_peso(producto)
        else:
            self.agregar_producto_por_unidad(producto)

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
                            row_pts = self.conexion.execute(
                                "SELECT COALESCE(puntos,0), COALESCE(nivel,'Bronce') "
                                "FROM clientes WHERE id=?",
                                (qr_result.client_id,)).fetchone()
                            if row_pts:
                                puntos = int(row_pts[0])
                                nivel = row_pts[1]
                        except Exception:
                            pass
                        self._cargar_cliente_en_venta(
                            cliente_id=qr_result.client_id,
                            nombre=qr_result.nombre,
                            telefono="",
                            puntos=puntos,
                            nivel=nivel)
                        return

                    if qr_result.tipo == QRType.TARJETA and qr_result.valid:
                        self._cargar_cliente_en_venta(
                            cliente_id=qr_result.client_id,
                            nombre=qr_result.nombre,
                            puntos=0, nivel="Bronce")
                        return

                # Fallback: búsqueda tradicional
                # 1a. Buscar tarjeta de fidelidad
                row_tarj = self.conexion.execute(
                    """SELECT t.id, t.codigo, COALESCE(t.nivel,'Bronce') as nivel,
                              c.id as cliente_id, c.nombre as cliente_nombre,
                              c.telefono, COALESCE(c.puntos,0) as puntos
                       FROM tarjetas_fidelidad t
                       JOIN clientes c ON c.id = t.id_cliente
                       WHERE t.codigo = ? AND t.activa = 1
                       LIMIT 1""",
                    (codigo,)
                ).fetchone()
                if row_tarj:
                    self._cargar_cliente_en_venta(
                        cliente_id=row_tarj['cliente_id'],
                        nombre=row_tarj['cliente_nombre'],
                        telefono=row_tarj['telefono'] or "",
                        puntos=int(row_tarj['puntos']),
                        nivel=row_tarj['nivel'],
                    )
                    return

                # 1b. Buscar cliente por ID o teléfono (NO por nombre LIKE)
                row_cli = self.conexion.execute(
                    """SELECT id, nombre, COALESCE(telefono,'') as telefono,
                              COALESCE(puntos,0) as puntos,
                              COALESCE(nivel,'Bronce') as nivel
                       FROM clientes
                       WHERE CAST(id AS TEXT)=? OR telefono=? OR codigo_qr=?
                       LIMIT 1""",
                    (codigo, codigo, codigo)
                ).fetchone()
                if row_cli:
                    self._cargar_cliente_en_venta(
                        cliente_id=row_cli['id'],
                        nombre=row_cli['nombre'],
                        telefono=row_cli['telefono'],
                        puntos=int(row_cli['puntos']),
                        nivel=row_cli['nivel'],
                    )
                    return

                # 1c. No encontrado → poner en txt_cliente para búsqueda manual
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
                row_prod = self.conexion.execute(
                    """SELECT id, nombre, precio_venta, precio_kilo,
                              existencia, unidad, tipo, imagen_path,
                              categoria, descripcion,
                              COALESCE(codigo_barras,'') as codigo_barras
                       FROM productos
                       WHERE (COALESCE(codigo_barras,'')=? OR codigo=? OR CAST(id AS TEXT)=?)
                         AND COALESCE(activo,1)=1 AND COALESCE(oculto,0)=0
                       LIMIT 1""",
                    (codigo, codigo, codigo)
                ).fetchone()
                if row_prod:
                    self.agregar_al_carrito(dict(row_prod))
                    self._mostrar_notif_scanner(
                        f"📦 {row_prod['nombre']}", "product")
                    if hasattr(self, 'txt_busqueda'):
                        self.txt_busqueda.clear()
                    return
                # Not found → populate search field
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
            row_prod = self.conexion.execute(
                """SELECT id, nombre, precio_venta, precio_kilo,
                          existencia, unidad, tipo, imagen_path,
                          categoria, descripcion,
                          COALESCE(codigo_barras,'') as codigo_barras
                   FROM productos
                   WHERE (COALESCE(codigo_barras,'')=? OR codigo=? OR CAST(id AS TEXT)=?)
                     AND COALESCE(activo,1)=1 AND COALESCE(oculto,0)=0
                   LIMIT 1""",
                (codigo, codigo, codigo)
            ).fetchone()
            if row_prod:
                self.agregar_al_carrito(dict(row_prod))
                self._mostrar_notif_scanner(f"📦 {row_prod['nombre']}", "product")
                return

            # ── 2. Tarjeta de fidelidad ──────────────────────────────────────
            row_tarj = self.conexion.execute(
                """SELECT t.id, t.codigo, COALESCE(t.nivel,'Bronce') as nivel,
                          c.id as cliente_id, c.nombre as cliente_nombre,
                          c.telefono, COALESCE(c.puntos,0) as puntos
                   FROM tarjetas_fidelidad t
                   JOIN clientes c ON c.id = t.id_cliente
                   WHERE t.codigo = ? AND t.activa = 1
                   LIMIT 1""",
                (codigo,)
            ).fetchone()
            if row_tarj:
                self._cargar_cliente_en_venta(
                    cliente_id=row_tarj['cliente_id'],
                    nombre=row_tarj['cliente_nombre'],
                    telefono=row_tarj['telefono'] or "",
                    puntos=int(row_tarj['puntos']),
                    nivel=row_tarj['nivel'],
                )
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
                        return
                except Exception:
                    pass

            # ── 4. Sin coincidencia ──────────────────────────────────────────
            if hasattr(self, 'txt_busqueda'):
                self.txt_busqueda.setText(codigo)
                self.buscar_productos()
            self._mostrar_notif_scanner(f"🔍 Buscando: {codigo}", "search")

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("_procesar_scanner_con_codigo: %s", e)

        try:
            # ── 1. Intentar como producto (barcode o código interno) ─────────
            row_prod = self.conexion.execute(
                """SELECT id, nombre, precio_venta, precio_kilo,
                          existencia, unidad, tipo,
                          imagen_path, categoria, descripcion,
                          COALESCE(codigo_barras,'') as codigo_barras
                   FROM productos
                   WHERE (COALESCE(codigo_barras,'') = ? OR codigo = ? OR CAST(id AS TEXT)=?)
                     AND COALESCE(activo,1)=1 AND COALESCE(oculto,0)=0
                   LIMIT 1""",
                (codigo, codigo, codigo)
            ).fetchone()

            if row_prod:
                prod_data = {
                    'id':          row_prod['id'],
                    'nombre':      row_prod['nombre'],
                    'precio':      row_prod['precio_venta'],
                    'precio_kilo': row_prod['precio_kilo'],
                    'existencia':  row_prod['existencia'],
                    'unidad':      row_prod['unidad'],
                    'tipo':        row_prod['tipo'],
                    'imagen_path': row_prod['imagen_path'],
                    'categoria':   row_prod['categoria'],
                    'descripcion': row_prod['descripcion'],
                    'codigo_barras': row_prod['codigo_barras'],
                }
                self.agregar_al_carrito(prod_data)
                self._mostrar_notif_scanner(f"📦 {prod_data['nombre']}", "product")
                return

            # ── 2. Intentar como tarjeta de fidelidad ───────────────────────
            row_tarj = self.conexion.execute(
                """SELECT t.id, t.codigo, t.nivel,
                          c.id as cliente_id, c.nombre as cliente_nombre,
                          c.telefono, COALESCE(c.puntos,0) as puntos
                   FROM tarjetas_fidelidad t
                   JOIN clientes c ON c.id = t.id_cliente
                   WHERE t.codigo = ? AND t.activa = 1
                   LIMIT 1""",
                (codigo,)
            ).fetchone()

            if row_tarj:
                # Load client into current sale
                if hasattr(self, 'set_cliente_venta'):
                    self.set_cliente_venta(
                        cliente_id=row_tarj['cliente_id'],
                        nombre=row_tarj['cliente_nombre'],
                        telefono=row_tarj['telefono'] or "",
                    )
                nivel_icons = {"Bronce":"🥉","Plata":"🥈","Oro":"🥇","Diamante":"💎"}
                nivel = row_tarj['nivel'] or "Bronce"
                icon  = nivel_icons.get(nivel, "⭐")
                self._mostrar_notif_scanner(
                    f"{icon} Tarjeta {nivel}: {row_tarj['cliente_nombre']} — {int(row_tarj['puntos'])} pts",
                    "card"
                )
                return

            # ── 3. Intentar como QR de contenedor (UUID format) ─────────────
            import re as _re
            if _re.match(
                r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$',
                codigo
            ):
                try:
                    row_cont = self.conexion.execute(
                        "SELECT uuid_qr, descripcion, sucursal_id FROM trazabilidad_qr WHERE uuid_qr=? LIMIT 1",
                        (codigo,)
                    ).fetchone()
                    if row_cont:
                        self._mostrar_notif_scanner(
                            f"📦 Contenedor: {row_cont['descripcion'] or codigo[:8]}...",
                            "container"
                        )
                        return
                except Exception:
                    pass

            # ── 4. No encontrado → poner en buscador para búsqueda manual ───
            if hasattr(self, 'txt_busqueda'):
                self.txt_busqueda.setText(codigo)
                self.buscar_productos()
            self._mostrar_notif_scanner(f"🔍 Buscando: {codigo}", "search")

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("_procesar_buffer_scanner: %s", e)

    def _set_scan_context(self, context: str, active_field) -> None:
        """
        Cambia el contexto del scanner y actualiza el estilo visual de los campos.
        
        context: "producto" | "cliente" | "auto"
        active_field: el QLineEdit activo, o None para limpiar estilos
        """
        self._scan_context = context

        # Reset styles — v13.4: sin colores de fondo hardcoded (compat dark mode)
        base_product = ("QLineEdit { padding:6px 8px; border:2px solid gray;"
                        " border-radius:4px; font-size:13px; }")
        active_product = ("QLineEdit { padding:6px 8px; border:2px solid var(--success);"
                          " border-radius:4px; font-size:13px; }"
                          "QLineEdit:focus { border-color: var(--success); }")
        active_client  = ("QLineEdit { padding:6px 8px; border:2px solid var(--primary);"
                          " border-radius:4px; font-size:13px; }"
                          "QLineEdit:focus { border-color: var(--primary); }")

        for field in (getattr(self,'txt_busqueda',None), getattr(self,'txt_cliente',None)):
            if field is None: continue
            if field is active_field:
                if context == "producto":
                    field.setStyleSheet(active_product)
                    field.setPlaceholderText("🟢 SCANNER ACTIVO — Escanear producto...")
                elif context == "cliente":
                    field.setStyleSheet(active_client)
                    field.setPlaceholderText("🔵 SCANNER ACTIVO — Escanear tarjeta o cliente...")
            else:
                field.setStyleSheet(base_product)
                # Restore original placeholder
                if field is getattr(self, 'txt_busqueda', None):
                    field.setPlaceholderText("🔍 Escanear o escribir producto...")
                elif field is getattr(self, 'txt_cliente', None):
                    field.setPlaceholderText("💳 Escanear tarjeta o buscar cliente...")

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
                self.lbl_scanner_notif.setProperty("class", clase)
                self.lbl_scanner_notif.setStyleSheet(
                    "padding:6px 12px;border-radius:4px;font-weight:bold;font-size:12px;")
                self.lbl_scanner_notif.show()
                # Auto-hide after 3s
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(3000, lambda: (
                    self.lbl_scanner_notif.hide()
                    if hasattr(self, 'lbl_scanner_notif') else None))
        except Exception:
            pass

    
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
                QMessageBox.information(
                    self, "💳 Tarjeta cargada",
                    f"Cliente: {cliente_nombre}\n"
                    f"Tarjeta: {numero}\n"
                    f"Puntos acumulados: {puntos}"
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
                row = self.conexion.execute(
                    "SELECT id, nombre, telefono, email, direccion, rfc, puntos, codigo_qr, saldo "
                    "FROM clientes WHERE id = ? AND activo = 1",
                    (tarjeta.id_cliente,)
                ).fetchone()
                if row:
                    self.cliente_actual = {
                        'id': row[0], 'nombre': row[1], 'telefono': row[2],
                        'email': row[3], 'direccion': row[4], 'rfc': row[5],
                        'puntos': row[6], 'codigo_qr': row[7], 'saldo': row[8] or 0.0,
                    }
                    self._actualizar_ui_cliente()
                    if hasattr(self, 'lbl_puntos_cliente'):
                        self.lbl_puntos_cliente.setText(f"Puntos: {row[6]} | Nivel: {tarjeta.nivel}")
                    return

            dialogo = _DialogoAsignarTarjeta(tarjeta, self.conexion, self)
            if dialogo.exec_() == QDialog.Accepted:
                resultado = dialogo.resultado
                if resultado and resultado.get('cliente_id'):
                    cliente_id = resultado['cliente_id']
                    eng.asignar_tarjeta(tarjeta.id, cliente_id, motivo="asignacion_en_venta")
                    row = self.conexion.execute(
                        "SELECT id, nombre, telefono, email, direccion, rfc, puntos, codigo_qr, saldo "
                        "FROM clientes WHERE id = ?",
                        (cliente_id,)
                    ).fetchone()
                    if row:
                        self.cliente_actual = {
                            'id': row[0], 'nombre': row[1], 'telefono': row[2],
                            'email': row[3], 'direccion': row[4], 'rfc': row[5],
                            'puntos': row[6], 'codigo_qr': row[7], 'saldo': row[8] or 0.0,
                        }
                        self._actualizar_ui_cliente()
        except ImportError:
            QMessageBox.information(self, "Tarjeta", "Motor de tarjetas no disponible en esta versión.")
        except Exception as exc:
            QMessageBox.critical(self, "Error Tarjeta", str(exc))

    def _actualizar_ui_cliente(self) -> None:
        if not self.cliente_actual: return
        nombre = self.cliente_actual.get('nombre', '')
        if hasattr(self, 'txt_cliente'): self.txt_cliente.setText(nombre)
        if hasattr(self, 'lbl_nombre_cliente'): self.lbl_nombre_cliente.setText(nombre)
        if hasattr(self, 'lbl_puntos_cliente'):
            puntos = self.cliente_actual.get('puntos', 0)
            self.lbl_puntos_cliente.setText(f"Puntos: {puntos}")

    def _descuento_rapido(self, pct: float) -> None:
        """Aplica descuento % al ítem — validado por DiscountGuard financiero."""
        row = self.tabla_compra.currentRow() if hasattr(self, 'tabla_compra') else -1
        if row < 0:
            if self.compra_actual:
                row = len(self.compra_actual) - 1
            else:
                QMessageBox.information(self, "Aviso",
                    "Selecciona un ítem del carrito primero.")
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
                # Solicitar PIN de gerente
                pin, ok = __import__('PyQt5.QtWidgets', fromlist=['QInputDialog']).QInputDialog.getText(
                    self, "Autorización Requerida",
                    "PIN de gerente requerido\n\n" + mensaje + "\n\nIngresa PIN:",
                    __import__('PyQt5.QtWidgets', fromlist=['QLineEdit']).QLineEdit.Password
                )
                if not ok:
                    return
                if not guard.solicitar_pin_gerente(self.conexion, pin):
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
            QMessageBox.information(self, "Aviso", "Selecciona un ítem primero.")
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
                return
            usuario = self.obtener_usuario_actual()
            cfg = cs.get_config(usuario)
            if not cfg or not cfg.get('activo'):
                self.lbl_comision_turno.setVisible(False)
                return
            datos = cs.get_comision_turno(usuario)
            monto  = float(datos.get('comision', 0))
            ventas = int(datos.get('ventas', 0))
            self.lbl_comision_turno.setText(
                f"💰 Comisión turno: ${monto:.2f}  ({ventas} vtas)")
            self.lbl_comision_turno.setVisible(True)
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
        2. QPrintDialog (sistema) como fallback si no hay impresora configurada
        3. PDF de auditoría siempre
        """
        from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
        from PyQt5.QtGui import QTextDocument

        impreso = False

        # ── Ruta 1: PrinterService unificado (ESC/POS) ────────────────────────
        printer_svc = getattr(self.container, 'printer_service', None)
        if printer_svc and printer_svc.has_ticket_printer():
            try:
                job_id = printer_svc.print_ticket(datos_ticket)
                if job_id:
                    impreso = True
                    self.guardar_ticket_pdf(datos_ticket)
                    return
            except Exception as _e:
                logger.warning("PrinterService: %s", _e)

        # ── Ruta 3: Impresora del sistema (QPrintDialog) ──────────────────────
        # v13.4: QTextDocument con soporte para imágenes base64
        try:
            html = self.generar_html_ticket(datos_ticket)

            doc = QTextDocument()

            # v13.4: Registrar imágenes base64 como recursos del documento
            # QTextDocument no entiende data:image/...;base64,... directamente
            import re, base64
            img_counter = 0
            def _register_b64_image(match):
                nonlocal img_counter
                b64_full = match.group(1)  # "data:image/png;base64,XXXX"
                try:
                    if ',' in b64_full:
                        b64_data = b64_full.split(',', 1)[1]
                    else:
                        b64_data = b64_full
                    img_bytes = base64.b64decode(b64_data)
                    qimg = QImage()
                    qimg.loadFromData(img_bytes)
                    if not qimg.isNull():
                        img_counter += 1
                        res_name = f"ticket_img_{img_counter}"
                        doc.addResource(
                            QTextDocument.ImageResource,
                            __import__('PyQt5.QtCore', fromlist=['QUrl']).QUrl(res_name),
                            qimg)
                        return f'src="{res_name}"'
                except Exception:
                    pass
                return match.group(0)

            html = re.sub(r'src="(data:image/[^"]+)"', _register_b64_image, html)
            doc.setHtml(html)

            # Leer config de papel
            paper_w = 80; paper_h = 297; margin_top = 5; margin_side = 3
            try:
                db = self.container.db
                def _pcfg(k, d=""):
                    r = db.execute("SELECT valor FROM configuraciones WHERE clave=?", (k,)).fetchone()
                    return r[0] if r and r[0] else d
                try: paper_w = int(_pcfg('ticket_paper_width', '80'))
                except: pass
                try: paper_h = int(_pcfg('ticket_paper_height', '0')) or 297
                except: pass
                try: margin_top = int(_pcfg('ticket_margin_top', '5'))
                except: pass
                try: margin_side = int(_pcfg('ticket_margin_side', '3'))
                except: pass
            except Exception:
                pass

            from PyQt5.QtPrintSupport import QPrinterInfo
            from PyQt5.QtCore import QSizeF
            default_printer = QPrinterInfo.defaultPrinter()

            if default_printer and not default_printer.isNull():
                printer = QPrinter(default_printer, QPrinter.HighResolution)
                printer.setPageSize(QPrinter.Custom)
                printer.setPageSizeMM(QSizeF(paper_w, paper_h))
                printer.setPageMargins(margin_side, margin_top, margin_side, margin_top, QPrinter.Millimeter)
                doc.print_(printer)
                impreso = True
                logger.info("Ticket impreso: %s (%dx%dmm)",
                            default_printer.printerName(), paper_w, paper_h)
            else:
                printer = QPrinter(QPrinter.HighResolution)
                dlg = QPrintDialog(printer, self)
                dlg.setWindowTitle("Imprimir Ticket")
                if dlg.exec_() == QPrintDialog.Accepted:
                    printer.setPageSize(QPrinter.Custom)
                    printer.setPageSizeMM(QSizeF(paper_w, paper_h))
                    printer.setPageMargins(margin_side, margin_top, margin_side, margin_top, QPrinter.Millimeter)
                    doc.print_(printer)
                    impreso = True
        except Exception as _e:
            logger.debug("QPrintDialog ticket: %s", _e)

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
                self.lbl_estado_bascula.setText("Báscula: ⚪ Desactivada")
            if hasattr(self, 'lbl_peso_bascula'):
                self.lbl_peso_bascula.setText("Peso: —")
            return
        self.lbl_estado_bascula.setText("Báscula: ⏳ Conectando...")
        self.lbl_peso_bascula.setText("Peso: 0.000 kg")
        self.timer_bascula.start()
        
    def leer_peso(self):
        """🛠️ FIX ENTERPRISE: Usa el Hardware Service centralizado."""
        try:
            if hasattr(self.container, 'hardware_service'):
                peso = self.container.hardware_service.read_scale()
                if peso > 0:
                    self.peso_actual = peso
                    self.lbl_peso_bascula.setText(f"Peso: {peso:.3f} kg")
                    self.lbl_estado_bascula.setText("Báscula: ✅ Conectada (HAL)")
                    if self.producto_pendiente:
                        self.procesar_peso_para_producto(peso)
                return
        except Exception:
            pass

        # Legacy Fallback — solo si báscula está habilitada en config hardware
        if not self._hw_bascula_habilitada:
            return
        try:
            if not self.bascula:
                puerto = self._hw_bascula_cfg.get("puerto", "COM3")
                baud   = int(self._hw_bascula_cfg.get("baud", 9600))
                self.bascula = serial.Serial(puerto, baud, timeout=0.2)
                self.lbl_estado_bascula.setText("Báscula: ✅ Conectada")

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
            self.lbl_estado_bascula.setText("Báscula: ❌ Desconectada")
                
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
        if cantidad <= 0:
            QMessageBox.warning(self, "Advertencia", "La cantidad debe ser mayor a cero.")
            self.limpiar_seleccion_producto()
            return
            
        if cantidad > producto['existencia']:
            QMessageBox.warning(self, "Stock Insuficiente",
                f"Stock insuficiente. Disponible: {producto['existencia']:.2f} {producto['unidad']}")
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
                                    f"Stock insuficiente. Disponible: {producto['existencia']:.2f} {producto['unidad']}"
                                )
                                break
                                
                            item['cantidad'] = nueva_cantidad
                            item['total'] = round(nueva_cantidad * item['precio_unitario'], 2)
                            self.actualizar_tabla_compra()
                            self.mostrar_mensaje("Éxito", f"Cantidad actualizada: {nueva_cantidad:.3f} {producto['unidad']}")
                            break
                else:
                    total_item = round(cantidad * producto['precio'], 2)
                    item_compra = {
                        'id': producto['id'],
                        'nombre': f"{producto['nombre']} (adicional)",
                        'cantidad': cantidad,
                        'unidad': producto['unidad'],
                        'precio_unitario': producto['precio'],
                        'total': total_item
                    }
                # Verificar stock antes de agregar al carrito
                # v13.4: Lee stock de branch_inventory para la sucursal activa
                try:
                    stock_row = self.container.db.execute(
                        "SELECT COALESCE(bi.quantity, p.existencia, 0) "
                        "FROM productos p "
                        "LEFT JOIN branch_inventory bi ON bi.product_id=p.id AND bi.branch_id=? "
                        "WHERE p.id=?",
                        (self.sucursal_id, producto['id'])
                    ).fetchone()
                    stock_actual = float(stock_row[0]) if stock_row and stock_row[0] else 0
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
        item_compra = {
            'id': producto['id'],
            'nombre': producto['nombre'],
            'cantidad': cantidad,
            'unidad': producto['unidad'],
            'precio_unitario': producto['precio'],
            'total': total_item
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
        self.tabla_compra.setRowCount(len(self.compra_actual))
        
        for row, item in enumerate(self.compra_actual): 
            self.tabla_compra.setItem(row, 0, QTableWidgetItem(item['nombre']))
            
            cantidad_item = QTableWidgetItem(f"{item['cantidad']:.3f}")
            cantidad_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabla_compra.setItem(row, 1, cantidad_item)
            
            precio_item = QTableWidgetItem(f"${item['precio_unitario']:.2f}")
            precio_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabla_compra.setItem(row, 2, precio_item)

            # v13.4: Columna de descuento con click para quitar
            desc_pct = float(item.get('descuento_pct', 0))
            if desc_pct > 0:
                btn_desc = QPushButton(f"-{desc_pct:.0f}%")
                btn_desc.setToolTip("Click para quitar descuento")
                btn_desc.setProperty("class", "btn-item-discount")
                btn_desc.setStyleSheet(
                    "padding:1px 3px;border-radius:3px;font-size:10px;")
                btn_desc.clicked.connect(
                    lambda _, r=row: self._quitar_descuento_item(r))
                self.tabla_compra.setCellWidget(row, 3, btn_desc)
            else:
                self.tabla_compra.setItem(row, 3, QTableWidgetItem(""))
            
            total_item = QTableWidgetItem(f"${item['total']:.2f}")
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabla_compra.setItem(row, 4, total_item)
            
            btn_modificar = QPushButton("✏️")
            btn_modificar.setToolTip("Modificar cantidad")
            btn_modificar.setFixedSize(26, 26)
            btn_modificar.clicked.connect(lambda checked, r=row: self.modificar_cantidad_producto(r))
            self.tabla_compra.setCellWidget(row, 5, btn_modificar)
            
            btn_eliminar = QPushButton("❌")
            btn_eliminar.setToolTip("Eliminar producto")
            btn_eliminar.setFixedSize(26, 26)
            btn_eliminar.clicked.connect(lambda checked, r=row: self.eliminar_producto_carrito(r))
            self.tabla_compra.setCellWidget(row, 6, btn_eliminar)
            
        self.calcular_totales()
        n = len(self.compra_actual)
        self.lbl_info_carrito.setText(f"{n} producto{'s' if n != 1 else ''}" if n else "")

    def _quitar_descuento_item(self, row: int):
        """v13.4: Quita el descuento de un item del carrito."""
        if 0 <= row < len(self.compra_actual):
            item = self.compra_actual[row]
            item['descuento_pct'] = 0
            item['total'] = round(item['cantidad'] * item['precio_unitario'], 2)
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
        """v13.4: Lee stock de branch_inventory para la sucursal activa."""
        try:
            cursor = self.conexion.cursor()
            cursor.execute(
                "SELECT COALESCE(bi.quantity, p.existencia, 0) "
                "FROM productos p "
                "LEFT JOIN branch_inventory bi ON bi.product_id=p.id AND bi.branch_id=? "
                "WHERE p.id=?",
                (self.sucursal_id, producto_id))
            resultado = cursor.fetchone()
            return float(resultado[0]) if resultado else 0.0
        except Exception:
            return 0.0

    def eliminar_producto_carrito(self, row: int):
        if 0 <= row < len(self.compra_actual):
            producto = self.compra_actual[row]['nombre']
            self.compra_actual.pop(row)
            self.actualizar_tabla_compra()
            self.mostrar_mensaje("Éxito", f"Producto '{producto}' eliminado del carrito.")

    def calcular_totales(self):
        subtotal = sum(item['total'] for item in self.compra_actual)
        # IVA: carnes y alimentos basicos = 0% en Mexico (LIVA Art. 2-A)
        # Se lee de configuraciones; default 0.0
        try:
            _iva_row = self.container.db.execute(
                "SELECT valor FROM configuraciones WHERE clave='tasa_iva'"
            ).fetchone()
            tasa_iva = float(_iva_row[0]) if _iva_row else 0.0
        except Exception:
            tasa_iva = 0.0
        impuestos = subtotal * tasa_iva
        total_final = subtotal + impuestos
        
        self.totales = {
            'subtotal': subtotal,
            'impuestos': impuestos,
            'total_final': total_final
        }
        
        self.lbl_total.setText(f"TOTAL: ${total_final:.2f}")
        puntos_venta = int(total_final)
        self.lbl_puntos_venta.setText(f"Puntos: {puntos_venta}")

    def buscar_cliente(self):
        termino = self.txt_cliente.text().strip()
        if not termino:
            self.limpiar_cliente()
            return
            
        try:
            cursor = self.conexion.cursor()
            query = """
                SELECT id, nombre, telefono, email, direccion, rfc, puntos, codigo_qr, saldo
                FROM clientes 
                WHERE (id = ? OR nombre LIKE ? OR telefono LIKE ? OR codigo_qr = ? OR email LIKE ?)
                AND activo = 1 LIMIT 1
            """
            cursor.execute(query, (termino, f'%{termino}%', f'%{termino}%', termino, f'%{termino}%'))
            cliente = cursor.fetchone()
            
            if cliente:
                self.cliente_actual = {
                    'id': cliente[0], 'nombre': cliente[1], 'telefono': cliente[2],
                    'email': cliente[3], 'direccion': cliente[4], 'rfc': cliente[5],
                    'puntos': cliente[6], 'codigo_qr': cliente[7], 'saldo': cliente[8]
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
            self.lbl_nombre_cliente.setText(f"Nombre: {self.cliente_actual['nombre']}")
            self.lbl_telefono_cliente.setText(f"Teléfono: {self.cliente_actual['telefono'] or '-'}")
            self.lbl_email_cliente.setText(f"Email: {self.cliente_actual['email'] or '-'}")
            self.lbl_puntos_cliente.setText(f"Puntos: {self.cliente_actual['puntos']}")
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
            cursor = self.conexion.cursor()
            tarjeta_id = cliente_data.get('tarjeta_id', '')
            
            # v13.4: Si se proporcionó un ID de tarjeta, verificar si el cliente ya existe
            if tarjeta_id:
                # Buscar si la tarjeta ya está asignada a un cliente
                existing = cursor.execute(
                    "SELECT c.id, c.nombre FROM clientes c "
                    "JOIN tarjetas_fidelidad t ON t.id_cliente = c.id "
                    "WHERE t.codigo = ? AND t.activa = 1 LIMIT 1",
                    (tarjeta_id,)).fetchone()
                if existing:
                    # Tarjeta ya asignada — cargar ese cliente
                    self.seleccionar_cliente(existing[0] if not hasattr(existing, 'keys') else existing['id'])
                    self.mostrar_mensaje("Info", f"Tarjeta ya asignada a: {existing[1] if not hasattr(existing, 'keys') else existing['nombre']}")
                    return
            
            codigo_qr = tarjeta_id or (
                f"CLI_{datetime.now().strftime('%Y%m%d%H%M%S')}" if cliente_data['generar_tarjeta'] else None)
            
            cursor.execute("""
                INSERT INTO clientes (nombre, telefono, email, direccion, puntos, codigo_qr, activo)
                VALUES (?, ?, ?, ?, 0, ?, 1)
            """, (cliente_data['nombre'], cliente_data['telefono'], cliente_data['email'], 
                  cliente_data['direccion'], codigo_qr))
            
            cliente_id = cursor.lastrowid
            
            # v13.4: Si hay tarjeta_id, crear registro en tarjetas_fidelidad
            if tarjeta_id:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO tarjetas_fidelidad 
                            (codigo, id_cliente, nivel, activa, fecha_emision)
                        VALUES (?, ?, 'Bronce', 1, datetime('now'))
                    """, (tarjeta_id, cliente_id))
                except Exception:
                    pass
            
            self.conexion.commit()
            
            self.cliente_actual = {
                'id': cliente_id, 'nombre': cliente_data['nombre'], 'telefono': cliente_data['telefono'],
                'email': cliente_data['email'], 'direccion': cliente_data['direccion'],
                'puntos': 0, 'codigo_qr': codigo_qr, 'saldo': 0.0
            }
            self.actualizar_info_cliente()
            self.mostrar_mensaje("Éxito", f"Cliente '{cliente_data['nombre']}' agregado.")
        except sqlite3.Error as e:
            self.conexion.rollback()
            self.mostrar_mensaje("Error", f"Error al guardar cliente: {str(e)}", QMessageBox.Critical)

    def limpiar_cliente(self):
        self.cliente_actual = None
        self.lbl_nombre_cliente.setText("Nombre: Público General")
        self.lbl_telefono_cliente.setText("Teléfono: -")
        self.lbl_email_cliente.setText("Email: -")
        self.lbl_puntos_cliente.setText("Puntos: 0")
        self.txt_cliente.clear()

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
            
        venta_id = f"venta_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.ventas_en_espera[venta_id] = {
            'nombre': nombre_venta, 'cliente': self.cliente_actual,
            'compra': self.compra_actual.copy(), 'totales': self.totales.copy(),
            'timestamp': datetime.now()
        }
        self.btn_reanudar.setText(f"▶️ Reanudar ({len(self.ventas_en_espera)})")
        self.mostrar_mensaje("Éxito", f"Venta '{nombre_venta}' suspendida.")
        self.cancelar_venta(silent=True)

    def mostrar_ventas_espera(self):
        if not self.ventas_en_espera:
            QMessageBox.information(self, "Ventas en Espera", "No hay ventas suspendidas.")
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

        # ── Validar límite de crédito antes de abrir diálogo ──────────────
        if self.cliente_actual:
            try:
                row = self.container.db.execute(
                    "SELECT COALESCE(saldo,0) as saldo, COALESCE(limite_credito,0) as limite_credito FROM clientes WHERE id=?",
                    (self.cliente_actual['id'],)
                ).fetchone()
                if row:
                    saldo_usado   = float(row[0] or 0)
                    limite        = float(row[1] or 0)
                    total_venta   = self.totales.get('total_final', 0)
                    if limite > 0 and (saldo_usado + total_venta) > limite:
                        disponible = max(0, limite - saldo_usado)
                        resp = QMessageBox.question(
                            self, "⚠️ Límite de crédito",
                            f"El cliente {self.cliente_actual['nombre']} tiene:\n"
                            f"  Saldo en uso: ${saldo_usado:.2f}\n"
                            f"  Límite: ${limite:.2f}\n"
                            f"  Disponible: ${disponible:.2f}\n\n"
                            f"Esta venta (${total_venta:.2f}) excede el límite.\n"
                            "¿Continuar de todas formas?",
                            QMessageBox.Yes | QMessageBox.No
                        )
                        if resp != QMessageBox.Yes:
                            return
            except Exception:
                pass  # Si falla la consulta, continuar normalmente

        # ── v13.4 Fase 2: Ofrecer canje de estrellas ──────────────────────
        descuento_canje = 0.0
        total_a_pagar = self.totales['total_final']
        if self.cliente_actual:
            try:
                loyalty = getattr(self.container, 'loyalty_service', None)
                if loyalty and loyalty.enabled:
                    saldo_pts = loyalty.saldo(self.cliente_actual['id'])
                    if saldo_pts > 0:
                        # Cap: máximo 50% del subtotal
                        max_canje = min(saldo_pts, int(total_a_pagar * 0.5))
                        if max_canje > 0:
                            resp = QMessageBox.question(
                                self, "⭐ Canjear estrellas",
                                f"{self.cliente_actual['nombre']} tiene *{saldo_pts} estrellas*.\n\n"
                                f"¿Canjear hasta {max_canje} estrellas "
                                f"(= ${max_canje:.2f} de descuento)?\n\n"
                                f"Total actual: ${total_a_pagar:.2f}\n"
                                f"Total con canje: ${total_a_pagar - max_canje:.2f}",
                                QMessageBox.Yes | QMessageBox.No)
                            if resp == QMessageBox.Yes:
                                # Pedir cantidad exacta
                                from PyQt5.QtWidgets import QInputDialog
                                cant, ok = QInputDialog.getInt(
                                    self, "Estrellas a canjear",
                                    f"¿Cuántas estrellas? (máx {max_canje}):",
                                    value=max_canje, min=1, max=max_canje)
                                if ok and cant > 0:
                                    cajero_id = loyalty._get_cajero_id(
                                        self.obtener_usuario_actual())
                                    canje_r = loyalty.canjear(
                                        cliente_id=self.cliente_actual['id'],
                                        cajero_id=cajero_id,
                                        subtotal=total_a_pagar,
                                        estrellas=cant)
                                    if canje_r.get("ok"):
                                        descuento_canje = float(
                                            canje_r.get("descuento_aplicado", 0))
                                        total_a_pagar -= descuento_canje
                                        self.lbl_puntos_venta.setText(
                                            f"⭐ Canje: -{descuento_canje:.0f} | "
                                            f"Restante: {canje_r.get('saldo_restante', 0)}")
                                    else:
                                        QMessageBox.warning(self, "Canje",
                                            canje_r.get("error", "Error en canje"))
            except Exception as _canje_e:
                logger.debug("Canje pre-pago: %s", _canje_e)

        dialogo = DialogoPago(total_a_pagar, self)
        if dialogo.exec_() == QDialog.Accepted:
            datos_pago = dialogo.get_datos_pago()
            datos_pago['descuento_canje'] = descuento_canje
            self.finalizar_venta(datos_pago)

    def finalizar_venta(self, datos_pago: Dict[str, Any]):
        """🚀 LÓGICA ENTERPRISE: Delegación total de cálculos y auditorías al Contenedor Central."""
        try:
            usuario = self.obtener_usuario_actual()
            cliente_id = self.cliente_actual['id'] if self.cliente_actual else None

            carrito_limpio = [
                {
                    'product_id': item['id'],
                    'qty': item['cantidad'],
                    'unit_price': item['precio_unitario'],
                    'es_compuesto': item.get('es_compuesto', 0)
                }
                for item in self.compra_actual
            ]

            # ── Guardrail: detectar ítems por debajo del costo ──────────────
            try:
                items_bajo_costo = []
                for item in self.compra_actual:
                    costo_row = self.container.db.execute(
                        "SELECT precio_compra FROM productos WHERE id=?",
                        (item['id'],)
                    ).fetchone()
                    costo = float(costo_row[0]) if costo_row and costo_row[0] else 0
                    if costo > 0 and float(item['precio_unitario']) < costo:
                        items_bajo_costo.append(
                            f"• {item['nombre']}: ${item['precio_unitario']:.2f} "
                            f"(costo ${costo:.2f})"
                        )
                if items_bajo_costo:
                    resp = QMessageBox.warning(
                        self, "⚠️ Venta por debajo del costo",
                        "Los siguientes productos se venden con pérdida:\n\n"
                        + "\n".join(items_bajo_costo)
                        + "\n\n¿Continuar de todas formas?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if resp != QMessageBox.Yes:
                        return
            except Exception:
                pass  # No bloquea la venta si la validación falla

            # v13.1: use ProcesarVentaUC (orquestador) when available
            _uc = getattr(self.container, 'uc_venta', None)
            if _uc:
                from core.use_cases.venta import ItemCarrito, DatosPago as _DP
                _items_uc = [ItemCarrito(
                    producto_id  = it['product_id'],
                    cantidad     = float(it['qty']),
                    precio_unit  = float(it['unit_price']),
                    nombre       = it.get('name', ''),
                    es_compuesto = int(it.get('es_compuesto', 0)),
                ) for it in carrito_limpio]
                _dp = _DP(
                    forma_pago       = datos_pago['forma_pago'],
                    monto_pagado     = datos_pago['efectivo_recibido'] if datos_pago['forma_pago'] == 'Efectivo' else self.totales['total_final'],
                    cliente_id       = cliente_id,
                    descuento_global = float(datos_pago.get('descuento', 0)),
                    notas            = f"Venta POS Mostrador. Cajero: {usuario}.",
                )
                _r = _uc.ejecutar(_items_uc, _dp, self.sucursal_id, usuario)
                if not _r.ok:
                    raise RuntimeError(_r.error)
                folio = _r.folio
                self._ultima_venta_id = _r.venta_id
                self.btn_factura.setEnabled(bool(_r.venta_id))
                self.btn_reimprimir.setEnabled(bool(_r.venta_id))
                if _r.ticket_html:
                    self._ticket_html_cache = _r.ticket_html
            else:
                # Fallback directo (sin UC — compatibilidad)
                folio, _ticket_html = self.container.sales_service.execute_sale(
                    branch_id=self.sucursal_id,
                    user=usuario,
                    items=carrito_limpio,
                    payment_method=datos_pago['forma_pago'],
                    amount_paid=datos_pago['efectivo_recibido'] if datos_pago['forma_pago'] == 'Efectivo' else self.totales['total_final'],
                    client_id=cliente_id,
                    notes=f"Venta POS Mostrador. Cajero: {usuario}.",
                )
                row = self.container.db.execute(
                    "SELECT id FROM ventas WHERE folio=? ORDER BY id DESC LIMIT 1", (folio,)
                ).fetchone()
                self._ultima_venta_id = row[0] if row else None
                if hasattr(self,'btn_reimprimir'):
                    self.btn_reimprimir.setEnabled(bool(self._ultima_venta_id))

            # MercadoPago: generar y enviar link de pago
            if datos_pago.get('forma_pago') == 'Mercado Pago':
                try:
                    mp = getattr(self.container, 'mercado_pago_service', None)
                    if mp:
                        result = mp.crear_link(
                            total=self.totales['total_final'],
                            pedido_id=folio,
                            descripcion=f"Venta {folio} — {self.container.config_service.get('nombre_empresa','SPJ POS') if hasattr(self.container,'config_service') else 'SPJ POS'}"
                        )
                        link = result.get('link') or result.get('url','')
                        if link and self.cliente_actual and self.cliente_actual.get('telefono'):
                            wa = getattr(self.container, 'whatsapp_service', None)
                            if wa:
                                msg = (f"Hola {self.cliente_actual.get('nombre','cliente')}, "
                                       f"aqui esta tu link de pago por ${self.totales['total_final']:.2f}:\n{link}")
                                wa.send_message(phone_number=self.cliente_actual['telefono'], message=msg)
                except Exception as _mp_e:
                    import logging; logging.getLogger(__name__).debug("MP link: %s", _mp_e)

            self._abrir_cajon()

            # ── v13.4 Fase 2: Acreditar puntos de fidelización ───────────────
            puntos_resultado = {"estrellas_ganadas": 0, "saldo_actual": 0,
                                "mensaje_gamificacion": ""}
            try:
                loyalty = getattr(self.container, 'loyalty_service', None)
                if loyalty and cliente_id:
                    cli_tel = self.cliente_actual.get('telefono', '') if self.cliente_actual else ''
                    cli_nom = self.cliente_actual.get('nombre', '') if self.cliente_actual else ''
                    puntos_resultado = loyalty.acreditar_venta(
                        cliente_id=cliente_id,
                        venta_id=folio,
                        cajero=usuario,
                        total=self.totales['total_final'],
                        telefono=cli_tel,
                        nombre=cli_nom)
                    # Actualizar display de puntos en UI
                    saldo = puntos_resultado.get("saldo_actual", 0)
                    self.lbl_puntos_venta.setText(
                        f"⭐ +{puntos_resultado.get('estrellas_ganadas', 0)} | Saldo: {saldo}")
            except Exception as _loyalty_e:
                logger.debug("Loyalty post-venta: %s", _loyalty_e)

            # ── v13.4 Fase 3: Registrar ingreso en Tesorería Central ─────────
            try:
                treasury = getattr(self.container, 'treasury_service', None)
                if treasury and treasury.enabled:
                    treasury.registrar_ingreso(
                        categoria="venta",
                        concepto=f"Venta {folio}",
                        monto=self.totales['total_final'],
                        sucursal_id=self.sucursal_id,
                        referencia=str(folio),
                        usuario=usuario)
            except Exception as _t_e:
                logger.debug("Treasury post-venta: %s", _t_e)

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

            QMessageBox.information(self, "Venta Exitosa",
                f"¡Venta #{folio} completada!\nTotal: ${self.totales['total_final']:.2f}")
            self.cancelar_venta(silent=True)
            self._actualizar_comision_turno()
            self._tiempo_inicio_venta = None  # reset timer

        except PermissionError as e:
            QMessageBox.warning(self, "Acceso Denegado", str(e))
        except ValueError as e:
            QMessageBox.warning(self, "Aviso de Venta", str(e))
        except Exception as e:
            logger.error(f"Fallo crítico en UI de ventas: {str(e)}")
            QMessageBox.critical(self, "Error Fatal", f"Error procesando la venta:\n{str(e)}")

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
            db = self.container.db
            def _cfg(k, d=""):
                r = db.execute("SELECT valor FROM configuraciones WHERE clave=?", (k,)).fetchone()
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
        """Retrieves last sale data from DB and opens the print dialog."""
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
            self._imprimir_ticket_consolidado(datos_ticket)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

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
        txt_folio = QLineEdit(); txt_folio.setPlaceholderText("Folio VNT-… o ID")
        sf.addRow("Folio / ID:", txt_folio)
        lay.addWidget(grp)

        lbl_info = QLabel("Ingresa el folio y presiona Buscar")
        lbl_info.setProperty("class", "text-secondary")
        lbl_info.setStyleSheet("padding:4px;")
        lay.addWidget(lbl_info)

        tbl = QTableWidget(0, 4)
        tbl.setHorizontalHeaderLabels(["Producto","Cant.","Precio","Subtotal"])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(tbl)

        cmb_motivo = QComboBox()
        cmb_motivo.addItems(["Producto defectuoso","Error de cajero","Cliente arrepentido","Otro"])
        lay.addWidget(QLabel("Motivo:")); lay.addWidget(cmb_motivo)

        btn_bar = QHBoxLayout()
        btn_buscar = QPushButton("🔍 Buscar")
        btn_buscar.setProperty("class", "btn-info")
        btn_buscar.setStyleSheet("padding:7px 16px;")
        btn_cancel = QPushButton("❌ Cancelar venta")
        btn_cancel.setProperty("class", "btn-danger")
        btn_cancel.setStyleSheet("padding:7px 16px;")
        btn_cancel.setEnabled(False)
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.clicked.connect(dlg.reject)
        btn_bar.addWidget(btn_buscar); btn_bar.addWidget(btn_cancel); btn_bar.addStretch(); btn_bar.addWidget(btn_cerrar)
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
                SalesReversalService(self.container.db).cancel_sale(vid, self.usuario_actual)
            except Exception:
                try:
                    self.container.db.execute(
                        "UPDATE ventas SET estado='cancelada',notas=? WHERE id=?",
                        (f"Cancelada: {motivo}", vid))
                    try: self.container.db.commit()
                    except Exception: pass
                    try:
                        _uid = getattr(self,"usuario_actual",None) or getattr(self,"usuario","Sistema")
                        _ctr = getattr(self,"container",None)
                        if _ctr: audit_write(_ctr,modulo="VENTAS",accion="VENTA_CANCELADA",entidad="ventas",usuario=_uid,detalles="Venta cancelada",sucursal_id=getattr(self,"sucursal_id",1))
                    except Exception: pass
                except Exception as e:
                    QMessageBox.critical(dlg, "Error", str(e)); return
            QMessageBox.information(dlg, "✅ Éxito", "Venta cancelada correctamente.")
            dlg.accept()

        btn_buscar.clicked.connect(_buscar)
        btn_cancel.clicked.connect(_cancelar)
        dlg.exec_()