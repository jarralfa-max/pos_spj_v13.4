from core.services.auto_audit import audit_write

# modulos/tesoreria.py
from core.events.event_bus import get_bus
from modulos.spj_styles import spj_btn, apply_btn_styles, apply_object_names
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QMessageBox, QFormLayout, QDoubleSpinBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QDialog, QDialogButtonBox, QHeaderView,
    QAbstractItemView, QFrame, QSplitter, QGridLayout, QListWidget,
    QListWidgetItem, QCompleter, QDateEdit, QTimeEdit, QTabWidget,
    QRadioButton, QButtonGroup, QCheckBox, QSpinBox, QTextEdit, QMenu,
    QAction, QToolBar, QStatusBar, QProgressBar, QSlider, QDial,
    QCalendarWidget, QColorDialog, QFontDialog, QFileDialog, QInputDialog,
    QErrorMessage, QProgressDialog, QSplashScreen, QSystemTrayIcon,
    QStyleFactory, QApplication, QSizePolicy, QStackedWidget, QScrollArea
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

logger = logging.getLogger("spj.audit_cleanup")




class ModuloTesoreria(QWidget):
    """
    Panel de Control Financiero (CFO Dashboard).
    Maneja Gastos, Cuentas por Pagar (Proveedores) y Cobrar (Clientes).
    """
    def __init__(self, container, parent=None):
        super().__init__(parent)
        try:
            from modulos.spj_refresh_mixin import RefreshMixin
            if isinstance(self, RefreshMixin):
                self._init_refresh(container, ["MOVIMIENTO_FINANCIERO", "VENTA_COMPLETADA"])
        except Exception: pass
        self.container = container # 🧠 Inyectamos el servicio
        self.sucursal_id = 1
        self.usuario_actual = ""
        self.init_ui()

    def _on_refresh(self, event_type: str, data: dict) -> None:
        """Auto-refresh al recibir eventos del EventBus."""
        try: self.set_sucursal()
        except Exception: pass

    def set_sucursal(self, sucursal_id: int, nombre_sucursal: str):
        self.sucursal_id = sucursal_id
        self.al_cambiar_pestana(self.tabs.currentIndex())

    def set_usuario_actual(self, usuario: str, rol: str):
        self.usuario_actual = usuario

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.lbl_titulo = QLabel("🏦 Tesorería Corporativa y Finanzas")
        self.lbl_titulo.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(self.lbl_titulo)
        
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { border: 1px solid #ccc; background: white; }")
        
        self.tab_opex = QWidget()
        self.tab_ap = QWidget()
        self.tab_ar = QWidget()
        
        self.tabs.addTab(self.tab_opex, "📉 Gastos Operativos (OPEX)")
        self.tabs.addTab(self.tab_ap, "🧾 Cuentas por Pagar (Proveedores)")
        self.tabs.addTab(self.tab_ar, "💰 Cuentas por Cobrar (Clientes)")

        # ── Nuevas pestañas ──────────────────────────────────────────────
        self.tab_gastos_futuros = QWidget()
        self.tab_gastos_fijos   = QWidget()
        self.tabs.addTab(self.tab_gastos_futuros, "📅 Gastos Futuros")
        self.tabs.addTab(self.tab_gastos_fijos,   "🔄 Gastos Fijos Recurrentes")

        # v13.4: Tab CAPEX / Capital
        self.tab_capex = QWidget()
        self.tabs.addTab(self.tab_capex, "💰 Capital / CAPEX")
        self._setup_tab_capex()

        self.setup_tab_gastos_futuros()
        self.setup_tab_gastos_fijos()
        
        self.setup_tab_opex()
        self.setup_tab_ap()
        self.setup_tab_ar()
        
        layout.addWidget(self.tabs)
        self.tabs.currentChanged.connect(self.al_cambiar_pestana)
        apply_object_names(self)  # Fase 1: design tokens en botones raw

    def al_cambiar_pestana(self, index):
        if index == 1: self.cargar_cuentas_pagar()
        elif index == 2: self.cargar_cuentas_cobrar()
        elif index == 5: self._cargar_capex()

    def al_cambiar_pestana(self, index):
        if index == 1: self.cargar_cuentas_pagar()
        elif index == 2: self.cargar_cuentas_cobrar()
        elif index == 5: self._cargar_capex()

    # =========================================================
    # PESTAÑA: CAPITAL / CAPEX
    # =========================================================
    def _setup_tab_capex(self):
        layout = QVBoxLayout(self.tab_capex)

        # ── Resumen de capital ──
        grp_resumen = QGroupBox("📊 Resumen de Capital")
        r_lay = QHBoxLayout(grp_resumen)

        self._lbl_capital_invertido = QLabel("$0.00")
        self._lbl_capital_invertido.setStyleSheet("font-size:22px;font-weight:bold;color:#27ae60;")
        self._lbl_capital_disponible = QLabel("$0.00")
        self._lbl_capital_disponible.setStyleSheet("font-size:22px;font-weight:bold;color:#2980b9;")
        self._lbl_roi = QLabel("0%")
        self._lbl_roi.setStyleSheet("font-size:18px;font-weight:bold;color:#8e44ad;")
        self._lbl_salud = QLabel("")
        self._lbl_salud.setStyleSheet("font-size:14px;font-weight:bold;")

        for lbl_title, lbl_val in [
            ("Capital Invertido", self._lbl_capital_invertido),
            ("Capital Disponible", self._lbl_capital_disponible),
            ("ROI", self._lbl_roi),
            ("Salud", self._lbl_salud),
        ]:
            col = QVBoxLayout()
            t = QLabel(lbl_title)
            t.setStyleSheet("font-size:11px;color:#7f8c8d;")
            t.setAlignment(Qt.AlignCenter)
            lbl_val.setAlignment(Qt.AlignCenter)
            col.addWidget(t)
            col.addWidget(lbl_val)
            r_lay.addLayout(col)

        layout.addWidget(grp_resumen)

        # ── Inyectar / Retirar capital ──
        grp_capital = QGroupBox("💰 Inyectar / Retirar Capital")
        c_lay = QHBoxLayout(grp_capital)
        self._spin_capital = QDoubleSpinBox()
        self._spin_capital.setRange(0, 99999999)
        self._spin_capital.setPrefix("$ ")
        self._spin_capital.setDecimals(2)
        self._spin_capital.setMinimumWidth(180)
        self._txt_desc_capital = QLineEdit()
        self._txt_desc_capital.setPlaceholderText("Descripción (ej: Capital socio A)")
        btn_inyectar = QPushButton("➕ Inyectar Capital")
        btn_inyectar.setStyleSheet("background:#27ae60;color:white;padding:8px 16px;font-weight:bold;border-radius:4px;")
        btn_inyectar.clicked.connect(self._on_inyectar_capital)
        btn_retirar = QPushButton("➖ Retirar Capital")
        btn_retirar.setStyleSheet("background:#e74c3c;color:white;padding:8px 16px;font-weight:bold;border-radius:4px;")
        btn_retirar.clicked.connect(self._on_retirar_capital)

        c_lay.addWidget(QLabel("Monto:"))
        c_lay.addWidget(self._spin_capital)
        c_lay.addWidget(self._txt_desc_capital, 1)
        c_lay.addWidget(btn_inyectar)
        c_lay.addWidget(btn_retirar)
        layout.addWidget(grp_capital)

        # ── Desglose de egresos del período ──
        grp_egresos = QGroupBox("📋 Desglose de Egresos del Mes")
        e_lay = QVBoxLayout(grp_egresos)
        self._tbl_egresos = QTableWidget(0, 2)
        self._tbl_egresos.setHorizontalHeaderLabels(["Concepto", "Monto ($)"])
        self._tbl_egresos.horizontalHeader().setStretchLastSection(True)
        self._tbl_egresos.horizontalHeader().setSectionResizeMode(0, self._tbl_egresos.horizontalHeader().Stretch)
        self._tbl_egresos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        e_lay.addWidget(self._tbl_egresos)
        layout.addWidget(grp_egresos)

    def _cargar_capex(self):
        """Carga datos reales de capital y egresos."""
        ts = getattr(self.container, 'treasury_service', None)
        if not ts:
            return
        try:
            kpis = ts.kpis_financieros()
            self._lbl_capital_invertido.setText(f"${kpis.get('capital_invertido', 0):,.2f}")
            self._lbl_capital_disponible.setText(f"${kpis.get('capital_disponible', 0):,.2f}")
            self._lbl_roi.setText(f"{kpis.get('roi_pct', 0):.1f}%")
            self._lbl_salud.setText(ts._salud(kpis))

            # Desglose egresos
            eg = kpis.get("egresos", {})
            items = [
                ("Compras de inventario", eg.get("compras_inventario", 0)),
                ("Gastos fijos (renta, luz, agua, gas)", eg.get("gastos_fijos", 0)),
                ("Gastos operativos", eg.get("gastos_operativos", 0)),
                ("Otros gastos", eg.get("gastos_otros", 0)),
                ("Nómina / RRHH", eg.get("nomina_rrhh", 0)),
                ("Merma", eg.get("merma", 0)),
                ("Depreciación activos", eg.get("depreciacion_activos", 0)),
                ("Comisión MercadoPago", eg.get("  mercadopago", 0)),
                ("Comisión Delivery", eg.get("  delivery", 0)),
                ("─────────────────────", 0),
                ("TOTAL EGRESOS", eg.get("total_egresos", 0)),
            ]
            self._tbl_egresos.setRowCount(len(items))
            for i, (concepto, monto) in enumerate(items):
                self._tbl_egresos.setItem(i, 0, QTableWidgetItem(concepto))
                m_item = QTableWidgetItem(f"${monto:,.2f}" if monto else "")
                m_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._tbl_egresos.setItem(i, 1, m_item)
        except Exception as e:
            logger.warning("_cargar_capex: %s", e)

    def _on_inyectar_capital(self):
        monto = self._spin_capital.value()
        desc = self._txt_desc_capital.text().strip()
        if monto <= 0:
            QMessageBox.warning(self, "Aviso", "Ingresa un monto mayor a $0.")
            return
        if not desc:
            QMessageBox.warning(self, "Aviso", "Ingresa una descripción.")
            return
        ts = getattr(self.container, 'treasury_service', None)
        if not ts:
            QMessageBox.warning(self, "Error", "TreasuryService no disponible.")
            return
        try:
            ts.inyectar_capital(monto, desc, self.usuario_actual)
            QMessageBox.information(self, "Éxito", f"Capital inyectado: ${monto:,.2f}")
            self._spin_capital.setValue(0)
            self._txt_desc_capital.clear()
            self._cargar_capex()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_retirar_capital(self):
        monto = self._spin_capital.value()
        desc = self._txt_desc_capital.text().strip()
        if monto <= 0:
            QMessageBox.warning(self, "Aviso", "Ingresa un monto mayor a $0.")
            return
        if not desc:
            QMessageBox.warning(self, "Aviso", "Ingresa una descripción.")
            return
        ts = getattr(self.container, 'treasury_service', None)
        if not ts:
            QMessageBox.warning(self, "Error", "TreasuryService no disponible.")
            return
        try:
            ts.retirar_capital(monto, desc, self.usuario_actual)
            QMessageBox.information(self, "Éxito", f"Capital retirado: ${monto:,.2f}")
            self._spin_capital.setValue(0)
            self._txt_desc_capital.clear()
            self._cargar_capex()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # =========================================================
    # PESTAÑA 1: GASTOS (OPEX)
    # =========================================================
    def setup_tab_opex(self):
        layout = QVBoxLayout(self.tab_opex)
        
        form_group = QGroupBox("Registrar Nuevo Gasto Operativo")
        form_layout = QFormLayout(form_group)
        
        self.cmb_categoria_gasto = QComboBox()
        self.cmb_categoria_gasto.addItems(["Servicios (Luz, Agua)", "Renta", "Nómina", "Mantenimiento", "Papelería", "Impuestos", "Otros"])
        
        self.txt_concepto_gasto = QLineEdit()
        self.txt_concepto_gasto.setPlaceholderText("Ej. Pago recibo de CFE Diciembre")
        
        self.txt_monto_gasto = QDoubleSpinBox()
        self.txt_monto_gasto.setRange(0.1, 999999.0)
        self.txt_monto_gasto.setPrefix("$ ")
        
        self.cmb_metodo_gasto = QComboBox()
        self.cmb_metodo_gasto.addItems(["Transferencia", "Efectivo (Caja Chica)", "Tarjeta Corporativa"])
        
        btn_guardar_gasto = QPushButton("💾 Guardar Gasto")
        btn_guardar_gasto.setStyleSheet("background:#e74c3c;color:white;font-weight:bold;padding:7px 16px;border-radius:5px;")
        btn_guardar_gasto.clicked.connect(self.registrar_gasto)
        
        form_layout.addRow("Categoría:", self.cmb_categoria_gasto)
        form_layout.addRow("Concepto/Descripción:", self.txt_concepto_gasto)
        form_layout.addRow("Monto del Gasto:", self.txt_monto_gasto)
        form_layout.addRow("Método de Pago:", self.cmb_metodo_gasto)
        form_layout.addRow("", btn_guardar_gasto)
        
        layout.addWidget(form_group)
        layout.addStretch()

    def registrar_gasto(self):
        concepto = self.txt_concepto_gasto.text().strip()
        monto = self.txt_monto_gasto.value()
        
        if not concepto:
            QMessageBox.warning(self, "Aviso", "Debe ingresar el concepto del gasto.")
            return
            
        try:
            # 🚀 LLAMADA AL SERVICIO
            self.container.treasury_service.registrar_gasto_opex(
                categoria=self.cmb_categoria_gasto.currentText(),
                concepto=concepto,
                monto=monto,
                metodo_pago=self.cmb_metodo_gasto.currentText(),
                usuario=self.usuario_actual,
                sucursal_id=self.sucursal_id
            )
            QMessageBox.information(self, "Éxito", "Gasto registrado en la contabilidad.")
            self.txt_concepto_gasto.clear()
            self.txt_monto_gasto.setValue(0.1)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # =========================================================
    # PESTAÑA 2: CUENTAS POR PAGAR (AP)
    # =========================================================
    def setup_tab_ap(self):
        layout = QVBoxLayout(self.tab_ap)
        lbl = QLabel("Facturas y deudas pendientes con proveedores (Mercancía o Servicios)")
        lbl.setStyleSheet("color: gray;")
        layout.addWidget(lbl)
        
        self.tabla_ap = QTableWidget()
        self.tabla_ap.setColumnCount(7)
        self.tabla_ap.setHorizontalHeaderLabels(["ID", "Fecha", "Folio/Doc", "Proveedor", "Concepto", "Saldo Pendiente", "Acción"])
        self.tabla_ap.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.tabla_ap.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.tabla_ap)

    def cargar_cuentas_pagar(self):
        self.tabla_ap.setRowCount(0)
        try:
            deudas = self.container.treasury_service.get_cuentas_por_pagar(self.sucursal_id)
            for row, deuda in enumerate(deudas):
                self.tabla_ap.insertRow(row)
                self.tabla_ap.setItem(row, 0, QTableWidgetItem(str(deuda['id'])))
                self.tabla_ap.setItem(row, 1, QTableWidgetItem(str(deuda['fecha']).split()[0]))
                self.tabla_ap.setItem(row, 2, QTableWidgetItem(deuda['folio']))
                self.tabla_ap.setItem(row, 3, QTableWidgetItem(deuda['proveedor'] or 'Varios'))
                self.tabla_ap.setItem(row, 4, QTableWidgetItem(deuda['concepto']))
                
                saldo_item = QTableWidgetItem(f"${deuda['saldo']:,.2f}")
                saldo_item.setForeground(Qt.red)
                saldo_item.setFont(QFont("Arial", 10, QFont.Bold))
                self.tabla_ap.setItem(row, 5, saldo_item)
                
                btn_pagar = QPushButton("💸 Abonar / Liquidar")
                btn_pagar.setStyleSheet("background:#2E86C1;color:white;font-weight:bold;padding:7px 16px;border-radius:5px;")
                btn_pagar.clicked.connect(lambda _, d=deuda: self.dialogo_abono_ap(d))
                self.tabla_ap.setCellWidget(row, 6, btn_pagar)
        except Exception as e:
            logger.error(f"Error cargando AP: {e}")

    # ══════════════════════════════════════════════════════════════════════
    # TAB: 📅 Gastos Futuros programados
    # ══════════════════════════════════════════════════════════════════════
    def setup_tab_gastos_futuros(self):
        """Gastos programados a futuro: fecha + estimación + estado."""
        from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QFormLayout,
            QGroupBox, QLineEdit, QDoubleSpinBox, QDateEdit,
            QComboBox, QTextEdit, QPushButton, QTableWidget,
            QTableWidgetItem, QHeaderView, QMessageBox, QLabel)
        from PyQt5.QtCore import QDate
        lay = QVBoxLayout(self.tab_gastos_futuros)

        # ── Formulario nuevo gasto futuro ───────────────────────────────
        grp = QGroupBox("Programar gasto futuro")
        form = QFormLayout(grp)
        self.gf_concepto  = QLineEdit(); self.gf_concepto.setPlaceholderText("Ej: Renta local norte")
        self.gf_categoria = QComboBox()
        self.gf_categoria.addItems(["Renta", "Nómina", "Servicios", "Proveedor", "Mantenimiento",
                                     "Impuestos", "Seguros", "Marketing", "Otros"])
        self.gf_monto     = QDoubleSpinBox(); self.gf_monto.setRange(1, 9_999_999); self.gf_monto.setDecimals(2); self.gf_monto.setPrefix("$")
        self.gf_fecha     = QDateEdit(QDate.currentDate().addMonths(1)); self.gf_fecha.setCalendarPopup(True)
        self.gf_notas     = QTextEdit(); self.gf_notas.setMaximumHeight(50)
        form.addRow("Concepto *:", self.gf_concepto)
        form.addRow("Categoría:",  self.gf_categoria)
        form.addRow("Monto estimado:", self.gf_monto)
        form.addRow("Fecha programada:", self.gf_fecha)
        form.addRow("Notas:", self.gf_notas)
        lay.addWidget(grp)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("➕ Programar gasto"); btn_add.setStyleSheet("background:#e74c3c;color:white;font-weight:bold;padding:7px 16px;")
        btn_pagar = QPushButton("✅ Marcar como pagado"); btn_pagar.setStyleSheet("background:#27ae60;color:white;padding:7px 16px;")
        btn_del   = QPushButton("🗑️ Eliminar"); btn_del.setStyleSheet("background:#7f8c8d;color:white;padding:7px 16px;")
        btn_row.addWidget(btn_add); btn_row.addWidget(btn_pagar); btn_row.addWidget(btn_del); btn_row.addStretch()
        lay.addLayout(btn_row)

        # ── Tabla ───────────────────────────────────────────────────────
        self.tabla_gf = QTableWidget(); self.tabla_gf.setColumnCount(6)
        self.tabla_gf.setHorizontalHeaderLabels(["ID","Concepto","Categoría","Monto","Fecha","Estado"])
        hh = self.tabla_gf.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla_gf.setColumnHidden(0, True)
        self.tabla_gf.setSelectionBehavior(self.tabla_gf.SelectRows)
        lay.addWidget(self.tabla_gf)

        btn_add.clicked.connect(self._programar_gasto_futuro)
        btn_pagar.clicked.connect(self._marcar_gasto_pagado)
        btn_del.clicked.connect(self._eliminar_gasto_futuro)
        self._ensure_gastos_tables()
        self._cargar_gastos_futuros()

    def _ensure_gastos_tables(self):
        try:
            self.conexion.executescript("""
                CREATE TABLE IF NOT EXISTS gastos_futuros (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    sucursal_id INTEGER DEFAULT 1,
                    concepto   TEXT NOT NULL,
                    categoria  TEXT,
                    monto      REAL NOT NULL,
                    fecha_prog DATE NOT NULL,
                    estado     TEXT DEFAULT 'pendiente',
                    notas      TEXT,
                    created_at DATETIME DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS gastos_fijos (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    sucursal_id INTEGER DEFAULT 1,
                    concepto    TEXT NOT NULL,
                    categoria   TEXT,
                    monto       REAL NOT NULL,
                    dia_del_mes INTEGER DEFAULT 1,
                    frecuencia  TEXT DEFAULT 'mensual',
                    proveedor   TEXT,
                    activo      INTEGER DEFAULT 1,
                    proximo_venc DATE,
                    notas       TEXT
                );
            """)
            try: self.conexion.commit()
            except Exception: pass
            try: get_bus().publish("MOVIMIENTO_FINANCIERO", {"event_type": "MOVIMIENTO_FINANCIERO"})
            except Exception: pass
            except Exception: pass
        except Exception: pass

    def _cargar_gastos_futuros(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtGui import QColor
        try:
            rows = self.conexion.execute("""
                SELECT id, concepto, COALESCE(categoria,''), monto,
                       fecha_prog, COALESCE(estado,'pendiente')
                FROM gastos_futuros
                WHERE sucursal_id=? AND estado != 'eliminado'
                ORDER BY fecha_prog
            """, (self.sucursal_id,)).fetchall()
        except Exception: rows = []
        self.tabla_gf.setRowCount(0)
        from datetime import date
        hoy = date.today().isoformat()
        for i, r in enumerate(rows):
            self.tabla_gf.insertRow(i)
            vals = [str(r[0]), r[1], r[2], f"${r[3]:,.2f}", str(r[4]), r[5]]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if r[5] == 'pagado': it.setForeground(QColor("#27ae60"))
                elif str(r[4]) < hoy and r[5] == 'pendiente':
                    it.setForeground(QColor("#e74c3c"))  # vencido
                self.tabla_gf.setItem(i, j, it)

    def _programar_gasto_futuro(self):
        # [spj-dedup removed local QMessageBox import]
        concepto = self.gf_concepto.text().strip()
        if not concepto:
            QMessageBox.warning(self, "Aviso", "El concepto es obligatorio."); return
        try:
            self.conexion.execute("""
                INSERT INTO gastos_futuros
                (sucursal_id, concepto, categoria, monto, fecha_prog, notas)
                VALUES(?,?,?,?,?,?)""",
                (self.sucursal_id, concepto, self.gf_categoria.currentText(),
                 self.gf_monto.value(),
                 self.gf_fecha.date().toString("yyyy-MM-dd"),
                 self.gf_notas.toPlainText().strip()))
            try: self.conexion.commit()
            except Exception: pass
            try:
                audit_write(getattr(self,'container',None), modulo="TESORERIA",
                    accion="GASTO_FUTURO", entidad="gastos_futuros",
                    usuario=getattr(self,'usuario_actual','Sistema'),
                    sucursal_id=getattr(self,'sucursal_id',1),
                    detalles=f"Concepto: {concepto}, Monto: ${self.gf_monto.value():.2f}")
            except Exception: pass
            self.gf_concepto.clear(); self.gf_notas.clear()
            self._cargar_gastos_futuros()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _marcar_gasto_pagado(self):
        # [spj-dedup removed local QMessageBox import]
        row = self.tabla_gf.currentRow()
        if row < 0: return
        gid = int(self.tabla_gf.item(row, 0).text())
        self.conexion.execute("UPDATE gastos_futuros SET estado='pagado' WHERE id=?", (gid,))
        try: self.conexion.commit()
        except Exception: pass
        self._cargar_gastos_futuros()

    def _eliminar_gasto_futuro(self):
        # [spj-dedup removed local QMessageBox import]
        row = self.tabla_gf.currentRow()
        if row < 0: return
        gid = int(self.tabla_gf.item(row, 0).text())
        if QMessageBox.question(self,"Confirmar","¿Eliminar este gasto programado?",
           QMessageBox.Yes|QMessageBox.No) != QMessageBox.Yes: return
        self.conexion.execute("UPDATE gastos_futuros SET estado='eliminado' WHERE id=?", (gid,))
        try: self.conexion.commit()
        except Exception: pass
        self._cargar_gastos_futuros()

    # ══════════════════════════════════════════════════════════════════════
    # TAB: 🔄 Gastos Fijos Recurrentes
    # ══════════════════════════════════════════════════════════════════════
    def setup_tab_gastos_fijos(self):
        """CxP recurrentes: rentas, nóminas, servicios fijos."""
        from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QFormLayout,
            QGroupBox, QLineEdit, QDoubleSpinBox, QSpinBox,
            QComboBox, QPushButton, QTableWidget,
            QTableWidgetItem, QHeaderView, QMessageBox, QLabel,
            QDialog, QDialogButtonBox)
        lay = QVBoxLayout(self.tab_gastos_fijos)

        info_lbl = QLabel(
            "Los gastos fijos se generan automáticamente como gasto futuro "
            "el día indicado de cada mes/semana."
        )
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("color:#555;background:#fffbea;padding:6px;border-radius:5px;font-size:11px;")
        lay.addWidget(info_lbl)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("➕ Agregar gasto fijo"); btn_add.setStyleSheet("background:#e67e22;color:white;font-weight:bold;padding:7px 16px;")
        btn_tog = QPushButton("⏸️ Pausar/Activar"); btn_tog.setStyleSheet("background:#3498db;color:white;padding:7px 16px;")
        btn_gen = QPushButton("⚡ Generar vencimientos ahora"); btn_gen.setStyleSheet("background:#9b59b6;color:white;padding:7px 16px;")
        btn_row.addWidget(btn_add); btn_row.addWidget(btn_tog); btn_row.addWidget(btn_gen); btn_row.addStretch()
        lay.addLayout(btn_row)

        self.tabla_fijos = QTableWidget(); self.tabla_fijos.setColumnCount(7)
        self.tabla_fijos.setHorizontalHeaderLabels(
            ["ID","Concepto","Categoría","Monto","Frecuencia","Día","Estado"])
        hh = self.tabla_fijos.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla_fijos.setColumnHidden(0, True)
        self.tabla_fijos.setSelectionBehavior(self.tabla_fijos.SelectRows)
        lay.addWidget(self.tabla_fijos)

        btn_add.clicked.connect(self._nuevo_gasto_fijo)
        btn_tog.clicked.connect(self._toggle_gasto_fijo)
        btn_gen.clicked.connect(self._generar_vencimientos)
        self._cargar_gastos_fijos()

    def _cargar_gastos_fijos(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtGui import QColor
        try:
            rows = self.conexion.execute("""
                SELECT id, concepto, COALESCE(categoria,''), monto,
                       COALESCE(frecuencia,'mensual'), COALESCE(dia_del_mes,1), activo
                FROM gastos_fijos WHERE sucursal_id=? ORDER BY activo DESC, concepto
            """, (self.sucursal_id,)).fetchall()
        except Exception: rows = []
        self.tabla_fijos.setRowCount(0)
        for i, r in enumerate(rows):
            self.tabla_fijos.insertRow(i)
            estado = "✅ Activo" if r[6] else "⏸️ Pausado"
            vals = [str(r[0]), r[1], r[2], f"${r[3]:,.2f}", r[4], f"Día {r[5]}", estado]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if not r[6]: it.setForeground(QColor("#aaa"))
                self.tabla_fijos.setItem(i, j, it)

    def _nuevo_gasto_fijo(self):
        from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
            QVBoxLayout, QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QMessageBox)
        dlg = QDialog(self); dlg.setWindowTitle("Nuevo gasto fijo"); dlg.setMinimumWidth(360)
        lay = QVBoxLayout(dlg); form = QFormLayout()
        txt_concepto  = QLineEdit(); txt_concepto.setPlaceholderText("Ej: Renta local principal")
        cmb_categoria = QComboBox(); cmb_categoria.addItems(
            ["Renta", "Nómina", "Electricidad", "Agua", "Gas", "Internet",
             "Seguro", "Proveedor fijo", "Préstamo", "Otros"])
        spin_monto = QDoubleSpinBox(); spin_monto.setRange(1,9_999_999); spin_monto.setPrefix("$")
        cmb_frec   = QComboBox(); cmb_frec.addItems(["mensual","quincenal","semanal","anual"])
        spin_dia   = QSpinBox(); spin_dia.setRange(1,28); spin_dia.setValue(1); spin_dia.setSuffix(" del mes")
        txt_prov   = QLineEdit(); txt_prov.setPlaceholderText("Proveedor / acreedor")
        form.addRow("Concepto *:",   txt_concepto)
        form.addRow("Categoría:",    cmb_categoria)
        form.addRow("Monto:",        spin_monto)
        form.addRow("Frecuencia:",   cmb_frec)
        form.addRow("Día pago:",     spin_dia)
        form.addRow("Proveedor:",    txt_prov)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() != QDialog.Accepted: return
        concepto = txt_concepto.text().strip()
        if not concepto: return
        try:
            self.conexion.execute("""
                INSERT INTO gastos_fijos
                (sucursal_id,concepto,categoria,monto,frecuencia,dia_del_mes,proveedor,activo)
                VALUES(?,?,?,?,?,?,?,1)""",
                (self.sucursal_id, concepto, cmb_categoria.currentText(),
                 spin_monto.value(), cmb_frec.currentText(),
                 spin_dia.value(), txt_prov.text().strip()))
            try: self.conexion.commit()
            except Exception: pass
            self._cargar_gastos_fijos()
        except Exception as e:
            QMessageBox.critical(self,"Error",str(e))

    def _toggle_gasto_fijo(self):
        row = self.tabla_fijos.currentRow()
        if row < 0: return
        fid = int(self.tabla_fijos.item(row,0).text())
        self.conexion.execute(
            "UPDATE gastos_fijos SET activo = CASE WHEN activo=1 THEN 0 ELSE 1 END WHERE id=?",
            (fid,))
        try: self.conexion.commit()
        except Exception: pass
        self._cargar_gastos_fijos()

    def _generar_vencimientos(self):
        """Genera gastos futuros para todos los fijos activos con vencimiento próximo."""
        # [spj-dedup removed local QMessageBox import]
        from datetime import date
        hoy = date.today()
        try:
            fijos = self.conexion.execute("""
                SELECT id, concepto, categoria, monto, frecuencia, dia_del_mes
                FROM gastos_fijos WHERE activo=1 AND sucursal_id=?
            """, (self.sucursal_id,)).fetchall()
            creados = 0
            for f in fijos:
                fid, concepto, cat, monto, frec, dia = f
                # Calcular próxima fecha
                if frec == "mensual":
                    mes = hoy.month + 1 if hoy.day > dia else hoy.month
                    anio = hoy.year + (1 if mes > 12 else 0)
                    mes = mes % 12 or 12
                    prox = date(anio, mes, min(dia, 28))
                elif frec == "quincenal":
                    prox = date(hoy.year, hoy.month, 15) if hoy.day < 15 else                            date(hoy.year if hoy.month < 12 else hoy.year+1,
                                hoy.month+1 if hoy.month < 12 else 1, 1)
                else:
                    from datetime import timedelta
                    prox = hoy + timedelta(days=7)
                # Only create if not already exists for this date
                exists = self.conexion.execute(
                    "SELECT id FROM gastos_futuros WHERE sucursal_id=? AND concepto=? AND fecha_prog=?",
                    (self.sucursal_id, concepto, prox.isoformat())
                ).fetchone()
                if not exists:
                    self.conexion.execute("""
                        INSERT INTO gastos_futuros
                        (sucursal_id, concepto, categoria, monto, fecha_prog)
                        VALUES(?,?,?,?,?)""",
                        (self.sucursal_id, concepto, cat, monto, prox.isoformat()))
                    creados += 1
            try: self.conexion.commit()
            except Exception: pass
            self._cargar_gastos_futuros()
            QMessageBox.information(self,"✅",f"{creados} vencimientos generados en Gastos Futuros.")
        except Exception as e:
            QMessageBox.critical(self,"Error",str(e))


    def dialogo_abono_ap(self, deuda):
        monto, ok = QInputDialog.getDouble(
            self, "Abono a Proveedor", 
            f"Proveedor: {deuda['proveedor']}\nSaldo Actual: ${deuda['saldo']:,.2f}\n\nIngrese el monto a pagar:",
            value=deuda['saldo'], min=0.1, max=deuda['saldo'], decimals=2
        )
        if ok and monto > 0:
            metodo, ok_metodo = QInputDialog.getItem(self, "Método de Pago", "Seleccione cómo se pagó:", ["Transferencia", "Efectivo", "Cheque"], 0, False)
            if ok_metodo:
                try:
                    self.container.treasury_service.abonar_cuenta_por_pagar(deuda['id'], monto, metodo, self.usuario_actual)
                    QMessageBox.information(self, "Éxito", f"Abono de ${monto:,.2f} registrado correctamente.")
                    self.cargar_cuentas_pagar()
                except Exception as e:
                    QMessageBox.critical(self, "Error", str(e))

    # =========================================================
    # PESTAÑA 3: CUENTAS POR COBRAR (AR)
    # =========================================================
    def setup_tab_ar(self):
        layout = QVBoxLayout(self.tab_ar)
        lbl = QLabel("Dinero que nos deben los clientes por ventas a crédito")
        lbl.setStyleSheet("color: gray;")
        layout.addWidget(lbl)
        
        self.tabla_ar = QTableWidget()
        self.tabla_ar.setColumnCount(7)
        self.tabla_ar.setHorizontalHeaderLabels(["ID", "Fecha", "Folio Venta", "Cliente", "Concepto", "Saldo a Favor", "Acción"])
        self.tabla_ar.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.tabla_ar.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.tabla_ar)

    def cargar_cuentas_cobrar(self):
        self.tabla_ar.setRowCount(0)
        try:
            deudas = self.container.treasury_service.get_cuentas_por_cobrar(self.sucursal_id)
            for row, deuda in enumerate(deudas):
                self.tabla_ar.insertRow(row)
                self.tabla_ar.setItem(row, 0, QTableWidgetItem(str(deuda['id'])))
                self.tabla_ar.setItem(row, 1, QTableWidgetItem(str(deuda['fecha']).split()[0]))
                self.tabla_ar.setItem(row, 2, QTableWidgetItem(deuda['folio']))
                self.tabla_ar.setItem(row, 3, QTableWidgetItem(deuda['cliente'] or 'Público'))
                self.tabla_ar.setItem(row, 4, QTableWidgetItem(deuda['concepto']))
                
                saldo_item = QTableWidgetItem(f"${deuda['saldo']:,.2f}")
                saldo_item.setForeground(Qt.darkGreen)
                saldo_item.setFont(QFont("Arial", 10, QFont.Bold))
                self.tabla_ar.setItem(row, 5, saldo_item)
                
                btn_cobrar = QPushButton("💰 Recibir Pago")
                btn_cobrar.setStyleSheet("background-color: #27ae60; color: white;")
                btn_cobrar.clicked.connect(lambda _, d=deuda: self.dialogo_abono_ar(d))
                self.tabla_ar.setCellWidget(row, 6, btn_cobrar)
        except Exception as e:
            logger.error(f"Error cargando AR: {e}")

    def dialogo_abono_ar(self, deuda):
        monto, ok = QInputDialog.getDouble(
            self, "Cobro a Cliente", 
            f"Cliente: {deuda['cliente']}\nDeuda Actual: ${deuda['saldo']:,.2f}\n\nIngrese el dinero recibido:",
            value=deuda['saldo'], min=0.1, max=deuda['saldo'], decimals=2
        )
        if ok and monto > 0:
            metodo, ok_metodo = QInputDialog.getItem(self, "Método de Pago", "Seleccione cómo pagó el cliente:", ["Efectivo", "Transferencia", "Tarjeta"], 0, False)
            if ok_metodo:
                try:
                    self.container.treasury_service.abonar_cuenta_por_cobrar(deuda['id'], monto, metodo, self.usuario_actual)
                    QMessageBox.information(self, "Éxito", f"Pago recibido de ${monto:,.2f} registrado correctamente.")
                    self.cargar_cuentas_cobrar()
                except Exception as e:
                    QMessageBox.critical(self, "Error", str(e))