# modulos/finanzas_unificadas.py — SPJ POS v13.4
# ── MÓDULO UNIFICADO DE FINANZAS ─────────────────────────────────────────────
# Fusiona: Tesorería + Finanzas + Proveedores en una sola UI con pestañas
# Todos consumen core/services/finance/* (single source of truth)

import logging
import re
from datetime import date, datetime
from typing import List, Dict, Any, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QMessageBox, 
    QLabel, QPushButton, QLineEdit, QComboBox, QFormLayout, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDialog, QDialogButtonBox, QDoubleSpinBox, QSpinBox, QTextEdit,
    QDateEdit, QInputDialog, QFrame, QScrollArea, QSplitter, QListWidget,
    QListWidgetItem, QCompleter, QTimeEdit, QRadioButton, QButtonGroup,
    QCheckBox, QCalendarWidget, QColorDialog, QFontDialog, QFileDialog,
    QStatusBar, QProgressBar, QSlider, QDial, QMenu, QAction, QToolBar,
    QProgressDialog, QSplashScreen, QSystemTrayIcon, QStyleFactory,
    QApplication, QSizePolicy, QStackedWidget, QGridLayout
)
from PyQt5.QtCore import Qt, QTimer, QDate
from PyQt5.QtGui import QFont, QPixmap, QPalette

from modulos.ui_components import PageHeader, Toast

logger = logging.getLogger("spj.finanzas_unificadas")


# ═════════════════════════════════════════════════════════════════════════════
#  DIÁLOGO DE PROVEEDOR CON VALIDACIÓN DE DUPLICADOS
# ═════════════════════════════════════════════════════════════════════════════

class DialogoProveedor(QDialog):
    """Diálogo para crear/editar proveedores con validación estricta de duplicados."""

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
        from modulos.spj_phone_widget import PhoneWidget
        
        lay = QVBoxLayout(self)
        form = QFormLayout()
        
        self.txt_nombre   = QLineEdit()
        self.txt_nombre.setPlaceholderText("Razón social o nombre")
        
        self.txt_rfc      = QLineEdit()
        self.txt_rfc.setPlaceholderText("RFC o NIT")
        
        self.txt_telefono = PhoneWidget()
        self.txt_telefono.setPlaceholderText("5512345678 (10 dígitos)")
        self.txt_telefono.setToolTip("Captura solo los 10 dígitos. El código +52 se agrega automáticamente.")
        
        self.txt_email    = QLineEdit()
        self.txt_email.setPlaceholderText("correo@proveedor.com")
        
        self.txt_contacto = QLineEdit()
        self.txt_contacto.setPlaceholderText("Nombre del contacto")
        
        self.cmb_categoria = QComboBox()
        self.cmb_categoria.addItems(["Productos","Servicios","Insumos","Equipos","Otro"])
        
        self.txt_direccion = QTextEdit()
        self.txt_direccion.setMaximumHeight(60)
        
        self.spin_dias   = QSpinBox()
        self.spin_dias.setRange(0, 180)
        self.spin_dias.setSuffix(" días")
        
        self.spin_limite = QDoubleSpinBox()
        self.spin_limite.setRange(0, 9999999)
        self.spin_limite.setPrefix("$")
        self.spin_limite.setDecimals(2)
        
        self.txt_banco   = QLineEdit()
        self.txt_banco.setPlaceholderText("Banco / CLABE")
        
        self.txt_notas   = QTextEdit()
        self.txt_notas.setMaximumHeight(60)
        
        form.addRow("Nombre *:",     self.txt_nombre)
        form.addRow("RFC / NIT:",    self.txt_rfc)
        form.addRow("Teléfono WA:",  self.txt_telefono)
        form.addRow("Email:",        self.txt_email)
        form.addRow("Contacto:",     self.txt_contacto)
        form.addRow("Categoría:",    self.cmb_categoria)
        form.addRow("Dirección:",    self.txt_direccion)
        form.addRow("Días crédito:", self.spin_dias)
        form.addRow("Límite:",       self.spin_limite)
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
            if not prov:
                return
            self.txt_nombre.setText(prov.get("nombre", ""))
            self.txt_rfc.setText(prov.get("rfc", ""))
            self.txt_telefono.set_phone(prov.get("telefono", ""))
            self.txt_email.setText(prov.get("email", ""))
            self.txt_contacto.setText(prov.get("contacto", ""))
            idx = self.cmb_categoria.findText(prov.get("categoria", "Productos"))
            if idx >= 0:
                self.cmb_categoria.setCurrentIndex(idx)
            self.txt_direccion.setPlainText(prov.get("direccion", ""))
            self.spin_dias.setValue(int(prov.get("condiciones_pago", 0) or 0))
            self.spin_limite.setValue(float(prov.get("limite_credito", 0) or 0))
            self.txt_banco.setText(prov.get("banco", ""))
            self.txt_notas.setPlainText(prov.get("notas", ""))
        except Exception as e:
            logger.warning("_cargar error: %s", e)

    def _normalizar_texto(self, texto: str) -> str:
        """Normaliza texto para comparación: mayúsculas, sin espacios extra."""
        if not texto:
            return ""
        return " ".join(texto.upper().strip().split())

    def _verificar_duplicado(self, nombre: str, rfc: str, telefono: str) -> Optional[str]:
        """
        Verifica si existe un proveedor duplicado.
        Retorna el motivo del duplicado o None si no hay duplicado.
        """
        try:
            # Obtener todos los proveedores activos
            proveedores = self._tps.get_all_proveedores(activo=True, limit=500)
            
            nombre_norm = self._normalizar_texto(nombre)
            rfc_norm = self._normalizar_texto(rfc)
            # Normalizar teléfono: quitar espacios, guiones, y comparar solo dígitos
            tel_digits = "".join(c for c in telefono if c.isdigit()) if telefono else ""
            
            for prov in proveedores:
                # Si estamos editando, saltar el mismo proveedor
                if self.proveedor_id and prov.get('id') == self.proveedor_id:
                    continue
                
                # Comparar nombre
                if nombre_norm and self._normalizar_texto(prov.get('nombre', '')) == nombre_norm:
                    return f"Nombre duplicado: '{prov.get('nombre')}'"
                
                # Comparar RFC
                if rfc_norm and self._normalizar_texto(prov.get('rfc', '')) == rfc_norm:
                    return f"RFC duplicado: '{prov.get('rfc')}'"
                
                # Comparar teléfono (solo si tiene 10+ dígitos)
                prov_tel = prov.get('telefono', '')
                prov_tel_digits = "".join(c for c in prov_tel if c.isdigit()) if prov_tel else ""
                if tel_digits and len(tel_digits) >= 10 and prov_tel_digits == tel_digits:
                    return f"Teléfono duplicado: '{prov_tel}'"
            
            return None
        except Exception as e:
            logger.warning("_verificar_duplicado error: %s", e)
            return None

    def _guardar(self):
        nombre = self.txt_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Aviso", "El nombre es obligatorio.")
            return
        
        # Obtener teléfono en formato E.164 (+52 + 10 dígitos)
        tel = self.txt_telefono.get_e164().strip().replace(" ", "")
        
        # Validar formato de teléfono: debe ser +52 seguido de exactamente 10 dígitos
        if tel and not re.match(r"^\+52\d{10}$", tel):
            QMessageBox.warning(
                self, "Teléfono inválido",
                "Formato requerido: +52 + 10 dígitos (ej: +525512345678)\n"
                "El número debe tener exactamente 10 dígitos después del código de país."
            )
            return
        
        # VERIFICAR DUPLICADOS ANTES DE GUARDAR
        rfc = self.txt_rfc.text().strip()
        motivo_duplicado = self._verificar_duplicado(nombre, rfc, tel)
        
        if motivo_duplicado:
            QMessageBox.critical(
                self, "Proveedor Duplicado",
                f"No se puede guardar el proveedor.\n\n"
                f"{motivo_duplicado}\n\n"
                "Por favor verifique los datos e intente con información diferente."
            )
            return
        
        datos = {
            "nombre": nombre,
            "rfc": rfc,
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


# ═════════════════════════════════════════════════════════════════════════════
#  DIÁLOGO DE ABONO A CUENTAS POR PAGAR/COBRAR CON BOTÓN "PAGAR TOTAL"
# ═════════════════════════════════════════════════════════════════════════════

class DialogoAbono(QDialog):
    """Diálogo para abonar a cuentas por pagar o cobrar con opción de pagar total."""

    def __init__(self, deuda, tipo="pagar", treasury_service=None, usuario="", parent=None):
        """
        tipo: "pagar" para CxP (proveedores), "cobrar" para CxC (clientes)
        """
        super().__init__(parent)
        self.deuda = deuda
        self.tipo = tipo
        self.ts = treasury_service
        self.usuario = usuario
        self.monto_aplicado = 0.0
        
        titulo = "Abono a Proveedor" if tipo == "pagar" else "Cobro a Cliente"
        self.setWindowTitle(titulo)
        self.setMinimumWidth(400)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        
        # Información de la deuda
        lbl_info = QLabel()
        if self.tipo == "pagar":
            lbl_info.setText(
                f"<b>Proveedor:</b> {self.deuda.get('proveedor', 'N/A')}<br>"
                f"<b>Folio:</b> {self.deuda.get('folio', 'N/A')}<br>"
                f"<b>Concepto:</b> {self.deuda.get('concepto', 'N/A')}<br>"
                f"<b>Saldo Actual:</b> <span style='color:red;font-size:16px;'>${self.deuda.get('saldo', 0):,.2f}</span>"
            )
        else:
            lbl_info.setText(
                f"<b>Cliente:</b> {self.deuda.get('cliente', 'N/A')}<br>"
                f"<b>Folio:</b> {self.deuda.get('folio', 'N/A')}<br>"
                f"<b>Concepto:</b> {self.deuda.get('concepto', 'N/A')}<br>"
                f"<b>Saldo Actual:</b> <span style='color:green;font-size:16px;'>${self.deuda.get('saldo', 0):,.2f}</span>"
            )
        lay.addWidget(lbl_info)
        
        # Input de monto
        form = QFormLayout()
        self.spin_monto = QDoubleSpinBox()
        self.spin_monto.setRange(0.01, self.deuda.get('saldo', 9999999))
        self.spin_monto.setPrefix("$ ")
        self.spin_monto.setDecimals(2)
        self.spin_monto.setValue(self.deuda.get('saldo', 0))
        form.addRow("Monto a aplicar:", self.spin_monto)
        lay.addLayout(form)
        
        # Checkbox para pagar total
        self.chk_pagar_total = QCheckBox("✅ Pagar/Pagar Total")
        self.chk_pagar_total.setChecked(True)
        self.chk_pagar_total.stateChanged.connect(self._toggle_pagar_total)
        lay.addWidget(self.chk_pagar_total)
        
        # Método de pago
        self.cmb_metodo = QComboBox()
        if self.tipo == "pagar":
            self.cmb_metodo.addItems(["Transferencia", "Efectivo", "Cheque"])
        else:
            self.cmb_metodo.addItems(["Efectivo", "Transferencia", "Tarjeta"])
        lay.addWidget(QLabel("Método de pago:"))
        lay.addWidget(self.cmb_metodo)
        
        # Botones
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._aplicar)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _toggle_pagar_total(self, state):
        """Autocompleta el monto con el saldo total cuando se marca pagar total."""
        if state == Qt.Checked:
            self.spin_monto.setValue(self.deuda.get('saldo', 0))
            self.spin_monto.setEnabled(False)
        else:
            self.spin_monto.setEnabled(True)

    def _aplicar(self):
        monto = self.spin_monto.value()
        metodo = self.cmb_metodo.currentText()
        
        if monto <= 0:
            QMessageBox.warning(self, "Aviso", "El monto debe ser mayor a 0.")
            return
        
        try:
            if self.tipo == "pagar":
                self.ts.abonar_cuenta_por_pagar(
                    self.deuda['id'], monto, metodo, self.usuario
                )
                Toast.success(
                    self.parent() or self, "Abono registrado",
                    f"Abono de ${monto:,.2f} registrado correctamente.",
                )
            else:
                self.ts.abonar_cuenta_por_cobrar(
                    self.deuda['id'], monto, metodo, self.usuario
                )
                Toast.success(
                    self.parent() or self, "Pago registrado",
                    f"Pago de ${monto:,.2f} registrado correctamente.",
                )
            self.monto_aplicado = monto
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


