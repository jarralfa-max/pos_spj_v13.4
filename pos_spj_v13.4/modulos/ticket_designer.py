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
    QDoubleSpinBox, QScrollArea, QFrame,
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


class ModuloTicketDesigner(QWidget):

    variables_disponibles = [
        "{{folio}}", "{{fecha}}", "{{cajero}}", "{{cliente_nombre}}",
        "{{items_html}}", "{{total}}", "{{subtotal}}", "{{descuento}}",
        "{{forma_pago}}", "{{cambio}}", "{{puntos_ganados}}",
        "{{puntos_totales}}", "{{mensaje_psicologico}}",
        "{{qr_code}}", "{{barcode}}", "{{logo}}",
        "{{nombre_empresa}}", "{{direccion}}", "{{telefono}}",
    ]

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container = container
        self._logo_b64 = ""
        self.init_ui()
        self.cargar_plantilla_actual()
        self._cargar_logo_guardado()
        self._cargar_config_qr_guardada()
        self._cargar_config_papel()

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
        
        header.addWidget(btn_print)
        header.addWidget(btn_save_all)
        lay.addLayout(header)

        tabs = QTabWidget()
        tabs.setObjectName("tabWidget")
        lay.addWidget(tabs)

        # Tab 1: Diseño
        tab_design = QWidget()
        tabs.addTab(tab_design, "✍️ Diseño de Plantilla")
        self._build_tab_design(tab_design)

        # Tab 2: Medios
        tab_media = QWidget()
        tabs.addTab(tab_media, "🖼️ Logo / QR / Barcode")
        self._build_tab_media(tab_media)

        # Tab 3: Papel
        tab_paper = QWidget()
        tabs.addTab(tab_paper, "📐 Papel / Impresión")
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
        splitter.addWidget(grp_vars)

        grp_ed = QGroupBox("📝 Plantilla HTML")
        grp_ed.setObjectName("styledGroup")
        le = QVBoxLayout(grp_ed)
        self.txt_editor = QPlainTextEdit()
        self.txt_editor.setFont(QFont("Courier New", 10))
        self.txt_editor.setObjectName("codeEditor")
        self.txt_editor.textChanged.connect(self.actualizar_vista_previa)
        le.addWidget(self.txt_editor)
        btn_rest = QPushButton("🔄 Restaurar")
        btn_rest = create_secondary_button(self, btn_rest, "Restaurar plantilla por defecto")
        btn_rest.clicked.connect(self.restaurar_defecto)
        le.addWidget(btn_rest)
        splitter.addWidget(grp_ed)

        grp_prev = QGroupBox("👁️ Vista Previa")
        grp_prev.setObjectName("styledGroup")
        lp = QVBoxLayout(grp_prev)
        self.visor_preview = QTextBrowser()
        self.visor_preview.setObjectName("previewBox")
        self.visor_preview.setMaximumWidth(350)
        self.visor_preview.setMinimumWidth(280)
        lp.addWidget(self.visor_preview)
        splitter.addWidget(grp_prev)
        splitter.setSizes([160, 440, 340])

    def _build_tab_media(self, parent):
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        content = QWidget(); lm = QVBoxLayout(content); lm.setSpacing(Spacing.MD)

        # Logo
        grp_logo = QGroupBox("Logo de la empresa")
        grp_logo.setObjectName("styledGroup")
        fl = QFormLayout(grp_logo)
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
        btn_lr.addWidget(btn_logo); btn_lr.addWidget(btn_clear)
        fl.addRow("", btn_lr)
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
        self.chk_barcode = QCheckBox("Incluir barcode (folio)")
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
            self._logo_b64 = f"data:image/{mime};base64,{base64.b64encode(data).decode()}"
            self._mostrar_logo_thumbnail(data)
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
            db = self.container.db
            row = db.execute("SELECT valor FROM configuraciones WHERE clave='ticket_logo_b64'").fetchone()
            if row and row[0]:
                self._logo_b64 = row[0]
                self._mostrar_logo_thumbnail()
                w = db.execute("SELECT valor FROM configuraciones WHERE clave='ticket_logo_width'").fetchone()
                if w and w[0]: self.spin_logo_w.setValue(int(w[0]))
                p = db.execute("SELECT valor FROM configuraciones WHERE clave='ticket_logo_pos'").fetchone()
                if p and p[0]:
                    idx = self.cmb_logo_pos.findText(p[0])
                    if idx >= 0: self.cmb_logo_pos.setCurrentIndex(idx)
        except Exception: pass

    def _cargar_config_qr_guardada(self):
        try:
            db = self.container.db
            def _g(k, d=""):
                r = db.execute("SELECT valor FROM configuraciones WHERE clave=?", (k,)).fetchone()
                return r[0] if r and r[0] else d
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
            db = self.container.db
            def _g(k, d=""):
                r = db.execute("SELECT valor FROM configuraciones WHERE clave=?", (k,)).fetchone()
                return r[0] if r and r[0] else d
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

    # ══════════════════════════════════════════════════════════════════════
    #  Guardar
    # ══════════════════════════════════════════════════════════════════════

    def _guardar_todo(self):
        try:
            db = self.container.db
            self.container.config_service.set('ticket_template_html', self.txt_editor.toPlainText())
            u = lambda k, v: db.execute(
                "INSERT INTO configuraciones(clave,valor) VALUES(?,?) ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor", (k, v))
            u('ticket_logo_b64', self._logo_b64)
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
            try: db.commit()
            except: pass
            QMessageBox.information(self, "✅ Guardado", "Plantilla, medios y papel guardados.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ══════════════════════════════════════════════════════════════════════
    #  Editor y vista previa
    # ══════════════════════════════════════════════════════════════════════

    def insertar_variable(self, item):
        self.txt_editor.insertPlainText(item.text())
        self.txt_editor.setFocus()

    def cargar_plantilla_actual(self):
        try: plantilla = self.container.config_service.get('ticket_template_html', self.obtener_html_defecto())
        except: plantilla = self.obtener_html_defecto()
        self.txt_editor.setPlainText(plantilla)
        self.actualizar_vista_previa()

    def guardar_plantilla(self):
        try:
            self.container.config_service.set('ticket_template_html', self.txt_editor.toPlainText())
            QMessageBox.information(self, "✅", "Plantilla guardada.")
        except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def actualizar_vista_previa(self):
        plantilla = self.txt_editor.toPlainText()

        # Logo con posición
        logo_pos = self.cmb_logo_pos.currentText() if hasattr(self, 'cmb_logo_pos') else "Centrado"
        align = {"Centrado":"center","Izquierda":"left","Derecha":"right"}.get(logo_pos,"center")
        logo_w = self.spin_logo_w.value() if hasattr(self, 'spin_logo_w') else 150
        if self._logo_b64:
            logo_html = f'<div style="text-align:{align};"><img src="{self._logo_b64}" width="{logo_w}px"></div>'
        else:
            logo_html = '<div style="text-align:center;color:#aaa;font-size:10px;border:1px dashed #ccc;padding:10px;">[Logo — cargar en pestaña Medios]</div>'

        # QR
        qr_html = ''
        if hasattr(self, 'chk_qr') and self.chk_qr.isChecked():
            qr_url = self.txt_qr_url.text().strip() if hasattr(self,'txt_qr_url') else ''
            qr_size = self.spin_qr_size.value() if hasattr(self,'spin_qr_size') else 100
            qr_content = qr_url or 'V-99998'
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
            barcode_html = f'<div style="text-align:center;background:#f5f5f5;padding:4px;font-family:monospace;font-size:9px;">||||||||||||| V-99998 |||||||||||||<br><small>{bc}</small></div>'

        font_fam = self.cmb_font_family.currentText() if hasattr(self,'cmb_font_family') else 'Courier New'
        font_sz = self.spin_font_base.value() if hasattr(self,'spin_font_base') else 12
        paper_w = self.spin_paper_w.value() if hasattr(self,'spin_paper_w') else 80

        dummy = {
            'folio':'V-99998','fecha':'2026-10-25 14:30','cajero':'Cajero Demo',
            'cliente_nombre':'Juan Pérez','total':'$250.50','subtotal':'$250.50',
            'descuento':'$0.00','forma_pago':'Efectivo','cambio':'$49.50',
            'puntos_ganados':'25','puntos_totales':'125',
            'mensaje_psicologico':'⭐ ¡Gracias por tu compra!',
            'logo':logo_html,'qr_code':qr_html,'barcode':barcode_html,
            'nombre_empresa':'SPJ POS','direccion':'Calle 1 #123',
            'telefono':'+52 614 123 4567',
            'items_html':'<tr><td>Pechuga</td><td>1.5kg</td><td>$150.00</td></tr>'
                         '<tr><td>Pierna</td><td>2.0kg</td><td>$120.00</td></tr>',
        }
        try:
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

    def restaurar_defecto(self):
        if QMessageBox.question(self,"Confirmar","¿Restaurar plantilla original?") == QMessageBox.Yes:
            self.txt_editor.setPlainText(self.obtener_html_defecto())

    def obtener_html_defecto(self):
        return """<div style="text-align:center;max-width:300px;margin:auto;">
{{logo}}
<h2 style="margin:4px 0;">{{nombre_empresa}}</h2>
<p style="font-size:10px;margin:2px 0;">{{direccion}}<br>Tel: {{telefono}}</p>
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
            from PyQt5.QtPrintSupport import QPrinter, QPrintDialog, QPrinterInfo
            from PyQt5.QtGui import QTextDocument
            from PyQt5.QtCore import QSizeF

            html = self.visor_preview.toHtml()
            if not html or not html.strip():
                QMessageBox.warning(self, "Aviso", "No hay contenido."); return

            doc = QTextDocument(); doc.setHtml(html)
            pw = self.spin_paper_w.value()
            ph = self.spin_paper_h.value() or 297
            mt = self.spin_margin_top.value()
            ms = self.spin_margin_side.value()

            dp = QPrinterInfo.defaultPrinter()
            if dp and not dp.isNull():
                printer = QPrinter(dp, QPrinter.HighResolution)
            else:
                printer = QPrinter(QPrinter.HighResolution)
                dlg = QPrintDialog(printer, self)
                if dlg.exec_() != QPrintDialog.Accepted: return

            printer.setPageSize(QPrinter.Custom)
            printer.setPageSizeMM(QSizeF(pw, ph))
            printer.setPageMargins(ms, mt, ms, mt, QPrinter.Millimeter)
            doc.print_(printer)
            pn = dp.printerName() if dp and not dp.isNull() else "impresora"
            QMessageBox.information(self, "✅ Impreso",
                f"Muestra enviada a: {pn}\nPapel: {pw}×{ph}mm")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
