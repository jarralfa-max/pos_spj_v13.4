# modulos/proveedores.py — SPJ POS v13
"""
Módulo de gestión de proveedores.

Funciones:
  - CRUD completo de proveedores
  - Historial de precios por producto/proveedor
  - Evaluación básica (puntualidad, calidad, precio)
  - Directorio con contactos y condiciones de pago
"""
from __future__ import annotations
from core.services.auto_audit import audit_write
from core.events.event_bus import get_bus
import logging
from datetime import date

from modulos.spj_phone_widget import PhoneWidget
from modulos.spj_styles import spj_btn, apply_btn_styles
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
    """Dialogo para crear/editar proveedores. v13.2"""

    def __init__(self, db, proveedor_id=None, parent=None):
        super().__init__(parent)
        self.db           = db
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
        self.txt_telefono.setPlaceholderText("+52 ej: +5215512345678")
        self.txt_telefono.setToolTip("Formato WhatsApp: +codigopais+numero sin espacios")
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
            cols = {r[1] for r in self.db.execute("PRAGMA table_info(proveedores)").fetchall()}
            cat_col  = "categoria," if "categoria" in cols else ""
            nota_col = "notas"      if "notas"     in cols else "NULL"
            row = self.db.execute(
                f"SELECT nombre,rfc,telefono,email,contacto,{cat_col}"
                f"direccion,condiciones_pago,limite_credito,banco,{nota_col} "
                f"FROM proveedores WHERE id=?", (self.proveedor_id,)
            ).fetchone()
            if not row: return
            i = 0
            self.txt_nombre.setText(str(row[i] or "")); i+=1
            self.txt_rfc.setText(str(row[i] or "")); i+=1
            self.txt_telefono.set_phone(str(row[i] or "")); i+=1
            self.txt_email.setText(str(row[i] or "")); i+=1
            self.txt_contacto.setText(str(row[i] or "")); i+=1
            if cat_col:
                idx = self.cmb_categoria.findText(str(row[i] or "Productos"))
                if idx >= 0: self.cmb_categoria.setCurrentIndex(idx)
                i+=1
            self.txt_direccion.setPlainText(str(row[i] or "")); i+=1
            self.spin_dias.setValue(int(row[i] or 0)); i+=1
            self.spin_limite.setValue(float(row[i] or 0)); i+=1
            self.txt_banco.setText(str(row[i] or "")); i+=1
            self.txt_notas.setPlainText(str(row[i] or ""))
        except Exception:
            pass

    def _guardar(self):
        # [spj-dedup] from PyQt5.QtWidgets import QMessageBox
        import re as _re
        nombre = self.txt_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Aviso", "El nombre es obligatorio.")
            return
        tel = self.txt_telefono.get_e164().strip().replace(" ","")
        if tel and not _re.match(r"^\+\d{7,15}$", tel):
            QMessageBox.warning(self, "Telefono invalido",
                "Formato: +codigopais+numero sin espacios\nEj: +5215512345678")
            return
        # ensure columns exist
        for col_def in ["categoria TEXT DEFAULT 'Productos'", "notas TEXT"]:
            try: self.db.execute(f"ALTER TABLE proveedores ADD COLUMN {col_def}")
            except Exception: pass
        try: self.db.commit()
        except Exception: pass
        datos = (
            nombre,
            self.txt_rfc.text().strip(),
            tel,
            self.txt_email.text().strip(),
            self.txt_contacto.text().strip(),
            self.cmb_categoria.currentText(),
            self.txt_direccion.toPlainText().strip(),
            self.spin_dias.value(),
            self.spin_limite.value(),
            self.txt_banco.text().strip(),
            self.txt_notas.toPlainText().strip(),
        )
        try:
            if self.proveedor_id:
                self.db.execute("""UPDATE proveedores
                    SET nombre=?,rfc=?,telefono=?,email=?,contacto=?,
                        categoria=?,direccion=?,condiciones_pago=?,
                        limite_credito=?,banco=?,notas=?,activo=1
                    WHERE id=?""", datos + (self.proveedor_id,))
            else:
                self.db.execute("""INSERT INTO proveedores
                    (nombre,rfc,telefono,email,contacto,categoria,
                     direccion,condiciones_pago,limite_credito,banco,notas,activo)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,1)""", datos)
            try: self.db.commit()
            except Exception: pass
            try:
                get_bus().publish("PROVEEDOR_CREADO", {"event_type": "PROVEEDOR_CREADO"})
            except Exception: pass
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error al guardar", str(e))