# ═════════════════════════════════════════════════════════════════════════════
#  MÓDULO PRINCIPAL UNIFICADO DE FINANZAS
# ═════════════════════════════════════════════════════════════════════════════

class ModuloFinanzasUnificadas(QWidget):
    """
    Módulo unificado de Finanzas que integra:
    - Pestaña 1: Tesorería (flujo de caja, gastos futuros/fijos, CAPEX, CxP, CxC)
    - Pestaña 2: Finanzas (gastos operativos, nómina)
    - Pestaña 3: Proveedores (CRUD, historial, evaluación)
    
    Todas las operaciones consumen servicios unificados:
    - core/services/finance/treasury_service.py
    - core/services/finance/third_party_service.py
    """
    
    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container = container
        self.sucursal_id = 1
        self.usuario_actual = ""
        self._ts = getattr(container, 'treasury_service', None)
        self._tps = getattr(container, 'third_party_service', None)
        self._fs = getattr(container, 'finance_service', None)
        self._analytics = getattr(container, "analytics_engine", None)
        self._tabs = None
        self._setup_ui()
        self._wire_live_refresh()
        self._wire_kpi_auto_refresh()
        
    def set_sucursal(self, sucursal_id: int, nombre: str = ""):
        self.sucursal_id = sucursal_id
        self._cargar_datos_actuales()
    
    def set_usuario_actual(self, usuario: str, rol: str = ""):
        self.usuario_actual = usuario

    def _wire_live_refresh(self):
        """Refresca tablas de finanzas en caliente sin reiniciar la app."""
        try:
            from core.events.event_bus import get_bus
            bus = get_bus()
            bus.subscribe("PROVEEDOR_CREADO", lambda _: QTimer.singleShot(0, self._cargar_proveedores), label="fin.ui.prov_creado")
            bus.subscribe("PROVEEDOR_ACTUALIZADO", lambda _: QTimer.singleShot(0, self._cargar_proveedores), label="fin.ui.prov_act")
            bus.subscribe("PROVEEDOR_ELIMINADO", lambda _: QTimer.singleShot(0, self._cargar_proveedores), label="fin.ui.prov_del")
            bus.subscribe("CXP_CREADA", lambda _: QTimer.singleShot(0, self._cargar_cuentas_pagar), label="fin.ui.cxp_creada")
            bus.subscribe("CXC_CREADA", lambda _: QTimer.singleShot(0, self._cargar_cuentas_cobrar), label="fin.ui.cxc_creada")
            bus.subscribe("CLIENTE_CREADO", lambda _: QTimer.singleShot(0, self._cargar_cuentas_cobrar), label="fin.ui.cliente_creado")
        except Exception:
            pass

    def _wire_kpi_auto_refresh(self):
        """Suscribe eventos de negocio para refrescar KPIs del dashboard."""
        try:
            self._kpi_timer = QTimer(self)
            self._kpi_timer.setInterval(15000)
            self._kpi_timer.timeout.connect(self._refresh_kpis_if_dashboard_visible)
            self._kpi_timer.start()
            from core.events.event_bus import get_bus
            bus = get_bus()
            for evt in ("VENTA_COMPLETADA", "MOVIMIENTO_FINANCIERO", "CXP_CREADA", "CXC_CREADA", "AJUSTE_INVENTARIO"):
                bus.subscribe(evt, lambda _d: QTimer.singleShot(0, self._cargar_dashboard_financiero), label=f"fin.ui.kpi.{evt.lower()}")
        except Exception:
            pass

    def _refresh_kpis_if_dashboard_visible(self):
        """Evita trabajo innecesario cuando la pestaña dashboard no está visible."""
        if self._tabs and self._tabs.currentIndex() != 0:
            return
        self._cargar_dashboard_financiero()
    
    def _setup_ui(self):
        """Configura la interfaz con pestañas unificadas."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        
        # Crear widget de pestañas principal — los colores vienen del QSS
        # global construido en modulos/qss_builder.py (Oscuro y Claro).
        tabs = QTabWidget()
        self._tabs = tabs
        tabs.setObjectName("finanzasTabs")
        tabs.setAccessibleName("Módulo Finanzas")
        tabs.setDocumentMode(False)
        
        # Pestaña 0: Dashboard financiero
        tab_dashboard = self._crear_pestaña_dashboard()
        tabs.addTab(tab_dashboard, "📊 Dashboard")

        # Pestaña 1: Tesorería (incluye CAPEX, CxP, CxC)
        tab_tesoreria = self._crear_pestaña_tesoreria()
        tabs.addTab(tab_tesoreria, "💰 Tesorería")
        
        # Pestaña 2: Finanzas
        tab_finanzas = self._crear_pestaña_finanzas()
        tabs.addTab(tab_finanzas, "📊 Finanzas")
        
        # Pestaña 3: Proveedores
        tab_proveedores = self._crear_pestaña_proveedores()
        tabs.addTab(tab_proveedores, "🏭 Proveedores")
        
        layout.addWidget(tabs)
        
        # Conectar cambio de pestaña para cargar datos
        tabs.currentChanged.connect(self._on_tab_changed)
        self._normalizar_botones_ui()

    def _normalizar_botones_ui(self):
        """Evita botones full-width; delega colores al QSS global del tema."""
        for btn in self.findChildren(QPushButton):
            # Mantener icon-buttons compactos de tablas.
            if btn.maximumWidth() <= 36 or (btn.minimumWidth() and btn.minimumWidth() <= 36):
                continue
            btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            if btn.minimumHeight() < 30:
                btn.setMinimumHeight(30)
            # Asignar objectName si aún no tiene uno definido, para que el QSS
            # global lo estilice correctamente en cualquier tema (claro/oscuro).
            if not btn.objectName() or btn.objectName() == btn.__class__.__name__:
                txt = (btn.text() or "").lower()
                if any(k in txt for k in ("eliminar", "baja", "cancelar", "retirar")):
                    btn.setObjectName("dangerBtn")
                elif any(k in txt for k in ("guardar", "nuevo", "inyectar", "cobrar", "pagar")):
                    btn.setObjectName("primaryBtn")
                else:
                    btn.setObjectName("secondaryBtn")
            # Limpiar cualquier estilo inline hardcodeado que anule el tema global.
            if btn.styleSheet():
                btn.setStyleSheet("")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
    
    def _on_tab_changed(self, index):
        """Carga datos según la pestaña activa."""
        if index == 0:  # Dashboard
            self._cargar_dashboard_financiero()
        elif index == 1:  # Tesorería
            self._cargar_capex()
            self._cargar_cuentas_pagar()
            self._cargar_cuentas_cobrar()
        elif index == 3:  # Proveedores
            self._cargar_proveedores()
    
    def _cargar_datos_actuales(self):
        """Refresca todos los datos."""
        self._cargar_dashboard_financiero()
        self._cargar_capex()
        self._cargar_cuentas_pagar()
        self._cargar_cuentas_cobrar()
        self._cargar_proveedores()

    def set_active_submodule(self, name: str) -> None:
        """Selecciona un submódulo interno (compatibilidad con wrappers legacy)."""
        if not self._tabs:
            return
        index_by_name = {
            "dashboard": 0,
            "tesoreria": 1,
            "finanzas": 2,
            "proveedores": 3,
        }
        idx = index_by_name.get((name or "").lower())
        if idx is not None:
            self._tabs.setCurrentIndex(idx)

    def _crear_pestaña_dashboard(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        grp = QGroupBox("KPIs Financieros")
        g = QGridLayout(grp)
        self._kpi_labels = {}
        kpis = [
            ("flujo_caja", "Flujo de caja"),
            ("ingresos_egresos", "Ingresos vs egresos"),
            ("cxp_aging", "Cuentas por pagar (aging)"),
            ("cxc_aging", "Cuentas por cobrar (aging)"),
            ("liquidez", "Liquidez"),
            ("margen_operativo", "Margen operativo"),
        ]
        for i, (key, title) in enumerate(kpis):
            row, col = divmod(i, 2)
            cell = QGroupBox(title)
            cell_l = QVBoxLayout(cell)
            lbl = QLabel("—")
            lbl.setObjectName("kpiValue")
            cell_l.addWidget(lbl, 0, Qt.AlignCenter)
            self._kpi_labels[key] = lbl
            g.addWidget(cell, row, col)
        layout.addWidget(grp)
        layout.addStretch()
        return widget

    def _cargar_dashboard_financiero(self):
        if not getattr(self, "_kpi_labels", None):
            return
        try:
            hoy = date.today().isoformat()
            sales = self._analytics.sales_metrics(hoy, self.sucursal_id) if self._analytics else {}
            total_ventas = float(sales.get("total_ventas", 0))
            kpis = self._ts.kpis_financieros() if self._ts else {}
            eg = (kpis.get("egresos") or {})
            total_eg = float(eg.get("total_egresos", 0))
            self._kpi_labels["flujo_caja"].setText(f"${(total_ventas - total_eg):,.2f}")
            self._kpi_labels["ingresos_egresos"].setText(f"${total_ventas:,.2f} / ${total_eg:,.2f}")
            self._kpi_labels["cxp_aging"].setText(f"${float(kpis.get('cxp_pendiente', 0) or 0):,.2f}")
            self._kpi_labels["cxc_aging"].setText(f"${float(kpis.get('cxc_pendiente', 0) or 0):,.2f}")
            self._kpi_labels["liquidez"].setText(f"{float(kpis.get('liquidez', 0)):.2f}")
            self._kpi_labels["margen_operativo"].setText(f"{float(kpis.get('margen_operativo_pct', 0)):.1f}%")
        except Exception as e:
            logger.warning("_cargar_dashboard_financiero: %s", e)
    
    # ──────────────────────────────────────────────────────────────────────────
    #  PESTAÑA 1: TESORERÍA (CAPEX, CxP, CxC)
    # ──────────────────────────────────────────────────────────────────────────
    
    def _crear_pestaña_tesoreria(self):
        """Crea la pestaña de Tesorería con CAPEX, CxP y CxC."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Sub-pestañas para organizar mejor
        sub_tabs = QTabWidget()
        
        # Sub-pestaña CAPEX
        tab_capex = self._crear_subpestaña_capex()
        sub_tabs.addTab(tab_capex, "💵 Capital / CAPEX")
        
        # Sub-pestaña Cuentas por Pagar
        tab_cxp = self._crear_subpestaña_cxp()
        sub_tabs.addTab(tab_cxp, "🧾 Cuentas por Pagar")
        
        # Sub-pestaña Cuentas por Cobrar
        tab_cxc = self._crear_subpestaña_cxc()
        sub_tabs.addTab(tab_cxc, "💰 Cuentas por Cobrar")
        
        layout.addWidget(sub_tabs)
        return widget
    
    def _crear_subpestaña_capex(self):
        """Crea la sub-pestaña de CAPEX con resumen e inyección/retiro de capital."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Resumen de capital
        grp_resumen = QGroupBox("📊 Resumen de Capital")
        r_lay = QHBoxLayout(grp_resumen)
        
        self._lbl_capital_invertido = QLabel("$0.00")
        self._lbl_capital_invertido.setObjectName("kpiValue")
        self._lbl_capital_disponible = QLabel("$0.00")
        self._lbl_capital_disponible.setObjectName("kpiValue")
        self._lbl_roi = QLabel("0%")
        self._lbl_roi.setObjectName("kpiValue")
        self._lbl_salud = QLabel("")
        self._lbl_salud.setObjectName("subheading")
        
        for lbl_title, lbl_val in [
            ("Capital Invertido", self._lbl_capital_invertido),
            ("Capital Disponible", self._lbl_capital_disponible),
            ("ROI", self._lbl_roi),
            ("Salud", self._lbl_salud),
        ]:
            col = QVBoxLayout()
            t = QLabel(lbl_title)
            t.setObjectName("caption")
            t.setAlignment(Qt.AlignCenter)
            lbl_val.setAlignment(Qt.AlignCenter)
            col.addWidget(t)
            col.addWidget(lbl_val)
            r_lay.addLayout(col)
        
        layout.addWidget(grp_resumen)
        
        # Inyectar / Retirar capital
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
        btn_inyectar.setObjectName("successBtn")
        btn_inyectar.setCursor(Qt.PointingHandCursor)
        btn_inyectar.clicked.connect(self._on_inyectar_capital)

        btn_retirar = QPushButton("➖ Retirar Capital")
        btn_retirar.setObjectName("dangerBtn")
        btn_retirar.setCursor(Qt.PointingHandCursor)
        btn_retirar.clicked.connect(self._on_retirar_capital)
        
        c_lay.addWidget(QLabel("Monto:"))
        c_lay.addWidget(self._spin_capital)
        c_lay.addWidget(self._txt_desc_capital, 1)
        c_lay.addWidget(btn_inyectar)
        c_lay.addWidget(btn_retirar)
        layout.addWidget(grp_capital)
        
        # Desglose de egresos
        grp_egresos = QGroupBox("📋 Desglose de Egresos del Mes")
        e_lay = QVBoxLayout(grp_egresos)
        
        self._tbl_egresos = QTableWidget(0, 2)
        self._tbl_egresos.setHorizontalHeaderLabels(["Concepto", "Monto ($)"])
        self._tbl_egresos.horizontalHeader().setStretchLastSection(True)
        self._tbl_egresos.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._tbl_egresos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        e_lay.addWidget(self._tbl_egresos)
        layout.addWidget(grp_egresos)
        
        layout.addStretch()
        return widget
    
    def _crear_subpestaña_cxp(self):
        """Crea la sub-pestaña de Cuentas por Pagar con filtro por nombre."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        lbl = QLabel("Facturas y deudas pendientes con proveedores")
        lbl.setObjectName("caption")
        layout.addWidget(lbl)

        top = QHBoxLayout()
        btn_nuevo_cxp = QPushButton("➕ Nueva CxP")
        btn_nuevo_cxp.setObjectName("primaryBtn")
        btn_nuevo_cxp.setCursor(Qt.PointingHandCursor)
        btn_nuevo_cxp.clicked.connect(self._dialogo_nueva_cxp)
        top.addWidget(btn_nuevo_cxp)
        btn_pago_global = QPushButton("💳 Pago global")
        btn_pago_global.clicked.connect(self._dialogo_pago_global_cxp)
        top.addWidget(btn_pago_global)
        top.addStretch()
        layout.addLayout(top)
        
        # Filtro por nombre
        self._txt_filtro_cxp = QLineEdit()
        self._txt_filtro_cxp.setPlaceholderText("🔍 Buscar por Nombre de Proveedor...")
        self._txt_filtro_cxp.textChanged.connect(self._filtrar_cxp)
        layout.addWidget(self._txt_filtro_cxp)
        
        # Tabla de CxP
        self._tabla_cxp = QTableWidget()
        self._tabla_cxp.setColumnCount(7)
        self._tabla_cxp.setHorizontalHeaderLabels(
            ["ID", "Fecha", "Folio", "Proveedor", "Concepto", "Saldo", "Acción"]
        )
        self._tabla_cxp.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self._tabla_cxp.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self._tabla_cxp)
        
        return widget
    
    def _crear_subpestaña_cxc(self):
        """Crea la sub-pestaña de Cuentas por Cobrar con filtro por nombre."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        lbl = QLabel("Dinero pendiente de cobro a clientes")
        lbl.setObjectName("caption")
        layout.addWidget(lbl)

        top = QHBoxLayout()
        btn_nuevo_cliente = QPushButton("👤 Nuevo cliente")
        btn_nuevo_cliente.setObjectName("secondaryBtn")
        btn_nuevo_cliente.setCursor(Qt.PointingHandCursor)
        btn_nuevo_cliente.clicked.connect(self._dialogo_nuevo_cliente)
        btn_nuevo_cxc = QPushButton("➕ Nueva CxC")
        btn_nuevo_cxc.setObjectName("successBtn")
        btn_nuevo_cxc.setCursor(Qt.PointingHandCursor)
        btn_nuevo_cxc.clicked.connect(self._dialogo_nueva_cxc)
        top.addWidget(btn_nuevo_cliente)
        top.addWidget(btn_nuevo_cxc)
        btn_cobro_global = QPushButton("💰 Cobro global")
        btn_cobro_global.clicked.connect(self._dialogo_cobro_global_cxc)
        top.addWidget(btn_cobro_global)
        top.addStretch()
        layout.addLayout(top)
        
        # Filtro por nombre
        self._txt_filtro_cxc = QLineEdit()
        self._txt_filtro_cxc.setPlaceholderText("🔍 Buscar por Nombre de Cliente...")
        self._txt_filtro_cxc.textChanged.connect(self._filtrar_cxc)
        layout.addWidget(self._txt_filtro_cxc)
        
        # Tabla de CxC
        self._tabla_cxc = QTableWidget()
        self._tabla_cxc.setColumnCount(7)
        self._tabla_cxc.setHorizontalHeaderLabels(
            ["ID", "Fecha", "Folio", "Cliente", "Concepto", "Saldo", "Acción"]
        )
        self._tabla_cxc.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self._tabla_cxc.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self._tabla_cxc)
        
        return widget
    
    # ──────────────────────────────────────────────────────────────────────────
    #  PESTAÑA 2: FINANZAS
    # ──────────────────────────────────────────────────────────────────────────
    
    def _crear_pestaña_finanzas(self):
        """Crea la pestaña de Finanzas (gastos operativos)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        form_group = QGroupBox("Registrar Nuevo Gasto Operativo")
        form_layout = QFormLayout(form_group)
        
        self.cmb_categoria_gasto = QComboBox()
        self.cmb_categoria_gasto.addItems([
            "Servicios (Luz, Agua)", "Renta", "Nómina", 
            "Mantenimiento", "Papelería", "Impuestos", "Otros"
        ])
        
        self.txt_concepto_gasto = QLineEdit()
        self.txt_concepto_gasto.setPlaceholderText("Ej. Pago recibo de CFE Diciembre")
        
        self.txt_monto_gasto = QDoubleSpinBox()
        self.txt_monto_gasto.setRange(0.1, 999999.0)
        self.txt_monto_gasto.setPrefix("$ ")
        
        self.cmb_metodo_gasto = QComboBox()
        self.cmb_metodo_gasto.addItems([
            "Transferencia", "Efectivo (Caja Chica)", "Tarjeta Corporativa"
        ])
        
        btn_guardar = QPushButton("💾 Guardar Gasto")
        btn_guardar.setObjectName("dangerBtn")
        btn_guardar.setCursor(Qt.PointingHandCursor)
        btn_guardar.clicked.connect(self._registrar_gasto)
        
        form_layout.addRow("Categoría:", self.cmb_categoria_gasto)
        form_layout.addRow("Concepto/Descripción:", self.txt_concepto_gasto)
        form_layout.addRow("Monto del Gasto:", self.txt_monto_gasto)
        form_layout.addRow("Método de Pago:", self.cmb_metodo_gasto)
        form_layout.addRow("", btn_guardar)
        
        layout.addWidget(form_group)
        layout.addStretch()
        return widget
    
    # ──────────────────────────────────────────────────────────────────────────
    #  PESTAÑA 3: PROVEEDORES
    # ──────────────────────────────────────────────────────────────────────────
    
    def _crear_pestaña_proveedores(self):
        """Crea la pestaña de Proveedores con tabla CRUD."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Header con botón nuevo
        hdr = QHBoxLayout()
        titulo = QLabel("🏭 Directorio de Proveedores")
        titulo.setObjectName("heading")
        btn_nuevo = QPushButton("➕ Nuevo Proveedor")
        btn_nuevo.setObjectName("successBtn")
        btn_nuevo.setCursor(Qt.PointingHandCursor)
        btn_nuevo.clicked.connect(self._nuevo_proveedor)
        hdr.addWidget(titulo)
        hdr.addStretch()
        hdr.addWidget(btn_nuevo)
        layout.addLayout(hdr)
        
        # Búsqueda
        self._txt_buscar_prov = QLineEdit()
        self._txt_buscar_prov.setPlaceholderText("🔍 Buscar por nombre, RFC o contacto...")
        self._txt_buscar_prov.textChanged.connect(self._filtrar_proveedores)
        layout.addWidget(self._txt_buscar_prov)
        
        # Tabla de proveedores
        self._tabla_proveedores = QTableWidget()
        self._tabla_proveedores.setColumnCount(7)
        self._tabla_proveedores.setHorizontalHeaderLabels(
            ["Nombre", "Teléfono", "Email", "Contacto", "Días crédito", "Saldo", "Acciones"]
        )
        hh = self._tabla_proveedores.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3, 4, 5):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._tabla_proveedores.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tabla_proveedores.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tabla_proveedores.setAlternatingRowColors(True)
        self._tabla_proveedores.verticalHeader().setVisible(False)
        self._tabla_proveedores.doubleClicked.connect(self._editar_proveedor_seleccionado)
        layout.addWidget(self._tabla_proveedores)

        detail = QGroupBox("Detalle de proveedor seleccionado")
        dl = QVBoxLayout(detail)
        self._lbl_proveedor_detalle = QLabel("Selecciona un proveedor para ver sus datos.")
        self._lbl_proveedor_resumen = QLabel("Resumen de cuentas pendientes: $0.00")
        self._lbl_proveedor_resumen.setStyleSheet("font-weight:bold;")
        dl.addWidget(self._lbl_proveedor_detalle)
        dl.addWidget(self._lbl_proveedor_resumen)
        layout.addWidget(detail)
        self._tabla_proveedores.itemSelectionChanged.connect(self._on_proveedor_selected)
        
        return widget
    
    # ──────────────────────────────────────────────────────────────────────────
    #  MÉTODOS DE CAPA / CAPEX
    # ──────────────────────────────────────────────────────────────────────────
    
    def _cargar_capex(self):
        """Carga datos reales de capital y egresos."""
        if not self._ts:
            return
        try:
            kpis = self._ts.kpis_financieros()
            self._lbl_capital_invertido.setText(f"${kpis.get('capital_invertido', 0):,.2f}")
            self._lbl_capital_disponible.setText(f"${kpis.get('capital_disponible', 0):,.2f}")
            self._lbl_roi.setText(f"{kpis.get('roi_pct', 0):.1f}%")
            self._lbl_salud.setText(self._ts._salud(kpis) if hasattr(self._ts, '_salud') else "")
            
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
                ("Comisión MercadoPago", eg.get("mercadopago", 0)),
                ("Comisión Delivery", eg.get("delivery", 0)),
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
        if not self._ts:
            QMessageBox.warning(self, "Error", "TreasuryService no disponible.")
            return
        try:
            self._ts.inyectar_capital(monto, desc, self.usuario_actual)
            Toast.success(self, "Capital inyectado", f"${monto:,.2f}")
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
        if not self._ts:
            QMessageBox.warning(self, "Error", "TreasuryService no disponible.")
            return
        try:
            self._ts.retirar_capital(monto, desc, self.usuario_actual)
            Toast.success(self, "Capital retirado", f"${monto:,.2f}")
            self._spin_capital.setValue(0)
            self._txt_desc_capital.clear()
            self._cargar_capex()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
    
    # ──────────────────────────────────────────────────────────────────────────
    #  MÉTODOS DE CUENTAS POR PAGAR (CxP)
    # ──────────────────────────────────────────────────────────────────────────
    
    def _cargar_cuentas_pagar(self):
        """Carga la tabla de cuentas por pagar."""
        if not self._ts:
            self._tabla_cxp.setRowCount(0)
            return
        try:
            deudas = self._ts.get_cuentas_por_pagar(self.sucursal_id)
            if not deudas and self.sucursal_id:
                deudas = self._ts.get_cuentas_por_pagar(0)
            self._tabla_cxp.setRowCount(len(deudas))
            for row, deuda in enumerate(deudas):
                self._tabla_cxp.setItem(row, 0, QTableWidgetItem(str(deuda['id'])))
                self._tabla_cxp.setItem(row, 1, QTableWidgetItem(str(deuda['fecha']).split()[0]))
                self._tabla_cxp.setItem(row, 2, QTableWidgetItem(deuda['folio']))
                self._tabla_cxp.setItem(row, 3, QTableWidgetItem(deuda['proveedor'] or 'Varios'))
                self._tabla_cxp.setItem(row, 4, QTableWidgetItem(deuda['concepto']))
                
                saldo_item = QTableWidgetItem(f"${deuda['saldo']:,.2f}")
                saldo_item.setForeground(Qt.red)
                saldo_item.setFont(QFont("Arial", 10, QFont.Bold))
                self._tabla_cxp.setItem(row, 5, saldo_item)
                
                btn_pagar = self._create_compact_action_button("💸 Abonar", "primary")
                btn_pagar.clicked.connect(lambda _, d=deuda: self._dialogo_abono_cxp(d))
                self._tabla_cxp.setCellWidget(row, 6, btn_pagar)
        except Exception as e:
            logger.error(f"Error cargando CxP: {e}")
    
    def _filtrar_cxp(self):
        """Filtra la tabla de CxP por nombre de proveedor."""
        txt = self._txt_filtro_cxp.text().lower()
        for i in range(self._tabla_cxp.rowCount()):
            nom = (self._tabla_cxp.item(i, 3) or QTableWidgetItem()).text().lower()
            visible = not txt or txt in nom
            self._tabla_cxp.setRowHidden(i, not visible)
    
    def _dialogo_abono_cxp(self, deuda):
        """Muestra diálogo de abono para CxP."""
        if not self._ts:
            QMessageBox.warning(self, "Error", "TreasuryService no disponible.")
            return
        dlg = DialogoAbono(deuda, tipo="pagar", treasury_service=self._ts, usuario=self.usuario_actual, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._cargar_cuentas_pagar()
    
    # ──────────────────────────────────────────────────────────────────────────
    #  MÉTODOS DE CUENTAS POR COBRAR (CxC)
    # ──────────────────────────────────────────────────────────────────────────
    
    def _cargar_cuentas_cobrar(self):
        """Carga la tabla de cuentas por cobrar."""
        if not self._ts:
            self._tabla_cxc.setRowCount(0)
            return
        try:
            deudas = self._ts.get_cuentas_por_cobrar(self.sucursal_id)
            if not deudas and self.sucursal_id:
                deudas = self._ts.get_cuentas_por_cobrar(0)
            self._tabla_cxc.setRowCount(len(deudas))
            for row, deuda in enumerate(deudas):
                self._tabla_cxc.setItem(row, 0, QTableWidgetItem(str(deuda['id'])))
                self._tabla_cxc.setItem(row, 1, QTableWidgetItem(str(deuda['fecha']).split()[0]))
                self._tabla_cxc.setItem(row, 2, QTableWidgetItem(deuda['folio']))
                self._tabla_cxc.setItem(row, 3, QTableWidgetItem(deuda['cliente'] or 'Público'))
                self._tabla_cxc.setItem(row, 4, QTableWidgetItem(deuda['concepto']))
                
                saldo_item = QTableWidgetItem(f"${deuda['saldo']:,.2f}")
                saldo_item.setForeground(Qt.darkGreen)
                saldo_item.setFont(QFont("Arial", 10, QFont.Bold))
                self._tabla_cxc.setItem(row, 5, saldo_item)
                
                btn_cobrar = self._create_compact_action_button("💰 Cobrar", "success")
                btn_cobrar.clicked.connect(lambda _, d=deuda: self._dialogo_abono_cxc(d))
                self._tabla_cxc.setCellWidget(row, 6, btn_cobrar)
        except Exception as e:
            logger.error(f"Error cargando CxC: {e}")

    def _create_compact_action_button(self, text: str, variant: str = "primary") -> QPushButton:
        """Botón compacto para acciones por fila en tablas — usa objectName para herencia de tema."""
        variant_map = {
            "primary": "primaryBtn",
            "success": "successBtn",
            "danger": "dangerBtn",
            "warning": "warningBtn",
            "outline": "outlineBtn",
            "secondary": "secondaryBtn",
        }
        btn = QPushButton(text)
        btn.setFixedHeight(26)
        btn.setMinimumWidth(80)
        btn.setMaximumWidth(110)
        btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setObjectName(variant_map.get(variant, "primaryBtn"))
        return btn
    
    def _filtrar_cxc(self):
        """Filtra la tabla de CxC por nombre de cliente."""
        txt = self._txt_filtro_cxc.text().lower()
        for i in range(self._tabla_cxc.rowCount()):
            nom = (self._tabla_cxc.item(i, 3) or QTableWidgetItem()).text().lower()
            visible = not txt or txt in nom
            self._tabla_cxc.setRowHidden(i, not visible)
    
    def _dialogo_abono_cxc(self, deuda):
        """Muestra diálogo de cobro para CxC."""
        if not self._ts:
            QMessageBox.warning(self, "Error", "TreasuryService no disponible.")
            return
        dlg = DialogoAbono(deuda, tipo="cobrar", treasury_service=self._ts, usuario=self.usuario_actual, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._cargar_cuentas_cobrar()

    def _dialogo_nueva_cxp(self):
        if not self._fs and not hasattr(self.container, "db"):
            QMessageBox.warning(self, "Error", "Servicios financieros no disponibles.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Nueva Cuenta por Pagar")
        lay = QFormLayout(dlg)
        proveedores = self._tps.get_all_proveedores(activo=True, limit=500) if self._tps else []
        txt_proveedor, selected_supplier_id = self._build_autocomplete_selector(
            [{"id": p.get("id"), "label": p.get("nombre", "—")} for p in proveedores],
            placeholder="Buscar proveedor por nombre…"
        )
        txt = QLineEdit(); txt.setPlaceholderText("Concepto")
        monto = QDoubleSpinBox(); monto.setRange(0.01, 999999999); monto.setPrefix("$ "); monto.setDecimals(2)
        due = QDateEdit(); due.setCalendarPopup(True); due.setDate(QDate.currentDate().addDays(30))
        lay.addRow("Proveedor:", txt_proveedor); lay.addRow("Concepto:", txt); lay.addRow("Monto:", monto); lay.addRow("Vence:", due)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        lay.addRow(btns)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        if dlg.exec_() != QDialog.Accepted:
            return
        supplier_id = selected_supplier_id.get("id")
        if not supplier_id:
            QMessageBox.warning(self, "Validación", "Seleccione un proveedor válido desde la búsqueda.")
            return
        try:
            if self._fs and hasattr(self._fs, "crear_cxp"):
                self._fs.crear_cxp(
                    supplier_id=supplier_id,
                    concepto=txt.text().strip() or "Cuenta por pagar",
                    amount=float(monto.value()),
                    due_date=due.date().toString("yyyy-MM-dd"),
                    usuario=self.usuario_actual or "Sistema",
                )
            else:
                raise RuntimeError("FinanceService.crear_cxp no disponible")
        except Exception:
            # Fallback schema-agnóstico para instalaciones con drift
            self.container.db.execute(
                "INSERT INTO accounts_payable(supplier_id, folio, concepto, amount, balance, due_date, status) "
                "VALUES (?,?,?,?,?,?,'pendiente')",
                (
                    supplier_id,
                    f"CXP-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    txt.text().strip() or "Cuenta por pagar",
                    float(monto.value()),
                    float(monto.value()),
                    due.date().toString("yyyy-MM-dd"),
                ),
            )
            try:
                self.container.db.commit()
            except Exception:
                pass
        self._cargar_cuentas_pagar()

    def _dialogo_nueva_cxc(self):
        if not self._fs and not hasattr(self.container, "db"):
            QMessageBox.warning(self, "Error", "Servicios financieros no disponibles.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Nueva Cuenta por Cobrar")
        lay = QFormLayout(dlg)
        clientes = self._listar_clientes()
        txt_cliente, selected_cliente_id = self._build_autocomplete_selector(
            [{"id": c.get("id"), "label": c.get("nombre", "—")} for c in clientes],
            placeholder="Buscar cliente por nombre…"
        )
        txt = QLineEdit(); txt.setPlaceholderText("Concepto")
        monto = QDoubleSpinBox(); monto.setRange(0.01, 999999999); monto.setPrefix("$ "); monto.setDecimals(2)
        due = QDateEdit(); due.setCalendarPopup(True); due.setDate(QDate.currentDate().addDays(15))
        lay.addRow("Cliente:", txt_cliente); lay.addRow("Concepto:", txt); lay.addRow("Monto:", monto); lay.addRow("Vence:", due)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        lay.addRow(btns)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        if dlg.exec_() != QDialog.Accepted:
            return
        cliente_id = selected_cliente_id.get("id")
        if not cliente_id:
            QMessageBox.warning(self, "Validación", "Seleccione un cliente válido desde la búsqueda.")
            return

        # Validar límite de crédito antes de crear CxC
        try:
            row_cli = self.container.db.execute(
                "SELECT COALESCE(saldo,0), COALESCE(limite_credito,0), COALESCE(nombre,'') FROM clientes WHERE id=?",
                (cliente_id,)
            ).fetchone()
            saldo_actual = float(row_cli[0] or 0) if row_cli else 0.0
            limite = float(row_cli[1] or 0) if row_cli else 0.0
            nombre_cli = str(row_cli[2] or "") if row_cli else ""
            monto_nuevo = float(monto.value())
            if limite <= 0:
                QMessageBox.warning(
                    self, "Límite de crédito",
                    f"El cliente '{nombre_cli or cliente_id}' no tiene límite de crédito configurado."
                )
                return
            if saldo_actual + monto_nuevo > limite + 0.01:
                disponible = max(0.0, limite - saldo_actual)
                QMessageBox.warning(
                    self, "Límite excedido",
                    f"Saldo actual: ${saldo_actual:,.2f}\n"
                    f"Límite: ${limite:,.2f}\n"
                    f"Disponible: ${disponible:,.2f}\n\n"
                    f"La nueva CxC (${monto_nuevo:,.2f}) excede el límite."
                )
                return
        except Exception as exc:
            logger.warning("validación límite crédito CxC falló: %s", exc)
            QMessageBox.warning(self, "Validación", "No fue posible validar el límite de crédito del cliente.")
            return
        try:
            if self._fs and hasattr(self._fs, "crear_cxc"):
                self._fs.crear_cxc(
                    cliente_id=cliente_id,
                    concepto=txt.text().strip() or "Cuenta por cobrar",
                    amount=float(monto.value()),
                    due_date=due.date().toString("yyyy-MM-dd"),
                    usuario=self.usuario_actual or "Sistema",
                )
            else:
                raise RuntimeError("FinanceService.crear_cxc no disponible")
        except Exception:
            self.container.db.execute(
                "INSERT INTO accounts_receivable(cliente_id, folio, concepto, amount, balance, due_date, status) "
                "VALUES (?,?,?,?,?,?,'pendiente')",
                (
                    cliente_id,
                    f"CXC-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    txt.text().strip() or "Cuenta por cobrar",
                    float(monto.value()),
                    float(monto.value()),
                    due.date().toString("yyyy-MM-dd"),
                ),
            )
            try:
                self.container.db.commit()
            except Exception:
                pass
        self._cargar_cuentas_cobrar()

    def _dialogo_nuevo_cliente(self):
        if not hasattr(self.container, "db"):
            QMessageBox.warning(self, "Error", "DB no disponible.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Nuevo Cliente")
        lay = QFormLayout(dlg)
        nombre = QLineEdit(); tel = QLineEdit(); email = QLineEdit()
        lay.addRow("Nombre:", nombre); lay.addRow("Teléfono:", tel); lay.addRow("Email:", email)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        lay.addRow(btns)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        if dlg.exec_() != QDialog.Accepted:
            return
        if not nombre.text().strip():
            QMessageBox.warning(self, "Aviso", "El nombre del cliente es obligatorio.")
            return
        self.container.db.execute(
            "INSERT INTO clientes(nombre, telefono, email, activo, sucursal_id, fecha_registro) "
            "VALUES (?,?,?,?,?,datetime('now'))",
            (nombre.text().strip(), tel.text().strip(), email.text().strip(), 1, self.sucursal_id or 1)
        )
        try:
            self.container.db.commit()
        except Exception:
            pass
        self._cargar_cuentas_cobrar()

    def _listar_clientes(self):
        if not hasattr(self.container, "db"):
            return []
        rows = self.container.db.execute(
            "SELECT id, nombre FROM clientes WHERE COALESCE(activo,1)=1 ORDER BY nombre LIMIT 500"
        ).fetchall()
        return [{"id": r[0], "nombre": r[1]} for r in rows]

    def _build_autocomplete_selector(self, items: List[Dict[str, Any]], placeholder: str = ""):
        """
        Crea selector por barra de búsqueda + autocompletar.
        Retorna (QLineEdit, selected_ref_dict) donde selected_ref_dict['id'] guarda el seleccionado.
        """
        txt = QLineEdit()
        txt.setPlaceholderText(placeholder or "Buscar…")
        selected_ref: Dict[str, Any] = {"id": None}
        if not items:
            return txt, selected_ref

        options = [f"{it.get('id')} - {it.get('label','')}" for it in items]
        index_map = {opt: int(it.get("id")) for opt, it in zip(options, items)}
        completer = QCompleter(options)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        txt.setCompleter(completer)

        def _on_activate(text: str):
            selected_ref["id"] = index_map.get(text)
            txt.setText(text)

        completer.activated[str].connect(_on_activate)

        def _sync_manual():
            selected_ref["id"] = index_map.get(txt.text().strip())

        txt.editingFinished.connect(_sync_manual)
        return txt, selected_ref
    
    # ──────────────────────────────────────────────────────────────────────────
    #  MÉTODOS DE GASTOS OPERATIVOS
    # ──────────────────────────────────────────────────────────────────────────
    
    def _registrar_gasto(self):
        """Registra un nuevo gasto operativo."""
        concepto = self.txt_concepto_gasto.text().strip()
        monto = self.txt_monto_gasto.value()
        
        if not concepto:
            QMessageBox.warning(self, "Aviso", "Debe ingresar el concepto del gasto.")
            return
        
        if not self._ts:
            QMessageBox.warning(self, "Error", "TreasuryService no disponible.")
            return
        
        try:
            self._ts.registrar_gasto_opex(
                categoria=self.cmb_categoria_gasto.currentText(),
                concepto=concepto,
                monto=monto,
                metodo_pago=self.cmb_metodo_gasto.currentText(),
                usuario=self.usuario_actual,
                sucursal_id=self.sucursal_id
            )
            Toast.success(self, "Gasto registrado", "Asentado en contabilidad.")
            self.txt_concepto_gasto.clear()
            self.txt_monto_gasto.setValue(0.1)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
    
    # ──────────────────────────────────────────────────────────────────────────
    #  MÉTODOS DE PROVEEDORES
    # ──────────────────────────────────────────────────────────────────────────
    
    def _cargar_proveedores(self):
        """Carga la tabla de proveedores."""
        if not self._tps:
            self._tabla_proveedores.setRowCount(0)
            return
        try:
            rows = self._tps.get_all_proveedores(activo=True, limit=300)
        except Exception as e:
            logger.warning("_cargar_proveedores: %s", e)
            rows = []

        # fallback defensivo para no bloquear la UX si falla el servicio unificado
        if not rows and hasattr(self.container, "db"):
            try:
                cur = self.container.db.execute(
                    "SELECT id,nombre,telefono,email,contacto,"
                    "COALESCE(condiciones_pago,0) FROM proveedores "
                    "WHERE COALESCE(activo,1)=1 ORDER BY nombre LIMIT 300"
                )
                rows = [
                    {
                        "id": r[0], "nombre": r[1], "telefono": r[2], "email": r[3],
                        "contacto": r[4], "condiciones_pago": r[5], "saldo_pendiente": 0.0
                    }
                    for r in cur.fetchall()
                ]
            except Exception as e:
                logger.warning("_cargar_proveedores fallback: %s", e)
        
        self._tabla_proveedores.setRowCount(len(rows))
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
                    it.setData(Qt.UserRole, pid)
                self._tabla_proveedores.setItem(ri, ci, it)
            
            # Botones de acción
            btn_w = QWidget()
            btn_lay = QHBoxLayout(btn_w)
            btn_lay.setContentsMargins(2, 2, 2, 2)
            
            btn_ed = QPushButton("✏️")
            btn_ed.setFixedSize(28, 26)
            btn_ed.setObjectName("outlineBtn")
            btn_ed.setToolTip("Editar")
            btn_ed.setCursor(Qt.PointingHandCursor)
            btn_ed.clicked.connect(lambda _, pid=pid: self._editar_por_id(pid))

            btn_del = QPushButton("🗑️")
            btn_del.setFixedSize(28, 26)
            btn_del.setObjectName("dangerBtn")
            btn_del.setToolTip("Eliminar")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.clicked.connect(lambda _, pid=pid, nom=nombre: self._eliminar_proveedor(pid, nom))
            
            btn_lay.addWidget(btn_ed)
            btn_lay.addWidget(btn_del)
            self._tabla_proveedores.setCellWidget(ri, 6, btn_w)
    
    def _filtrar_proveedores(self):
        """Filtra la tabla de proveedores por nombre, RFC o contacto."""
        txt = self._txt_buscar_prov.text().lower()
        for i in range(self._tabla_proveedores.rowCount()):
            nom = (self._tabla_proveedores.item(i, 0) or QTableWidgetItem()).text().lower()
            tel = (self._tabla_proveedores.item(i, 1) or QTableWidgetItem()).text().lower()
            con = (self._tabla_proveedores.item(i, 3) or QTableWidgetItem()).text().lower()
            visible = not txt or txt in nom or txt in tel or txt in con
            self._tabla_proveedores.setRowHidden(i, not visible)

    def _on_proveedor_selected(self):
        row = self._tabla_proveedores.currentRow()
        if row < 0:
            self._lbl_proveedor_detalle.setText("Selecciona un proveedor para ver sus datos.")
            self._lbl_proveedor_resumen.setText("Resumen de cuentas pendientes: $0.00")
            return
        it = self._tabla_proveedores.item(row, 0)
        proveedor_id = it.data(Qt.UserRole) if it else None
        if not proveedor_id:
            self._lbl_proveedor_detalle.setText("Proveedor no identificado.")
            self._lbl_proveedor_resumen.setText("Resumen de cuentas pendientes: $0.00")
            return
        try:
            prov = self._tps.get_proveedor(int(proveedor_id)) if self._tps else None
            if prov:
                self._lbl_proveedor_detalle.setText(
                    f"Nombre: {prov.get('nombre','-')} | RFC: {prov.get('rfc','-')} | "
                    f"Tel: {prov.get('telefono','-')} | Email: {prov.get('email','-')}"
                )
            else:
                self._lbl_proveedor_detalle.setText("No se encontraron datos generales del proveedor.")
            deudas = [d for d in (self._ts.get_cuentas_por_pagar(0) if self._ts else [])
                      if int(d.get("proveedor_id") or 0) == int(proveedor_id)]
            saldo = sum(float(d.get("saldo", 0) or 0) for d in deudas)
            if saldo <= 0:
                self._lbl_proveedor_resumen.setText("Resumen de cuentas pendientes: Sin cuentas pendientes.")
            else:
                self._lbl_proveedor_resumen.setText(
                    f"Resumen de cuentas pendientes: ${saldo:,.2f} en {len(deudas)} documento(s)."
                )
        except Exception as exc:
            logger.warning("_on_proveedor_selected: %s", exc)
            self._lbl_proveedor_detalle.setText("No fue posible cargar el detalle del proveedor.")
            self._lbl_proveedor_resumen.setText("Resumen de cuentas pendientes: $0.00")

    def _dialogo_pago_global_cxp(self):
        if not self._ts:
            return
        proveedores = self._tps.get_all_proveedores(activo=True, limit=500) if self._tps else []
        if not proveedores:
            QMessageBox.information(self, "Sin proveedores", "No hay proveedores activos para aplicar pago global.")
            return
        nombres = [f"{p.get('id')} - {p.get('nombre','')}" for p in proveedores]
        seleccionado, ok_sel = QInputDialog.getItem(self, "Proveedor", "Selecciona proveedor:", nombres, 0, False)
        if not ok_sel:
            return
        tercero_id = int(str(seleccionado).split(" - ", 1)[0])
        monto, ok = QInputDialog.getDouble(self, "Pago global CxP", "Monto total a aplicar:", 0.0, 0.0, 999999999.0, 2)
        if not ok or monto <= 0:
            return
        metodo, ok2 = QInputDialog.getItem(self, "Método", "Forma de pago:", ["Transferencia", "Efectivo", "Cheque"], 0, False)
        if not ok2:
            return
        self._ts.aplicar_pago_global("proveedor", monto, metodo=metodo, usuario=self.usuario_actual, tercero_id=tercero_id)
        self._cargar_cuentas_pagar()
        self._cargar_dashboard_financiero()

    def _dialogo_cobro_global_cxc(self):
        if not self._ts:
            return
        clientes = self._listar_clientes()
        if not clientes:
            QMessageBox.information(self, "Sin clientes", "No hay clientes activos para aplicar cobro global.")
            return
        nombres = [f"{c.get('id')} - {c.get('nombre','')}" for c in clientes]
        seleccionado, ok_sel = QInputDialog.getItem(self, "Cliente", "Selecciona cliente:", nombres, 0, False)
        if not ok_sel:
            return
        tercero_id = int(str(seleccionado).split(" - ", 1)[0])
        monto, ok = QInputDialog.getDouble(self, "Cobro global CxC", "Monto total a aplicar:", 0.0, 0.0, 999999999.0, 2)
        if not ok or monto <= 0:
            return
        metodo, ok2 = QInputDialog.getItem(self, "Método", "Forma de cobro:", ["Efectivo", "Transferencia", "Tarjeta"], 0, False)
        if not ok2:
            return
        self._ts.aplicar_pago_global("cliente", monto, metodo=metodo, usuario=self.usuario_actual, tercero_id=tercero_id)
        self._cargar_cuentas_cobrar()
        self._cargar_dashboard_financiero()
    
    def _nuevo_proveedor(self):
        """Abre diálogo para crear nuevo proveedor."""
        if not self._tps:
            QMessageBox.warning(self, "Error", "Servicio de proveedores no disponible.")
            return
        dlg = DialogoProveedor(self._tps, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._cargar_proveedores()
    
    def _editar_por_id(self, proveedor_id: int):
        """Abre diálogo para editar proveedor por ID."""
        if not self._tps:
            QMessageBox.warning(self, "Error", "Servicio de proveedores no disponible.")
            return
        dlg = DialogoProveedor(self._tps, proveedor_id, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._cargar_proveedores()
    
    def _editar_proveedor_seleccionado(self):
        """Edita el proveedor seleccionado en la tabla."""
        row = self._tabla_proveedores.currentRow()
        if row < 0:
            return
        pid_item = self._tabla_proveedores.item(row, 0)
        if not pid_item:
            return
        proveedor_id = pid_item.data(Qt.UserRole)
        if not proveedor_id:
            return
        self._editar_por_id(proveedor_id)
    
    def _eliminar_proveedor(self, proveedor_id: int, nombre: str):
        """Elimina un proveedor."""
        resp = QMessageBox.question(
            self, "Eliminar proveedor",
            f"¿Eliminar a '{nombre}'?\nEsta acción no se puede deshacer.",
            QMessageBox.Yes | QMessageBox.No
        )
        if resp != QMessageBox.Yes:
            return
        if not self._tps:
            QMessageBox.warning(self, "Error", "Servicio de proveedores no disponible.")
            return
        try:
            self._tps.delete_proveedor(proveedor_id, soft=True)
            self._cargar_proveedores()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


# Alias para compatibilidad con main_window.py
ModuloFinanzas = ModuloFinanzasUnificadas
