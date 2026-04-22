# modulos/proveedores.py — SPJ POS v13.4
"""
Módulo de gestión de proveedores — UI DELGADA.

TODA la lógica de negocio está en:
  core/services/finance/third_party_service.py

Este módulo solo:
  - Renderiza UI
  - Consume servicios
  - Maneja eventos de usuario
"""
from __future__ import annotations
from core.events.event_bus import get_bus
import logging
from datetime import date

from modulos.spj_phone_widget import PhoneWidget
from modulos.spj_styles import spj_btn, apply_btn_styles
from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import create_primary_button, create_success_button, create_heading, apply_tooltip
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView,
    QGroupBox, QDialog, QDialogButtonBox, QMessageBox,
    QSpinBox, QDoubleSpinBox, QTextEdit, QTabWidget,
    QComboBox, QSplitter
)

logger = logging.getLogger("spj.proveedores")


# ── Diálogo editar/crear proveedor ─────────────────────────────────────────

class DialogoProveedor(QDialog):
    """Dialogo para crear/editar proveedores. v13.4 - UI Delgada"""

    def __init__(self, third_party_service, proveedor_id=None, parent=None):
        super().__init__(parent)
        self._tps = third_party_service
        self.proveedor_id = proveedor_id
        self.setWindowTitle("Editar Proveedor" if proveedor_id else "Nuevo Proveedor")
        self.setMinimumWidth(460)
        self._build_ui()
        if proveedor_id:
            self._cargar()

    def _build_ui(self):
        from PyQt5.QtWidgets import (QFormLayout, QLineEdit, QTextEdit, QSpinBox,
            QDoubleSpinBox, QDialogButtonBox, QComboBox, QLabel, QMessageBox)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.txt_nombre   = QLineEdit(); self.txt_nombre.setPlaceholderText("Razon social o nombre")
        self.txt_rfc      = QLineEdit(); self.txt_rfc.setPlaceholderText("RFC o NIT")
        self.txt_telefono = PhoneWidget()
        self.txt_telefono.setPlaceholderText("5512345678 (10 dígitos)")
        self.txt_telefono.setToolTip("Captura solo los 10 dígitos. El código +52 se agrega automáticamente.")
        self.txt_email    = QLineEdit(); self.txt_email.setPlaceholderText("correo@proveedor.com")
        self.txt_contacto = QLineEdit(); self.txt_contacto.setPlaceholderText("Nombre del contacto")
        self.cmb_categoria = QComboBox()
        self.cmb_categoria.addItems(["Productos","Servicios","Insumos","Equipos","Otro"])
        self.txt_direccion = QTextEdit(); self.txt_direccion.setMaximumHeight(60)
        self.spin_dias   = QSpinBox(); self.spin_dias.setRange(0,180); self.spin_dias.setSuffix(" dias")
        self.spin_limite = QDoubleSpinBox(); self.spin_limite.setRange(0,9999999); self.spin_limite.setPrefix("$"); self.spin_limite.setDecimals(2)
        self.txt_banco   = QLineEdit(); self.txt_banco.setPlaceholderText("Banco / CLABE")
        self.txt_notas   = QTextEdit(); self.txt_notas.setMaximumHeight(60)
        form.addRow("Nombre *:",     self.txt_nombre)
        form.addRow("RFC / NIT:",    self.txt_rfc)
        form.addRow("Telefono WA:",  self.txt_telefono)
        form.addRow("Email:",        self.txt_email)
        form.addRow("Contacto:",     self.txt_contacto)
        form.addRow("Categoria:",    self.cmb_categoria)
        form.addRow("Direccion:",    self.txt_direccion)
        form.addRow("Dias credito:", self.spin_dias)
        form.addRow("Limite:",       self.spin_limite)
        form.addRow("Banco/CLABE:",  self.txt_banco)
        form.addRow("Notas:",        self.txt_notas)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._guardar)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _cargar(self):
        try:
            prov = self._tps.get_proveedor(self.proveedor_id)
            if not prov: return
            self.txt_nombre.setText(prov.get("nombre", ""))
            self.txt_rfc.setText(prov.get("rfc", ""))
            self.txt_telefono.set_phone(prov.get("telefono", ""))
            self.txt_email.setText(prov.get("email", ""))
            self.txt_contacto.setText(prov.get("contacto", ""))
            idx = self.cmb_categoria.findText(prov.get("categoria", "Productos"))
            if idx >= 0: self.cmb_categoria.setCurrentIndex(idx)
            self.txt_direccion.setPlainText(prov.get("direccion", ""))
            self.spin_dias.setValue(int(prov.get("condiciones_pago", 0) or 0))
            self.spin_limite.setValue(float(prov.get("limite_credito", 0) or 0))
            self.txt_banco.setText(prov.get("banco", ""))
            self.txt_notas.setPlainText(prov.get("notas", ""))
        except Exception as e:
            logger.warning("_cargar error: %s", e)

    def _guardar(self):
        import re as _re
        nombre = self.txt_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Aviso", "El nombre es obligatorio.")
            return
        tel = self.txt_telefono.get_e164().strip().replace(" ","")
        if tel and not _re.match(r"^\+\d{12}$", tel):  # +52 + 10 dígitos = 12 caracteres totales
            QMessageBox.warning(self, "Telefono invalido",
                "Formato requerido: +52 + 10 dígitos (ej: +525512345678)")
            return
        
        datos = {
            "nombre": nombre,
            "rfc": self.txt_rfc.text().strip(),
            "telefono": tel,
            "email": self.txt_email.text().strip(),
            "contacto": self.txt_contacto.text().strip(),
            "categoria": self.cmb_categoria.currentText(),
            "direccion": self.txt_direccion.toPlainText().strip(),
            "condiciones_pago": self.spin_dias.value(),
            "limite_credito": self.spin_limite.value(),
            "banco": self.txt_banco.text().strip(),
            "notas": self.txt_notas.toPlainText().strip(),
        }
        try:
            if self.proveedor_id:
                self._tps.update_proveedor(self.proveedor_id, datos)
            else:
                self._tps.create_proveedor(datos)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error al guardar", str(e))

