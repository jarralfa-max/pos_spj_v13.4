# modulos/etiquetas.py — SPJ POS v13
"""
Módulo de diseño e impresión de etiquetas de empaque.

Flujo:
  Seleccionar producto → ingresar peso/lote/fecha → 
  vista previa → imprimir (Zebra/TSC/PDF)

Campos en la etiqueta:
  Nombre del corte, Peso neto, Precio/kg, Precio total,
  Número de lote, Fecha de empaque, Fecha de caducidad,
  QR de trazabilidad, Código de barras (EAN/SKU)
"""
from __future__ import annotations
from modulos.spj_styles import spj_btn, apply_btn_styles
from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import (
    create_primary_button, create_success_button, create_secondary_button,
    create_input, create_combo, apply_tooltip,
    PageHeader, Toast,
)
import logging
import os
from datetime import date, timedelta

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QDoubleSpinBox,
    QComboBox, QGroupBox, QMessageBox, QSpinBox,
    QDateEdit, QCheckBox, QFileDialog, QSplitter,
    QScrollArea, QFrame, QCompleter, QTabWidget
)
from PyQt5.QtCore import QDate, QStringListModel
from core.events.event_bus import get_bus, AJUSTE_INVENTARIO, VENTA_COMPLETADA

logger = logging.getLogger("spj.etiquetas")

# Tamaños de etiqueta estándar (mm)
TAMAÑOS = {
    "Pequeña 50×30":  (50, 30),
    "Estándar 80×50": (80, 50),
    "Grande 100×70":  (100, 70),
    "Personalizada":  (0, 0),
}


