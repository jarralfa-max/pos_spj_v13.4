# modulos/finanzas_unificadas.py — SPJ POS v13.4
# ── MÓDULO UNIFICADO DE FINANZAS ─────────────────────────────────────────────
# Arquitectura: Sidebar (12 secciones) + QStackedWidget (lazy loading)
# Todas las operaciones consumen core/services/finance/* (single source of truth)
# NO hay SQL directo en este archivo.

import logging
import re
from datetime import date, datetime
from typing import List, Dict, Any, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QMessageBox,
    QLabel, QPushButton, QLineEdit, QComboBox, QFormLayout, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDialog, QDialogButtonBox, QDoubleSpinBox, QSpinBox, QTextEdit,
    QDateEdit, QInputDialog, QFrame, QSplitter, QListWidget,
    QListWidgetItem, QCompleter, QCheckBox,
    QSizePolicy, QStackedWidget, QGridLayout, QScrollArea
)
from PyQt5.QtCore import Qt, QTimer, QDate
from PyQt5.QtGui import QFont, QColor

from modulos.ui_components import PageHeader, Toast
from modulos.design_tokens import Colors

logger = logging.getLogger("spj.finanzas_unificadas")

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTES DE SECCIONES
# ─────────────────────────────────────────────────────────────────────────────

_SECCIONES = [
    ("Resumen",             "📊"),
    ("Caja y conciliación", "💰"),
    ("Capital",             "🏦"),
    ("Cuentas por cobrar",  "📥"),
    ("Cuentas por pagar",   "📤"),
    ("Movimientos",         "🔄"),
    ("Asientos contables",  "📒"),
    ("Nómina",              "👥"),
    ("Proveedores",         "🏭"),
    ("Clientes con crédito","🤝"),
    ("Reportes",            "📈"),
    ("Configuración",       "⚙️"),
]

_BADGE_COLORS = {
    "pagado":      ("#16a34a", "#dcfce7"),
    "cobrado":     ("#16a34a", "#dcfce7"),
    "conciliado":  ("#16a34a", "#dcfce7"),
    "pendiente":   ("#d97706", "#fef3c7"),
    "parcial":     ("#d97706", "#fef3c7"),
    "vencido":     ("#dc2626", "#fee2e2"),
    "cancelado":   ("#6b7280", "#f3f4f6"),
    "diferencia":  ("#d97706", "#fef3c7"),
    "borrador":    ("#6b7280", "#f3f4f6"),
    "confirmado":  ("#2563eb", "#dbeafe"),
    "reversado":   ("#dc2626", "#fee2e2"),
}


# ═════════════════════════════════════════════════════════════════════════════
#  COMPONENTES REUTILIZABLES DE FINANZAS
# ═════════════════════════════════════════════════════════════════════════════

