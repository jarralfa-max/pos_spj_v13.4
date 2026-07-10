# modulos/ticket_designer.py — SPJ POS v13.30
"""
Diseñador profesional de Tickets con:
  - Configuración de tamaño de papel
  - Logo que se inyecta en la impresión real (no solo preview)
  - QR y código de barras configurables
  - Vista previa en tiempo real
  - Botón imprimir muestra
"""
from __future__ import annotations
from modulos.spj_styles import spj_btn, apply_btn_styles
from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import create_primary_button, create_success_button, create_secondary_button, create_input, create_combo, create_card, apply_tooltip
import logging
import base64
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QTextBrowser, QSplitter, QGroupBox,
    QListWidget, QMessageBox, QFileDialog, QTabWidget,
    QFormLayout, QLineEdit, QCheckBox, QComboBox, QSpinBox,
    QDoubleSpinBox, QScrollArea, QFrame, QTextEdit, QListWidgetItem,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPixmap

logger = logging.getLogger("spj.ticket_designer")

PAPER_SIZES = {
    "58mm (mini)":     (58, 0),
    "80mm (estándar)": (80, 0),
    "80mm x 297mm":    (80, 297),
    "A4":              (210, 297),
    "Personalizado":   (0, 0),
}

BLOCK_LABELS = {
    "logo": "Logo",
    "brand_header": "Encabezado / marca",
    "sale_info": "Datos de venta",
    "customer": "Cliente",
    "items": "Productos",
    "totals": "Totales",
    "payment": "Pago",
    "loyalty": "Fidelidad",
    "fomo": "FOMO / promociones",
    "raffle_title": "Título del sorteo",
    "ticket_number": "Número de boleto",
    "prize": "Premio",
    "draw_date": "Fecha del sorteo",
    "qr": "Código QR",
    "barcode": "Código de barras",
    "footer": "Mensaje footer",
    "legal": "Mensaje legal",
}

SALE_ONLY_BLOCKS = {"items", "totals", "payment", "loyalty", "fomo"}
RAFFLE_ONLY_BLOCKS = {"raffle_title", "ticket_number", "prize", "draw_date"}


