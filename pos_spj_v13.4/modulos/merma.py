# modulos/merma.py — SPJ POS v13.30
"""
Módulo de registro de merma con:
  - Autocompletado de productos desde la BD
  - Protección financiera (muestra valor de pérdida, confirmación en altos montos)
  - Auditoría completa (audit_logs + EventBus)
  - Historial con datos financieros y filtros
"""
from __future__ import annotations
from modulos.spj_styles import spj_btn, apply_btn_styles
from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import create_primary_button, create_secondary_button, create_input, create_combo, create_card, create_heading, create_caption, apply_tooltip
import logging
import uuid
from datetime import date, datetime

from PyQt5.QtCore import Qt, QDate, QStringListModel
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QDoubleSpinBox,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QGroupBox, QDateEdit, QMessageBox,
    QCompleter, QTabWidget, QFrame, QSpinBox,
)

logger = logging.getLogger("spj.modulo.merma")

# Umbral de protección financiera (pedir confirmación)
UMBRAL_VALOR_ALTO = 500.0  # pesos


class ModuloMerma(QWidget):
    """Registro, visualización y auditoría de merma diaria."""

    MOTIVOS = [
        "Caducidad / vencimiento",
        "Evaporación / deshidratación",
        "Recorte en proceso",
        "Daño en manipulación",
        "Contaminación",
        "Error de proceso",
        "Robo interno",
        "Devolución no reingresable",
        "Otro",
    ]

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container   = container
        self.sucursal_id = getattr(container, 'sucursal_id', 1)
        self.usuario     = ""
        self._productos_cache = []  # [(id, nombre, precio_compra, unidad, existencia)]
        self._selected_product = None
        self._ensure_schema()
        self._build_ui()
        self._cargar_productos()
        self._cargar_historial()

    def set_usuario_actual(self, usuario: str, rol: str = "cajero") -> None:
        self.usuario = usuario

    def set_sucursal(self, sucursal_id: int, nombre: str = "") -> None:
        self.sucursal_id = sucursal_id
        self._cargar_historial()

    # ── Schema migration ──────────────────────────────────────────────────────
    def _ensure_schema(self):
        """Agrega columnas faltantes a la tabla mermas para BDs existentes."""
        db = self.container.db
        for col in ["costo_unitario REAL DEFAULT 0",
                     "valor_perdida REAL DEFAULT 0",
                     "notas TEXT DEFAULT ''",
                     "fecha TEXT"]:
            try:
                db.execute(f"ALTER TABLE mermas ADD COLUMN {col}")
            except Exception:
                pass  # Column already exists
        try:
            db.commit()
        except Exception:
            pass

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        titulo = QLabel("🗑️ Control de Merma")
        titulo.setObjectName("heading")
        hdr.addWidget(titulo)
        hdr.addStretch()
        # Resumen financiero del día
        self.lbl_resumen = QLabel()
        self.lbl_resumen.setObjectName("caption")
        self.lbl_resumen.setStyleSheet(f"color: {Colors.DANGER_BASE}; font-weight: bold;")
        hdr.addWidget(self.lbl_resumen)
        lay.addLayout(hdr)

        tabs = QTabWidget()
        tabs.setObjectName("tabWidget")

        # ── Tab 1: Registro ───────────────────────────────────────────────
        tab_reg = QWidget()
        self._build_tab_registro(tab_reg)
        tabs.addTab(tab_reg, "📝 Registrar Merma")

        # ── Tab 2: Historial ──────────────────────────────────────────────
        tab_hist = QWidget()
        self._build_tab_historial(tab_hist)
        tabs.addTab(tab_hist, "📋 Historial")

        lay.addWidget(tabs)

    def _build_tab_registro(self, parent):
        lay = QVBoxLayout(parent)
        lay.setSpacing(10)

        grp = QGroupBox("Datos de la merma")
        grp.setObjectName("styledGroup")
        form = QFormLayout(grp)
        form.setSpacing(8)

        # ── Búsqueda con autocompletado ───────────────────────────────────
        self.txt_producto = create_input(self, "🔍 Buscar producto por nombre...")
        self._completer_model = QStringListModel()
        self._completer = QCompleter()
        self._completer.setModel(self._completer_model)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.setMaxVisibleItems(12)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        self._completer.activated.connect(self._on_producto_selected)
        self.txt_producto.setCompleter(self._completer)
        form.addRow("Producto:", self.txt_producto)

        # ── Info del producto (feedback visual) ───────────────────────────
        self.lbl_producto_info = QLabel("")
        self.lbl_producto_info.setObjectName("caption")
        form.addRow("", self.lbl_producto_info)

        # ── Cantidad ──────────────────────────────────────────────────────
        self.spin_cantidad = QDoubleSpinBox()
        self.spin_cantidad.setRange(0.001, 99999)
        self.spin_cantidad.setDecimals(3)
        self.spin_cantidad.setStyleSheet(f"padding: {Spacing.XS}; font-size: {Typography.SIZE_SM};")
        self.spin_cantidad.valueChanged.connect(self._actualizar_valor_perdida)
        form.addRow("Cantidad:", self.spin_cantidad)

        # ── Valor estimado de pérdida (protección financiera) ─────────────
        self.lbl_valor_perdida = QLabel("$0.00")
        self.lbl_valor_perdida.setObjectName("heading")
        self.lbl_valor_perdida.setStyleSheet(f"color: {Colors.DANGER_BASE};")
        form.addRow("Valor pérdida:", self.lbl_valor_perdida)

        # ── Motivo ────────────────────────────────────────────────────────
        self.cmb_motivo = create_combo(self, self.MOTIVOS)
        form.addRow("Motivo:", self.cmb_motivo)

        # ── Notas ─────────────────────────────────────────────────────────
        self.txt_notas = create_input(self, "Observaciones (opcional)")
        form.addRow("Notas:", self.txt_notas)

        # ── Fecha ─────────────────────────────────────────────────────────
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setObjectName("inputField")
        form.addRow("Fecha:", self.date_edit)

        lay.addWidget(grp)

        # Botón registrar
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_guardar = create_primary_button(self, "🗑️ Registrar Merma", "Confirmar el registro de la merma seleccionada")
        btn_guardar.clicked.connect(self._registrar)
        btn_row.addWidget(btn_guardar)
        lay.addLayout(btn_row)
        lay.addStretch()

    def _build_tab_historial(self, parent):
        lay = QVBoxLayout(parent)

        # Filtros
        filt = QHBoxLayout()
        lbl_periodo = QLabel("Período:")
        lbl_periodo.setObjectName("caption")
        filt.addWidget(lbl_periodo)
        self.cmb_periodo = create_combo(self, ["Hoy", "Última semana", "Último mes", "Todo"])
        self.cmb_periodo.currentIndexChanged.connect(self._cargar_historial)
        filt.addWidget(self.cmb_periodo)
        filt.addStretch()
        btn_refresh = create_secondary_button(self, "🔄 Actualizar", "Recargar el historial de mermas")
        btn_refresh.clicked.connect(self._cargar_historial)
        filt.addWidget(btn_refresh)
        lay.addLayout(filt)

        # Tabla con columnas financieras
        self.tbl = QTableWidget()
        self.tbl.setObjectName("tableView")
        self.tbl.setColumnCount(9)
        self.tbl.setHorizontalHeaderLabels([
            "Fecha", "Producto", "Cantidad", "Unidad",
            "Costo/u", "Valor Pérdida", "Motivo", "Usuario", "Notas"
        ])
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.verticalHeader().setVisible(False)
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(6, QHeaderView.Stretch)
        lay.addWidget(self.tbl, 1)

        # Totales
        self.lbl_total_hist = QLabel()
        self.lbl_total_hist.setObjectName("caption")
        self.lbl_total_hist.setStyleSheet(f"font-weight: bold; color: {Colors.DANGER_BASE};")
        lay.addWidget(self.lbl_total_hist)

    # ── Productos y autocompletado ────────────────────────────────────────────

    def _cargar_productos(self):
        try:
            rows = self.container.db.execute(
                "SELECT id, nombre, COALESCE(precio_compra,0), COALESCE(unidad,'kg'), "
                "COALESCE(existencia,0) FROM productos WHERE activo=1 ORDER BY nombre LIMIT 2000"
            ).fetchall()
            self._productos_cache = [
                (r[0], r[1], float(r[2]), str(r[3]), float(r[4])) for r in rows
            ]
            nombres = [r[1] for r in self._productos_cache]
            self._completer_model.setStringList(nombres)
        except Exception as e:
            logger.warning("_cargar_productos: %s", e)

    def _on_producto_selected(self, nombre: str):
        for pid, nom, costo, unidad, stock in self._productos_cache:
            if nom == nombre:
                self._selected_product = (pid, nom, costo, unidad, stock)
                self.spin_cantidad.setSuffix(f" {unidad}")
                self.lbl_producto_info.setText(
                    f"Stock actual: {stock:.3f} {unidad}  |  "
                    f"Costo: ${costo:.2f}/{unidad}")
                self._actualizar_valor_perdida()
                return
        self._selected_product = None
        self.lbl_producto_info.setText("")

    def _actualizar_valor_perdida(self):
        if self._selected_product:
            costo = self._selected_product[2]
            cantidad = self.spin_cantidad.value()
            valor = round(cantidad * costo, 2)
            self.lbl_valor_perdida.setText(f"${valor:.2f}")
            # Estilo dinámico según el monto (protección financiera visual)
            if valor >= UMBRAL_VALOR_ALTO:
                self.lbl_valor_perdida.setStyleSheet(
                    f"font-size: {Typography.SIZE_LG}; font-weight: bold; color: {Colors.TEXT_INVERTED}; "
                    f"background-color: {Colors.DANGER_BASE}; padding: {Spacing.XS} {Spacing.SM}; border-radius: {Borders.RADIUS_MD};")
            else:
                self.lbl_valor_perdida.setStyleSheet(
                    f"font-size: {Typography.SIZE_LG}; font-weight: bold; color: {Colors.DANGER_BASE}; "
                    f"padding: {Spacing.XS} {Spacing.SM}; background-color: {Colors.DANGER_BG}; border-radius: {Borders.RADIUS_MD};")
        else:
            self.lbl_valor_perdida.setText("$0.00")

    # ── Registrar merma ───────────────────────────────────────────────────────

    def _registrar(self) -> None:
        # v13.30: Verificar permiso
        try:
            from core.permissions import verificar_permiso
            if not verificar_permiso(self.container, "inventario.ajustar", self):
                return
        except Exception: pass
        nombre   = self.txt_producto.text().strip()
        cantidad = self.spin_cantidad.value()
        motivo   = self.cmb_motivo.currentText()
        notas    = self.txt_notas.text().strip()
        fecha    = self.date_edit.date().toString("yyyy-MM-dd")

        if not nombre:
            QMessageBox.warning(self, "Aviso", "Selecciona un producto."); return
        if cantidad <= 0:
            QMessageBox.warning(self, "Aviso", "La cantidad debe ser > 0."); return

        # Buscar producto
        prod = self._selected_product
        if not prod or prod[1] != nombre:
            # Buscar en BD directamente
            try:
                row = self.container.db.execute(
                    "SELECT id, nombre, COALESCE(precio_compra,0), COALESCE(unidad,'kg'), "
                    "COALESCE(existencia,0) FROM productos WHERE nombre=? AND activo=1",
                    (nombre,)
                ).fetchone()
                if not row:
                    QMessageBox.warning(self, "Aviso", f"Producto '{nombre}' no encontrado.")
                    return
                prod = (row[0], row[1], float(row[2]), str(row[3]), float(row[4]))
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e)); return

        prod_id, _, costo_unitario, unidad, stock_actual = prod
        valor_perdida = round(cantidad * costo_unitario, 2)

        # ── Protección financiera: validar stock ──────────────────────────
        if cantidad > stock_actual:
            resp = QMessageBox.warning(
                self, "⚠️ Stock insuficiente",
                f"La merma ({cantidad:.3f} {unidad}) es mayor al stock actual "
                f"({stock_actual:.3f} {unidad}).\n\n"
                "Esto dejará el inventario en negativo.\n"
                "¿Registrar de todas formas?",
                QMessageBox.Yes | QMessageBox.No)
            if resp != QMessageBox.Yes:
                return

        # ── Protección financiera: confirmación para altos montos ─────────
        if valor_perdida >= UMBRAL_VALOR_ALTO:
            resp = QMessageBox.warning(
                self, "⚠️ Merma de alto valor",
                f"Esta merma tiene un valor de ${valor_perdida:.2f}\n"
                f"({cantidad:.3f} {unidad} × ${costo_unitario:.2f}/{unidad})\n\n"
                f"Producto: {nombre}\n"
                f"Motivo: {motivo}\n\n"
                "¿Confirmar el registro?",
                QMessageBox.Yes | QMessageBox.No)
            if resp != QMessageBox.Yes:
                return

        try:
            from core.db.connection import transaction
            op_id = str(uuid.uuid4())[:12]

            with transaction(self.container.db):
                # Insertar en mermas
                self.container.db.execute("""
                    INSERT INTO mermas
                    (producto_id, sucursal_id, cantidad, unidad, motivo,
                     costo_unitario, valor_perdida, notas, usuario, operation_id, created_at, fecha)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    prod_id, self.sucursal_id, cantidad, unidad, motivo,
                    costo_unitario, valor_perdida, notas,
                    self.usuario, op_id, datetime.now().isoformat(), fecha
                ))

                # Descontar inventario via ApplicationService
                app_svc = getattr(self.container, 'app_service', None)
                if app_svc:
                    app_svc.registrar_merma(
                        producto_id=prod_id, cantidad=cantidad,
                        motivo=motivo, usuario=self.usuario,
                        sucursal_id=self.sucursal_id)
                else:
                    self.container.db.execute(
                        "UPDATE productos SET existencia=MAX(0,existencia-?) WHERE id=?",
                        (cantidad, prod_id))

            # ── Auditoría ─────────────────────────────────────────────────
            try:
                from core.services.auto_audit import audit_write
                audit_write(
                    self.container, modulo="MERMA", accion="REGISTRAR_MERMA",
                    entidad="mermas", entidad_id=op_id, usuario=self.usuario,
                    sucursal_id=self.sucursal_id,
                    detalles=(f"Producto: {nombre} | Cant: {cantidad:.3f} {unidad} | "
                              f"Costo: ${costo_unitario:.2f}/u | "
                              f"Pérdida: ${valor_perdida:.2f} | Motivo: {motivo}"))
            except Exception:
                pass

            # ── EventBus ──────────────────────────────────────────────────
            try:
                from core.events.event_bus import get_bus, AJUSTE_INVENTARIO
                get_bus().publish(AJUSTE_INVENTARIO, {
                    "producto_id": prod_id, "sucursal_id": self.sucursal_id,
                    "tipo": "merma", "cantidad": -cantidad,
                    "valor": -valor_perdida, "usuario": self.usuario,
                })
            except Exception:
                pass

            # Mensaje de éxito
            QMessageBox.information(
                self, "✅ Merma registrada",
                f"Registrado: {cantidad:.3f} {unidad} de '{nombre}'\n"
                f"Valor pérdida: ${valor_perdida:.2f}\n"
                f"Motivo: {motivo}")

            # Limpiar form
            self.txt_producto.clear()
            self.spin_cantidad.setValue(0)
            self.txt_notas.clear()
            self._selected_product = None
            self.lbl_producto_info.setText("")
            self.lbl_valor_perdida.setText("$0.00")
            self._cargar_productos()  # Refrescar stock
            self._cargar_historial()

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ── Historial ─────────────────────────────────────────────────────────────

    def _cargar_historial(self):
        periodo = self.cmb_periodo.currentText() if hasattr(self, 'cmb_periodo') else "Hoy"
        where_fecha = ""
        if periodo == "Hoy":
            where_fecha = "AND COALESCE(m.fecha, m.created_at) >= date('now')"
        elif periodo == "Última semana":
            where_fecha = "AND COALESCE(m.fecha, m.created_at) >= date('now','-7 days')"
        elif periodo == "Último mes":
            where_fecha = "AND COALESCE(m.fecha, m.created_at) >= date('now','-30 days')"

        try:
            rows = self.container.db.execute(f"""
                SELECT COALESCE(m.fecha, substr(m.created_at,1,10)) as fecha,
                       p.nombre, m.cantidad, m.unidad,
                       COALESCE(m.costo_unitario,0), COALESCE(m.valor_perdida,0),
                       m.motivo, m.usuario, COALESCE(m.notas,'')
                FROM mermas m
                JOIN productos p ON p.id = m.producto_id
                WHERE m.sucursal_id = ? {where_fecha}
                ORDER BY COALESCE(m.fecha, m.created_at) DESC, m.id DESC
                LIMIT 500
            """, (self.sucursal_id,)).fetchall()
        except Exception as e:
            logger.debug("_cargar_historial: %s", e)
            rows = []

        self.tbl.setRowCount(len(rows))
        total_valor = 0.0
        total_cantidad = 0.0
        for ri, r in enumerate(rows):
            fecha_str = str(r[0] or "")[:10]
            nombre = str(r[1] or "")
            cant = float(r[2] or 0)
            unidad = str(r[3] or "kg")
            costo = float(r[4] or 0)
            valor = float(r[5] or 0)
            motivo = str(r[6] or "")
            usuario = str(r[7] or "")
            notas = str(r[8] or "")

            vals = [
                fecha_str, nombre, f"{cant:.3f}", unidad,
                f"${costo:.2f}", f"${valor:.2f}",
                motivo, usuario, notas
            ]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci in (2, 4, 5):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if ci == 5 and valor >= UMBRAL_VALOR_ALTO:
                    it.setForeground(QColor("#e74c3c"))
                    it.setFont(QFont("Arial", -1, QFont.Bold))
                self.tbl.setItem(ri, ci, it)

            total_valor += valor
            total_cantidad += cant

        # Actualizar resúmenes
        n_registros = len(rows)
        if hasattr(self, 'lbl_total_hist'):
            self.lbl_total_hist.setText(
                f"Total período: {n_registros} registros  |  "
                f"Cantidad: {total_cantidad:.3f}  |  "
                f"Valor pérdida: ${total_valor:.2f}")

        # Resumen del día en header
        try:
            hoy_row = self.container.db.execute("""
                SELECT COUNT(*), COALESCE(SUM(COALESCE(valor_perdida,0)),0)
                FROM mermas
                WHERE sucursal_id=? AND COALESCE(fecha, substr(created_at,1,10)) = date('now')
            """, (self.sucursal_id,)).fetchone()
            n_hoy = int(hoy_row[0]) if hoy_row else 0
            v_hoy = float(hoy_row[1]) if hoy_row else 0.0
            self.lbl_resumen.setText(
                f"Hoy: {n_hoy} mermas  —  Pérdida: ${v_hoy:.2f}")
        except Exception:
            self.lbl_resumen.setText("Hoy: —")