class _FinSectionHeader(QWidget):
    """Header reutilizable: título, subtítulo y botón Actualizar."""

    def __init__(self, title: str, subtitle: str = "", btn_text: str = "🔄 Actualizar",
                 btn_callback=None, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        col = QVBoxLayout()
        col.setSpacing(2)
        lbl_title = QLabel(title)
        lbl_title.setObjectName("heading")
        col.addWidget(lbl_title)
        if subtitle:
            lbl_sub = QLabel(subtitle)
            lbl_sub.setObjectName("caption")
            col.addWidget(lbl_sub)
        lay.addLayout(col)
        lay.addStretch()

        if btn_text and btn_callback:
            btn = QPushButton(btn_text)
            btn.setObjectName("secondaryBtn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            btn.clicked.connect(btn_callback)
            lay.addWidget(btn)


class _FinKpiCard(QFrame):
    """Tarjeta KPI: etiqueta arriba, valor grande abajo, color semántico."""

    def __init__(self, label: str, value: str = "—", color: str = None, parent=None):
        super().__init__(parent)
        self.setObjectName("finKpiCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumWidth(140)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)

        self._lbl_label = QLabel(label.upper())
        self._lbl_label.setObjectName("caption")
        self._lbl_label.setAlignment(Qt.AlignCenter)

        self._lbl_value = QLabel(value)
        self._lbl_value.setObjectName("kpiValue")
        self._lbl_value.setAlignment(Qt.AlignCenter)
        if color:
            self._lbl_value.setStyleSheet(f"color:{color}; font-size:18px; font-weight:700;")

        lay.addWidget(self._lbl_label)
        lay.addWidget(self._lbl_value)

    def set_value(self, value: str, color: str = None):
        self._lbl_value.setText(value)
        if color:
            self._lbl_value.setStyleSheet(f"color:{color}; font-size:18px; font-weight:700;")


class _FinStatusBadge(QLabel):
    """Badge de estado con colores semánticos."""

    def __init__(self, status: str, parent=None):
        super().__init__(parent)
        self.set_status(status)
        self.setAlignment(Qt.AlignCenter)

    def set_status(self, status: str):
        status_lower = (status or "").lower()
        fg, bg = _BADGE_COLORS.get(status_lower, ("#374151", "#f3f4f6"))
        self.setText(status or "—")
        self.setStyleSheet(
            f"color:{fg}; background:{bg}; border-radius:4px; "
            f"padding:2px 6px; font-size:10px; font-weight:600;"
        )


class _FinEmptyState(QWidget):
    """Estado vacío: icono + mensaje + descripción opcional."""

    def __init__(self, icon: str = "📭", message: str = "Sin datos",
                 description: str = "", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(8)

        lbl_icon = QLabel(icon)
        lbl_icon.setStyleSheet("font-size:40px;")
        lbl_icon.setAlignment(Qt.AlignCenter)

        lbl_msg = QLabel(message)
        lbl_msg.setObjectName("heading")
        lbl_msg.setAlignment(Qt.AlignCenter)

        lay.addWidget(lbl_icon)
        lay.addWidget(lbl_msg)

        if description:
            lbl_desc = QLabel(description)
            lbl_desc.setObjectName("caption")
            lbl_desc.setAlignment(Qt.AlignCenter)
            lbl_desc.setWordWrap(True)
            lay.addWidget(lbl_desc)


class _FinTable(QTableWidget):
    """Tabla estándar con headers, scroll, selección por fila."""

    def __init__(self, headers: List[str], parent=None):
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(headers)
        hh = self.horizontalHeader()
        hh.setStretchLastSection(False)
        # Stretch primera columna no-acción por defecto
        if headers:
            hh.setSectionResizeMode(0, QHeaderView.Stretch)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(True)


def _kpi_row(cards: List[_FinKpiCard]) -> QWidget:
    """Fila horizontal de KPI cards."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    for card in cards:
        lay.addWidget(card)
    lay.addStretch()
    return w


def _compact_btn(text: str, variant: str = "primary") -> QPushButton:
    variant_map = {
        "primary": "primaryBtn", "success": "successBtn",
        "danger": "dangerBtn", "warning": "warningBtn",
        "outline": "outlineBtn", "secondary": "secondaryBtn",
    }
    btn = QPushButton(text)
    btn.setFixedHeight(26)
    btn.setMinimumWidth(70)
    btn.setMaximumWidth(120)
    btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setObjectName(variant_map.get(variant, "primaryBtn"))
    return btn


# ═════════════════════════════════════════════════════════════════════════════
#  DIÁLOGOS REUTILIZABLES
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
        try:
            from modulos.spj_phone_widget import PhoneWidget
            self.txt_telefono = PhoneWidget()
        except Exception:
            self.txt_telefono = QLineEdit()
        self.txt_telefono.setPlaceholderText("5512345678 (10 dígitos)")

        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.txt_nombre    = QLineEdit(); self.txt_nombre.setPlaceholderText("Razón social o nombre")
        self.txt_rfc       = QLineEdit(); self.txt_rfc.setPlaceholderText("RFC o NIT")
        self.txt_email     = QLineEdit(); self.txt_email.setPlaceholderText("correo@proveedor.com")
        self.txt_contacto  = QLineEdit(); self.txt_contacto.setPlaceholderText("Nombre del contacto")
        self.cmb_categoria = QComboBox()
        self.cmb_categoria.addItems(["Productos", "Servicios", "Insumos", "Equipos", "Otro"])
        self.txt_direccion = QTextEdit(); self.txt_direccion.setMaximumHeight(60)
        self.spin_dias     = QSpinBox(); self.spin_dias.setRange(0, 180); self.spin_dias.setSuffix(" días")
        self.spin_limite   = QDoubleSpinBox()
        self.spin_limite.setRange(0, 9999999); self.spin_limite.setPrefix("$"); self.spin_limite.setDecimals(2)
        self.txt_banco     = QLineEdit(); self.txt_banco.setPlaceholderText("Banco / CLABE")
        self.txt_notas     = QTextEdit(); self.txt_notas.setMaximumHeight(60)

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
            if hasattr(self.txt_telefono, "set_phone"):
                self.txt_telefono.set_phone(prov.get("telefono", ""))
            else:
                self.txt_telefono.setText(prov.get("telefono", ""))
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
            logger.warning("DialogoProveedor._cargar error: %s", e)

    def _normalizar_texto(self, texto: str) -> str:
        if not texto:
            return ""
        return " ".join(texto.upper().strip().split())

    def _verificar_duplicado(self, nombre: str, rfc: str, telefono: str) -> Optional[str]:
        try:
            proveedores = self._tps.get_all_proveedores(activo=True, limit=500)
            nombre_norm = self._normalizar_texto(nombre)
            rfc_norm    = self._normalizar_texto(rfc)
            tel_digits  = "".join(c for c in telefono if c.isdigit()) if telefono else ""
            for prov in proveedores:
                if self.proveedor_id and prov.get("id") == self.proveedor_id:
                    continue
                if nombre_norm and self._normalizar_texto(prov.get("nombre", "")) == nombre_norm:
                    return f"Nombre duplicado: '{prov.get('nombre')}'"
                if rfc_norm and self._normalizar_texto(prov.get("rfc", "")) == rfc_norm:
                    return f"RFC duplicado: '{prov.get('rfc')}'"
                prov_tel = prov.get("telefono", "")
                prov_tel_digits = "".join(c for c in prov_tel if c.isdigit()) if prov_tel else ""
                if tel_digits and len(tel_digits) >= 10 and prov_tel_digits == tel_digits:
                    return f"Teléfono duplicado: '{prov_tel}'"
            return None
        except Exception as e:
            logger.warning("_verificar_duplicado: %s", e)
            return None

    def _guardar(self):
        nombre = self.txt_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Aviso", "El nombre es obligatorio.")
            return

        if hasattr(self.txt_telefono, "get_e164"):
            tel = self.txt_telefono.get_e164().strip().replace(" ", "")
        else:
            tel = self.txt_telefono.text().strip()

        if tel and not re.match(r"^\+52\d{10}$", tel):
            QMessageBox.warning(
                self, "Teléfono inválido",
                "Formato requerido: +52 + 10 dígitos (ej: +525512345678)\n"
                "El número debe tener exactamente 10 dígitos después del código de país."
            )
            return

        rfc = self.txt_rfc.text().strip()
        if hasattr(self._tps, "check_duplicate_proveedor"):
            motivo = self._tps.check_duplicate_proveedor(
                nombre=nombre, rfc=rfc, telefono=tel, exclude_id=self.proveedor_id)
        else:
            motivo = self._verificar_duplicado(nombre, rfc, tel)

        if motivo:
            QMessageBox.critical(
                self, "Proveedor Duplicado",
                f"No se puede guardar el proveedor.\n\n{motivo}\n\n"
                "Por favor verifique los datos e intente con información diferente."
            )
            return

        datos = {
            "nombre": nombre, "rfc": rfc, "telefono": tel,
            "email":    self.txt_email.text().strip(),
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


class DialogoAbono(QDialog):
    """Diálogo para abonar a cuentas por pagar o cobrar con opción de pagar total."""

    def __init__(self, deuda, tipo="pagar", treasury_service=None, usuario="", parent=None):
        super().__init__(parent)
        self.deuda = deuda
        self.tipo  = tipo
        self.ts    = treasury_service
        self.usuario = usuario
        self.monto_aplicado = 0.0
        titulo = "Abono a Proveedor" if tipo == "pagar" else "Cobro a Cliente"
        self.setWindowTitle(titulo)
        self.setMinimumWidth(400)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lbl_info = QLabel()
        if self.tipo == "pagar":
            lbl_info.setText(
                f"<b>Proveedor:</b> {self.deuda.get('proveedor','N/A')}<br>"
                f"<b>Folio:</b> {self.deuda.get('folio','N/A')}<br>"
                f"<b>Concepto:</b> {self.deuda.get('concepto','N/A')}<br>"
                f"<b>Saldo:</b> <span style='color:red;font-size:16px;'>"
                f"${self.deuda.get('saldo',0):,.2f}</span>"
            )
        else:
            lbl_info.setText(
                f"<b>Cliente:</b> {self.deuda.get('cliente','N/A')}<br>"
                f"<b>Folio:</b> {self.deuda.get('folio','N/A')}<br>"
                f"<b>Concepto:</b> {self.deuda.get('concepto','N/A')}<br>"
                f"<b>Saldo:</b> <span style='color:green;font-size:16px;'>"
                f"${self.deuda.get('saldo',0):,.2f}</span>"
            )
        lay.addWidget(lbl_info)

        form = QFormLayout()
        self.spin_monto = QDoubleSpinBox()
        self.spin_monto.setRange(0.01, self.deuda.get("saldo", 9999999))
        self.spin_monto.setPrefix("$ ")
        self.spin_monto.setDecimals(2)
        self.spin_monto.setValue(self.deuda.get("saldo", 0))
        form.addRow("Monto a aplicar:", self.spin_monto)
        lay.addLayout(form)

        self.chk_total = QCheckBox("Pagar total")
        self.chk_total.setChecked(True)
        self.chk_total.stateChanged.connect(self._toggle_total)
        lay.addWidget(self.chk_total)

        self.cmb_metodo = QComboBox()
        if self.tipo == "pagar":
            self.cmb_metodo.addItems(["Transferencia", "Efectivo", "Cheque"])
        else:
            self.cmb_metodo.addItems(["Efectivo", "Transferencia", "Tarjeta"])
        lay.addWidget(QLabel("Método de pago:"))
        lay.addWidget(self.cmb_metodo)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._aplicar)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _toggle_total(self, state):
        if state == Qt.Checked:
            self.spin_monto.setValue(self.deuda.get("saldo", 0))
            self.spin_monto.setEnabled(False)
        else:
            self.spin_monto.setEnabled(True)

    def _aplicar(self):
        monto  = self.spin_monto.value()
        metodo = self.cmb_metodo.currentText()
        if monto <= 0:
            QMessageBox.warning(self, "Aviso", "El monto debe ser mayor a 0.")
            return
        try:
            if self.tipo == "pagar":
                self.ts.abonar_cuenta_por_pagar(self.deuda["id"], monto, metodo, self.usuario)
                Toast.success(self.parent() or self, "Abono registrado", f"${monto:,.2f}")
            else:
                self.ts.abonar_cuenta_por_cobrar(self.deuda["id"], monto, metodo, self.usuario)
                Toast.success(self.parent() or self, "Pago registrado", f"${monto:,.2f}")
            self.monto_aplicado = monto
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


# ═════════════════════════════════════════════════════════════════════════════
#  SECCIONES DEL MÓDULO (LAZY)
# ═════════════════════════════════════════════════════════════════════════════

class _SeccionResumen(QWidget):
    def __init__(self, modulo, parent=None):
        super().__init__(parent)
        self._m = modulo
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        lay.addWidget(_FinSectionHeader(
            "Resumen Financiero",
            "Vista consolidada del estado financiero",
            btn_callback=self.recargar
        ))

        # KPIs
        self._kpi_caja    = _FinKpiCard("Caja y bancos", "—", Colors.SUCCESS_BASE)
        self._kpi_cxc     = _FinKpiCard("Cuentas por cobrar", "—", Colors.WARNING_BASE)
        self._kpi_cxp     = _FinKpiCard("Cuentas por pagar", "—", Colors.DANGER_BASE)
        self._kpi_flujo   = _FinKpiCard("Flujo neto del período", "—", Colors.PRIMARY_BASE)
        self._kpi_capital = _FinKpiCard("Capital actual", "$0.00 (pendiente)", Colors.ACCENT_BASE)
        lay.addWidget(_kpi_row([self._kpi_caja, self._kpi_cxc, self._kpi_cxp,
                                self._kpi_flujo, self._kpi_capital]))

        # Panel de alertas
        grp_alertas = QGroupBox("Alertas y pendientes")
        a_lay = QHBoxLayout(grp_alertas)
        self._lbl_cxp_venc = QLabel("CxP vencidas: —")
        self._lbl_cxc_venc = QLabel("CxC vencidas: —")
        self._lbl_dif_caja = QLabel("Diferencias de caja: —")
        for lbl in (self._lbl_cxp_venc, self._lbl_cxc_venc, self._lbl_dif_caja):
            lbl.setObjectName("caption")
            a_lay.addWidget(lbl)
        a_lay.addStretch()
        lay.addWidget(grp_alertas)

        # Acciones rápidas
        grp_acc = QGroupBox("Acciones rápidas")
        acc_lay = QHBoxLayout(grp_acc)
        btn_gasto  = QPushButton("➕ Registrar gasto")
        btn_cobro  = QPushButton("💰 Aplicar cobro")
        btn_pago   = QPushButton("💸 Aplicar pago")
        btn_asiento= QPushButton("📒 Registrar asiento")
        for btn, obj in [(btn_gasto, "secondaryBtn"), (btn_cobro, "successBtn"),
                         (btn_pago, "dangerBtn"),   (btn_asiento, "primaryBtn")]:
            btn.setObjectName(obj)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            acc_lay.addWidget(btn)
        acc_lay.addStretch()
        btn_gasto.clicked.connect(lambda: self._m._nav_to(7))   # Nómina/Gastos
        btn_cobro.clicked.connect(lambda: self._m._nav_to(3))   # CxC
        btn_pago.clicked.connect(lambda:  self._m._nav_to(4))   # CxP
        btn_asiento.clicked.connect(lambda: self._m._nav_to(6)) # Asientos
        lay.addWidget(grp_acc)

        # Actividad reciente
        grp_act = QGroupBox("Actividad reciente (últimos 20 movimientos)")
        act_lay = QVBoxLayout(grp_act)
        self._tbl_actividad = _FinTable(
            ["Fecha", "Tipo", "Concepto", "Módulo", "Monto", "Usuario"])
        self._tbl_actividad.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        act_lay.addWidget(self._tbl_actividad)
        lay.addWidget(grp_act)

        lay.addStretch()

    def recargar(self):
        m = self._m
        # KPI caja
        try:
            if m._ts and hasattr(m._ts, "balance_general"):
                bal = m._ts.balance_general()
                self._kpi_caja.set_value(f"${float(bal):,.2f}", Colors.SUCCESS_BASE)
            elif m._dash_svc:
                data = m._dash_svc.get_quick_kpis()
                self._kpi_caja.set_value(f"${data.get('saldo_tesoreria',0):,.2f}", Colors.SUCCESS_BASE)
                self._kpi_cxc.set_value(f"${data.get('cxc_pendiente',0):,.2f}", Colors.WARNING_BASE)
                self._kpi_cxp.set_value(f"${data.get('cxp_pendiente',0):,.2f}", Colors.DANGER_BASE)
                self._kpi_flujo.set_value(f"${data.get('flujo_mes',0):,.2f}", Colors.PRIMARY_BASE)
        except Exception as e:
            logger.warning("_SeccionResumen KPI caja: %s", e)

        # CxC y CxP separados si hay servicios específicos
        try:
            if m._ts:
                kpis = m._ts.kpis_financieros()
                self._kpi_cxc.set_value(f"${float(kpis.get('cxc_pendiente',0) or 0):,.2f}", Colors.WARNING_BASE)
                self._kpi_cxp.set_value(f"${float(kpis.get('cxp_pendiente',0) or 0):,.2f}", Colors.DANGER_BASE)
        except Exception as e:
            logger.warning("_SeccionResumen KPI CxC/CxP: %s", e)

        # Actividad reciente
        try:
            rows = []
            if m._tm_svc and hasattr(m._tm_svc, "get_movimientos"):
                rows = m._tm_svc.get_movimientos(limit=20)
            elif m._erp and hasattr(m._erp, "get_ledger"):
                rows = m._erp.get_ledger(sucursal_id=m.sucursal_id)[:20]
            self._tbl_actividad.setRowCount(len(rows))
            for ri, r in enumerate(rows):
                vals = [
                    str(r.get("fecha") or r.get("timestamp", ""))[:10],
                    str(r.get("tipo") or r.get("evento", "")),
                    str(r.get("concepto") or r.get("descripcion", "")),
                    str(r.get("modulo") or r.get("modulo_origen", "")),
                    f"${float(r.get('monto', 0)):,.2f}",
                    str(r.get("usuario", "")),
                ]
                for ci, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self._tbl_actividad.setItem(ri, ci, it)
        except Exception as e:
            logger.warning("_SeccionResumen actividad: %s", e)


class _SeccionCajayConciliacion(QWidget):
    def __init__(self, modulo, parent=None):
        super().__init__(parent)
        self._m = modulo
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        lay.addWidget(_FinSectionHeader(
            "Caja y Conciliación",
            "Historial de cortes y diferencias detectadas. No duplica módulo de Caja.",
            btn_callback=self.recargar
        ))

        # KPIs
        self._kpi_cortes = _FinKpiCard("Cortes recientes", "—")
        self._kpi_dif    = _FinKpiCard("Diferencias detectadas", "—", Colors.WARNING_BASE)
        self._kpi_movs   = _FinKpiCard("Movimientos del período", "—", Colors.PRIMARY_BASE)
        lay.addWidget(_kpi_row([self._kpi_cortes, self._kpi_dif, self._kpi_movs]))

        # Tabla de cortes de caja
        grp = QGroupBox("Cortes de caja")
        g_lay = QVBoxLayout(grp)

        filtros = QHBoxLayout()
        self._txt_buscar = QLineEdit()
        self._txt_buscar.setPlaceholderText("Buscar por cajero o fecha...")
        self._txt_buscar.textChanged.connect(self._filtrar)
        filtros.addWidget(self._txt_buscar)

        btn_exp = QPushButton("📤 Exportar")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.setCursor(Qt.PointingHandCursor)
        btn_exp.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        filtros.addWidget(btn_exp)
        filtros.addStretch()
        g_lay.addLayout(filtros)

        self._tbl = _FinTable(
            ["Fecha", "Caja", "Cajero", "Total declarado", "Total esperado", "Diferencia", "Estado", "Acciones"]
        )
        self._tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        g_lay.addWidget(self._tbl)
        lay.addWidget(grp)
        lay.addStretch()

    def _filtrar(self):
        txt = self._txt_buscar.text().lower()
        for i in range(self._tbl.rowCount()):
            cajero = (self._tbl.item(i, 2) or QTableWidgetItem()).text().lower()
            fecha  = (self._tbl.item(i, 0) or QTableWidgetItem()).text().lower()
            self._tbl.setRowHidden(i, bool(txt) and txt not in cajero and txt not in fecha)

    def recargar(self):
        m = self._m
        try:
            rows = []
            if m._recon_svc and hasattr(m._recon_svc, "get_conciliaciones"):
                rows = m._recon_svc.get_conciliaciones(limit=100)
            elif m._erp and hasattr(m._erp, "get_conciliaciones"):
                rows = m._erp.get_conciliaciones(sucursal_id=m.sucursal_id)

            cortes_ok = 0
            difs = 0
            self._tbl.setRowCount(len(rows))
            for ri, r in enumerate(rows):
                dif_val = float(r.get("diferencia", 0) or 0)
                if dif_val != 0:
                    difs += 1
                else:
                    cortes_ok += 1
                vals = [
                    str(r.get("fecha") or r.get("periodo", ""))[:10],
                    str(r.get("caja") or r.get("cuenta_financiera_id", "")),
                    str(r.get("cajero") or r.get("creado_por", "")),
                    f"${float(r.get('saldo_real', 0) or 0):,.2f}",
                    f"${float(r.get('saldo_sistema', 0) or 0):,.2f}",
                    f"${dif_val:+,.2f}",
                    str(r.get("estado", "")),
                ]
                for ci, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self._tbl.setItem(ri, ci, it)
                # Badge en columna estado
                badge = _FinStatusBadge(r.get("estado", ""))
                self._tbl.setCellWidget(ri, 6, badge)
                # Botón ver
                btn_ver = _compact_btn("Ver", "outline")
                self._tbl.setCellWidget(ri, 7, btn_ver)

            self._kpi_cortes.set_value(str(cortes_ok + difs))
            self._kpi_dif.set_value(str(difs), Colors.WARNING_BASE if difs else Colors.SUCCESS_BASE)
            self._kpi_movs.set_value(str(len(rows)))
        except Exception as e:
            logger.warning("_SeccionCajayConciliacion.recargar: %s", e)


class _SeccionCapital(QWidget):
    def __init__(self, modulo, parent=None):
        super().__init__(parent)
        self._m = modulo
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        lay.addWidget(_FinSectionHeader(
            "Capital y Patrimonio",
            "Aportaciones, retiros y capital neto de socios",
            btn_callback=self.recargar
        ))

        has_svc = self._m._capital_svc is not None

        self._kpi_actual      = _FinKpiCard("Capital actual", "$—")
        self._kpi_aportaciones= _FinKpiCard("Aportaciones", "$—", Colors.SUCCESS_BASE)
        self._kpi_retiros     = _FinKpiCard("Retiros", "$—", Colors.DANGER_BASE)
        self._kpi_neto        = _FinKpiCard("Capital neto", "$—", Colors.PRIMARY_BASE)
        lay.addWidget(_kpi_row([self._kpi_actual, self._kpi_aportaciones,
                                self._kpi_retiros, self._kpi_neto]))

        if not has_svc:
            lay.addWidget(_FinEmptyState(
                "🏦",
                "Capital y patrimonio — próximamente",
                "El servicio de capital no está disponible en esta instalación. "
                "Los datos se mostrarán automáticamente cuando se active."
            ))

        # Bloque de inyección/retiro (siempre visible, usa treasury_service)
        grp_cap = QGroupBox("Inyectar / Retirar Capital (Tesorería)")
        c_lay = QHBoxLayout(grp_cap)

        self._spin_capital = QDoubleSpinBox()
        self._spin_capital.setRange(0, 99999999)
        self._spin_capital.setPrefix("$ ")
        self._spin_capital.setDecimals(2)
        self._spin_capital.setMinimumWidth(160)

        self._txt_desc = QLineEdit()
        self._txt_desc.setPlaceholderText("Descripción (ej: Capital socio A)")

        self._btn_inyectar = QPushButton("➕ Inyectar Capital")
        self._btn_inyectar.setObjectName("successBtn")
        self._btn_inyectar.setCursor(Qt.PointingHandCursor)
        self._btn_inyectar.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self._btn_inyectar.clicked.connect(self._on_inyectar)

        self._btn_retirar = QPushButton("➖ Retirar Capital")
        self._btn_retirar.setObjectName("dangerBtn")
        self._btn_retirar.setCursor(Qt.PointingHandCursor)
        self._btn_retirar.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self._btn_retirar.clicked.connect(self._on_retirar)

        if not has_svc and not self._m._ts:
            tip = "Disponible cuando se conecte el servicio de capital"
            for btn in (self._btn_inyectar, self._btn_retirar):
                btn.setEnabled(False)
                btn.setToolTip(tip)

        c_lay.addWidget(QLabel("Monto:"))
        c_lay.addWidget(self._spin_capital)
        c_lay.addWidget(self._txt_desc, 1)
        c_lay.addWidget(self._btn_inyectar)
        c_lay.addWidget(self._btn_retirar)
        lay.addWidget(grp_cap)

        # Tabla de movimientos de capital
        grp_tbl = QGroupBox("Movimientos de capital")
        t_lay = QVBoxLayout(grp_tbl)
        self._tbl = _FinTable(
            ["Fecha", "Tipo", "Socio", "Concepto", "Método", "Monto", "Referencia", "Estado"])
        self._tbl.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        t_lay.addWidget(self._tbl)
        lay.addWidget(grp_tbl)

        # Desglose egresos (del servicio de tesorería)
        grp_eg = QGroupBox("Desglose de egresos del mes")
        e_lay = QVBoxLayout(grp_eg)
        self._tbl_egresos = QTableWidget(0, 2)
        self._tbl_egresos.setHorizontalHeaderLabels(["Concepto", "Monto ($)"])
        self._tbl_egresos.horizontalHeader().setStretchLastSection(True)
        self._tbl_egresos.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._tbl_egresos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_egresos.verticalHeader().setVisible(False)
        e_lay.addWidget(self._tbl_egresos)
        lay.addWidget(grp_eg)

        lay.addStretch()

    def _on_inyectar(self):
        monto = self._spin_capital.value()
        desc  = self._txt_desc.text().strip()
        if monto <= 0:
            QMessageBox.warning(self, "Aviso", "Ingresa un monto mayor a $0.")
            return
        if not desc:
            QMessageBox.warning(self, "Aviso", "Ingresa una descripción.")
            return
        if not self._m._ts:
            QMessageBox.warning(self, "Error", "TreasuryService no disponible.")
            return
        try:
            self._m._ts.inyectar_capital(monto, desc, self._m.usuario_actual)
            Toast.success(self, "Capital inyectado", f"${monto:,.2f}")
            self._spin_capital.setValue(0)
            self._txt_desc.clear()
            self.recargar()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_retirar(self):
        monto = self._spin_capital.value()
        desc  = self._txt_desc.text().strip()
        if monto <= 0:
            QMessageBox.warning(self, "Aviso", "Ingresa un monto mayor a $0.")
            return
        if not desc:
            QMessageBox.warning(self, "Aviso", "Ingresa una descripción.")
            return
        if not self._m._ts:
            QMessageBox.warning(self, "Error", "TreasuryService no disponible.")
            return
        try:
            self._m._ts.retirar_capital(monto, desc, self._m.usuario_actual)
            Toast.success(self, "Capital retirado", f"${monto:,.2f}")
            self._spin_capital.setValue(0)
            self._txt_desc.clear()
            self.recargar()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def recargar(self):
        m = self._m
        try:
            if m._ts:
                kpis = m._ts.kpis_financieros()
                self._kpi_actual.set_value(f"${float(kpis.get('capital_invertido',0)):,.2f}")
                self._kpi_neto.set_value(f"${float(kpis.get('capital_disponible',0)):,.2f}", Colors.PRIMARY_BASE)
                # Egresos
                eg = kpis.get("egresos", {})
                items = [
                    ("Compras de inventario",           eg.get("compras_inventario", 0)),
                    ("Gastos fijos",                    eg.get("gastos_fijos", 0)),
                    ("Gastos operativos",                eg.get("gastos_operativos", 0)),
                    ("Nómina / RRHH",                   eg.get("nomina_rrhh", 0)),
                    ("Otros gastos",                    eg.get("gastos_otros", 0)),
                    ("Merma",                           eg.get("merma", 0)),
                    ("Depreciación activos",             eg.get("depreciacion_activos", 0)),
                    ("Comisión MercadoPago",             eg.get("mercadopago", 0)),
                    ("Comisión Delivery",                eg.get("delivery", 0)),
                    ("─────────────────────",           0),
                    ("TOTAL EGRESOS",                   eg.get("total_egresos", 0)),
                ]
                self._tbl_egresos.setRowCount(len(items))
                for i, (concepto, monto) in enumerate(items):
                    self._tbl_egresos.setItem(i, 0, QTableWidgetItem(concepto))
                    m_item = QTableWidgetItem(f"${monto:,.2f}" if monto else "")
                    m_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self._tbl_egresos.setItem(i, 1, m_item)
        except Exception as e:
            logger.warning("_SeccionCapital.recargar: %s", e)


class _SeccionCuentasPorCobrar(QWidget):
    def __init__(self, modulo, parent=None):
        super().__init__(parent)
        self._m = modulo
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        lay.addWidget(_FinSectionHeader(
            "Cuentas por Cobrar",
            "Facturas y deudas pendientes de cobro a clientes",
            btn_callback=self.recargar
        ))

        self._kpi_total   = _FinKpiCard("Total por cobrar", "—", Colors.PRIMARY_BASE)
        self._kpi_vencido = _FinKpiCard("Vencido", "—", Colors.DANGER_BASE)
        self._kpi_porvenc = _FinKpiCard("Por vencer", "—", Colors.WARNING_BASE)
        self._kpi_cobrado = _FinKpiCard("Cobrado este mes", "—", Colors.SUCCESS_BASE)
        lay.addWidget(_kpi_row([self._kpi_total, self._kpi_vencido,
                                self._kpi_porvenc, self._kpi_cobrado]))

        # Acciones y filtros
        acc = QHBoxLayout()
        btn_nuevo_cli = QPushButton("👤 Nuevo cliente")
        btn_nuevo_cli.setObjectName("secondaryBtn")
        btn_nuevo_cli.setCursor(Qt.PointingHandCursor)
        btn_nuevo_cli.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        btn_nuevo_cli.clicked.connect(self._dialogo_nuevo_cliente)

        btn_nueva_cxc = QPushButton("➕ Nueva CxC")
        btn_nueva_cxc.setObjectName("successBtn")
        btn_nueva_cxc.setCursor(Qt.PointingHandCursor)
        btn_nueva_cxc.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        btn_nueva_cxc.clicked.connect(self._dialogo_nueva_cxc)

        btn_cobro_global = QPushButton("💰 Cobro global")
        btn_cobro_global.setObjectName("primaryBtn")
        btn_cobro_global.setCursor(Qt.PointingHandCursor)
        btn_cobro_global.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        btn_cobro_global.clicked.connect(self._dialogo_cobro_global)

        acc.addWidget(btn_nuevo_cli)
        acc.addWidget(btn_nueva_cxc)
        acc.addWidget(btn_cobro_global)
        acc.addStretch()
        lay.addLayout(acc)

        filtros = QHBoxLayout()
        self._cmb_estado = QComboBox()
        self._cmb_estado.addItems(["Todos", "pendiente", "parcial", "pagado", "vencido"])
        self._cmb_estado.currentIndexChanged.connect(self._filtrar)

        self._txt_buscar = QLineEdit()
        self._txt_buscar.setPlaceholderText("Buscar por cliente...")
        self._txt_buscar.textChanged.connect(self._filtrar)

        filtros.addWidget(QLabel("Estado:"))
        filtros.addWidget(self._cmb_estado)
        filtros.addWidget(self._txt_buscar, 1)
        lay.addLayout(filtros)

        self._tbl = _FinTable(
            ["ID", "Folio", "Cliente", "Monto", "Saldo", "Vencimiento", "Estado", "Acciones"])
        self._tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        lay.addWidget(self._tbl)
        lay.addStretch()

    def _filtrar(self):
        estado_fil = self._cmb_estado.currentText()
        txt = self._txt_buscar.text().lower()
        for i in range(self._tbl.rowCount()):
            cli   = (self._tbl.item(i, 2) or QTableWidgetItem()).text().lower()
            est   = (self._tbl.item(i, 6) or QTableWidgetItem()).text().lower()
            show  = True
            if txt and txt not in cli:
                show = False
            if estado_fil != "Todos" and est != estado_fil.lower():
                show = False
            self._tbl.setRowHidden(i, not show)

    def _dialogo_nuevo_cliente(self):
        m = self._m
        if not hasattr(m.container, "db"):
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
        nombre_val = nombre.text().strip()
        if not nombre_val:
            QMessageBox.warning(self, "Aviso", "El nombre del cliente es obligatorio.")
            return
        try:
            if not getattr(m, "_dash_svc", None):
                raise RuntimeError("FinancialDashboardService no disponible.")
            m._dash_svc.crear_cliente(
                nombre=nombre_val,
                telefono=tel.text().strip(),
                email=email.text().strip(),
                sucursal_id=m.sucursal_id or 1,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No fue posible crear el cliente:\n{exc}")
            return
        self.recargar()

    def _dialogo_nueva_cxc(self):
        m = self._m
        if not m._fs and not hasattr(m.container, "db"):
            QMessageBox.warning(self, "Error", "Servicios financieros no disponibles.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Nueva Cuenta por Cobrar")
        lay = QFormLayout(dlg)
        clientes = m._dash_svc.listar_clientes(sucursal_id=m.sucursal_id) if m._dash_svc else []
        txt_cliente, sel_cli = m._build_autocomplete_selector(
            [{"id": c.get("id"), "label": c.get("nombre", "—")} for c in clientes],
            placeholder="Buscar cliente por nombre…"
        )
        txt = QLineEdit(); txt.setPlaceholderText("Concepto")
        monto = QDoubleSpinBox(); monto.setRange(0.01, 999999999); monto.setPrefix("$ "); monto.setDecimals(2)
        due = QDateEdit(); due.setCalendarPopup(True); due.setDate(QDate.currentDate().addDays(15))
        lay.addRow("Cliente:", txt_cliente); lay.addRow("Concepto:", txt)
        lay.addRow("Monto:", monto); lay.addRow("Vence:", due)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        lay.addRow(btns)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        if dlg.exec_() != QDialog.Accepted:
            return
        cliente_id = sel_cli.get("id")
        if not cliente_id:
            QMessageBox.warning(self, "Validación", "Seleccione un cliente válido.")
            return
        # Validar límite de crédito
        try:
            if not m._dash_svc:
                raise RuntimeError("FinancialDashboardService no disponible.")
            info = m._dash_svc.get_credit_info(cliente_id)
            saldo_actual = info["saldo_actual"]
            limite = info["limite_credito"]
            monto_nuevo = float(monto.value())
            if limite <= 0:
                QMessageBox.warning(self, "Sin límite de crédito",
                    f"El cliente no tiene límite de crédito configurado.")
                return
            if saldo_actual + monto_nuevo > limite + 0.01:
                disponible = max(0.0, limite - saldo_actual)
                QMessageBox.warning(self, "Límite excedido",
                    f"Saldo actual: ${saldo_actual:,.2f}\n"
                    f"Límite: ${limite:,.2f}\nDisponible: ${disponible:,.2f}\n\n"
                    f"La nueva CxC (${monto_nuevo:,.2f}) excede el límite.")
                return
        except Exception as exc:
            logger.warning("validación límite crédito: %s", exc)
            QMessageBox.warning(self, "Validación", "No fue posible validar el límite de crédito.")
            return
        if not m._fs or not hasattr(m._fs, "crear_cxc"):
            QMessageBox.critical(self, "Error", "FinanceService no disponible.")
            return
        try:
            m._fs.crear_cxc(
                cliente_id=cliente_id,
                concepto=txt.text().strip() or "Cuenta por cobrar",
                amount=float(monto.value()),
                due_date=due.date().toString("yyyy-MM-dd"),
                usuario=m.usuario_actual or "Sistema",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        self.recargar()

    def _dialogo_cobro_global(self):
        m = self._m
        if not m._ts:
            return
        clientes = m._dash_svc.listar_clientes(sucursal_id=m.sucursal_id) if m._dash_svc else []
        if not clientes:
            QMessageBox.information(self, "Sin clientes", "No hay clientes activos.")
            return
        nombres = [f"{c.get('id')} - {c.get('nombre','')}" for c in clientes]
        seleccionado, ok = QInputDialog.getItem(self, "Cliente", "Selecciona cliente:", nombres, 0, False)
        if not ok:
            return
        tercero_id = int(str(seleccionado).split(" - ", 1)[0])
        monto, ok2 = QInputDialog.getDouble(self, "Cobro global CxC", "Monto total:", 0.0, 0.0, 999999999.0, 2)
        if not ok2 or monto <= 0:
            return
        metodo, ok3 = QInputDialog.getItem(self, "Método", "Forma de cobro:", ["Efectivo", "Transferencia", "Tarjeta"], 0, False)
        if not ok3:
            return
        m._ts.aplicar_pago_global("cliente", monto, metodo=metodo, usuario=m.usuario_actual, tercero_id=tercero_id)
        self.recargar()

    def recargar(self):
        m = self._m
        if not m._ts:
            self._tbl.setRowCount(0)
            return
        try:
            deudas = m._ts.get_cuentas_por_cobrar(m.sucursal_id)
            if not deudas and m.sucursal_id:
                deudas = m._ts.get_cuentas_por_cobrar(0)
            self._tbl.setRowCount(len(deudas))
            total = sum(float(d.get("saldo", 0) or 0) for d in deudas)
            self._kpi_total.set_value(f"${total:,.2f}", Colors.PRIMARY_BASE)
            for row, d in enumerate(deudas):
                vals = [
                    str(d.get("id", "")),
                    str(d.get("folio", "")),
                    str(d.get("cliente") or "Público"),
                    f"${float(d.get('monto', d.get('saldo', 0)) or 0):,.2f}",
                    f"${float(d.get('saldo', 0) or 0):,.2f}",
                    str(d.get("vencimiento") or d.get("fecha_vencimiento", ""))[:10],
                    str(d.get("estado", "pendiente")),
                ]
                for ci, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self._tbl.setItem(row, ci, it)
                badge = _FinStatusBadge(d.get("estado", "pendiente"))
                self._tbl.setCellWidget(row, 6, badge)
                btn_cobrar = _compact_btn("💰 Cobrar", "success")
                btn_cobrar.clicked.connect(lambda _, dd=d: self._cobrar(dd))
                self._tbl.setCellWidget(row, 7, btn_cobrar)
        except Exception as e:
            logger.error("_SeccionCuentasPorCobrar.recargar: %s", e)

    def _cobrar(self, deuda):
        m = self._m
        if not m._ts:
            return
        dlg = DialogoAbono(deuda, tipo="cobrar", treasury_service=m._ts, usuario=m.usuario_actual, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.recargar()


class _SeccionCuentasPorPagar(QWidget):
    def __init__(self, modulo, parent=None):
        super().__init__(parent)
        self._m = modulo
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        lay.addWidget(_FinSectionHeader(
            "Cuentas por Pagar",
            "Facturas y deudas pendientes con proveedores",
            btn_callback=self.recargar
        ))

        self._kpi_total   = _FinKpiCard("Total por pagar", "—", Colors.DANGER_BASE)
        self._kpi_vencido = _FinKpiCard("Vencido", "—", Colors.DANGER_BASE)
        self._kpi_porvenc = _FinKpiCard("Por vencer", "—", Colors.WARNING_BASE)
        self._kpi_pagado  = _FinKpiCard("Pagado este mes", "—", Colors.SUCCESS_BASE)
        lay.addWidget(_kpi_row([self._kpi_total, self._kpi_vencido,
                                self._kpi_porvenc, self._kpi_pagado]))

        acc = QHBoxLayout()
        btn_nueva_cxp = QPushButton("➕ Nueva CxP")
        btn_nueva_cxp.setObjectName("primaryBtn")
        btn_nueva_cxp.setCursor(Qt.PointingHandCursor)
        btn_nueva_cxp.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        btn_nueva_cxp.clicked.connect(self._dialogo_nueva_cxp)

        btn_pago_global = QPushButton("💳 Pago global")
        btn_pago_global.setObjectName("secondaryBtn")
        btn_pago_global.setCursor(Qt.PointingHandCursor)
        btn_pago_global.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        btn_pago_global.clicked.connect(self._dialogo_pago_global)

        acc.addWidget(btn_nueva_cxp)
        acc.addWidget(btn_pago_global)
        acc.addStretch()
        lay.addLayout(acc)

        self._txt_filtro = QLineEdit()
        self._txt_filtro.setPlaceholderText("Buscar por nombre de proveedor...")
        self._txt_filtro.textChanged.connect(self._filtrar)
        lay.addWidget(self._txt_filtro)

        self._tbl = _FinTable(
            ["ID", "Fecha", "Folio", "Proveedor", "Concepto", "Saldo", "Estado", "Acciones"])
        self._tbl.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self._tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        lay.addWidget(self._tbl)
        lay.addStretch()

    def _filtrar(self):
        txt = self._txt_filtro.text().lower()
        for i in range(self._tbl.rowCount()):
            nom = (self._tbl.item(i, 3) or QTableWidgetItem()).text().lower()
            self._tbl.setRowHidden(i, bool(txt) and txt not in nom)

    def _dialogo_nueva_cxp(self):
        m = self._m
        if not m._fs and not hasattr(m.container, "db"):
            QMessageBox.warning(self, "Error", "Servicios financieros no disponibles.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Nueva Cuenta por Pagar")
        lay = QFormLayout(dlg)
        proveedores = m._tps.get_all_proveedores(activo=True, limit=500) if m._tps else []
        txt_prov, sel_prov = m._build_autocomplete_selector(
            [{"id": p.get("id"), "label": p.get("nombre", "—")} for p in proveedores],
            placeholder="Buscar proveedor por nombre…"
        )
        txt = QLineEdit(); txt.setPlaceholderText("Concepto")
        monto = QDoubleSpinBox(); monto.setRange(0.01, 999999999); monto.setPrefix("$ "); monto.setDecimals(2)
        due = QDateEdit(); due.setCalendarPopup(True); due.setDate(QDate.currentDate().addDays(30))
        lay.addRow("Proveedor:", txt_prov); lay.addRow("Concepto:", txt)
        lay.addRow("Monto:", monto); lay.addRow("Vence:", due)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        lay.addRow(btns)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        if dlg.exec_() != QDialog.Accepted:
            return
        supplier_id = sel_prov.get("id")
        if not supplier_id:
            QMessageBox.warning(self, "Validación", "Seleccione un proveedor válido.")
            return
        if not m._fs or not hasattr(m._fs, "crear_cxp"):
            QMessageBox.critical(self, "Error", "FinanceService no disponible.")
            return
        try:
            m._fs.crear_cxp(
                supplier_id=supplier_id,
                concepto=txt.text().strip() or "Cuenta por pagar",
                amount=float(monto.value()),
                due_date=due.date().toString("yyyy-MM-dd"),
                usuario=m.usuario_actual or "Sistema",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        self.recargar()

    def _dialogo_pago_global(self):
        m = self._m
        if not m._ts:
            return
        proveedores = m._tps.get_all_proveedores(activo=True, limit=500) if m._tps else []
        if not proveedores:
            QMessageBox.information(self, "Sin proveedores", "No hay proveedores activos.")
            return
        nombres = [f"{p.get('id')} - {p.get('nombre','')}" for p in proveedores]
        sel, ok = QInputDialog.getItem(self, "Proveedor", "Selecciona proveedor:", nombres, 0, False)
        if not ok:
            return
        tercero_id = int(str(sel).split(" - ", 1)[0])
        monto, ok2 = QInputDialog.getDouble(self, "Pago global CxP", "Monto total:", 0.0, 0.0, 999999999.0, 2)
        if not ok2 or monto <= 0:
            return
        metodo, ok3 = QInputDialog.getItem(self, "Método", "Forma de pago:", ["Transferencia", "Efectivo", "Cheque"], 0, False)
        if not ok3:
            return
        m._ts.aplicar_pago_global("proveedor", monto, metodo=metodo, usuario=m.usuario_actual, tercero_id=tercero_id)
        self.recargar()

    def recargar(self):
        m = self._m
        if not m._ts:
            self._tbl.setRowCount(0)
            return
        try:
            deudas = m._ts.get_cuentas_por_pagar(m.sucursal_id)
            if not deudas and m.sucursal_id:
                deudas = m._ts.get_cuentas_por_pagar(0)
            self._tbl.setRowCount(len(deudas))
            total = sum(float(d.get("saldo", 0) or 0) for d in deudas)
            self._kpi_total.set_value(f"${total:,.2f}", Colors.DANGER_BASE)
            for row, d in enumerate(deudas):
                vals = [
                    str(d.get("id", "")),
                    str(d.get("fecha", ""))[:10],
                    str(d.get("folio", "")),
                    str(d.get("proveedor") or "Varios"),
                    str(d.get("concepto", "")),
                    f"${float(d.get('saldo', 0) or 0):,.2f}",
                    str(d.get("estado", "pendiente")),
                ]
                for ci, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self._tbl.setItem(row, ci, it)
                badge = _FinStatusBadge(d.get("estado", "pendiente"))
                self._tbl.setCellWidget(row, 6, badge)
                btn_pagar = _compact_btn("💸 Abonar", "primary")
                btn_pagar.clicked.connect(lambda _, dd=d: self._abonar(dd))
                self._tbl.setCellWidget(row, 7, btn_pagar)
        except Exception as e:
            logger.error("_SeccionCuentasPorPagar.recargar: %s", e)

    def _abonar(self, deuda):
        m = self._m
        if not m._ts:
            return
        dlg = DialogoAbono(deuda, tipo="pagar", treasury_service=m._ts, usuario=m.usuario_actual, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.recargar()


class _SeccionMovimientos(QWidget):
    def __init__(self, modulo, parent=None):
        super().__init__(parent)
        self._m = modulo
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        lay.addWidget(_FinSectionHeader(
            "Movimientos",
            "Registro de entradas y salidas de tesorería",
            btn_callback=self.recargar
        ))

        # Filtros
        filtros = QHBoxLayout()
        self._cmb_tipo = QComboBox()
        self._cmb_tipo.addItems(["Todos", "ingreso", "egreso"])
        self._cmb_tipo.currentIndexChanged.connect(self._filtrar)

        self._txt_buscar = QLineEdit()
        self._txt_buscar.setPlaceholderText("Buscar por concepto o referencia...")
        self._txt_buscar.textChanged.connect(self._filtrar)

        filtros.addWidget(QLabel("Tipo:"))
        filtros.addWidget(self._cmb_tipo)
        filtros.addWidget(self._txt_buscar, 1)
        lay.addLayout(filtros)

        self._tbl = _FinTable(
            ["Fecha", "Tipo", "Categoría", "Concepto", "Referencia", "Entrada", "Salida", "Saldo", "Usuario"])
        self._tbl.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        lay.addWidget(self._tbl)
        lay.addStretch()

    def _filtrar(self):
        tipo_fil = self._cmb_tipo.currentText()
        txt = self._txt_buscar.text().lower()
        for i in range(self._tbl.rowCount()):
            tipo  = (self._tbl.item(i, 1) or QTableWidgetItem()).text().lower()
            conc  = (self._tbl.item(i, 3) or QTableWidgetItem()).text().lower()
            ref   = (self._tbl.item(i, 4) or QTableWidgetItem()).text().lower()
            show  = True
            if tipo_fil != "Todos" and tipo != tipo_fil.lower():
                show = False
            if txt and txt not in conc and txt not in ref:
                show = False
            self._tbl.setRowHidden(i, not show)

    def recargar(self):
        m = self._m
        try:
            rows = []
            if m._tm_svc and hasattr(m._tm_svc, "get_movimientos"):
                rows = m._tm_svc.get_movimientos(sucursal_id=m.sucursal_id, limit=200)
            elif m._erp and hasattr(m._erp, "get_ledger"):
                rows = m._erp.get_ledger(sucursal_id=m.sucursal_id)[:200]
            elif m._ts and hasattr(m._ts, "kpis_financieros"):
                # fallback: sin movimientos detallados disponibles
                rows = []

            self._tbl.setRowCount(len(rows))
            for ri, r in enumerate(rows):
                tipo = str(r.get("tipo") or r.get("evento", ""))
                monto_val = float(r.get("monto", 0) or 0)
                entrada = f"${monto_val:,.2f}" if "ingreso" in tipo.lower() or "entrada" in tipo.lower() else ""
                salida  = f"${monto_val:,.2f}" if "egreso" in tipo.lower() or "salida" in tipo.lower() else ""
                if not entrada and not salida:
                    entrada = f"${monto_val:,.2f}"

                vals = [
                    str(r.get("fecha") or r.get("timestamp", ""))[:10],
                    tipo,
                    str(r.get("categoria") or r.get("modulo_origen", "")),
                    str(r.get("concepto") or r.get("descripcion", "")),
                    str(r.get("referencia") or r.get("ref", "")),
                    entrada,
                    salida,
                    f"${float(r.get('saldo', 0) or 0):,.2f}",
                    str(r.get("usuario", "")),
                ]
                for ci, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    if ci in (5, 6) and v:
                        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self._tbl.setItem(ri, ci, it)
        except Exception as e:
            logger.warning("_SeccionMovimientos.recargar: %s", e)


class _SeccionAsientosContables(QWidget):
    def __init__(self, modulo, parent=None):
        super().__init__(parent)
        self._m = modulo
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        hdr = _FinSectionHeader(
            "Asientos Contables",
            "Registro de doble entrada inmutable. No se edita ni se borra.",
            btn_callback=self.recargar
        )
        lay.addWidget(hdr)

        acc = QHBoxLayout()
        btn_nuevo = QPushButton("➕ Registrar asiento manual")
        btn_nuevo.setObjectName("primaryBtn")
        btn_nuevo.setCursor(Qt.PointingHandCursor)
        btn_nuevo.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        btn_nuevo.clicked.connect(self._dialogo_nuevo_asiento)

        btn_export = QPushButton("📤 Exportar")
        btn_export.setObjectName("secondaryBtn")
        btn_export.setCursor(Qt.PointingHandCursor)
        btn_export.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

        acc.addWidget(btn_nuevo)
        acc.addWidget(btn_export)
        acc.addStretch()
        lay.addLayout(acc)

        nota = QLabel("Registro inmutable de todos los eventos financieros.")
        nota.setObjectName("caption")
        lay.addWidget(nota)

        self._tbl = _FinTable(
            ["Fecha", "Evento", "Módulo", "Cuenta debe", "Cuenta haber", "Monto", "Referencia", "Usuario"])
        self._tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        lay.addWidget(self._tbl)
        lay.addStretch()

    def _dialogo_nuevo_asiento(self):
        m = self._m
        if not m._je_svc and not m._fs:
            QMessageBox.warning(self, "Error", "Servicio de asientos no disponible.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Nuevo Asiento Contable")
        lay = QFormLayout(dlg)
        txt_evento  = QLineEdit(); txt_evento.setPlaceholderText("Descripción del evento")
        txt_debe    = QLineEdit(); txt_debe.setPlaceholderText("Cuenta debe (ej: 1100)")
        txt_haber   = QLineEdit(); txt_haber.setPlaceholderText("Cuenta haber (ej: 2100)")
        spin_monto  = QDoubleSpinBox(); spin_monto.setRange(0.01, 999999999); spin_monto.setPrefix("$"); spin_monto.setDecimals(2)
        txt_ref     = QLineEdit(); txt_ref.setPlaceholderText("Referencia opcional")
        lay.addRow("Evento:", txt_evento)
        lay.addRow("Cuenta debe:", txt_debe)
        lay.addRow("Cuenta haber:", txt_haber)
        lay.addRow("Monto:", spin_monto)
        lay.addRow("Referencia:", txt_ref)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        lay.addRow(btns)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        if dlg.exec_() != QDialog.Accepted:
            return
        try:
            if m._je_svc and hasattr(m._je_svc, "registrar"):
                m._je_svc.registrar(
                    evento=txt_evento.text().strip(),
                    cuenta_debe=txt_debe.text().strip(),
                    cuenta_haber=txt_haber.text().strip(),
                    monto=float(spin_monto.value()),
                    referencia=txt_ref.text().strip(),
                    usuario=m.usuario_actual or "Sistema",
                )
            elif m._fs and hasattr(m._fs, "registrar_asiento"):
                m._fs.registrar_asiento(
                    evento=txt_evento.text().strip(),
                    cuenta_debe=txt_debe.text().strip(),
                    cuenta_haber=txt_haber.text().strip(),
                    monto=float(spin_monto.value()),
                    referencia=txt_ref.text().strip(),
                )
            self.recargar()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def recargar(self):
        m = self._m
        try:
            rows = []
            if m._je_svc and hasattr(m._je_svc, "get_asientos"):
                rows = m._je_svc.get_asientos(sucursal_id=m.sucursal_id, limit=200)
            elif m._erp and hasattr(m._erp, "get_ledger"):
                rows = m._erp.get_ledger(sucursal_id=m.sucursal_id)[:200]

            self._tbl.setRowCount(len(rows))
            for ri, r in enumerate(rows):
                vals = [
                    str(r.get("fecha") or r.get("timestamp", ""))[:10],
                    str(r.get("evento") or r.get("descripcion", "")),
                    str(r.get("modulo") or r.get("modulo_origen", "")),
                    str(r.get("cuenta_debe", "")),
                    str(r.get("cuenta_haber", "")),
                    f"${float(r.get('monto', 0) or 0):,.2f}",
                    str(r.get("referencia", "")),
                    str(r.get("usuario", "")),
                ]
                for ci, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self._tbl.setItem(ri, ci, it)
        except Exception as e:
            logger.warning("_SeccionAsientosContables.recargar: %s", e)


class _SeccionNomina(QWidget):
    def __init__(self, modulo, parent=None):
        super().__init__(parent)
        self._m = modulo
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        lay.addWidget(_FinSectionHeader(
            "Nómina",
            "Pagos de nómina y gastos operativos del período",
            btn_callback=self.recargar
        ))

        self._kpi_total    = _FinKpiCard("Total del período", "—", Colors.PRIMARY_BASE)
        self._kpi_pendiente= _FinKpiCard("Pendiente", "—", Colors.WARNING_BASE)
        self._kpi_pagada   = _FinKpiCard("Pagada", "—", Colors.SUCCESS_BASE)
        lay.addWidget(_kpi_row([self._kpi_total, self._kpi_pendiente, self._kpi_pagada]))

        # Formulario de gasto operativo
        grp_gasto = QGroupBox("Registrar nuevo gasto operativo")
        g_lay = QFormLayout(grp_gasto)

        self.cmb_categoria = QComboBox()
        self.cmb_categoria.addItems([
            "Servicios (Luz, Agua)", "Renta", "Nómina",
            "Mantenimiento", "Papelería", "Impuestos", "Otros"
        ])
        self.txt_concepto = QLineEdit()
        self.txt_concepto.setPlaceholderText("Ej: Pago recibo CFE Diciembre")
        self.spin_monto = QDoubleSpinBox()
        self.spin_monto.setRange(0.1, 999999.0)
        self.spin_monto.setPrefix("$ ")
        self.cmb_metodo = QComboBox()
        self.cmb_metodo.addItems(["Transferencia", "Efectivo (Caja Chica)", "Tarjeta Corporativa"])

        btn_guardar = QPushButton("💾 Guardar gasto")
        btn_guardar.setObjectName("dangerBtn")
        btn_guardar.setCursor(Qt.PointingHandCursor)
        btn_guardar.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        btn_guardar.clicked.connect(self._registrar_gasto)

        g_lay.addRow("Categoría:", self.cmb_categoria)
        g_lay.addRow("Concepto:", self.txt_concepto)
        g_lay.addRow("Monto:", self.spin_monto)
        g_lay.addRow("Método de pago:", self.cmb_metodo)
        g_lay.addRow("", btn_guardar)
        lay.addWidget(grp_gasto)

        # Tabla de nómina
        grp_tbl = QGroupBox("Historial de nómina")
        t_lay = QVBoxLayout(grp_tbl)
        self._tbl = _FinTable(
            ["Período", "Empleado", "Neto", "Método", "Estado", "Fecha pago"])
        self._tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        t_lay.addWidget(self._tbl)
        lay.addWidget(grp_tbl)
        lay.addStretch()

    def _registrar_gasto(self):
        m = self._m
        concepto = self.txt_concepto.text().strip()
        monto    = self.spin_monto.value()
        if not concepto:
            QMessageBox.warning(self, "Aviso", "Debe ingresar el concepto del gasto.")
            return
        if not m._ts:
            QMessageBox.warning(self, "Error", "TreasuryService no disponible.")
            return
        try:
            m._ts.registrar_gasto_opex(
                categoria=self.cmb_categoria.currentText(),
                concepto=concepto,
                monto=monto,
                metodo_pago=self.cmb_metodo.currentText(),
                usuario=m.usuario_actual,
                sucursal_id=m.sucursal_id,
            )
            Toast.success(self, "Gasto registrado", "Asentado en contabilidad.")
            self.txt_concepto.clear()
            self.spin_monto.setValue(0.1)
            self.recargar()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def recargar(self):
        m = self._m
        try:
            rows = []
            if m._ts and hasattr(m._ts, "get_nomina"):
                rows = m._ts.get_nomina(sucursal_id=m.sucursal_id)
            self._tbl.setRowCount(len(rows))
            for ri, r in enumerate(rows):
                vals = [
                    str(r.get("periodo", "")),
                    str(r.get("empleado", "")),
                    f"${float(r.get('neto', 0) or 0):,.2f}",
                    str(r.get("metodo", "")),
                    str(r.get("estado", "")),
                    str(r.get("fecha_pago", ""))[:10],
                ]
                for ci, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self._tbl.setItem(ri, ci, it)
                badge = _FinStatusBadge(r.get("estado", ""))
                self._tbl.setCellWidget(ri, 4, badge)
        except Exception as e:
            logger.warning("_SeccionNomina.recargar: %s", e)


class _SeccionProveedores(QWidget):
    def __init__(self, modulo, parent=None):
        super().__init__(parent)
        self._m = modulo
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        hdr_row = QHBoxLayout()
        hdr_row.addWidget(_FinSectionHeader(
            "Directorio de Proveedores",
            "CRUD de proveedores — categorías, crédito, contacto",
        ))
        btn_nuevo = QPushButton("➕ Nuevo Proveedor")
        btn_nuevo.setObjectName("successBtn")
        btn_nuevo.setCursor(Qt.PointingHandCursor)
        btn_nuevo.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        btn_nuevo.clicked.connect(self._nuevo_proveedor)
        hdr_row.addWidget(btn_nuevo)

        btn_refr = QPushButton("🔄 Actualizar")
        btn_refr.setObjectName("secondaryBtn")
        btn_refr.setCursor(Qt.PointingHandCursor)
        btn_refr.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        btn_refr.clicked.connect(self.recargar)
        hdr_row.addWidget(btn_refr)

        lay.addLayout(hdr_row)

        self._txt_buscar = QLineEdit()
        self._txt_buscar.setPlaceholderText("Buscar por nombre, RFC o contacto...")
        self._txt_buscar.textChanged.connect(self._filtrar)
        lay.addWidget(self._txt_buscar)

        self._tbl = _FinTable(
            ["Nombre", "Teléfono", "Email", "Contacto", "Días crédito", "Saldo", "Acciones"])
        hh = self._tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3, 4, 5):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._tbl.doubleClicked.connect(self._editar_seleccionado)
        self._tbl.itemSelectionChanged.connect(self._on_selected)
        lay.addWidget(self._tbl)

        grp_det = QGroupBox("Detalle de proveedor seleccionado")
        d_lay = QVBoxLayout(grp_det)
        self._lbl_detalle  = QLabel("Selecciona un proveedor para ver sus datos.")
        self._lbl_resumen  = QLabel("Resumen de cuentas pendientes: $0.00")
        self._lbl_resumen.setStyleSheet("font-weight:bold;")
        d_lay.addWidget(self._lbl_detalle)
        d_lay.addWidget(self._lbl_resumen)
        lay.addWidget(grp_det)
        lay.addStretch()

    def _filtrar(self):
        txt = self._txt_buscar.text().lower()
        for i in range(self._tbl.rowCount()):
            nom = (self._tbl.item(i, 0) or QTableWidgetItem()).text().lower()
            tel = (self._tbl.item(i, 1) or QTableWidgetItem()).text().lower()
            con = (self._tbl.item(i, 3) or QTableWidgetItem()).text().lower()
            self._tbl.setRowHidden(i, bool(txt) and txt not in nom and txt not in tel and txt not in con)

    def _on_selected(self):
        row = self._tbl.currentRow()
        if row < 0:
            self._lbl_detalle.setText("Selecciona un proveedor para ver sus datos.")
            self._lbl_resumen.setText("Resumen de cuentas pendientes: $0.00")
            return
        it = self._tbl.item(row, 0)
        pid = it.data(Qt.UserRole) if it else None
        if not pid:
            return
        m = self._m
        try:
            prov = m._tps.get_proveedor(int(pid)) if m._tps else None
            if prov:
                self._lbl_detalle.setText(
                    f"Nombre: {prov.get('nombre','-')} | RFC: {prov.get('rfc','-')} | "
                    f"Tel: {prov.get('telefono','-')} | Email: {prov.get('email','-')}")
            deudas = [d for d in (m._ts.get_cuentas_por_pagar(0) if m._ts else [])
                      if int(d.get("proveedor_id") or 0) == int(pid)]
            saldo = sum(float(d.get("saldo", 0) or 0) for d in deudas)
            if saldo <= 0:
                self._lbl_resumen.setText("Sin cuentas pendientes.")
            else:
                self._lbl_resumen.setText(f"Cuentas pendientes: ${saldo:,.2f} en {len(deudas)} documento(s).")
        except Exception as exc:
            logger.warning("_SeccionProveedores._on_selected: %s", exc)

    def _nuevo_proveedor(self):
        m = self._m
        if not m._tps:
            QMessageBox.warning(self, "Error", "Servicio de proveedores no disponible.")
            return
        dlg = DialogoProveedor(m._tps, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.recargar()

    def _editar_seleccionado(self):
        row = self._tbl.currentRow()
        if row < 0:
            return
        it = self._tbl.item(row, 0)
        pid = it.data(Qt.UserRole) if it else None
        if not pid:
            return
        self._editar_por_id(pid)

    def _editar_por_id(self, pid):
        m = self._m
        if not m._tps:
            return
        dlg = DialogoProveedor(m._tps, pid, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.recargar()

    def _eliminar_proveedor(self, pid, nombre):
        resp = QMessageBox.question(
            self, "Eliminar proveedor",
            f"¿Eliminar a '{nombre}'?\nEsta acción no se puede deshacer.",
            QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes:
            return
        m = self._m
        if not m._tps:
            return
        try:
            m._tps.delete_proveedor(pid, soft=True)
            self.recargar()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def recargar(self):
        m = self._m
        rows = []
        if m._tps:
            try:
                rows = m._tps.get_all_proveedores(activo=True, limit=300)
            except Exception as e:
                logger.warning("_SeccionProveedores.recargar tps: %s", e)

        # Fallback defensivo si el servicio falla pero hay db
        if not rows and hasattr(m.container, "db"):
            try:
                cur = m.container.db.execute(
                    "SELECT id,nombre,telefono,email,contacto,"
                    "COALESCE(condiciones_pago,0) FROM proveedores "
                    "WHERE COALESCE(activo,1)=1 ORDER BY nombre LIMIT 300"
                )
                rows = [
                    {"id": r[0], "nombre": r[1], "telefono": r[2], "email": r[3],
                     "contacto": r[4], "condiciones_pago": r[5], "saldo_pendiente": 0.0}
                    for r in cur.fetchall()
                ]
            except Exception as e:
                logger.warning("_SeccionProveedores.recargar fallback: %s", e)

        self._tbl.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            pid    = r.get("id")
            nombre = r.get("nombre", "")
            vals = [
                nombre,
                r.get("telefono", ""),
                r.get("email", ""),
                r.get("contacto", ""),
                f"{int(r.get('condiciones_pago', 0) or 0)} días",
                f"${float(r.get('saldo_pendiente', 0) or 0):,.2f}",
            ]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci == 0:
                    it.setData(Qt.UserRole, pid)
                self._tbl.setItem(ri, ci, it)

            btn_w   = QWidget()
            btn_lay = QHBoxLayout(btn_w)
            btn_lay.setContentsMargins(2, 2, 2, 2)
            btn_ed  = QPushButton("✏️"); btn_ed.setFixedSize(28, 26)
            btn_ed.setObjectName("outlineBtn"); btn_ed.setToolTip("Editar")
            btn_ed.setCursor(Qt.PointingHandCursor)
            btn_ed.clicked.connect(lambda _, p=pid: self._editar_por_id(p))
            btn_del = QPushButton("🗑️"); btn_del.setFixedSize(28, 26)
            btn_del.setObjectName("dangerBtn"); btn_del.setToolTip("Eliminar")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.clicked.connect(lambda _, p=pid, n=nombre: self._eliminar_proveedor(p, n))
            btn_lay.addWidget(btn_ed); btn_lay.addWidget(btn_del)
            self._tbl.setCellWidget(ri, 6, btn_w)


class _SeccionClientesCredito(QWidget):
    def __init__(self, modulo, parent=None):
        super().__init__(parent)
        self._m = modulo
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        lay.addWidget(_FinSectionHeader(
            "Clientes con Crédito",
            "Límites, saldos utilizados y disponibles",
            btn_callback=self.recargar
        ))

        self._tbl = _FinTable(
            ["Cliente", "Límite", "Saldo usado", "Disponible", "Estado", "Última compra", "Acciones"])
        self._tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        lay.addWidget(self._tbl)
        lay.addStretch()

    def recargar(self):
        m = self._m
        try:
            clientes = []
            if m._dash_svc and hasattr(m._dash_svc, "listar_clientes_credito"):
                clientes = m._dash_svc.listar_clientes_credito(sucursal_id=m.sucursal_id)
            elif m._dash_svc and hasattr(m._dash_svc, "listar_clientes"):
                todos = m._dash_svc.listar_clientes(sucursal_id=m.sucursal_id)
                clientes = [c for c in todos if float(c.get("limite_credito", 0) or 0) > 0]

            self._tbl.setRowCount(len(clientes))
            for ri, c in enumerate(clientes):
                limite    = float(c.get("limite_credito", 0) or 0)
                saldo     = float(c.get("saldo_credito", 0) or 0)
                disponible = max(0.0, limite - saldo)
                estado = "activo" if disponible > 0 else "sin disponible"
                vals = [
                    str(c.get("nombre", "")),
                    f"${limite:,.2f}",
                    f"${saldo:,.2f}",
                    f"${disponible:,.2f}",
                    estado,
                    str(c.get("ultima_compra", ""))[:10],
                ]
                for ci, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self._tbl.setItem(ri, ci, it)
                badge = _FinStatusBadge(estado)
                self._tbl.setCellWidget(ri, 4, badge)
                btn_hist = _compact_btn("Historial", "outline")
                self._tbl.setCellWidget(ri, 6, btn_hist)
        except Exception as e:
            logger.warning("_SeccionClientesCredito.recargar: %s", e)


class _SeccionReportes(QWidget):
    def __init__(self, modulo, parent=None):
        super().__init__(parent)
        self._m = modulo
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        lay.addWidget(_FinSectionHeader(
            "Reportes Financieros",
            "Genera y exporta reportes del período"
        ))

        reportes = [
            ("Flujo de efectivo",       "Estado de entradas y salidas de caja"),
            ("Estado CxC",              "Cuentas por cobrar pendientes y vencidas"),
            ("Estado CxP",              "Cuentas por pagar pendientes y vencidas"),
            ("Utilidad del período",    "Ingresos menos egresos totales"),
            ("Conciliación de caja",    "Diferencias entre sistema y conteo físico"),
            ("Póliza contable",         "Asientos contables del período"),
            ("Gastos por categoría",    "Desglose de egresos por categoría"),
            ("Nómina pagada",           "Detalle de pagos de nómina"),
            ("Capital y aportaciones",  "Movimientos de capital de socios"),
            ("Saldos de proveedores",   "Resumen de deuda con proveedores"),
            ("Saldos de clientes",      "Resumen de saldos de clientes con crédito"),
            ("Balance general",         "Activo, pasivo y capital"),
        ]

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(12)
        grid.setContentsMargins(0, 0, 0, 0)

        for i, (titulo, desc) in enumerate(reportes):
            row, col = divmod(i, 3)
            card = QGroupBox(titulo)
            c_lay = QVBoxLayout(card)
            c_lay.setSpacing(6)

            lbl = QLabel(desc)
            lbl.setObjectName("caption")
            lbl.setWordWrap(True)
            c_lay.addWidget(lbl)

            btns_row = QHBoxLayout()
            btn_ver  = QPushButton("Ver")
            btn_ver.setObjectName("primaryBtn")
            btn_ver.setCursor(Qt.PointingHandCursor)
            btn_ver.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            btn_exp  = QPushButton("Exportar")
            btn_exp.setObjectName("secondaryBtn")
            btn_exp.setCursor(Qt.PointingHandCursor)
            btn_exp.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            btns_row.addWidget(btn_ver); btns_row.addWidget(btn_exp); btns_row.addStretch()
            c_lay.addLayout(btns_row)

            grid.addWidget(card, row, col)

        scroll.setWidget(container)
        lay.addWidget(scroll)


class _SeccionConfiguracion(QWidget):
    def __init__(self, modulo, parent=None):
        super().__init__(parent)
        self._m = modulo
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        lay.addWidget(_FinSectionHeader(
            "Configuración Financiera",
            "Categorías, métodos de pago, reglas de conciliación y preferencias"
        ))

        # Categorías financieras
        grp_cat = QGroupBox("Categorías financieras")
        g_cat = QVBoxLayout(grp_cat)
        lbl_cat = QLabel("Administra las categorías para clasificar ingresos y egresos.")
        lbl_cat.setObjectName("caption")
        g_cat.addWidget(lbl_cat)
        lay.addWidget(grp_cat)

        # Métodos de pago
        grp_met = QGroupBox("Métodos de pago")
        g_met = QVBoxLayout(grp_met)
        lbl_met = QLabel("Efectivo, Transferencia, Tarjeta, Cheque, Crédito.")
        lbl_met.setObjectName("caption")
        g_met.addWidget(lbl_met)
        lay.addWidget(grp_met)

        # Reglas de conciliación
        grp_recon = QGroupBox("Reglas de conciliación")
        g_recon = QVBoxLayout(grp_recon)
        m = self._m
        if m._recon_svc:
            lbl_recon = QLabel("ReconciliationService disponible. Configura reglas aquí.")
        else:
            lbl_recon = QLabel("ReconciliationService no disponible en esta instalación.")
        lbl_recon.setObjectName("caption")
        g_recon.addWidget(lbl_recon)
        lay.addWidget(grp_recon)

        # Series / Folios
        grp_folios = QGroupBox("Series y Folios")
        g_folios = QVBoxLayout(grp_folios)
        lbl_folios = QLabel("Configura las series de folios para cada tipo de documento.")
        lbl_folios.setObjectName("caption")
        g_folios.addWidget(lbl_folios)
        lay.addWidget(grp_folios)

        # Preferencias de reportes
        grp_pref = QGroupBox("Preferencias de reportes")
        g_pref = QVBoxLayout(grp_pref)
        lbl_pref = QLabel("Moneda, formato de fecha, decimales, zona horaria.")
        lbl_pref.setObjectName("caption")
        g_pref.addWidget(lbl_pref)
        lay.addWidget(grp_pref)

        lay.addStretch()


# ═════════════════════════════════════════════════════════════════════════════
#  MÓDULO PRINCIPAL
# ═════════════════════════════════════════════════════════════════════════════

class ModuloFinanzasUnificadas(QWidget):
    """Centro financiero ERP con navegación lateral (12 secciones)."""

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container     = container
        self.sucursal_id   = 1
        self.usuario_actual = ""

        # Servicios existentes
        self._ts      = getattr(container, "treasury_service", None)
        self._tps     = getattr(container, "third_party_service", None)
        self._fs      = getattr(container, "finance_service", None)
        self._analytics = getattr(container, "analytics_engine", None)
        self._erp     = getattr(container, "erp_financial_service", None)

        # Servicios nuevos mig 083
        self._je_svc    = getattr(container, "journal_entry_service", None)
        self._fd_svc    = getattr(container, "financial_document_service", None)
        self._tm_svc    = getattr(container, "treasury_movement_service", None)
        self._recon_svc = getattr(container, "reconciliation_service", None)

        # Capital (puede no existir)
        self._capital_svc = getattr(container, "capital_service", None)

        # Dashboard service
        try:
            from core.services.finance.financial_dashboard_service import FinancialDashboardService
            _db = getattr(container, "db", None)
            self._dash_svc = FinancialDashboardService(db=_db, treasury_service=self._ts)
        except Exception:
            self._dash_svc = None

        # Lazy-build state
        self._section_built   = [False] * 12
        self._section_widgets = [None] * 12

        # Referencia al nav sidebar (para _nav_to)
        self._nav = None

        self._setup_ui()
        self._wire_live_refresh()
        self._wire_kpi_auto_refresh()

    # ─── Métodos públicos ────────────────────────────────────────────────────

    def set_sucursal(self, sucursal_id: int, nombre: str = ""):
        self.sucursal_id = sucursal_id
        self._cargar_datos_actuales()

    def set_usuario_actual(self, usuario: str, rol: str = ""):
        self.usuario_actual = usuario

    def set_active_submodule(self, name: str) -> None:
        """Selecciona sección por nombre (compatibilidad con wrappers)."""
        mapping = {
            "resumen": 0, "dashboard": 0,
            "caja": 1, "conciliacion": 1,
            "capital": 2,
            "cxc": 3, "cobrar": 3,
            "cxp": 4, "pagar": 4,
            "movimientos": 5, "tesoreria": 5,
            "asientos": 6, "ledger": 6,
            "nomina": 7, "finanzas": 7,
            "proveedores": 8,
            "clientes": 9,
            "reportes": 10,
            "configuracion": 11,
        }
        idx = mapping.get((name or "").lower())
        if idx is not None:
            self._nav_to(idx)

    def _cargar_datos_actuales(self):
        """Refresca la sección activa."""
        if self._nav is None:
            return
        idx = self._nav.currentRow()
        self._reload_section(idx)

    # ─── Acceso a autocomplete selector (usado en secciones) ─────────────────

    def _build_autocomplete_selector(self, items: List[Dict[str, Any]],
                                     placeholder: str = ""):
        txt = QLineEdit()
        txt.setPlaceholderText(placeholder or "Buscar…")
        selected_ref: Dict[str, Any] = {"id": None}
        if not items:
            return txt, selected_ref
        options   = [f"{it.get('id')} - {it.get('label','')}" for it in items]
        index_map = {opt: int(it.get("id")) for opt, it in zip(options, items)}
        completer = QCompleter(options)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        txt.setCompleter(completer)

        def _on_activate(text: str):
            selected_ref["id"] = index_map.get(text)
            txt.setText(text)

        completer.activated[str].connect(_on_activate)

        def _sync():
            selected_ref["id"] = index_map.get(txt.text().strip())

        txt.editingFinished.connect(_sync)
        return txt, selected_ref

    # ─── Setup UI ────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # PageHeader
        header = PageHeader(
            self,
            title="Finanzas",
            subtitle="Tesorería · Contabilidad · Proveedores — fuente única de verdad",
        )
        root.addWidget(header)

        # Splitter: sidebar | stack
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)

        # ── Sidebar ──────────────────────────────────────────────────────────
        self._nav = QListWidget()
        self._nav.setObjectName("finSidebar")
        self._nav.setFixedWidth(180)
        self._nav.setStyleSheet(
            f"QListWidget#finSidebar {{"
            f"  background:{Colors.SIDEBAR.BG};"
            f"  border:none;"
            f"  color:{Colors.SIDEBAR.TEXT};"
            f"  font-size:12px;"
            f"  outline:none;"
            f"}}"
            f"QListWidget#finSidebar::item {{"
            f"  padding:10px 14px;"
            f"  border-left:3px solid transparent;"
            f"}}"
            f"QListWidget#finSidebar::item:hover {{"
            f"  background:{Colors.SIDEBAR.HOVER};"
            f"}}"
            f"QListWidget#finSidebar::item:selected {{"
            f"  background:{Colors.SIDEBAR.ACTIVE};"
            f"  border-left:3px solid {Colors.PRIMARY_BASE};"
            f"  color:{Colors.NEUTRAL.WHITE};"
            f"}}"
        )
        for label, icon in _SECCIONES:
            item = QListWidgetItem(f"  {icon}  {label}")
            self._nav.addItem(item)
        self._nav.currentRowChanged.connect(self._on_section_changed)

        # ── Stack ────────────────────────────────────────────────────────────
        self._stack = QStackedWidget()
        # Rellenar con placeholders
        for _ in _SECCIONES:
            placeholder = QWidget()
            self._stack.addWidget(placeholder)

        splitter.addWidget(self._nav)
        splitter.addWidget(self._stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter)

        # Seleccionar primera sección
        self._nav.setCurrentRow(0)

    def _nav_to(self, index: int):
        """Navega programáticamente a una sección."""
        if 0 <= index < 12:
            self._nav.setCurrentRow(index)

    def _on_section_changed(self, index: int):
        if index < 0:
            return
        self._ensure_section_built(index)
        self._stack.setCurrentIndex(index)
        self._reload_section(index)

    def _ensure_section_built(self, index: int):
        if self._section_built[index]:
            return
        builders = [
            lambda: _SeccionResumen(self),
            lambda: _SeccionCajayConciliacion(self),
            lambda: _SeccionCapital(self),
            lambda: _SeccionCuentasPorCobrar(self),
            lambda: _SeccionCuentasPorPagar(self),
            lambda: _SeccionMovimientos(self),
            lambda: _SeccionAsientosContables(self),
            lambda: _SeccionNomina(self),
            lambda: _SeccionProveedores(self),
            lambda: _SeccionClientesCredito(self),
            lambda: _SeccionReportes(self),
            lambda: _SeccionConfiguracion(self),
        ]
        widget = builders[index]()
        self._section_widgets[index] = widget
        self._stack.removeWidget(self._stack.widget(index))
        self._stack.insertWidget(index, widget)
        self._section_built[index] = True

    def _reload_section(self, index: int):
        if not self._section_built[index]:
            return
        w = self._section_widgets[index]
        if w and hasattr(w, "recargar"):
            try:
                w.recargar()
            except Exception as e:
                logger.warning("_reload_section[%d]: %s", index, e)

    # ─── Eventos del bus ─────────────────────────────────────────────────────

    def _wire_live_refresh(self):
        try:
            from core.events.event_bus import get_bus
            bus = get_bus()
            bus.subscribe("PROVEEDOR_CREADO",     lambda _: QTimer.singleShot(0, lambda: self._reload_section(8)),  label="fin.ui.prov_creado")
            bus.subscribe("PROVEEDOR_ACTUALIZADO",lambda _: QTimer.singleShot(0, lambda: self._reload_section(8)),  label="fin.ui.prov_act")
            bus.subscribe("PROVEEDOR_ELIMINADO",  lambda _: QTimer.singleShot(0, lambda: self._reload_section(8)),  label="fin.ui.prov_del")
            bus.subscribe("CXP_CREADA",           lambda _: QTimer.singleShot(0, lambda: self._reload_section(4)),  label="fin.ui.cxp_creada")
            bus.subscribe("CXC_CREADA",           lambda _: QTimer.singleShot(0, lambda: self._reload_section(3)),  label="fin.ui.cxc_creada")
            bus.subscribe("CLIENTE_CREADO",       lambda _: QTimer.singleShot(0, lambda: self._reload_section(3)),  label="fin.ui.cliente_creado")
        except Exception:
            pass

    def _wire_kpi_auto_refresh(self):
        try:
            self._kpi_timer = QTimer(self)
            self._kpi_timer.setInterval(15000)
            self._kpi_timer.timeout.connect(self._refresh_kpis_if_visible)
            self._kpi_timer.start()
            from core.events.event_bus import get_bus
            bus = get_bus()
            for evt in ("VENTA_COMPLETADA", "MOVIMIENTO_FINANCIERO", "CXP_CREADA", "CXC_CREADA", "AJUSTE_INVENTARIO"):
                bus.subscribe(evt, lambda _d: QTimer.singleShot(0, lambda: self._reload_section(0)),
                              label=f"fin.ui.kpi.{evt.lower()}")
        except Exception:
            pass

    def _refresh_kpis_if_visible(self):
        if self._nav and self._nav.currentRow() == 0:
            self._reload_section(0)

    # ─── Métodos legacy (compatibilidad interna) ──────────────────────────────

    def _cargar_proveedores(self):
        """Compatibilidad: recarga sección proveedores."""
        self._reload_section(8)

    def _cargar_cuentas_pagar(self):
        """Compatibilidad: recarga sección CxP."""
        self._reload_section(4)

    def _cargar_cuentas_cobrar(self):
        """Compatibilidad: recarga sección CxC."""
        self._reload_section(3)

    def _cargar_dashboard_financiero(self):
        """Compatibilidad: recarga sección resumen."""
        self._reload_section(0)

    def _normalizar_botones_ui(self):
        """Compatibilidad: normaliza botones en la UI."""
        for btn in self.findChildren(QPushButton):
            if btn.maximumWidth() <= 36:
                continue
            btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            if btn.minimumHeight() < 30:
                btn.setMinimumHeight(30)


# Alias de compatibilidad
ModuloFinanzas = ModuloFinanzasUnificadas
