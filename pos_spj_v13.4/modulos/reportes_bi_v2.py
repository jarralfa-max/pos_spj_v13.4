# -*- coding: utf-8 -*-
# modulos/reportes_bi_v2.py
from modulos.design_tokens import Colors, Spacing, Typography, Borders, Shadows
from modulos.ui_components import (
    create_primary_button, create_success_button, create_danger_button,
    create_secondary_button, create_input, create_combo, create_card,
    create_heading, create_subheading, create_caption, apply_tooltip,
    FilterBar, EmptyStateWidget, LoadingIndicator, DataTableWithFilters, confirm_action,
    PageHeader, Toast,
)
from modulos.spj_styles import spj_btn, apply_btn_styles
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QMessageBox, QFormLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QGridLayout, QGroupBox, QFrame, QSplitter, QTabWidget,
    QAbstractItemView, QDialog, QCheckBox, QListWidget, QListWidgetItem,
    QSizePolicy, QAction, QMenu, QToolBar, QStatusBar, QProgressBar,
    QCompleter, QDateEdit, QSpinBox, QDoubleSpinBox,
    QFileDialog
)
from PyQt5.QtCore import Qt, QMetaObject, pyqtSlot
from PyQt5.QtGui import QFont

class ModuloReportesBIv2(QWidget):
    """
    Dashboard Corporativo de Business Intelligence.
    Cero SQL. Toda la data proviene del BIService.
    """
    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container = container
        self.sucursal_id = getattr(container, "sucursal_id", "") or ""
        self._last_data = {}
        self.init_ui()
        self._wire_business_events()

    def set_usuario_actual(self, usuario: str, rol: str = "cajero") -> None:
        """Recibe el usuario activo al cambiar de sesión."""
        self.usuario_actual = usuario
        self.rol_actual = rol

    def set_sucursal(self, sucursal_id: int, nombre_sucursal: str = ""):
        """Recibe la sucursal activa y refresca dashboard."""
        self.sucursal_id = sucursal_id
        self.cargar_dashboard()

    def init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        layout_principal = QVBoxLayout()
        layout_principal.setSpacing(16)
        outer.addLayout(layout_principal)

        # --- HEADER (PageHeader: título + subtítulo + acciones) ---
        self.page_header = PageHeader(
            self,
            title="📈 Inteligencia Comercial",
            subtitle="Dashboard ejecutivo de BI",
        )

        # ── Filtros globales (afectan todo el dashboard, persisten en sesión) ──
        self.cmb_rango = create_combo(
            self, ["Hoy", "Ayer", "Esta Semana", "Este Mes", "Mes Pasado"])
        self.cmb_rango.setCurrentText("Este Mes")
        self.cmb_rango.currentTextChanged.connect(self._on_filters_changed)
        self.page_header.add_action(QLabel("Período:"))
        self.page_header.add_action(self.cmb_rango)

        self.cmb_sucursal = create_combo(self, ["Todas"])
        self.cmb_sucursal.currentIndexChanged.connect(self._on_filters_changed)
        self.page_header.add_action(QLabel("Sucursal:"))
        self.page_header.add_action(self.cmb_sucursal)

        self.cmb_categoria = create_combo(self, ["Todas"])
        self.cmb_categoria.currentIndexChanged.connect(self._on_filters_changed)
        self.page_header.add_action(QLabel("Categoría:"))
        self.page_header.add_action(self.cmb_categoria)

        self.cmb_metodo = create_combo(self, ["Todos"])
        self.cmb_metodo.currentIndexChanged.connect(self._on_filters_changed)
        self.page_header.add_action(QLabel("Pago:"))
        self.page_header.add_action(self.cmb_metodo)

        self.btn_limpiar = create_secondary_button(self, "🧹 Limpiar", "Limpiar todos los filtros")
        self.btn_limpiar.clicked.connect(self._limpiar_filtros)
        self.page_header.add_action(self.btn_limpiar)

        # Refrescar
        self.btn_actualizar = create_secondary_button(self, "🔄 Refrescar", "Actualizar datos del dashboard")
        self.btn_actualizar.clicked.connect(self.cargar_dashboard)
        self.page_header.add_action(self.btn_actualizar)

        # Exportar
        btn_excel = create_success_button(self, "📊 Excel", "Exportar dashboard a Excel (.xlsx)")
        btn_excel.clicked.connect(lambda: self._exportar("excel"))
        self.page_header.add_action(btn_excel)

        btn_pdf = create_danger_button(self, "📄 PDF", "Exportar dashboard a PDF")
        btn_pdf.clicked.connect(lambda: self._exportar("pdf"))
        self.page_header.add_action(btn_pdf)

        layout_principal.addWidget(self.page_header)

        # Los KPIs viven en el Dashboard Visual (payload de BiDashboardService);
        # se retiró la barra superior de 4 tarjetas para no duplicar información.

        self.loading_dashboard = QLabel("⏳ Cargando datos…")
        self.loading_dashboard.setAlignment(Qt.AlignCenter)
        self.loading_dashboard.setVisible(False)
        layout_principal.addWidget(self.loading_dashboard)

        self.tabs_bi = QTabWidget()
        self.tabs_bi.setDocumentMode(True)
        layout_principal.addWidget(self.tabs_bi)

        self._build_tab_visual_dashboard()
        self._build_tab_rankings()
        self._build_tab_rentabilidad()
        self._build_tab_cajeros()
        # Forecast: existe un módulo dedicado de forecast; se retira la pestaña aquí.
        self._build_tab_decision_engine()
        self._build_tab_franchise()
        self._build_section_tabs()
        self._build_reportes_tab()
        self._build_config_tab()

        # Poblar filtros + lazy loading de secciones al cambiar de pestaña.
        self._populate_filter_options()
        self.tabs_bi.currentChanged.connect(self._on_tab_changed)

    def _crear_tab_contenedor(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        return tab, layout

    def _add_tab(self, widget, icon: str, tooltip: str) -> int:
        """Añade una pestaña compacta: sólo icono visible + tooltip con el nombre."""
        idx = self.tabs_bi.addTab(widget, icon)
        self.tabs_bi.setTabToolTip(idx, tooltip)
        return idx

    def _build_tab_visual_dashboard(self):
        """Dashboard visual moderno con QWebEngineView + Apache ECharts."""
        tab, layout = self._crear_tab_contenedor()

        # Fila de KPIs nativos (mismas KPICard que el módulo de Inventario).
        self._kpi_cards = {}
        self._kpi_row = QWidget()
        self._kpi_grid = QGridLayout(self._kpi_row)
        self._kpi_grid.setContentsMargins(0, 0, 0, 0)
        self._kpi_grid.setHorizontalSpacing(8)
        self._kpi_grid.setVerticalSpacing(8)
        layout.addWidget(self._kpi_row)

        self._chart_empty = EmptyStateWidget(
            "Sin datos para graficar",
            "No hay movimientos suficientes para construir el dashboard visual.",
            "📉",
            self,
        )
        self._chart_empty.hide()

        try:
            from PyQt5.QtWebEngineWidgets import QWebEngineView
            self._chart_view = QWebEngineView(self)
            self._install_drilldown(self._chart_view)
            layout.addWidget(self._chart_view, 1)
            layout.addWidget(self._chart_empty)
        except Exception:
            self._chart_view = None
            fallback = QLabel("QWebEngine no disponible en este entorno.\nSe mostrará solo KPI tabular.")
            fallback.setStyleSheet("color:#6c757d; padding:12px;")
            fallback.setAlignment(Qt.AlignCenter)
            layout.addWidget(fallback)
        self._add_tab(tab, "📈", "Dashboard Visual")

    def _build_tab_rankings(self):
        tab, layout = self._crear_tab_contenedor()
        toolbar = QHBoxLayout()
        btn_ref_rank = create_primary_button(self, "🔄 Actualizar", "Actualizar rankings")
        btn_ref_rank.clicked.connect(self.cargar_dashboard)
        btn_export_rank = create_secondary_button(self, "📊 Exportar", "Exportar rankings a Excel")
        btn_export_rank.clicked.connect(lambda: self._exportar("excel"))
        self._lbl_rankings_estado = QLabel("Sin datos cargados.")
        self._lbl_rankings_estado.setStyleSheet("color:#6c757d; font-size:11px;")
        self._lbl_resumen_alertas = QLabel("")
        self._lbl_resumen_alertas.setStyleSheet("color:#b45309; font-size:11px;")
        toolbar.addWidget(btn_ref_rank)
        toolbar.addWidget(btn_export_rank)
        toolbar.addStretch()
        toolbar.addWidget(self._lbl_rankings_estado)
        layout.addLayout(toolbar)
        layout.addWidget(self._lbl_resumen_alertas)

        self._tabs_rankings = QTabWidget()
        self._tabs_rankings.setDocumentMode(True)
        self._grp_top = self._crear_tabla_ranking("⭐ Productos Más Vendidos", ["Producto", "Cant.", "Ingresos"])
        self.tabla_top = self._grp_top._tabla.table
        self._grp_lentos = self._crear_tabla_ranking("🐢 Productos Lentos", ["Producto", "Cant.", "Ingresos"])
        self.tabla_lentos = self._grp_lentos._tabla.table
        self._grp_vips = self._crear_tabla_ranking("👑 Clientes Recurrentes (VIP)", ["Cliente", "Visitas", "Gasto Total"])
        self.tabla_vips = self._grp_vips._tabla.table
        self._tabs_rankings.addTab(self._grp_top, "Más vendidos")
        self._tabs_rankings.addTab(self._grp_lentos, "Lentos")
        self._tabs_rankings.addTab(self._grp_vips, "Clientes VIP")
        layout.addWidget(self._tabs_rankings)
        self._add_tab(tab, "🏆", "Ventas / Rankings")

    def _build_tab_rentabilidad(self):
        tab, layout = self._crear_tab_contenedor()
        self._build_rentabilidad_section(layout)
        self._add_tab(tab, "💹", "Rentabilidad")

    def _build_tab_cajeros(self):
        tab, layout = self._crear_tab_contenedor()
        self._build_cajeros_section(layout)
        self._add_tab(tab, "🧑‍💼", "Cajeros")

    def _build_tab_decision_engine(self):
        tab, layout = self._crear_tab_contenedor()
        self._build_decision_engine_section(layout)
        self._add_tab(tab, "💡", "Sugerencias")

    def _build_tab_franchise(self):
        tab, layout = self._crear_tab_contenedor()
        self._build_franchise_section(layout)
        self._add_tab(tab, "🏪", "Sucursales / Franquicias")

    def _build_rentabilidad_section(self, parent_layout):
        """Tabla de rentabilidad por producto: margen, rotación, contribución."""
        from PyQt5.QtWidgets import QGroupBox
        grp = QGroupBox("💰 Rentabilidad por Producto (Margen Bruto)")
        grp.setObjectName("styledGroup")
        lay = QVBoxLayout(grp)

        toolbar = QHBoxLayout()
        btn_rent = create_primary_button(self, "📊 Calcular Rentabilidad", "Calcular rentabilidad por producto")
        btn_rent.clicked.connect(self._cargar_rentabilidad)
        btn_export = create_secondary_button(self, "📥 Exportar CSV", "Exportar reporte a CSV")
        btn_export.clicked.connect(self._exportar_rentabilidad_csv)
        toolbar.addWidget(btn_rent); toolbar.addWidget(btn_export); toolbar.addStretch()
        lay.addLayout(toolbar)

        self._tbl_rent = QTableWidget()
        self._tbl_rent.setColumnCount(8)
        self._tbl_rent.setHorizontalHeaderLabels([
            "Producto", "Categoría", "Unidades", "Ingresos",
            "Costo Total", "Margen $", "Margen %", "ABC"
        ])
        self._tbl_rent.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tbl_rent.setSelectionBehavior(QTableWidget.SelectRows)
        self._tbl_rent.setAlternatingRowColors(True)
        self._tbl_rent.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._tbl_rent.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        hh = self._tbl_rent.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        self._tbl_rent.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(self._tbl_rent)
        self._lbl_rent_estado = QLabel("Calculando rentabilidad…")
        self._lbl_rent_estado.setStyleSheet("color:#6c757d; font-size:11px;")
        lay.addWidget(self._lbl_rent_estado)

        self._chart_rent = self._make_chart_view()
        lay.addWidget(self._chart_rent)

        parent_layout.addWidget(grp)
        self._cargar_rentabilidad()

    # ── Rendimiento Cajeros: ranking por frecuencia y volumen ─────────────────

    def _build_cajeros_section(self, parent_layout):
        """Ranking de cajeros por # transacciones, volumen y ticket prom. Fase 2."""
        grp = QGroupBox("📊 Rendimiento de Cajeros")
        grp.setStyleSheet(
            "QGroupBox { font-weight:bold; border:1px solid #dee2e6;"
            " border-radius:6px; margin-top:10px; padding-top:8px; }"
        )
        lay = QVBoxLayout(grp)

        toolbar = QHBoxLayout()
        btn_caj = create_primary_button(self, "📋 Cargar Ranking Cajeros",
                                        "Calcular ranking de cajeros por transacciones y volumen")
        btn_caj.clicked.connect(self._cargar_cajeros)
        toolbar.addWidget(btn_caj)
        toolbar.addStretch()
        self._lbl_caj_estado = QLabel("Haz clic para ver el rendimiento de cajeros del mes.")
        self._lbl_caj_estado.setStyleSheet("color:#888; font-size:11px;")
        toolbar.addWidget(self._lbl_caj_estado)
        lay.addLayout(toolbar)

        self._tbl_caj = QTableWidget()
        self._tbl_caj.setColumnCount(6)
        self._tbl_caj.setHorizontalHeaderLabels([
            "Cajero", "# Ventas", "Total $", "Ticket Prom $", "Descuentos $", "Días Activo"
        ])
        hh = self._tbl_caj.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        self._tbl_caj.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_caj.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_caj.setAlternatingRowColors(True)
        self._tbl_caj.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._tbl_caj.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._tbl_caj.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(self._tbl_caj)

        self._chart_caj = self._make_chart_view()
        lay.addWidget(self._chart_caj)

        parent_layout.addWidget(grp)

    def _cargar_cajeros(self):
        """Carga ranking de cajeros via AnalyticsEngine.get_ranking_cajeros() (BI unificado)."""
        self._tbl_caj.setRowCount(0)
        try:
            # BI unificado: fuente única analytics_engine
            analytics = getattr(self.container, 'analytics_engine', None)
            if analytics is None:
                self._lbl_caj_estado.setText("AnalyticsEngine no disponible.")
                return
            rango = self.cmb_rango.currentText()
            rango_key = "hoy" if "hoy" in rango.lower() else \
                        "semana" if "semana" in rango.lower() else "mes"
            # Calcular fechas para el ranking
            from datetime import datetime, timedelta
            hoy = datetime.now()
            if rango_key == 'hoy':
                fecha_inicio = fecha_fin = hoy.strftime('%Y-%m-%d')
            elif rango_key == 'semana':
                fecha_inicio = (hoy - timedelta(days=hoy.weekday())).strftime('%Y-%m-%d')
                fecha_fin = hoy.strftime('%Y-%m-%d')
            else:  # mes
                fecha_inicio = hoy.replace(day=1).strftime('%Y-%m-%d')
                fecha_fin = hoy.strftime('%Y-%m-%d')
            rows = analytics.get_ranking_cajeros(self.sucursal_id, fecha_inicio, fecha_fin, limite=20)
            self._lbl_caj_estado.setText(f"{len(rows)} cajeros encontrados.")
            for i, r in enumerate(rows):
                self._tbl_caj.insertRow(i)
                vals = [
                    str(r.get("cajero", "(sin usuario)")),
                    str(r.get("num_ventas", 0)),
                    f"${float(r.get('total_ventas', 0)):,.2f}",
                    f"${float(r.get('ticket_promedio', 0)):,.2f}",
                    f"${float(r.get('total_descuentos', 0)):,.2f}",
                    str(r.get("dias_activo", 0)),
                ]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(v)
                    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    if i == 0:  # Top cajero destacado
                        item.setForeground(
                            __import__('PyQt5.QtGui', fromlist=['QColor']).QColor('#27ae60'))
                    self._tbl_caj.setItem(i, j, item)
            from modulos.bi_charts import bar_chart_html
            self._set_chart(getattr(self, "_chart_caj", None), bar_chart_html(
                "Ventas por cajero",
                [str(r.get("cajero", "")) for r in rows[:8]],
                [float(r.get("total_ventas", 0)) for r in rows[:8]]))
        except Exception as exc:
            self._lbl_caj_estado.setText(f"Error: {exc}")

    # ── DecisionEngine: sugerencias accionables ───────────────────────────────

    def _build_decision_engine_section(self, parent_layout):
        """Panel de sugerencias del DecisionEngine (FASE 5 — solo lectura)."""
        grp = QGroupBox("🤖 Sugerencias Accionables (DecisionEngine)")
        grp.setStyleSheet(
            "QGroupBox { font-weight:bold; border:1px solid #dee2e6;"
            " border-radius:6px; margin-top:10px; padding-top:8px; }"
        )
        lay = QVBoxLayout(grp)

        toolbar = QHBoxLayout()
        btn_gen = create_primary_button(self, "🔍 Generar Sugerencias",
                                        "Analizar datos y generar sugerencias accionables")
        btn_gen.clicked.connect(self._cargar_decision_engine)
        toolbar.addWidget(btn_gen)
        toolbar.addStretch()
        self._lbl_de_estado = QLabel("Haz clic en 'Generar Sugerencias' para analizar.")
        self._lbl_de_estado.setStyleSheet("color:#888; font-size:11px;")
        toolbar.addWidget(self._lbl_de_estado)
        lay.addLayout(toolbar)

        self._tbl_de = QTableWidget()
        self._tbl_de.setColumnCount(5)
        self._tbl_de.setHorizontalHeaderLabels([
            "Prioridad", "Tipo", "Sugerencia", "Impacto Estimado", "Acción Propuesta"
        ])
        hh = self._tbl_de.horizontalHeader()
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._tbl_de.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_de.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_de.setAlternatingRowColors(True)
        self._tbl_de.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._tbl_de.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._tbl_de.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(self._tbl_de)

        parent_layout.addWidget(grp)

    def _cargar_decision_engine(self):
        """Invoca DecisionEngine.generar_sugerencias() y muestra los resultados."""
        self._tbl_de.setRowCount(0)
        try:
            engine = getattr(self.container, "decision_engine", None)
            if engine is None:
                self._lbl_de_estado.setText("DecisionEngine no disponible en este contenedor.")
                return
            sugs = engine.generar_sugerencias(sucursal_id=self.sucursal_id)
            self._lbl_de_estado.setText(
                f"{len(sugs)} sugerencias generadas — solo lectura, no se ejecuta nada."
            )
            for i, s in enumerate(sugs):
                self._tbl_de.insertRow(i)
                accion = s.get("accion_propuesta", {})
                accion_txt = accion.get("descripcion", str(accion)) if isinstance(accion, dict) else str(accion)
                vals = [
                    s.get("prioridad", ""),
                    s.get("tipo", ""),
                    s.get("titulo", "") + (" — " + s.get("detalle", "") if s.get("detalle") else ""),
                    s.get("impacto_estimado", ""),
                    accion_txt[:80],
                ]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(str(v))
                    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self._tbl_de.setItem(i, j, item)
        except Exception as exc:
            self._lbl_de_estado.setText(f"Error: {exc}")

    # ── FranchiseManager: ranking multi-sucursal ──────────────────────────────

    def _build_franchise_section(self, parent_layout):
        """Ranking de sucursales via FranchiseManager (Fase 6 — multi-franquicia)."""
        grp = QGroupBox("🏪 Ranking de Sucursales (FranchiseManager)")
        grp.setStyleSheet(
            "QGroupBox { font-weight:bold; border:1px solid #dee2e6;"
            " border-radius:6px; margin-top:10px; padding-top:8px; }"
        )
        lay = QVBoxLayout(grp)

        toolbar = QHBoxLayout()
        btn_rank = create_primary_button(self, "🏆 Calcular Ranking",
                                         "Calcular ranking de sucursales por ventas y rentabilidad")
        btn_rank.clicked.connect(self._cargar_franchise_ranking)
        toolbar.addWidget(btn_rank)
        toolbar.addStretch()
        self._lbl_fm_estado = QLabel("Haz clic en 'Calcular Ranking' para comparar sucursales.")
        self._lbl_fm_estado.setStyleSheet("color:#888; font-size:11px;")
        toolbar.addWidget(self._lbl_fm_estado)
        lay.addLayout(toolbar)

        self._tbl_fm = QTableWidget()
        self._tbl_fm.setColumnCount(6)
        self._tbl_fm.setHorizontalHeaderLabels([
            "Sucursal", "Ventas $", "# Transacciones", "Ticket Prom $",
            "Margen Bruto %", "Rank"
        ])
        hh = self._tbl_fm.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        self._tbl_fm.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_fm.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_fm.setAlternatingRowColors(True)
        self._tbl_fm.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._tbl_fm.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._tbl_fm.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay.addWidget(self._tbl_fm)

        self._chart_fm = self._make_chart_view()
        lay.addWidget(self._chart_fm)

        parent_layout.addWidget(grp)

    def _cargar_franchise_ranking(self):
        """Carga ranking de sucursales via FranchiseManager."""
        self._tbl_fm.setRowCount(0)
        try:
            fm = getattr(self.container, "franchise_manager", None)
            if fm is None:
                self._lbl_fm_estado.setText("FranchiseManager no disponible.")
                return
            rows = fm.ranking_sucursales()
            self._lbl_fm_estado.setText(f"{len(rows)} sucursales analizadas.")
            for i, r in enumerate(rows):
                self._tbl_fm.insertRow(i)
                vals = [
                    str(r.get("nombre", r.get("sucursal_id", ""))),
                    f"${float(r.get('ingresos', 0)):,.2f}",
                    str(r.get("tickets", 0)),
                    f"${float(r.get('ticket_promedio', 0)):,.2f}",
                    f"{float(r.get('margen_pct', 0)):.1f}%",
                    str(r.get("posicion", i + 1)),
                ]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(str(v))
                    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self._tbl_fm.setItem(i, j, item)
            from modulos.bi_charts import bar_chart_html
            self._set_chart(getattr(self, "_chart_fm", None), bar_chart_html(
                "Ingresos por sucursal",
                [str(r.get("nombre", r.get("sucursal_id", ""))) for r in rows[:8]],
                [float(r.get("ingresos", 0)) for r in rows[:8]]))
        except Exception as exc:
            self._lbl_fm_estado.setText(f"Error: {exc}")

    def _cargar_rentabilidad(self):
        """Carga el reporte de rentabilidad por producto para el período activo (BI unificado)."""
        self._tbl_rent.setRowCount(0)
        rango = self.cmb_rango.currentText()
        
        # Calcular fechas según el rango seleccionado
        from datetime import datetime, timedelta
        hoy = datetime.now()
        if "hoy" in rango.lower():
            fecha_inicio = fecha_fin = hoy.strftime('%Y-%m-%d')
        elif "semana" in rango.lower():
            fecha_inicio = (hoy - timedelta(days=hoy.weekday())).strftime('%Y-%m-%d')
            fecha_fin = hoy.strftime('%Y-%m-%d')
        else:  # mes
            fecha_inicio = hoy.replace(day=1).strftime('%Y-%m-%d')
            fecha_fin = hoy.strftime('%Y-%m-%d')
        
        try:
            # ✅ FASE 2: Usar AnalyticsEngine para rentabilidad de productos
            analytics = getattr(self.container, 'analytics_engine', None)
            if not analytics:
                raise RuntimeError("AnalyticsEngine no disponible")
            
            # Servicio unificado: incluye nombre, categoría, unidades y costo real.
            rows_raw = analytics.product_profitability_detail(
                fecha_inicio, fecha_fin, self.sucursal_id, limit=50)
            rows = [
                (r['nombre'], r['categoria'], r['unidades'], r['ingresos'], r['costo'])
                for r in rows_raw
            ]
        except Exception as e:
            self._lbl_rent_estado.setText(f"Error al cargar rentabilidad: {e}")
            return

        if not rows:
            self._lbl_rent_estado.setText("Sin datos de rentabilidad para el período seleccionado.")
            return

        total_margen = sum((float(r[3] or 0) - float(r[4] or 0)) for r in rows)

        for i, r in enumerate(rows):
            ingresos    = float(r[3] or 0)
            costo       = float(r[4] or 0)
            margen_monto = ingresos - costo
            margen_pct   = (margen_monto / ingresos * 100) if ingresos > 0 else 0
            contrib_pct  = (margen_monto / total_margen * 100) if total_margen > 0 else 0

            # ABC classification
            if contrib_pct >= 10:    abc = "A ⭐"
            elif contrib_pct >= 3:   abc = "B"
            else:                     abc = "C"

            self._tbl_rent.insertRow(i)
            self._tbl_rent.setItem(i, 0, QTableWidgetItem(str(r[0])))
            self._tbl_rent.setItem(i, 1, QTableWidgetItem(str(r[1] or "")))
            self._tbl_rent.setItem(i, 2, QTableWidgetItem(f"{float(r[2] or 0):.1f}"))
            self._tbl_rent.setItem(i, 3, QTableWidgetItem(f"${ingresos:,.2f}"))
            self._tbl_rent.setItem(i, 4, QTableWidgetItem(f"${costo:,.2f}"))

            item_margen = QTableWidgetItem(f"${margen_monto:,.2f}")
            if margen_pct < 0:
                item_margen.setForeground(__import__('PyQt5.QtGui', fromlist=['QColor']).QColor('#e74c3c'))
            self._tbl_rent.setItem(i, 5, item_margen)

            item_pct = QTableWidgetItem(f"{margen_pct:.1f}%")
            color = '#27ae60' if margen_pct >= 20 else '#e67e22' if margen_pct >= 10 else '#e74c3c'
            item_pct.setForeground(__import__('PyQt5.QtGui', fromlist=['QColor']).QColor(color))
            self._tbl_rent.setItem(i, 6, item_pct)
            self._tbl_rent.setItem(i, 7, QTableWidgetItem(abc))
        self._lbl_rent_estado.setText(f"{len(rows)} productos analizados.")

        # Gráfica: margen $ de los productos top (offline SVG)
        from modulos.bi_charts import bar_chart_html
        top = sorted(rows, key=lambda r: float(r[3] or 0) - float(r[4] or 0),
                     reverse=True)[:8]
        self._set_chart(getattr(self, "_chart_rent", None), bar_chart_html(
            "Margen por producto (top 8)",
            [str(r[0]) for r in top],
            [float(r[3] or 0) - float(r[4] or 0) for r in top]))

    def _exportar_rentabilidad_csv(self):
        """Exporta la tabla de rentabilidad a CSV."""
        try:
            from PyQt5.QtWidgets import QFileDialog
            import csv
            path, _ = QFileDialog.getSaveFileName(
                self, "Guardar CSV", "rentabilidad.csv", "CSV (*.csv)")
            if not path: return
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                headers = [self._tbl_rent.horizontalHeaderItem(c).text()
                           for c in range(self._tbl_rent.columnCount())]
                writer.writerow(headers)
                for row in range(self._tbl_rent.rowCount()):
                    writer.writerow([
                        self._tbl_rent.item(row, col).text() if self._tbl_rent.item(row, col) else ""
                        for col in range(self._tbl_rent.columnCount())
                    ])
            Toast.success(self, "Exportado", f"CSV guardado:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _crear_tarjeta_kpi(self, titulo, valor_inicial):
        """Crea una tarjeta visual estilizada para los indicadores."""
        # CORRECCIÓN: with_layout=False para evitar conflicto de layouts
        tarjeta = create_card(self, with_layout=False)
        layout = QVBoxLayout(tarjeta)

        lbl_titulo = create_caption(self, titulo)
        lbl_titulo.setAlignment(Qt.AlignCenter)

        lbl_valor = create_subheading(self, valor_inicial)
        lbl_valor.setObjectName("textPrimary")  # Color azul primario
        lbl_valor.setAlignment(Qt.AlignCenter)

        layout.addWidget(lbl_titulo)
        layout.addWidget(lbl_valor)
        tarjeta._lbl_valor = lbl_valor   # keep reference on the frame
        return tarjeta
    def _crear_tabla_ranking(self, titulo, headers):
        """Crea un panel con tabla reusable y filtros de búsqueda."""
        grupo = QGroupBox(titulo)
        grupo.setObjectName("styledGroup")
        layout = QVBoxLayout(grupo)

        tabla = DataTableWithFilters(headers=headers, parent=grupo)
        tabla.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        tabla.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout.addWidget(tabla)
        grupo._tabla = tabla
        return grupo

    def _on_global_filters_changed(self, payload: dict) -> None:
        search = (payload or {}).get("search", "").strip().lower()
        wrappers = [self._grp_top._tabla, self._grp_lentos._tabla, self._grp_vips._tabla]
        for wrapper in wrappers:
            wrapper.filter_bar.search.blockSignals(True)
            wrapper.filter_bar.search.setText(search)
            wrapper.filter_bar.search.blockSignals(False)
            wrapper._apply_filter({"search": search})
        self._lbl_rankings_estado.setText(
            "Sin filtros globales activos." if not search else f"Filtro activo: '{search}'"
        )

    def _wire_business_events(self) -> None:
        """Refresco reactivo ante eventos de negocio del ERP.

        Se suscribe a los canales REALES del bus. (Los canales anteriores —
        'venta_confirmada', 'stock_actualizado', 'pago_registrado' — no los
        emite nadie en el repo, por lo que el dashboard nunca se refrescaba
        en caliente.) Debounce de 800 ms para no recargar por cada evento de
        una ráfaga.
        """
        self._bi_refresh_pending = False
        try:
            from core.events.event_bus import (
                get_bus,
                VENTA_COMPLETADA,
                COMPRA_REGISTRADA,
                MOVIMIENTO_FINANCIERO,
                AJUSTE_INVENTARIO,
            )
            # Remediación A: el canal canónico de corte Z de caja (CASH_*) refresca
            # el dashboard BI. El bridge CAJA_*→CASH_* garantiza que cualquier
            # emisor de caja (interactivo o backend) llegue por este canal único.
            from backend.shared.events.event_names import EventName
            bus = get_bus()
            for evt in (VENTA_COMPLETADA, COMPRA_REGISTRADA,
                        MOVIMIENTO_FINANCIERO, AJUSTE_INVENTARIO,
                        EventName.CASH_Z_CUT_GENERATED.value):
                bus.subscribe(evt, self._on_business_event,
                              label=f"bi_v2.refresh.{str(evt).lower()}")
        except Exception:
            pass

    def _on_business_event(self, _payload: dict) -> None:
        """Handler del bus → hilo Qt vía invokeMethod.

        VENTA_COMPLETADA y MOVIMIENTO_FINANCIERO se publican con async_=True,
        así que este handler corre en el ThreadPoolExecutor del bus. Un
        QTimer.singleShot desde ese hilo (sin event loop Qt) no dispararía y
        dejaría el debounce atascado; invokeMethod con QueuedConnection
        despacha el slot en el hilo del widget.
        """
        try:
            QMetaObject.invokeMethod(
                self, "_schedule_business_refresh", Qt.QueuedConnection
            )
        except Exception:
            pass  # widget destruido o Qt no disponible — sin refresh

    @pyqtSlot()
    def _schedule_business_refresh(self) -> None:
        """Corre en el hilo Qt: aplica el debounce de 800 ms."""
        if getattr(self, "_bi_refresh_pending", False):
            return
        self._bi_refresh_pending = True
        try:
            from PyQt5.QtCore import QTimer as _QT
            _QT.singleShot(800, self._do_business_refresh)
        except Exception:
            self._bi_refresh_pending = False

    def _do_business_refresh(self) -> None:
        self._bi_refresh_pending = False
        try:
            self.cargar_dashboard()
        except Exception:
            pass

    def _exportar(self, formato: str) -> None:
        """Exporta el resumen ejecutivo a Excel/PDF vía BiExportService.

        Respeta los filtros activos e incluye usuario, rango y fecha de generación.
        """
        import os, datetime

        export_svc = getattr(self.container, "bi_export_service", None)
        bi_svc = getattr(self.container, "bi_dashboard_service", None)
        if export_svc is None or bi_svc is None:
            QMessageBox.warning(self, "No disponible", "El servicio de BI no está listo.")
            return

        _map = {"excel": ("xlsx", "Excel (*.xlsx)"), "pdf": ("pdf", "PDF (*.pdf)"),
                "csv": ("csv", "CSV (*.csv)")}
        fmt, filtro = _map.get(formato, ("xlsx", "Excel (*.xlsx)"))
        ext = fmt
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        ruta, _ = QFileDialog.getSaveFileName(
            self, f"Guardar {ext.upper()}", f"dashboard_bi_{ts}.{ext}", filtro)
        if not ruta:
            return
        if not confirm_action(
            self, "Confirmar exportación",
            f"¿Deseas exportar el resumen ejecutivo en {ext.upper()}?",
            confirm_text="Sí, exportar", cancel_text="Cancelar"):
            return

        try:
            filters = self._current_filters().resolved()
            payload = bi_svc.build_dashboard(filters).to_dict()
            sucursal = self.cmb_sucursal.currentText() if hasattr(self, "cmb_sucursal") else "Todas"
            meta = {
                "usuario": str(getattr(self, "usuario_actual", "") or "—"),
                "rango": f"{filters.date_from} a {filters.date_to} ({self.cmb_rango.currentText()})",
                "sucursal": sucursal,
                "generado": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            escrito = export_svc.export_summary(payload, meta, ruta, fmt=fmt)
            Toast.success(self, "Exportado", f"Archivo guardado en:\n{escrito}")
            os.startfile(escrito) if os.name == "nt" else None
        except Exception as e:
            QMessageBox.critical(self, "Error al exportar", str(e))

    def cargar_dashboard(self):
        """Pide los datos al AnalyticsEngine (BI unificado) y actualiza la UI."""
        rango_str = self.cmb_rango.currentText().lower().split(' ')[-1] # 'hoy', 'semana', 'mes'
        self.loading_dashboard.setVisible(True)
        
        try:
            # BI unificado: fuente única analytics_engine
            analytics = getattr(self.container, 'analytics_engine', None)
            if not analytics:
                raise RuntimeError("AnalyticsEngine no disponible en el contenedor")
            data = analytics.get_dashboard_data(self.sucursal_id, rango_str)
            self._last_data = data

            # Los KPIs se renderizan en el Dashboard Visual desde el payload
            # (ver _render_echarts_dashboard); ya no hay barra superior que actualizar.

            # Comparativa vs período anterior
            comp = data.get('comparativa', {})
            if comp and hasattr(self, 'lbl_comparativa'):
                prev_ing = comp.get('ingresos', 0)
                curr_ing = data['kpis'].get('ingresos', 0)
                if prev_ing > 0:
                    diff_pct = (curr_ing - prev_ing) / prev_ing * 100
                    arrow = "▲" if diff_pct >= 0 else "▼"
                    color = Colors.SUCCESS_BASE if diff_pct >= 0 else Colors.DANGER_HOVER
                    self.lbl_comparativa.setText(
                        f"<span style='color:{color}'>{arrow} {abs(diff_pct):.1f}% vs período anterior</span>")
                    self.lbl_comparativa.show()
            
            # 2. Llenar Tabla Top Productos
            self._llenar_tabla(self.tabla_top, data['top_productos'], ['nombre', 'cantidad_vendida', 'ingresos_generados'])
            
            # 3. Llenar Tabla Productos Lentos
            self._llenar_tabla(self.tabla_lentos, data['productos_lentos'], ['nombre', 'cantidad_vendida', 'ingresos_generados'])
            
            # 4. Llenar Tabla Clientes VIP
            self._llenar_tabla(self.tabla_vips, data['clientes_recurrentes'], ['nombre', 'visitas', 'valor_vida'])
            top_n = len(data.get('top_productos', []))
            lentos_n = len(data.get('productos_lentos', []))
            vip_n = len(data.get('clientes_recurrentes', []))
            self._lbl_rankings_estado.setText(
                f"Top: {top_n} | Lentos: {lentos_n} | VIP: {vip_n}"
            )
            alertas = []
            if lentos_n > 0:
                alertas.append(f"{lentos_n} productos lentos")
            if top_n == 0:
                alertas.append("sin productos más vendidos")
            self._lbl_resumen_alertas.setText(
                "Alertas: " + (", ".join(alertas) if alertas else "sin alertas relevantes.")
            )
            self._render_echarts_dashboard(data)

        except PermissionError as e:
            # Si el Feature Flag 'bi_v2' está apagado
            QMessageBox.warning(self, "Módulo Inactivo", str(e))
            self._lbl_rankings_estado.setText(f"Módulo inactivo: {e}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo actualizar el dashboard BI.\nDetalle: {e}")
            self._lbl_rankings_estado.setText(f"Error al cargar rankings: {e}")
            self._lbl_resumen_alertas.setText(f"Alertas: error al cargar datos ({e}).")
        finally:
            self.loading_dashboard.setVisible(False)

    _PRESET_MAP = {
        "hoy": "today", "ayer": "yesterday", "esta semana": "week",
        "este mes": "month", "mes pasado": "last_month",
    }

    def _current_filters(self):
        """Construye DashboardFilters desde la barra de filtros globales de la UI."""
        from backend.application.dto.bi_dashboard_dto import DashboardFilters
        preset = self._PRESET_MAP.get(self.cmb_rango.currentText().strip().lower(), "month")
        branch = self.cmb_sucursal.currentData() if hasattr(self, "cmb_sucursal") else ""
        cat = self.cmb_categoria.currentData() if hasattr(self, "cmb_categoria") else ""
        pay = self.cmb_metodo.currentData() if hasattr(self, "cmb_metodo") else ""
        return DashboardFilters(
            preset=preset, branch_id=str(branch or ""),
            category=str(cat or ""), payment_method=str(pay or ""))

    def _current_theme(self) -> str:
        """Tema activo ('dark'/'light'). Preferencia almacenada + fallback paleta."""
        from modulos.bi_theme import normalize_theme
        # 1) Preferencia del usuario (ThemeService — sin SQL en la UI).
        try:
            db = getattr(self.container, "db", None)
            if db is not None:
                from core.services.theme_service import ThemeService
                pref = ThemeService(db).get_user_preferences().get("theme")
                if pref:
                    return normalize_theme(pref)  # 'Oscuro'→dark, 'Claro'→light
        except Exception:
            pass
        # 2) Fallback: luminancia del fondo real del widget.
        try:
            from PyQt5.QtGui import QPalette
            c = self.palette().color(QPalette.Window)
            lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
            return "light" if lum > 140 else "dark"
        except Exception:
            return "dark"

    def _populate_filter_options(self):
        """Rellena los combos de sucursal/categoría/método desde el servicio."""
        svc = getattr(self.container, "bi_dashboard_service", None)
        if svc is None:
            return
        try:
            opts = svc.filter_options()
        except Exception:
            return
        for combo, items in (
            (self.cmb_sucursal, [(b["nombre"], b["id"]) for b in opts.get("branches", [])]),
            (self.cmb_categoria, [(c, c) for c in opts.get("categories", [])]),
            (self.cmb_metodo, [(str(m).replace("_", " ").title(), m)
                               for m in opts.get("payment_methods", [])]),
        ):
            combo.blockSignals(True)
            for label, data in items:
                combo.addItem(label, data)
            combo.blockSignals(False)

    def _on_filters_changed(self, *_):
        """Filtros cambiaron: invalida caché, marca secciones sucias y recarga."""
        svc = getattr(self.container, "bi_dashboard_service", None)
        if svc is not None:
            try:
                svc.invalidate_cache()
            except Exception:
                pass
        self._section_dirty = {k: True for k in getattr(self, "_section_views", {})}
        self.cargar_dashboard()
        self._render_current_section()

    def _limpiar_filtros(self):
        """Restablece los filtros a sus valores por defecto."""
        for combo in (getattr(self, "cmb_sucursal", None), getattr(self, "cmb_categoria", None),
                      getattr(self, "cmb_metodo", None)):
            if combo is not None:
                combo.blockSignals(True)
                combo.setCurrentIndex(0)
                combo.blockSignals(False)
        self.cmb_rango.setCurrentText("Este Mes")  # dispara _on_filters_changed

    # ── Pestañas detalladas por sección (lazy) ────────────────────────────────

    _SECTIONS = [
        ("ventas", "🧾", "Ventas"), ("inventario", "📦", "Inventario"),
        ("compras", "🛒", "Compras"), ("caja", "💵", "Caja"),
        ("clientes", "👥", "Clientes"), ("proveedores", "🚚", "Proveedores"),
        ("finanzas", "💰", "Finanzas"), ("merma", "🗑️", "Merma"),
    ]

    def _build_section_tabs(self):
        self._section_views = {}
        self._section_dirty = {}
        allowed = self._allowed_sections()
        for key, icon, name in self._SECTIONS:
            if key not in allowed:
                continue
            view = self._make_chart_view(min_height=360)
            self._section_views[key] = view
            self._section_dirty[key] = True
            self._add_tab(view, icon, name)

    def _allowed_sections(self):
        svc = getattr(self.container, "bi_dashboard_service", None)
        if svc is None:
            return {k for k, _icon, _name in self._SECTIONS}
        try:
            return set(svc.build_dashboard(self._current_filters()).allowed_sections)
        except Exception:
            return {k for k, _icon, _name in self._SECTIONS}

    def _section_for_view(self, widget):
        for key, view in getattr(self, "_section_views", {}).items():
            if view is widget:
                return key
        return None

    # ── Drill-down (clic en KPI → pestaña destino) ────────────────────────────

    def _install_drilldown(self, view):
        """Intercepta enlaces 'spjdrill:<section>' del web view y navega a la pestaña."""
        try:
            from PyQt5.QtWebEngineWidgets import QWebEnginePage
        except Exception:
            return
        module = self

        class _DrillPage(QWebEnginePage):
            def acceptNavigationRequest(self, url, nav_type, is_main_frame):
                s = url.toString()
                if s.startswith("spjdrill:"):
                    module._go_to_section(s.split(":", 1)[1])
                    return False
                return super().acceptNavigationRequest(url, nav_type, is_main_frame)

        try:
            view.setPage(_DrillPage(view))
        except Exception:
            pass

    def _go_to_section(self, section):
        """Cambia a la pestaña detallada de la sección (si existe y hay permiso)."""
        section = str(section or "").strip()
        view = getattr(self, "_section_views", {}).get(section)
        if view is not None:
            self._render_section(section)
            self.tabs_bi.setCurrentWidget(view)

    def _on_tab_changed(self, _index):
        widget = self.tabs_bi.currentWidget()
        key = self._section_for_view(widget)
        if key:
            self._render_section(key)

    def _render_current_section(self):
        widget = self.tabs_bi.currentWidget() if hasattr(self, "tabs_bi") else None
        key = self._section_for_view(widget)
        if key:
            self._render_section(key)

    def _render_section(self, key):
        view = self._section_views.get(key)
        if view is None or not hasattr(view, "setHtml"):
            return
        if not self._section_dirty.get(key, True):
            return
        svc = getattr(self.container, "bi_dashboard_service", None)
        if svc is None:
            return
        from modulos.bi_dashboard_view import render_section_html
        try:
            data = svc.section_data(key, self._current_filters())
            view.setHtml(render_section_html(data, theme=self._current_theme()))
            self._section_dirty[key] = False
        except Exception:
            pass

    # ── Reportes (exportación ejecutiva) ──────────────────────────────────────

    def _build_reportes_tab(self):
        if "reportes" not in self._allowed_sections():
            return
        tab = QWidget()
        layout = QVBoxLayout(tab)
        titulo = QLabel("📄 Reportes — exportación del resumen ejecutivo")
        titulo.setObjectName("heading")
        layout.addWidget(titulo)
        info = QLabel("Exporta el resumen ejecutivo respetando los filtros activos. "
                      "Incluye usuario, periodo, sucursal y fecha de generación.")
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{Colors.NEUTRAL.DARK_TEXT_SEC}; font-size:11px;")
        layout.addWidget(info)

        fila = QHBoxLayout()
        btn_xlsx = create_success_button(self, "📊 Excel (.xlsx)", "Exportar resumen a Excel")
        btn_xlsx.clicked.connect(lambda: self._exportar("excel"))
        btn_pdf = create_danger_button(self, "📄 PDF", "Exportar resumen a PDF")
        btn_pdf.clicked.connect(lambda: self._exportar("pdf"))
        btn_csv = create_secondary_button(self, "🧾 CSV", "Exportar resumen a CSV")
        btn_csv.clicked.connect(lambda: self._exportar("csv"))
        fila.addWidget(btn_xlsx)
        fila.addWidget(btn_pdf)
        fila.addWidget(btn_csv)
        fila.addStretch()
        layout.addLayout(fila)
        layout.addStretch()
        self._add_tab(tab, "📄", "Reportes")

    # ── Configuración BI (metas, umbrales, forecast) ──────────────────────────

    _CONFIG_SPECS = [
        ("threshold_merma_pct", "Umbral merma alta (%)", "%"),
        ("threshold_margen_bajo_pct", "Umbral margen bajo (%)", "%"),
        ("threshold_caida_ventas_pct", "Umbral caída de ventas (%)", "%"),
        ("threshold_cxc_aumento_pct", "Umbral aumento CxC (%)", "%"),
        ("threshold_compras_aumento_pct", "Umbral aumento compras (%)", "%"),
        ("meta_ventas_periodo", "Meta de ventas del periodo ($)", "$"),
    ]

    def _build_config_tab(self):
        if "configuracion" not in self._allowed_sections():
            return
        settings = getattr(self.container, "bi_settings_service", None)
        if settings is None:
            return
        from PyQt5.QtWidgets import QFormLayout
        tab = QWidget()
        layout = QVBoxLayout(tab)
        titulo = QLabel("⚙️ Configuración BI — metas, umbrales de alertas y forecast")
        titulo.setObjectName("heading")
        layout.addWidget(titulo)

        form = QFormLayout()
        self._config_inputs = {}
        for key, label, unit in self._CONFIG_SPECS:
            spin = QDoubleSpinBox()
            spin.setDecimals(2)
            spin.setMaximum(1_000_000_000.0)
            spin.setSingleStep(1.0)
            spin.setSuffix(f" {unit}")
            spin.setValue(float(settings.get(key)))
            self._config_inputs[key] = spin
            form.addRow(label, spin)

        self._config_forecast = QSpinBox()
        self._config_forecast.setMaximum(365)
        self._config_forecast.setSuffix(" días")
        self._config_forecast.setValue(int(settings.get("forecast_window_days")))
        form.addRow("Ventana de forecast", self._config_forecast)
        layout.addLayout(form)

        botones = QHBoxLayout()
        btn_guardar = create_primary_button(self, "💾 Guardar", "Guardar configuración de BI")
        btn_guardar.clicked.connect(self._save_config)
        btn_reset = create_secondary_button(self, "↩️ Restablecer", "Restablecer valores por defecto")
        btn_reset.clicked.connect(self._reset_config)
        botones.addWidget(btn_guardar)
        botones.addWidget(btn_reset)
        botones.addStretch()
        layout.addLayout(botones)
        layout.addStretch()
        self._add_tab(tab, "⚙️", "Configuración")

    def _save_config(self):
        settings = getattr(self.container, "bi_settings_service", None)
        svc = getattr(self.container, "bi_dashboard_service", None)
        if settings is None:
            return
        try:
            for key, spin in self._config_inputs.items():
                settings.set(key, spin.value())
            settings.set("forecast_window_days", self._config_forecast.value())
            if svc is not None:
                svc.invalidate_cache()
            self._section_dirty = {k: True for k in getattr(self, "_section_views", {})}
            self.cargar_dashboard()
            Toast.success(self, "Configuración guardada", "Los umbrales de BI se actualizaron.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _reset_config(self):
        settings = getattr(self.container, "bi_settings_service", None)
        if settings is None:
            return
        defaults = settings.defaults
        for key, spin in self._config_inputs.items():
            spin.setValue(float(defaults.get(key, 0)))
        self._config_forecast.setValue(int(defaults.get("forecast_window_days", 30)))
        self._save_config()

    def _render_echarts_dashboard(self, data: dict) -> None:
        """Dashboard visual compuesto consumiendo BiDashboardService (payload).

        Canonical route: UI → BiDashboardService → query services → DB. La UI sólo
        transforma el payload en paneles SVG (offline, sin CDN).
        """
        svc = getattr(self.container, "bi_dashboard_service", None)
        if svc is None:
            return
        from modulos.bi_dashboard_view import render_dashboard_html
        try:
            payload = svc.build_dashboard(self._current_filters()).to_dict()
        except Exception:
            return

        # KPIs como tarjetas nativas (estilo Inventario) — siempre, aunque el
        # web view de gráficas no esté disponible en este entorno.
        self._update_kpi_cards(payload.get("kpis", []))

        if not getattr(self, "_chart_view", None):
            return
        # ¿Hay datos? (al menos una KPI de ventas > 0 o algún chart con valores)
        kpis = {k["key"]: k for k in payload.get("kpis", [])}
        ventas = float(kpis.get("ventas_netas", {}).get("value", 0) or 0)
        if ventas <= 0 and not payload.get("charts"):
            self._chart_empty.show()
            self._chart_view.hide()
            return
        self._chart_empty.hide()
        self._chart_view.show()
        self._chart_view.setHtml(render_dashboard_html(
            payload, theme=self._current_theme(), include_kpis=False))

    # ── KPI cards nativas (iguales a las del módulo Inventario) ────────────────

    @staticmethod
    def _fmt_kpi(k: dict) -> str:
        v = float(k.get("value", 0) or 0)
        u = k.get("unit", "")
        if u == "%":
            return f"{v:.1f}%"
        if u == "x":
            return f"{v:.2f}x"
        if u == "":
            return f"{int(round(v)):,}"
        return f"${v:,.0f}"

    @staticmethod
    def _kpi_tooltip(k: dict) -> str:
        dp, pts = k.get("delta_pct"), k.get("delta_points")
        comp = (f"{dp:+.1f}% vs periodo anterior" if dp is not None
                else f"{pts:+.2f} pp vs periodo anterior" if pts is not None else "")
        base = k.get("tooltip") or k.get("formula") or ""
        return " · ".join(x for x in (base, comp) if x)

    def _update_kpi_cards(self, kpis: list) -> None:
        """Crea (una vez) y actualiza la fila de KPICard nativas desde el payload."""
        if not hasattr(self, "_kpi_grid"):
            return
        from modulos.kpi_card import KPICard
        if not self._kpi_cards:
            cols = 5
            for i, k in enumerate(kpis):
                card = KPICard(k.get("title", ""), self._fmt_kpi(k),
                               k.get("icon", "📊"), k.get("variant", "primary"))
                card.setToolTip(self._kpi_tooltip(k))
                self._kpi_cards[k["key"]] = card
                drill = k.get("drilldown", "")
                widget = card
                if drill:
                    btn = QPushButton()
                    btn.setFlat(True)
                    btn.setCursor(Qt.PointingHandCursor)
                    bl = QHBoxLayout(btn)
                    bl.setContentsMargins(0, 0, 0, 0)
                    bl.addWidget(card)
                    btn.clicked.connect(lambda _, s=drill: self._go_to_section(s))
                    widget = btn
                self._kpi_grid.addWidget(widget, i // cols, i % cols)
        else:
            for k in kpis:
                card = self._kpi_cards.get(k["key"])
                if card is not None:
                    card.set_valor(self._fmt_kpi(k))
                    card.setToolTip(self._kpi_tooltip(k))

    def changeEvent(self, event):
        """Re-renderiza las gráficas al cambiar el tema (paleta) de la app."""
        try:
            from PyQt5.QtCore import QEvent
            if event.type() in (QEvent.PaletteChange, QEvent.StyleChange,
                                QEvent.ApplicationPaletteChange):
                if getattr(self, "_chart_view", None) is not None:
                    self._render_echarts_dashboard({})
                self._section_dirty = {k: True for k in getattr(self, "_section_views", {})}
                self._render_current_section()
        except Exception:
            pass
        super().changeEvent(event)

    # ── Chart helpers reutilizables por pestaña (offline SVG) ─────────────────

    def _make_chart_view(self, min_height: int = 260):
        """Crea una vista de gráfica (QWebEngineView) con fallback si no existe."""
        try:
            from PyQt5.QtWebEngineWidgets import QWebEngineView
            view = QWebEngineView(self)
            view.setMinimumHeight(min_height)
            return view
        except Exception:
            lbl = QLabel("Gráfica no disponible (QWebEngine ausente).")
            lbl.setStyleSheet("color:#6c757d; padding:10px;")
            lbl.setAlignment(Qt.AlignCenter)
            return lbl

    def _set_chart(self, view, html: str) -> None:
        """Coloca HTML en la vista si soporta setHtml (QWebEngineView)."""
        if view is not None and hasattr(view, "setHtml"):
            view.setHtml(html)

    def _llenar_tabla(self, tabla: QTableWidget, datos: list, llaves: list):
        if not datos:
            tabla.setRowCount(1)
            tabla.setItem(0, 0, QTableWidgetItem("Sin datos para el período seleccionado."))
            for col in range(1, tabla.columnCount()):
                tabla.setItem(0, col, QTableWidgetItem(""))
            if hasattr(tabla.parent(), "empty_state"):
                tabla.parent().empty_state.show()
            return
        tabla.setRowCount(len(datos))
        if hasattr(tabla.parent(), "empty_state"):
            tabla.parent().empty_state.hide()
        for row, item in enumerate(datos):
            for col, llave in enumerate(llaves):
                valor = item.get(llave, '')
                # Dar formato de moneda si es dinero
                if isinstance(valor, (float, int)) and ('ingresos' in llave or 'valor' in llave):
                    txt = f"${valor:,.2f}"
                else:
                    txt = str(valor)
                    
                celda = QTableWidgetItem(txt)
                if col > 0: celda.setTextAlignment(Qt.AlignCenter)
                tabla.setItem(row, col, celda)
