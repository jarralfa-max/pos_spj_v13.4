
# modulos/reportes_bi_v2.py
from modulos.design_tokens import Colors, Spacing, Typography, Borders, Shadows
from modulos.ui_components import (
    create_primary_button, create_success_button, create_danger_button, 
    create_secondary_button, create_input, create_combo, create_card,
    create_heading, create_subheading, create_caption, apply_tooltip
)
from modulos.spj_styles import spj_btn, apply_btn_styles
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QMessageBox, QFormLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QGridLayout, QGroupBox, QFrame, QSplitter, QTabWidget,
    QAbstractItemView, QDialog, QCheckBox, QListWidget, QListWidgetItem,
    QSizePolicy, QAction, QMenu, QToolBar, QStatusBar, QProgressBar,
    QScrollArea, QCompleter, QDateEdit, QSpinBox, QDoubleSpinBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

class ModuloReportesBIv2(QWidget):
    """
    Dashboard Corporativo de Business Intelligence.
    Cero SQL. Toda la data proviene del BIService.
    """
    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container = container
        self.sucursal_id = 1
        self.init_ui()

    def set_usuario_actual(self, usuario: str, rol: str = "cajero") -> None:
        """Recibe el usuario activo al cambiar de sesión."""
        self.usuario_actual = usuario
        self.rol_actual = rol

    def set_sucursal(self, sucursal_id: int, nombre: str = "") -> None:
        """Recibe la sucursal activa."""
        self.sucursal_id = sucursal_id

    def set_sucursal(self, sucursal_id: int, nombre_sucursal: str):
        self.sucursal_id = sucursal_id
        self.cargar_dashboard()

    def init_ui(self):
        layout_principal = QVBoxLayout(self)
        layout_principal.setSpacing(20)

        # --- HEADER Y FILTROS ---
        header_layout = QHBoxLayout()
        
        lbl_titulo = create_heading(self, "📈 Inteligencia Comercial (Dashboard)")
        header_layout.addWidget(lbl_titulo)
        
        header_layout.addStretch()
        
        self.cmb_rango = create_combo(self, ["Hoy", "Esta Semana", "Este Mes"])
        self.cmb_rango.currentTextChanged.connect(self.cargar_dashboard)
        
        self.btn_actualizar = create_secondary_button(self, "🔄 Refrescar", "Actualizar datos del dashboard")
        self.btn_actualizar.clicked.connect(self.cargar_dashboard)

        btn_excel = create_success_button(self, "📊 Excel", "Exportar dashboard a Excel (.xlsx)")
        btn_excel.clicked.connect(lambda: self._exportar("excel"))

        btn_pdf = create_danger_button(self, "📄 PDF", "Exportar dashboard a PDF")
        btn_pdf.clicked.connect(lambda: self._exportar("pdf"))

        header_layout.addWidget(QLabel("Período:"))
        header_layout.addWidget(self.cmb_rango)
        header_layout.addWidget(self.btn_actualizar)
        header_layout.addWidget(btn_excel)
        header_layout.addWidget(btn_pdf)
        
        layout_principal.addLayout(header_layout)

        # --- FILA 1: KPIs (TARJETAS) ---
        kpi_layout = QHBoxLayout()
        
        self.lbl_kpi_ingresos = self._crear_tarjeta_kpi("💵 Ingresos Totales", "$0.00")
        self.lbl_kpi_ticket = self._crear_tarjeta_kpi("🧾 Ticket Promedio", "$0.00")
        self.lbl_kpi_ventas = self._crear_tarjeta_kpi("🛒 Num. Ventas", "0")
        self.lbl_kpi_clientes = self._crear_tarjeta_kpi("👥 Clientes Únicos", "0")
        
        kpi_layout.addWidget(self.lbl_kpi_ingresos)
        kpi_layout.addWidget(self.lbl_kpi_ticket)
        kpi_layout.addWidget(self.lbl_kpi_ventas)
        kpi_layout.addWidget(self.lbl_kpi_clientes)
        
        layout_principal.addLayout(kpi_layout)

        self.lbl_comparativa = create_caption(self, "")
        self.lbl_comparativa.setAlignment(Qt.AlignCenter)
        self.lbl_comparativa.hide()
        layout_principal.addWidget(self.lbl_comparativa)

        # --- FILA 2: TABLAS DE RANKING ---
        tablas_layout = QHBoxLayout()
        
        # Productos Estrella
        self._grp_top = self._crear_tabla_ranking("⭐ Productos Más Vendidos", ["Producto", "Cant.", "Ingresos"])
        self.tabla_top = self._grp_top._tabla
        # Productos Lentos
        self._grp_lentos = self._crear_tabla_ranking("🐢 Productos Lentos", ["Producto", "Cant.", "Ingresos"])
        self.tabla_lentos = self._grp_lentos._tabla
        # Clientes VIP
        self._grp_vips = self._crear_tabla_ranking("👑 Clientes Recurrentes (VIP)", ["Cliente", "Visitas", "Gasto Total"])
        self.tabla_vips = self._grp_vips._tabla

        tablas_layout.addWidget(self.tabla_top)
        tablas_layout.addWidget(self.tabla_lentos)
        tablas_layout.addWidget(self.tabla_vips)
        
        layout_principal.addLayout(tablas_layout)

        # ── Rentabilidad por producto (tab adicional) ─────────────────────────
        self._build_rentabilidad_section(layout_principal)
        self._build_cajeros_section(layout_principal)
        self._build_decision_engine_section(layout_principal)
        self._build_franchise_section(layout_principal)

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
        hh = self._tbl_rent.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        self._tbl_rent.setMaximumHeight(240)
        lay.addWidget(self._tbl_rent)

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
        self._tbl_caj.setMaximumHeight(240)
        lay.addWidget(self._tbl_caj)

        parent_layout.addWidget(grp)

    def _cargar_cajeros(self):
        """Carga ranking de cajeros via BIService.ranking_cajeros()."""
        self._tbl_caj.setRowCount(0)
        try:
            bi_svc = getattr(self.container, "bi_service", None)
            if bi_svc is None:
                self._lbl_caj_estado.setText("BIService no disponible.")
                return
            rango = self.cmb_rango.currentText()
            rango_key = "hoy" if "hoy" in rango.lower() else \
                        "semana" if "semana" in rango.lower() else "mes"
            rows = bi_svc.ranking_cajeros(self.sucursal_id, rango_key)
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
        self._tbl_de.setMaximumHeight(280)
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
        self._tbl_fm.setMaximumHeight(220)
        lay.addWidget(self._tbl_fm)

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
                    f"${float(r.get('total_ventas', 0)):,.2f}",
                    str(r.get("num_transacciones", 0)),
                    f"${float(r.get('ticket_promedio', 0)):,.2f}",
                    f"{float(r.get('margen_bruto_pct', 0)):.1f}%",
                    str(r.get("rank", i + 1)),
                ]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(str(v))
                    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self._tbl_fm.setItem(i, j, item)
        except Exception as exc:
            self._lbl_fm_estado.setText(f"Error: {exc}")

    def _cargar_rentabilidad(self):
        """Carga el reporte de rentabilidad por producto para el período activo."""
        self._tbl_rent.setRowCount(0)
        rango = self.cmb_rango.currentText()
        filtro_fecha = {
            "Hoy":          "DATE(v.fecha)=DATE('now')",
            "Esta Semana":  "v.fecha >= DATE('now','weekday 0','-7 days')",
            "Este Mes":     "strftime('%Y-%m',v.fecha)=strftime('%Y-%m','now')",
        }.get(rango, "DATE(v.fecha)=DATE('now')")
        try:
            rows = self.container.db.execute(f"""
                SELECT p.nombre, p.categoria,
                       SUM(vd.cantidad) as unidades,
                       SUM(vd.cantidad * vd.precio_unitario) as ingresos,
                       SUM(vd.cantidad * COALESCE(p.precio_compra,0)) as costo_total
                FROM ventas v
                JOIN detalles_venta vd ON vd.venta_id=v.id
                JOIN productos p ON p.id=vd.producto_id
                WHERE v.estado='completada' AND {filtro_fecha}
                GROUP BY p.id, p.nombre, p.categoria
                ORDER BY (SUM(vd.cantidad * vd.precio_unitario) -
                          SUM(vd.cantidad * COALESCE(p.precio_compra,0))) DESC
                LIMIT 50
            """).fetchall()
        except Exception as e:
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
            QMessageBox.information(self, "Exportado", f"CSV guardado:\n{path}")
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
        """Crea un panel con una tabla limpia para los rankings.
        Returns the QGroupBox (parent kept alive) with _tabla attribute."""
        grupo = QGroupBox(titulo)
        grupo.setObjectName("styledGroup")
        layout = QVBoxLayout(grupo)
        
        tabla = QTableWidget()
        tabla.setColumnCount(len(headers))
        tabla.setHorizontalHeaderLabels(headers)
        tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        tabla.verticalHeader().setVisible(False)
        tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tabla.setObjectName("tableView")
        
        layout.addWidget(tabla)
        grupo._tabla = tabla   # keep strong reference on the container
        return grupo           # return the container, not the tabla

    def _exportar(self, formato: str) -> None:
        """Exporta el dashboard actual a PDF o Excel via ExportService."""
        # [spj-dedup removed local QMessageBox import]
        import os, datetime

        rango = self.cmb_rango.currentText()
        ts    = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        ext   = "xlsx" if formato == "excel" else "pdf"
        nombre_default = f"dashboard_bi_{ts}.{ext}"

        ruta, _ = QFileDialog.getSaveFileName(
            self, f"Guardar {ext.upper()}", nombre_default,
            f"{'Excel (*.xlsx)' if formato == 'excel' else 'PDF (*.pdf)'}"
        )
        if not ruta:
            return

        try:
            from core.services.export_service import ExportService
            svc  = ExportService(self.container.db)
            data = self.container.bi_service.get_dashboard_data(
                self.sucursal_id,
                rango.lower().split(" ")[-1]
            )
            if formato == "excel":
                sheets = {
                    "KPIs": [data["kpis"]],
                    "Top Productos":    data.get("top_productos", []),
                    "Productos Lentos": data.get("productos_lentos", []),
                    "Clientes VIP":     data.get("clientes_recurrentes", []),
                }
                result = svc.export_ventas(fmt="xlsx")
                # Write our structured BI export
                import openpyxl
                wb = openpyxl.Workbook()
                for sheet_name, rows in sheets.items():
                    ws = wb.create_sheet(title=sheet_name[:31])
                    if rows:
                        ws.append(list(rows[0].keys()))
                        for row in rows:
                            ws.append([str(v) for v in row.values()])
                if "Sheet" in wb.sheetnames:
                    del wb["Sheet"]
                wb.save(ruta)
            else:
                # PDF via ReportEngine if available
                try:
                    from core.services.enterprise.report_engine import ReportEngine
                    engine = ReportEngine(self.container.db)
                    engine.export_pdf("dashboard", data, filepath=ruta)
                except Exception:
                    # Simple PDF fallback
                    svc.export(
                        "SELECT folio, total, fecha FROM ventas "
                        "WHERE DATE(fecha)=DATE('now') ORDER BY fecha DESC LIMIT 500",
                        (), fmt="pdf", filepath=ruta
                    )
            QMessageBox.information(
                self, "✅ Exportado",
                f"Archivo guardado en:\n{ruta}"
            )
            os.startfile(ruta) if os.name == "nt" else None
        except Exception as e:
            QMessageBox.critical(self, "Error al exportar", str(e))

    def cargar_dashboard(self):
        """Pide los datos al BIService y actualiza la UI."""
        rango_str = self.cmb_rango.currentText().lower().split(' ')[-1] # 'hoy', 'semana', 'mes'
        
        try:
            # 🚀 LLAMADA ENTERPRISE: Un solo viaje al backend
            data = self.container.bi_service.get_dashboard_data(self.sucursal_id, rango_str)
            
            # 1. Actualizar KPIs
            self.lbl_kpi_ingresos._lbl_valor.setText(f"${data['kpis']['ingresos']:,.2f}")
            self.lbl_kpi_ticket._lbl_valor.setText(f"${data['kpis']['ticket_promedio']:,.2f}")
            self.lbl_kpi_ventas._lbl_valor.setText(str(data['kpis']['tickets']))
            self.lbl_kpi_clientes._lbl_valor.setText(str(data['kpis']['clientes_unicos']))

            # Comparativa vs período anterior
            comp = data.get('comparativa', {})
            if comp and hasattr(self, 'lbl_comparativa'):
                prev_ing = comp.get('ingresos', 0)
                curr_ing = data['kpis'].get('ingresos', 0)
                if prev_ing > 0:
                    diff_pct = (curr_ing - prev_ing) / prev_ing * 100
                    arrow = "▲" if diff_pct >= 0 else "▼"
                    color = "#27ae60" if diff_pct >= 0 else "#e74c3c"
                    self.lbl_comparativa.setText(
                        f"<span style='color:{color}'>{arrow} {abs(diff_pct):.1f}% vs período anterior</span>")
                    self.lbl_comparativa.show()
            
            # 2. Llenar Tabla Top Productos
            self._llenar_tabla(self.tabla_top, data['top_productos'], ['nombre', 'cantidad_vendida', 'ingresos_generados'])
            
            # 3. Llenar Tabla Productos Lentos
            self._llenar_tabla(self.tabla_lentos, data['productos_lentos'], ['nombre', 'cantidad_vendida', 'ingresos_generados'])
            
            # 4. Llenar Tabla Clientes VIP
            self._llenar_tabla(self.tabla_vips, data['clientes_recurrentes'], ['nombre', 'visitas', 'valor_vida'])

        except PermissionError as e:
            # Si el Feature Flag 'bi_v2' está apagado
            QMessageBox.warning(self, "Módulo Inactivo", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _llenar_tabla(self, tabla: QTableWidget, datos: list, llaves: list):
        tabla.setRowCount(len(datos))
        for row, item in enumerate(datos):
            for col, llave in enumerate(llaves):
                valor = item.get(llave, '')
                # Dar formato de moneda si es dinero
                if isinstance(valor, float) and 'ingresos' in llave or 'valor' in llave:
                    txt = f"${valor:,.2f}"
                else:
                    txt = str(valor)
                    
                celda = QTableWidgetItem(txt)
                if col > 0: celda.setTextAlignment(Qt.AlignCenter)
                tabla.setItem(row, col, celda)