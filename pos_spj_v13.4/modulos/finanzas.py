
# modulos/finanzas.py
# ── ModuloFinanzas — Motor Financiero Enterprise SPJ POS ─────────────────────
#
# 8 Tabs:
#   [0] 📊 Dashboard   — KPIs financieros ejecutivos
#   [1] 💸 CXP         — Cuentas por Pagar (proveedores)
#   [2] 💰 CXC         — Cuentas por Cobrar (clientes crédito)
#   [3] 🏢 Proveedores  — Catálogo extendido de proveedores
#   [4] 📋 Gastos       — Gastos operativos / recurrentes
#   [5] 👥 Personal     — RRHH + nómina
#   [6] 🏗 Activos      — Activos fijos + mantenimientos
#   [7] 🛒 Compras      — Compras inventariables (pollo, abarrotes)
#
# REGLA: cero SQL directo en UI — todo via FinanceService
# Diálogos legacy preservados: _DialogoCompraInventariable, DialogoGasto, DialogoEmpleado
from __future__ import annotations
from core.services.auto_audit import audit_write

import logging
import sqlite3
from datetime import date, datetime
from typing import Optional

from modulos.design_tokens import Colors, Spacing, Typography, Shadows
from modulos.ui_components import create_primary_button, create_success_button, create_danger_button, create_secondary_button, create_warning_button, create_input_field, create_card, apply_tooltip, create_heading, create_subheading, create_badge
from PyQt5.QtCore import Qt, QDate, QTimer
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
    QFileDialog
)

from .base import ModuloBase
from core.services.enterprise.finance_service import FinanceService
from core.events.event_bus import EventBus

logger = logging.getLogger("spj.ui.finanzas")

# ── Paleta corporativa (LEGACY - en desuso, usar design_tokens) ─────────────
# Estas constantes se mantienen solo para compatibilidad con código no refactorizado
# NUEVO CÓDIGO: usar Colors.PRIMARY_BASE, Colors.SUCCESS_BASE, etc.
_NAVY  = "#0F4C81"
_BLUE  = "#2E86C1"
_TEAL  = "#1ABC9C"
_AMBER = "#F4D03F"
_RED   = "#E74C3C"
_GREEN = "#27AE60"
_SLATE = "#2C3E50"
_DARK  = "#1A252F"
_ASH   = "#ECF0F1"
_GRAY  = "#7F8C8D"
_ORANGE= "#E67E22"

_TAB_STYLE = (
    "QTabWidget::pane{background:#1A252F;border:1px solid #2C3E50;}"
    "QTabBar::tab{background:#2C3E50;color:#95A5A6;padding:8px 16px;"
    "border-radius:3px 3px 0 0;margin-right:2px;font-size:11px;}"
    "QTabBar::tab:selected{background:#0F4C81;color:white;font-weight:bold;}"
    "QTabBar::tab:hover{background:#2E86C1;color:white;}"
)
_TBL = (
    "QTableWidget{background:#1A252F;color:#ECF0F1;gridline-color:#2C3E50;}"
    "QHeaderView::section{background:#0F4C81;color:#ECF0F1;padding:5px;"
    "border:none;font-weight:bold;font-size:10px;}"
    "QTableWidget::item:alternate{background:#1E2D3D;}"
    "QTableWidget::item:selected{background:#2E86C1;color:white;}"
)
_GRP = (
    "QGroupBox{color:#ECF0F1;font-weight:bold;border:1px solid #2C3E50;"
    "border-radius:4px;margin-top:8px;padding-top:8px;}"
    "QGroupBox::title{subcontrol-origin:margin;left:8px;color:#ECF0F1;}"
)
_BTN = "QPushButton{{background:{};color:white;padding:5px 12px;" \
       "border-radius:3px;font-weight:bold;}}" \
       "QPushButton:hover{{background:{};color:white;}}"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _it(txt, align=Qt.AlignLeft | Qt.AlignVCenter,
        color=None, bold=False, bg=None):
    it = QTableWidgetItem(str(txt))
    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
    it.setTextAlignment(align)
    if color: it.setForeground(QColor(color))
    if bg:    it.setBackground(QColor(bg))
    if bold:
        f = it.font(); f.setBold(True); it.setFont(f)
    return it


_R = Qt.AlignRight | Qt.AlignVCenter


def _tbl(headers, stretch=0):
    """Tabla estandarizada con diseño limpio."""
    t = QTableWidget()
    t.setColumnCount(len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.verticalHeader().setVisible(False)
    t.setAlternatingRowColors(True)
    t.setObjectName("dataTable")  # Usa estilos de design_tokens
    h = t.horizontalHeader()
    h.setSectionResizeMode(stretch, QHeaderView.Stretch)
    for i in range(len(headers)):
        if i != stretch:
            h.setSectionResizeMode(i, QHeaderView.ResizeToContents)
    return t


def _btn(label, color=Colors.PRIMARY_BASE, parent=None):
    """Botón estandarizado usando factory."""
    b = QPushButton(label, parent)
    b.setObjectName("primaryBtn")  # Usa estilos centralizados
    return b


    def _tab_rrhh_redirect(self):
        """Tab que linkea al módulo RRHH dedicado."""
        w = QWidget(); layout = QVBoxLayout(w); layout.addStretch()
        lbl = create_heading(self, "👥 Módulo RRHH")
        lbl.setAlignment(Qt.AlignCenter)
        desc = create_subheading(self, "El módulo de Recursos Humanos ahora tiene su propio panel.\n\nAccede desde el menú lateral → RRHH")
        desc.setAlignment(Qt.AlignCenter)
        try:
            btn = create_primary_button(self, "Ir a RRHH →", "Navegar al módulo de Recursos Humanos")
            btn.clicked.connect(lambda: self.parent().mostrar_modulo("rrhh") if self.parent() and hasattr(self.parent(),"mostrar_modulo") else None)
            layout.addWidget(lbl); layout.addSpacing(Spacing.MD); layout.addWidget(desc); layout.addSpacing(Spacing.LG); layout.addWidget(btn, 0, Qt.AlignCenter)
        except Exception:
            layout.addWidget(lbl); layout.addWidget(desc)
        layout.addStretch()
        return w

    def _tab_activos_redirect(self):
        w = QWidget(); layout = QVBoxLayout(w); layout.addStretch()
        lbl = create_heading(self, "🏭 Módulo Activos Fijos")
        lbl.setAlignment(Qt.AlignCenter)
        desc = create_subheading(self, "El módulo de Activos Fijos ahora tiene su propio panel.\n\nAccede desde el menú lateral → ACTIVOS")
        desc.setAlignment(Qt.AlignCenter)
        try:
            btn = create_warning_button(self, "Ir a Activos →", "Navegar al módulo de Activos Fijos")
            btn.clicked.connect(lambda: self.parent().mostrar_modulo("activos") if self.parent() and hasattr(self.parent(),"mostrar_modulo") else None)
            layout.addWidget(lbl); layout.addSpacing(Spacing.MD); layout.addWidget(desc); layout.addSpacing(Spacing.LG); layout.addWidget(btn, 0, Qt.AlignCenter)
        except Exception:
            layout.addWidget(lbl); layout.addWidget(desc)
        layout.addStretch()
        return w

    def _tab_compras_redirect(self):
        w = QWidget(); layout = QVBoxLayout(w); layout.addStretch()
        lbl = create_heading(self, "🛒 Sistema de Compras Pro")
        lbl.setAlignment(Qt.AlignCenter)
        desc = create_subheading(self, "El sistema de Compras ahora tiene su propio panel completo.\n\nAccede desde el menú lateral → COMPRAS PRO")
        desc.setAlignment(Qt.AlignCenter)
        try:
            btn = create_success_button(self, "Ir a Compras Pro →", "Navegar al módulo de Compras Pro")
            btn.clicked.connect(lambda: self.parent().mostrar_modulo("compras_pro") if self.parent() and hasattr(self.parent(),"mostrar_modulo") else None)
            layout.addWidget(lbl); layout.addSpacing(Spacing.MD); layout.addWidget(desc); layout.addSpacing(Spacing.LG); layout.addWidget(btn, 0, Qt.AlignCenter)
        except Exception:
            layout.addWidget(lbl); layout.addWidget(desc)
        layout.addStretch()
        return w


class _KpiCard(QFrame):
    def __init__(self, title, color, icon=""):
        super().__init__()
        self.setFixedHeight(88)
        self.setObjectName("kpiCard")  # Usa estilos centralizados
        lay = QVBoxLayout(self)
        lay.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)
        lay.setSpacing(Spacing.XS)
        lbl = QLabel(f"{icon}  {title}".strip())
        lbl.setObjectName("caption")  # Usa estilo caption
        self._v = QLabel("—")
        self._v.setObjectName("kpiValue")  # Usa estilo centralizado para valor KPI con color dinámico
        self._s = QLabel("")
        self._s.setObjectName("caption")
        lay.addWidget(lbl)
        lay.addWidget(self._v)
        lay.addWidget(self._s)

    def set(self, val, sub="", pos=None):
        self._v.setText(str(val))
        if sub:
            c = _GREEN if pos else (_RED if pos is False else _GRAY)
            self._s.setText(sub)
            self._s.setStyleSheet(f"color:{c};font-size:9px;")  # Subtítulo mantiene color dinámico pequeño


# ── Wrapper DB compatible con FinanceService ──────────────────────────────────

class _DBWrapper:
    def __init__(self, conexion):
        self._c = conexion

    @property
    def conn(self):
        return self._c

    def fetchone(self, sql, params=()):
        r = self._c.execute(sql, params).fetchone()
        if r is None:
            return None
        if hasattr(r, 'keys'):
            return r
        return r

    def fetchall(self, sql, params=()):
        return self._c.execute(sql, params).fetchall()

    def execute(self, sql, params=()):
        return self._c.execute(sql, params)


# ══════════════════════════════════════════════════════════════════════════════

    def commit(self):
        try: self._c.commit()
        except Exception: pass

    def rollback(self):
        try: self._c.rollback()
        except Exception: pass

