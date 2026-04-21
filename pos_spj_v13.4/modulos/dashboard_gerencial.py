# modulos/dashboard_gerencial.py — SPJ ERP v13.4
"""
Dashboard Gerencial — Panel ejecutivo de alto nivel.

Consume exclusivamente servicios del container (sin SQL directo):
  - AnalyticsEngine  → ventas del día, top productos, forecast, ranking sucursales
  - TreasuryService  → balance general, flujo de caja, estado de cuenta
  - FiscalEngine     → desglose IVA/ISR del período

Compatible con el interface estándar de módulos SPJ:
  set_sucursal(id, nombre) / set_usuario_actual(usuario, rol)
"""
from __future__ import annotations
import logging
from datetime import date

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QGroupBox, QGridLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QSizePolicy, QScrollArea, QFrame, QComboBox, QAbstractItemView,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

logger = logging.getLogger("spj.dashboard_gerencial")


# ── Helper: worker thread para no bloquear la UI ─────────────────────────────

class _LoadWorker(QThread):
    resultado = pyqtSignal(dict)
    error     = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.resultado.emit(self._fn())
        except Exception as e:
            self.error.emit(str(e))


# ── Widget principal ──────────────────────────────────────────────────────────

class DashboardGerencial(QWidget):
    """
    Panel ejecutivo. Tres pestañas:
      1. 📊 Ejecutivo   — KPIs del día, top productos, ranking sucursales
      2. 💰 Tesorería   — Balance general, flujo de caja, estado de cuenta
      3. 📈 Proyección  — Forecast 7 días, desglose fiscal del período
    """

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container   = container
        self.sucursal_id = 1
        self._usuario    = ""
        self._hoy        = date.today().isoformat()
        self._workers: list = []
        self._init_ui()
        self.actualizar()

    # ── Interface estándar SPJ ────────────────────────────────────────────────

    def set_sucursal(self, sucursal_id: int, nombre_sucursal: str = ""):
        self.sucursal_id = sucursal_id
        self._lbl_sucursal.setText(f"Sucursal: {nombre_sucursal or sucursal_id}")
        self.actualizar()

    def set_usuario_actual(self, usuario: str, rol: str = ""):
        self._usuario = usuario

    # ── Construcción de UI ────────────────────────────────────────────────────

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # ── Header ──
        hdr = QHBoxLayout()
        lbl_titulo = QLabel("🏢 Dashboard Gerencial")
        lbl_titulo.setFont(QFont("Arial", 16, QFont.Bold))
        self._lbl_sucursal = QLabel("Sucursal: —")
        self._lbl_sucursal.setStyleSheet("color:#666; font-size:12px;")
        self._lbl_hoy = QLabel(f"📅 {self._hoy}")
        self._lbl_hoy.setStyleSheet("color:#666; font-size:12px;")
        btn_act = QPushButton("🔄 Actualizar")
        btn_act.setFixedWidth(110)
        btn_act.clicked.connect(self.actualizar)

        hdr.addWidget(lbl_titulo)
        hdr.addStretch()
        hdr.addWidget(self._lbl_hoy)
        hdr.addWidget(self._lbl_sucursal)
        hdr.addWidget(btn_act)
        outer.addLayout(hdr)

        # ── Tabs ──
        self._tabs = QTabWidget()
        outer.addWidget(self._tabs)

        self._tab_ejecutivo  = self._build_tab_ejecutivo()
        self._tab_tesoreria  = self._build_tab_tesoreria()
        self._tab_proyeccion = self._build_tab_proyeccion()

        self._tabs.addTab(self._tab_ejecutivo,  "📊 Ejecutivo")
        self._tabs.addTab(self._tab_tesoreria,  "💰 Tesorería")
        self._tabs.addTab(self._tab_proyeccion, "📈 Proyección")
        self._tabs.currentChanged.connect(self._on_tab_changed)

    def _kpi_card(self, titulo: str, valor: str = "—") -> tuple:
        """Returns (QGroupBox, QLabel_valor) so callers can update the label."""
        grp = QGroupBox(titulo)
        grp.setStyleSheet(
            "QGroupBox { font-size:11px; font-weight:bold; color:#555; "
            "border:1px solid #ddd; border-radius:6px; padding:6px; "
            "background:#fafafa; }"
        )
        lbl = QLabel(valor)
        lbl.setFont(QFont("Arial", 18, QFont.Bold))
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color:#2c3e50;")
        v = QVBoxLayout(grp)
        v.addWidget(lbl)
        return grp, lbl

    def _simple_table(self, headers: list) -> QTableWidget:
        tbl = QTableWidget(0, len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.verticalHeader().setVisible(False)
        tbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return tbl

    # ── Tab 1: Ejecutivo ──────────────────────────────────────────────────────

    def _build_tab_ejecutivo(self) -> QWidget:
        w  = QWidget()
        vl = QVBoxLayout(w)
        vl.setSpacing(8)

        # KPI cards row
        kpi_row = QHBoxLayout()
        self._kpi_ingresos,  self._lbl_ingresos  = self._kpi_card("💵 Ingresos del Día")
        self._kpi_tickets,   self._lbl_tickets    = self._kpi_card("🧾 Transacciones")
        self._kpi_ticket_p,  self._lbl_ticket_p   = self._kpi_card("📈 Ticket Promedio")
        self._kpi_margen,    self._lbl_margen      = self._kpi_card("💹 Margen Top 5")
        for grp in (self._kpi_ingresos, self._kpi_tickets,
                    self._kpi_ticket_p, self._kpi_margen):
            kpi_row.addWidget(grp)
        vl.addLayout(kpi_row)

        # Bottom: top productos + ranking sucursales
        split = QHBoxLayout()

        grp_top = QGroupBox("🏆 Top 10 Productos (Margen)")
        grp_top.setStyleSheet("QGroupBox { font-weight:bold; }")
        vl_top = QVBoxLayout(grp_top)
        self._tbl_top_prod = self._simple_table(
            ["Producto ID", "Ingresos", "Costo", "Margen"])
        vl_top.addWidget(self._tbl_top_prod)
        split.addWidget(grp_top)

        grp_rank = QGroupBox("🏢 Ranking Sucursales (Hoy)")
        grp_rank.setStyleSheet("QGroupBox { font-weight:bold; }")
        vl_rank = QVBoxLayout(grp_rank)
        self._tbl_ranking = self._simple_table(
            ["Sucursal", "Rank", "Score"])
        vl_rank.addWidget(self._tbl_ranking)
        split.addWidget(grp_rank)

        vl.addLayout(split)
        return w

    # ── Tab 2: Tesorería ─────────────────────────────────────────────────────

    def _build_tab_tesoreria(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        scroll.setWidget(inner)
        vl = QVBoxLayout(inner)
        vl.setSpacing(8)

        # KPI cards row
        kpi_row = QHBoxLayout()
        self._kpi_capital,    self._lbl_capital    = self._kpi_card("🏦 Capital Total")
        self._kpi_ing_mes,    self._lbl_ing_mes    = self._kpi_card("📥 Ingresos Mes")
        self._kpi_egr_mes,    self._lbl_egr_mes    = self._kpi_card("📤 Egresos Mes")
        self._kpi_flujo_neto, self._lbl_flujo_neto = self._kpi_card("⚖️ Flujo Neto")
        for grp in (self._kpi_capital, self._kpi_ing_mes,
                    self._kpi_egr_mes, self._kpi_flujo_neto):
            kpi_row.addWidget(grp)
        vl.addLayout(kpi_row)

        # Balance summary grid
        grp_balance = QGroupBox("📋 Balance Rápido")
        grp_balance.setStyleSheet("QGroupBox { font-weight:bold; }")
        grid = QGridLayout(grp_balance)
        self._balance_labels: dict = {}
        fields = [
            ("activo_circulante", "Activo Circulante"),
            ("activo_fijo_neto",  "Activo Fijo Neto"),
            ("pasivo_corriente",  "Pasivo Corriente"),
            ("capital_contable",  "Capital Contable"),
        ]
        for i, (key, label) in enumerate(fields):
            lbl_k = QLabel(label + ":")
            lbl_k.setStyleSheet("font-weight:bold; color:#555;")
            lbl_v = QLabel("—")
            lbl_v.setStyleSheet("color:#2c3e50; font-size:13px;")
            grid.addWidget(lbl_k, i // 2, (i % 2) * 2)
            grid.addWidget(lbl_v, i // 2, (i % 2) * 2 + 1)
            self._balance_labels[key] = lbl_v
        vl.addWidget(grp_balance)

        # CxP / CxC summary
        cxpcxc_row = QHBoxLayout()
        grp_cxp = QGroupBox("🧾 Cuentas por Pagar")
        grp_cxp.setStyleSheet("QGroupBox { font-weight:bold; }")
        vl_cxp = QVBoxLayout(grp_cxp)
        self._lbl_cxp_total = QLabel("—")
        self._lbl_cxp_total.setFont(QFont("Arial", 16, QFont.Bold))
        self._lbl_cxp_total.setAlignment(Qt.AlignCenter)
        self._lbl_cxp_vencidas = QLabel("Vencidas: —")
        self._lbl_cxp_vencidas.setAlignment(Qt.AlignCenter)
        vl_cxp.addWidget(self._lbl_cxp_total)
        vl_cxp.addWidget(self._lbl_cxp_vencidas)
        cxpcxc_row.addWidget(grp_cxp)

        grp_cxc = QGroupBox("💰 Cuentas por Cobrar")
        grp_cxc.setStyleSheet("QGroupBox { font-weight:bold; }")
        vl_cxc = QVBoxLayout(grp_cxc)
        self._lbl_cxc_total = QLabel("—")
        self._lbl_cxc_total.setFont(QFont("Arial", 16, QFont.Bold))
        self._lbl_cxc_total.setAlignment(Qt.AlignCenter)
        self._lbl_cxc_vencidas = QLabel("Vencidas: —")
        self._lbl_cxc_vencidas.setAlignment(Qt.AlignCenter)
        vl_cxc.addWidget(self._lbl_cxc_total)
        vl_cxc.addWidget(self._lbl_cxc_vencidas)
        cxpcxc_row.addWidget(grp_cxc)
        vl.addLayout(cxpcxc_row)

        return scroll

    # ── Tab 3: Proyección ─────────────────────────────────────────────────────

    def _build_tab_proyeccion(self) -> QWidget:
        w  = QWidget()
        vl = QVBoxLayout(w)
        vl.setSpacing(8)

        # Forecast table
        grp_fc = QGroupBox("📈 Proyección de Ventas — Próximos 7 Días")
        grp_fc.setStyleSheet("QGroupBox { font-weight:bold; }")
        vl_fc = QVBoxLayout(grp_fc)
        self._tbl_forecast = self._simple_table(["Fecha", "Proyección ($)"])
        self._tbl_forecast.setMaximumHeight(220)
        vl_fc.addWidget(self._tbl_forecast)
        vl.addWidget(grp_fc)

        # Fiscal summary
        grp_fiscal = QGroupBox("🧾 Resumen Fiscal del Período")
        grp_fiscal.setStyleSheet("QGroupBox { font-weight:bold; }")
        grid_f = QGridLayout(grp_fiscal)
        self._fiscal_labels: dict = {}
        fiscal_fields = [
            ("periodo",        "Período"),
            ("ingresos_brutos","Ingresos Brutos"),
            ("iva_cobrado",    "IVA Cobrado"),
            ("base_gravable",  "Base Gravable"),
            ("tasa_iva_pct",   "Tasa IVA"),
        ]
        for i, (key, label) in enumerate(fiscal_fields):
            lbl_k = QLabel(label + ":")
            lbl_k.setStyleSheet("font-weight:bold; color:#555;")
            lbl_v = QLabel("—")
            lbl_v.setStyleSheet("color:#2c3e50; font-size:12px;")
            grid_f.addWidget(lbl_k, i, 0)
            grid_f.addWidget(lbl_v, i, 1)
            self._fiscal_labels[key] = lbl_v
        vl.addWidget(grp_fiscal)

        # Inventory intelligence
        grp_inv = QGroupBox("🚨 Alertas de Inventario")
        grp_inv.setStyleSheet("QGroupBox { font-weight:bold; }")
        vl_inv = QVBoxLayout(grp_inv)
        self._tbl_low_stock = self._simple_table(
            ["Producto", "Existencia", "Mínimo"])
        self._tbl_low_stock.setMaximumHeight(200)
        vl_inv.addWidget(self._tbl_low_stock)
        vl.addWidget(grp_inv)

        return w

    # ── Carga de datos ────────────────────────────────────────────────────────

    def actualizar(self):
        """Recarga todos los datos del dashboard desde los servicios."""
        self._hoy = date.today().isoformat()
        self._lbl_hoy.setText(f"📅 {self._hoy}")
        self._load_ejecutivo()
        self._load_tesoreria()
        self._load_proyeccion()

    def _on_tab_changed(self, idx: int):
        """Lazy-reload on tab switch."""
        if idx == 1:
            self._load_tesoreria()
        elif idx == 2:
            self._load_proyeccion()

    def _fmt(self, val, prefix="$") -> str:
        try:
            return f"{prefix}{float(val):,.2f}"
        except Exception:
            return str(val)

    # ── Ejecutivo ─────────────────────────────────────────────────────────────

    def _load_ejecutivo(self):
        ae = getattr(self.container, "analytics_engine", None)
        if ae is None:
            self._lbl_ingresos.setText("N/D")
            return
        try:
            metrics = ae.sales_metrics(self._hoy, self.sucursal_id)
            self._lbl_ingresos.setText(self._fmt(metrics.get("total_ventas", 0)))
            self._lbl_tickets.setText(str(metrics.get("num_transacciones", 0)))
            self._lbl_ticket_p.setText(self._fmt(metrics.get("promedio_ticket", 0)))
        except Exception as e:
            logger.warning("load_ejecutivo metrics: %s", e)

        try:
            inicio_mes = self._hoy[:8] + "01"
            pp = ae.product_profitability(inicio_mes, self._hoy, self.sucursal_id, 10)
            total_margen = sum(r.get("margen", 0) for r in pp) if pp else 0
            self._lbl_margen.setText(self._fmt(total_margen))
            self._fill_table(
                self._tbl_top_prod, pp,
                ["producto_id", "ingresos", "costo", "margen"],
                fmt_cols={1, 2, 3},
            )
        except Exception as e:
            logger.warning("load_ejecutivo products: %s", e)

        try:
            ranking = ae.branch_ranking(self._hoy)
            self._tbl_ranking.setRowCount(0)
            for row in ranking:
                r = self._tbl_ranking.rowCount()
                self._tbl_ranking.insertRow(r)
                self._tbl_ranking.setItem(r, 0, QTableWidgetItem(
                    str(row.get("sucursal_id", ""))))
                self._tbl_ranking.setItem(r, 1, QTableWidgetItem(
                    str(row.get("rank_ventas", ""))))
                self._tbl_ranking.setItem(r, 2, QTableWidgetItem(
                    self._fmt(row.get("score", 0))))
        except Exception as e:
            logger.warning("load_ejecutivo ranking: %s", e)

    # ── Tesorería ─────────────────────────────────────────────────────────────

    def _load_tesoreria(self):
        ts = getattr(self.container, "treasury_service", None)
        fs = getattr(self.container, "finance_service", None)
        if ts is None and fs is None:
            return
        try:
            if ts:
                kpis = ts.kpis_financieros()
                self._lbl_capital.setText(
                    self._fmt(kpis.get("capital_total") or kpis.get("capital", 0)))
                self._lbl_ing_mes.setText(
                    self._fmt(kpis.get("ingresos_totales") or kpis.get("ingresos", 0)))
                self._lbl_egr_mes.setText(
                    self._fmt(kpis.get("egresos_totales") or kpis.get("egresos", 0)))
                flujo = (
                    (kpis.get("ingresos_totales") or kpis.get("ingresos") or 0)
                    - (kpis.get("egresos_totales") or kpis.get("egresos") or 0)
                )
                color = "#27ae60" if flujo >= 0 else "#e74c3c"
                self._lbl_flujo_neto.setStyleSheet(f"color:{color};")
                self._lbl_flujo_neto.setText(self._fmt(flujo))
        except Exception as e:
            logger.warning("load_tesoreria kpis: %s", e)

        try:
            if fs:
                bal = fs.balance_general()
                for key, lbl in self._balance_labels.items():
                    val = bal.get(key, 0)
                    lbl.setText(self._fmt(val))
                cxp = fs.cxp_summary()
                self._lbl_cxp_total.setText(
                    self._fmt(cxp.get("total_pendiente", 0)))
                self._lbl_cxp_vencidas.setText(
                    f"Vencidas: {self._fmt(cxp.get('total_vencido', 0))}")
                cxc = fs.cxc_summary()
                self._lbl_cxc_total.setText(
                    self._fmt(cxc.get("total_pendiente", 0)))
                self._lbl_cxc_vencidas.setText(
                    f"Vencidas: {self._fmt(cxc.get('total_vencido', 0))}")
        except Exception as e:
            logger.warning("load_tesoreria balance: %s", e)

    # ── Proyección ────────────────────────────────────────────────────────────

    def _load_proyeccion(self):
        ae = getattr(self.container, "analytics_engine", None)
        fe = getattr(self.container, "fiscal_engine", None)

        try:
            if ae:
                fc = ae.forecast(self.sucursal_id, 7)
                self._tbl_forecast.setRowCount(0)
                for row in fc:
                    r = self._tbl_forecast.rowCount()
                    self._tbl_forecast.insertRow(r)
                    self._tbl_forecast.setItem(r, 0, QTableWidgetItem(
                        str(row.get("fecha", ""))))
                    self._tbl_forecast.setItem(r, 1, QTableWidgetItem(
                        self._fmt(row.get("proyeccion", 0), prefix="")))
        except Exception as e:
            logger.warning("load_proyeccion forecast: %s", e)

        try:
            if fe and ae:
                inicio_mes = self._hoy[:8] + "01"
                pp = ae.product_profitability(inicio_mes, self._hoy, self.sucursal_id, 200)
                ingresos_brutos = sum(r.get("ingresos", 0) for r in pp)
                dsg = fe.desglosar_iva(ingresos_brutos)
                periodo = fe.periodo_fiscal(self._hoy)
                self._fiscal_labels["periodo"].setText(periodo["periodo"])
                self._fiscal_labels["ingresos_brutos"].setText(
                    self._fmt(ingresos_brutos))
                self._fiscal_labels["iva_cobrado"].setText(
                    self._fmt(dsg["iva"]))
                self._fiscal_labels["base_gravable"].setText(
                    self._fmt(dsg["base"]))
                self._fiscal_labels["tasa_iva_pct"].setText(
                    f"{dsg['tasa_pct']:.0f}%")
        except Exception as e:
            logger.warning("load_proyeccion fiscal: %s", e)

        try:
            if ae:
                inv = ae.inventory_intelligence(self.sucursal_id, 8)
                rows = inv.get("low_stock", [])
                self._tbl_low_stock.setRowCount(0)
                for row in rows:
                    r = self._tbl_low_stock.rowCount()
                    self._tbl_low_stock.insertRow(r)
                    self._tbl_low_stock.setItem(r, 0, QTableWidgetItem(
                        str(row.get("nombre", row.get("id", "")))))
                    self._tbl_low_stock.setItem(r, 1, QTableWidgetItem(
                        str(row.get("existencia", ""))))
                    self._tbl_low_stock.setItem(r, 2, QTableWidgetItem(
                        str(row.get("stock_minimo", ""))))
        except Exception as e:
            logger.warning("load_proyeccion inventory: %s", e)

    # ── Util ──────────────────────────────────────────────────────────────────

    def _fill_table(self, tbl: QTableWidget, rows: list, keys: list, fmt_cols: set = None):
        fmt_cols = fmt_cols or set()
        tbl.setRowCount(0)
        for row in rows:
            r = tbl.rowCount()
            tbl.insertRow(r)
            for c, key in enumerate(keys):
                val = row.get(key, "")
                txt = self._fmt(val, prefix="") if c in fmt_cols else str(val)
                tbl.setItem(r, c, QTableWidgetItem(txt))
