
# modulos/recepcion_qr_widget.py — SPJ POS v13.4
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
from modulos.design_tokens import Colors
from modulos.spj_styles import apply_object_names
from modulos.ui_components import (
    create_primary_button, create_success_button, create_secondary_button,
    create_danger_button, Toast, create_badge,
)
import logging, uuid, json
from typing import Dict, List, Optional
from PyQt5.QtWidgets import (
    QListWidget, QListWidgetItem,
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QMessageBox,
    QDialog, QTabWidget, QTextEdit, QFrame, QSizePolicy, QSpinBox,
    QCheckBox, QDateEdit, QFileDialog,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QDate
from PyQt5.QtGui import QColor, QFont

logger = logging.getLogger("spj.ui.recepcion_qr")

_C_GRIS = Colors.NEUTRAL.SLATE_500  # muted text


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
        self._tipo_contenedor: str = "Caja"
        self._tipo_btns: list = []
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
        info.setObjectName("caption")
        lay.addWidget(info)

        # ── Selector de tipo de contenedor ────────────────────────────────────
        tipo_lbl = QLabel("Tipo de contenedor:")
        tipo_lbl.setStyleSheet("font-weight:bold; font-size:12px;")
        lay.addWidget(tipo_lbl)

        tipos_row = QHBoxLayout()
        tipos_row.setSpacing(4)
        _TIPOS = [
            ("📦", "Caja"),
            ("🪨", "Pallet"),
            ("💰", "Saco"),
            ("🧊", "Hielera"),
            ("🗂", "Jaula"),
            ("🪣", "Cubeta"),
            ("❄️", "Refrigerador"),
            ("✏️", "Otro"),
        ]
        self._tipo_btns = []
        for icon, nombre in _TIPOS:
            btn = QPushButton(f"{icon} {nombre}")
            btn.setFixedSize(54, 38)
            btn.setFlat(True)
            btn.setProperty("tipo_nombre", nombre)
            btn.clicked.connect(lambda _checked, n=nombre: self._seleccionar_tipo_contenedor(n))
            self._tipo_btns.append(btn)
            tipos_row.addWidget(btn)
        tipos_row.addStretch()
        lay.addLayout(tipos_row)
        # Apply initial selection style
        self._seleccionar_tipo_contenedor(self._tipo_contenedor)

        # ── Formulario ────────────────────────────────────────────────────────
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
            "border:2px dashed rgba(0,0,0,0.18);"
            "background:rgba(0,0,0,0.02);"
            "color:rgba(0,0,0,0.38);"
            "font-size:13px;"
        )
        lay.addWidget(self._lbl_qr_preview)

        btns = QHBoxLayout()
        btn_generar  = create_primary_button(self, "🏷️ Generar y Ver QR",
                                             "Generar código QR para el contenedor")
        btn_imprimir = create_success_button(self, "🖨️ Imprimir Etiqueta",
                                             "Imprimir etiqueta del último QR generado")
        btn_generar.clicked.connect(self._generar_qr_contenedor)
        btn_imprimir.clicked.connect(self._imprimir_etiqueta_qr)
        btns.addStretch(); btns.addWidget(btn_generar); btns.addWidget(btn_imprimir)
        lay.addLayout(btns)
        lay.addStretch()

    # ── Pestaña 2: Asignar Compra ─────────────────────────────────────────────

    def _build_tab_asignar(self) -> None:
        root_lay = QHBoxLayout(self._tab_asignar)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # ── Left sidebar: contenedores disponibles ────────────────────────────
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(
            f"QFrame {{ background:{Colors.NEUTRAL.SLATE_50};"
            f"border-right:1px solid {Colors.NEUTRAL.SLATE_300}; }}"
        )
        sb_lay = QVBoxLayout(sidebar)
        sb_lay.setContentsMargins(6, 8, 6, 8)
        sb_lay.setSpacing(4)

        sb_title = QLabel("📦 Contenedores")
        sb_title.setStyleSheet("font-weight:bold; font-size:12px; padding:2px 0;")
        sb_lay.addWidget(sb_title)

        self._txt_buscar_sidebar = QLineEdit()
        self._txt_buscar_sidebar.setPlaceholderText("🔍 Buscar…")
        self._txt_buscar_sidebar.setMinimumHeight(28)
        self._txt_buscar_sidebar.textChanged.connect(self._filtrar_cont_sidebar)
        sb_lay.addWidget(self._txt_buscar_sidebar)

        self._lst_cont_sidebar = QListWidget()
        self._lst_cont_sidebar.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._lst_cont_sidebar.itemDoubleClicked.connect(self._seleccionar_cont_sidebar)
        sb_lay.addWidget(self._lst_cont_sidebar, 1)

        btn_ref_sidebar = create_secondary_button(self, "🔄 Actualizar", "Actualizar lista de contenedores")
        btn_ref_sidebar.clicked.connect(self._poblar_contenedores_sidebar)
        sb_lay.addWidget(btn_ref_sidebar)

        root_lay.addWidget(sidebar)

        # ── Right: existing steps content ─────────────────────────────────────
        right_widget = QWidget()
        lay = QVBoxLayout(right_widget)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        root_lay.addWidget(right_widget, 1)

        # ── Step 1: Escanear contenedor ───────────────────────────────────────
        step1 = QGroupBox("① Escanear contenedor QR")
        s1 = QHBoxLayout(step1); s1.setContentsMargins(8, 6, 8, 6)
        self._txt_uuid_asignar = QLineEdit()
        self._txt_uuid_asignar.setPlaceholderText("Escanea el QR o escribe el UUID…")
        self._txt_uuid_asignar.setMinimumHeight(32)
        self._txt_uuid_asignar.returnPressed.connect(self._cargar_contenedor)
        btn_cargar = create_primary_button(self, "🔍 Cargar", "Cargar datos del contenedor QR")
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
        self._timer_buscar_prov = QTimer(); self._timer_buscar_prov.setSingleShot(True)
        self._timer_buscar_prov.timeout.connect(
            lambda: self._buscar_proveedor_asignar(self._txt_buscar_proveedor.text())
        )
        self._txt_buscar_proveedor.textChanged.connect(
            lambda: self._timer_buscar_prov.start(300)
        )
        self._lbl_proveedor_sel = QLabel("Ninguno")
        self._lbl_proveedor_sel.setStyleSheet(
            f"color:{Colors.PRIMARY_BASE};font-weight:bold;padding:4px 10px;"
            "border-radius:4px;border:1px solid rgba(0,0,0,0.2);min-width:120px;")
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
        self._timer_buscar_prod = QTimer(); self._timer_buscar_prod.setSingleShot(True)
        self._timer_buscar_prod.timeout.connect(
            lambda: self._buscar_producto_asignar(self._txt_buscar_prod_asign.text())
        )
        self._txt_buscar_prod_asign.textChanged.connect(
            lambda: self._timer_buscar_prod.start(300)
        )
        self._lbl_prod_asign_sel = QLabel("")
        self._lbl_prod_asign_sel.setStyleSheet(f"color:{Colors.PRIMARY_BASE};font-size:11px;")
        self._prod_asignar_id = 0

        self._spin_qty_asign = QDoubleSpinBox()
        self._spin_qty_asign.setRange(0.001, 99999); self._spin_qty_asign.setDecimals(3)
        self._spin_qty_asign.setPrefix("Cant: "); self._spin_qty_asign.setMinimumHeight(30)
        self._spin_qty_asign.setFixedWidth(110)

        self._spin_costo_asign = QDoubleSpinBox()
        self._spin_costo_asign.setRange(0, 999999); self._spin_costo_asign.setDecimals(2)
        self._spin_costo_asign.setPrefix("$ "); self._spin_costo_asign.setMinimumHeight(30)
        self._spin_costo_asign.setFixedWidth(110)

        btn_add_item = create_success_button(self, "➕", "Agregar producto al contenedor")
        btn_add_item.setFixedSize(36, 30)
        btn_add_item.clicked.connect(self._agregar_item_asignacion)

        btn_rm_item = create_danger_button(self, "🗑", "Quitar producto seleccionado")
        btn_rm_item.setFixedSize(36, 30)
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
        self._lbl_saldo.setStyleSheet(f"color:{Colors.DANGER_BASE};font-weight:bold;")
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
        btn_guardar_asig = create_success_button(self, "💾 Guardar asignación",
                                                 "Guardar asignación de productos al contenedor QR")
        btn_guardar_asig.setMinimumHeight(38)
        btn_guardar_asig.clicked.connect(self._guardar_asignacion)
        lay.addWidget(btn_guardar_asig)

        # Populate sidebar now that all widgets are built
        self._poblar_contenedores_sidebar()

    # ── Pestaña 3: Recepcionar ─────────────────────────────────────────────────

    def _build_tab_recepcionar(self) -> None:
        outer = QHBoxLayout(self._tab_recepcionar)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── LEFT: Pending queue (180px) ───────────────────────────────────────
        left = QFrame()
        left.setFixedWidth(180)
        left.setStyleSheet(
            f"QFrame{{background:{Colors.NEUTRAL.SLATE_50};"
            f"border-right:1px solid {Colors.NEUTRAL.SLATE_200};}}"
        )
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(6, 8, 6, 8)
        left_lay.setSpacing(4)
        self._lbl_pending_count = QLabel("Pendientes de recepción")
        self._lbl_pending_count.setStyleSheet(
            f"font-weight:700;font-size:11px;color:{Colors.NEUTRAL.SLATE_700};"
        )
        left_lay.addWidget(self._lbl_pending_count)
        self._lst_pending_recv = QListWidget()
        self._lst_pending_recv.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._lst_pending_recv.itemDoubleClicked.connect(self._seleccionar_pendiente_recv)
        left_lay.addWidget(self._lst_pending_recv, 1)
        btn_ref_pend = create_secondary_button(self, "🔄", "Actualizar pendientes")
        btn_ref_pend.setMaximumWidth(36)
        btn_ref_pend.clicked.connect(self._cargar_pendientes_recepcion)
        left_lay.addWidget(btn_ref_pend)
        outer.addWidget(left)

        # ── CENTER: scan + table + incidencias + peso + buttons ───────────────
        center = QWidget()
        lay = QVBoxLayout(center)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        outer.addWidget(center, 1)

        # Caption
        info_lbl = QLabel("Escanea el QR del contenedor al recibirlo en sucursal. Confirma o ajusta cantidades reales.")
        info_lbl.setWordWrap(True)
        info_lbl.setObjectName("caption")
        lay.addWidget(info_lbl)

        # Scan group
        scan_grp = QGroupBox("① Escanear QR del contenedor recibido")
        scan_lay = QHBoxLayout(scan_grp)
        self._txt_uuid_recv = QLineEdit()
        self._txt_uuid_recv.setPlaceholderText("Escanea el QR con el lector HID…")
        self._txt_uuid_recv.returnPressed.connect(self._cargar_para_recepcion)
        btn_recv_cargar = create_primary_button(self, "🔍 Cargar", "Cargar contenedor QR para recepción")
        btn_recv_cargar.clicked.connect(self._cargar_para_recepcion)
        scan_lay.addWidget(self._txt_uuid_recv); scan_lay.addWidget(btn_recv_cargar)
        lay.addWidget(scan_grp)

        self._lbl_recv_info = QLabel("Sin contenedor cargado")
        self._lbl_recv_info.setStyleSheet(f"color:{Colors.NEUTRAL.SLATE_500}; padding:4px;")
        lay.addWidget(self._lbl_recv_info)

        # Comparison table (8 columns)
        self._tbl_recv = QTableWidget()
        self._tbl_recv.setColumnCount(8)
        self._tbl_recv.setHorizontalHeaderLabels(
            ["ID", "Producto", "Unidad", "Esperado", "Recibido Real", "Diferencia", "Lote/Caducidad", "Estado"]
        )
        self._tbl_recv.verticalHeader().setVisible(False)
        self._tbl_recv.setAlternatingRowColors(True)
        self._tbl_recv.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hdr = self._tbl_recv.horizontalHeader()
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)   # Producto stretches
        for i in (0, 2, 3, 4, 5, 6, 7):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        lay.addWidget(self._tbl_recv)

        # Diff summary label
        self._lbl_recv_diff = QLabel("Diferencia total: 0.000")
        self._lbl_recv_diff.setStyleSheet(f"font-weight:bold;font-size:13px;color:{Colors.NEUTRAL.SLATE_600};")
        lay.addWidget(self._lbl_recv_diff)

        # Incidencias section
        inc_grp = QGroupBox("🚨 Incidencias")
        inc_lay = QVBoxLayout(inc_grp)
        self._chk_incidencia = QCheckBox("¿Hay incidencias o diferencias?")
        self._chk_incidencia.toggled.connect(self._toggle_incidencia_panel)
        inc_lay.addWidget(self._chk_incidencia)
        self._inc_panel = QWidget()
        self._inc_panel.setVisible(False)
        inc_form = QFormLayout(self._inc_panel)
        inc_form.setSpacing(4)
        self._cmb_tipo_incidencia = QComboBox()
        self._cmb_tipo_incidencia.addItems([
            "Diferencia de peso", "Producto dañado", "Producto incorrecto",
            "Faltante", "Excedente", "Otro"
        ])
        self._txt_desc_incidencia = QLineEdit()
        self._txt_desc_incidencia.setPlaceholderText("Descripción de la incidencia…")
        self._cmb_accion_incidencia = QComboBox()
        self._cmb_accion_incidencia.addItems([
            "Aceptar con nota", "Rechazar", "Ajuste por merma",
            "Devolver al proveedor", "Requiere revisión"
        ])
        inc_form.addRow("Tipo:", self._cmb_tipo_incidencia)
        inc_form.addRow("Descripción:", self._txt_desc_incidencia)
        inc_form.addRow("Acción:", self._cmb_accion_incidencia)
        inc_lay.addWidget(self._inc_panel)
        lay.addWidget(inc_grp)

        # Peso de recepción section
        peso_grp = QGroupBox("⚖ Peso de recepción")
        peso_form = QFormLayout(peso_grp)
        peso_form.setSpacing(4)
        self._spin_peso_bruto = QDoubleSpinBox()
        self._spin_peso_bruto.setRange(0, 99999); self._spin_peso_bruto.setDecimals(3)
        self._spin_peso_bruto.setSuffix(" kg"); self._spin_peso_bruto.valueChanged.connect(self._actualizar_pesos_recepcion)
        self._spin_peso_tara = QDoubleSpinBox()
        self._spin_peso_tara.setRange(0, 99999); self._spin_peso_tara.setDecimals(3)
        self._spin_peso_tara.setSuffix(" kg"); self._spin_peso_tara.valueChanged.connect(self._actualizar_pesos_recepcion)
        self._lbl_peso_dif = QLabel("Diferencia: — kg")
        self._lbl_peso_dif.setObjectName("caption")
        self._lbl_peso_neto = QLabel("Peso neto: — kg")
        self._lbl_peso_neto.setStyleSheet(f"font-weight:700;color:{Colors.SUCCESS_BASE};")
        peso_form.addRow("Peso bruto (kg):", self._spin_peso_bruto)
        peso_form.addRow("Peso tara (kg):", self._spin_peso_tara)
        peso_form.addRow("", self._lbl_peso_dif)
        peso_form.addRow("", self._lbl_peso_neto)
        lay.addWidget(peso_grp)

        # Notes
        self._txt_recv_notas = QTextEdit()
        self._txt_recv_notas.setMaximumHeight(40)
        self._txt_recv_notas.setPlaceholderText("Observaciones de recepción, daños, faltantes…")
        lay.addWidget(self._txt_recv_notas)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_parcial = create_secondary_button(self, "⚠ Marcar parcial", "Registrar recepción parcial del contenedor")
        btn_parcial.clicked.connect(self._marcar_recepcion_parcial)
        btn_incid = create_danger_button(self, "🚨 Marcar incidencias", "Registrar incidencias de recepción")
        btn_incid.clicked.connect(self._marcar_incidencias)
        btn_aceptar_todo = create_success_button(self, "✅ Aceptar todo", "Igualar recibido a esperado")
        btn_aceptar_todo.clicked.connect(self._aceptar_todo_recepcion)
        btn_confirmar_recv = create_success_button(
            self, "✅ Confirmar Recepción", "Confirmar recepción e ingresar al inventario")
        btn_confirmar_recv.setMinimumHeight(38)
        btn_confirmar_recv.clicked.connect(self._confirmar_recepcion)
        btn_row.addWidget(btn_aceptar_todo)
        btn_row.addWidget(btn_parcial)
        btn_row.addWidget(btn_incid)
        btn_row.addStretch()
        btn_row.addWidget(btn_confirmar_recv)
        lay.addLayout(btn_row)

        # ── RIGHT: summary panel (185px, already built) ───────────────────────
        outer.addWidget(self._build_recv_summary_panel())

        # Load pending containers
        self._cargar_pendientes_recepcion()

    # ── Pestaña 4: Historial ──────────────────────────────────────────────────

    def _build_tab_historial(self) -> None:
        lay = QVBoxLayout(self._tab_historial)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # ── Filter bar ────────────────────────────────────────────────────────
        flt = QHBoxLayout()
        _today = QDate.currentDate()
        self._qr_hist_desde = QDateEdit(QDate(_today.year(), _today.month(), 1))
        self._qr_hist_desde.setCalendarPopup(True); self._qr_hist_desde.setDisplayFormat("dd/MM/yyyy")
        self._qr_hist_hasta = QDateEdit(_today)
        self._qr_hist_hasta.setCalendarPopup(True); self._qr_hist_hasta.setDisplayFormat("dd/MM/yyyy")
        self._cmb_qr_tipo = QComboBox()
        self._cmb_qr_tipo.addItems(["Todos", "Caja", "Pallet", "Saco", "Hielera", "Jaula", "Cubeta", "Refrigerador", "Otro"])
        self._cmb_qr_prov = QComboBox()
        self._cmb_qr_prov.addItem("Todos proveedores", None)
        self._txt_qr_buscar = QLineEdit()
        self._txt_qr_buscar.setPlaceholderText("Buscar contenedor…")
        self._txt_qr_buscar.setMinimumWidth(160)
        btn_buscar_qr = create_primary_button(self, "🔍 Buscar", "Buscar en historial QR")
        btn_buscar_qr.clicked.connect(self._cargar_historial_qr)
        btn_exp_qr = create_secondary_button(self, "⬇ Exportar CSV", "Exportar historial QR a CSV")
        btn_exp_qr.clicked.connect(self._exportar_historial_qr_csv)
        flt.addWidget(QLabel("Desde:")); flt.addWidget(self._qr_hist_desde)
        flt.addWidget(QLabel("Hasta:")); flt.addWidget(self._qr_hist_hasta)
        flt.addWidget(QLabel("Tipo:")); flt.addWidget(self._cmb_qr_tipo)
        flt.addWidget(QLabel("Proveedor:")); flt.addWidget(self._cmb_qr_prov)
        flt.addWidget(self._txt_qr_buscar)
        flt.addWidget(btn_buscar_qr); flt.addWidget(btn_exp_qr)
        lay.addLayout(flt)

        # ── Main QR history table (10 cols) ───────────────────────────────────
        self._tbl_qr_hist = QTableWidget()
        self._tbl_qr_hist.setColumnCount(10)
        self._tbl_qr_hist.setHorizontalHeaderLabels([
            "Contenedor", "Tipo", "Proveedor", "Factura", "Sucursal destino",
            "Estado", "Peso est.(kg)", "Peso rec.(kg)", "Total($)", "Fecha recepción"
        ])
        self._tbl_qr_hist.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tbl_qr_hist.setSelectionBehavior(QTableWidget.SelectRows)
        self._tbl_qr_hist.setAlternatingRowColors(True)
        self._tbl_qr_hist.verticalHeader().setVisible(False)
        hh = self._tbl_qr_hist.horizontalHeader()
        hh.setSectionResizeMode(2, QHeaderView.Stretch)  # Proveedor stretches
        for c in (0, 1, 3, 4, 5, 6, 7, 8, 9):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._tbl_qr_hist.itemSelectionChanged.connect(self._on_qr_hist_row_selected)
        lay.addWidget(self._tbl_qr_hist, 2)

        # Recepciones table (kept for _cargar_historial compatibility)
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
        self._tbl_hist.setObjectName("tableView")
        self._tbl_hist.setVisible(False)  # hidden but kept for _cargar_historial()
        hdr_h = self._tbl_hist.horizontalHeader()
        hdr_h.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr_h.setSectionResizeMode(6, QHeaderView.Fixed)
        self._tbl_hist.setColumnWidth(6, 110)
        for c in (0, 1, 3, 4, 5):
            hdr_h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        lay.addWidget(self._tbl_hist)

        # ── Detail panel (hidden until row selected) ──────────────────────────
        self._qr_detail_panel = QGroupBox("Detalle del contenedor")
        self._qr_detail_panel.setVisible(False)
        det_lay = QHBoxLayout(self._qr_detail_panel)

        # Left: container info
        self._lbl_qr_detail_info = QLabel("—")
        self._lbl_qr_detail_info.setWordWrap(True)
        self._lbl_qr_detail_info.setObjectName("caption")
        det_lay.addWidget(self._lbl_qr_detail_info)

        # Center: traceability timeline
        timeline_grp = QGroupBox("📍 Timeline de trazabilidad")
        tl_lay = QVBoxLayout(timeline_grp)
        self._tbl_timeline = QTableWidget()
        self._tbl_timeline.setColumnCount(3)
        self._tbl_timeline.setHorizontalHeaderLabels(["Fecha", "Evento", "Usuario"])
        self._tbl_timeline.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tbl_timeline.verticalHeader().setVisible(False)
        self._tbl_timeline.setMaximumHeight(120)
        th = self._tbl_timeline.horizontalHeader()
        th.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (0, 2): th.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        tl_lay.addWidget(self._tbl_timeline)
        det_lay.addWidget(timeline_grp, 2)

        # Right: documents placeholder
        docs_grp = QGroupBox("📄 Documentos")
        docs_lay = QVBoxLayout(docs_grp)
        self._lst_qr_docs = QListWidget()
        self._lst_qr_docs.setMaximumHeight(100)
        docs_lay.addWidget(self._lst_qr_docs)
        det_lay.addWidget(docs_grp)

        lay.addWidget(self._qr_detail_panel)

        self._cargar_historial_qr()
        self._cargar_historial()
        self._cargar_proveedores_qr_hist()
        apply_object_names(self)

    # ── Nuevos helpers UI ─────────────────────────────────────────────────────

    def _seleccionar_tipo_contenedor(self, tipo: str) -> None:
        self._tipo_contenedor = tipo
        for btn in self._tipo_btns:
            is_sel = btn.property("tipo_nombre") == tipo
            btn.setStyleSheet(
                f"background:{Colors.PRIMARY_BASE};color:white;border-radius:6px;font-weight:bold;"
                if is_sel else
                f"background:transparent;border:1px solid {Colors.NEUTRAL.SLATE_300};"
                f"border-radius:6px;color:{Colors.NEUTRAL.SLATE_600};"
            )

    def _poblar_contenedores_sidebar(self) -> None:
        """Load containers with estado='disponible' or 'generado' from trazabilidad_qr or contenedores_qr."""
        self._lst_cont_sidebar.clear()
        try:
            rows = self.conexion.execute("""
                SELECT c.uuid_qr,
                       COALESCE(c.codigo_interno, '') as codigo,
                       COALESCE(c.descripcion, '') as desc,
                       COALESCE(t.estado, 'disponible') as estado
                FROM contenedores_qr c
                LEFT JOIN trazabilidad_qr t ON t.uuid_qr = c.uuid_qr
                WHERE COALESCE(t.estado, 'disponible') IN ('disponible','generado')
                ORDER BY c.created_at DESC LIMIT 100
            """).fetchall()
            if not rows:
                it = QListWidgetItem("Sin contenedores disponibles")
                it.setFlags(Qt.NoItemFlags)
                self._lst_cont_sidebar.addItem(it)
                return
            for r in rows:
                uuid_qr, codigo, desc, estado = r[0], r[1], r[2], r[3]
                label = f"{codigo or uuid_qr[:12]+'…'}"
                if desc:
                    label += f"\n{desc[:28]}"
                it = QListWidgetItem(label)
                it.setData(Qt.UserRole, uuid_qr)
                estado_icon = "🟢" if estado == "disponible" else "🔵"
                it.setToolTip(f"{estado_icon} {estado.upper()} | {uuid_qr}")
                self._lst_cont_sidebar.addItem(it)
        except Exception as exc:
            logger.warning("sidebar: %s", exc)
            it = QListWidgetItem("—")
            it.setFlags(Qt.NoItemFlags)
            self._lst_cont_sidebar.addItem(it)

    def _filtrar_cont_sidebar(self, text: str) -> None:
        for i in range(self._lst_cont_sidebar.count()):
            item = self._lst_cont_sidebar.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def _seleccionar_cont_sidebar(self, item: "QListWidgetItem") -> None:
        uuid_qr = item.data(Qt.UserRole)
        if uuid_qr:
            self._txt_uuid_asignar.setText(uuid_qr)
            self._cargar_contenedor()

    def _build_recv_summary_panel(self) -> QFrame:
        """Builds the 185px right summary panel for the recepcionar tab."""
        panel = QFrame()
        panel.setFixedWidth(185)
        panel.setStyleSheet(
            f"QFrame {{ background:{Colors.NEUTRAL.SLATE_50};"
            f"border-left:1px solid {Colors.NEUTRAL.SLATE_300}; }}"
        )
        p_lay = QVBoxLayout(panel)
        p_lay.setContentsMargins(8, 10, 8, 8)
        p_lay.setSpacing(6)

        # Resumen section
        sec_resumen = QLabel("📊 RESUMEN")
        sec_resumen.setStyleSheet(
            f"font-weight:bold;font-size:11px;color:{Colors.NEUTRAL.SLATE_600};"
            "padding:2px 0;letter-spacing:0.5px;"
        )
        p_lay.addWidget(sec_resumen)

        self._sum_recv_esperado = QLabel("Esp: —")
        self._sum_recv_recibido = QLabel("Rec: —")
        self._sum_recv_diff_lbl = QLabel("Dif: —")
        self._sum_recv_pct      = QLabel("Avance: —")
        for lbl in (self._sum_recv_esperado, self._sum_recv_recibido,
                    self._sum_recv_diff_lbl, self._sum_recv_pct):
            lbl.setStyleSheet("font-size:12px; padding:1px 2px;")
            lbl.setWordWrap(True)
            p_lay.addWidget(lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{Colors.NEUTRAL.SLATE_300};")
        p_lay.addWidget(sep)

        # Discrepancias section
        sec_disc = QLabel("⚠ DISCREPANCIAS")
        sec_disc.setStyleSheet(
            f"font-weight:bold;font-size:11px;color:{Colors.NEUTRAL.SLATE_600};"
            "padding:2px 0;letter-spacing:0.5px;"
        )
        p_lay.addWidget(sec_disc)

        self._lst_recv_discrepancias = QListWidget()
        self._lst_recv_discrepancias.setMaximumHeight(120)
        self._lst_recv_discrepancias.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._lst_recv_discrepancias.setStyleSheet("font-size:11px;")
        p_lay.addWidget(self._lst_recv_discrepancias)

        p_lay.addStretch()
        return panel

    def _actualizar_resumen_recepcion(self) -> None:
        """Reads all rows from _tbl_recv and updates the summary panel."""
        total_esp  = 0.0
        total_recv = 0.0
        self._lst_recv_discrepancias.clear()
        for ri in range(self._tbl_recv.rowCount()):
            spin = self._tbl_recv.cellWidget(ri, 4)
            if not spin:
                continue
            qty_esp  = float(spin.property("qty_esperada") or 0)
            qty_recv = spin.value()
            total_esp  += qty_esp
            total_recv += qty_recv
            diff = qty_recv - qty_esp
            if abs(diff) > 0.001:
                prod_item = self._tbl_recv.item(ri, 1)
                prod_name = prod_item.text() if prod_item else f"Fila {ri+1}"
                it = QListWidgetItem(f"{prod_name[:20]}: {diff:+.3f}")
                color = Colors.DANGER_BASE if diff < 0 else Colors.SUCCESS_BASE
                it.setForeground(QColor(color))
                self._lst_recv_discrepancias.addItem(it)
        total_diff = total_recv - total_esp
        pct = (total_recv / total_esp * 100) if total_esp > 0 else 0.0
        self._sum_recv_esperado.setText(f"Esp: {total_esp:.3f}")
        self._sum_recv_recibido.setText(f"Rec: {total_recv:.3f}")
        diff_color = Colors.DANGER_BASE if total_diff < -0.001 else (
            Colors.SUCCESS_BASE if total_diff > 0.001 else Colors.NEUTRAL.SLATE_700
        )
        self._sum_recv_diff_lbl.setText(f"Dif: {total_diff:+.3f}")
        self._sum_recv_diff_lbl.setStyleSheet(
            f"font-size:12px;padding:1px 2px;color:{diff_color};font-weight:bold;"
        )
        self._sum_recv_pct.setText(f"Avance: {pct:.1f}%")
        if not self._lst_recv_discrepancias.count():
            it = QListWidgetItem("✅ Sin discrepancias")
            it.setForeground(QColor(Colors.SUCCESS_BASE))
            self._lst_recv_discrepancias.addItem(it)

    # ── Helpers UI — Tab 2.3 (Recepcionar) ───────────────────────────────────

    def _cargar_pendientes_recepcion(self) -> None:
        """Load containers with estado='asignado' or 'en_transito' into the pending queue."""
        if not hasattr(self, '_lst_pending_recv'):
            return
        self._lst_pending_recv.clear()
        try:
            rows = self.conexion.execute("""
                SELECT t.uuid_qr,
                       COALESCE(c.codigo_interno, t.uuid_qr) AS codigo,
                       t.estado,
                       COALESCE(p.nombre, '—') AS proveedor
                FROM trazabilidad_qr t
                LEFT JOIN contenedores_qr c ON c.uuid_qr = t.uuid_qr
                LEFT JOIN proveedores p ON p.id = (
                    SELECT json_extract(t2.datos_extra,'$.proveedor_id')
                    FROM trazabilidad_qr t2 WHERE t2.uuid_qr = t.uuid_qr LIMIT 1
                )
                WHERE t.estado IN ('asignado','en_transito','enviado')
                ORDER BY t.fecha_generacion DESC LIMIT 50
            """).fetchall()
        except Exception:
            rows = []
        count = len(rows)
        if hasattr(self, '_lbl_pending_count'):
            self._lbl_pending_count.setText(f"Pendientes de recepción: {count}")
        if not rows:
            it = QListWidgetItem("Sin pendientes")
            it.setFlags(Qt.NoItemFlags)
            self._lst_pending_recv.addItem(it)
            return
        _ESTADO_ICON = {"asignado": "🔵", "en_transito": "🟡", "enviado": "🟠"}
        for r in rows:
            uuid_qr, codigo, estado, proveedor = r[0], r[1], r[2], r[3]
            icon = _ESTADO_ICON.get(estado, "⚪")
            it = QListWidgetItem(f"{icon} {codigo}\n{proveedor[:22]}")
            it.setData(Qt.UserRole, uuid_qr)
            it.setToolTip(f"{uuid_qr}\nEstado: {estado}\nProveedor: {proveedor}")
            self._lst_pending_recv.addItem(it)

    def _seleccionar_pendiente_recv(self, item: "QListWidgetItem") -> None:
        uuid_qr = item.data(Qt.UserRole)
        if uuid_qr and hasattr(self, '_txt_uuid_recv'):
            self._txt_uuid_recv.setText(uuid_qr)
            self._cargar_para_recepcion()

    def _toggle_incidencia_panel(self, checked: bool) -> None:
        if hasattr(self, '_inc_panel'):
            self._inc_panel.setVisible(checked)

    def _actualizar_pesos_recepcion(self, _=None) -> None:
        if not hasattr(self, '_spin_peso_bruto'):
            return
        bruto = self._spin_peso_bruto.value()
        tara  = self._spin_peso_tara.value()
        neto  = max(0.0, bruto - tara)
        dif   = bruto - tara
        if hasattr(self, '_lbl_peso_dif'):
            self._lbl_peso_dif.setText(f"Diferencia: {dif:+.3f} kg")
        if hasattr(self, '_lbl_peso_neto'):
            self._lbl_peso_neto.setText(f"Peso neto: {neto:.3f} kg")

    def _marcar_recepcion_parcial(self) -> None:
        if not self._contenedor_activo:
            QMessageBox.warning(self, "Aviso", "Carga un contenedor primero."); return
        resp = QMessageBox.question(
            self, "Recepción parcial",
            "¿Confirmar como recepción PARCIAL?\n"
            "El contenedor quedará en estado 'recepción parcial' y se podrá completar después.",
            QMessageBox.Yes | QMessageBox.No
        )
        if resp != QMessageBox.Yes:
            return
        try:
            uuid_qr = self._contenedor_activo.get("uuid_qr", "")
            self.conexion.execute(
                "UPDATE trazabilidad_qr SET estado='recepcion_parcial' WHERE uuid_qr=?",
                (uuid_qr,)
            )
            self.conexion.commit()
            Toast.success(self, "⚠ Recepción parcial registrada", f"QR: {uuid_qr}")
            self._cargar_pendientes_recepcion()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _marcar_incidencias(self) -> None:
        if not self._contenedor_activo:
            QMessageBox.warning(self, "Aviso", "Carga un contenedor primero."); return
        if not (hasattr(self, '_chk_incidencia') and self._chk_incidencia.isChecked()):
            QMessageBox.information(self, "Aviso", "Marca el checkbox de incidencias primero."); return
        tipo = self._cmb_tipo_incidencia.currentText() if hasattr(self, '_cmb_tipo_incidencia') else "—"
        desc = self._txt_desc_incidencia.text().strip() if hasattr(self, '_txt_desc_incidencia') else ""
        accion = self._cmb_accion_incidencia.currentText() if hasattr(self, '_cmb_accion_incidencia') else "—"
        try:
            uuid_qr = self._contenedor_activo.get("uuid_qr", "")
            import json as _json
            nota = _json.dumps({"tipo": tipo, "descripcion": desc, "accion": accion}, ensure_ascii=False)
            self.conexion.execute(
                "UPDATE trazabilidad_qr SET estado='incidencia', datos_extra=json_patch(COALESCE(datos_extra,'{}'), ?) WHERE uuid_qr=?",
                (f'{{"incidencia":{nota}}}', uuid_qr)
            )
            self.conexion.commit()
            Toast.success(self, "🚨 Incidencia registrada", f"{tipo}: {desc[:40]}")
            self._cargar_pendientes_recepcion()
        except Exception as e:
            logger.warning("_marcar_incidencias: %s", e)
            QMessageBox.critical(self, "Error", str(e))

    # ── Helpers UI — Tab 2.4 (Histórico QR) ──────────────────────────────────

    def _cargar_proveedores_qr_hist(self) -> None:
        if not hasattr(self, '_cmb_qr_prov'): return
        try:
            rows = self.conexion.execute(
                "SELECT id, nombre FROM proveedores WHERE activo=1 ORDER BY nombre LIMIT 200"
            ).fetchall()
            for r in rows:
                self._cmb_qr_prov.addItem(r[1], r[0])
        except Exception:
            pass

    def _cargar_historial_qr(self) -> None:
        if not hasattr(self, '_tbl_qr_hist'): return
        self._tbl_qr_hist.setRowCount(0)
        try:
            desde = self._qr_hist_desde.date().toString("yyyy-MM-dd") if hasattr(self, '_qr_hist_desde') else "2000-01-01"
            hasta = self._qr_hist_hasta.date().toString("yyyy-MM-dd") if hasattr(self, '_qr_hist_hasta') else "2099-12-31"
            buscar = self._txt_qr_buscar.text().strip() if hasattr(self, '_txt_qr_buscar') else ""
            rows = self.conexion.execute("""
                SELECT COALESCE(c.codigo_interno, t.uuid_qr) AS contenedor,
                       COALESCE(json_extract(t.datos_extra,'$.tipo_contenedor'), 'Caja') AS tipo,
                       COALESCE(p.nombre,'—') AS proveedor,
                       COALESCE(json_extract(t.datos_extra,'$.factura'),'—') AS factura,
                       COALESCE(s.nombre,'—') AS sucursal_destino,
                       COALESCE(t.estado,'—') AS estado,
                       COALESCE(CAST(json_extract(t.datos_extra,'$.peso_estimado') AS REAL),0) AS peso_est,
                       COALESCE(r.peso_total_kg,0) AS peso_rec,
                       COALESCE(CAST(json_extract(t.datos_extra,'$.monto_total') AS REAL),0) AS total,
                       COALESCE(r.created_at,'—') AS fecha_recepcion,
                       t.uuid_qr
                FROM trazabilidad_qr t
                LEFT JOIN contenedores_qr c ON c.uuid_qr = t.uuid_qr
                LEFT JOIN proveedores p ON p.id = CAST(json_extract(t.datos_extra,'$.proveedor_id') AS INTEGER)
                LEFT JOIN sucursales s ON s.id = t.sucursal_destino
                LEFT JOIN recepciones r ON r.uuid_qr = t.uuid_qr AND r.estado='completada'
                WHERE DATE(COALESCE(r.created_at, t.fecha_generacion)) BETWEEN ? AND ?
                ORDER BY COALESCE(r.created_at, t.fecha_generacion) DESC LIMIT 300
            """, (desde, hasta)).fetchall()
            if buscar:
                b = buscar.lower()
                rows = [r for r in rows if b in str(r[0]).lower() or b in str(r[2]).lower()]
            self._qr_hist_rows_cache = rows
            self._tbl_qr_hist.setRowCount(len(rows))
            _STATUS_CHIP = {
                "disponible":       (Colors.NEUTRAL.SLATE_400, "⚪ Disponible"),
                "asignado":         (Colors.INFO_BASE,         "🔵 Asignado"),
                "en_transito":      (Colors.WARNING_BASE,      "🟡 En tránsito"),
                "recibido":         (Colors.SUCCESS_BASE,      "🟢 Recibido"),
                "recepcion_parcial":(Colors.WARNING_HOVER,     "🟠 Parcial"),
                "incidencia":       (Colors.DANGER_BASE,       "🔴 Incidencia"),
            }
            for ri, r in enumerate(rows):
                vals = [str(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4]),
                        "", f"{float(r[6]):.2f}", f"{float(r[7]):.2f}",
                        f"${float(r[8]):,.2f}", str(r[9])[:16]]
                for ci, v in enumerate(vals):
                    if ci == 5: continue
                    it = QTableWidgetItem(v)
                    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    if ci in (6, 7, 8): it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    if ci == 0: it.setData(Qt.UserRole, r[10])  # store uuid_qr
                    self._tbl_qr_hist.setItem(ri, ci, it)
                # Status chip col 5
                estado_key = str(r[5]).lower().replace(' ', '_')
                color, label = _STATUS_CHIP.get(estado_key, (Colors.NEUTRAL.SLATE_500, str(r[5])))
                chip = QLabel(label)
                chip.setStyleSheet(
                    f"background:{color};color:white;border-radius:8px;"
                    f"padding:2px 6px;font-size:10px;font-weight:700;"
                )
                self._tbl_qr_hist.setCellWidget(ri, 5, chip)
        except Exception as exc:
            logger.warning("_cargar_historial_qr: %s", exc)

    def _on_qr_hist_row_selected(self) -> None:
        if not hasattr(self, '_tbl_qr_hist') or not hasattr(self, '_qr_detail_panel'): return
        sel = self._tbl_qr_hist.selectedItems()
        if not sel:
            self._qr_detail_panel.setVisible(False); return
        row = self._tbl_qr_hist.currentRow()
        id_item = self._tbl_qr_hist.item(row, 0)
        if not id_item: return
        uuid_qr = id_item.data(Qt.UserRole)
        if not uuid_qr: return
        try:
            # Container info
            c_row = self.conexion.execute(
                "SELECT uuid_qr, COALESCE(codigo_interno,'—'), COALESCE(descripcion,'—') FROM contenedores_qr WHERE uuid_qr=?",
                (uuid_qr,)
            ).fetchone()
            info_txt = (
                f"<b>QR:</b> {uuid_qr[:16]}…<br>"
                f"<b>Código:</b> {c_row[1] if c_row else '—'}<br>"
                f"<b>Descripción:</b> {c_row[2] if c_row else '—'}"
            )
            if hasattr(self, '_lbl_qr_detail_info'):
                self._lbl_qr_detail_info.setText(info_txt)
                self._lbl_qr_detail_info.setTextFormat(Qt.RichText)
            # Timeline
            tl_rows = self.conexion.execute("""
                SELECT fecha, tipo_movimiento, usuario FROM movimientos_inventario
                WHERE referencia LIKE ? OR descripcion LIKE ?
                ORDER BY fecha DESC LIMIT 10
            """, (f"%{uuid_qr[:8]}%", f"%{uuid_qr[:8]}%")).fetchall()
            if hasattr(self, '_tbl_timeline'):
                self._tbl_timeline.setRowCount(len(tl_rows))
                for ri, tl in enumerate(tl_rows):
                    for ci, v in enumerate([str(tl[0])[:16], str(tl[1]), str(tl[2])]):
                        it = QTableWidgetItem(v)
                        it.setFlags(Qt.ItemIsEnabled)
                        self._tbl_timeline.setItem(ri, ci, it)
            # Documents placeholder
            if hasattr(self, '_lst_qr_docs'):
                self._lst_qr_docs.clear()
                self._lst_qr_docs.addItem(QListWidgetItem(f"📄 Recepción QR {uuid_qr[:8]}"))
            self._qr_detail_panel.setTitle(f"Detalle del contenedor — {id_item.text()}")
            self._qr_detail_panel.setVisible(True)
        except Exception as exc:
            logger.debug("_on_qr_hist_row_selected: %s", exc)

    def _exportar_historial_qr_csv(self) -> None:
        import csv
        rows = getattr(self, '_qr_hist_rows_cache', [])
        if not rows:
            QMessageBox.information(self, "Info", "No hay datos para exportar."); return
        try:
            path, _ = QFileDialog.getSaveFileName(self, "Exportar QR Historial", "historial_qr.csv", "CSV (*.csv)")
            if not path: return
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f)
                w.writerow(["Contenedor", "Tipo", "Proveedor", "Factura", "Sucursal", "Estado", "Peso est.", "Peso rec.", "Total", "Fecha"])
                for r in rows:
                    w.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9]])
            Toast.success(self, "✅ Exportado", path.split('/')[-1])
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

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
                "usuario":           self.usuario,
                "codigo_interno":    self._txt_codigo_interno.text().strip(),
                "descripcion":       self._txt_descripcion.text().strip(),
                "tipo_contenedor":   self._tipo_contenedor,
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
            except Exception as _e_db:
                logger.warning("contenedores_qr insert failed (non-fatal): %s", _e_db)

            # Mostrar imagen QR
            png_bytes = svc.generar_imagen_qr(f"SPJ:CONT:{uuid_qr}", size=200)
            pixmap = QPixmap()
            pixmap.loadFromData(png_bytes)
            self._lbl_qr_preview.setPixmap(
                pixmap.scaled(190, 190, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            self._last_generated_uuid = uuid_qr
            self._last_generated_png  = png_bytes
            Toast.success(self, "🏷️ QR Generado", f"UUID: {uuid_qr}")
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
                self._lbl_cont_info.setStyleSheet(f"color:{Colors.SUCCESS_BASE}; padding:4px;")
            else:
                # Contenedor nuevo o nunca registrado
                self._contenedor_activo = {"uuid_qr": uuid_qr, "es_nuevo": True}
                self._lbl_cont_info.setText(
                    f"🆕 QR nuevo (no asignado antes): {uuid_qr}"
                )
                self._lbl_cont_info.setStyleSheet(f"color:{Colors.WARNING_BASE}; padding:4px;")
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
            self._lbl_recv_info.setStyleSheet(f"color:{Colors.PRIMARY_BASE}; padding:4px; font-weight:bold;")
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
            product_id   = item.get("product_id", "")

            # Col 0: ID
            lbl_id = QTableWidgetItem(str(product_id) if product_id else "")
            lbl_id.setFlags(Qt.ItemIsEnabled)
            # Col 1: Producto (nombre)
            lbl_prod = QTableWidgetItem(nombre)
            lbl_prod.setFlags(Qt.ItemIsEnabled)
            # Col 2: Unidad
            lbl_unit = QTableWidgetItem(unidad)
            lbl_unit.setFlags(Qt.ItemIsEnabled)
            # Col 3: Esperado
            lbl_qty  = QTableWidgetItem(f"{qty_esperada:.3f}")
            lbl_qty.setFlags(Qt.ItemIsEnabled)
            lbl_qty.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # Col 4: Recibido Real (QDoubleSpinBox)
            spin_recv = QDoubleSpinBox()
            spin_recv.setRange(0, qty_esperada * 2 or 99999)
            spin_recv.setDecimals(3)
            spin_recv.setValue(qty_esperada)
            spin_recv.setProperty("qty_esperada", qty_esperada)
            spin_recv.setProperty("product_id", product_id)
            spin_recv.setProperty("costo_unitario", item.get("costo_unitario", 0))
            spin_recv.valueChanged.connect(self._actualizar_diff_recepcion)

            # Col 5: Diferencia
            diff_item = QTableWidgetItem("0.000")
            diff_item.setFlags(Qt.ItemIsEnabled)
            diff_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # Col 6: Lote/Caducidad (QLineEdit)
            cad_edit = QLineEdit()
            cad_edit.setPlaceholderText("YYYY-MM-DD")

            # Col 7: Estado badge
            estado_lbl = QLabel("🟡 Pendiente")
            estado_lbl.setStyleSheet(
                f"color:{Colors.WARNING_BASE};font-size:10px;padding:2px 4px;"
            )

            self._tbl_recv.setItem(ri, 0, lbl_id)
            self._tbl_recv.setItem(ri, 1, lbl_prod)
            self._tbl_recv.setItem(ri, 2, lbl_unit)
            self._tbl_recv.setItem(ri, 3, lbl_qty)
            self._tbl_recv.setCellWidget(ri, 4, spin_recv)
            self._tbl_recv.setItem(ri, 5, diff_item)
            self._tbl_recv.setCellWidget(ri, 6, cad_edit)
            self._tbl_recv.setCellWidget(ri, 7, estado_lbl)

    def _actualizar_diff_recepcion(self) -> None:
        total_diff = 0.0
        for ri in range(self._tbl_recv.rowCount()):
            spin = self._tbl_recv.cellWidget(ri, 4)
            diff_item = self._tbl_recv.item(ri, 5)
            if not spin or not diff_item: continue
            qty_esp  = float(spin.property("qty_esperada") or 0)
            qty_recv = spin.value()
            diff     = qty_recv - qty_esp
            total_diff += abs(diff)
            diff_item.setText(f"{diff:+.3f}")
            diff_item.setForeground(
                QColor(Colors.DANGER_BASE if diff < -0.001 else
                       Colors.SUCCESS_BASE if diff > 0.001 else
                       Colors.NEUTRAL.SLATE_700)
            )
        color = Colors.DANGER_BASE if total_diff > 0.01 else Colors.SUCCESS_BASE
        self._lbl_recv_diff.setText(f"Diferencia total: {total_diff:.3f}")
        self._lbl_recv_diff.setStyleSheet(f"font-weight:bold;font-size:13px;color:{color};")
        self._actualizar_resumen_recepcion()

    def _confirmar_recepcion(self) -> None:
        """Confirma la recepción: actualiza inventario, lotes y trazabilidad."""
        if not self._contenedor_activo:
            QMessageBox.warning(self, "Aviso", "Carga un contenedor primero."); return
        try:
            uuid_qr    = self._contenedor_activo.get("uuid_qr", "")
            notas_recv = self._txt_recv_notas.toPlainText().strip()
            items_recibidos = []
            for ri in range(self._tbl_recv.rowCount()):
                spin    = self._tbl_recv.cellWidget(ri, 4)
                cad_edit = self._tbl_recv.cellWidget(ri, 6)
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

            Toast.success(self, "✅ Recepción Completada",
                          f"QR: {uuid_qr} · {len(items_recibidos)} ítem(s) al inventario")
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
        _tqr_row = self.conexion.execute(
            "SELECT COALESCE(datos_extra,'{}') FROM trazabilidad_qr WHERE uuid_qr=?",
            (uuid_qr,)
        ).fetchone()
        datos_extra = json.loads(_tqr_row[0] if _tqr_row else "{}")
        proveedor_id = datos_extra.get("proveedor_id")
        condicion    = datos_extra.get("condicion_pago", "liquidado")
        metodo       = datos_extra.get("metodo_pago", "efectivo")
        monto_pagado = float(datos_extra.get("monto_pagado", 0))
        monto_total  = float(datos_extra.get("monto_total", 0))

        from core.db.connection import transaction as _tx_qr
        with _tx_qr(self.conexion):
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
                # CASE guard prevents division-by-zero if existing quantity is somehow 0.
                self.conexion.execute("""
                    INSERT INTO inventario_actual(producto_id, sucursal_id, cantidad, costo_promedio)
                    VALUES(?,?,?,?)
                    ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET
                        cantidad = cantidad + excluded.cantidad,
                        costo_promedio = CASE
                            WHEN (cantidad + excluded.cantidad) > 0
                            THEN (cantidad * costo_promedio + excluded.cantidad * excluded.costo_promedio)
                                 / (cantidad + excluded.cantidad)
                            ELSE excluded.costo_promedio
                        END,
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
            except Exception as _e_cont:
                logger.warning("contenedores_qr update failed (non-fatal): %s", _e_cont)

        # Stock already updated inside the transaction above (inventario_actual UPSERT
        # + productos.existencia sync via SUM). No post-commit update needed.

    def _guardar_asignacion(self) -> None:
        """Guarda la asignación de productos + pago al contenedor."""
        if not self._contenedor_activo:
            QMessageBox.warning(self, "Aviso", "Carga un contenedor primero."); return
        if not self._items_asignados:
            QMessageBox.warning(self, "Aviso", "Agrega al menos un producto."); return
        if not self._proveedor_asignar_id:
            QMessageBox.warning(self, "Aviso",
                "Selecciona un proveedor antes de guardar la asignación."); return

        uuid_qr      = self._contenedor_activo.get("uuid_qr", "")
        proveedor_id = self._proveedor_asignar_id
        condicion    = self._cmb_condicion.currentText()
        metodo       = self._cmb_metodo.currentText()
        monto_total  = sum(i["subtotal"] for i in self._items_asignados)
        monto_pagado = self._spin_monto_pagado.value()
        if condicion == "liquidado": monto_pagado = monto_total
        elif condicion == "crédito": monto_pagado = 0.0
        dest_id    = self._cmb_sucursal_destino.currentData() or self.sucursal_id
        notas      = self._txt_notas_asign.toPlainText().strip()
        referencia = self._txt_referencia.text().strip()

        datos_extra = {
            "items":           self._items_asignados,
            "proveedor_id":    proveedor_id,
            "condicion_pago":  condicion,
            "metodo_pago":     metodo,
            "monto_pagado":    monto_pagado,
            "monto_total":     monto_total,
            "saldo_pendiente": max(0, monto_total - monto_pagado),
            "sucursal_destino": dest_id,
            "referencia_pago": referencia,
            "notas":           notas,
        }

        try:
            self.conexion.execute("""
                INSERT INTO trazabilidad_qr
                    (uuid_qr, tipo, proveedor_id, sucursal_id, sucursal_destino,
                     estado, datos_extra)
                VALUES(?,?,?,?,?,'asignado',?)
                ON CONFLICT(uuid_qr) DO UPDATE SET
                    estado='asignado',
                    proveedor_id=excluded.proveedor_id,
                    sucursal_destino=excluded.sucursal_destino,
                    datos_extra=excluded.datos_extra,
                    fecha_generacion=datetime('now')
            """, (uuid_qr, "contenedor", proveedor_id,
                  self.sucursal_id, dest_id,
                  json.dumps(datos_extra, ensure_ascii=False)))
            self.conexion.commit()
            Toast.success(self, "✅ Asignación guardada",
                          f"Total: ${monto_total:.2f} · Pagado: ${monto_pagado:.2f}")
            self._poblar_contenedores_sidebar()
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
        unidad = getattr(self, '_prod_asignar_unidad', 'pz')
        self._items_asignados.append({
            "product_id":    prod_id,
            "nombre":        nombre,
            "cantidad":      qty,
            "costo_unitario": costo,
            "subtotal":      round(qty * costo, 2),
            "unidad":        unidad,
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
                    item = QListWidgetItem(name)
                    item.setData(Qt.UserRole, pid)
                    self._lst_proveedores.addItem(item)
                self._lst_proveedores.setVisible(True)
            else:
                self._lst_proveedores.setVisible(False)
        except Exception as e:
            logger.debug("_buscar_proveedor_asignar: %s", e)

    def _seleccionar_proveedor_asignar(self, item) -> None:
        """Confirma la selección de proveedor y oculta la lista."""
        self._proveedor_asignar_id = item.data(Qt.UserRole)
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
                    item = QListWidgetItem(f"{name}  [${costo:.2f}/{unidad}]")
                    item.setData(Qt.UserRole, (pid, name, costo, unidad))
                    self._lst_prod_asign.addItem(item)
                self._lst_prod_asign.setVisible(True)
            else:
                self._lst_prod_asign.setVisible(False)
        except Exception as e:
            logger.debug("_buscar_producto_asignar: %s", e)

    def _seleccionar_producto_asignar(self, item) -> None:
        """Confirma selección de producto y pre-llena el costo."""
        pid, name, costo, unidad = item.data(Qt.UserRole)
        self._prod_asignar_id = pid
        self._prod_asignar_unidad = unidad   # persist for _agregar_item_asignacion
        self._lbl_prod_asign_sel.setText(name)
        self._txt_buscar_prod_asign.setText(name)
        self._spin_costo_asign.setValue(costo)
        self._lst_prod_asign.setVisible(False)

    def _recargar_listas(self) -> None:
        """Recarga todas las listas dinámicas. Llamado por el botón Recargar del módulo padre."""
        self._cargar_historial()
        self._cargar_historial_qr()
        self._cargar_sucursales_combo_recepcion()

    def _cargar_sucursales_combo_recepcion(self) -> None:
        self._cmb_sucursal_destino.clear()
        try:
            rows = self.conexion.execute(
                "SELECT id, nombre FROM sucursales WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            for r in rows:
                self._cmb_sucursal_destino.addItem(f"🏪 {r[1]}", r[0])
        except Exception:
            self._cmb_sucursal_destino.addItem("Principal", 1)

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
                btn_print.clicked.connect(dlg.accept)
                ll.addWidget(btn_print)
                dlg.exec_()
            except ImportError:
                QMessageBox.information(self, "QR UUID",
                    f"UUID del contenedor:\n{uuid_qr}\n\n"
                    "Para imprimir instala: pip install qrcode[pil]")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    _HIST_ESTADO_VARIANTS = {
        "completada": "success", "completa":   "success",
        "credito":    "warning", "pendiente":  "info",
        "cancelada":  "error",   "parcial":    "primary",
    }

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
                    f"${float(r[5] or 0):.2f}",
                ]
                for ci, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    if ci in (4, 5):
                        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self._tbl_hist.setItem(ri, ci, it)
                # Col 6: status badge
                estado_raw = str(r[6] or "").strip().lower()
                variant    = self._HIST_ESTADO_VARIANTS.get(estado_raw, "primary")
                badge      = create_badge(self, (r[6] or "—").upper(), variant)
                self._tbl_hist.setCellWidget(ri, 6, badge)
        except Exception as e:
            logger.warning("_cargar_historial: %s", e)

    def _aceptar_todo_recepcion(self) -> None:
        """Establece cantidad recibida = esperada en todas las filas."""
        for ri in range(self._tbl_recv.rowCount()):
            spin = self._tbl_recv.cellWidget(ri, 4)
            if spin:
                qty_esp = float(spin.property("qty_esperada") or 0)
                spin.blockSignals(True)
                spin.setValue(qty_esp)
                spin.blockSignals(False)
        self._actualizar_diff_recepcion()

    def _resetear_diff_recepcion(self) -> None:
        """Alias de _aceptar_todo — restaura received = expected."""
        self._aceptar_todo_recepcion()

    def _limpiar_tab_recepcion(self) -> None:
        self._txt_uuid_recv.clear()
        self._lbl_recv_info.setText("Sin contenedor cargado")
        self._tbl_recv.setRowCount(0)
        self._txt_recv_notas.clear()
        self._contenedor_activo = None