class ModuloFinanzas(ModuloBase):

    def __init__(self, conexion, parent=None):
        super().__init__(conexion, parent)
        # Accept AppContainer or direct db connection
        from core.db.connection import wrap
        if hasattr(conexion, 'db'):
            self.container = conexion
            self.conexion  = wrap(conexion.db)
        else:
            self.container = None
            self.conexion  = wrap(conexion)
        self.main_window     = parent
        self.usuario_actual  = "admin"
        self.rol_usuario     = ""
        self.sucursal_id     = 1
        self.sucursal_nombre = "Principal"
        self._svc = FinanceService(self.conexion)
        self._init_ui()
        try:
            EventBus().subscribe("VENTA_COMPLETADA",
                               lambda _: QTimer.singleShot(3000, self._sync_and_refresh))
        except Exception:
            pass
        QTimer.singleShot(300, self._sync_all)

    # ── Propiedades ───────────────────────────────────────────────────────────

    def set_sucursal(self, sid, nombre):
        self.sucursal_id = sid
        self.sucursal_nombre = nombre

    def set_usuario_actual(self, u, rol=""):
        self.usuario_actual = u or "admin"
        self.rol_usuario = rol or ""

    def obtener_usuario_actual(self):
        return self.usuario_actual

    # ── Sincronización ────────────────────────────────────────────────────────

    def _sync_all(self):
        try:
            n1 = self._svc.sync_cxp_from_compras()
            n2 = self._svc.sync_cxc_from_ventas()
            if n1 or n2:
                logger.info("Sync: %d CXP + %d CXC nuevas", n1, n2)
        except Exception as exc:
            logger.warning("sync_all: %s", exc)

    def _sync_and_refresh(self):
        self._sync_all()
        self._on_tab(self.tabs.currentIndex())

    # ── UI ────────────────────────────────────────────────────────────────────

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        root.setSpacing(Spacing.SM)

        # Cabecera
        hdr = QHBoxLayout()
        ttl = create_heading(self, "💼  Motor Financiero Enterprise")
        self._lbl_hdr = QLabel()
        self._lbl_hdr.setObjectName("caption")
        hdr.addWidget(ttl); hdr.addStretch(); hdr.addWidget(self._lbl_hdr)
        root.addLayout(hdr)

        # Controles período
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Desde:"))
        self._df = QDateEdit(QDate.currentDate().addDays(-30))
        self._df.setCalendarPopup(True)
        self._dt = QDateEdit(QDate.currentDate())
        self._dt.setCalendarPopup(True)
        ctrl.addWidget(self._df)
        ctrl.addWidget(QLabel("Hasta:"))
        ctrl.addWidget(self._dt)

        for d, lb in [(7,"7d"),(30,"30d"),(90,"3m"),(365,"Año")]:
            b = QPushButton(lb); b.setFixedWidth(40)
            b.setObjectName("secondaryBtn")  # Usa estilo centralizado
            b.clicked.connect(lambda _, dd=d: self._set_period(dd))
            ctrl.addWidget(b)

        br = create_primary_button(self, "🔄 Actualizar", "Actualizar datos financieros")
        br.clicked.connect(lambda _, _vs=s: self._on_tab(_vself.tabs.currentIndex()))
        ctrl.addWidget(br)

        bs = create_success_button(self, "🔗 Sincronizar", "Sincronizar CXP desde compras y CXC desde ventas crédito")
        bs.clicked.connect(self._sync_and_refresh)
        ctrl.addWidget(bs)
        ctrl.addStretch()
        root.addLayout(ctrl)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setObjectName("tabWidget")  # Usa estilo centralizado
        self.tabs.currentChanged.connect(self._on_tab)
        self.tabs.addTab(self._tab_dashboard(),   "📊 Dashboard")
        self.tabs.addTab(self._tab_cxp(),         "💸 C×Pagar")
        self.tabs.addTab(self._tab_cxc(),         "💰 C×Cobrar")
        self.tabs.addTab(self._tab_proveedores(),  "🏢 Proveedores")
        self.tabs.addTab(self._tab_gastos(),       "📋 Gastos")
        self.tabs.addTab(self._tab_rrhh_redirect(), "👥 RRHH")
        self.tabs.addTab(self._tab_activos_redirect(), "🏗 Activos")
        self.tabs.addTab(self._tab_compras_redirect(), "🛒 Compras")
        root.addWidget(self.tabs)

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 0 — DASHBOARD
    # ═══════════════════════════════════════════════════════════════════════

    def _tab_dashboard(self):
        w = QWidget(); root = QVBoxLayout(w); root.setSpacing(10)

        # KPI grid 4×2
        g = QGridLayout(); g.setSpacing(8)
        self.kpi_ingresos   = _KpiCard("Ingresos",        _TEAL,  "💰")
        self.kpi_ut_bruta   = _KpiCard("Utilidad Bruta",  _GREEN, "📈")
        self.kpi_ut_neta    = _KpiCard("Utilidad Neta",   _BLUE,  "💵")
        self.kpi_margen     = _KpiCard("Margen Neto %",   _AMBER, "📊")
        self.kpi_gastos     = _KpiCard("Gastos Totales",  _RED,   "📋")
        self.kpi_nomina     = _KpiCard("Nómina Pagada",   _ORANGE,"👥")
        self.kpi_cxp        = _KpiCard("CXP Pendiente",   _RED,   "💸")
        self.kpi_cxc        = _KpiCard("CXC Pendiente",   _TEAL,  "💰")
        cards = [self.kpi_ingresos, self.kpi_ut_bruta, self.kpi_ut_neta, self.kpi_margen,
                 self.kpi_gastos, self.kpi_nomina, self.kpi_cxp, self.kpi_cxc]
        for i, c in enumerate(cards):
            g.addWidget(c, i // 4, i % 4)
        root.addLayout(g)

        # Balance general (tabla)
        lbl_bg = create_subheading(self, "🏦  Balance General")
        root.addWidget(lbl_bg)

        self.tbl_balance = _tbl(["Rubro", "Subcategoría", "Monto"], stretch=1)
        self.tbl_balance.setMaximumHeight(250)
        root.addWidget(self.tbl_balance)

        # Flujo de caja (tabla simple)
        lbl_fc = create_subheading(self, "💸  Flujo de Caja del Período")
        root.addWidget(lbl_fc)
        self.tbl_flujo = _tbl(["Tipo", "Concepto", "Monto"], stretch=1)
        self.tbl_flujo.setMaximumHeight(180)
        root.addWidget(self.tbl_flujo)
        root.addStretch()
        return w

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 1 — CXP
    # ═══════════════════════════════════════════════════════════════════════

    def _tab_cxp(self):
        w = QWidget(); root = QVBoxLayout(w)

        top = QHBoxLayout()
        self._lbl_cxp_resumen = QLabel()
        self._lbl_cxp_resumen.setObjectName("caption")  # Usa estilo caption
        top.addWidget(self._lbl_cxp_resumen); top.addStretch()

        bt_nuevo  = create_primary_button(self, "➕ Nueva CXP", "Crear nueva cuenta por pagar")
        bt_abonar = create_success_button(self, "💵 Abonar", "Registrar abono a CXP")
        bt_hist   = create_secondary_button(self, "📜 Historial", "Ver historial de pagos")
        bt_ref    = create_secondary_button(self, "🔄 Actualizar", "Actualizar lista de CXP")
        bt_nuevo.clicked.connect(self._nueva_cxp)
        bt_abonar.clicked.connect(self._abonar_cxp)
        bt_hist.clicked.connect(self._historial_cxp)
        bt_ref.clicked.connect(self._load_cxp)
        for b in [bt_nuevo, bt_abonar, bt_hist, bt_ref]:
            top.addWidget(b)
        root.addLayout(top)

        # Filtro
        fh = QHBoxLayout()
        fh.addWidget(QLabel("Estado:"))
        self._cxp_estado_f = QComboBox()
        for s in ["Todas","pendiente","parcial","pagado"]:
            self._cxp_estado_f.addItem(s)
        self._cxp_estado_f.currentIndexChanged.connect(self._load_cxp)
        fh.addWidget(self._cxp_estado_f); fh.addStretch()
        root.addLayout(fh)

        self.tbl_cxp = _tbl(
            ["ID","Folio","Proveedor","Concepto","Total","Saldo",
             "Vencimiento","Aging","Estado"],
            stretch=3
        )
        root.addWidget(self.tbl_cxp)
        return w

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 2 — CXC
    # ═══════════════════════════════════════════════════════════════════════

    def _tab_cxc(self):
        w = QWidget(); root = QVBoxLayout(w)

        top = QHBoxLayout()
        self._lbl_cxc_resumen = QLabel()
        self._lbl_cxc_resumen.setObjectName("textAccent")  # Usa estilo centralizado para texto destacado
        top.addWidget(self._lbl_cxc_resumen); top.addStretch()

        bt_nueva  = create_primary_button(self, "➕ Nueva CXC", "Crear nueva cuenta por cobrar")
        bt_cobrar = create_success_button(self, "💵 Cobrar", "Registrar cobro de cuenta por cobrar")
        bt_ref    = create_secondary_button(self, "🔄 Actualizar", "Refrescar lista de CXC")
        bt_nueva.clicked.connect(self._nueva_cxc)
        bt_cobrar.clicked.connect(self._cobrar_cxc)
        bt_ref.clicked.connect(self._load_cxc)
        for b in [bt_nueva, bt_cobrar, bt_ref]:
            top.addWidget(b)
        root.addLayout(top)

        self.tbl_cxc = _tbl(
            ["ID","Folio","Cliente","Concepto","Total","Saldo",
             "Vencimiento","Días Venc.","Estado"],
            stretch=3
        )
        root.addWidget(self.tbl_cxc)
        return w

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 3 — PROVEEDORES
    # ═══════════════════════════════════════════════════════════════════════

    def _tab_proveedores(self):
        w = QWidget(); root = QVBoxLayout(w)
        sp = QSplitter(Qt.Horizontal)

        # Lista
        left = QWidget(); ll = QVBoxLayout(left)
        top = QHBoxLayout()
        self._prov_buscar = QLineEdit()
        self._prov_buscar.setPlaceholderText("Buscar proveedor…")
        self._prov_buscar.textChanged.connect(self._load_proveedores)
        top.addWidget(self._prov_buscar)
        bt_nuevo = _btn("➕ Nuevo", _NAVY)
        bt_nuevo.clicked.connect(self._nuevo_proveedor)
        bt_editar = _btn("✏ Editar", _BLUE)
        bt_editar.clicked.connect(self._editar_proveedor)
        for b in [bt_nuevo, bt_editar]: top.addWidget(b)
        ll.addLayout(top)

        self.tbl_prov = _tbl(
            ["ID","Nombre","RFC","Teléfono","Tipo","Crédito días",
             "Saldo Pend.","Facturas"],
            stretch=1
        )
        self.tbl_prov.itemSelectionChanged.connect(self._prov_sel)
        ll.addWidget(self.tbl_prov)
        sp.addWidget(left)

        # Panel detalle
        right = QWidget(); rl = QVBoxLayout(right)
        rl.addWidget(QLabel("Detalle de Proveedor:"))
        self._prov_detail = QTextEdit()
        self._prov_detail.setReadOnly(True)
        self._prov_detail.setObjectName("infoBox")  # Usa estilo centralizado para box informativo
        rl.addWidget(self._prov_detail)

        rl.addWidget(QLabel("CXP abiertas:"))
        self.tbl_prov_cxp = _tbl(
            ["ID","Concepto","Total","Saldo","Vence","Estado"],
            stretch=1
        )
        rl.addWidget(self.tbl_prov_cxp)
        sp.addWidget(right)
        sp.setSizes([550, 350])
        root.addWidget(sp)
        return w

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 4 — GASTOS (preserva lógica legacy)
    # ═══════════════════════════════════════════════════════════════════════

    def _tab_gastos(self):
        w = QWidget(); root = QVBoxLayout(w)

        # Filtros
        fh = QHBoxLayout()
        self.combo_filtro_estado = QComboBox()
        self.combo_filtro_estado.addItems(
            ["Todos","Pendientes","Pagados","Recurrentes"]
        )
        self.combo_filtro_estado.currentIndexChanged.connect(self.filtrar_gastos)
        self._gastos_buscar = QLineEdit()
        self._gastos_buscar.setPlaceholderText("Buscar gasto…")
        self._gastos_buscar.returnPressed.connect(self.filtrar_gastos)
        fh.addWidget(QLabel("Estado:")); fh.addWidget(self.combo_filtro_estado)
        fh.addWidget(self._gastos_buscar)
        bt_buscar = _btn("🔍", _NAVY); bt_buscar.setFixedWidth(32)
        bt_buscar.clicked.connect(self.filtrar_gastos)
        fh.addWidget(bt_buscar); fh.addStretch()
        root.addLayout(fh)

        # Botones
        bh = QHBoxLayout()
        bt_nuevo   = _btn("➕ Nuevo",    _NAVY)
        bt_editar  = _btn("✏ Editar",   _BLUE)
        bt_abonar  = _btn("💵 Abonar",  _GREEN)
        bt_elim    = _btn("🗑 Eliminar", _RED)
        bt_ref     = _btn("🔄 Refrescar",_GRAY)
        bt_nuevo.clicked.connect(self.nuevo_gasto)
        bt_editar.clicked.connect(self.editar_gasto)
        bt_abonar.clicked.connect(self.abonar_gasto)
        bt_elim.clicked.connect(self.eliminar_gasto)
        bt_ref.clicked.connect(self.filtrar_gastos)
        self.btn_editar_gasto  = bt_editar
        self.btn_eliminar_gasto = bt_elim
        self.btn_abonar_gasto  = bt_abonar
        for b in [bt_nuevo, bt_editar, bt_abonar, bt_elim, bt_ref]:
            bh.addWidget(b)
        bh.addStretch(); root.addLayout(bh)

        self.tabla_gastos = _tbl(
            ["ID","Fecha","Categoría","Concepto","Monto","Pagado",
             "Pendiente","Estado","Método","Recurrente","Usuario"],
            stretch=3
        )
        self.tabla_gastos.itemSelectionChanged.connect(self.actualizar_botones_gastos)
        root.addWidget(self.tabla_gastos)

        # Resumen por categoría
        grp = QGroupBox("Resumen por Categoría")
        grp.setObjectName("styledGroup")  # Usa estilo centralizado para GroupBox
        gl = QVBoxLayout(grp)
        self.tbl_gastos_cat = _tbl(
            ["Categoría","Registros","Total","Pagado","Pendiente"],
            stretch=0
        )
        self.tbl_gastos_cat.setMaximumHeight(160)
        gl.addWidget(self.tbl_gastos_cat)
        root.addWidget(grp)
        return w

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 5 — PERSONAL (preserva lógica legacy)
    # ═══════════════════════════════════════════════════════════════════════

    def _tab_personal(self):
        w = QWidget(); root = QVBoxLayout(w)

        fh = QHBoxLayout()
        self.combo_filtro_estado = QComboBox() if not hasattr(self, 'combo_filtro_estado') else self.combo_filtro_estado
        self._combo_filtro_personal = QComboBox()
        self._combo_filtro_personal.addItems(["Todos","Activos","Inactivos"])
        self._combo_filtro_personal.currentIndexChanged.connect(self.cargar_personal)
        self.busqueda_personal = QLineEdit()
        self.busqueda_personal.setPlaceholderText("Buscar empleado…")
        self.busqueda_personal.returnPressed.connect(self.buscar_personal)
        fh.addWidget(QLabel("Estado:")); fh.addWidget(self._combo_filtro_personal)
        fh.addWidget(self.busqueda_personal)
        bt_b = _btn("🔍", _NAVY); bt_b.setFixedWidth(32)
        bt_b.clicked.connect(self.buscar_personal)
        fh.addWidget(bt_b); fh.addStretch()
        root.addLayout(fh)

        bh = QHBoxLayout()
        bt_nuevo  = _btn("➕ Nuevo",    _NAVY)
        bt_editar = _btn("✏ Editar",   _BLUE)
        bt_elim   = _btn("🗑 Desactivar",_RED)
        bt_nomina = _btn("💵 Pagar Nómina",_GREEN)
        bt_hist_nom = _btn("📜 Historial Nómina",_ORANGE)
        bt_nuevo.clicked.connect(self.nuevo_empleado)
        bt_editar.clicked.connect(self.editar_empleado)
        bt_elim.clicked.connect(self.eliminar_empleado)
        bt_nomina.clicked.connect(self._pagar_nomina)
        bt_hist_nom.clicked.connect(self._historial_nomina)
        self.btn_editar_empleado   = bt_editar
        self.btn_eliminar_empleado = bt_elim
        for b in [bt_nuevo, bt_editar, bt_elim, bt_nomina, bt_hist_nom]:
            bh.addWidget(b)
        bh.addStretch(); root.addLayout(bh)

        sp = QSplitter(Qt.Vertical)
        self.tabla_personal = _tbl(
            ["ID","Nombre","Apellidos","Puesto","Salario",
             "Fecha Ingreso","Estado","Total Nómina"],
            stretch=1
        )
        self.tabla_personal.itemSelectionChanged.connect(self.actualizar_botones_personal)
        sp.addWidget(self.tabla_personal)

        grp_nom = QGroupBox("Últimos Pagos de Nómina")
        grp_nom.setObjectName("styledGroup")  # Usa estilo centralizado para GroupBox
        gn_lay = QVBoxLayout(grp_nom)
        self.tbl_nomina = _tbl(
            ["ID","Empleado","Puesto","Período","Salario","Bonos","Ded.","Total","Método","Fecha"],
            stretch=1
        )
        self.tbl_nomina.setMaximumHeight(180)
        gn_lay.addWidget(self.tbl_nomina)
        sp.addWidget(grp_nom)
        sp.setSizes([300, 190])
        root.addWidget(sp)
        return w

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 6 — ACTIVOS FIJOS
    # ═══════════════════════════════════════════════════════════════════════

    def _tab_activos(self):
        w = QWidget(); root = QVBoxLayout(w)
        sp = QSplitter(Qt.Vertical)

        # Lista de activos
        top_w = QWidget(); tl = QVBoxLayout(top_w)
        bh = QHBoxLayout()
        self._act_tipo_f = QComboBox()
        for t in ["Todos","vehiculo","equipo_pos","refrigerador",
                  "bascula","mobiliario","otro"]:
            self._act_tipo_f.addItem(t)
        self._act_tipo_f.currentIndexChanged.connect(self._load_activos)
        bh.addWidget(QLabel("Tipo:")); bh.addWidget(self._act_tipo_f)
        bt_nuevo = _btn("➕ Nuevo Activo", _NAVY)
        bt_mant  = _btn("🔧 Mantenimiento", _ORANGE)
        bt_ref   = _btn("🔄 Actualizar", _GRAY)
        bt_nuevo.clicked.connect(self._nuevo_activo)
        bt_mant.clicked.connect(self._nuevo_mantenimiento)
        bt_ref.clicked.connect(self._load_activos)
        for b in [bt_nuevo, bt_mant, bt_ref]: bh.addWidget(b)
        bh.addStretch(); tl.addLayout(bh)

        self.tbl_activos = _tbl(
            ["ID","Código","Nombre","Tipo","Marca","Valor Compra",
             "Valor Actual","Estado","Ubicación","# Mant.","$ Mant."],
            stretch=2
        )
        self.tbl_activos.itemSelectionChanged.connect(self._act_sel)
        tl.addWidget(self.tbl_activos)
        sp.addWidget(top_w)

        # Historial de mantenimientos
        bot_w = QWidget(); bl = QVBoxLayout(bot_w)
        lbl_m = QLabel("Historial de Mantenimientos:")
        lbl_m.setObjectName("subheading")  # Usa estilo centralizado para subtítulo
        bl.addWidget(lbl_m)
        self.tbl_mant = _tbl(
            ["ID","Activo","Tipo","Fecha","Descripción","Costo",
             "Responsable","Estado","Próxima Revisión"],
            stretch=4
        )
        bl.addWidget(self.tbl_mant)
        sp.addWidget(bot_w)
        sp.setSizes([280, 220])
        root.addWidget(sp)
        return w

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 7 — COMPRAS INVENTARIABLES (legacy preservado)
    # ═══════════════════════════════════════════════════════════════════════

    def _tab_compras_inv(self):
        w = QWidget(); root = QVBoxLayout(w)

        bh = QHBoxLayout()
        bt_nueva = _btn("➕ Nueva Compra", _NAVY)
        bt_ref   = _btn("🔄 Actualizar",   _GRAY)
        bt_nueva.clicked.connect(self._nueva_compra_inv)
        bt_ref.clicked.connect(self._load_compras_inv)
        for b in [bt_nueva, bt_ref]: bh.addWidget(b)
        bh.addStretch(); root.addLayout(bh)

        sp = QSplitter(Qt.Vertical)

        # Tabla compras
        self.tbl_compras_inv = _tbl(
            ["ID","Producto","Proveedor","Volumen","Unidad",
             "C.Unit","Total","Pagado","Saldo","Estado","Fecha"],
            stretch=1
        )
        sp.addWidget(self.tbl_compras_inv)

        # CXP de estas compras
        grp = QGroupBox("Cuentas por Pagar de Compras")
        grp.setObjectName("styledGroup")  # Usa estilo centralizado para GroupBox
        gl = QVBoxLayout(grp)
        self._lbl_cxp_ci_total = QLabel()
        self._lbl_cxp_ci_total.setObjectName("textDanger")  # Usa estilo centralizado para texto de peligro
        gl.addWidget(self._lbl_cxp_ci_total)
        self.tbl_cxp_ci = _tbl(
            ["ID","Proveedor","Producto","Total","Pagado","Saldo","Vencimiento","Estado"],
            stretch=1
        )
        bt_pagar_ci = _btn("💵 Registrar Pago", _GREEN)
        bt_pagar_ci.clicked.connect(self._pagar_cxp_ci)
        gl.addWidget(self.tbl_cxp_ci)
        gl.addWidget(bt_pagar_ci)
        sp.addWidget(grp)
        sp.setSizes([280, 220])
        root.addWidget(sp)
        return w

    # ═══════════════════════════════════════════════════════════════════════
    # LÓGICA DE CARGA — CONTROLES
    # ═══════════════════════════════════════════════════════════════════════

    def _dates(self):
        return (
            self._df.date().toString("yyyy-MM-dd"),
            self._dt.date().toString("yyyy-MM-dd"),
        )

    def _set_period(self, days):
        self._dt.setDate(QDate.currentDate())
        self._df.setDate(QDate.currentDate().addDays(-days + 1))
        self._on_tab(self.tabs.currentIndex())

    def _on_tab(self, idx):
        df, dt = self._dates()
        self._lbl_hdr.setText(
            f"Sucursal: {self.sucursal_nombre}  ·  {df} → {dt}"
        )
        loaders = [
            lambda _, _vd=d: self._load_dashboard(_vdf, dt),
            lambda: self._load_cxp(),
            lambda: self._load_cxc(),
            lambda: self._load_proveedores(),
            lambda _, _vd=d: self._load_gastos(_vdf, dt),
            lambda: self._load_personal(),
            lambda: self._load_activos(),
            lambda: self._load_compras_inv(),
        ]
        if 0 <= idx < len(loaders):
            try:
                loaders[idx]()
            except Exception as exc:
                logger.error("tab[%d]: %s", idx, exc)

    def showEvent(self, ev):
        super().showEvent(ev)
        self._on_tab(self.tabs.currentIndex())

    # ═══════════════════════════════════════════════════════════════════════
    # LOADERS
    # ═══════════════════════════════════════════════════════════════════════

    def _load_dashboard(self, df, dt):
        try:
            k = self._svc.dashboard_kpis(self.sucursal_id, df, dt)
            self.kpi_ingresos.set(f"${k['ingresos']:,.2f}")
            ub = k['utilidad_bruta']
            self.kpi_ut_bruta.set(
                f"${ub:,.2f}",
                sub=f"Margen bruto: {k['margen_bruto']:.1f}%",
                pos=ub > 0
            )
            un = k['utilidad_neta']
            self.kpi_ut_neta.set(
                f"${un:,.2f}", pos=un > 0
            )
            mn = k['margen_neto']
            self.kpi_margen.set(f"{mn:.1f}%", pos=mn > 0)
            self.kpi_gastos.set(f"${k['gastos']:,.2f}")
            self.kpi_nomina.set(f"${k['nomina']:,.2f}")
            cxp_sub = ""
            if k['cxp_vencidas']:
                cxp_sub = f"⚠ {k['cxp_vencidas']} vencidas"
            self.kpi_cxp.set(
                f"${k['cxp_total']:,.2f}",
                sub=cxp_sub or f"{k['cxp_count']} cuentas",
                pos=k['cxp_total'] == 0
            )
            self.kpi_cxc.set(
                f"${k['cxc_total']:,.2f}",
                sub=f"{k['cxc_count']} cuentas"
            )
        except Exception as exc:
            logger.error("dashboard_kpis: %s", exc)

        # Balance general
        try:
            bal = self._svc.balance_general(self.sucursal_id)
            rows = [
                ("ACTIVOS",     "Inventario",         bal["activos"]["corrientes"]["inventario"]),
                ("ACTIVOS",     "CXC (clientes)",     bal["activos"]["corrientes"]["cxc"]),
                ("ACTIVOS",     "Caja",                bal["activos"]["corrientes"]["caja"]),
                ("ACTIVOS",     "Activos Fijos",      bal["activos"]["no_corrientes"]["activos_fijos"]),
                ("ACTIVOS",     "TOTAL ACTIVOS",      bal["activos"]["total"]),
                ("PASIVOS",     "CXP (proveedores)",  bal["pasivos"]["corrientes"]["cxp"]),
                ("PASIVOS",     "Gastos Pendientes",  bal["pasivos"]["corrientes"]["gastos_pend"]),
                ("PASIVOS",     "TOTAL PASIVOS",      bal["pasivos"]["total"]),
                ("PATRIMONIO",  "Patrimonio Neto",    bal["patrimonio"]),
            ]
            self.tbl_balance.setRowCount(len(rows))
            for ri, (rubro, sub, monto) in enumerate(rows):
                is_total = "TOTAL" in sub or "PATRIMONIO" == rubro
                rc = _TEAL if rubro=="ACTIVOS" else (_RED if rubro=="PASIVOS" else _GREEN)
                mc = _GREEN if monto >= 0 else _RED
                self.tbl_balance.setItem(ri, 0, _it(rubro, color=rc, bold=is_total))
                self.tbl_balance.setItem(ri, 1, _it(sub, bold=is_total))
                self.tbl_balance.setItem(ri, 2,
                    _it(f"${monto:,.2f}", _R, mc, bold=is_total))
        except Exception as exc:
            logger.error("balance_general: %s", exc)

        # Flujo de caja
        try:
            fc = self._svc.flujo_caja(df, dt, self.sucursal_id)
            rows_fc = [
                ("ENTRADA", "Ventas",               fc["entradas"]["ventas"]),
                ("ENTRADA", "Cobros CXC",           fc["entradas"]["cobros_cxc"]),
                ("ENTRADA", "TOTAL ENTRADAS",       fc["entradas"]["total"]),
                ("SALIDA",  "Gastos Operativos",    fc["salidas"]["gastos"]),
                ("SALIDA",  "Pagos a Proveedores",  fc["salidas"]["pagos_prov"]),
                ("SALIDA",  "Nómina",               fc["salidas"]["nomina"]),
                ("SALIDA",  "TOTAL SALIDAS",        fc["salidas"]["total"]),
                ("NETO",    "FLUJO NETO",           fc["flujo_neto"]),
            ]
            self.tbl_flujo.setRowCount(len(rows_fc))
            for ri, (tipo, con, monto) in enumerate(rows_fc):
                is_total = "TOTAL" in con or "NETO" == tipo
                tc = _TEAL if tipo=="ENTRADA" else (_RED if tipo=="SALIDA" else _AMBER)
                mc = _GREEN if monto >= 0 else _RED
                self.tbl_flujo.setItem(ri, 0, _it(tipo, color=tc, bold=is_total))
                self.tbl_flujo.setItem(ri, 1, _it(con, bold=is_total))
                self.tbl_flujo.setItem(ri, 2,
                    _it(f"${monto:,.2f}", _R, mc, bold=is_total))
        except Exception as exc:
            logger.error("flujo_caja: %s", exc)

    def _load_cxp(self):
        estado_f = self._cxp_estado_f.currentText()
        estado_f = None if estado_f == "Todas" else estado_f
        try:
            rows = self._svc.cuentas_por_pagar(status_filter=estado_f)
            total_saldo = sum(float(r.get("balance",0)) for r in rows)
            vencidas = sum(1 for r in rows if r.get("aging") not in ("corriente",))
            self._lbl_cxp_resumen.setText(
                f"💸  Total pendiente: ${total_saldo:,.2f}  |  "
                f"{len(rows)} cuentas  |  {vencidas} con aging"
            )
            self.tbl_cxp.setRowCount(len(rows))
            for ri, r in enumerate(rows):
                saldo = float(r.get("balance",0))
                st = str(r.get("status",""))
                sc = _GREEN if st=="pagado" else (_AMBER if st=="parcial" else _RED)
                ag = str(r.get("aging",""))
                ac = _RED if ag != "corriente" else _TEAL
                cells = [
                    _it(str(r.get("id",""))),
                    _it(str(r.get("folio",""))),
                    _it(str(r.get("supplier_nombre","—"))),
                    _it(str(r.get("concepto",""))),
                    _it(f"${float(r.get('amount',0)):,.2f}", _R),
                    _it(f"${saldo:,.2f}", _R, _RED if saldo > 0 else _GREEN, bold=True),
                    _it(str(r.get("due_date","—"))[:10]),
                    _it(ag, color=ac, bold=True),
                    _it(st.capitalize(), color=sc, bold=True),
                ]
                for ci, it in enumerate(cells):
                    self.tbl_cxp.setItem(ri, ci, it)
                    if ci == 0: it.setData(Qt.UserRole, r.get("id"))
        except Exception as exc:
            logger.error("load_cxp: %s", exc)

    def _load_cxc(self):
        try:
            rows = self._svc.cuentas_por_cobrar()
            total_saldo = sum(float(r.get("balance",0)) for r in rows)
            self._lbl_cxc_resumen.setText(
                f"💰  Total por cobrar: ${total_saldo:,.2f}  |  {len(rows)} cuentas"
            )
            self.tbl_cxc.setRowCount(len(rows))
            for ri, r in enumerate(rows):
                saldo = float(r.get("balance",0))
                st = str(r.get("status",""))
                sc = _GREEN if st=="pagado" else (_AMBER if st=="parcial" else _RED)
                dv = int(r.get("dias_vencido",0))
                cells = [
                    _it(str(r.get("id",""))),
                    _it(str(r.get("folio",""))),
                    _it(str(r.get("cliente_nombre","—")).strip()),
                    _it(str(r.get("concepto",""))),
                    _it(f"${float(r.get('amount',0)):,.2f}", _R),
                    _it(f"${saldo:,.2f}", _R, _RED if saldo > 0 else _GREEN, bold=True),
                    _it(str(r.get("due_date","—"))[:10]),
                    _it(f"{dv}d" if dv > 0 else "—", color=_RED if dv > 0 else _TEAL),
                    _it(st.capitalize(), color=sc, bold=True),
                ]
                for ci, it in enumerate(cells):
                    self.tbl_cxc.setItem(ri, ci, it)
                    if ci == 0: it.setData(Qt.UserRole, r.get("id"))
        except Exception as exc:
            logger.error("load_cxc: %s", exc)

    def _load_proveedores(self):
        buscar = self._prov_buscar.text().strip() or None
        try:
            rows = self._svc.get_suppliers(buscar=buscar)
            self.tbl_prov.setRowCount(len(rows))
            for ri, r in enumerate(rows):
                saldo = float(r.get("saldo_total",0))
                cells = [
                    _it(str(r.get("id",""))),
                    _it(str(r.get("nombre",""))),
                    _it(str(r.get("rfc",""))),
                    _it(str(r.get("telefono",""))),
                    _it(str(r.get("tipo",""))),
                    _it(f"{r.get('condiciones_pago',0)}d", _R),
                    _it(f"${saldo:,.2f}", _R,
                        _RED if saldo > 0 else _TEAL, bold=saldo > 0),
                    _it(str(r.get("facturas_abiertas",0)), _R),
                ]
                for ci, it in enumerate(cells):
                    self.tbl_prov.setItem(ri, ci, it)
                    if ci == 0: it.setData(Qt.UserRole, dict(r))
        except Exception as exc:
            logger.error("load_prov: %s", exc)

    def _prov_sel(self):
        row = self.tbl_prov.currentRow()
        if row < 0: return
        it = self.tbl_prov.item(row, 0)
        if not it: return
        r = it.data(Qt.UserRole)
        if not r: return
        self._prov_detail.setPlainText(
            f"Nombre:        {r.get('nombre','')}\n"
            f"RFC:           {r.get('rfc','')}\n"
            f"Teléfono:      {r.get('telefono','')}\n"
            f"Email:         {r.get('email','')}\n"
            f"Dirección:     {r.get('direccion','')}\n"
            f"Tipo:          {r.get('tipo','')}\n"
            f"Crédito (días):{r.get('condiciones_pago',0)}\n"
            f"Límite créd.:  ${float(r.get('limite_credito',0)):,.2f}\n"
            f"Banco:         {r.get('banco','')}\n"
            f"Cuenta:        {r.get('cuenta_bancaria','')}\n"
            f"Contacto:      {r.get('contacto','')}\n"
            f"Notas:         {r.get('notas','')}\n"
        )
        # CXP de este proveedor
        try:
            cxps = self._svc.cuentas_por_pagar(supplier_id=r.get("id"))
            self.tbl_prov_cxp.setRowCount(len(cxps))
            for ri, c in enumerate(cxps):
                cells = [
                    _it(str(c.get("id",""))),
                    _it(str(c.get("concepto",""))),
                    _it(f"${float(c.get('amount',0)):,.2f}", _R),
                    _it(f"${float(c.get('balance',0)):,.2f}", _R, _RED),
                    _it(str(c.get("due_date","—"))[:10]),
                    _it(str(c.get("status","")).capitalize()),
                ]
                for ci, it in enumerate(cells):
                    self.tbl_prov_cxp.setItem(ri, ci, it)
        except Exception as exc:
            logger.error("prov_cxp: %s", exc)

    def _load_gastos(self, df, dt):
        try:
            data = self._svc.gastos_mes(df, dt)
            det  = data.get("detalle", [])
            self.tabla_gastos.setRowCount(len(det))
            for ri, r in enumerate(det):
                monto    = float(r.get("monto",0))
                pagado   = float(r.get("monto_pagado") or 0)
                pendiente = monto - pagado
                est = str(r.get("estado",""))
                ec  = _GREEN if est=="pagado" else (_AMBER if est=="parcial" else _RED)
                cells = [
                    _it(str(r.get("id",""))),
                    _it(str(r.get("fecha",""))[:10]),
                    _it(str(r.get("categoria",""))),
                    _it(str(r.get("concepto",""))),
                    _it(f"${monto:,.2f}", _R),
                    _it(f"${pagado:,.2f}", _R, _GREEN),
                    _it(f"${pendiente:,.2f}", _R,
                        _RED if pendiente > 0 else _TEAL),
                    _it(est.capitalize(), color=ec, bold=True),
                    _it(str(r.get("metodo_pago",""))),
                    _it("Sí" if r.get("recurrente") else "No"),
                    _it(str(r.get("usuario",""))),
                ]
                for ci, it in enumerate(cells):
                    self.tabla_gastos.setItem(ri, ci, it)
            # Resumen por categoría
            by_cat = data.get("by_categoria", [])
            self.tbl_gastos_cat.setRowCount(len(by_cat))
            for ri, r in enumerate(by_cat):
                cells = [
                    _it(str(r.get("categoria",""))),
                    _it(str(r.get("num_registros",0)), _R),
                    _it(f"${float(r.get('total',0)):,.2f}", _R, _RED),
                    _it(f"${float(r.get('pagado',0)):,.2f}", _R, _GREEN),
                    _it(f"${float(r.get('pendiente',0)):,.2f}", _R),
                ]
                for ci, it in enumerate(cells):
                    self.tbl_gastos_cat.setItem(ri, ci, it)
        except Exception as exc:
            logger.error("load_gastos: %s", exc)

    def _load_personal(self):
        estado_text = getattr(self, '_combo_filtro_personal',
                              None) and self._combo_filtro_personal.currentText()
        activo = None
        if estado_text == "Activos": activo = 1
        elif estado_text == "Inactivos": activo = 0
        try:
            rows = self._svc.get_personal(activo=activo)
            self.tabla_personal.setRowCount(len(rows))
            for ri, r in enumerate(rows):
                est = 1 if r.get("activo",1) else 0
                cells = [
                    _it(str(r.get("id",""))),
                    _it(str(r.get("nombre",""))),
                    _it(str(r.get("apellidos",""))),
                    _it(str(r.get("puesto",""))),
                    _it(f"${float(r.get('salario',0)):,.2f}", _R),
                    _it(str(r.get("fecha_ingreso",""))[:10]),
                    _it("Activo" if est else "Inactivo",
                        color=_GREEN if est else _RED),
                    _it(f"${float(r.get('total_pagado',0)):,.2f}", _R, _AMBER),
                ]
                for ci, it in enumerate(cells):
                    self.tabla_personal.setItem(ri, ci, it)
                    if ci == 0: it.setData(Qt.UserRole, r.get("id"))
        except Exception as exc:
            logger.error("load_personal: %s", exc)

        self._load_nomina()

    def _load_nomina(self, emp_id=None):
        try:
            df, dt = self._dates()
            rows = self._svc.get_nomina_pagos(
                empleado_id=emp_id, date_from=df, date_to=dt, limit=50
            )
            self.tbl_nomina.setRowCount(len(rows))
            for ri, r in enumerate(rows):
                cells = [
                    _it(str(r.get("id",""))),
                    _it(str(r.get("empleado_nombre","")).strip()),
                    _it(str(r.get("puesto",""))),
                    _it(f"{str(r.get('periodo_inicio',''))[:10]} → {str(r.get('periodo_fin',''))[:10]}"),
                    _it(f"${float(r.get('salario_base',0)):,.2f}", _R),
                    _it(f"${float(r.get('bonos',0)):,.2f}", _R, _GREEN),
                    _it(f"${float(r.get('deducciones',0)):,.2f}", _R, _RED),
                    _it(f"${float(r.get('total',0)):,.2f}", _R, _AMBER, bold=True),
                    _it(str(r.get("metodo_pago",""))),
                    _it(str(r.get("created_at",""))[:16]),
                ]
                for ci, it in enumerate(cells):
                    self.tbl_nomina.setItem(ri, ci, it)
        except Exception as exc:
            logger.error("load_nomina: %s", exc)

    def _load_activos(self):
        tipo_f = self._act_tipo_f.currentText()
        tipo_f = None if tipo_f == "Todos" else tipo_f
        try:
            rows = self._svc.get_assets(tipo=tipo_f)
            self.tbl_activos.setRowCount(len(rows))
            for ri, r in enumerate(rows):
                est = str(r.get("estado",""))
                ec  = _GREEN if est=="activo" else (_AMBER if est=="mantenimiento" else _RED)
                cells = [
                    _it(str(r.get("id",""))),
                    _it(str(r.get("codigo",""))),
                    _it(str(r.get("nombre",""))),
                    _it(str(r.get("tipo",""))),
                    _it(str(r.get("marca",""))),
                    _it(f"${float(r.get('valor_compra',0)):,.2f}", _R),
                    _it(f"${float(r.get('valor_actual',0)):,.2f}", _R, _BLUE),
                    _it(est.capitalize(), color=ec, bold=True),
                    _it(str(r.get("ubicacion",""))),
                    _it(str(r.get("num_mant",0)), _R),
                    _it(f"${float(r.get('costo_mant',0)):,.2f}", _R),
                ]
                for ci, it in enumerate(cells):
                    self.tbl_activos.setItem(ri, ci, it)
                    if ci == 0: it.setData(Qt.UserRole, r.get("id"))
        except Exception as exc:
            logger.error("load_activos: %s", exc)
        self._load_mantenimientos()

    def _act_sel(self):
        row = self.tbl_activos.currentRow()
        if row < 0: return
        it = self.tbl_activos.item(row, 0)
        aid = it.data(Qt.UserRole) if it else None
        if aid: self._load_mantenimientos(aid)

    def _load_mantenimientos(self, asset_id=None):
        try:
            rows = self._svc.get_maintenance(asset_id=asset_id)
            self.tbl_mant.setRowCount(len(rows))
            for ri, r in enumerate(rows):
                tc = _ORANGE if r.get("tipo")=="correctivo" else _BLUE
                cells = [
                    _it(str(r.get("id",""))),
                    _it(str(r.get("activo_nombre",""))),
                    _it(str(r.get("tipo","")).capitalize(), color=tc),
                    _it(str(r.get("fecha",""))[:10]),
                    _it(str(r.get("descripcion",""))),
                    _it(f"${float(r.get('costo',0)):,.2f}", _R, _RED),
                    _it(str(r.get("responsable",""))),
                    _it(str(r.get("estado","")).capitalize()),
                    _it(str(r.get("proxima_revision",""))[:10]),
                ]
                for ci, it in enumerate(cells):
                    self.tbl_mant.setItem(ri, ci, it)
        except Exception as exc:
            logger.error("load_mant: %s", exc)

    def _load_compras_inv(self):
        try:
            rows = self.conexion.execute("""
                SELECT ci.id, COALESCE(p.nombre,'?') AS producto,
                       ci.proveedor, ci.volumen, ci.unidad, ci.costo_unitario,
                       ci.costo_total, ci.monto_pagado, ci.saldo_pendiente,
                       ci.estado, ci.fecha
                FROM compras_inventariables ci
                LEFT JOIN productos p ON p.id = ci.producto_id
                ORDER BY ci.fecha DESC LIMIT 200
            """).fetchall()
            self.tbl_compras_inv.setRowCount(len(rows))
            for ri, r in enumerate(rows):
                sp = float(r[8] or 0)
                sc = _RED if sp > 0 else _TEAL
                cells = [
                    _it(str(r[0])),
                    _it(str(r[1])),
                    _it(str(r[2] or "")),
                    _it(f"{float(r[3] or 0):,.3f}", _R),
                    _it(str(r[4] or "")),
                    _it(f"${float(r[5] or 0):,.4f}", _R),
                    _it(f"${float(r[6] or 0):,.2f}", _R),
                    _it(f"${float(r[7] or 0):,.2f}", _R, _GREEN),
                    _it(f"${sp:,.2f}", _R, sc, bold=sp > 0),
                    _it(str(r[9] or "")),
                    _it(str(r[10] or "")[:16]),
                ]
                for ci, it in enumerate(cells):
                    self.tbl_compras_inv.setItem(ri, ci, it)
        except Exception as exc:
            logger.error("load_compras_inv: %s", exc)

        # CXP de compras inventariables
        try:
            from core.services.compras_inventariables_engine import ComprasInventariablesEngine
            eng = ComprasInventariablesEngine(
                self.conexion, self.sucursal_id, self.usuario_actual or "admin"
            )
            cxps = eng.cuentas_por_pagar()
            total_s = sum(c.saldo_pendiente for c in cxps)
            self._lbl_cxp_ci_total.setText(
                f"Total pendiente: ${total_s:,.2f}  |  {len(cxps)} cuentas"
            )
            self.tbl_cxp_ci.setRowCount(len(cxps))
            for ri, c in enumerate(cxps):
                cells = [
                    _it(str(c.id)),
                    _it(c.proveedor),
                    _it(c.producto_nombre),
                    _it(f"${c.monto_total:,.2f}", _R),
                    _it(f"${c.monto_pagado:,.2f}", _R, _GREEN),
                    _it(f"${c.saldo_pendiente:,.2f}", _R, _RED, bold=True),
                    _it(str(c.fecha_vencimiento or "—")[:10]),
                    _it(c.estado.capitalize()),
                ]
                for ci, it in enumerate(cells):
                    self.tbl_cxp_ci.setItem(ri, ci, it)
                    if ci == 0: it.setData(Qt.UserRole, c.id)
        except Exception as exc:
            logger.error("load_cxp_ci: %s", exc)

    # ═══════════════════════════════════════════════════════════════════════
    # ACCIONES — CXP
    # ═══════════════════════════════════════════════════════════════════════

    def _nueva_cxp(self):
        dlg = _DlgNuevaCXP(self.conexion, self.usuario_actual, self)
        if dlg.exec_() == QDialog.Accepted:
            d = dlg.data()
            try:
                self._svc.crear_cxp(**d)
                self._load_cxp()
                QMessageBox.information(self, "CXP", "Cuenta por pagar creada.")
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))

    def _abonar_cxp(self):
        row = self.tbl_cxp.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Seleccione una CXP.")
            return
        ap_id = self.tbl_cxp.item(row, 0).data(Qt.UserRole)
        saldo_str = self.tbl_cxp.item(row, 5).text().replace("$","").replace(",","")
        try: saldo = float(saldo_str)
        except: saldo = 0
        dlg = _DlgAbono(f"Abonar CXP #{ap_id}", saldo, self)
        if dlg.exec_() == QDialog.Accepted:
            monto, metodo = dlg.values()
            try:
                r = self._svc.abonar_cxp(ap_id, monto, metodo, self.usuario_actual)
                self._load_cxp()
                QMessageBox.information(
                    self, "Abono registrado",
                    f"Pago ${monto:,.2f} aplicado.\n"
                    f"Nuevo saldo: ${r['nuevo_balance']:,.2f}  •  {r['nuevo_status']}"
                )
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))

    def _historial_cxp(self):
        row = self.tbl_cxp.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Seleccione una CXP.")
            return
        ap_id = self.tbl_cxp.item(row, 0).data(Qt.UserRole)
        try:
            hist = self._svc.historial_pagos_cxp(ap_id)
            msg = f"Historial de pagos — CXP #{ap_id}\n\n"
            if hist:
                for h in hist:
                    msg += f"• {str(h.get('fecha',''))[:16]}  ${float(h.get('monto',0)):,.2f}  {h.get('metodo_pago','')}  {h.get('usuario','')}\n"
            else:
                msg += "(Sin pagos registrados)"
            QMessageBox.information(self, "Historial CXP", msg)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    # ═══════════════════════════════════════════════════════════════════════
    # ACCIONES — CXC
    # ═══════════════════════════════════════════════════════════════════════

    def _nueva_cxc(self):
        dlg = _DlgNuevaCXC(self.conexion, self.usuario_actual, self)
        if dlg.exec_() == QDialog.Accepted:
            d = dlg.data()
            try:
                self._svc.crear_cxc(**d)
                self._load_cxc()
                QMessageBox.information(self, "CXC", "Cuenta por cobrar creada.")
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))

    def _cobrar_cxc(self):
        row = self.tbl_cxc.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Seleccione una CXC.")
            return
        ar_id = self.tbl_cxc.item(row, 0).data(Qt.UserRole)
        saldo_str = self.tbl_cxc.item(row, 5).text().replace("$","").replace(",","")
        try: saldo = float(saldo_str)
        except: saldo = 0
        dlg = _DlgAbono(f"Cobrar CXC #{ar_id}", saldo, self)
        if dlg.exec_() == QDialog.Accepted:
            monto, metodo = dlg.values()
            try:
                r = self._svc.cobrar_cxc(ar_id, monto, metodo, self.usuario_actual)
                self._load_cxc()
                QMessageBox.information(
                    self, "Cobro registrado",
                    f"Cobro ${monto:,.2f} aplicado.\nNuevo saldo: ${r['nuevo_balance']:,.2f}"
                )
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))

    # ═══════════════════════════════════════════════════════════════════════
    # ACCIONES — PROVEEDORES
    # ═══════════════════════════════════════════════════════════════════════

    def _nuevo_proveedor(self):
        dlg = _DlgProveedor(self)
        if dlg.exec_() == QDialog.Accepted:
            try:
                self._svc.upsert_supplier(dlg.data())
                self._load_proveedores()
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))

    def _editar_proveedor(self):
        row = self.tbl_prov.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Seleccione un proveedor.")
            return
        it = self.tbl_prov.item(row, 0)
        if not it: return
        data = it.data(Qt.UserRole)
        dlg = _DlgProveedor(self, data=data)
        if dlg.exec_() == QDialog.Accepted:
            try:
                self._svc.upsert_supplier(dlg.data())
                self._load_proveedores()
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))

    # ═══════════════════════════════════════════════════════════════════════
    # ACCIONES — GASTOS (lógica legacy preservada)
    # ═══════════════════════════════════════════════════════════════════════

    def filtrar_gastos(self):
        df, dt = self._dates()
        self._load_gastos(df, dt)

    def cargar_gastos(self, consulta=None, parametros=None):
        df, dt = self._dates()
        self._load_gastos(df, dt)

    def nuevo_gasto(self):
        dlg = DialogoGasto(self.conexion, self.usuario_actual, self)
        if dlg.exec_() == QDialog.Accepted:
            self.filtrar_gastos()

    def editar_gasto(self):
        row = self.tabla_gastos.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Seleccione un gasto.")
            return
        gid = self.tabla_gastos.item(row, 0).text()
        try:
            cur = self.conexion.execute("SELECT * FROM gastos WHERE id=?", (gid,))
            row_data = cur.fetchone()
            if row_data:
                cols = [d[0] for d in cur.description]
                gdata = dict(zip(cols, row_data))
                dlg = DialogoGasto(self.conexion, self.usuario_actual, self, gdata)
                if dlg.exec_() == QDialog.Accepted:
                    self.filtrar_gastos()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def eliminar_gasto(self):
        row = self.tabla_gastos.currentRow()
        if row < 0: return
        gid = self.tabla_gastos.item(row, 0).text()
        if QMessageBox.question(
            self, "Confirmar",
            f"¿Eliminar gasto #{gid}? (se marcará inactivo)",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            try:
                self.conexion.execute(
                    "UPDATE gastos SET activo=0 WHERE id=?", (gid,)
                )
                self.conexion.commit()
                try:
                    _ctr = getattr(self,"container",None)
                    if _ctr: audit_write(_ctr,modulo="FINANZAS",accion="REGISTRO_FINANCIERO",entidad="finanzas",usuario=getattr(self,"usuario_actual","Sistema"),detalles="Registro financiero guardado",sucursal_id=getattr(self,"sucursal_id",1))
                except Exception: pass
                self.filtrar_gastos()
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))

    def abonar_gasto(self):
        row = self.tabla_gastos.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Seleccione un gasto.")
            return
        gid = self.tabla_gastos.item(row, 0).text()
        monto_str  = self.tabla_gastos.item(row, 4).text().replace("$","").replace(",","")
        pagado_str = self.tabla_gastos.item(row, 5).text().replace("$","").replace(",","")
        try:
            monto  = float(monto_str)
            pagado = float(pagado_str)
        except: return
        pendiente = max(0, monto - pagado)
        dlg = _DlgAbono(f"Abonar a Gasto #{gid}", pendiente, self)
        if dlg.exec_() == QDialog.Accepted:
            abono, _ = dlg.values()
            try:
                nuevo_pagado = pagado + abono
                nuevo_estado = "pagado" if nuevo_pagado >= monto else "parcial"
                self.conexion.execute("""
                    UPDATE gastos SET monto_pagado=?, estado=? WHERE id=?
                """, (nuevo_pagado, nuevo_estado, gid))
                self.conexion.commit()
                self.filtrar_gastos()
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))

    def actualizar_botones_gastos(self):
        ok = len(self.tabla_gastos.selectedItems()) > 0
        self.btn_editar_gasto.setEnabled(ok)
        self.btn_eliminar_gasto.setEnabled(ok)
        self.btn_abonar_gasto.setEnabled(ok)

    def notificar_actualizacion_gastos(self):
        self.filtrar_gastos()

    # ═══════════════════════════════════════════════════════════════════════
    # ACCIONES — PERSONAL (legacy preservado)
    # ═══════════════════════════════════════════════════════════════════════

    @property
    def combo_filtro_estado(self):
        return getattr(self, '_combo_filtro_personal', None)

    @combo_filtro_estado.setter
    def combo_filtro_estado(self, v):
        self._combo_filtro_personal_ext = v

    def cargar_personal(self):
        self._load_personal()

    def buscar_personal(self):
        buscar = self.busqueda_personal.text().strip() or None
        estado_text = self._combo_filtro_personal.currentText()
        activo = None
        if estado_text == "Activos": activo = 1
        elif estado_text == "Inactivos": activo = 0
        try:
            rows = self._svc.get_personal(activo=activo, buscar=buscar)
            self.tabla_personal.setRowCount(len(rows))
            for ri, r in enumerate(rows):
                est = 1 if r.get("activo", 1) else 0
                cells = [
                    _it(str(r.get("id",""))),
                    _it(str(r.get("nombre",""))),
                    _it(str(r.get("apellidos",""))),
                    _it(str(r.get("puesto",""))),
                    _it(f"${float(r.get('salario',0)):,.2f}", _R),
                    _it(str(r.get("fecha_ingreso",""))[:10]),
                    _it("Activo" if est else "Inactivo",
                        color=_GREEN if est else _RED),
                    _it(f"${float(r.get('total_pagado',0)):,.2f}", _R),
                ]
                for ci, it in enumerate(cells):
                    self.tabla_personal.setItem(ri, ci, it)
                    if ci == 0: it.setData(Qt.UserRole, r.get("id"))
        except Exception as exc:
            logger.error("buscar_personal: %s", exc)

    def nuevo_empleado(self):
        dlg = DialogoEmpleado(self.conexion, self)
        if dlg.exec_() == QDialog.Accepted:
            self._load_personal()

    def editar_empleado(self):
        row = self.tabla_personal.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Seleccione un empleado.")
            return
        eid = self.tabla_personal.item(row, 0).data(Qt.UserRole)
        try:
            cur = self.conexion.execute("SELECT * FROM personal WHERE id=?", (eid,))
            data = cur.fetchone()
            if data:
                cols = [d[0] for d in cur.description]
                dlg = DialogoEmpleado(self.conexion, self, dict(zip(cols, data)))
                if dlg.exec_() == QDialog.Accepted:
                    self._load_personal()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def eliminar_empleado(self):
        row = self.tabla_personal.currentRow()
        if row < 0: return
        eid = self.tabla_personal.item(row, 0).data(Qt.UserRole)
        if QMessageBox.question(
            self, "Confirmar", "¿Desactivar este empleado?",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            try:
                self.conexion.execute(
                    "UPDATE personal SET activo=0 WHERE id=?", (eid,)
                )
                self.conexion.commit()
                self._load_personal()
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))

    def actualizar_botones_personal(self):
        ok = len(self.tabla_personal.selectedItems()) > 0
        self.btn_editar_empleado.setEnabled(ok)
        self.btn_eliminar_empleado.setEnabled(ok)

    def _pagar_nomina(self):
        row = self.tabla_personal.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Seleccione un empleado.")
            return
        eid = self.tabla_personal.item(row, 0).data(Qt.UserRole)
        sal_str = self.tabla_personal.item(row, 4).text().replace("$","").replace(",","")
        try: sal = float(sal_str)
        except: sal = 0
        dlg = _DlgNomina(eid, sal, self)
        if dlg.exec_() == QDialog.Accepted:
            d = dlg.data()
            try:
                self._svc.pagar_nomina(**d, usuario=self.usuario_actual)
                self._load_nomina()
                QMessageBox.information(self, "Nómina", f"Pago registrado: ${d['salario_base']:,.2f}")
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))

    def _historial_nomina(self):
        row = self.tabla_personal.currentRow()
        eid = None
        if row >= 0 and self.tabla_personal.item(row, 0):
            eid = self.tabla_personal.item(row, 0).data(Qt.UserRole)
        self._load_nomina(eid)

    # ═══════════════════════════════════════════════════════════════════════
    # ACCIONES — ACTIVOS
    # ═══════════════════════════════════════════════════════════════════════

    def _nuevo_activo(self):
        dlg = _DlgActivo(self.conexion, self)
        if dlg.exec_() == QDialog.Accepted:
            try:
                self._svc.upsert_asset(dlg.data())
                self._load_activos()
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))

    def _nuevo_mantenimiento(self):
        row = self.tbl_activos.currentRow()
        asset_id = None
        if row >= 0 and self.tbl_activos.item(row, 0):
            asset_id = self.tbl_activos.item(row, 0).data(Qt.UserRole)
        dlg = _DlgMantenimiento(self.conexion, asset_id, self)
        if dlg.exec_() == QDialog.Accepted:
            try:
                self._svc.registrar_mantenimiento(dlg.data())
                self._load_activos()
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))

    # ═══════════════════════════════════════════════════════════════════════
    # ACCIONES — COMPRAS INV. (legacy preservado)
    # ═══════════════════════════════════════════════════════════════════════

    def _nueva_compra_inv(self):
        dlg = _DialogoCompraInventariable(
            self.conexion, self.usuario_actual or "admin", self
        )
        if dlg.exec_() == QDialog.Accepted:
            self._load_compras_inv()
            self._sync_all()

    def _pagar_cxp_ci(self):
        row = self.tbl_cxp_ci.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Seleccione una cuenta.")
            return
        cxp_id = self.tbl_cxp_ci.item(row, 0).data(Qt.UserRole)
        saldo_str = self.tbl_cxp_ci.item(row, 5).text().replace("$","").replace(",","")
        try: saldo = float(saldo_str)
        except: saldo = 0
        dlg = _DlgAbono(f"Pagar CXP #{cxp_id}", saldo, self)
        if dlg.exec_() == QDialog.Accepted:
            monto, _ = dlg.values()
            try:
                from core.services.compras_inventariables_engine import ComprasInventariablesEngine
                eng = ComprasInventariablesEngine(
                    self.conexion, self.sucursal_id, self.usuario_actual or "admin"
                )
                r = eng.registrar_pago_cxp(cxp_id, monto)
                self._load_compras_inv()
                QMessageBox.information(
                    self, "Pago registrado",
                    f"Pago ${monto:,.2f} aplicado.\n"
                    f"Nuevo saldo: ${r.get('nuevo_saldo',0):,.2f}"
                )
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))

    # ── legacy helpers ─────────────────────────────────────────────────────

    def mostrar_mensaje(self, titulo, msg, tipo=None, btns=None):
        if tipo == QMessageBox.Critical:
            QMessageBox.critical(self, titulo, msg)
        elif tipo == QMessageBox.Question and btns:
            return QMessageBox.question(self, titulo, msg, btns)
        else:
            QMessageBox.information(self, titulo, msg)

    def actualizar_datos(self):
        self._on_tab(self.tabs.currentIndex())

    def on_venta_realizada(self, datos):
        QTimer.singleShot(2000, self._sync_and_refresh)

    def on_datos_actualizados(self, _):
        QTimer.singleShot(0, self.actualizar_datos)

    def conectar_eventos(self): pass
    def desconectar_eventos(self): pass


