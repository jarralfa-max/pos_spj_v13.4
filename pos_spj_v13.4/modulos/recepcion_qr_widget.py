
# modulos/recepcion_qr_widget.py — SPJ POS v12
# ── Widget de Recepción con QR Reutilizable ───────────────────────────────────
#
# Flujo completo:
#   1. GENERACIÓN (POS): Encargado genera etiqueta QR para un contenedor físico.
#      El QR se imprime y pega en la caja/contenedor.
#      Si el contenedor ya tiene QR (reuso), se omite este paso.
#
#   2. ASIGNACIÓN (COMPRADOR, en bodega del proveedor):
#      Escanea el QR del contenedor → el sistema carga sus datos.
#      Asigna: productos, volumen/cantidad, costo unitario, sucursal destino.
#      Registra condición de pago (liquidado/crédito/parcial) y método.
#
#   3. RECEPCIÓN (ENCARGADO SUCURSAL):
#      Escanea el QR al recibir la caja.
#      Confirma o ajusta las cantidades reales recibidas.
#      El sistema: actualiza inventario_actual, registra lote FIFO,
#                  actualiza trazabilidad_qr, vincula a recepciones.
#
# REUTILIZACIÓN DE CONTENEDORES:
#   El QR físico permanece en la caja. Solo se reemplaza si se daña.
#   Cada "viaje" crea un nuevo registro en recepciones pero mantiene el mismo uuid_qr.
#
from __future__ import annotations
from core.services.auto_audit import audit_write
from modulos.spj_styles import spj_btn, apply_btn_styles, apply_object_names
import logging, uuid, json
from typing import Dict, List, Optional
from PyQt5.QtWidgets import (
    QListWidget, QListWidgetItem,
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QMessageBox,
    QDialog, QTabWidget, QTextEdit, QFrame, QSizePolicy, QSpinBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont

logger = logging.getLogger("spj.ui.recepcion_qr")

_C_AZUL   = "#2980b9"
_C_VERDE  = "#27ae60"
_C_ROJO   = "#e74c3c"
_C_NARAN  = "#e67e22"
_C_GRIS   = "#7f8c8d"


class RecepcionQRWidget(QWidget):
    """
    Widget reutilizable para recepción de mercancía con QR.
    Se embebe tanto en ModuloTransferencias como en ModuloComprasPro.
    """
    recepcion_completada = pyqtSignal(dict)   # emite datos de la recepción al módulo padre

    def __init__(self, conexion, sucursal_id: int = 1,
                 usuario: str = "Sistema", parent=None):
        super().__init__(parent)
        # Accept AppContainer or direct db connection
        if hasattr(conexion, 'db'):
            self.container = conexion
            self.conexion  = conexion.db
        else:
            self.container = None
            self.conexion  = conexion
        self.sucursal_id  = sucursal_id
        self.usuario      = usuario
        self._contenedor_activo: Optional[Dict] = None
        self._items_asignados: List[Dict] = []
        self._build_ui()
        # Activar lector QR HID
        self._activar_lector_qr()

    def set_sucursal(self, sucursal_id: int, nombre: str = ""):
        self.sucursal_id = sucursal_id

    def set_usuario(self, usuario: str, rol: str = ""):
        self.usuario = usuario

    # ── Construcción de UI ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        # Pestañas: Generar QR | Asignar Compra | Recepcionar
        self._tabs = QTabWidget()
        self._tab_generar    = QWidget()
        self._tab_asignar    = QWidget()
        self._tab_recepcionar = QWidget()
        self._tab_historial  = QWidget()
        self._tabs.addTab(self._tab_generar,     "🏷️ 1. Generar Etiqueta QR")
        self._tabs.addTab(self._tab_asignar,     "📋 2. Asignar Compra")
        self._tabs.addTab(self._tab_recepcionar, "📦 3. Recepcionar")
        self._tabs.addTab(self._tab_historial,   "📜 Historial")
        root.addWidget(self._tabs)

        self._build_tab_generar()
        self._build_tab_asignar()
        self._build_tab_recepcionar()
        self._build_tab_historial()

    # ── Pestaña 1: Generar QR ─────────────────────────────────────────────────

    def _build_tab_generar(self) -> None:
        lay = QVBoxLayout(self._tab_generar)
        lay.setContentsMargins(12, 10, 12, 10)

        info = QLabel(
            "Genera una etiqueta QR para un contenedor físico (caja, canasta, cubeta). "
            "Imprime y pega la etiqueta. El mismo QR se reutiliza en cada viaje — "
            "solo reemplázalo si se daña."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{_C_GRIS}; font-size:12px;")
        lay.addWidget(info)

        form = QFormLayout()
        self._txt_codigo_interno = QLineEdit()
        self._txt_codigo_interno.setPlaceholderText("Ej: CAJA-001, CANASTA-A (opcional)")
        self._txt_descripcion = QLineEdit()
        self._txt_descripcion.setPlaceholderText("Ej: Caja de plástico 50L azul")
        self._cmb_copias = QSpinBox()
        self._cmb_copias.setRange(1, 10); self._cmb_copias.setValue(1)
        form.addRow("Código interno:", self._txt_codigo_interno)
        form.addRow("Descripción:", self._txt_descripcion)
        form.addRow("Copias a imprimir:", self._cmb_copias)
        lay.addLayout(form)

        # Vista previa del QR
        self._lbl_qr_preview = QLabel("Vista previa del QR aparecerá aquí")
        self._lbl_qr_preview.setAlignment(Qt.AlignCenter)
        self._lbl_qr_preview.setFixedHeight(200)
        self._lbl_qr_preview.setStyleSheet(
            "border:2px dashed #ccc; background:#f9f9f9; color:#aaa; font-size:13px;"
        )
        lay.addWidget(self._lbl_qr_preview)

        btns = QHBoxLayout()
        btn_generar = QPushButton("🏷️ Generar y Ver QR")
        btn_generar.setObjectName("primaryBtn")
        btn_generar.clicked.connect(self._generar_qr_contenedor)
        btn_imprimir = QPushButton("🖨️ Imprimir Etiqueta")
        btn_imprimir.setObjectName("outlineBtn")
        btn_imprimir.clicked.connect(self._imprimir_etiqueta_qr)
        btns.addStretch(); btns.addWidget(btn_generar); btns.addWidget(btn_imprimir)
        lay.addLayout(btns)
        lay.addStretch()

    # ── Pestaña 2: Asignar Compra ─────────────────────────────────────────────

    def _build_tab_asignar(self) -> None:
        lay = QVBoxLayout(self._tab_asignar)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)

        # ── Step 1: Escanear contenedor ───────────────────────────────────────
        step1 = QGroupBox("① Escanear contenedor QR")
        s1 = QHBoxLayout(step1); s1.setContentsMargins(8, 6, 8, 6)
        self._txt_uuid_asignar = QLineEdit()
        self._txt_uuid_asignar.setPlaceholderText("Escanea el QR o escribe el UUID…")
        self._txt_uuid_asignar.setMinimumHeight(32)
        self._txt_uuid_asignar.returnPressed.connect(self._cargar_contenedor)
        btn_cargar = QPushButton("🔍 Cargar")
        btn_cargar.setObjectName("primaryBtn")
        btn_cargar.clicked.connect(self._cargar_contenedor)
        s1.addWidget(self._txt_uuid_asignar, 1)
        s1.addWidget(btn_cargar)
        lay.addWidget(step1)

        # Info del contenedor cargado
        self._lbl_cont_info = QLabel("Sin contenedor cargado")
        self._lbl_cont_info.setStyleSheet(f"color:{_C_GRIS};padding:2px 8px;font-style:italic;")
        lay.addWidget(self._lbl_cont_info)

        # ── Step 2: Proveedor ─────────────────────────────────────────────────
        step2 = QGroupBox("② Proveedor")
        s2 = QHBoxLayout(step2); s2.setContentsMargins(8, 6, 8, 6)
        self._txt_buscar_proveedor = QLineEdit()
        self._txt_buscar_proveedor.setPlaceholderText("Buscar por nombre o RFC…")
        self._txt_buscar_proveedor.setMinimumHeight(30)
        self._txt_buscar_proveedor.textChanged.connect(self._buscar_proveedor_asignar)
        self._lbl_proveedor_sel = QLabel("Ninguno")
        self._lbl_proveedor_sel.setStyleSheet(
            f"color:{_C_AZUL};font-weight:bold;padding:4px 10px;"
            "border-radius:4px;border:1px solid gray;min-width:120px;")
        self._proveedor_asignar_id = 0
        s2.addWidget(self._txt_buscar_proveedor, 1)
        s2.addWidget(self._lbl_proveedor_sel)
        lay.addWidget(step2)

        # Popup búsqueda proveedor
        self._lst_proveedores = QListWidget()
        self._lst_proveedores.setMaximumHeight(100)
        self._lst_proveedores.setVisible(False)
        self._lst_proveedores.itemClicked.connect(self._seleccionar_proveedor_asignar)
        lay.addWidget(self._lst_proveedores)

        # ── Step 3: Productos ─────────────────────────────────────────────────
        step3 = QGroupBox("③ Productos del contenedor")
        s3 = QVBoxLayout(step3); s3.setContentsMargins(8, 6, 8, 6); s3.setSpacing(6)

        # Fila para agregar producto
        add_row = QHBoxLayout(); add_row.setSpacing(4)
        self._txt_buscar_prod_asign = QLineEdit()
        self._txt_buscar_prod_asign.setPlaceholderText("Buscar producto…")
        self._txt_buscar_prod_asign.setMinimumHeight(30)
        self._txt_buscar_prod_asign.textChanged.connect(self._buscar_producto_asignar)
        self._lbl_prod_asign_sel = QLabel("")
        self._lbl_prod_asign_sel.setStyleSheet(f"color:{_C_AZUL};font-size:11px;")
        self._prod_asignar_id = 0

        self._spin_qty_asign = QDoubleSpinBox()
        self._spin_qty_asign.setRange(0.001, 99999); self._spin_qty_asign.setDecimals(3)
        self._spin_qty_asign.setPrefix("Cant: "); self._spin_qty_asign.setMinimumHeight(30)
        self._spin_qty_asign.setFixedWidth(110)

        self._spin_costo_asign = QDoubleSpinBox()
        self._spin_costo_asign.setRange(0, 999999); self._spin_costo_asign.setDecimals(2)
        self._spin_costo_asign.setPrefix("$ "); self._spin_costo_asign.setMinimumHeight(30)
        self._spin_costo_asign.setFixedWidth(110)

        btn_add_item = QPushButton("➕")
        btn_add_item.setToolTip("Agregar producto al contenedor")
        btn_add_item.setFixedSize(36, 30)
        btn_add_item.setObjectName("successBtn")
        btn_add_item.clicked.connect(self._agregar_item_asignacion)

        btn_rm_item = QPushButton("🗑")
        btn_rm_item.setToolTip("Quitar producto seleccionado")
        btn_rm_item.setFixedSize(36, 30)
        btn_rm_item.setObjectName("dangerBtn")
        btn_rm_item.clicked.connect(self._quitar_item_asignacion)

        add_row.addWidget(self._txt_buscar_prod_asign, 1)
        add_row.addWidget(self._spin_qty_asign)
        add_row.addWidget(self._spin_costo_asign)
        add_row.addWidget(btn_add_item)
        add_row.addWidget(btn_rm_item)
        s3.addWidget(self._lbl_prod_asign_sel)
        s3.addLayout(add_row)

        # Popup búsqueda producto
        self._lst_prod_asign = QListWidget()
        self._lst_prod_asign.setMaximumHeight(90)
        self._lst_prod_asign.setVisible(False)
        self._lst_prod_asign.itemClicked.connect(self._seleccionar_producto_asignar)
        s3.addWidget(self._lst_prod_asign)

        # Tabla de ítems asignados
        self._tbl_items_asign = QTableWidget()
        self._tbl_items_asign.setColumnCount(5)
        self._tbl_items_asign.setHorizontalHeaderLabels(
            ["Producto", "Cantidad", "Unidad", "Costo Unit. ($)", "Subtotal ($)"])
        self._tbl_items_asign.verticalHeader().setVisible(False)
        self._tbl_items_asign.setAlternatingRowColors(True)
        self._tbl_items_asign.setMinimumHeight(120)
        self._tbl_items_asign.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hdr = self._tbl_items_asign.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3, 4):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        s3.addWidget(self._tbl_items_asign)
        lay.addWidget(step3, 1)  # stretch

        # ── Step 4: Pago ──────────────────────────────────────────────────────
        step4 = QGroupBox("④ Pago y destino")
        s4 = QGridLayout(step4); s4.setContentsMargins(8, 6, 8, 6); s4.setSpacing(6)

        self._cmb_condicion = QComboBox()
        self._cmb_condicion.addItems(["liquidado", "crédito", "parcial"])
        self._cmb_condicion.currentTextChanged.connect(self._on_condicion_changed)
        self._cmb_metodo = QComboBox()
        self._cmb_metodo.addItems(["efectivo", "tarjeta", "transferencia", "cheque"])
        self._spin_monto_pagado = QDoubleSpinBox()
        self._spin_monto_pagado.setRange(0, 9999999)
        self._spin_monto_pagado.setDecimals(2)
        self._spin_monto_pagado.setPrefix("$ ")
        self._txt_referencia = QLineEdit()
        self._txt_referencia.setPlaceholderText("No. cheque / referencia (opcional)")
        self._lbl_saldo = QLabel("Saldo pendiente: $0.00")
        self._lbl_saldo.setStyleSheet(f"color:{_C_ROJO};font-weight:bold;")
        self._cmb_sucursal_destino = QComboBox()
        self._cargar_sucursales_combo_recepcion()
        self._txt_notas_asign = QTextEdit()
        self._txt_notas_asign.setMaximumHeight(40)
        self._txt_notas_asign.setPlaceholderText("Notas (opcional)…")

        # Fila 1: Condición | Método | Monto | Referencia
        s4.addWidget(QLabel("Condición:"), 0, 0)
        s4.addWidget(self._cmb_condicion, 0, 1)
        s4.addWidget(QLabel("Método:"), 0, 2)
        s4.addWidget(self._cmb_metodo, 0, 3)
        s4.addWidget(QLabel("Monto pagado:"), 0, 4)
        s4.addWidget(self._spin_monto_pagado, 0, 5)
        s4.addWidget(QLabel("Referencia:"), 0, 6)
        s4.addWidget(self._txt_referencia, 0, 7)

        # Fila 2: Sucursal destino | Notas | Saldo
        s4.addWidget(QLabel("Sucursal destino:"), 1, 0)
        s4.addWidget(self._cmb_sucursal_destino, 1, 1, 1, 2)
        s4.addWidget(QLabel("Notas:"), 1, 3)
        self._txt_notas_asign.setMaximumHeight(30)
        s4.addWidget(self._txt_notas_asign, 1, 4, 1, 3)
        s4.addWidget(self._lbl_saldo, 1, 7)

        lay.addWidget(step4)

        # ── Botón guardar ─────────────────────────────────────────────────────
        btn_guardar_asig = QPushButton("💾 Guardar asignación")
        btn_guardar_asig.setMinimumHeight(38)
        btn_guardar_asig.setObjectName("successBtn")
        btn_guardar_asig.clicked.connect(self._guardar_asignacion)
        lay.addWidget(btn_guardar_asig)

    # ── Pestaña 3: Recepcionar ─────────────────────────────────────────────────

    def _build_tab_recepcionar(self) -> None:
        lay = QVBoxLayout(self._tab_recepcionar)
        lay.setContentsMargins(12, 10, 12, 10)

        info = QLabel(
            "Escanea el QR de cada contenedor al recibirlo en la sucursal. "
            "Confirma o ajusta las cantidades reales. "
            "El sistema actualiza inventario, lotes FIFO y trazabilidad."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{_C_GRIS}; font-size:12px;")
        lay.addWidget(info)

        scan_grp = QGroupBox("Escanear QR del contenedor recibido")
        scan_lay = QHBoxLayout(scan_grp)
        self._txt_uuid_recv = QLineEdit()
        self._txt_uuid_recv.setPlaceholderText("Escanea el QR con el lector HID…")
        self._txt_uuid_recv.returnPressed.connect(self._cargar_para_recepcion)
        btn_recv_cargar = QPushButton("🔍 Cargar")
        btn_recv_cargar.setObjectName("primaryBtn")
        btn_recv_cargar.clicked.connect(self._cargar_para_recepcion)
        scan_lay.addWidget(self._txt_uuid_recv); scan_lay.addWidget(btn_recv_cargar)
        lay.addWidget(scan_grp)

        self._lbl_recv_info = QLabel("Sin contenedor cargado")
        self._lbl_recv_info.setStyleSheet(f"color:{_C_GRIS}; padding:4px;")
        lay.addWidget(self._lbl_recv_info)

        self._tbl_recv = QTableWidget()
        self._tbl_recv.setColumnCount(6)
        self._tbl_recv.setHorizontalHeaderLabels(
            ["Producto", "Esperado", "Unidad", "Recibido Real", "Diferencia", "Caducidad (opc.)"]
        )
        self._tbl_recv.verticalHeader().setVisible(False)
        self._tbl_recv.setAlternatingRowColors(True)
        hdr = self._tbl_recv.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1,2,3,4,5): hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        lay.addWidget(self._tbl_recv)

        recv_form = QFormLayout()
        self._txt_recv_notas = QTextEdit(); self._txt_recv_notas.setMaximumHeight(50)
        self._txt_recv_notas.setPlaceholderText("Observaciones de recepción, daños, faltantes…")
        recv_form.addRow("Notas:", self._txt_recv_notas)
        lay.addLayout(recv_form)

        self._lbl_recv_diff = QLabel("Diferencia total: 0.000")
        self._lbl_recv_diff.setStyleSheet("font-weight:bold; font-size:13px;")
        lay.addWidget(self._lbl_recv_diff)

        btn_confirmar_recv = QPushButton("✅ Confirmar Recepción y Actualizar Inventario")
        btn_confirmar_recv.setObjectName("successBtn")
        btn_confirmar_recv.clicked.connect(self._confirmar_recepcion)
        lay.addWidget(btn_confirmar_recv)

    # ── Pestaña 4: Historial ──────────────────────────────────────────────────

    def _build_tab_historial(self) -> None:
        from PyQt5.QtWidgets import QTabWidget
        lay = QVBoxLayout(self._tab_historial)
        lay.setContentsMargins(8, 8, 8, 8)

        # Sub-tabs: Recepciones | QR Generados
        sub_tabs = QTabWidget()
        lay.addWidget(sub_tabs)

        # ── Sub-tab 1: Recepciones (original) ────────────────────────────────
        tab_rec = QWidget(); sub_tabs.addTab(tab_rec, "📦 Recepciones")
        lay_rec = QVBoxLayout(tab_rec); lay_rec.setContentsMargins(4,4,4,4)
        self._tbl_hist = QTableWidget()
        self._tbl_hist.setColumnCount(7)
        self._tbl_hist.setHorizontalHeaderLabels([
            "Folio", "Fecha", "Proveedor", "Condición Pago",
            "Total", "Pagado", "Estado"
        ])
        self._tbl_hist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_hist.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_hist.verticalHeader().setVisible(False)
        self._tbl_hist.setAlternatingRowColors(True)
        hdr = self._tbl_hist.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.Stretch)
        lay.addWidget(self._tbl_hist)
        btn_refresh = QPushButton("🔄 Actualizar historial")
        btn_refresh.setObjectName("warningBtn")
        btn_refresh.clicked.connect(self._cargar_historial)
        lay_rec.addWidget(self._tbl_hist)
        lay_rec.addWidget(btn_refresh)

        # ── Sub-tab 2: QR Generados (para reimpresión) ────────────────────────
        tab_qr = QWidget(); sub_tabs.addTab(tab_qr, "🏷️ QR Generados")
        lay_qr = QVBoxLayout(tab_qr); lay_qr.setContentsMargins(4,4,4,4)

        hdr_qr = QHBoxLayout()
        hdr_qr.addWidget(QLabel("<b>Historial de QR generados — reimpresión</b>"))
        hdr_qr.addStretch()
        btn_ref_qr = QPushButton("🔄 Actualizar")
        btn_ref_qr.setObjectName("warningBtn")
        btn_ref_qr.clicked.connect(self._cargar_historial_qr)
        hdr_qr.addWidget(btn_ref_qr)
        lay_qr.addLayout(hdr_qr)

        self._tbl_qr_hist = QTableWidget()
        self._tbl_qr_hist.setColumnCount(6)
        self._tbl_qr_hist.setHorizontalHeaderLabels([
            "UUID QR", "Descripción", "Tipo", "Sucursal", "Fecha Creación", "Acciones"
        ])
        self._tbl_qr_hist.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tbl_qr_hist.setSelectionBehavior(QTableWidget.SelectRows)
        self._tbl_qr_hist.setAlternatingRowColors(True)
        hh = self._tbl_qr_hist.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        lay_qr.addWidget(self._tbl_qr_hist)

        self._cargar_historial_qr()
        self._cargar_historial()
        apply_object_names(self)

    # ── Lógica de negocio ─────────────────────────────────────────────────────

    def _activar_lector_qr(self) -> None:
        """Activa el LectorQR HID para capturar escaneos automáticamente."""
        try:
            from hardware.lector_qr import LectorQR
            self._lector = LectorQR(parent=self)
            self._lector.qr_contenedor.connect(self._on_qr_escaneado)
            self._lector.activar()
            logger.info("LectorQR activado en RecepcionQRWidget.")
        except Exception as e:
            logger.warning("LectorQR no disponible: %s", e)
            self._lector = None

    def _on_qr_escaneado(self, uuid_qr: str) -> None:
        """Callback del lector HID — rellena el campo activo según la pestaña."""
        tab = self._tabs.currentIndex()
        if tab == 1:  # Asignar
            self._txt_uuid_asignar.setText(uuid_qr)
            self._cargar_contenedor()
        elif tab == 2:  # Recepcionar
            self._txt_uuid_recv.setText(uuid_qr)
            self._cargar_para_recepcion()

    def _generar_qr_contenedor(self) -> None:
        """Genera un QR nuevo para un contenedor y muestra la imagen."""
        from PyQt5.QtGui import QPixmap
        try:
            from services.qr_service import QRService
            svc = QRService(self.conexion, self.sucursal_id)
            datos = {
                "usuario":         self.usuario,
                "codigo_interno":  self._txt_codigo_interno.text().strip(),
                "descripcion":     self._txt_descripcion.text().strip(),
            }
            uuid_qr = svc.generar_uuid_qr("contenedor", datos)
            # Registrar en contenedores_qr
            try:
                self.conexion.execute("""
                    INSERT OR IGNORE INTO contenedores_qr
                        (uuid_qr, codigo_interno, descripcion, sucursal_origen)
                    VALUES(?,?,?,?)
                """, (uuid_qr,
                      self._txt_codigo_interno.text().strip() or None,
                      self._txt_descripcion.text().strip() or None,
                      self.sucursal_id))
                self.conexion.commit()
            except Exception: pass

            # Mostrar imagen QR
            png_bytes = svc.generar_imagen_qr(f"SPJ:CONT:{uuid_qr}", size=200)
            pixmap = QPixmap()
            pixmap.loadFromData(png_bytes)
            self._lbl_qr_preview.setPixmap(
                pixmap.scaled(190, 190, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            self._last_generated_uuid = uuid_qr
            self._last_generated_png  = png_bytes
            QMessageBox.information(self, "QR Generado",
                f"UUID: {uuid_qr}\nListo para imprimir.")
        except Exception as e:
            logger.exception("_generar_qr_contenedor")
            QMessageBox.critical(self, "Error", str(e))

    def _imprimir_etiqueta_qr(self) -> None:
        """Imprime la etiqueta del último QR generado."""
        if not hasattr(self, '_last_generated_uuid'):
            QMessageBox.warning(self, "Aviso", "Genera un QR primero."); return
        try:
            from hardware.impresora_etiquetas import ImpresoraEtiquetas
            from labels.generador_etiquetas import GeneradorEtiquetas
            gen = GeneradorEtiquetas(self.conexion)
            cmds = gen.etiqueta_contenedor_qr(
                uuid_qr     = self._last_generated_uuid,
                codigo      = self._txt_codigo_interno.text().strip(),
                descripcion = self._txt_descripcion.text().strip(),
            )
            imp = ImpresoraEtiquetas()
            imp.imprimir(cmds, copias=self._cmb_copias.value())
            QMessageBox.information(self, "Impresión", "Etiqueta enviada a impresora.")
        except Exception as e:
            QMessageBox.warning(self, "Impresión",
                f"No se pudo imprimir automáticamente.\nUUID: {self._last_generated_uuid}\n{e}")

    def _cargar_contenedor(self) -> None:
        """Carga los datos del contenedor por UUID para la asignación."""
        uuid_qr = self._txt_uuid_asignar.text().strip()
        if not uuid_qr: return
        # Normalizar prefijo del lector
        if uuid_qr.startswith("SPJ:CONT:"):
            uuid_qr = uuid_qr[9:]
        try:
            row = self.conexion.execute(
                "SELECT * FROM trazabilidad_qr WHERE uuid_qr=? LIMIT 1", (uuid_qr,)
            ).fetchone()
            if row:
                row = dict(row)
                self._contenedor_activo = row
                self._lbl_cont_info.setText(
                    f"✅ Contenedor: {uuid_qr} | "
                    f"Viaje #{row.get('datos_extra','{}')}"
                )
                self._lbl_cont_info.setStyleSheet(f"color:{_C_VERDE}; padding:4px;")
            else:
                # Contenedor nuevo o nunca registrado
                self._contenedor_activo = {"uuid_qr": uuid_qr, "es_nuevo": True}
                self._lbl_cont_info.setText(
                    f"🆕 QR nuevo (no asignado antes): {uuid_qr}"
                )
                self._lbl_cont_info.setStyleSheet(f"color:{_C_NARAN}; padding:4px;")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _cargar_para_recepcion(self) -> None:
        """Carga los datos del contenedor para recepcionar."""
        uuid_qr = self._txt_uuid_recv.text().strip()
        if uuid_qr.startswith("SPJ:CONT:"): uuid_qr = uuid_qr[9:]
        if not uuid_qr: return
        try:
            row = self.conexion.execute("""
                SELECT t.*, p.nombre as proveedor_nombre
                FROM trazabilidad_qr t
                LEFT JOIN proveedores p ON p.id = t.proveedor_id
                WHERE t.uuid_qr=? LIMIT 1""", (uuid_qr,)
            ).fetchone()
            if not row:
                QMessageBox.warning(self, "No encontrado",
                    f"QR {uuid_qr} no tiene datos asignados.\n"
                    "Ve a la pestaña 'Asignar Compra' primero."); return
            row = dict(row)
            datos_extra = json.loads(row.get("datos_extra") or "{}")
            items = datos_extra.get("items", [])
            self._lbl_recv_info.setText(
                f"📦 UUID: {uuid_qr} | Proveedor: {row.get('proveedor_nombre','—')} | "
                f"Items: {len(items)}"
            )
            self._lbl_recv_info.setStyleSheet(f"color:{_C_AZUL}; padding:4px; font-weight:bold;")
            self._poblar_tabla_recepcion(items)
            self._contenedor_activo = row
        except Exception as e:
            logger.exception("_cargar_para_recepcion")
            QMessageBox.critical(self, "Error", str(e))

    def _poblar_tabla_recepcion(self, items: List[Dict]) -> None:
        self._tbl_recv.setRowCount(len(items))
        for ri, item in enumerate(items):
            qty_esperada = float(item.get("cantidad", item.get("quantity", 0)))
            nombre       = item.get("nombre", item.get("product_name", "?"))
            unidad       = item.get("unidad", item.get("unit", "kg"))

            lbl_prod = QTableWidgetItem(nombre)
            lbl_prod.setFlags(Qt.ItemIsEnabled)
            lbl_qty  = QTableWidgetItem(f"{qty_esperada:.3f}")
            lbl_qty.setFlags(Qt.ItemIsEnabled); lbl_qty.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter)
            lbl_unit = QTableWidgetItem(unidad); lbl_unit.setFlags(Qt.ItemIsEnabled)

            spin_recv = QDoubleSpinBox()
            spin_recv.setRange(0, qty_esperada * 2); spin_recv.setDecimals(3)
            spin_recv.setValue(qty_esperada)
            spin_recv.setProperty("qty_esperada", qty_esperada)
            spin_recv.setProperty("product_id", item.get("product_id"))
            spin_recv.setProperty("costo_unitario", item.get("costo_unitario", 0))
            spin_recv.valueChanged.connect(self._actualizar_diff_recepcion)

            diff_item = QTableWidgetItem("0.000")
            diff_item.setFlags(Qt.ItemIsEnabled); diff_item.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter)

            cad_edit = QLineEdit(); cad_edit.setPlaceholderText("YYYY-MM-DD")

            self._tbl_recv.setItem(ri, 0, lbl_prod)
            self._tbl_recv.setItem(ri, 1, lbl_qty)
            self._tbl_recv.setItem(ri, 2, lbl_unit)
            self._tbl_recv.setCellWidget(ri, 3, spin_recv)
            self._tbl_recv.setItem(ri, 4, diff_item)
            self._tbl_recv.setCellWidget(ri, 5, cad_edit)

    def _actualizar_diff_recepcion(self) -> None:
        total_diff = 0.0
        for ri in range(self._tbl_recv.rowCount()):
            spin = self._tbl_recv.cellWidget(ri, 3)
            diff_item = self._tbl_recv.item(ri, 4)
            if not spin or not diff_item: continue
            qty_esp  = float(spin.property("qty_esperada") or 0)
            qty_recv = spin.value()
            diff     = qty_recv - qty_esp
            total_diff += abs(diff)
            diff_item.setText(f"{diff:+.3f}")
            diff_item.setForeground(
                QColor(_C_ROJO if diff < -0.001 else _C_VERDE if diff > 0.001 else "#333")
            )
        color = _C_ROJO if total_diff > 0.01 else _C_VERDE
        self._lbl_recv_diff.setText(f"Diferencia total: {total_diff:.3f}")
        self._lbl_recv_diff.setStyleSheet(f"font-weight:bold;font-size:13px;color:{color};")

    def _confirmar_recepcion(self) -> None:
        """Confirma la recepción: actualiza inventario, lotes y trazabilidad."""
        if not self._contenedor_activo:
            QMessageBox.warning(self, "Aviso", "Carga un contenedor primero."); return
        try:
            uuid_qr    = self._contenedor_activo.get("uuid_qr", "")
            notas_recv = self._txt_recv_notas.toPlainText().strip()
            items_recibidos = []
            for ri in range(self._tbl_recv.rowCount()):
                spin    = self._tbl_recv.cellWidget(ri, 3)
                cad_edit = self._tbl_recv.cellWidget(ri, 5)
                prod_id  = spin.property("product_id") if spin else None
                qty_recv = spin.value() if spin else 0
                costo    = float(spin.property("costo_unitario") or 0) if spin else 0
                caducidad = cad_edit.text().strip() if cad_edit else None
                if prod_id and qty_recv > 0:
                    items_recibidos.append({
                        "product_id":    prod_id,
                        "cantidad":      qty_recv,
                        "costo_unitario": costo,
                        "fecha_caducidad": caducidad,
                    })

            if not items_recibidos:
                QMessageBox.warning(self, "Aviso", "No hay ítems con cantidad > 0."); return

            # Actualizar inventario y lotes
            self._procesar_recepcion_en_bd(uuid_qr, items_recibidos, notas_recv)

            QMessageBox.information(self, "✅ Recepción Completada",
                f"Inventario actualizado.\nQR: {uuid_qr}\n"
                f"Items procesados: {len(items_recibidos)}")
            self._limpiar_tab_recepcion()
            self._cargar_historial()
            self.recepcion_completada.emit({
                "uuid_qr": uuid_qr, "items": items_recibidos
            })
        except Exception as e:
            logger.exception("_confirmar_recepcion")
            QMessageBox.critical(self, "Error", str(e))

    def _procesar_recepcion_en_bd(self, uuid_qr: str, items: List[Dict], notas: str) -> None:
        """Transacción atómica: recepciones + recepcion_items + inventario + lotes + trazabilidad."""
        op_id = str(uuid.uuid4())
        folio = f"REC-{op_id[:8].upper()}"
        datos_extra = json.loads(
            self.conexion.execute(
                "SELECT COALESCE(datos_extra,'{}') FROM trazabilidad_qr WHERE uuid_qr=?",
                (uuid_qr,)
            ).fetchone()[0] if self.conexion.execute(
                "SELECT 1 FROM trazabilidad_qr WHERE uuid_qr=?", (uuid_qr,)
            ).fetchone() else "{}"
        )
        proveedor_id = datos_extra.get("proveedor_id")
        condicion    = datos_extra.get("condicion_pago", "liquidado")
        metodo       = datos_extra.get("metodo_pago", "efectivo")
        monto_pagado = float(datos_extra.get("monto_pagado", 0))
        monto_total  = float(datos_extra.get("monto_total", 0))

        import uuid as _u2
        _sp_qr = f"qr_{_u2.uuid4().hex[:8]}"
        self.conexion.execute(f"SAVEPOINT {_sp_qr}")
        try:
            # 1. Recepción cabecera
            cur = self.conexion.execute("""
                INSERT INTO recepciones
                    (folio, tipo, proveedor_id, sucursal_id, usuario,
                     notas, operation_id, estado,
                     uuid_qr, condicion_pago, metodo_pago,
                     monto_pagado, monto_total,
                     saldo_pendiente)
                VALUES(?,?,?,?,?,?,?,'completada',?,?,?,?,?,?)
            """, (folio, "COMPRA", proveedor_id, self.sucursal_id, self.usuario,
                  notas, op_id, uuid_qr, condicion, metodo,
                  monto_pagado, monto_total,
                  max(0, monto_total - monto_pagado)))
            recepcion_id = cur.lastrowid

            for item in items:
                prod_id  = item["product_id"]
                qty      = float(item["cantidad"])
                costo    = float(item.get("costo_unitario", 0))
                caducidad = item.get("fecha_caducidad")

                # 2. Detalle de recepción
                self.conexion.execute("""
                    INSERT INTO recepcion_items
                        (recepcion_id, producto_id, cantidad, costo_unitario,
                         uuid_qr_contenedor, fecha_caducidad)
                    VALUES(?,?,?,?,?,?)
                """, (recepcion_id, prod_id, qty, costo, uuid_qr, caducidad))

                # 3. Actualizar inventario_actual (UPSERT con costo promedio ponderado)
                self.conexion.execute("""
                    INSERT INTO inventario_actual(producto_id, sucursal_id, cantidad, costo_promedio)
                    VALUES(?,?,?,?)
                    ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET
                        cantidad = cantidad + excluded.cantidad,
                        costo_promedio = (
                            (cantidad * costo_promedio + excluded.cantidad * excluded.costo_promedio)
                            / (cantidad + excluded.cantidad)
                        ),
                        ultima_actualizacion = datetime('now')
                """, (prod_id, self.sucursal_id, qty, costo))

                # 3b. Sync productos.existencia (sum across all branches)
                # This is what the POS and all modules read for stock levels
                self.conexion.execute("""
                    UPDATE productos
                    SET existencia   = (SELECT COALESCE(SUM(cantidad),0)
                                        FROM inventario_actual
                                        WHERE producto_id = ?),
                        precio_compra = ?
                    WHERE id = ?
                """, (prod_id, costo, prod_id))

                # 4. Movimiento de inventario (auditoría)
                self.conexion.execute("""
                    INSERT INTO movimientos_inventario
                        (uuid, producto_id, tipo, tipo_movimiento, cantidad,
                         descripcion, referencia, usuario, sucursal_id)
                    VALUES(?,?,'entrada','COMPRA',?,?,?,?,?)
                """, (str(uuid.uuid4()), prod_id, qty,
                      f"Recepción QR {uuid_qr}", folio, self.usuario, self.sucursal_id))

            # 5. Marcar QR como recibido
            self.conexion.execute("""
                UPDATE trazabilidad_qr
                SET estado='recibido', fecha_recepcion=datetime('now'), recepcion_id=?
                WHERE uuid_qr=?
            """, (recepcion_id, uuid_qr))

            # 6. Actualizar contenedor a disponible
            try:
                self.conexion.execute("""
                    UPDATE contenedores_qr
                    SET estado='disponible', sucursal_destino=?,
                        viaje_actual=viaje_actual+1, updated_at=datetime('now')
                    WHERE uuid_qr=?
                """, (self.sucursal_id, uuid_qr))
            except Exception: pass

            self.conexion.execute(f"RELEASE SAVEPOINT {_sp_qr}")

            # Actualizar inventario via ApplicationService
            _app = getattr(self.container, 'app_service', None) if self.container else None
            for item in items:
                try:
                    pid = item.get("product_id", item.get("producto_id", 0))
                    qty = float(item.get("cantidad", 0))
                    costo = float(item.get("costo_unitario", 0))
                    if _app and pid and qty > 0:
                        _app.registrar_compra(
                            producto_id=pid, cantidad=qty,
                            costo_unitario=costo,
                            usuario=getattr(self, 'usuario', ''),
                            sucursal_id=self.sucursal_id)
                    elif pid and qty > 0:
                        self.conexion.execute(
                            "UPDATE productos SET existencia = existencia + ?, "
                            "precio_compra = CASE WHEN ? > 0 THEN ? ELSE precio_compra END "
                            "WHERE id = ?",
                            (qty, costo, costo, pid))
                except Exception as _ue:
                    import logging as _lg
                    _lg.getLogger(__name__).error("QR existencia update: %s", _ue)

        except Exception:
            try: self.conexion.execute(f"ROLLBACK TO SAVEPOINT {_sp_qr}")
            except Exception: pass
            raise

    def _guardar_asignacion(self) -> None:
        """Guarda la asignación de productos + pago al contenedor."""
        if not self._contenedor_activo:
            QMessageBox.warning(self, "Aviso", "Carga un contenedor primero."); return
        if not self._items_asignados:
            QMessageBox.warning(self, "Aviso", "Agrega al menos un producto."); return

        uuid_qr     = self._contenedor_activo.get("uuid_qr", "")
        condicion   = self._cmb_condicion.currentText()
        metodo      = self._cmb_metodo.currentText()
        monto_total = sum(i["subtotal"] for i in self._items_asignados)
        monto_pagado = self._spin_monto_pagado.value()
        if condicion == "liquidado": monto_pagado = monto_total
        elif condicion == "crédito": monto_pagado = 0.0
        dest_id     = self._cmb_sucursal_destino.currentData() or self.sucursal_id
        notas       = self._txt_notas_asign.toPlainText().strip()
        referencia  = self._txt_referencia.text().strip()

        datos_extra = {
            "items":          self._items_asignados,
            "condicion_pago": condicion,
            "metodo_pago":    metodo,
            "monto_pagado":   monto_pagado,
            "monto_total":    monto_total,
            "saldo_pendiente": max(0, monto_total - monto_pagado),
            "sucursal_destino": dest_id,
            "referencia_pago":  referencia,
            "notas":           notas,
        }

        try:
            self.conexion.execute("""
                INSERT INTO trazabilidad_qr
                    (uuid_qr, tipo, sucursal_id, sucursal_destino, estado, datos_extra)
                VALUES(?,?,?,?,'asignado',?)
                ON CONFLICT(uuid_qr) DO UPDATE SET
                    estado='asignado',
                    sucursal_destino=excluded.sucursal_destino,
                    datos_extra=excluded.datos_extra,
                    fecha_generacion=datetime('now')
            """, (uuid_qr, "contenedor", self.sucursal_id, dest_id,
                  json.dumps(datos_extra, ensure_ascii=False)))
            self.conexion.commit()
            QMessageBox.information(self, "Guardado",
                f"Asignación guardada.\nTotal: ${monto_total:.2f} | Pagado: ${monto_pagado:.2f}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_condicion_changed(self, condicion: str) -> None:
        monto_total = sum(i.get("subtotal", 0) for i in self._items_asignados)
        if condicion == "liquidado":
            self._spin_monto_pagado.setValue(monto_total)
        elif condicion == "crédito":
            self._spin_monto_pagado.setValue(0)
        saldo = max(0, monto_total - self._spin_monto_pagado.value())
        self._lbl_saldo.setText(f"Saldo pendiente: ${saldo:.2f}")

    def _agregar_item_asignacion(self) -> None:
        prod_id = getattr(self, '_prod_asignar_id', 0)
        if not prod_id:
            QMessageBox.warning(self, "Aviso", "Selecciona un producto primero.")
            return
        qty   = self._spin_qty_asign.value()
        costo = self._spin_costo_asign.value()
        if qty <= 0:
            QMessageBox.warning(self, "Aviso", "La cantidad debe ser mayor a 0.")
            return
        if costo <= 0:
            QMessageBox.warning(self, "Aviso",
                "El costo unitario debe ser mayor a $0.\n"
                "Ingresa el precio de compra del producto.")
            self._spin_costo_asign.setFocus()
            return
        nombre = (self._lbl_prod_asign_sel.text()
                  if hasattr(self, '_lbl_prod_asign_sel') else "Producto")
        if any(i["product_id"] == prod_id for i in self._items_asignados):
            QMessageBox.warning(self, "Dup.", "Ese producto ya está en la lista."); return
        self._items_asignados.append({
            "product_id":    prod_id,
            "nombre":        nombre,
            "cantidad":      qty,
            "costo_unitario": costo,
            "subtotal":      round(qty * costo, 2),
            "unidad":        "kg",
        })
        self._refrescar_tabla_items_asign()
        # Limpiar selección para siguiente producto
        self._prod_asignar_id = 0
        self._lbl_prod_asign_sel.setText("—")
        self._txt_buscar_prod_asign.clear()
        self._spin_qty_asign.setValue(1)
        self._spin_costo_asign.setValue(0)
        self._txt_buscar_prod_asign.setFocus()

    def _quitar_item_asignacion(self) -> None:
        row = self._tbl_items_asign.currentRow()
        if row >= 0:
            self._items_asignados.pop(row)
            self._refrescar_tabla_items_asign()

    def _refrescar_tabla_items_asign(self) -> None:
        self._tbl_items_asign.setRowCount(len(self._items_asignados))
        for ri, item in enumerate(self._items_asignados):
            for ci, v in enumerate([
                item["nombre"], f"{item['cantidad']:.3f}",
                item["unidad"], f"${item['costo_unitario']:.2f}",
                f"${item['subtotal']:.2f}"
            ]):
                it = QTableWidgetItem(str(v))
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci > 0: it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._tbl_items_asign.setItem(ri, ci, it)
        monto_total = sum(i["subtotal"] for i in self._items_asignados)
        saldo = max(0, monto_total - self._spin_monto_pagado.value())
        self._lbl_saldo.setText(f"Saldo pendiente: ${saldo:.2f}")

    def _buscar_proveedor_asignar(self, texto: str) -> None:
        """Busca proveedores en tiempo real y muestra lista de resultados."""
        self._lst_proveedores.clear()
        if not texto.strip():
            self._lst_proveedores.setVisible(False)
            return
        try:
            rows = self.conexion.execute(
                "SELECT id, nombre, rfc FROM proveedores WHERE activo=1 "
                "AND (nombre LIKE ? OR rfc LIKE ?) ORDER BY nombre LIMIT 8",
                (f"%{texto}%", f"%{texto}%")
            ).fetchall()
            if rows:
                for r in rows:
                    pid  = r['id']    if hasattr(r,'keys') else r[0]
                    name = r['nombre'] if hasattr(r,'keys') else r[1]
                    item = __import__('PyQt5.QtWidgets', fromlist=['QListWidgetItem']).QListWidgetItem(name)
                    item.setData(32, pid)  # Qt.UserRole = 32
                    self._lst_proveedores.addItem(item)
                self._lst_proveedores.setVisible(True)
            else:
                self._lst_proveedores.setVisible(False)
        except Exception as e:
            import logging; logging.getLogger(__name__).debug("_buscar_proveedor_asignar: %s", e)

    def _seleccionar_proveedor_asignar(self, item) -> None:
        """Confirma la selección de proveedor y oculta la lista."""
        self._proveedor_asignar_id = item.data(32)
        self._lbl_proveedor_sel.setText(item.text())
        self._txt_buscar_proveedor.setText(item.text())
        self._lst_proveedores.setVisible(False)

    def _buscar_producto_asignar(self, texto: str) -> None:
        """Busca productos en tiempo real para la asignación."""
        if not hasattr(self, '_lst_prod_asign'):
            return
        self._lst_prod_asign.clear()
        if not texto.strip():
            self._lst_prod_asign.setVisible(False)
            return
        try:
            rows = self.conexion.execute(
                """SELECT id, nombre, COALESCE(codigo,'') as codigo,
                          COALESCE(precio_compra,0) as costo,
                          COALESCE(unidad,'pz') as unidad
                   FROM productos
                   WHERE (nombre LIKE ? OR COALESCE(codigo,'') LIKE ?
                          OR COALESCE(codigo_barras,'') LIKE ?
                          OR CAST(id AS TEXT) = ?)
                     AND COALESCE(oculto,0)=0 AND COALESCE(activo,1)=1
                   ORDER BY nombre LIMIT 10""",
                (f"%{texto}%", f"%{texto}%", f"%{texto}%", texto)
            ).fetchall()
            if rows:
                for r in rows:
                    pid  = r['id']    if hasattr(r,'keys') else r[0]
                    name = r['nombre'] if hasattr(r,'keys') else r[1]
                    costo = float(r['costo'] if hasattr(r,'keys') else r[3])
                    unidad = r['unidad'] if hasattr(r,'keys') else r[4]
                    item = __import__('PyQt5.QtWidgets', fromlist=['QListWidgetItem']).QListWidgetItem(
                        f"{name}  [${costo:.2f}/{unidad}]")
                    item.setData(32, (pid, name, costo, unidad))
                    self._lst_prod_asign.addItem(item)
                self._lst_prod_asign.setVisible(True)
            else:
                self._lst_prod_asign.setVisible(False)
        except Exception as e:
            import logging; logging.getLogger(__name__).debug("_buscar_producto_asignar: %s", e)

    def _seleccionar_producto_asignar(self, item) -> None:
        """Confirma selección de producto y pre-llena el costo."""
        pid, name, costo, unidad = item.data(32)
        self._prod_asignar_id = pid
        self._lbl_prod_asign_sel.setText(name)
        self._txt_buscar_prod_asign.setText(name)
        self._spin_costo_asign.setValue(costo)
        self._lst_prod_asign.setVisible(False)

    def _cargar_proveedores_asignar(self) -> None:
        """No-op: proveedor ahora se selecciona con la barra de búsqueda."""
        pass

    def _cargar_productos_combo(self) -> None:
        """No-op: productos ahora se buscan con la barra de búsqueda."""
        pass
    def _cargar_sucursales_combo_recepcion(self) -> None:
        self._cmb_sucursal_destino.clear()
        try:
            rows = self.conexion.execute(
                "SELECT id, nombre FROM sucursales WHERE activa=1 ORDER BY id"
            ).fetchall()
            for r in rows:
                self._cmb_sucursal_destino.addItem(f"🏪 {r[1]}", r[0])
        except Exception:
            self._cmb_sucursal_destino.addItem("Principal", 1)

    def _cargar_historial_qr(self) -> None:
        """Carga el historial de QR generados para cajas/contenedores."""
        self._tbl_qr_hist.setRowCount(0)
        try:
            rows = self.conexion.execute(
                """SELECT uuid_qr, COALESCE(descripcion,'') as descripcion,
                          COALESCE(tipo,'contenedor') as tipo,
                          COALESCE(sucursal_id,1) as sucursal_id,
                          COALESCE(fecha_creacion, created_at, '') as fecha
                   FROM trazabilidad_qr
                   ORDER BY fecha DESC LIMIT 200"""
            ).fetchall()
        except Exception:
            rows = []
        for i, r in enumerate(rows):
            self._tbl_qr_hist.insertRow(i)
            uuid = str(r[0])
            self._tbl_qr_hist.setItem(i, 0, QTableWidgetItem(uuid[:18] + "…"))
            self._tbl_qr_hist.setItem(i, 1, QTableWidgetItem(str(r[1])))
            self._tbl_qr_hist.setItem(i, 2, QTableWidgetItem(str(r[2])))
            self._tbl_qr_hist.setItem(i, 3, QTableWidgetItem(str(r[3])))
            self._tbl_qr_hist.setItem(i, 4, QTableWidgetItem(str(r[4])[:16]))
            # Reprint button
            btn_reimp = QPushButton("🖨 Reimprimir QR")
            btn_reimp.setObjectName("outlineBtn")
            btn_reimp.clicked.connect(lambda _, u=uuid: self._reimprimir_qr(u))
            self._tbl_qr_hist.setCellWidget(i, 5, btn_reimp)

    def _reimprimir_qr(self, uuid_qr: str) -> None:
        """Regenera e imprime el QR de un contenedor existente."""
        try:
            try:
                import qrcode
                from PyQt5.QtGui import QPixmap, QImage
                from PyQt5.QtCore import QBuffer, QIODevice
                import io
                qr = qrcode.QRCode(box_size=6, border=2)
                qr.add_data(uuid_qr)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buf = io.BytesIO(); img.save(buf, "PNG")
                pix = QPixmap()
                pix.loadFromData(buf.getvalue())
                # Show in a dialog
                dlg = QDialog(self)
                dlg.setWindowTitle(f"QR — {uuid_qr[:8]}…")
                ll = QVBoxLayout(dlg)
                lbl = QLabel(); lbl.setPixmap(pix.scaled(200,200))
                lbl.setAlignment(Qt.AlignCenter)
                ll.addWidget(lbl)
                ll.addWidget(QLabel(f"UUID: {uuid_qr}"))
                btn_print = QPushButton("🖨 Imprimir etiqueta")
                btn_print.setObjectName("outlineBtn")
                btn_print.clicked.connect(dlg.accept)
                ll.addWidget(btn_print)
                dlg.exec_()
            except ImportError:
                QMessageBox.information(self, "QR UUID",
                    f"UUID del contenedor:\n{uuid_qr}\n\n"
                    "Para imprimir instala: pip install qrcode[pil]")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _cargar_historial(self) -> None:
        try:
            rows = self.conexion.execute("""
                SELECT r.folio, r.created_at, p.nombre as proveedor,
                       r.condicion_pago, r.monto_total, r.monto_pagado,
                       r.estado
                FROM recepciones r
                LEFT JOIN proveedores p ON p.id = r.proveedor_id
                WHERE r.sucursal_id = ? AND r.tipo='COMPRA'
                ORDER BY r.created_at DESC LIMIT 100
            """, (self.sucursal_id,)).fetchall()
            self._tbl_hist.setRowCount(len(rows))
            for ri, r in enumerate(rows):
                vals = [
                    str(r[0] or ""), str(r[1] or "")[:16],
                    str(r[2] or "—"), str(r[3] or ""),
                    f"${float(r[4] or 0):.2f}",
                    f"${float(r[5] or 0):.2f}", str(r[6] or "")
                ]
                for ci, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self._tbl_hist.setItem(ri, ci, it)
        except Exception as e:
            logger.warning("_cargar_historial: %s", e)

    def _limpiar_tab_recepcion(self) -> None:
        self._txt_uuid_recv.clear()
        self._lbl_recv_info.setText("Sin contenedor cargado")
        self._tbl_recv.setRowCount(0)
        self._txt_recv_notas.clear()
        self._contenedor_activo = None