class ModuloProveedores(QWidget):
    """Módulo de Proveedores — UI DELGADA. Consume UnifiedThirdPartyService."""

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container = container
        self._tps = getattr(container, 'third_party_service', None)
        if not self._tps:
            logger.warning("third_party_service no disponible en container")
        self.usuario_actual = ""
        self._build_ui()
        self._cargar_tabla()

    def set_usuario_actual(self, usuario: str, rol: str = "cajero") -> None:
        self.usuario_actual = usuario

    def set_sucursal(self, sucursal_id: int, nombre: str = "") -> None:
        pass

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        titulo = QLabel("🏭 Proveedores")
        titulo.setObjectName("heading")
        btn_nuevo = create_success_button(self, "➕ Nuevo Proveedor", "Crear nuevo proveedor")
        btn_nuevo.clicked.connect(self._nuevo)
        hdr.addWidget(titulo); hdr.addStretch(); hdr.addWidget(btn_nuevo)
        lay.addLayout(hdr)

        # Búsqueda
        busq = QHBoxLayout()
        self.txt_buscar = QLineEdit()
        self.txt_buscar.setPlaceholderText("Buscar por nombre, RFC o contacto...")
        self.txt_buscar.textChanged.connect(self._filtrar)
        busq.addWidget(self.txt_buscar)
        lay.addLayout(busq)

        # Tabs
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)

        # ── Tab Directorio ──────────────────────────────────────────────────
        tab_dir = QWidget(); dl = QVBoxLayout(tab_dir)
        self.tbl = QTableWidget()
        self.tbl.setColumnCount(7)
        self.tbl.setHorizontalHeaderLabels(
            ["Nombre", "Teléfono", "Email", "Contacto", "Días crédito", "Saldo", "Acciones"])
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1,2,3,4,5): hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.doubleClicked.connect(self._editar_seleccionado)
        dl.addWidget(self.tbl)
        self.tabs.addTab(tab_dir, "📋 Directorio")

        # ── Tab Historial de precios ────────────────────────────────────────
        tab_hist = QWidget(); hl = QVBoxLayout(tab_hist)
        hist_top = QHBoxLayout()
        self.cmb_proveedor_hist = QComboBox()
        self.cmb_proveedor_hist.currentIndexChanged.connect(self._cargar_historial_precios)
        hist_top.addWidget(QLabel("Proveedor:")); hist_top.addWidget(self.cmb_proveedor_hist, 1)
        hl.addLayout(hist_top)

        self.tbl_hist = QTableWidget()
        self.tbl_hist.setColumnCount(5)
        self.tbl_hist.setHorizontalHeaderLabels(
            ["Producto", "Precio", "Cantidad", "Fecha", "Compra"])
        self.tbl_hist.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_hist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_hist.verticalHeader().setVisible(False)
        hl.addWidget(self.tbl_hist)
        self.tabs.addTab(tab_hist, "📈 Historial de precios")

        # ── Tab Evaluación ──────────────────────────────────────────────────
        tab_eval = QWidget(); el = QVBoxLayout(tab_eval)
        self.tbl_eval = QTableWidget()
        self.tbl_eval.setColumnCount(6)
        self.tbl_eval.setHorizontalHeaderLabels(
            ["Proveedor", "Compras", "Total comprado", "Última compra", "Saldo pend.", "Estado"])
        self.tbl_eval.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_eval.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_eval.verticalHeader().setVisible(False)
        self.tbl_eval.setAlternatingRowColors(True)
        el.addWidget(self.tbl_eval)
        btn_refr = QPushButton("🔄 Actualizar evaluación")
        btn_refr.clicked.connect(self._cargar_evaluacion)
        el.addWidget(btn_refr, 0, Qt.AlignRight)
        self.tabs.addTab(tab_eval, "⭐ Evaluación")

        self.tabs.currentChanged.connect(self._on_tab_change)

    # ── Acciones ───────────────────────────────────────────────────────────

    def _nuevo(self):
        if not self._tps:
            QMessageBox.warning(self, "Error", "Servicio de proveedores no disponible.")
            return
        dlg = DialogoProveedor(self._tps, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._cargar_tabla()
            self._cargar_combo_proveedores()

    def _editar_seleccionado(self):
        row = self.tbl.currentRow()
        if row < 0: return
        pid = self.tbl.item(row, 0)
        if not pid: return
        from PyQt5.QtCore import Qt as _Qt
        proveedor_id = pid.data(_Qt.UserRole)
        if not proveedor_id: return
        if not self._tps:
            QMessageBox.warning(self, "Error", "Servicio de proveedores no disponible.")
            return
        dlg = DialogoProveedor(self._tps, proveedor_id, self)
        if dlg.exec_() == QDialog.Accepted:
            self._cargar_tabla()

    def _eliminar(self, proveedor_id: int, nombre: str):
        resp = QMessageBox.question(
            self, "Eliminar proveedor",
            f"¿Eliminar a '{nombre}'?\nEsta acción no se puede deshacer.",
            QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes: return
        if not self._tps:
            QMessageBox.warning(self, "Error", "Servicio de proveedores no disponible.")
            return
        try:
            self._tps.delete_proveedor(proveedor_id, soft=True)
            self._cargar_tabla()
            self._cargar_combo_proveedores()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ── Datos ──────────────────────────────────────────────────────────────

    def _cargar_tabla(self):
        if not self._tps:
            self.tbl.setRowCount(0)
            return
        try:
            rows = self._tps.get_all_proveedores(activo=True, limit=300)
        except Exception as e:
            logger.warning("_cargar_tabla: %s", e)
            rows = []

        self.tbl.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            pid, nombre = r.get('id'), r.get('nombre', '')
            vals = [
                nombre, 
                r.get('telefono', ''), 
                r.get('email', ''), 
                r.get('contacto', ''),
                f"{int(r.get('condiciones_pago', 0) or 0)} días", 
                f"${float(r.get('saldo_pendiente', 0) or 0):,.2f}"
            ]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci == 0:
                    from PyQt5.QtCore import Qt as _Qt
                    it.setData(_Qt.UserRole, pid)
                self.tbl.setItem(ri, ci, it)

            # Botones acción
            btn_w = QWidget(); btn_lay = QHBoxLayout(btn_w)
            btn_lay.setContentsMargins(2, 2, 2, 2)
            btn_ed = QPushButton("✏️")
            btn_ed.setFixedSize(28, 26)
            btn_ed.setToolTip("Editar")
            btn_ed.clicked.connect(
                lambda _, pid=pid: self._editar_por_id(pid))
            btn_del = QPushButton("🗑️")
            btn_del.setFixedSize(28, 26)
            btn_del.setToolTip("Eliminar")
            btn_del.clicked.connect(
                lambda _, pid=pid, nom=nombre: self._eliminar(pid, nom))
            btn_lay.addWidget(btn_ed); btn_lay.addWidget(btn_del)
            self.tbl.setCellWidget(ri, 6, btn_w)

    def _editar_por_id(self, proveedor_id: int):
        if not self._tps:
            QMessageBox.warning(self, "Error", "Servicio de proveedores no disponible.")
            return
        dlg = DialogoProveedor(self._tps, proveedor_id, self)
        if dlg.exec_() == QDialog.Accepted:
            self._cargar_tabla()

    def _filtrar(self):
        txt = self.txt_buscar.text().lower()
        for i in range(self.tbl.rowCount()):
            nom = (self.tbl.item(i, 0) or QTableWidgetItem()).text().lower()
            tel = (self.tbl.item(i, 1) or QTableWidgetItem()).text().lower()
            con = (self.tbl.item(i, 3) or QTableWidgetItem()).text().lower()
            visible = not txt or txt in nom or txt in tel or txt in con
            self.tbl.setRowHidden(i, not visible)

    def _cargar_combo_proveedores(self):
        if not self._tps:
            return
        try:
            rows = self._tps.get_all_proveedores(activo=True, limit=500)
            self.cmb_proveedor_hist.blockSignals(True)
            self.cmb_proveedor_hist.clear()
            for r in rows:
                self.cmb_proveedor_hist.addItem(r.get('nombre', ''), r.get('id'))
            self.cmb_proveedor_hist.blockSignals(False)
            self._cargar_historial_precios()
        except Exception as e:
            logger.debug("_cargar_combo: %s", e)

    def _cargar_historial_precios(self):
        if not self._tps:
            self.tbl_hist.setRowCount(0)
            return
        pid = self.cmb_proveedor_hist.currentData()
        if not pid: return
        try:
            rows = self._tps.get_historial_precios(proveedor_id=pid, limit=200)
        except Exception:
            rows = []
        self.tbl_hist.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            vals = [
                r.get('producto', ''), 
                f"${float(r.get('precio', 0)):.4f}", 
                f"{float(r.get('cantidad', 0)):.2f}",
                str(r.get('fecha', ''))[:10], 
                f"#{r.get('compra_id', '')}"
            ]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci in (1, 2):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tbl_hist.setItem(ri, ci, it)

    def _cargar_evaluacion(self):
        if not self._tps:
            self.tbl_eval.setRowCount(0)
            return
        try:
            rows = self._tps.get_evaluacion_proveedores(limit=100)
        except Exception as e:
            logger.warning("_cargar_eval: %s", e)
            rows = []

        self.tbl_eval.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            saldo = float(r.get("saldo_pendiente", 0) or 0)
            estado = r.get("estado", "✅ Al corriente")
            vals = [
                r.get("nombre", ""), 
                str(int(r.get("num_compras", 0) or 0)),
                f"${float(r.get('total_comprado', 0) or 0):,.2f}",
                str(r.get("ultima_compra", "") or "—")[:10],
                f"${saldo:,.2f}", 
                estado
            ]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci in (1, 2, 4):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if ci == 5 and saldo > 0:
                    it.setForeground(Qt.red)
                self.tbl_eval.setItem(ri, ci, it)

    def _on_tab_change(self, idx: int):
        if idx == 1:
            self._cargar_combo_proveedores()
        elif idx == 2:
            self._cargar_evaluacion()