class EtiquetaPreview(QLabel):
    """Vista previa profesional de la etiqueta con código de barras y QR."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nombre_negocio = "SPJ"
        self.datos = {}
        self.opciones = {
            "mostrar_qr": True,
            "mostrar_barcode": True,
            "mostrar_logo": False,
            "tipo_barcode": "Code128",
        }
        self.setFixedSize(360, 220)
        self.setFrameStyle(QFrame.Box)
        self._render()

    def set_opciones(self, opciones: dict):
        self.opciones.update(opciones)
        self._render()

    def actualizar(self, datos: dict):
        self.datos = datos
        self._render()

    def _render(self):
        from PyQt5.QtGui import QPainter, QColor, QPen, QBrush
        d = self.datos
        pix = QPixmap(360, 220)
        pix.fill(QColor("white"))
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)

        # ── Borde con esquinas redondeadas ────────────────────────────────
        p.setPen(QPen(QColor("#555"), 1.5))
        p.setBrush(QBrush(QColor("white")))
        p.drawRoundedRect(2, 2, 356, 216, 6, 6)

        # ── Font sizes from design controls ───────────────────────────────
        fn_nombre  = d.get("font_nombre", 12)
        fn_precio  = d.get("font_precio", 18)
        fn_detalle = d.get("font_detalle", 8)

        # ── Encabezado: nombre del negocio ────────────────────────────────
        negocio = d.get("nombre_negocio", self._nombre_negocio)
        p.setFont(QFont("Arial", 7))
        p.setPen(QColor("#999"))
        p.drawText(8, 6, 200, 14, Qt.AlignLeft | Qt.AlignVCenter, negocio)

        # ── Nombre del producto (tamaño configurable) ─────────────────────
        nombre = d.get("nombre", "Nombre del producto")[:32]
        p.setFont(QFont("Arial", fn_nombre, QFont.Bold))
        p.setPen(QColor("#1a1a1a"))
        p.drawText(8, 20, 340, fn_nombre + 12, Qt.AlignLeft | Qt.AlignVCenter, nombre)

        # ── Línea separadora ──────────────────────────────────────────────
        sep_y = 22 + fn_nombre + 10
        p.setPen(QPen(QColor("#ddd"), 1))
        p.drawLine(8, sep_y, 352, sep_y)

        # ── Precio total (tamaño configurable, rojo) ─────────────────────
        cantidad = float(d.get("cantidad", d.get("peso_kg", 0)))
        precio   = float(d.get("precio_unitario", d.get("precio_kg", 0)))
        unidad   = d.get("unidad", "kg")
        total    = round(cantidad * precio, 2)

        price_y = sep_y + 4
        p.setFont(QFont("Arial", fn_precio, QFont.Bold))
        p.setPen(QColor("#c0392b"))
        p.drawText(8, price_y, 180, fn_precio + 10, Qt.AlignLeft, f"${total:.2f}")

        # ── Cantidad, unidad y precio unitario ────────────────────────────
        detail_y = price_y + fn_precio + 12
        p.setFont(QFont("Arial", fn_detalle))
        p.setPen(QColor("#555"))
        p.drawText(8, detail_y, 180, 14, Qt.AlignLeft,
                   f"{cantidad:.3f} {unidad}")
        p.drawText(8, detail_y + 14, 180, 14, Qt.AlignLeft,
                   f"${precio:.2f}/{unidad}")

        # ── Lote y fechas ─────────────────────────────────────────────────
        lote  = d.get("lote", "")
        sku   = d.get("sku", "")
        f_emp = d.get("fecha_empaque", str(date.today()))
        f_cad = d.get("fecha_caducidad", "")

        p.setFont(QFont("Arial", fn_detalle))
        p.setPen(QColor("#333"))
        info_y = detail_y + 32
        if lote:
            p.drawText(8, info_y, 180, 12, Qt.AlignLeft, f"Lote: {lote}")
            info_y += 13
        if sku:
            p.drawText(8, info_y, 180, 12, Qt.AlignLeft, f"SKU: {sku}")
            info_y += 13
        p.drawText(8, info_y, 180, 12, Qt.AlignLeft, f"Emp: {f_emp}")
        info_y += 13
        if f_cad:
            p.setFont(QFont("Arial", fn_detalle, QFont.Bold))
            p.setPen(QColor("#c0392b"))
            p.drawText(8, info_y, 180, 12, Qt.AlignLeft, f"Cad: {f_cad}")

        # ── QR Code (lado derecho superior) ───────────────────────────────
        qr_x, qr_y, qr_size = 260, 50, 80
        if self.opciones.get("mostrar_qr", True):
            qr_rendered = False
            try:
                import qrcode as _qrc
                import io as _io
                qr_content = lote or nombre[:20] or "SPJ"
                qr = _qrc.QRCode(version=1, box_size=2, border=1)
                qr.add_data(f"SPJ:{qr_content}")
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buf = _io.BytesIO()
                img.save(buf, format='PNG')
                buf.seek(0)
                qr_pix = QPixmap()
                qr_pix.loadFromData(buf.getvalue())
                if not qr_pix.isNull():
                    p.drawPixmap(qr_x, qr_y, qr_size, qr_size,
                                 qr_pix.scaled(qr_size, qr_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    qr_rendered = True
            except ImportError:
                pass
            except Exception:
                pass

            if not qr_rendered:
                # Fallback: dibujar QR placeholder con patrón
                p.setPen(QPen(QColor("#333"), 1))
                p.setBrush(QBrush(QColor("#f8f8f8")))
                p.drawRect(qr_x, qr_y, qr_size, qr_size)
                # Dibujar patrón de esquinas tipo QR
                for ox, oy in [(0, 0), (56, 0), (0, 56)]:
                    p.setBrush(QBrush(QColor("#333")))
                    p.drawRect(qr_x + ox + 4, qr_y + oy + 4, 20, 20)
                    p.setBrush(QBrush(QColor("white")))
                    p.drawRect(qr_x + ox + 8, qr_y + oy + 8, 12, 12)
                    p.setBrush(QBrush(QColor("#333")))
                    p.drawRect(qr_x + ox + 11, qr_y + oy + 11, 6, 6)
                p.setFont(QFont("Arial", 6))
                p.setPen(QColor("#999"))
                p.drawText(qr_x, qr_y + qr_size + 2, qr_size, 12, Qt.AlignCenter, "QR Trazabilidad")

        # ── Código de barras (parte inferior) ─────────────────────────────
        if self.opciones.get("mostrar_barcode", True):
            bc_x, bc_y, bc_w, bc_h = 8, 180, 200, 32
            bc_content = lote or nombre[:12] or "000000000"
            # Dibujar barras simuladas Code128
            p.setPen(Qt.NoPen)
            import hashlib
            hash_bytes = hashlib.md5(bc_content.encode()).digest()
            x = bc_x
            for i, byte_val in enumerate(hash_bytes):
                if x >= bc_x + bc_w:
                    break
                bar_w = 1 + (byte_val % 3)
                if byte_val % 2 == 0:
                    p.setBrush(QBrush(QColor("black")))
                    p.drawRect(x, bc_y, bar_w, bc_h - 10)
                x += bar_w + 1
            # Texto debajo
            p.setFont(QFont("Courier New", 7))
            p.setPen(QColor("#333"))
            tipo_bc = self.opciones.get("tipo_barcode", "Code128")
            p.drawText(bc_x, bc_y + bc_h - 8, bc_w, 12, Qt.AlignCenter,
                        bc_content[:20])

        p.end()
        self.setPixmap(pix)


class ModuloEtiquetas(QWidget):

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container   = container
        self.db          = container.db
        self.usuario     = ""
        self.sucursal_id = getattr(container, 'sucursal_id', 1)
        self._nombre_negocio = "SPJ"
        self._productos_cache = []   # [(id, nombre, precio, unidad)]
        self._selected_product_id = None
        self._build_ui()
        self._cargar_config()
        self._cargar_productos()
        try:
            bus = get_bus()
            bus.subscribe(AJUSTE_INVENTARIO, self._on_stock_actualizado, label="etiquetas.stock.ajuste")
            bus.subscribe(VENTA_COMPLETADA, self._on_stock_actualizado, label="etiquetas.stock.venta")
        except Exception as exc:
            logger.debug("No se pudo suscribir a eventos de stock: %s", exc)

    def set_usuario_actual(self, usuario: str, rol: str = "cajero") -> None:
        self.usuario = usuario

    def set_sucursal(self, sucursal_id: int, nombre: str = "") -> None:
        self.sucursal_id = sucursal_id

    def _on_stock_actualizado(self, _payload: dict):
        """Refresca catálogo y vista previa cuando cambia inventario sin reiniciar app."""
        try:
            self._cargar_productos()
            self._actualizar_preview()
        except Exception as exc:
            logger.debug("refresh etiquetas por stock: %s", exc)

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)

        titulo = QLabel("🏷️ Diseño e Impresión de Etiquetas")
        titulo.setObjectName("heading")
        lay.addWidget(titulo)

        splitter = QSplitter(Qt.Horizontal)

        # ══════════════════════════════════════════════════════════════════
        # Panel izquierdo: formulario con tabs
        # ══════════════════════════════════════════════════════════════════
        left = QWidget(); left.setMaximumWidth(420)
        ll = QVBoxLayout(left); ll.setSpacing(6)

        tabs = QTabWidget()
        tabs.setObjectName("tabWidget")

        # ── Tab 1: Producto ──────────────────────────────────────────────
        tab_prod = QWidget()
        pf = QFormLayout(tab_prod); pf.setSpacing(8)

        # Búsqueda con autocompletado (reemplaza ComboBox)
        self.txt_buscar_producto = QLineEdit()
        self.txt_buscar_producto.setPlaceholderText("🔍 Buscar producto por nombre o código...")
        self.txt_buscar_producto.setObjectName("inputField")

        self._completer_model = QStringListModel()
        self._completer = QCompleter()
        self._completer.setModel(self._completer_model)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.setMaxVisibleItems(12)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        self._completer.activated.connect(self._on_producto_selected)
        self.txt_buscar_producto.setCompleter(self._completer)
        self.txt_buscar_producto.textChanged.connect(self._actualizar_preview)
        pf.addRow("Producto:", self.txt_buscar_producto)

        # Precio unitario
        self.spin_precio = QDoubleSpinBox()
        self.spin_precio.setRange(0, 99999); self.spin_precio.setDecimals(2)
        self.spin_precio.setPrefix("$ ")
        self.spin_precio.setObjectName("inputField")
        self.spin_precio.valueChanged.connect(self._actualizar_preview)
        pf.addRow("Precio:", self.spin_precio)

        # Unidad de medida (reemplaza peso fijo)
        self.cmb_unidad = QComboBox()
        self.cmb_unidad.addItems(["kg", "g", "pz", "lt", "ml", "m", "cm", "oz", "lb"])
        self.cmb_unidad.setObjectName("inputField")
        self.cmb_unidad.currentIndexChanged.connect(self._on_unidad_change)
        pf.addRow("Unidad:", self.cmb_unidad)

        # Cantidad / Volumen (reemplaza "peso neto")
        self.spin_cantidad = QDoubleSpinBox()
        self.spin_cantidad.setRange(0.001, 99999); self.spin_cantidad.setDecimals(3)
        self.spin_cantidad.setValue(1.0)
        self.spin_cantidad.setObjectName("inputField")
        self.spin_cantidad.valueChanged.connect(self._actualizar_preview)
        self.lbl_cantidad = QLabel("Cantidad:")
        pf.addRow(self.lbl_cantidad, self.spin_cantidad)

        tabs.addTab(tab_prod, "📦 Producto")

        # ── Tab 2: Lote y Fechas ─────────────────────────────────────────
        tab_lote = QWidget()
        lf = QFormLayout(tab_lote); lf.setSpacing(8)

        self.txt_lote = QLineEdit()
        self.txt_lote.setPlaceholderText("Ej: LOT-2026-001")
        self.txt_lote.textChanged.connect(self._actualizar_preview)
        lf.addRow("Lote:", self.txt_lote)

        self.date_empaque = QDateEdit(QDate.currentDate())
        self.date_empaque.setCalendarPopup(True)
        self.date_empaque.dateChanged.connect(self._actualizar_preview)
        lf.addRow("Empaque:", self.date_empaque)

        self.chk_caducidad = QCheckBox("Incluir fecha de caducidad")
        self.chk_caducidad.stateChanged.connect(self._toggle_caducidad)
        lf.addRow("", self.chk_caducidad)

        self.spin_dias_vida = QSpinBox()
        self.spin_dias_vida.setRange(1, 365); self.spin_dias_vida.setValue(5)
        self.spin_dias_vida.setSuffix(" días"); self.spin_dias_vida.setEnabled(False)
        self.spin_dias_vida.valueChanged.connect(self._actualizar_preview)
        lf.addRow("Vida útil:", self.spin_dias_vida)

        self.txt_sku = QLineEdit()
        self.txt_sku.setPlaceholderText("Código SKU / EAN (opcional)")
        self.txt_sku.textChanged.connect(self._actualizar_preview)
        lf.addRow("SKU/EAN:", self.txt_sku)

        tabs.addTab(tab_lote, "📋 Lote / Fechas")

        # ── Tab 3: Diseño visual ─────────────────────────────────────────
        tab_design = QWidget()
        df = QFormLayout(tab_design); df.setSpacing(8)

        self.spin_font_nombre = QSpinBox()
        self.spin_font_nombre.setRange(6, 24); self.spin_font_nombre.setValue(12)
        self.spin_font_nombre.setSuffix(" pt")
        self.spin_font_nombre.valueChanged.connect(self._actualizar_preview)
        df.addRow("Tamaño nombre:", self.spin_font_nombre)

        self.spin_font_precio = QSpinBox()
        self.spin_font_precio.setRange(8, 36); self.spin_font_precio.setValue(18)
        self.spin_font_precio.setSuffix(" pt")
        self.spin_font_precio.valueChanged.connect(self._actualizar_preview)
        df.addRow("Tamaño precio:", self.spin_font_precio)

        self.spin_font_detalle = QSpinBox()
        self.spin_font_detalle.setRange(5, 14); self.spin_font_detalle.setValue(8)
        self.spin_font_detalle.setSuffix(" pt")
        self.spin_font_detalle.valueChanged.connect(self._actualizar_preview)
        df.addRow("Tamaño detalle:", self.spin_font_detalle)

        self.chk_qr_label = QCheckBox("Código QR")
        self.chk_qr_label.setChecked(True)
        self.chk_qr_label.stateChanged.connect(self._actualizar_opciones_preview)
        self.chk_barcode_label = QCheckBox("Código de barras")
        self.chk_barcode_label.setChecked(True)
        self.chk_barcode_label.stateChanged.connect(self._actualizar_opciones_preview)

        codes_row = QHBoxLayout()
        codes_row.addWidget(self.chk_qr_label)
        codes_row.addWidget(self.chk_barcode_label)
        df.addRow("Códigos:", codes_row)

        self.cmb_barcode_type = QComboBox()
        self.cmb_barcode_type.addItems(["Code128", "EAN13", "Code39", "ITF"])
        self.cmb_barcode_type.currentIndexChanged.connect(self._actualizar_opciones_preview)
        df.addRow("Tipo barcode:", self.cmb_barcode_type)

        tabs.addTab(tab_design, "🎨 Diseño")

        ll.addWidget(tabs)

        # ── Impresión ────────────────────────────────────────────────────
        grp_imp = QGroupBox("Impresión")
        imf = QFormLayout(grp_imp)
        self.cmb_tamaño = QComboBox()
        self.cmb_tamaño.addItems(list(TAMAÑOS.keys()))
        self.cmb_tamaño.setCurrentIndex(1)  # Estándar 80x50
        self.spin_copias = QSpinBox()
        self.spin_copias.setRange(1, 100); self.spin_copias.setValue(1)
        self.spin_copias.setSuffix(" copia(s)")
        imf.addRow("Tamaño:", self.cmb_tamaño)
        imf.addRow("Copias:", self.spin_copias)
        ll.addWidget(grp_imp)

        btn_row = QHBoxLayout()
        btn_pdf = create_secondary_button(self, "📄 PDF", "Guardar etiqueta como PDF")
        btn_pdf.clicked.connect(self._guardar_pdf)
        
        btn_test = create_primary_button(self, "🧪 Muestra", "Imprimir etiqueta de prueba")
        btn_test.clicked.connect(self._imprimir_muestra)
        
        btn_imp = create_success_button(self, "🖨️ Imprimir", "Enviar a impresora de etiquetas")
        btn_imp.clicked.connect(self._imprimir)
        
        btn_row.addWidget(btn_pdf); btn_row.addWidget(btn_test); btn_row.addWidget(btn_imp)
        ll.addLayout(btn_row)
        ll.addStretch()
        splitter.addWidget(left)

        # ══════════════════════════════════════════════════════════════════
        # Panel derecho: vista previa
        # ══════════════════════════════════════════════════════════════════
        right = QWidget(); rl = QVBoxLayout(right)
        lbl_prev = QLabel("Vista previa de etiqueta:")
        lbl_prev.setObjectName("subheading")
        rl.addWidget(lbl_prev)
        self.preview = EtiquetaPreview()
        rl.addWidget(self.preview, 0, Qt.AlignHCenter | Qt.AlignTop)
        rl.addStretch()
        splitter.addWidget(right)
        splitter.setSizes([420, 380])
        lay.addWidget(splitter)
        self._actualizar_preview()

    # ── Productos: carga y autocompletado ─────────────────────────────────────

    def _cargar_productos(self):
        """Carga productos de la BD y configura el autocompletado."""
        try:
            rows = self.db.execute(
                "SELECT id, nombre, COALESCE(precio,0), COALESCE(unidad,'pz') "
                "FROM productos WHERE activo=1 ORDER BY nombre LIMIT 2000"
            ).fetchall()
            self._productos_cache = [
                (r[0], r[1], float(r[2]), str(r[3])) for r in rows
            ]
            nombres = [r[1] for r in self._productos_cache]
            self._completer_model.setStringList(nombres)
            if nombres:
                self.txt_buscar_producto.setText(nombres[0])
                self._on_producto_selected(nombres[0])
        except Exception as e:
            logger.warning("_cargar_productos: %s", e)

    def _on_producto_selected(self, nombre_texto: str):
        """Cuando el usuario selecciona un producto del autocompletado."""
        for pid, nombre, precio, unidad in self._productos_cache:
            if nombre == nombre_texto:
                self._selected_product_id = pid
                self.spin_precio.setValue(precio)
                # Seleccionar unidad
                unidad_lower = unidad.lower().strip()
                idx = self.cmb_unidad.findText(unidad_lower)
                if idx >= 0:
                    self.cmb_unidad.setCurrentIndex(idx)
                break
        self._actualizar_preview()

    def _on_unidad_change(self, idx):
        """Actualiza la etiqueta del campo cantidad según la unidad."""
        unidad = self.cmb_unidad.currentText()
        labels = {"kg": "Peso (kg):", "g": "Peso (g):", "pz": "Piezas:",
                  "lt": "Litros:", "ml": "Mililitros:", "m": "Metros:",
                  "cm": "Centímetros:", "oz": "Onzas:", "lb": "Libras:"}
        self.lbl_cantidad.setText(labels.get(unidad, "Cantidad:"))
        # Ajustar decimales según unidad
        if unidad in ("pz",):
            self.spin_cantidad.setDecimals(0)
        else:
            self.spin_cantidad.setDecimals(3)
        self._actualizar_preview()

    def _toggle_caducidad(self, state):
        self.spin_dias_vida.setEnabled(bool(state))
        self._actualizar_preview()

    def _cargar_config(self):
        try:
            row = self.db.execute(
                "SELECT valor FROM configuraciones WHERE clave='nombre_empresa'"
            ).fetchone()
            self._nombre_negocio = row[0] if row else "SPJ"
        except Exception:
            self._nombre_negocio = "SPJ"

    # ── Construir datos para preview/impresión ────────────────────────────────

    def _build_datos(self) -> dict:
        nombre = self.txt_buscar_producto.text().strip() or "Producto"
        precio = self.spin_precio.value()
        cantidad = self.spin_cantidad.value()
        unidad = self.cmb_unidad.currentText()
        total = round(cantidad * precio, 2)

        f_emp = self.date_empaque.date().toString("yyyy-MM-dd")
        f_cad = ""
        if self.chk_caducidad.isChecked():
            dias = self.spin_dias_vida.value()
            f_cad = (date.fromisoformat(f_emp) + timedelta(days=dias)).isoformat()

        return {
            "nombre":           nombre,
            "cantidad":         cantidad,
            "unidad":           unidad,
            "precio_unitario":  precio,
            "total":            total,
            # Backwards compat con preview
            "peso_kg":          cantidad,
            "precio_kg":        precio,
            "lote":             self.txt_lote.text().strip(),
            "sku":              self.txt_sku.text().strip() if hasattr(self, 'txt_sku') else "",
            "fecha_empaque":    f_emp,
            "fecha_caducidad":  f_cad,
            "nombre_negocio":   self._nombre_negocio,
            "producto_id":      self._selected_product_id,
            # Font sizes for preview
            "font_nombre":      self.spin_font_nombre.value() if hasattr(self, 'spin_font_nombre') else 12,
            "font_precio":      self.spin_font_precio.value() if hasattr(self, 'spin_font_precio') else 18,
            "font_detalle":     self.spin_font_detalle.value() if hasattr(self, 'spin_font_detalle') else 8,
        }

    def _actualizar_preview(self):
        self.preview.actualizar(self._build_datos())

    def _actualizar_opciones_preview(self):
        self.preview.set_opciones({
            "mostrar_qr": self.chk_qr_label.isChecked(),
            "mostrar_barcode": self.chk_barcode_label.isChecked(),
            "tipo_barcode": self.cmb_barcode_type.currentText(),
        })
        self._actualizar_preview()

    def _get_printer_config(self) -> dict:
        """Lee configuración de impresora de etiquetas desde hardware_config."""
        import json as _json
        # Intentar ambas claves posibles
        for tipo_key in ('etiquetas', 'impresora_etiquetas'):
            try:
                row = self.db.execute(
                    "SELECT configuraciones FROM hardware_config WHERE tipo=?",
                    (tipo_key,)
                ).fetchone()
                if row and row[0]:
                    cfg = _json.loads(row[0])
                    if cfg.get("ubicacion") or cfg.get("ip") or cfg.get("puerto_serial"):
                        return cfg
            except Exception:
                pass
        return {}

    def _send_to_printer(self, data: bytes, cfg: dict) -> bool:
        """Envía datos raw a la impresora de etiquetas según la config de hardware."""
        tipo = cfg.get("tipo", "").lower()
        ubicacion = cfg.get("ubicacion", cfg.get("ip", ""))
        if not ubicacion:
            return False

        try:
            if "red" in tipo or "ip" in tipo or ":" in ubicacion:
                # Red TCP/IP
                import socket
                ip, port = ubicacion.split(":") if ":" in ubicacion else (ubicacion, "9100")
                s = socket.socket()
                s.settimeout(5)
                s.connect((ip.strip(), int(port)))
                s.sendall(data)
                s.close()
                return True
            elif "serial" in tipo or "com" in tipo.lower():
                # Serial port
                import serial as _ser
                with _ser.Serial(ubicacion, 9600, timeout=3) as sp:
                    sp.write(data)
                return True
            elif "usb" in tipo:
                # USB via win32print (Windows)
                try:
                    import win32print
                    hp = win32print.OpenPrinter(ubicacion)
                    try:
                        hj = win32print.StartDocPrinter(hp, 1, ("SPJ Etiqueta", None, "RAW"))
                        win32print.StartPagePrinter(hp)
                        win32print.WritePrinter(hp, data)
                        win32print.EndPagePrinter(hp)
                        win32print.EndDocPrinter(hp)
                    finally:
                        win32print.ClosePrinter(hp)
                    return True
                except ImportError:
                    logger.warning("win32print no disponible — usar Red o Serial")
                    return False
        except Exception as e:
            logger.warning("_send_to_printer: %s", e)
            raise
        return False

    def _imprimir_muestra(self):
        """Imprime una sola etiqueta usando la configuración de hardware de la app."""
        datos = self._build_datos()
        cfg = self._get_printer_config()

        # ── Ruta 1: Impresora de etiquetas (ZPL/EPL/TSPL) via hardware config ──
        if cfg:
            try:
                from labels.generador_etiquetas import GeneradorEtiquetas
                tamaño = TAMAÑOS.get(self.cmb_tamaño.currentText(), (80, 50))
                gen = GeneradorEtiquetas(ancho_mm=tamaño[0])
                lote_data = {
                    "nombre": datos["nombre"],
                    "precio": datos.get("precio_unitario", datos.get("precio_kg", 0)),
                    "peso_kg": datos.get("cantidad", datos.get("peso_kg", 0)),
                    "lote": datos.get("lote", ""),
                    "fecha_empaque": datos.get("fecha_empaque", ""),
                    "fecha_caducidad": datos.get("fecha_caducidad", ""),
                    "sucursal": self._nombre_negocio,
                    "uuid_qr": datos.get("lote", "SPJ-MUESTRA"),
                }
                comandos = gen.etiqueta_producto(lote_data)
                raw = comandos.encode("utf-8") if isinstance(comandos, str) else comandos
                self._send_to_printer(raw, cfg)
                Toast.success(self, "✅ Muestra enviada", cfg.get('ubicacion','impresora'))
                return
            except Exception as e:
                logger.warning("_imprimir_muestra HW: %s", e)
                QMessageBox.warning(self, "⚠️ Error de impresora",
                    f"Error al enviar a la impresora configurada:\n{e}\n\n"
                    f"Config: {cfg.get('tipo','')} @ {cfg.get('ubicacion','')}\n"
                    "Verifica la conexión en Configuración → Hardware.")
                return
        else:
            # Sin impresora configurada — avisar al usuario
            QMessageBox.warning(self, "⚠️ Sin impresora de etiquetas",
                "No hay impresora de etiquetas configurada.\n\n"
                "Configúrala en:\n"
                "  Configuración → Hardware → Impresora de etiquetas\n\n"
                "Puedes usar 'Guardar PDF' como alternativa.")

    def _imprimir(self):
        """Imprime N etiquetas usando la configuración de hardware de la app."""
        datos = self._build_datos()
        copias = self.spin_copias.value()
        cfg = self._get_printer_config()

        if not cfg:
            QMessageBox.warning(self, "⚠️ Sin impresora de etiquetas",
                "No hay impresora de etiquetas configurada.\n\n"
                "Configúrala en:\n"
                "  Configuración → Hardware → Impresora de etiquetas\n\n"
                "Puedes usar 'Guardar PDF' como alternativa.")
            return

        try:
            from labels.generador_etiquetas import GeneradorEtiquetas
            tamaño = TAMAÑOS.get(self.cmb_tamaño.currentText(), (80, 50))
            gen = GeneradorEtiquetas(ancho_mm=tamaño[0])
            lote_data = {
                "nombre":          datos["nombre"],
                "precio":          datos.get("precio_unitario", datos.get("precio_kg", 0)),
                "peso_kg":         datos.get("cantidad", datos.get("peso_kg", 0)),
                "lote":            datos.get("lote", ""),
                "fecha_empaque":   datos.get("fecha_empaque", ""),
                "fecha_caducidad": datos.get("fecha_caducidad", ""),
                "sucursal":        self._nombre_negocio,
                "codigo":          datos.get("sku", ""),
                "uuid_qr":         datos.get("lote", "SPJ-0001"),
            }
            for i in range(copias):
                comandos = gen.etiqueta_producto(lote_data)
                raw = comandos.encode("utf-8") if isinstance(comandos, str) else comandos
                self._send_to_printer(raw, cfg)
            Toast.success(
                self, "✅ Impreso",
                f"{copias} etiqueta(s) enviadas a {cfg.get('ubicacion','impresora')}",
            )
        except Exception as e:
            logger.warning("_imprimir: %s", e)
            QMessageBox.warning(self, "⚠️ Error de impresora",
                f"No se pudo imprimir: {e}\n\n"
                f"Config: {cfg.get('tipo','')} @ {cfg.get('ubicacion','')}\n"
                "Verifica la conexión o usa 'Guardar PDF' como alternativa.")

    def _guardar_pdf(self):
        datos   = self._build_datos()
        copias  = self.spin_copias.value()
        tamaño  = TAMAÑOS.get(self.cmb_tamaño.currentText(), (80, 50))
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar etiquetas PDF", "etiquetas.pdf", "PDF (*.pdf)")
        if not ruta: return
        try:
            from reportlab.pdfgen import canvas as rl_canvas
            from reportlab.lib.units import mm

            W = tamaño[0] * mm; H = tamaño[1] * mm
            c = rl_canvas.Canvas(ruta, pagesize=(W, H))
            cantidad = float(datos.get("cantidad", datos.get("peso_kg", 0)))
            precio   = float(datos.get("precio_unitario", datos.get("precio_kg", 0)))
            unidad   = datos.get("unidad", "kg")
            total    = round(cantidad * precio, 2)

            for _ in range(copias):
                c.setFillColorRGB(1,1,1); c.rect(0,0,W,H,fill=1,stroke=0)
                c.setStrokeColorRGB(0.2,0.2,0.2); c.setLineWidth(0.5)
                c.rect(1*mm,1*mm,W-2*mm,H-2*mm,fill=0,stroke=1)
                # Nombre producto
                c.setFillColorRGB(0,0,0)
                c.setFont("Helvetica-Bold", min(10, tamaño[0]/9))
                c.drawString(3*mm, H-8*mm, datos["nombre"][:28])
                # Precio total
                c.setFont("Helvetica-Bold", 14)
                c.setFillColorRGB(0.8,0.1,0.1)
                c.drawString(3*mm, H-18*mm, f"${total:.2f}")
                c.setFont("Helvetica", 8); c.setFillColorRGB(0.3,0.3,0.3)
                c.drawString(3*mm, H-26*mm, f"{cantidad:.3f} {unidad}  ${precio:.2f}/{unidad}")
                if datos.get("lote"):
                    c.drawString(3*mm, H-34*mm, f"Lote: {datos['lote']}")
                c.drawString(3*mm, H-42*mm, f"Emp: {datos['fecha_empaque']}")
                if datos.get("fecha_caducidad"):
                    c.setFont("Helvetica-Bold",8); c.setFillColorRGB(0.8,0,0)
                    c.drawString(3*mm, H-50*mm, f"Cad: {datos['fecha_caducidad']}")
                # QR
                try:
                    from reportlab.graphics.barcode.qr import QrCodeWidget
                    from reportlab.graphics.shapes import Drawing
                    from reportlab.graphics import renderPDF
                    qr_size = min(tamaño[1]*0.5*mm, 30*mm)
                    qr_content = (datos.get("lote") or datos["nombre"][:20])
                    qrw = QrCodeWidget(qr_content)
                    qrw.barWidth = qrw.barHeight = qr_size
                    d = Drawing(qr_size, qr_size)
                    d.add(qrw)
                    renderPDF.draw(d, c, W - qr_size - 2*mm, H/2 - qr_size/2)
                except Exception:
                    pass
                c.showPage()
            c.save()
            Toast.success(self, "✅ PDF guardado", os.path.basename(ruta))
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