# ═════════════════════════════════════════════════════════════════════════════
# DIÁLOGOS RÁPIDOS NUEVOS
# ═════════════════════════════════════════════════════════════════════════════

class _DlgAbono(QDialog):
    """Diálogo genérico para registrar un abono/cobro."""
    def __init__(self, titulo, saldo, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setMinimumWidth(340)
        self.setModal(True)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self._spin = QDoubleSpinBox()
        self._spin.setDecimals(2)
        self._spin.setRange(0.01, max(saldo, 0.01))
        self._spin.setValue(saldo)
        self._spin.setPrefix("$")
        form.addRow(f"Monto (saldo: ${saldo:,.2f}):", self._spin)
        self._combo = QComboBox()
        self._combo.addItems(["efectivo","transferencia","cheque","tarjeta"])
        form.addRow("Método de pago:", self._combo)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def values(self):
        return self._spin.value(), self._combo.currentText()


class _DlgNuevaCXP(QDialog):
    def __init__(self, conexion, usuario, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nueva Cuenta por Pagar")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._usuario = usuario
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self._combo_sup = QComboBox()
        self._combo_sup.addItem("— Sin proveedor —", None)
        try:
            rows = conexion.execute(
                "SELECT id, nombre FROM suppliers WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            for r in rows:
                self._combo_sup.addItem(r[1], r[0])
        except Exception:
            pass
        form.addRow("Proveedor:", self._combo_sup)
        self._concepto = QLineEdit(); self._concepto.setPlaceholderText("Factura, servicio…")
        form.addRow("Concepto *:", self._concepto)
        self._monto = QDoubleSpinBox()
        self._monto.setDecimals(2); self._monto.setRange(0.01,9999999)
        self._monto.setPrefix("$")
        form.addRow("Monto *:", self._monto)
        self._vence = QDateEdit(QDate.currentDate().addDays(30))
        self._vence.setCalendarPopup(True)
        form.addRow("Vencimiento:", self._vence)
        self._tipo = QComboBox()
        self._tipo.addItems(["factura","servicio","renta","otro"])
        form.addRow("Tipo:", self._tipo)
        self._notas = QLineEdit()
        form.addRow("Notas:", self._notas)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def data(self):
        return {
            "supplier_id": self._combo_sup.currentData(),
            "concepto":    self._concepto.text() or "Sin concepto",
            "amount":      self._monto.value(),
            "due_date":    self._vence.date().toString("yyyy-MM-dd"),
            "tipo":        self._tipo.currentText(),
            "usuario":     self._usuario,
            "notas":       self._notas.text() or None,
        }


class _DlgNuevaCXC(QDialog):
    def __init__(self, conexion, usuario, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nueva Cuenta por Cobrar")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._usuario = usuario
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self._combo_cli = QComboBox()
        self._combo_cli.addItem("— Sin cliente —", None)
        try:
            rows = conexion.execute(
                "SELECT id, nombre||' '||COALESCE(apellido_paterno,'') "
                "FROM clientes WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            for r in rows:
                self._combo_cli.addItem(r[1].strip(), r[0])
        except Exception:
            pass
        form.addRow("Cliente:", self._combo_cli)
        self._concepto = QLineEdit()
        form.addRow("Concepto *:", self._concepto)
        self._monto = QDoubleSpinBox()
        self._monto.setDecimals(2); self._monto.setRange(0.01, 9999999)
        self._monto.setPrefix("$")
        form.addRow("Monto *:", self._monto)
        self._vence = QDateEdit(QDate.currentDate().addDays(30))
        self._vence.setCalendarPopup(True)
        form.addRow("Vencimiento:", self._vence)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def data(self):
        return {
            "cliente_id": self._combo_cli.currentData(),
            "concepto":   self._concepto.text() or "Sin concepto",
            "amount":     self._monto.value(),
            "due_date":   self._vence.date().toString("yyyy-MM-dd"),
            "usuario":    self._usuario,
        }


class _DlgProveedor(QDialog):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.setWindowTitle("Proveedor" + (" — Editar" if data else " — Nuevo"))
        self.setMinimumWidth(460)
        self.setModal(True)
        self._id = (data or {}).get("id")
        lay = QVBoxLayout(self)
        form = QFormLayout()

        def _le(ph=""):
            e = QLineEdit(); e.setPlaceholderText(ph); return e

        self._nombre = _le("Nombre del proveedor")
        self._rfc = _le("RFC")
        self._tel  = _le("Teléfono")
        self._email = _le("Email")
        self._dir  = _le("Dirección")
        self._tipo = QComboBox()
        self._tipo.addItems(["general","carnico","abarrotes","servicios","transporte"])
        self._dias_cred = QSpinBox()
        self._dias_cred.setRange(0,365); self._dias_cred.setValue(30)
        self._lim_cred = QDoubleSpinBox()
        self._lim_cred.setDecimals(2); self._lim_cred.setRange(0,9999999)
        self._lim_cred.setPrefix("$")
        self._banco = _le("Banco")
        self._cuenta = _le("Número de cuenta")
        self._contacto = _le("Nombre contacto")
        self._notas = QLineEdit()

        for lb, w in [
            ("Nombre *:", self._nombre), ("RFC:", self._rfc),
            ("Teléfono:", self._tel), ("Email:", self._email),
            ("Dirección:", self._dir), ("Tipo:", self._tipo),
            ("Crédito días:", self._dias_cred), ("Límite crédito:", self._lim_cred),
            ("Banco:", self._banco), ("Cuenta:", self._cuenta),
            ("Contacto:", self._contacto), ("Notas:", self._notas),
        ]:
            form.addRow(lb, w)
        lay.addLayout(form)

        if data:
            self._nombre.setText(str(data.get("nombre","")))
            self._rfc.setText(str(data.get("rfc","")))
            self._tel.setText(str(data.get("telefono","")))
            self._email.setText(str(data.get("email","")))
            self._dir.setText(str(data.get("direccion","")))
            idx = self._tipo.findText(str(data.get("tipo","general")))
            if idx >= 0: self._tipo.setCurrentIndex(idx)
            self._dias_cred.setValue(int(data.get("condiciones_pago",30) or 30))
            self._lim_cred.setValue(float(data.get("limite_credito",0) or 0))
            self._banco.setText(str(data.get("banco","")))
            self._cuenta.setText(str(data.get("cuenta_bancaria","")))
            self._contacto.setText(str(data.get("contacto","")))
            self._notas.setText(str(data.get("notas","")))

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def data(self):
        d = {
            "nombre": self._nombre.text(),
            "rfc": self._rfc.text(), "telefono": self._tel.text(),
            "email": self._email.text(), "direccion": self._dir.text(),
            "tipo": self._tipo.currentText(),
            "condiciones_pago": self._dias_cred.value(),
            "limite_credito": self._lim_cred.value(),
            "banco": self._banco.text(), "cuenta_bancaria": self._cuenta.text(),
            "contacto": self._contacto.text(), "notas": self._notas.text(),
            "activo": 1,
        }
        if self._id: d["id"] = self._id
        return d


class _DlgActivo(QDialog):
    def __init__(self, conexion, parent=None, data=None):
        super().__init__(parent)
        self.setWindowTitle("Activo Fijo — " + ("Editar" if data else "Nuevo"))
        self.setMinimumWidth(440)
        self.setModal(True)
        self._id = (data or {}).get("id")
        lay = QVBoxLayout(self)
        form = QFormLayout()

        self._nombre = QLineEdit()
        self._tipo = QComboBox()
        self._tipo.addItems(["vehiculo","equipo_pos","refrigerador",
                              "bascula","mobiliario","otro"])
        self._marca = QLineEdit()
        self._modelo = QLineEdit()
        self._serie = QLineEdit()
        self._fecha = QDateEdit(QDate.currentDate())
        self._fecha.setCalendarPopup(True)
        self._valor_c = QDoubleSpinBox()
        self._valor_c.setDecimals(2); self._valor_c.setRange(0,9999999)
        self._valor_c.setPrefix("$")
        self._depr = QDoubleSpinBox()
        self._depr.setDecimals(2); self._depr.setRange(0,100)
        self._depr.setSuffix("%/año")
        self._estado = QComboBox()
        self._estado.addItems(["activo","mantenimiento","dado_baja"])
        self._ubicacion = QLineEdit()
        self._responsable = QLineEdit()
        self._notas = QLineEdit()

        for lb, w in [
            ("Nombre *:", self._nombre), ("Tipo:", self._tipo),
            ("Marca:", self._marca), ("Modelo:", self._modelo),
            ("No. Serie:", self._serie), ("Fecha compra:", self._fecha),
            ("Valor compra:", self._valor_c), ("Depreciación anual:", self._depr),
            ("Estado:", self._estado), ("Ubicación:", self._ubicacion),
            ("Responsable:", self._responsable), ("Notas:", self._notas),
        ]:
            form.addRow(lb, w)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def data(self):
        d = {
            "nombre": self._nombre.text(),
            "tipo": self._tipo.currentText(),
            "marca": self._marca.text(), "modelo": self._modelo.text(),
            "numero_serie": self._serie.text(),
            "fecha_compra": self._fecha.date().toString("yyyy-MM-dd"),
            "valor_compra": self._valor_c.value(),
            "valor_actual": self._valor_c.value(),
            "depreciacion_anual": self._depr.value(),
            "estado": self._estado.currentText(),
            "ubicacion": self._ubicacion.text(),
            "responsable": self._responsable.text(),
            "notas": self._notas.text(),
        }
        if self._id: d["id"] = self._id
        return d


class _DlgMantenimiento(QDialog):
    def __init__(self, conexion, asset_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Registro de Mantenimiento")
        self.setMinimumWidth(420)
        self.setModal(True)
        lay = QVBoxLayout(self)
        form = QFormLayout()

        self._combo_act = QComboBox()
        try:
            rows = conexion.execute(
                "SELECT id, nombre FROM assets WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            for r in rows:
                self._combo_act.addItem(f"{r[1]}", r[0])
            if asset_id:
                idx = self._combo_act.findData(asset_id)
                if idx >= 0: self._combo_act.setCurrentIndex(idx)
        except Exception:
            pass
        form.addRow("Activo *:", self._combo_act)

        self._tipo = QComboBox()
        self._tipo.addItems(["preventivo","correctivo","revision","garantia"])
        form.addRow("Tipo:", self._tipo)

        self._fecha = QDateEdit(QDate.currentDate())
        self._fecha.setCalendarPopup(True)
        form.addRow("Fecha:", self._fecha)

        self._desc = QLineEdit()
        form.addRow("Descripción *:", self._desc)

        self._costo = QDoubleSpinBox()
        self._costo.setDecimals(2); self._costo.setRange(0,999999)
        self._costo.setPrefix("$")
        form.addRow("Costo:", self._costo)

        self._resp = QLineEdit()
        form.addRow("Responsable:", self._resp)

        self._prox = QDateEdit(QDate.currentDate().addMonths(3))
        self._prox.setCalendarPopup(True)
        form.addRow("Próxima revisión:", self._prox)

        self._notas = QLineEdit()
        form.addRow("Notas:", self._notas)

        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def data(self):
        return {
            "asset_id":        self._combo_act.currentData(),
            "tipo":            self._tipo.currentText(),
            "fecha":           self._fecha.date().toString("yyyy-MM-dd"),
            "descripcion":     self._desc.text(),
            "costo":           self._costo.value(),
            "responsable":     self._resp.text(),
            "estado":          "completado",
            "proxima_revision": self._prox.date().toString("yyyy-MM-dd"),
            "notas":           self._notas.text(),
        }


class _DlgNomina(QDialog):
    def __init__(self, empleado_id, salario_base, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pago de Nómina")
        self.setMinimumWidth(380)
        self.setModal(True)
        self._eid = empleado_id
        lay = QVBoxLayout(self)
        form = QFormLayout()

        today = QDate.currentDate()
        self._pi = QDateEdit(today.addDays(-14))
        self._pi.setCalendarPopup(True)
        form.addRow("Período inicio:", self._pi)

        self._pf = QDateEdit(today)
        self._pf.setCalendarPopup(True)
        form.addRow("Período fin:", self._pf)

        self._sal = QDoubleSpinBox()
        self._sal.setDecimals(2); self._sal.setRange(0,999999)
        self._sal.setValue(salario_base); self._sal.setPrefix("$")
        form.addRow("Salario:", self._sal)

        self._bon = QDoubleSpinBox()
        self._bon.setDecimals(2); self._bon.setRange(0,999999)
        self._bon.setPrefix("$")
        form.addRow("Bonos:", self._bon)

        self._ded = QDoubleSpinBox()
        self._ded.setDecimals(2); self._ded.setRange(0,999999)
        self._ded.setPrefix("$")
        form.addRow("Deducciones:", self._ded)

        self._metodo = QComboBox()
        self._metodo.addItems(["efectivo","transferencia","cheque"])
        form.addRow("Método:", self._metodo)

        self._notas = QLineEdit()
        form.addRow("Notas:", self._notas)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def data(self):
        return {
            "empleado_id":    self._eid,
            "periodo_inicio": self._pi.date().toString("yyyy-MM-dd"),
            "periodo_fin":    self._pf.date().toString("yyyy-MM-dd"),
            "salario_base":   self._sal.value(),
            "bonos":          self._bon.value(),
            "deducciones":    self._ded.value(),
            "metodo_pago":    self._metodo.currentText(),
            "notas":          self._notas.text() or None,
        }


class _DialogoCompraInventariable(QDialog):
    """
    Registro de compra inventariable:
    - Selección producto
    - Volumen, costo unitario
    - Proveedor, forma de pago, crédito/parcial
    Al aceptar: crea registro en gastos + compras_inventariables
    """

    def __init__(self, conexion, usuario, parent=None):
        super().__init__(parent)
        self.conexion  = conexion
        self.usuario   = usuario
        self.compra_id = None
        self.setWindowTitle("Nueva Compra de Inventario")
        self.setMinimumWidth(500)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        form = QFormLayout()

        # Producto
        self.combo_producto = QComboBox()
        self.combo_producto.setEditable(False)  # no popup list
        try:
            prods = self.conexion.execute(
                "SELECT id, nombre, unidad FROM productos WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            for pid, nombre, unidad in prods:
                self.combo_producto.addItem(f"{nombre} ({unidad})", pid)
        except Exception:
            pass
        form.addRow("Producto *:", self.combo_producto)

        # Proveedor
        self.txt_proveedor = QLineEdit()
        self.txt_proveedor.setPlaceholderText("Nombre del proveedor")
        form.addRow("Proveedor:", self.txt_proveedor)

        # Volumen + unidad
        vol_layout = QHBoxLayout()
        self.spin_volumen = QDoubleSpinBox()
        self.spin_volumen.setDecimals(3)
        self.spin_volumen.setRange(0.001, 999999)
        self.spin_volumen.setValue(1.0)
        self.spin_volumen.valueChanged.connect(self._actualizar_total)
        self.txt_unidad = QLineEdit()
        self.txt_unidad.setText("kg")
        self.txt_unidad.setMaximumWidth(60)
        vol_layout.addWidget(self.spin_volumen)
        vol_layout.addWidget(QLabel("Unidad:"))
        vol_layout.addWidget(self.txt_unidad)
        form.addRow("Volumen *:", vol_layout)

        # Costo unitario
        self.spin_costo_unit = QDoubleSpinBox()
        self.spin_costo_unit.setDecimals(4)
        self.spin_costo_unit.setRange(0, 999999)
        self.spin_costo_unit.setPrefix("$")
        self.spin_costo_unit.valueChanged.connect(self._actualizar_total)
        form.addRow("Costo unitario *:", self.spin_costo_unit)

        # Total calculado
        self.lbl_total = QLabel("$0.00")
        self.lbl_total.setObjectName("tituloPrincipal")
        form.addRow("Total calculado:", self.lbl_total)

        # Forma de pago
        self.combo_pago = QComboBox()
        self.combo_pago.addItems(["EFECTIVO", "TRANSFERENCIA", "CHEQUE", "CRÉDITO", "PARCIAL"])
        self.combo_pago.currentTextChanged.connect(self._on_forma_pago_changed)
        form.addRow("Forma de pago:", self.combo_pago)

        # Pago parcial / crédito
        self.grp_credito = QGroupBox("Crédito / Parcial")
        grp_lay = QFormLayout(self.grp_credito)
        self.spin_monto_pagado = QDoubleSpinBox()
        self.spin_monto_pagado.setDecimals(2)
        self.spin_monto_pagado.setRange(0, 999999)
        self.spin_monto_pagado.setPrefix("$")
        grp_lay.addRow("Monto pagado:", self.spin_monto_pagado)
        self.date_vencimiento = QDateEdit()
        self.date_vencimiento.setCalendarPopup(True)
        from PyQt5.QtCore import QDate
        self.date_vencimiento.setDate(QDate.currentDate().addDays(30))
        grp_lay.addRow("Vence:", self.date_vencimiento)
        self.grp_credito.setVisible(False)

        # Notas
        self.txt_notas = QLineEdit()
        self.txt_notas.setPlaceholderText("Observaciones opcionales")
        form.addRow("Notas:", self.txt_notas)

        layout.addLayout(form)
        layout.addWidget(self.grp_credito)

        # Botones
        botones = QHBoxLayout()
        self.btn_guardar  = QPushButton("💾 Registrar Compra")
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_guardar.clicked.connect(self._guardar)
        self.btn_cancelar.clicked.connect(self.reject)
        botones.addStretch()
        botones.addWidget(self.btn_guardar)
        botones.addWidget(self.btn_cancelar)
        layout.addLayout(botones)

    def _actualizar_total(self):
        total = self.spin_volumen.value() * self.spin_costo_unit.value()
        self.lbl_total.setText(f"${total:,.2f}")

    def _on_forma_pago_changed(self, forma):
        self.grp_credito.setVisible(forma in ("CRÉDITO", "PARCIAL"))

    def _guardar(self):
        import uuid as _uuid, json as _json
        producto_id = self.combo_producto.currentData()
        if not producto_id:
            QMessageBox.warning(self, "Error", "Seleccione un producto")
            return
        volumen = self.spin_volumen.value()
        if volumen <= 0:
            QMessageBox.warning(self, "Error", "El volumen debe ser mayor a 0")
            return
        costo_unit  = self.spin_costo_unit.value()
        costo_total = round(volumen * costo_unit, 4)
        proveedor   = self.txt_proveedor.text().strip() or None
        unidad      = self.txt_unidad.text().strip() or "kg"
        forma_pago  = self.combo_pago.currentText()
        notas       = self.txt_notas.text().strip()
        es_credito  = 1 if forma_pago in ("CRÉDITO", "PARCIAL") else 0
        monto_pagado = self.spin_monto_pagado.value() if es_credito else costo_total
        saldo       = round(costo_total - monto_pagado, 4) if es_credito else 0.0
        vence       = (self.date_vencimiento.date().toString("yyyy-MM-dd")
                       if es_credito else None)
        estado      = "credito" if forma_pago == "CRÉDITO" else (
                       "parcial" if forma_pago == "PARCIAL" else "pagado")

        try:
            from datetime import datetime as _dt
            hoy = _dt.now().strftime("%Y-%m-%d")

            # Crear gasto
            prod_row = self.conexion.execute(
                "SELECT nombre FROM productos WHERE id=?", (producto_id,)
            ).fetchone()
            prod_nombre = prod_row[0] if prod_row else "Producto"

            cur_g = self.conexion.execute(
                """
                INSERT INTO gastos
                    (fecha, categoria, concepto, monto, monto_pagado,
                     metodo_pago, estado, proveedor_id, usuario, activo)
                VALUES (?,?,?,?,?,'{}',?,NULL,?,1)
                """.replace("'{}'", f"'{forma_pago}'"),
                (
                    hoy, "Compra Inventario",
                    f"Compra {prod_nombre} — {volumen}{unidad} @ ${costo_unit}/{unidad}",
                    costo_total, monto_pagado, estado,
                    self.usuario or "admin",
                )
            )
            gasto_id = cur_g.lastrowid

            # Registrar en compras_inventariables
            ci_uuid = _uuid.uuid4().hex
            cur_ci = self.conexion.execute(
                """
                INSERT INTO compras_inventariables
                    (uuid, gasto_id, producto_id, proveedor,
                     volumen, unidad, costo_unitario, costo_total,
                     forma_pago, es_credito, monto_pagado, saldo_pendiente,
                     fecha_vencimiento, estado, notas,
                     sucursal_id, usuario, fecha)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
                """,
                (
                    ci_uuid, gasto_id, producto_id, proveedor,
                    volumen, unidad, costo_unit, costo_total,
                    forma_pago, es_credito, monto_pagado, saldo,
                    vence, estado, notas,
                    1, self.usuario or "admin",
                )
            )
            self.compra_id = cur_ci.lastrowid

            self.conexion.commit()
            self.accept()

        except Exception as exc:
            self.conexion.rollback()
            QMessageBox.critical(self, "Error", f"No se pudo registrar: {exc}")


# --- Diálogo para Crear/Editar Gasto ---
class DialogoGasto(QDialog):
    def __init__(self, conexion, usuario_actual, parent=None, gasto_data=None):
        super().__init__(parent)
        self.conexion = conexion
        self.usuario_actual = usuario_actual
        self.gasto_data = gasto_data # None para nuevo, dict para editar
        self.setWindowTitle("Nuevo Gasto" if not gasto_data else "Editar Gasto")
        self.setFixedSize(450, 450)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        form_layout = QFormLayout()
        
        self.date_fecha = QDateEdit()
        self.date_fecha.setDate(QDate.currentDate())
        self.date_fecha.setDisplayFormat("dd/MM/yyyy")
        self.date_fecha.setCalendarPopup(True)
        
        self.edit_categoria = QComboBox()
        self.edit_categoria.setEditable(True)
        self.cargar_categorias()
        
        self.edit_proveedor = QComboBox()
        self.edit_proveedor.setEditable(False)  # no popup list
        self.cargar_proveedores()
        
        self.spin_monto = QDoubleSpinBox()
        self.spin_monto.setRange(0.01, 999999.99)
        self.spin_monto.setPrefix("$ ")
        self.spin_monto.setDecimals(2)
        
        self.combo_estado = QComboBox()
        self.combo_estado.addItems(["PENDIENTE", "PAGADO", "PARCIAL"])
        
        self.spin_monto_pagado = QDoubleSpinBox()
        self.spin_monto_pagado.setRange(0.00, 999999.99)
        self.spin_monto_pagado.setPrefix("$ ")
        self.spin_monto_pagado.setDecimals(2)
        
        self.edit_descripcion = QTextEdit()
        self.edit_descripcion.setMaximumHeight(100)
        
        self.edit_metodo_pago = QComboBox()
        self.edit_metodo_pago.addItems(["Efectivo", "Tarjeta", "Transferencia", "Cheque", "Crédito"])

        # Poblar campos si es edición
        if self.gasto_data:
            # Convertir string de fecha a QDate
            fecha_str = self.gasto_data.get('fecha', '')
            if fecha_str:
                fecha_dt = QDate.fromString(fecha_str.split(' ')[0], "yyyy-MM-dd") # Solo la parte de la fecha
                if fecha_dt.isValid():
                    self.date_fecha.setDate(fecha_dt)
            
            categoria = self.gasto_data.get('categoria', '')
            if categoria and self.edit_categoria.findText(categoria) == -1:
                self.edit_categoria.addItem(categoria)
            self.edit_categoria.setCurrentText(categoria)
            
            # Proveedor
            proveedor_id = self.gasto_data.get('proveedor_id')
            if proveedor_id:
                try:
                    cursor = self.conexion.cursor()
                    cursor.execute("SELECT nombre FROM proveedores WHERE id = ?", (proveedor_id,))
                    proveedor = cursor.fetchone()
                    if proveedor:
                        nombre_proveedor = proveedor[0]
                        if self.edit_proveedor.findText(nombre_proveedor) == -1:
                            self.edit_proveedor.addItem(nombre_proveedor)
                        self.edit_proveedor.setCurrentText(nombre_proveedor)
                except sqlite3.Error:
                    pass # Si hay error, dejar el combo vacío
            
            self.spin_monto.setValue(self.gasto_data.get('monto', 0.0))
            self.combo_estado.setCurrentText(self.gasto_data.get('estado', 'PENDIENTE'))
            self.spin_monto_pagado.setValue(self.gasto_data.get('monto_pagado', 0.0))
            self.edit_descripcion.setPlainText(self.gasto_data.get('descripcion', ''))
            metodo_pago = self.gasto_data.get('metodo_pago', 'Efectivo')
            index_metodo = self.edit_metodo_pago.findText(metodo_pago)
            if index_metodo >= 0:
                self.edit_metodo_pago.setCurrentIndex(index_metodo)

        # Conectar señales
        self.combo_estado.currentTextChanged.connect(self.on_estado_changed)
        self.spin_monto.valueChanged.connect(self.on_monto_changed)

        form_layout.addRow("Fecha*:", self.date_fecha)
        form_layout.addRow("Categoría*:", self.edit_categoria)
        form_layout.addRow("Proveedor:", self.edit_proveedor)
        form_layout.addRow("Monto*:", self.spin_monto)
        form_layout.addRow("Estado*:", self.combo_estado)
        form_layout.addRow("Monto Pagado:", self.spin_monto_pagado)
        form_layout.addRow("Método de Pago:", self.edit_metodo_pago)
        form_layout.addRow("Descripción:", self.edit_descripcion)

        btn_layout = QHBoxLayout()
        self.btn_guardar = QPushButton("Guardar")
        self.btn_cancelar = QPushButton("Cancelar")
        btn_layout.addWidget(self.btn_guardar)
        btn_layout.addWidget(self.btn_cancelar)

        layout.addLayout(form_layout)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

        # Conexiones
        self.btn_guardar.clicked.connect(self.guardar)
        self.btn_cancelar.clicked.connect(self.reject)
        
        # Inicializar estado de widgets
        self.on_estado_changed(self.combo_estado.currentText())

    def cargar_categorias(self):
        """Carga las categorías existentes en el combo box."""
        try:
            cursor = self.conexion.cursor()
            cursor.execute("SELECT DISTINCT categoria FROM gastos WHERE categoria IS NOT NULL")
            categorias = cursor.fetchall()
            self.edit_categoria.addItem("") # Opción vacía
            for cat in categorias:
                self.edit_categoria.addItem(cat[0])
        except sqlite3.Error:
            pass # Si hay error, el combo queda vacío excepto la opción por defecto

    def cargar_proveedores(self):
        """Carga los proveedores existentes en el combo box."""
        try:
            cursor = self.conexion.cursor()
            cursor.execute("SELECT nombre FROM proveedores ORDER BY nombre")
            proveedores = cursor.fetchall()
            self.edit_proveedor.addItem("") # Opción vacía
            for prov in proveedores:
                self.edit_proveedor.addItem(prov[0])
        except sqlite3.Error:
            pass # Si hay error, el combo queda vacío excepto la opción por defecto

    def on_estado_changed(self, estado):
        """Habilita/deshabilita el campo de monto pagado según el estado."""
        if estado == "PAGADO":
            self.spin_monto_pagado.setEnabled(True)
            self.spin_monto_pagado.setValue(self.spin_monto.value())
        elif estado == "PARCIAL":
            self.spin_monto_pagado.setEnabled(True)
        else: # PENDIENTE
            self.spin_monto_pagado.setEnabled(False)
            self.spin_monto_pagado.setValue(0.00)

    def on_monto_changed(self, monto):
        """Actualiza el monto pagado si el estado es PAGADO."""
        if self.combo_estado.currentText() == "PAGADO":
            self.spin_monto_pagado.setValue(monto)

    def validar_formulario(self):
        """Valida los datos del formulario."""
        if self.spin_monto.value() <= 0:
            QMessageBox.warning(self, "Error", "El monto debe ser mayor a cero.")
            return False
        if not self.edit_categoria.currentText().strip():
            QMessageBox.warning(self, "Error", "La categoría es obligatoria.")
            return False
        return True

    def guardar(self):
        """Guarda el gasto en la base de datos."""
        if not self.validar_formulario():
            return

        try:
            cursor = self.conexion.cursor()
            
            fecha = self.date_fecha.date().toString("yyyy-MM-dd")
            categoria = self.edit_categoria.currentText().strip()
            nombre_proveedor = self.edit_proveedor.currentText().strip() or None
            monto = self.spin_monto.value()
            estado = self.combo_estado.currentText()
            monto_pagado = self.spin_monto_pagado.value() if estado in ["PAGADO", "PARCIAL"] else 0.0
            descripcion = self.edit_descripcion.toPlainText().strip() or None
            metodo_pago = self.edit_metodo_pago.currentText()
            usuario = self.usuario_actual
            
            # Obtener ID del proveedor si se proporcionó nombre
            proveedor_id = None
            if nombre_proveedor:
                cursor.execute("SELECT id FROM proveedores WHERE nombre = ?", (nombre_proveedor,))
                prov = cursor.fetchone()
                if prov:
                    proveedor_id = prov[0]
                else:
                    # Crear nuevo proveedor si no existe
                    cursor.execute("INSERT INTO proveedores (nombre) VALUES (?)", (nombre_proveedor,))
                    proveedor_id = cursor.lastrowid

            # CORRECCIÓN: Usar self.gasto_data en lugar de self.gasto
            if self.gasto_data:  # Editar
                id_gasto = self.gasto_data['id']
                
                cursor.execute("""
                    UPDATE gastos 
                    SET fecha = ?, categoria = ?, proveedor_id = ?, monto = ?, 
                        monto_pagado = ?, estado = ?, descripcion = ?, metodo_pago = ?
                    WHERE id = ?
                """, (fecha, categoria, proveedor_id, monto, monto_pagado, estado, descripcion, metodo_pago, id_gasto))
                
                self.conexion.commit()
                QMessageBox.information(self, "Éxito", "Gasto actualizado correctamente.")
                self.accept()
            else:  # Nuevo
                cursor.execute("""
                    INSERT INTO gastos (fecha, categoria, proveedor_id, monto, 
                                        monto_pagado, estado, descripcion, usuario, metodo_pago)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (fecha, categoria, proveedor_id, monto, monto_pagado, estado, descripcion, usuario, metodo_pago))
                
                self.conexion.commit()
                QMessageBox.information(self, "Éxito", "Gasto creado correctamente.")
                self.accept()

        except sqlite3.IntegrityError as e:
            self.conexion.rollback()
            QMessageBox.warning(self, "Error", f"Error de integridad: {str(e)}")
        except sqlite3.Error as e:
            self.conexion.rollback()
            QMessageBox.critical(self, "Error", f"Error en la base de datos: {str(e)}")
        except Exception as e:
            self.conexion.rollback()
            QMessageBox.critical(self, "Error", f"Error inesperado: {str(e)}")

# --- Diálogo para Crear/Editar Empleado ---
class DialogoEmpleado(QDialog):
    def __init__(self, conexion, parent=None, empleado_data=None):
        super().__init__(parent)
        self.conexion = conexion
        self.empleado_data = empleado_data # None para nuevo, dict para editar
        self.setWindowTitle("Nuevo Empleado" if not empleado_data else "Editar Empleado")
        self.setFixedSize(400, 350)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        form_layout = QFormLayout()
        
        self.edit_nombre = QLineEdit()
        self.edit_apellidos = QLineEdit()
        self.edit_puesto = QLineEdit()
        self.spin_salario = QDoubleSpinBox()
        self.spin_salario.setRange(0.01, 999999.99)
        self.spin_salario.setPrefix("$ ")
        self.spin_salario.setDecimals(2)
        self.date_fecha_ingreso = QDateEdit()
        self.date_fecha_ingreso.setDate(QDate.currentDate())
        self.date_fecha_ingreso.setDisplayFormat("dd/MM/yyyy")
        self.date_fecha_ingreso.setCalendarPopup(True)
        self.chk_activo = QCheckBox("Activo")
        self.chk_activo.setChecked(True)

        # Poblar campos si es edición
        if self.empleado_data:
            self.edit_nombre.setText(self.empleado_data.get('nombre', ''))
            self.edit_apellidos.setText(self.empleado_data.get('apellidos', ''))
            self.edit_puesto.setText(self.empleado_data.get('puesto', ''))
            self.spin_salario.setValue(self.empleado_data.get('salario', 0.0))
            
            # Convertir string de fecha a QDate
            fecha_str = self.empleado_data.get('fecha_ingreso', '')
            if fecha_str:
                fecha_dt = QDate.fromString(fecha_str, "yyyy-MM-dd")
                if fecha_dt.isValid():
                    self.date_fecha_ingreso.setDate(fecha_dt)
            
            self.chk_activo.setChecked(self.empleado_data.get('activo', 1) == 1)

        form_layout.addRow("Nombre*:", self.edit_nombre)
        form_layout.addRow("Apellidos:", self.edit_apellidos)
        form_layout.addRow("Puesto:", self.edit_puesto)
        form_layout.addRow("Salario:", self.spin_salario)
        form_layout.addRow("Fecha de Ingreso:", self.date_fecha_ingreso)
        form_layout.addRow(self.chk_activo)

        btn_layout = QHBoxLayout()
        self.btn_guardar = QPushButton("Guardar")
        self.btn_cancelar = QPushButton("Cancelar")
        btn_layout.addWidget(self.btn_guardar)
        btn_layout.addWidget(self.btn_cancelar)

        layout.addLayout(form_layout)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

        # Conexiones
        self.btn_guardar.clicked.connect(self.guardar)
        self.btn_cancelar.clicked.connect(self.reject)

    def validar_formulario(self):
        """Valida los datos del formulario."""
        if not self.edit_nombre.text().strip():
            QMessageBox.warning(self, "Error", "El nombre es obligatorio.")
            return False
        if self.spin_salario.value() <= 0:
            QMessageBox.warning(self, "Error", "El salario debe ser mayor a cero.")
            return False
        return True

    def guardar(self):
        """Guarda el empleado en la base de datos."""
        if not self.validar_formulario():
            return

        try:
            cursor = self.conexion.cursor()
            
            nombre = self.edit_nombre.text().strip()
            apellidos = self.edit_apellidos.text().strip() or None
            puesto = self.edit_puesto.text().strip() or None
            salario = self.spin_salario.value()
            fecha_ingreso = self.date_fecha_ingreso.date().toString("yyyy-MM-dd")
            activo = 1 if self.chk_activo.isChecked() else 0

            # CORRECCIÓN: Usar self.empleado_data en lugar de self.empleado
            if self.empleado_data:  # Editar
                id_empleado = self.empleado_data['id']
                
                cursor.execute("""
                    UPDATE personal 
                    SET nombre = ?, apellidos = ?, puesto = ?, salario = ?, 
                        fecha_ingreso = ?, activo = ?
                    WHERE id = ?
                """, (nombre, apellidos, puesto, salario, fecha_ingreso, activo, id_empleado))
                
                self.conexion.commit()
                QMessageBox.information(self, "Éxito", "Empleado actualizado correctamente.")
                self.accept()
            else:  # Nuevo
                cursor.execute("""
                    INSERT INTO personal (nombre, apellidos, puesto, salario, fecha_ingreso, activo)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (nombre, apellidos, puesto, salario, fecha_ingreso, activo))
                
                self.conexion.commit()
                QMessageBox.information(self, "Éxito", "Empleado creado correctamente.")
                self.accept()

        except sqlite3.IntegrityError as e:
            self.conexion.rollback()
            QMessageBox.warning(self, "Error", f"Error de integridad: {str(e)}")
        except sqlite3.Error as e:
            self.conexion.rollback()
            QMessageBox.critical(self, "Error", f"Error en la base de datos: {str(e)}")
        except Exception as e:
            self.conexion.rollback()
            QMessageBox.critical(self, "Error", f"Error inesperado: {str(e)}")

    