class ModuloProveedores(QWidget):

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container = container
        self.db = container.db
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
        titulo.setStyleSheet("font-size:17px;font-weight:bold;")
        btn_nuevo = QPushButton("➕ Nuevo Proveedor")
        btn_nuevo.setStyleSheet(
            "background:#27ae60;color:white;font-weight:bold;padding:6px 14px;border-radius:4px;")
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
        dlg = DialogoProveedor(self.db, parent=self)
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
        dlg = DialogoProveedor(self.db, proveedor_id, self)
        if dlg.exec_() == QDialog.Accepted:
            self._cargar_tabla()

    def _eliminar(self, proveedor_id: int, nombre: str):
        resp = QMessageBox.question(
            self, "Eliminar proveedor",
            f"¿Eliminar a '{nombre}'?\nEsta acción no se puede deshacer.",
            QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes: return
        try:
            # Soft-delete (marcar inactivo)
            self.db.execute(
                "UPDATE proveedores SET activo=0 WHERE id=?", (proveedor_id,))
            try: self.db.commit()
            except Exception: pass
            self._cargar_tabla()
            self._cargar_combo_proveedores()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ── Datos ──────────────────────────────────────────────────────────────

    def _cargar_tabla(self):
        try:
            rows = self.db.execute("""
                SELECT p.id, p.nombre, p.telefono, p.email, p.contacto,
                       COALESCE(p.condiciones_pago,0) as condiciones_pago,
                       COALESCE(SUM(ap.balance),0) as saldo_pendiente
                FROM proveedores p
                LEFT JOIN accounts_payable ap ON ap.supplier_id=p.id
                  AND ap.status='pendiente'
                WHERE p.activo=1
                GROUP BY p.id
                ORDER BY p.nombre
                LIMIT 300
            """).fetchall()
        except Exception:
            try:
                rows = self.db.execute(
                    "SELECT id,nombre,telefono,email,contacto,COALESCE(condiciones_pago,0),0 "
                    "FROM proveedores WHERE activo=1 ORDER BY nombre LIMIT 300"
                ).fetchall()
            except Exception as e:
                logger.warning("_cargar_tabla: %s", e); rows = []

        self.tbl.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            pid, nombre = r[0], r[1]
            vals = [nombre, r[2] or "", r[3] or "", r[4] or "",
                    f"{int(r[5] or 0)} días", f"${float(r[6] or 0):,.2f}"]
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
        dlg = DialogoProveedor(self.db, proveedor_id, self)
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
        try:
            rows = self.db.execute(
                "SELECT id, nombre FROM proveedores WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            self.cmb_proveedor_hist.blockSignals(True)
            self.cmb_proveedor_hist.clear()
            for r in rows:
                self.cmb_proveedor_hist.addItem(r[1], r[0])
            self.cmb_proveedor_hist.blockSignals(False)
            self._cargar_historial_precios()
        except Exception as e:
            logger.debug("_cargar_combo: %s", e)

    def _cargar_historial_precios(self):
        pid = self.cmb_proveedor_hist.currentData()
        if not pid: return
        try:
            rows = self.db.execute("""
                SELECT pr.nombre, dc.precio_unitario, dc.cantidad,
                       c.fecha, c.id
                FROM detalles_compra dc
                JOIN productos pr ON pr.id = dc.producto_id
                JOIN compras c ON c.id = dc.compra_id
                WHERE c.proveedor_id=?
                ORDER BY c.fecha DESC
                LIMIT 200
            """, (pid,)).fetchall()
        except Exception:
            rows = []
        self.tbl_hist.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            vals = [r[0], f"${float(r[1]):.4f}", f"{float(r[2]):.2f}",
                    str(r[3])[:10], f"#{r[4]}"]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci in (1, 2):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tbl_hist.setItem(ri, ci, it)

    def _cargar_evaluacion(self):
        try:
            rows = self.db.execute("""
                SELECT p.nombre,
                       COUNT(c.id) as num_compras,
                       COALESCE(SUM(c.total),0) as total_comprado,
                       MAX(c.fecha) as ultima,
                       COALESCE(SUM(ap.balance),0) as saldo_pend
                FROM proveedores p
                LEFT JOIN compras c ON c.proveedor_id=p.id
                LEFT JOIN accounts_payable ap
                    ON ap.supplier_id=p.id AND ap.status='pendiente'
                WHERE p.activo=1
                GROUP BY p.id
                ORDER BY total_comprado DESC
                LIMIT 100
            """).fetchall()
        except Exception as e:
            logger.warning("_cargar_eval: %s", e); rows = []

        self.tbl_eval.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            saldo = float(r[4] or 0)
            estado = "⚠️ Saldo pendiente" if saldo > 0 else "✅ Al corriente"
            vals = [r[0], str(int(r[1] or 0)),
                    f"${float(r[2] or 0):,.2f}",
                    str(r[3] or "—")[:10],
                    f"${saldo:,.2f}", estado]
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