class ModuloTicketDesigner(QWidget):

    variables_disponibles = [
        "{{folio}}", "{{fecha}}", "{{cajero}}", "{{cliente_nombre}}",
        "{{items_html}}", "{{total}}", "{{subtotal}}", "{{descuento}}",
        "{{forma_pago}}", "{{cambio}}", "{{puntos_ganados}}",
        "{{puntos_totales}}", "{{mensaje_psicologico}}",
        "{{qr_code}}", "{{barcode}}", "{{logo}}",
        "{{nombre_empresa}}", "{{direccion}}", "{{telefono}}",
        # Encabezado de sucursal + datos fiscales
        "{{sucursal_nombre}}", "{{sucursal_direccion}}", "{{sucursal_telefono}}",
        "{{whatsapp_empresa}}", "{{rfc_emisor}}", "{{regimen_fiscal}}",
        "{{web_empresa}}",
    ]

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container = container
        self._logo_b64 = ""
        self.current_layout_type = "sale_ticket"
        self.init_ui()
        self.cargar_plantilla_actual()
        self._cargar_logo_guardado()
        self._cargar_config_qr_guardada()
        self._cargar_config_papel()
        self._cargar_layout_activo()

    def set_usuario_actual(self, usuario: str, rol: str = "cajero") -> None:
        self.usuario_actual = usuario

    def set_sucursal(self, sucursal_id: int, nombre: str = "") -> None:
        self.sucursal_id = sucursal_id

    # ══════════════════════════════════════════════════════════════════════
    #  UI
    # ══════════════════════════════════════════════════════════════════════

    def init_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)

        header = QHBoxLayout()
        lbl = QLabel("🎨 Diseñador de Tickets")
        lbl.setObjectName("heading")
        header.addWidget(lbl)
        header.addStretch()
        
        btn_print = QPushButton("🖨️ Imprimir muestra")
        btn_print = create_secondary_button(self, btn_print, "Imprimir ticket de prueba")
        btn_print.clicked.connect(self._imprimir_muestra)
        
        btn_save_all = QPushButton("💾 Guardar todo")
        btn_save_all = create_success_button(self, btn_save_all, "Guardar configuración del ticket")
        btn_save_all.clicked.connect(self._guardar_todo)
        btn_brand = QPushButton("⚙️ Editar identidad del sistema")
        btn_brand = create_secondary_button(self, btn_brand, "Editar marca en Configuración del Sistema")
        btn_brand.clicked.connect(self._abrir_configuracion_sistema)
        
        self.cmb_layout_type = QComboBox()
        self.cmb_layout_type.addItem("Ticket de venta", "sale_ticket")
        self.cmb_layout_type.addItem("Boleto de sorteo", "raffle_ticket")
        self.cmb_layout_type.currentIndexChanged.connect(self._on_layout_type_changed)
        header.addWidget(QLabel("Diseñar:"))
        header.addWidget(self.cmb_layout_type)
        header.addWidget(btn_print)
        header.addWidget(btn_brand)
        header.addWidget(btn_save_all)
        lay.addLayout(header)

        self.tabs = QTabWidget()
        tabs = self.tabs
        tabs.setObjectName("tabWidget")
        lay.addWidget(tabs)

        warn = QLabel("⚠️ La impresión térmica real usa ESC/POS RAW. El HTML solo sirve para preview/PDF.")
        warn.setObjectName("caption")
        lay.addWidget(warn)

        # Tab 1: Estructura (Preview/PDF avanzado, no impresión térmica)
        tab_design = QWidget()
        tabs.addTab(tab_design, "📦 Estructura")
        self._build_tab_design(tab_design)

        # Tab 2: Marca
        tab_media = QWidget()
        tabs.addTab(tab_media, "🏷️ Marca")
        self._build_tab_media(tab_media)

        # Tab 3: Fidelidad
        self.tab_loyalty = QWidget()
        tabs.addTab(self.tab_loyalty, "🎯 Fidelidad")
        self._build_tab_loyalty(self.tab_loyalty)

        # Tab 4: FOMO / Promociones
        self.tab_fomo = QWidget()
        tabs.addTab(self.tab_fomo, "🔥 FOMO / Promociones")
        self._build_tab_fomo(self.tab_fomo)

        # Tab 5: Impresión ESC/POS
        tab_paper = QWidget()
        tabs.addTab(tab_paper, "🖨️ Impresión ESC/POS")
        self._build_tab_paper(tab_paper)

    def _build_tab_design(self, parent):
        splitter = QSplitter(Qt.Horizontal)
        QVBoxLayout(parent).addWidget(splitter)

        grp_vars = QGroupBox("📌 Variables")
        grp_vars.setMaximumWidth(180)
        lv = QVBoxLayout(grp_vars)
        lbl_help = QLabel("Doble clic para insertar:")
        lbl_help.setObjectName("caption")
        lv.addWidget(lbl_help)
        self.lista_variables = QListWidget()
        self.lista_variables.setObjectName("inputField")
        self.lista_variables.addItems(self.variables_disponibles)
        self.lista_variables.itemDoubleClicked.connect(self.insertar_variable)
        lv.addWidget(self.lista_variables)

        self.lst_blocks = QListWidget()
        self.lst_blocks.setObjectName("inputField")
        self.lst_blocks.setToolTip("Activa/desactiva bloques y usa Subir/Bajar para definir el orden ESC/POS")
        self.lst_blocks.itemChanged.connect(self.actualizar_vista_previa)
        lv.addWidget(QLabel("Bloques ESC/POS:"))
        lv.addWidget(self.lst_blocks)
        btn_block_order = QHBoxLayout()
        btn_up = QPushButton("↑")
        btn_down = QPushButton("↓")
        btn_up = create_secondary_button(self, btn_up, "Subir bloque")
        btn_down = create_secondary_button(self, btn_down, "Bajar bloque")
        btn_up.clicked.connect(lambda: self._mover_bloque(-1))
        btn_down.clicked.connect(lambda: self._mover_bloque(1))
        btn_block_order.addWidget(btn_up)
        btn_block_order.addWidget(btn_down)
        lv.addLayout(btn_block_order)
        splitter.addWidget(grp_vars)

        grp_ed = QGroupBox("📝 Plantilla HTML (solo Preview/PDF avanzado)")
        grp_ed.setObjectName("styledGroup")
        le = QVBoxLayout(grp_ed)
        self.txt_editor = QPlainTextEdit()
        self.txt_editor.setFont(QFont("Courier New", 10))
        self.txt_editor.setObjectName("codeEditor")
        self.txt_editor.textChanged.connect(self.actualizar_vista_previa)
        le.addWidget(self.txt_editor)
        note = QLabel("HTML no controla la impresión térmica física; se usa para preview/PDF.")
        note.setObjectName("caption")
        le.addWidget(note)
        btn_rest = QPushButton("🔄 Restaurar")
        btn_rest = create_secondary_button(self, btn_rest, "Restaurar plantilla por defecto")
        btn_rest.clicked.connect(self.restaurar_defecto)
        le.addWidget(btn_rest)
        splitter.addWidget(grp_ed)

        grp_prev = QGroupBox("👁️ Vista previa HTML (aproximada)")
        grp_prev.setObjectName("styledGroup")
        lp = QVBoxLayout(grp_prev)
        self.visor_preview = QTextBrowser()
        self.visor_preview.setObjectName("previewBox")
        self.visor_preview.setMaximumWidth(350)
        self.visor_preview.setMinimumWidth(280)
        lp.addWidget(self.visor_preview)
        self.txt_preview_escpos = QTextEdit()
        self.txt_preview_escpos.setReadOnly(True)
        self.txt_preview_escpos.setObjectName("codeEditor")
        self.txt_preview_escpos.setPlaceholderText("Preview monoespaciado ESC/POS")
        lp.addWidget(self.txt_preview_escpos)
        splitter.addWidget(grp_prev)
        splitter.setSizes([160, 440, 340])

    def _build_tab_media(self, parent):
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        content = QWidget(); lm = QVBoxLayout(content); lm.setSpacing(Spacing.MD)

        # Logo
        grp_logo = QGroupBox("Logo de la empresa")
        grp_logo.setObjectName("styledGroup")
        fl = QFormLayout(grp_logo)
        lbl_brand = QLabel("Usa logo de Configuración del Sistema como fuente principal.")
        lbl_brand.setObjectName("caption")
        fl.addRow("", lbl_brand)
        self.chk_logo = QCheckBox("Mostrar logo")
        self.chk_logo.setChecked(True)
        self.chk_logo.stateChanged.connect(self.actualizar_vista_previa)
        fl.addRow("", self.chk_logo)
        self.lbl_logo_preview = QLabel("Sin logo cargado")
        self.lbl_logo_preview.setFixedHeight(90)
        self.lbl_logo_preview.setFixedWidth(200)
        self.lbl_logo_preview.setAlignment(Qt.AlignCenter)
        self.lbl_logo_preview.setObjectName("logoPreviewBox")
        fl.addRow("Vista previa:", self.lbl_logo_preview)
        btn_lr = QHBoxLayout()
        btn_logo = QPushButton("📁 Cargar")
        btn_logo = create_primary_button(self, btn_logo, "Cargar imagen del logo")
        btn_logo.clicked.connect(self._cargar_logo)
        btn_clear = QPushButton("🗑️ Quitar")
        btn_clear = create_secondary_button(self, btn_clear, "Quitar logo actual")
        btn_clear.clicked.connect(self._quitar_logo)
        btn_nobg = QPushButton("✨ Quitar fondo")
        btn_nobg = create_secondary_button(self, btn_nobg, "Hacer transparente el fondo del logo actual")
        btn_nobg.clicked.connect(self._aplicar_quitar_fondo)
        btn_lr.addWidget(btn_logo); btn_lr.addWidget(btn_clear); btn_lr.addWidget(btn_nobg)
        fl.addRow("", btn_lr)
        self.chk_logo_nobg = QCheckBox("Quitar fondo automáticamente al cargar")
        self.chk_logo_nobg.setChecked(True)
        fl.addRow("", self.chk_logo_nobg)
        self.spin_logo_w = QSpinBox()
        self.spin_logo_w.setRange(20, 400); self.spin_logo_w.setValue(150)
        self.spin_logo_w.setSuffix(" px")
        self.spin_logo_w.setObjectName("inputField")
        self.spin_logo_w.valueChanged.connect(self.actualizar_vista_previa)
        fl.addRow("Ancho:", self.spin_logo_w)
        self.cmb_logo_pos = QComboBox()
        self.cmb_logo_pos.addItems(["Centrado", "Izquierda", "Derecha"])
        self.cmb_logo_pos.setObjectName("inputField")
        self.cmb_logo_pos.currentIndexChanged.connect(self.actualizar_vista_previa)
        fl.addRow("Posición:", self.cmb_logo_pos)
        self.txt_footer_message = QLineEdit()
        self.txt_footer_message.setPlaceholderText("Mensaje final / footer")
        self.txt_footer_message.setObjectName("inputField")
        self.txt_footer_message.textChanged.connect(self.actualizar_vista_previa)
        fl.addRow("Footer:", self.txt_footer_message)
        self.txt_legal_message = QLineEdit()
        self.txt_legal_message.setPlaceholderText("Texto legal o condiciones")
        self.txt_legal_message.setObjectName("inputField")
        self.txt_legal_message.textChanged.connect(self.actualizar_vista_previa)
        fl.addRow("Legal:", self.txt_legal_message)
        lm.addWidget(grp_logo)

        # QR
        grp_qr = QGroupBox("Código QR")
        grp_qr.setObjectName("styledGroup")
        fq = QFormLayout(grp_qr)
        self.chk_qr = QCheckBox("Incluir QR")
        self.chk_qr.stateChanged.connect(self.actualizar_vista_previa)
        fq.addRow("", self.chk_qr)
        self.cmb_qr_dato = QComboBox()
        self.cmb_qr_dato.addItems(["URL del negocio","Folio de la venta","Número de cliente","WhatsApp del negocio"])
        self.cmb_qr_dato.setObjectName("inputField")
        fq.addRow("Dato:", self.cmb_qr_dato)
        self.txt_qr_url = QLineEdit(); self.txt_qr_url.setPlaceholderText("https://mitienda.com")
        self.txt_qr_url.setObjectName("inputField")
        fq.addRow("URL:", self.txt_qr_url)
        self.spin_qr_size = QSpinBox(); self.spin_qr_size.setRange(40,200); self.spin_qr_size.setValue(100); self.spin_qr_size.setSuffix(" px")
        self.spin_qr_size.setObjectName("inputField")
        fq.addRow("Tamaño:", self.spin_qr_size)
        lm.addWidget(grp_qr)

        # Barcode
        grp_bc = QGroupBox("Código de barras")
        grp_bc.setObjectName("styledGroup")
        fb = QFormLayout(grp_bc)
        self.chk_barcode = QCheckBox("Incluir barcode (folio / número de boleto)")
        self.chk_barcode.stateChanged.connect(self.actualizar_vista_previa)
        fb.addRow("", self.chk_barcode)
        self.cmb_barcode_type = QComboBox()
        self.cmb_barcode_type.addItems(["Code128","EAN13","QR (alternativo)"])
        self.cmb_barcode_type.setObjectName("inputField")
        fb.addRow("Tipo:", self.cmb_barcode_type)
        lm.addWidget(grp_bc)
        lm.addStretch()
        scroll.setWidget(content)
        QVBoxLayout(parent).addWidget(scroll)

    def _build_tab_paper(self, parent):
        lp = QVBoxLayout(parent); lp.setSpacing(Spacing.MD)

        grp = QGroupBox("Tamaño de papel")
        grp.setObjectName("styledGroup")
        pf = QFormLayout(grp)
        self.cmb_paper_size = QComboBox()
        self.cmb_paper_size.addItems(list(PAPER_SIZES.keys()))
        self.cmb_paper_size.setCurrentIndex(1)
        self.cmb_paper_size.setObjectName("inputField")
        self.cmb_paper_size.currentIndexChanged.connect(self._on_paper_change)
        pf.addRow("Predefinido:", self.cmb_paper_size)
        self.spin_paper_w = QSpinBox(); self.spin_paper_w.setRange(30,300); self.spin_paper_w.setValue(80); self.spin_paper_w.setSuffix(" mm")
        self.spin_paper_w.setObjectName("inputField")
        pf.addRow("Ancho:", self.spin_paper_w)
        self.spin_paper_h = QSpinBox(); self.spin_paper_h.setRange(0,500); self.spin_paper_h.setValue(0); self.spin_paper_h.setSuffix(" mm")
        self.spin_paper_h.setSpecialValueText("Continuo (sin corte)")
        self.spin_paper_h.setObjectName("inputField")
        pf.addRow("Alto:", self.spin_paper_h)
        lp.addWidget(grp)

        grp_m = QGroupBox("Márgenes")
        grp_m.setObjectName("styledGroup")
        mf = QFormLayout(grp_m)
        self.spin_margin_top = QSpinBox(); self.spin_margin_top.setRange(0,30); self.spin_margin_top.setValue(5); self.spin_margin_top.setSuffix(" mm")
        self.spin_margin_top.setObjectName("inputField")
        mf.addRow("Superior:", self.spin_margin_top)
        self.spin_margin_side = QSpinBox(); self.spin_margin_side.setRange(0,20); self.spin_margin_side.setValue(3); self.spin_margin_side.setSuffix(" mm")
        self.spin_margin_side.setObjectName("inputField")
        mf.addRow("Laterales:", self.spin_margin_side)
        lp.addWidget(grp_m)

        grp_f = QGroupBox("Tipografía")
        grp_f.setObjectName("styledGroup")
        ff = QFormLayout(grp_f)
        self.cmb_font_family = QComboBox()
        self.cmb_font_family.addItems(["Courier New","Arial","Helvetica","Consolas","Lucida Console","monospace"])
        self.cmb_font_family.setObjectName("inputField")
        ff.addRow("Fuente:", self.cmb_font_family)
        self.spin_font_base = QSpinBox(); self.spin_font_base.setRange(8,18); self.spin_font_base.setValue(12); self.spin_font_base.setSuffix(" px")
        ff.addRow("Tamaño base:", self.spin_font_base)
        lp.addWidget(grp_f)
        lp.addStretch()

    def _build_tab_loyalty(self, parent):
        lay = QVBoxLayout(parent)
        grp = QGroupBox("Fidelidad en ticket")
        grp.setObjectName("styledGroup")
        form = QFormLayout(grp)
        self.chk_show_points = QCheckBox("Mostrar puntos ganados")
        self.chk_show_points.setChecked(True)
        self.chk_show_balance = QCheckBox("Mostrar saldo actual")
        self.chk_show_balance.setChecked(True)
        self.chk_show_level = QCheckBox("Mostrar nivel del cliente")
        self.chk_show_goal = QCheckBox("Mostrar meta cercana")
        form.addRow("", self.chk_show_points)
        form.addRow("", self.chk_show_balance)
        form.addRow("", self.chk_show_level)
        form.addRow("", self.chk_show_goal)
        lay.addWidget(grp)
        lay.addStretch()

    def _build_tab_fomo(self, parent):
        lay = QVBoxLayout(parent)
        grp = QGroupBox("Mensajes FOMO / Promociones")
        grp.setObjectName("styledGroup")
        form = QFormLayout(grp)
        self.chk_fomo_enabled = QCheckBox("Activar mensajes FOMO")
        self.chk_fomo_enabled.setChecked(True)
        self.spin_fomo_max = QSpinBox()
        self.spin_fomo_max.setRange(1, 5)
        self.spin_fomo_max.setValue(2)
        self.spin_fomo_max.setObjectName("inputField")
        self.cmb_fomo_priority = QComboBox()
        self.cmb_fomo_priority.addItems(["Promoción por vencer", "Meta cercana", "Canje de puntos"])
        self.cmb_fomo_priority.setObjectName("inputField")
        form.addRow("", self.chk_fomo_enabled)
        form.addRow("Máx. mensajes:", self.spin_fomo_max)
        form.addRow("Prioridad:", self.cmb_fomo_priority)
        lay.addWidget(grp)
        lay.addStretch()

    def _on_paper_change(self, idx):
        key = self.cmb_paper_size.currentText()
        w, h = PAPER_SIZES.get(key, (80, 0))
        if w > 0: self.spin_paper_w.setValue(w)
        if h >= 0: self.spin_paper_h.setValue(h)

    # ══════════════════════════════════════════════════════════════════════
    #  Logo
    # ══════════════════════════════════════════════════════════════════════

    def _cargar_logo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar logo", "",
            "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif *.svg)")
        if not path: return
        try:
            with open(path, 'rb') as f: data = f.read()
            ext = os.path.splitext(path)[1].lower().strip('.')
            mime = {'jpg':'jpeg','jpeg':'jpeg','png':'png','gif':'gif','bmp':'bmp','svg':'svg+xml'}.get(ext,'png')
            # Quitar fondo automáticamente (transparencia) si está activado. quitar_fondo
            # devuelve un PNG; si la imagen no es rasterizable (SVG) deja los bytes igual.
            if getattr(self, 'chk_logo_nobg', None) and self.chk_logo_nobg.isChecked():
                from frontend.desktop.components.logo_utils import quitar_fondo
                nueva = quitar_fondo(data)
                if nueva is not data and nueva != data:
                    data, mime = nueva, 'png'
            self._logo_b64 = f"data:image/{mime};base64,{base64.b64encode(data).decode()}"
            self._mostrar_logo_thumbnail(data)
            self.actualizar_vista_previa()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _aplicar_quitar_fondo(self):
        """Hace transparente el fondo del logo ya cargado."""
        if not self._logo_b64:
            QMessageBox.information(self, "Logo", "Carga un logo primero."); return
        try:
            from frontend.desktop.components.logo_utils import quitar_fondo
            b64_part = self._logo_b64.split(",", 1)[1] if "," in self._logo_b64 else self._logo_b64
            raw = base64.b64decode(b64_part)
            nueva = quitar_fondo(raw)
            self._logo_b64 = f"data:image/png;base64,{base64.b64encode(nueva).decode()}"
            self._mostrar_logo_thumbnail(nueva)
            self.actualizar_vista_previa()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _quitar_logo(self):
        self._logo_b64 = ""
        self.lbl_logo_preview.setPixmap(QPixmap())
        self.lbl_logo_preview.setText("Sin logo cargado")
        self.lbl_logo_preview.setObjectName("logoPreviewBox")
        self.actualizar_vista_previa()

    def _mostrar_logo_thumbnail(self, raw_data=None):
        try:
            if raw_data is None and self._logo_b64:
                b64_part = self._logo_b64.split(",", 1)[1] if "," in self._logo_b64 else self._logo_b64
                raw_data = base64.b64decode(b64_part)
            if raw_data:
                pix = QPixmap(); pix.loadFromData(raw_data)
                if not pix.isNull():
                    self.lbl_logo_preview.setPixmap(pix.scaledToHeight(80, Qt.SmoothTransformation))
                    self.lbl_logo_preview.setObjectName("logoPreviewSuccess")
                    return
        except Exception: pass
        self.lbl_logo_preview.setText("Sin logo")

    def _cargar_logo_guardado(self):
        try:
            cfg = self.container.config_service
            b64 = cfg.get('ticket_logo_b64')
            if b64:
                self._logo_b64 = b64
                self._mostrar_logo_thumbnail()
                w = cfg.get('ticket_logo_width')
                if w: self.spin_logo_w.setValue(int(w))
                p = cfg.get('ticket_logo_pos')
                if p:
                    idx = self.cmb_logo_pos.findText(p)
                    if idx >= 0: self.cmb_logo_pos.setCurrentIndex(idx)
        except Exception: pass

    def _cargar_config_qr_guardada(self):
        try:
            cfg = self.container.config_service
            def _g(k, d=""):
                return cfg.get(k) or d
            self.chk_qr.setChecked(_g('ticket_qr_enabled','0') == '1')
            d = _g('ticket_qr_dato','')
            if d:
                i = self.cmb_qr_dato.findText(d)
                if i >= 0: self.cmb_qr_dato.setCurrentIndex(i)
            self.txt_qr_url.setText(_g('ticket_qr_url',''))
            try: self.spin_qr_size.setValue(int(_g('ticket_qr_size','100')))
            except: pass
            self.chk_barcode.setChecked(_g('ticket_bc_enabled','0') == '1')
            bt = _g('ticket_bc_type','')
            if bt:
                i = self.cmb_barcode_type.findText(bt)
                if i >= 0: self.cmb_barcode_type.setCurrentIndex(i)
            self.actualizar_vista_previa()
        except Exception as e: logger.debug("load qr cfg: %s", e)

    def _cargar_config_papel(self):
        try:
            cfg = self.container.config_service
            def _g(k, d=""):
                return cfg.get(k) or d
            try: self.spin_paper_w.setValue(int(_g('ticket_paper_width','80')))
            except: pass
            try: self.spin_paper_h.setValue(int(_g('ticket_paper_height','0')))
            except: pass
            f = _g('ticket_font_family','Courier New')
            i = self.cmb_font_family.findText(f)
            if i >= 0: self.cmb_font_family.setCurrentIndex(i)
            try: self.spin_font_base.setValue(int(_g('ticket_font_size','12')))
            except: pass
            try: self.spin_margin_top.setValue(int(_g('ticket_margin_top','5')))
            except: pass
            try: self.spin_margin_side.setValue(int(_g('ticket_margin_side','3')))
            except: pass
        except Exception as e: logger.debug("load paper cfg: %s", e)


    def _layout_repo(self):
        from core.tickets.ticket_layout_repository import TicketLayoutRepository
        return TicketLayoutRepository(db_conn=self.container.db)

    def _on_layout_type_changed(self):
        self.current_layout_type = self.cmb_layout_type.currentData() or "sale_ticket"
        self._aplicar_bloques_por_tipo()
        self.cargar_plantilla_actual()
        self._cargar_layout_activo()
        self.actualizar_vista_previa()

    def _allowed_blocks_for_current_type(self):
        from core.tickets.ticket_layout_config import DEFAULT_BLOCK_ORDER, RAFFLE_BLOCK_ORDER
        layout_type = self.current_layout_type or "sale_ticket"
        return list(RAFFLE_BLOCK_ORDER if layout_type == "raffle_ticket" else DEFAULT_BLOCK_ORDER)

    def _set_sale_only_tabs_enabled(self, enabled: bool):
        tabs = getattr(self, "tabs", None)
        if not tabs:
            return
        for tab in (getattr(self, "tab_loyalty", None), getattr(self, "tab_fomo", None)):
            if tab is not None:
                idx = tabs.indexOf(tab)
                if idx >= 0:
                    tabs.setTabEnabled(idx, bool(enabled))

    def _on_layout_type_changed(self):
        self.current_layout_type = self.cmb_layout_type.currentData() or "sale_ticket"
        self._aplicar_bloques_por_tipo()
        self.cargar_plantilla_actual()
        self._cargar_layout_activo()
        self.actualizar_vista_previa()

    def _aplicar_bloques_por_tipo(self):
        is_raffle = self.current_layout_type == "raffle_ticket"
        self.variables_disponibles = [
            "{{raffle_name}}", "{{numero_boleto}}", "{{cliente_nombre}}", "{{folio_venta}}",
            "{{premio}}", "{{fecha_sorteo}}", "{{qr_code}}", "{{barcode}}", "{{logo}}",
            "{{nombre_empresa}}", "{{direccion}}", "{{telefono}}", "{{footer_message}}", "{{legal_message}}",
        ] if is_raffle else [
            "{{folio}}", "{{fecha}}", "{{cajero}}", "{{cliente_nombre}}",
            "{{items_html}}", "{{total}}", "{{subtotal}}", "{{descuento}}",
            "{{forma_pago}}", "{{cambio}}", "{{puntos_ganados}}",
            "{{puntos_totales}}", "{{mensaje_psicologico}}",
            "{{qr_code}}", "{{barcode}}", "{{logo}}",
            "{{nombre_empresa}}", "{{direccion}}", "{{telefono}}",
            "{{sucursal_nombre}}", "{{sucursal_direccion}}", "{{sucursal_telefono}}",
            "{{whatsapp_empresa}}", "{{rfc_emisor}}", "{{regimen_fiscal}}", "{{web_empresa}}",
            "{{footer_message}}", "{{legal_message}}",
        ]
        if hasattr(self, "lista_variables"):
            self.lista_variables.clear(); self.lista_variables.addItems(self.variables_disponibles)
        self._set_sale_only_tabs_enabled(not is_raffle)
        self._populate_block_list(self._allowed_blocks_for_current_type(), {})
        if hasattr(self, "cmb_qr_dato"):
            self.cmb_qr_dato.clear()
            self.cmb_qr_dato.addItems(
                ["Número de boleto", "Folio de venta", "URL del negocio", "WhatsApp del negocio"]
                if is_raffle else
                ["URL del negocio", "Folio de la venta", "Número de cliente", "WhatsApp del negocio"]
            )
        if hasattr(self, "txt_editor") and not self.txt_editor.toPlainText().strip():
            self.txt_editor.setPlainText(self.obtener_html_defecto())

    def _populate_block_list(self, order, enabled_by_block=None):
        if not hasattr(self, "lst_blocks"):
            return
        enabled_by_block = enabled_by_block or {}
        previous = self.lst_blocks.blockSignals(True)
        try:
            self.lst_blocks.clear()
            for block_name in order:
                item = QListWidgetItem(BLOCK_LABELS.get(block_name, block_name))
                item.setData(Qt.UserRole, block_name)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setCheckState(Qt.Checked if enabled_by_block.get(block_name, True) else Qt.Unchecked)
                self.lst_blocks.addItem(item)
        finally:
            self.lst_blocks.blockSignals(previous)

    def _block_list_state(self):
        order = []
        enabled = {}
        if not hasattr(self, "lst_blocks") or self.lst_blocks.count() == 0:
            for name in self._allowed_blocks_for_current_type():
                order.append(name); enabled[name] = True
            return order, enabled
        for row in range(self.lst_blocks.count()):
            item = self.lst_blocks.item(row)
            name = item.data(Qt.UserRole)
            if not name:
                continue
            order.append(str(name))
            enabled[str(name)] = item.checkState() == Qt.Checked
        return order, enabled

    def _mover_bloque(self, delta: int):
        if not hasattr(self, "lst_blocks"):
            return
        row = self.lst_blocks.currentRow()
        new_row = row + int(delta)
        if row < 0 or new_row < 0 or new_row >= self.lst_blocks.count():
            return
        item = self.lst_blocks.takeItem(row)
        self.lst_blocks.insertItem(new_row, item)
        self.lst_blocks.setCurrentRow(new_row)
        self.actualizar_vista_previa()

    def _cargar_layout_activo(self):
        try:
            cfg = self._layout_repo().load(layout_type=self.current_layout_type)
            self.spin_paper_w.setValue(int(cfg.paper_width_mm or 80))
            self.spin_logo_w.setValue(int(float(cfg.logo_size)) if str(cfg.logo_size).replace('.', '', 1).isdigit() else self.spin_logo_w.value())
            pos = {"center": "Centrado", "left": "Izquierda", "right": "Derecha"}.get(str(cfg.logo_alignment), "Centrado")
            idx = self.cmb_logo_pos.findText(pos)
            if idx >= 0: self.cmb_logo_pos.setCurrentIndex(idx)
            self.chk_logo.setChecked(bool(cfg.show_logo and cfg.blocks.get("logo", None).enabled if cfg.blocks.get("logo") else cfg.show_logo))
            self.chk_qr.setChecked(bool(cfg.show_qr and cfg.blocks.get("qr", None).enabled if cfg.blocks.get("qr") else cfg.show_qr))
            self.chk_barcode.setChecked(bool(cfg.show_barcode and cfg.blocks.get("barcode", None).enabled if cfg.blocks.get("barcode") else cfg.show_barcode))
            self.txt_footer_message.setText(str(getattr(cfg, "footer_message", "") or ""))
            self.txt_legal_message.setText(str(getattr(cfg, "legal_message", "") or ""))
            allowed = self._allowed_blocks_for_current_type()
            ordered = [name for name in list(cfg.block_order or allowed) if name in allowed]
            ordered += [name for name in allowed if name not in ordered]
            enabled = {name: bool(cfg.blocks.get(name).enabled) for name in cfg.blocks if name in allowed}
            self._populate_block_list(ordered, enabled)
        except Exception as e:
            logger.debug("load active layout: %s", e)

    def _layout_config_from_controls(self):
        from core.tickets.ticket_layout_config import TicketLayoutConfig, TicketLayoutBlock, DEFAULT_BLOCK_ORDER, RAFFLE_BLOCK_ORDER
        layout_type = self.current_layout_type or "sale_ticket"
        # Keep this expression explicit: raffle_ticket uses only RAFFLE_BLOCK_ORDER; sale_ticket uses DEFAULT_BLOCK_ORDER.
        default_order = list(RAFFLE_BLOCK_ORDER if layout_type == "raffle_ticket" else DEFAULT_BLOCK_ORDER)
        order, enabled = self._block_list_state()
        order = [name for name in order if name in default_order]
        order += [name for name in default_order if name not in order]
        cfg = TicketLayoutConfig.for_layout_type(layout_type) if layout_type == "raffle_ticket" else TicketLayoutConfig()
        cfg.paper_width_mm = int(self.spin_paper_w.value())
        cfg.logo_size = str(self.spin_logo_w.value())
        cfg.logo_alignment = {"Centrado": "center", "Izquierda": "left", "Derecha": "right"}.get(self.cmb_logo_pos.currentText(), "center")
        cfg.show_logo = bool(self.chk_logo.isChecked()) and bool(enabled.get("logo", True))
        cfg.show_qr = bool(self.chk_qr.isChecked()) and bool(enabled.get("qr", True))
        cfg.show_barcode = bool(self.chk_barcode.isChecked()) and bool(enabled.get("barcode", True))
        cfg.show_customer = bool(enabled.get("customer", True))
        cfg.footer_message = self.txt_footer_message.text().strip()
        cfg.legal_message = self.txt_legal_message.text().strip()
        cfg.block_order = order
        cfg.blocks = {name: TicketLayoutBlock(enabled=bool(enabled.get(name, True)), order=i) for i, name in enumerate(order)}
        for name, flag in (("logo", cfg.show_logo), ("qr", cfg.show_qr), ("barcode", cfg.show_barcode), ("customer", cfg.show_customer)):
            if name in cfg.blocks:
                cfg.blocks[name].enabled = bool(flag)
        if layout_type == "sale_ticket":
            cfg.show_loyalty = bool(enabled.get("loyalty", True)); cfg.show_fomo = bool(enabled.get("fomo", True))
        else:
            cfg.show_loyalty = False; cfg.show_fomo = False
        return cfg

    def _guardar_layout_activo(self):
        try:
            layout_type = self.current_layout_type or "sale_ticket"
            cfg = self._layout_config_from_controls()
            self._layout_repo().save(cfg, layout_type=layout_type)
        except Exception as e:
            logger.warning("save active layout: %s", e)

    # ══════════════════════════════════════════════════════════════════════
    #  Guardar
    # ══════════════════════════════════════════════════════════════════════

    def _guardar_todo(self):
        try:
            cfg = self.container.config_service
            cfg.set(self._template_config_key(), self.txt_editor.toPlainText())
            u = lambda k, v: cfg.set(k, v)
            u('ticket_logo_b64', self._logo_b64)
            if self.current_layout_type == "sale_ticket":
                u('ticket_logo_width', str(self.spin_logo_w.value()))
                u('ticket_logo_pos', self.cmb_logo_pos.currentText())
                u('ticket_qr_enabled', '1' if self.chk_qr.isChecked() else '0')
                u('ticket_qr_dato', self.cmb_qr_dato.currentText())
                u('ticket_qr_url', self.txt_qr_url.text().strip())
                u('ticket_qr_size', str(self.spin_qr_size.value()))
                u('ticket_bc_enabled', '1' if self.chk_barcode.isChecked() else '0')
                u('ticket_bc_type', self.cmb_barcode_type.currentText())
                u('ticket_paper_width', str(self.spin_paper_w.value()))
                u('ticket_paper_height', str(self.spin_paper_h.value()))
                u('ticket_font_family', self.cmb_font_family.currentText())
                u('ticket_font_size', str(self.spin_font_base.value()))
                u('ticket_margin_top', str(self.spin_margin_top.value()))
                u('ticket_margin_side', str(self.spin_margin_side.value()))
            self._guardar_layout_activo()
            QMessageBox.information(self, "✅ Guardado", "Plantilla, medios y papel guardados.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ══════════════════════════════════════════════════════════════════════
    #  Editor y vista previa
    # ══════════════════════════════════════════════════════════════════════

    def insertar_variable(self, item):
        self.txt_editor.insertPlainText(item.text())
        self.txt_editor.setFocus()

    def _template_config_key(self):
        return "raffle_ticket_template_html" if self.current_layout_type == "raffle_ticket" else "ticket_template_html"

    def cargar_plantilla_actual(self):
        key = self._template_config_key()
        try: plantilla = self.container.config_service.get(key, self.obtener_html_defecto())
        except: plantilla = self.obtener_html_defecto()
        self.txt_editor.setPlainText(plantilla or self.obtener_html_defecto())
        self.actualizar_vista_previa()

    def guardar_plantilla(self):
        try:
            self.container.config_service.set(self._template_config_key(), self.txt_editor.toPlainText())
            QMessageBox.information(self, "✅", "Plantilla guardada.")
        except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def actualizar_vista_previa(self):
        plantilla = self.txt_editor.toPlainText()

        # Logo con posición
        logo_pos = self.cmb_logo_pos.currentText() if hasattr(self, 'cmb_logo_pos') else "Centrado"
        align = {"Centrado":"center","Izquierda":"left","Derecha":"right"}.get(logo_pos,"center")
        logo_w = self.spin_logo_w.value() if hasattr(self, 'spin_logo_w') else 150
        if self._logo_b64 and (not hasattr(self, 'chk_logo') or self.chk_logo.isChecked()):
            logo_html = f'<div style="text-align:{align};"><img src="{self._logo_b64}" width="{logo_w}px"></div>'
        else:
            logo_html = '<div style="text-align:center;color:#aaa;font-size:10px;border:1px dashed #ccc;padding:10px;">[Logo — cargar en pestaña Medios]</div>'

        # QR
        qr_html = ''
        if hasattr(self, 'chk_qr') and self.chk_qr.isChecked():
            qr_url = self.txt_qr_url.text().strip() if hasattr(self,'txt_qr_url') else ''
            qr_size = self.spin_qr_size.value() if hasattr(self,'spin_qr_size') else 100
            qr_content = qr_url or ('1-99998-1' if self.current_layout_type == 'raffle_ticket' else 'V-99998')
            qr_dato = self.cmb_qr_dato.currentText() if hasattr(self,'cmb_qr_dato') else ''
            try:
                import io as _io, qrcode as _qrc
                qr = _qrc.QRCode(version=1, box_size=4, border=1)
                qr.add_data(qr_content); qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buf = _io.BytesIO(); img.save(buf, format='PNG')
                qr_b64 = base64.b64encode(buf.getvalue()).decode()
                qr_html = f'<div style="text-align:center;"><img src="data:image/png;base64,{qr_b64}" width="{qr_size}px"><br><small>{qr_dato}</small></div>'
            except ImportError:
                qr_html = f'<div style="text-align:center;background:#eee;padding:6px;font-size:9px;">📱 QR: {qr_content}</div>'
            except: qr_html = '<div style="text-align:center;background:#eee;padding:6px;">📱 QR</div>'

        barcode_html = ''
        if hasattr(self, 'chk_barcode') and self.chk_barcode.isChecked():
            bc = self.cmb_barcode_type.currentText() if hasattr(self,'cmb_barcode_type') else 'Code128'
            bc_value = '1-99998-1' if self.current_layout_type == 'raffle_ticket' else 'V-99998'
            barcode_html = f'<div style="text-align:center;background:#f5f5f5;padding:4px;font-family:monospace;font-size:9px;">||||||||||||| {bc_value} |||||||||||||<br><small>{bc}</small></div>'

        font_fam = self.cmb_font_family.currentText() if hasattr(self,'cmb_font_family') else 'Courier New'
        font_sz = self.spin_font_base.value() if hasattr(self,'spin_font_base') else 12
        paper_w = self.spin_paper_w.value() if hasattr(self,'spin_paper_w') else 80

        dummy = {
            'folio':'V-99998','fecha':'2026-10-25 14:30','cajero':'Cajero Demo',
            'cliente_nombre':'Juan Pérez','total':'$250.50','subtotal':'$250.50',
            'descuento':'$0.00','forma_pago':'Efectivo','cambio':'$49.50',
            'puntos_ganados':'25','puntos_totales':'125',
            'mensaje_psicologico':'⭐ ¡Gracias por tu compra!',
            'raffle_name':'Sorteo Navidad SPJ','numero_boleto':'1-99998-1',
            'folio_venta':'V-99998','premio':'Cena familiar','fecha_sorteo':'2026-12-24',
            'footer_message': self.txt_footer_message.text().strip() if hasattr(self, 'txt_footer_message') else '',
            'legal_message': self.txt_legal_message.text().strip() if hasattr(self, 'txt_legal_message') else '',
            'logo':logo_html,'qr_code':qr_html,'barcode':barcode_html,
            'nombre_empresa':'SPJ POS','direccion':'Calle 1 #123',
            'telefono':'+52 614 123 4567',
            'items_html':'<tr><td>Pechuga</td><td>1.5kg</td><td>$150.00</td></tr>'
                         '<tr><td>Pierna</td><td>2.0kg</td><td>$120.00</td></tr>',
        }
        try:
            if self.current_layout_type == "raffle_ticket":
                raise RuntimeError("preview directo de boleto de sorteo")
            html = self.container.ticket_template_engine.generar_ticket(
                plantilla, {'folio':dummy['folio'],'cajero':dummy['cajero'],
                    'fecha':dummy['fecha'],'cliente':'Juan Pérez',
                    'totales':{'total_final':250.50,'subtotal':250.50,'descuento':0},
                    'items':[{'nombre':'Pechuga','cantidad':1.5,'precio_unitario':100,'total':150},
                             {'nombre':'Pierna','cantidad':2.0,'precio_unitario':60,'total':120}],
                    'efectivo_recibido':300,'cambio':49.50,'forma_pago':'Efectivo',
                    'puntos_ganados':25,'puntos_totales':125}, '⭐ ¡Gracias!')
        except:
            html = plantilla
            for k, v in dummy.items(): html = html.replace('{{'+k+'}}', str(v))
        wrapper = f'<div style="font-family:\'{font_fam}\',monospace;font-size:{font_sz}px;max-width:{paper_w*3}px;margin:auto;">{html}</div>'
        self.visor_preview.setHtml(wrapper)
        self._actualizar_preview_escpos(dummy)

    def _actualizar_preview_escpos(self, dummy: dict):
        try:
            layout_cfg = self._layout_config_from_controls() if hasattr(self, "lst_blocks") else None
            if self.current_layout_type == "raffle_ticket":
                from core.tickets.raffle_ticket_renderer import RaffleTicketESCPOSRenderer
                payload = {
                    "empresa": dummy.get("nombre_empresa", "SPJ POS"),
                    "direccion": dummy.get("direccion", ""),
                    "telefono": dummy.get("telefono", ""),
                    "raffle_name": dummy.get("raffle_name", "Sorteo"),
                    "numero_boleto": dummy.get("numero_boleto", "1-99998-1"),
                    "cliente": dummy.get("cliente_nombre", ""),
                    "folio_venta": dummy.get("folio_venta", "V-99998"),
                    "premio": dummy.get("premio", ""),
                    "fecha_sorteo": dummy.get("fecha_sorteo", ""),
                    "footer_message": dummy.get("footer_message", ""),
                    "legal_message": dummy.get("legal_message", ""),
                    "layout_config": layout_cfg.to_dict() if layout_cfg else {"paper_width_mm": self.spin_paper_w.value()},
                }
                txt = RaffleTicketESCPOSRenderer(paper_width_mm=self.spin_paper_w.value()).render_text_preview(payload, layout_cfg)
            else:
                from core.ticket_escpos_renderer import TicketESCPOSRenderer
                payload = {
                    "empresa": dummy.get("nombre_empresa", "SPJ POS"),
                    "direccion": dummy.get("direccion", ""),
                    "telefono": dummy.get("telefono", ""),
                    "folio": dummy.get("folio", "V-99998"),
                    "fecha": dummy.get("fecha", ""),
                    "cajero": dummy.get("cajero", ""),
                    "cliente": dummy.get("cliente_nombre", ""),
                    "items": [
                        {"nombre": "Pechuga", "cantidad": 1.5, "total": 150},
                        {"nombre": "Pierna", "cantidad": 2.0, "total": 120},
                    ],
                    "totales": {"total_final": 250.50},
                    "layout_config": layout_cfg.to_dict() if layout_cfg else {"paper_width_mm": self.spin_paper_w.value()},
                }
                txt = TicketESCPOSRenderer(paper_width_mm=self.spin_paper_w.value()).render_text_preview(payload)
            self.txt_preview_escpos.setPlainText(txt)
        except Exception as e:
            self.txt_preview_escpos.setPlainText(f"[preview escpos no disponible] {e}")

    def _abrir_configuracion_sistema(self):
        QMessageBox.information(
            self,
            "Identidad del sistema",
            "Para cambiar logo/nombre/dirección oficiales, use el módulo Configuración del Sistema.",
        )

    def restaurar_defecto(self):
        if QMessageBox.question(self,"Confirmar","¿Restaurar plantilla original?") == QMessageBox.Yes:
            self.txt_editor.setPlainText(self.obtener_html_defecto())

    def obtener_html_defecto(self):
        if self.current_layout_type == "raffle_ticket":
            return """<div style="text-align:center;max-width:300px;margin:auto;">
{{logo}}
<h2 style="margin:4px 0;">{{nombre_empresa}}</h2>
<p style="font-size:10px;margin:2px 0;">{{direccion}}<br>Tel: {{telefono}}</p>
<hr style="border:none;border-top:1px dashed #000;">
<h2>{{raffle_name}}</h2>
<p style="font-size:18px;"><b>{{numero_boleto}}</b></p>
<p>Cliente: {{cliente_nombre}}<br>Venta: {{folio_venta}}</p>
<p>Premio: {{premio}}<br>Sorteo: {{fecha_sorteo}}</p>
{{qr_code}}
{{barcode}}
<p style="font-size:10px;">{{footer_message}}</p>
<p style="font-size:9px;">{{legal_message}}</p>
</div>"""
        return """<div style="text-align:center;max-width:300px;margin:auto;">
{{logo}}
<h2 style="margin:4px 0;">{{nombre_empresa}}</h2>
<p style="font-size:10px;margin:2px 0;">
Sucursal: {{sucursal_nombre}}<br>
{{sucursal_direccion}}<br>
Tel: {{sucursal_telefono}}<br>
WhatsApp: {{whatsapp_empresa}}<br>
RFC: {{rfc_emisor}}<br>
Régimen: {{regimen_fiscal}}
</p>
<hr style="border:none;border-top:1px dashed #000;">
<p>Ticket: <b>{{folio}}</b><br>{{fecha}}<br>Cajero: {{cajero}}</p>
<hr style="border:none;border-top:1px dashed #000;">
<table width="100%" style="font-size:11px;">
  <tr><th align="left">Producto</th><th>Cant</th><th align="right">Total</th></tr>
  {{items_html}}
</table>
<hr style="border:none;border-top:1px dashed #000;">
<table width="100%" style="font-size:12px;">
  <tr><td>Subtotal:</td><td align="right">{{subtotal}}</td></tr>
  <tr><td>Descuento:</td><td align="right">{{descuento}}</td></tr>
  <tr><td><b>TOTAL:</b></td><td align="right"><b>{{total}}</b></td></tr>
  <tr><td>Pagó:</td><td align="right">{{forma_pago}}</td></tr>
  <tr><td>Recibido:</td><td align="right">{{recibido}}</td></tr>
  <tr><td>Cambio:</td><td align="right">{{cambio}}</td></tr>
</table>
<hr style="border:none;border-top:1px dashed #000;">
<p style="font-size:10px;">Cliente: {{cliente_nombre}}<br>
Puntos: +{{puntos_ganados}} | Total: {{puntos_totales}}</p>
{{qr_code}}
{{barcode}}
<p style="font-style:italic;font-size:10px;">{{mensaje_psicologico}}</p>
</div>"""

    # ══════════════════════════════════════════════════════════════════════
    #  Imprimir muestra
    # ══════════════════════════════════════════════════════════════════════

    def _imprimir_muestra(self):
        try:
            printer_svc = getattr(self.container, "printer_service", None)
            if not printer_svc or not printer_svc.has_ticket_printer():
                QMessageBox.warning(self, "Aviso", "No hay impresora térmica ESC/POS configurada.")
                return

            if self.current_layout_type == "raffle_ticket":
                sample_ticket = {
                    "ticket_type": "raffle_ticket",
                    "raffle_name": "Sorteo Navidad SPJ",
                    "numero_boleto": "1-99998-1",
                    "cliente": "Cliente muestra",
                    "folio_venta": "TST-ESC-POS",
                    "premio": "Cena familiar",
                    "fecha_sorteo": "2026-12-24",
                    "qr_content": "RAFFLE:1|SALE:TST-ESC-POS|TICKET:1-99998-1",
                    "barcode": "1-99998-1",
                    "layout_config": self._layout_config_from_controls().to_dict(),
                }
                printer_svc.print_raffle_ticket(sample_ticket)
            else:
                sample_ticket = {
                    "folio": "TST-ESC-POS",
                    "fecha": "2026-01-01 12:00:00",
                    "cajero": "Diseñador",
                    "cliente": "Cliente muestra",
                    "items": [
                        {"nombre": "Producto Demo", "cantidad": 1, "precio_unitario": 100, "total": 100},
                    ],
                    "totales": {"subtotal": 100, "descuento": 0, "total_final": 100},
                    "forma_pago": "Prueba",
                    "plantilla": "ticket_designer_sample",
                    "layout_config": self._layout_config_from_controls().to_dict(),
                }
                printer_svc.print_ticket(sample_ticket)
            QMessageBox.information(self, "✅ Impreso", "Muestra enviada a impresora térmica ESC/POS.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
