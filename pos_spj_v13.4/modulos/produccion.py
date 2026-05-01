# -*- coding: utf-8 -*-
# modulos/produccion.py
# ── ModuloProduccion — Ventana de Producción Industrial ──────────────────────
#
# Soporta los 3 tipos de receta:
#   SUBPRODUCTO  — despiece (pollo entero → pechuga, pierna, ala, etc.)
#   COMBINACION  — kits/paquetes (surtido = 1kg pierna + 1kg pechuga)
#   PRODUCCION   — elaboración (pollo marinado = pechuga + especias)
#
# Características:
#   ✔ Vista previa de movimientos antes de ejecutar
#   ✔ Validación de stock en tiempo real
#   ✔ Historial de producciones con detalle
#   ✔ Actualización automática vía EventBus
#   ✔ Integración con RecipeEngine (atómico, BEGIN IMMEDIATE)
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget,
)

from core.events.event_bus import EventBus, get_bus
from core.services.auto_audit import audit_write
from core.services.recipe_engine import (
    RecipeEngine,
    RecipeEngineError,
    RecetaNoEncontradaError,
    StockInsuficienteProduccionError,
    ProduccionDuplicadaError,
)
from modulos.design_tokens import Colors, Spacing, Typography, Borders, Shadows
from modulos.spj_styles import apply_btn_styles, spj_btn
from modulos.ui_components import (
    EmptyStateWidget,
    FilterBar,
    LoadingIndicator,
    apply_tooltip,
    create_card,
    create_caption,
    create_combo,
    create_danger_button,
    create_heading,
    create_input,
    create_primary_button,
    create_secondary_button,
    create_subheading,
    create_success_button,
)

from .base import ModuloBase

logger = logging.getLogger("spj.ui.produccion")

# ── Color aliases from design tokens (single source of truth) ─────────────────
_RED   = Colors.DANGER_BASE
_BLUE  = Colors.PRIMARY_BASE
_GREEN = Colors.SUCCESS_BASE
_GOLD  = Colors.WARNING_BASE
_GRAY  = Colors.TEXT_SECONDARY

TIPO_LABELS = {
    "subproducto": "🔪 Despiece / Subproductos",
    "combinacion": "📦 Kit / Paquete / Combo",
    "produccion":  "🍳 Producción / Elaboración",
}
TIPO_COLOR = {
    "subproducto": Colors.DANGER_BASE,
    "combinacion": Colors.PRIMARY_BASE,
    "produccion":  Colors.SUCCESS_BASE,
}


# ── DB Wrapper ────────────────────────────────────────────────────────────────

class _DBWrapperProd:
    """Minimal DB wrapper for RecipeEngine compatibility with raw sqlite3.Connection."""

    def __init__(self, conexion):
        self.conn = conexion

    def fetchone(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()

    def fetchall(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()

    def execute(self, sql, params=()):
        return self.conn.execute(sql, params)

    def commit(self):
        try:
            self.conn.commit()
        except Exception:
            pass

    def rollback(self):
        try:
            self.conn.rollback()
        except Exception:
            pass

    from contextlib import contextmanager

    @contextmanager
    def transaction(self, name=""):
        from core.db.connection import transaction as _canonical_tx
        with _canonical_tx(self.conn):
            yield self


# ── Main Module ───────────────────────────────────────────────────────────────

class ModuloProduccion(ModuloBase):
    """
    Ventana de producción industrial. Tabs:
        [0] Ejecutar Producción   — formulario + preview
        [1] Historial             — registro de producciones pasadas
        [2] Cárnica / Lotes       — lote cárnico rápido
        [3] Recetas               — CRUD de recetas
    """

    def __init__(self, conexion, parent=None):
        # conexion puede ser AppContainer o sqlite3.Connection
        if hasattr(conexion, 'db'):
            self.container = conexion
            db_conn = conexion.db
        else:
            self.container = None
            db_conn = conexion
        super().__init__(db_conn, parent)
        from core.db.connection import wrap
        self.conexion        = wrap(db_conn)
        self.main_window     = parent
        self.sucursal_id     = 1
        self.sucursal_nombre = "Principal"
        self.usuario_actual  = "Sistema"
        self._db_wrapped     = self.conexion
        self._engine         = RecipeEngine(self._db_wrapped, branch_id=1)
        self._recetas_cache: List[Dict] = []
        self._ui_ready = False
        self._init_ui()
        self._subscribe_events()
        QTimer.singleShot(0, self._refresh_all)

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_sucursal(self, sucursal_id: int, sucursal_nombre: str) -> None:
        self.sucursal_id     = sucursal_id
        self.sucursal_nombre = sucursal_nombre
        self._db_wrapped = self.conexion
        self._engine = RecipeEngine(self._db_wrapped, branch_id=sucursal_id)

    def set_usuario_actual(self, usuario: str, rol: str = "") -> None:
        self.usuario_actual = usuario or "Sistema"

    def obtener_usuario_actual(self) -> str:
        return self.usuario_actual

    def limpiar(self) -> None:
        for evt in ("PRODUCCION_COMPLETADA", "RECETA_CREADA", "RECETA_ACTUALIZADA",
                    "INVENTARIO_ACTUALIZADO"):
            try:
                EventBus.unsubscribe(evt, self._on_data_changed)
            except Exception:
                pass

    # ── Events ─────────────────────────────────────────────────────────────────

    def _subscribe_events(self) -> None:
        for evt in ("PRODUCCION_COMPLETADA", "RECETA_CREADA", "RECETA_ACTUALIZADA",
                    "INVENTARIO_ACTUALIZADO"):
            EventBus().subscribe(evt, self._on_data_changed)

    def _on_data_changed(self, _data: dict) -> None:
        QTimer.singleShot(0, self._refresh_all)

    def _refresh_all(self) -> None:
        if not getattr(self, '_ui_ready', False):
            return
        self._lbl_suc.setText(f"Sucursal: {self.sucursal_nombre}")
        self._load_recetas()
        self._load_historial()

    # ── Root UI ────────────────────────────────────────────────────────────────

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        root.setSpacing(Spacing.SM)

        root.addLayout(self._crear_header())
        root.addWidget(self._crear_kpis())

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_tab_produccion(), "🏭 Ejecutar Producción")
        self._tabs.addTab(self._build_tab_historial(),  "📋 Historial")
        self._tabs.addTab(self._build_tab_carnica(),    "🥩 Cárnica / Lotes")
        self._tabs.addTab(self._build_tab_recetas(),    "📋 Recetas")
        root.addWidget(self._tabs)

        # Must be last — guards _refresh_all from firing on unbuilt widgets
        self._ui_ready = True

    def _crear_header(self) -> QHBoxLayout:
        """Top row: title + branch badge."""
        hdr = QHBoxLayout()
        hdr.setSpacing(Spacing.SM)

        ttl = QLabel("🔪 Procesamiento Cárnico")
        ttl.setObjectName("heading")
        ttl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self._lbl_suc = QLabel()
        self._lbl_suc.setObjectName("textSecondary")
        self._lbl_suc.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        hdr.addWidget(ttl)
        hdr.addStretch()
        hdr.addWidget(self._lbl_suc)
        return hdr

    def _crear_kpis(self) -> QFrame:
        """KPI strip below the header: recipe count, branch, user."""
        frame = QFrame()
        frame.setObjectName("card")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        lay = QHBoxLayout(frame)
        lay.setContentsMargins(Spacing.MD, Spacing.XS, Spacing.MD, Spacing.XS)
        lay.setSpacing(Spacing.XL)

        self._kpi_recetas = self._kpi_block("Recetas activas", "—")
        self._kpi_usuario = self._kpi_block("Usuario", self.usuario_actual)
        self._kpi_sucursal = self._kpi_block("Sucursal", self.sucursal_nombre)

        lay.addWidget(self._kpi_recetas)
        lay.addWidget(self._kpi_usuario)
        lay.addWidget(self._kpi_sucursal)
        lay.addStretch()
        return frame

    @staticmethod
    def _kpi_block(label: str, value: str) -> QWidget:
        """Single KPI cell: label on top, value below."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        lbl = QLabel(label)
        lbl.setObjectName("caption")
        val = QLabel(value)
        val.setObjectName("subheading")
        val.setObjectName("kpiValue")
        v.addWidget(lbl)
        v.addWidget(val)
        return w

    # ── TAB: Ejecutar Producción ───────────────────────────────────────────────

    def _build_tab_produccion(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        lay.setSpacing(Spacing.SM)

        sp = QSplitter(Qt.Horizontal)
        sp.addWidget(self._crear_formulario())
        sp.addWidget(self._crear_panel_preview())
        sp.setSizes([320, 500])

        lay.addWidget(sp)
        return w

    def _crear_formulario(self) -> QGroupBox:
        """Left panel: recipe selector + quantity + notes + stock indicator."""
        grp = QGroupBox("Configuración de Producción")
        grp.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        fl = QVBoxLayout(grp)
        fl.setSpacing(Spacing.SM)
        fl.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)

        # ── Recipe selector ──────────────────────────────────────────────────
        form = QFormLayout()
        form.setSpacing(Spacing.SM)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._combo_receta = QComboBox()
        self._combo_receta.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._combo_receta.currentIndexChanged.connect(self._on_receta_changed)
        form.addRow("Receta:", self._combo_receta)

        self._lbl_tipo = QLabel()
        self._lbl_tipo.setObjectName("badge")
        form.addRow("Tipo:", self._lbl_tipo)

        self._lbl_base = QLabel()
        self._lbl_base.setObjectName("caption")
        self._lbl_base.setWordWrap(True)
        form.addRow("Base:", self._lbl_base)

        # ── Quantity row ─────────────────────────────────────────────────────
        qty_w = QWidget()
        qty_row = QHBoxLayout(qty_w)
        qty_row.setContentsMargins(0, 0, 0, 0)
        qty_row.setSpacing(Spacing.XS)

        self._spin_cant = QDoubleSpinBox()
        self._spin_cant.setRange(0.001, 999999)
        self._spin_cant.setDecimals(3)
        self._spin_cant.setValue(1.0)
        self._spin_cant.setSingleStep(0.5)
        self._spin_cant.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._spin_cant.valueChanged.connect(self._on_cant_changed)

        self._lbl_unidad = QLabel("kg")
        self._lbl_unidad.setObjectName("textSecondary")
        self._lbl_unidad.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        qty_row.addWidget(self._spin_cant)
        qty_row.addWidget(self._lbl_unidad)
        form.addRow("Cantidad base:", qty_w)

        self._e_notas = QLineEdit()
        self._e_notas.setPlaceholderText("Observaciones de esta producción…")
        form.addRow("Notas:", self._e_notas)

        fl.addLayout(form)
        fl.addStretch()

        # ── Stock indicator ──────────────────────────────────────────────────
        self._grp_stock = QGroupBox("Stock disponible")
        sl = QVBoxLayout(self._grp_stock)
        sl.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        self._lbl_stock = QLabel("—")
        self._lbl_stock.setObjectName("subheading")
        sl.addWidget(self._lbl_stock)
        fl.addWidget(self._grp_stock)

        # ── Action buttons ───────────────────────────────────────────────────
        btn_preview = create_primary_button(
            self, "🔍 Vista Previa", "Ver movimientos antes de ejecutar producción"
        )
        btn_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn_preview.clicked.connect(self._preview)
        fl.addWidget(btn_preview)

        self._btn_ejecutar = create_success_button(
            self, "▶ EJECUTAR PRODUCCIÓN", "Ejecutar producción con validación de stock"
        )
        self._btn_ejecutar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_ejecutar.clicked.connect(self._ejecutar)
        fl.addWidget(self._btn_ejecutar)

        return grp

    def _crear_panel_preview(self) -> QGroupBox:
        """Right panel: movement preview table + summary label."""
        grp = QGroupBox("Vista Previa de Movimientos")
        grp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        rl = QVBoxLayout(grp)
        rl.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)

        self._tbl_prev = self._crear_tabla(
            cols=["Movimiento", "Producto", "Cantidad", "Unidad", "Stock Actual"],
            stretch_col=1,
            number_cols=(2, 4),
        )
        rl.addWidget(self._tbl_prev)

        self._lbl_resumen = QLabel()
        self._lbl_resumen.setObjectName("subheading")
        self._lbl_resumen.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        rl.addWidget(self._lbl_resumen)
        return grp

    # ── TAB: Historial ─────────────────────────────────────────────────────────

    def _build_tab_historial(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        lay.setSpacing(Spacing.SM)

        # Filter row
        fh = QHBoxLayout()
        self._hist_filter = FilterBar(self, placeholder="Receta, usuario o producto base…")
        self._hist_filter.filters_changed.connect(lambda _v: self._load_historial())
        self._search_hist = self._hist_filter.search
        fh.addWidget(self._hist_filter, 1)
        btn_ref = QPushButton("🔄 Actualizar")
        btn_ref.clicked.connect(self._load_historial)
        fh.addWidget(btn_ref)
        lay.addLayout(fh)

        self._hist_loading = LoadingIndicator("Cargando historial de producción…", self)
        self._hist_loading.hide()
        lay.addWidget(self._hist_loading)

        sp = QSplitter(Qt.Horizontal)

        # Production list
        self._tbl_hist = self._crear_tabla(
            cols=["ID", "Fecha", "Receta", "Tipo", "Base", "Cantidad", "Usuario"],
            stretch_col=2,
            number_cols=(5,),
        )
        self._tbl_hist.itemSelectionChanged.connect(self._on_hist_sel)
        sp.addWidget(self._tbl_hist)

        self._hist_empty = EmptyStateWidget(
            "Sin producciones",
            "No hay registros de producción para el filtro aplicado.",
            "📭",
            self,
        )
        self._hist_empty.hide()

        # Detail panel
        det_grp = QGroupBox("Detalle de Producción")
        det_grp.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        rl = QVBoxLayout(det_grp)
        rl.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)

        self._tbl_det = self._crear_tabla(
            cols=["Tipo", "Producto", "Cantidad", "Unidad", "Rendimiento %"],
            stretch_col=1,
            number_cols=(2, 4),
        )
        rl.addWidget(self._tbl_det)

        self._lbl_det_info = QLabel()
        self._lbl_det_info.setObjectName("caption")
        rl.addWidget(self._lbl_det_info)

        sp.addWidget(det_grp)
        sp.setSizes([480, 340])

        lay.addWidget(sp)
        lay.addWidget(self._hist_empty)
        return w

    # ── Shared table factory ───────────────────────────────────────────────────

    @staticmethod
    def _crear_tabla(
        cols: List[str],
        stretch_col: int = 0,
        number_cols: tuple = (),
    ) -> QTableWidget:
        """Build a read-only, alternating-row QTableWidget with standard resize modes."""
        tbl = QTableWidget()
        tbl.setColumnCount(len(cols))
        tbl.setHorizontalHeaderLabels(cols)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.verticalHeader().setVisible(False)
        tbl.setAlternatingRowColors(True)
        tbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        hdr = tbl.horizontalHeader()
        hdr.setSectionResizeMode(stretch_col, QHeaderView.Stretch)
        for i in range(len(cols)):
            if i != stretch_col:
                hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        # Store number_cols so callers can right-align them when populating
        tbl.setProperty("number_cols", number_cols)
        return tbl

    # ── TAB: Cárnica / Lotes ───────────────────────────────────────────────────

    def _build_tab_carnica(self) -> QWidget:
        """Lote cárnico — simple form to register a raw-weight batch via RecipeEngine."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        lay.setSpacing(Spacing.SM)

        grp_in = QGroupBox("Ingresar lote a producción cárnica")
        form = QFormLayout(grp_in)
        form.setSpacing(Spacing.SM)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._car_cmb_producto = QComboBox()
        self._car_cmb_producto.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._car_spin_peso = QDoubleSpinBox()
        self._car_spin_peso.setRange(0.001, 9999)
        self._car_spin_peso.setDecimals(3)
        self._car_spin_peso.setSuffix(" kg")
        self._car_spin_peso.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._car_spin_merma = QDoubleSpinBox()
        self._car_spin_merma.setRange(0, 100)
        self._car_spin_merma.setDecimals(1)
        self._car_spin_merma.setSuffix(" %")
        self._car_spin_merma.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        form.addRow("Producto:", self._car_cmb_producto)
        form.addRow("Peso bruto:", self._car_spin_peso)
        form.addRow("Merma esperada:", self._car_spin_merma)
        lay.addWidget(grp_in)

        btn_row = QHBoxLayout()
        btn_proc = create_danger_button(
            self, "⚙️ Procesar lote cárnico",
            "Procesar lote de producción cárnica con cálculo de merma"
        )
        btn_proc.clicked.connect(self._procesar_lote_carnico)
        btn_row.addWidget(btn_proc)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self._car_tabla = self._crear_tabla(
            cols=["Fecha", "Producto", "Bruto kg", "Merma kg", "Neto kg"],
            stretch_col=1,
            number_cols=(2, 3, 4),
        )
        lay.addWidget(self._car_tabla)

        self._cargar_productos_carnica()
        self._cargar_hist_carnica()
        return w

    def _cargar_productos_carnica(self) -> None:
        self._car_cmb_producto.clear()
        try:
            rows = self.conexion.execute(
                "SELECT id, nombre FROM productos WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            for r in rows:
                self._car_cmb_producto.addItem(r[1], r[0])
        except Exception:
            pass

    def _on_refresh(self, event_type: str, data: dict) -> None:
        """Auto-refresh on EventBus events."""
        try:
            self._cargar_hist_carnica()
        except Exception:
            pass

    def _cargar_hist_carnica(self) -> None:
        try:
            rows = self.conexion.execute("""
                SELECT COALESCE(fecha_produccion, created_at, '?'), p.nombre,
                       COALESCE(peso_bruto_kg,0), COALESCE(merma_kg,0),
                       COALESCE(peso_neto_kg, peso_bruto_kg - merma_kg, 0)
                FROM recepciones_pollo rp
                LEFT JOIN productos p ON p.id = rp.producto_id
                ORDER BY 1 DESC LIMIT 100
            """).fetchall()
        except Exception:
            rows = []
        self._car_tabla.setRowCount(0)
        for i, r in enumerate(rows):
            self._car_tabla.insertRow(i)
            for j, v in enumerate(r):
                item = QTableWidgetItem(str(v) if v else "")
                if j in (2, 3, 4):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._car_tabla.setItem(i, j, item)

    def _procesar_lote_carnico(self) -> None:
        """
        Delegates to RecipeEngine — registers production with full traceability.
        Finds the active recipe for the selected product (subproducto type).
        """
        prod_id = self._car_cmb_producto.currentData()
        if not prod_id:
            QMessageBox.warning(self, "Aviso", "Selecciona un producto.")
            return

        peso = self._car_spin_peso.value()
        if peso <= 0:
            QMessageBox.warning(self, "Aviso", "El peso debe ser mayor a cero.")
            return

        rec_row = self.conexion.execute(
            "SELECT id, nombre_receta FROM product_recipes "
            "WHERE base_product_id=? AND is_active=1 LIMIT 1",
            (prod_id,)
        ).fetchone()

        if not rec_row:
            QMessageBox.warning(
                self, "Sin receta",
                "Este producto no tiene una receta activa.\n"
                "Crea la receta en el módulo Recetas antes de registrar producción."
            )
            return

        receta_id  = rec_row[0] if not hasattr(rec_row, 'keys') else rec_row['id']
        receta_nom = rec_row[1] if not hasattr(rec_row, 'keys') else rec_row['nombre_receta']

        try:
            from core.services.recipe_engine import RecipeEngine
            engine = RecipeEngine(
                self.container.db, branch_id=getattr(self, 'sucursal_id', 1)
            )
            preview = engine.preview_produccion(receta_id, peso)
        except Exception as _pe:
            QMessageBox.critical(self, "Error al previsualizar", str(_pe))
            return

        lines = [f"Receta: {receta_nom}", f"Entrada: {peso:.3f} kg", ""]
        for m in preview:
            arrow = "▼ SALIDA" if m['delta'] < 0 else "▲ ENTRADA"
            lines.append(f"{arrow}  {m['nombre']}: {abs(m['delta']):.3f} kg")

        resp = QMessageBox.question(
            self, "Confirmar producción",
            "\n".join(lines) + "\n\n¿Ejecutar?",
            QMessageBox.Yes | QMessageBox.No
        )
        if resp != QMessageBox.Yes:
            return

        try:
            res = engine.ejecutar_produccion(
                receta_id=receta_id,
                cantidad_base=peso,
                usuario=getattr(self, 'usuario_actual', '') or getattr(self, 'usuario', 'Sistema'),
                sucursal_id=getattr(self, 'sucursal_id', 1),
                notas="Lote cárnico produccion.py",
            )
            try:
                get_bus().publish("PRODUCCION_REGISTRADA", {"event_type": "PRODUCCION_REGISTRADA"})
            except Exception:
                pass

            result_lines = [
                f"Producción #{res.produccion_id} registrada",
                f"Total generado:  {res.total_generado:.3f} kg",
                f"Total consumido: {res.total_consumido:.3f} kg",
                "",
            ]
            for comp in res.componentes:
                arrow = "▲" if comp.tipo == "entrada" else "▼"
                result_lines.append(f"{arrow} {comp.nombre}: {comp.cantidad:.3f} kg")

            QMessageBox.information(self, "✅ Producción Registrada", "\n".join(result_lines))
            self._cargar_hist_carnica()

        except Exception as e:
            QMessageBox.critical(self, "Error en producción", str(e))

    # ── TAB: Recetas ───────────────────────────────────────────────────────────

    def _build_tab_recetas(self) -> QWidget:
        """CRUD tab for production recipes."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        lay.setSpacing(Spacing.SM)

        info = QLabel(
            "Gestión de recetas para producción y despiece cárnico. "
            "Cada receta define insumos, rendimientos y subproductos."
        )
        info.setWordWrap(True)
        info.setObjectName("caption")
        lay.addWidget(info)

        btn_row = QHBoxLayout()
        btn_nueva  = create_success_button(self, "➕ Nueva receta", "Crear nueva receta de producción")
        btn_editar = create_secondary_button(self, "✏️ Editar receta", "Editar receta seleccionada")
        btn_ver    = QPushButton("👁️ Ver detalle")
        btn_desact = create_danger_button(self, "🗑️ Desactivar", "Desactivar receta seleccionada")
        btn_refresh = QPushButton("🔄")
        apply_tooltip(btn_refresh, "Actualizar lista de recetas")

        btn_row.addWidget(btn_nueva)
        btn_row.addWidget(btn_editar)
        btn_row.addWidget(btn_ver)
        btn_row.addWidget(btn_desact)
        btn_row.addStretch()
        btn_row.addWidget(btn_refresh)
        lay.addLayout(btn_row)

        self._rec_tabla = self._crear_tabla(
            cols=["ID", "Nombre", "Producto base", "Rendimiento", "Componentes"],
            stretch_col=1,
        )
        self._rec_tabla.setColumnHidden(0, True)
        self._rec_tabla.setSelectionBehavior(self._rec_tabla.SelectRows)
        lay.addWidget(self._rec_tabla)

        btn_nueva.clicked.connect(self._receta_nueva)
        btn_editar.clicked.connect(self._receta_editar)
        btn_ver.clicked.connect(self._ver_detalle_receta)
        btn_desact.clicked.connect(self._receta_desactivar)
        btn_refresh.clicked.connect(self._cargar_lista_recetas)
        self._cargar_lista_recetas()
        return w

    def _cargar_lista_recetas(self) -> None:
        try:
            rows = self.conexion.execute("""
                SELECT r.id,
                       COALESCE(r.nombre_receta, r.nombre, '') as nombre,
                       COALESCE(p.nombre, '') as producto_base,
                       COALESCE(r.total_rendimiento, r.rendimiento_esperado_pct, 0) as rendimiento,
                       (
                        SELECT COUNT(*)
                        FROM product_recipe_components rc
                        WHERE rc.recipe_id = r.id
                       ) as componentes
                FROM product_recipes r
                LEFT JOIN productos p ON p.id = COALESCE(r.product_id, r.base_product_id)
                WHERE COALESCE(r.is_active, r.activa, 1) = 1
                ORDER BY nombre LIMIT 200
            """).fetchall()
        except Exception:
            try:
                rows = self.conexion.execute("""
                    SELECT r.id, r.nombre,
                           COALESCE(p.nombre, ''),
                           COALESCE(r.rendimiento_esperado_pct, 0),
                           0
                    FROM recetas r
                    LEFT JOIN productos p ON p.id = r.producto_id
                    ORDER BY r.nombre LIMIT 200
                """).fetchall()
            except Exception:
                rows = []

        self._rec_tabla.setRowCount(0)
        if not rows:
            self._rec_tabla.setRowCount(1)
            self._rec_tabla.setSpan(0, 0, 1, self._rec_tabla.columnCount())
            self._rec_tabla.setItem(0, 0, QTableWidgetItem("No hay recetas activas registradas."))
            return
        for i, r in enumerate(rows):
            self._rec_tabla.insertRow(i)
            vals = [str(r[0]), r[1], r[2], f"{r[3]:.1f}%", str(r[4])]
            for j, v in enumerate(vals):
                self._rec_tabla.setItem(i, j, QTableWidgetItem(v))

    # ── Schema introspection helpers ───────────────────────────────────────────

    def _pr_columns(self) -> set:
        try:
            rows = self.conexion.execute("PRAGMA table_info(product_recipes)").fetchall()
            return {r[1] for r in rows}
        except Exception:
            return set()

    def _pr_product_expr(self) -> str:
        cols = self._pr_columns()
        if "product_id" in cols:
            return "r.product_id"
        if "base_product_id" in cols:
            return "r.base_product_id"
        return "NULL"

    # ── Recipe CRUD actions ────────────────────────────────────────────────────

    def _receta_nueva(self) -> None:
        try:
            from repositories.recetas import RecetaRepository
            repo = RecetaRepository(self.conexion)
            productos = self.conexion.execute(
                "SELECT id, nombre, unidad FROM productos WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            prods = [{'id': p[0], 'nombre': p[1], 'unidad': p[2] or 'kg'} for p in productos]
            dlg = DialogoReceta(repo, prods, self.usuario_actual, parent=self)
            if dlg.exec_() == dlg.Accepted:
                self._cargar_lista_recetas()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo abrir editor de recetas:\n{e}")

    def _receta_editar(self) -> None:
        row = self._rec_tabla.currentRow()
        if row < 0:
            QMessageBox.information(self, "Aviso", "Selecciona una receta.")
            return
        rid = int(self._rec_tabla.item(row, 0).text())
        try:
            from repositories.recetas import RecetaRepository
            repo = RecetaRepository(self.conexion)
            productos = self.conexion.execute(
                "SELECT id, nombre, unidad FROM productos WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            prods = [{'id': p[0], 'nombre': p[1], 'unidad': p[2] or 'kg'} for p in productos]
            receta_row = self.conexion.execute(
                "SELECT * FROM product_recipes WHERE id=?", (rid,)
            ).fetchone()
            receta_data = dict(receta_row) if receta_row else None
            comps = self.conexion.execute(
                "SELECT * FROM product_recipe_components WHERE recipe_id=?", (rid,)
            ).fetchall()
            componentes = [dict(c) for c in comps] if comps else []
            dlg = DialogoReceta(
                repo, prods, self.usuario_actual,
                receta_data=receta_data, componentes=componentes, parent=self
            )
            if dlg.exec_() == dlg.Accepted:
                self._cargar_lista_recetas()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo abrir editor:\n{e}")

    def _receta_desactivar(self) -> None:
        row = self._rec_tabla.currentRow()
        if row < 0:
            return
        rid = int(self._rec_tabla.item(row, 0).text())
        nombre = self._rec_tabla.item(row, 1).text()
        if QMessageBox.question(
            self, "Confirmar",
            f"¿Desactivar la receta '{nombre}'?",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return
        try:
            self.conexion.execute("UPDATE product_recipes SET is_active=0 WHERE id=?", (rid,))
            try:
                self.conexion.commit()
            except Exception:
                pass
            self._cargar_lista_recetas()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _nueva_receta_simple(self) -> None:
        """Fallback: simple recipe dialog (no DialogoReceta)."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Nueva Receta")
        dlg.setMinimumWidth(360)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()

        txt_nombre = QLineEdit()
        txt_nombre.setPlaceholderText("Nombre de la receta")
        cmb_producto = QComboBox()
        try:
            prods = self.conexion.execute(
                "SELECT id, nombre FROM productos WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            for p in prods:
                cmb_producto.addItem(p[1], p[0])
        except Exception:
            pass
        spin_rend = QDoubleSpinBox()
        spin_rend.setRange(0, 100)
        spin_rend.setSuffix("%")
        spin_rend.setDecimals(1)
        form.addRow("Nombre *:", txt_nombre)
        form.addRow("Producto base:", cmb_producto)
        form.addRow("Rendimiento esperado:", spin_rend)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec_() != QDialog.Accepted:
            return
        nombre = txt_nombre.text().strip()
        if not nombre:
            return
        try:
            self.conexion.execute(
                "INSERT INTO product_recipes(nombre_receta, product_id, total_rendimiento, is_active)"
                " VALUES(?,?,?,1)",
                (nombre, cmb_producto.currentData(), spin_rend.value())
            )
            try:
                self.conexion.commit()
            except Exception:
                pass
            self._cargar_lista_recetas()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _ver_detalle_receta(self) -> None:
        row = self._rec_tabla.currentRow()
        if row < 0:
            return
        rid = int(self._rec_tabla.item(row, 0).text())
        nombre = self._rec_tabla.item(row, 1).text()
        try:
            comps = self.conexion.execute("""
                SELECT p.nombre,
                       COALESCE(rc.cantidad, 0) AS cantidad,
                       COALESCE(rc.unidad, p.unidad, 'kg') AS unidad,
                       COALESCE(rc.merma_pct, 0) AS merma_pct,
                       COALESCE(rc.rendimiento_pct, 0) AS rendimiento_pct
                FROM product_recipe_components rc
                LEFT JOIN productos p ON p.id = rc.component_product_id
                WHERE rc.recipe_id=? ORDER BY rc.orden
            """, (rid,)).fetchall()
            if not comps:
                QMessageBox.information(
                    self, "Sin componentes",
                    f"La receta '{nombre}' no tiene componentes registrados."
                )
                return
            txt = f"Receta: {nombre}\n\nComponentes:\n"
            for c in comps:
                txt += f"  • {c[0]}: {c[1]} {c[2] or 'u'} (merma {c[3]:.1f}%)\n"
            QMessageBox.information(self, "Detalle receta", txt)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ── Data loading ───────────────────────────────────────────────────────────

    def _load_recetas(self) -> None:
        if not hasattr(self, '_combo_receta'):
            return
        try:
            product_expr = self._pr_product_expr()
            rows = self.conexion.fetchall("""
                SELECT r.id,
                       COALESCE(r.nombre_receta, '') AS nombre,
                       COALESCE(r.tipo_receta, 'produccion') AS tipo_receta,
                       {product_expr} AS producto_base_id,
                       COALESCE(r.peso_promedio_kg, 1.0) AS peso_promedio_kg,
                       COALESCE(r.unidad_base, p.unidad, 'kg') AS unidad_base,
                       p.nombre AS prod_nombre, p.unidad AS prod_unidad
                FROM product_recipes r
                LEFT JOIN productos p ON p.id = {product_expr}
                WHERE COALESCE(r.is_active, r.activa, 1) = 1
                ORDER BY tipo_receta, nombre
            """.format(product_expr=product_expr))
            self._recetas_cache = [dict(r) for r in rows]
        except Exception as exc:
            logger.warning("load_recetas: %s", exc)
            self._recetas_cache = []

        prev_id = self._combo_receta.currentData()
        self._combo_receta.blockSignals(True)
        self._combo_receta.clear()
        self._combo_receta.addItem("— Seleccionar receta —", None)
        for r in self._recetas_cache:
            tipo_lbl = TIPO_LABELS.get(r.get("tipo_receta", ""), r.get("tipo_receta", ""))
            self._combo_receta.addItem(f"{r['nombre']}  [{tipo_lbl}]", r["id"])
        if prev_id:
            idx = self._combo_receta.findData(prev_id)
            if idx >= 0:
                self._combo_receta.setCurrentIndex(idx)
        self._combo_receta.blockSignals(False)
        self._on_receta_changed()

    def _get_receta_actual(self) -> Optional[Dict]:
        if not hasattr(self, '_combo_receta'):
            return None
        rid = self._combo_receta.currentData()
        if not rid:
            return None
        return next((r for r in self._recetas_cache if r["id"] == rid), None)

    def _on_receta_changed(self) -> None:
        r = self._get_receta_actual()
        if not r:
            self._lbl_tipo.setText("")
            self._lbl_base.setText("")
            self._lbl_unidad.setText("—")
            self._tbl_prev.setRowCount(0)
            self._lbl_resumen.setText("")
            self._lbl_stock.setText("—")
            return
        tipo = r.get("tipo_receta", "")
        self._lbl_tipo.setText(TIPO_LABELS.get(tipo, tipo))
        self._lbl_tipo.setObjectName("badge")
        peso = r.get("peso_promedio_kg") or 1.0
        unidad = r.get("unidad_base") or r.get("prod_unidad") or "kg"
        self._lbl_base.setText(
            f"Base: {r.get('prod_nombre','?')} | "
            f"Peso prom: {float(peso):.3f} kg/ud | "
            f"Unidad: {unidad}"
        )
        self._lbl_unidad.setText(unidad)
        self._update_stock_label(r)
        self._preview()

    def _on_cant_changed(self, _val: float) -> None:
        r = self._get_receta_actual()
        if r:
            self._update_stock_label(r)
            self._preview()

    def _update_stock_label(self, r: Dict) -> None:
        try:
            row = self.conexion.fetchone("""
                SELECT COALESCE(SUM(bi.quantity), 0) as qty
                FROM branch_inventory bi
                WHERE bi.branch_id = ? AND bi.product_id = ?
            """, (self.sucursal_id, r["producto_base_id"]))
            stock = float(row["qty"]) if row else 0.0
            cant = self._spin_cant.value()
            unidad = r.get("unidad_base") or "kg"
            ok = stock >= cant
            self._lbl_stock.setText(f"{stock:.3f} {unidad}")
            self._lbl_stock.setObjectName("textSuccess" if ok else "textDanger")
            self._lbl_stock.style().unpolish(self._lbl_stock)
            self._lbl_stock.style().polish(self._lbl_stock)
        except Exception as exc:
            logger.warning("update_stock_label: %s", exc)
            self._lbl_stock.setText("?")

    def _preview(self) -> None:
        r = self._get_receta_actual()
        if not r:
            self._tbl_prev.setRowCount(0)
            self._lbl_resumen.setText("")
            return
        cant = self._spin_cant.value()
        try:
            movs = self._engine.preview_produccion(r["id"], cant)
        except Exception as exc:
            self._tbl_prev.setRowCount(0)
            self._lbl_resumen.setText(f"⚠ {exc}")
            return

        stocks = {}
        try:
            for pid in {m["product_id"] for m in movs}:
                row = self.conexion.fetchone("""
                    SELECT COALESCE(SUM(quantity), 0) as q
                    FROM branch_inventory
                    WHERE branch_id = ? AND product_id = ?
                """, (self.sucursal_id, pid))
                stocks[pid] = float(row["q"]) if row else 0.0
        except Exception:
            pass

        self._tbl_prev.setRowCount(len(movs))
        total_in = 0.0
        total_out = 0.0
        hay_error = False

        for ri, mov in enumerate(movs):
            delta = float(mov["delta"])
            pid = mov["product_id"]
            stock_act = stocks.get(pid, 0.0)
            es_salida = delta < 0

            if es_salida and stock_act < abs(delta) - 0.001:
                hay_error = True

            tipo_color  = _RED if es_salida else _GREEN
            stock_color = _RED if (es_salida and stock_act < abs(delta)) else _GREEN

            vals = [
                "⬇ CONSUMO" if es_salida else "⬆ GENERADO",
                mov.get("nombre", f"#{pid}"),
                f"{abs(delta):.3f}",
                mov.get("unidad", "kg"),
                f"{stock_act:.3f}",
            ]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci == 0:
                    it.setForeground(QColor(tipo_color))
                    it.setFont(QFont("", -1, QFont.Bold))
                if ci == 4:
                    it.setForeground(QColor(stock_color))
                if ci in (2, 4):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._tbl_prev.setItem(ri, ci, it)

            if es_salida:
                total_out += abs(delta)
            else:
                total_in += delta

        if hay_error:
            self._lbl_resumen.setText(
                f"❌ STOCK INSUFICIENTE | Consumo: {total_out:.3f} | Generado: {total_in:.3f}"
            )
            self._lbl_resumen.setObjectName("textDanger")
            self._btn_ejecutar.setEnabled(False)
        else:
            self._lbl_resumen.setText(
                f"✅ OK | Consumo: {total_out:.3f} | Generado: {total_in:.3f} | "
                f"Movimientos: {len(movs)}"
            )
            self._lbl_resumen.setObjectName("textSuccess")
            self._btn_ejecutar.setEnabled(True)

        self._lbl_resumen.style().unpolish(self._lbl_resumen)
        self._lbl_resumen.style().polish(self._lbl_resumen)

    # ── Execute production ─────────────────────────────────────────────────────

    def _reset_btn_ejecutar(self) -> None:
        """Restore the execute button to its default enabled state."""
        self._btn_ejecutar.setText("▶ EJECUTAR PRODUCCIÓN")
        self._btn_ejecutar.setEnabled(True)

    def _ejecutar(self) -> None:
        r = self._get_receta_actual()
        if not r:
            QMessageBox.warning(self, "Validación", "Seleccione una receta.")
            return
        cant = self._spin_cant.value()
        tipo = r.get("tipo_receta", "")
        tipo_lbl = TIPO_LABELS.get(tipo, tipo)

        confirm = QMessageBox.question(
            self, "Confirmar Producción",
            f"¿Ejecutar producción?\n\n"
            f"Receta: {r['nombre']}\n"
            f"Tipo: {tipo_lbl}\n"
            f"Base: {r.get('prod_nombre','?')}\n"
            f"Cantidad: {cant:.3f} {r.get('unidad_base','kg')}\n"
            f"Sucursal: {self.sucursal_nombre}\n"
            f"Usuario: {self.usuario_actual}\n\n"
            f"Esta operación modificará el inventario y no puede deshacerse.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        self._btn_ejecutar.setEnabled(False)
        self._btn_ejecutar.setText("⏳ Procesando…")

        try:
            resultado = self._engine.ejecutar_produccion(
                receta_id=r["id"],
                cantidad_base=cant,
                usuario=self.usuario_actual,
                sucursal_id=self.sucursal_id,
                notas=self._e_notas.text().strip(),
            )
            self._reset_btn_ejecutar()
            detalle = "\n".join(
                f"  {'⬆' if c.tipo=='entrada' else '⬇'} {c.nombre}: "
                f"{c.cantidad:.3f} {c.unidad}"
                f"{f'  ({c.rendimiento:.1f}%)' if c.rendimiento > 0 else ''}"
                for c in resultado.componentes
            )
            QMessageBox.information(
                self, "✅ Producción Completada",
                f"Producción #{resultado.produccion_id} ejecutada exitosamente.\n\n"
                f"Receta: {resultado.receta_nombre}\n"
                f"Tipo: {resultado.tipo_receta}\n"
                f"Base: {resultado.producto_base} × {cant:.3f}\n"
                f"Total generado: {resultado.total_generado:.3f}\n"
                f"Total consumido: {resultado.total_consumido:.3f}\n\n"
                f"Movimientos:\n{detalle}"
            )
            self._e_notas.clear()
            self._refresh_all()

        except StockInsuficienteProduccionError as exc:
            self._reset_btn_ejecutar()
            QMessageBox.critical(self, "Stock Insuficiente", str(exc))
        except ProduccionDuplicadaError as exc:
            self._reset_btn_ejecutar()
            QMessageBox.warning(self, "Producción Duplicada", str(exc))
        except RecetaNoEncontradaError as exc:
            self._reset_btn_ejecutar()
            QMessageBox.warning(self, "Receta No Encontrada", str(exc))
        except RecipeEngineError as exc:
            self._reset_btn_ejecutar()
            QMessageBox.critical(self, "Error de Producción", str(exc))
        except Exception as exc:
            self._reset_btn_ejecutar()
            logger.exception("ejecutar_produccion")
            QMessageBox.critical(self, "Error Inesperado", str(exc))

    # ── History ────────────────────────────────────────────────────────────────

    def _load_historial(self) -> None:
        if hasattr(self, "_hist_loading"):
            self._hist_loading.show()
        search = (
            self._search_hist.text() if hasattr(self, "_search_hist") else ""
        ).strip().lower()
        try:
            try:
                rows = self._engine.get_historial(
                    sucursal_id=self.sucursal_id if self.sucursal_id != 1 else None,
                    limit=200,
                )
            except Exception as exc:
                logger.warning("load_historial: %s", exc)
                rows = []

            if search:
                rows = [
                    r for r in rows
                    if search in r.get("receta_nombre", "").lower()
                    or search in r.get("usuario", "").lower()
                    or search in r.get("producto_base_nombre", "").lower()
                ]

            self._tbl_hist.setRowCount(len(rows))
            if hasattr(self, "_hist_empty"):
                self._hist_empty.setVisible(len(rows) == 0)

            for ri, r in enumerate(rows):
                tipo = r.get("tipo_receta", "")
                tipo_color = TIPO_COLOR.get(tipo, _GRAY)
                fecha_str = r.get("fecha", "")
                if fecha_str and "T" in fecha_str:
                    fecha_str = fecha_str.replace("T", " ")[:19]

                vals = [
                    str(r.get("id", "")),
                    fecha_str,
                    r.get("receta_nombre", "—"),
                    TIPO_LABELS.get(tipo, tipo),
                    r.get("producto_base_nombre", "—"),
                    f"{float(r.get('cantidad_base', 0)):.3f}",
                    r.get("usuario", "—"),
                ]
                for ci, v in enumerate(vals):
                    it = QTableWidgetItem(str(v))
                    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    if ci == 3:
                        it.setForeground(QColor(tipo_color))
                    if ci == 5:
                        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    if ci == 0:
                        it.setData(Qt.UserRole, r.get("id"))
                    self._tbl_hist.setItem(ri, ci, it)
        finally:
            if hasattr(self, "_hist_loading"):
                self._hist_loading.hide()

    def _on_hist_sel(self) -> None:
        row = self._tbl_hist.currentRow()
        if row < 0:
            self._tbl_det.setRowCount(0)
            return
        it = self._tbl_hist.item(row, 0)
        if not it:
            return
        prod_id = it.data(Qt.UserRole)
        if not prod_id:
            return
        try:
            detalles = self._engine.get_detalle_produccion(int(prod_id))
        except Exception as exc:
            logger.warning("get_detalle_produccion: %s", exc)
            return

        self._tbl_det.setRowCount(len(detalles))
        total_in = 0.0
        total_out = 0.0

        for ri, d in enumerate(detalles):
            tipo = d.get("tipo", "salida")
            cant = float(d.get("cantidad_generada", 0))
            rend = float(d.get("rendimiento_aplicado", 0))
            es_entrada = tipo == "entrada"
            color = _GREEN if es_entrada else _RED

            vals = [
                "⬆ GENERADO" if es_entrada else "⬇ CONSUMO",
                d.get("producto_nombre", f"#{d.get('producto_resultante_id','?')}"),
                f"{cant:.3f}",
                d.get("unidad", "kg"),
                f"{rend:.2f}%" if rend > 0 else "—",
            ]
            for ci, v in enumerate(vals):
                it2 = QTableWidgetItem(str(v))
                it2.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci == 0:
                    it2.setForeground(QColor(color))
                    it2.setFont(QFont("", -1, QFont.Bold))
                if ci in (2, 4):
                    it2.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._tbl_det.setItem(ri, ci, it2)

            if es_entrada:
                total_in += cant
            else:
                total_out += cant

        self._lbl_det_info.setText(
            f"Total generado: {total_in:.3f} | Total consumido: {total_out:.3f}"
        )


# ── Recipe Dialog ─────────────────────────────────────────────────────────────

class DialogoReceta(QDialog):

    def __init__(
        self,
        repo,
        productos: List[Dict],
        usuario: str,
        receta_data: Optional[Dict] = None,
        componentes: Optional[List[Dict]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._repo        = repo
        self._productos   = productos
        self._usuario     = usuario
        self._data        = receta_data
        self._componentes = componentes or []
        self._comp_rows: List[Dict] = []
        self.setWindowTitle("Nueva Receta" if not receta_data else "Editar Receta")
        self.setMinimumWidth(700)
        self.setMinimumHeight(550)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self._build_ui()
        if receta_data:
            self._load()

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setSpacing(Spacing.SM)
        lay.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)

        # Header form
        fl = QFormLayout()
        fl.setSpacing(Spacing.SM)
        fl.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._e_nombre = QLineEdit()
        self._e_nombre.setPlaceholderText("Nombre de la receta…")
        self._e_nombre.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._combo_base = QComboBox()
        self._combo_base.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._combo_base.addItem("— Seleccionar producto base —", None)
        for p in self._productos:
            self._combo_base.addItem(f"{p['nombre']} [{p.get('unidad','kg')}]", p["id"])

        fl.addRow("Nombre Receta*:", self._e_nombre)
        fl.addRow("Producto Base*:", self._combo_base)
        lay.addLayout(fl)

        # Components table + add-component form
        grp = QGroupBox("Componentes (suma rendimiento debe ser 100% exacto)")
        gl = QVBoxLayout(grp)
        gl.setSpacing(Spacing.SM)

        self._tbl_comp = QTableWidget()
        self._tbl_comp.setColumnCount(6)
        self._tbl_comp.setHorizontalHeaderLabels(
            ["Componente", "Rendimiento %", "Merma %", "Total %", "Tolerancia %", "Descripción"]
        )
        self._tbl_comp.verticalHeader().setVisible(False)
        self._tbl_comp.setAlternatingRowColors(True)
        self._tbl_comp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        hdr = self._tbl_comp.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3, 4, 5):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        gl.addWidget(self._tbl_comp)

        # Add-component controls
        add_form = QFormLayout()
        add_form.setSpacing(Spacing.XS)
        add_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._combo_comp = QComboBox()
        self._combo_comp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._combo_comp.addItem("— Componente —", None)
        for p in self._productos:
            self._combo_comp.addItem(p['nombre'], p["id"])

        self._spin_rend = QDoubleSpinBox()
        self._spin_rend.setRange(0, 100)
        self._spin_rend.setDecimals(3)
        self._spin_rend.setSuffix(" %")

        self._spin_merma = QDoubleSpinBox()
        self._spin_merma.setRange(0, 100)
        self._spin_merma.setDecimals(3)
        self._spin_merma.setSuffix(" %")

        self._spin_tolerancia = QDoubleSpinBox()
        self._spin_tolerancia.setRange(0.1, 20.0)
        self._spin_tolerancia.setDecimals(1)
        self._spin_tolerancia.setSuffix(" %")
        self._spin_tolerancia.setValue(2.0)
        self._spin_tolerancia.setToolTip(
            "Error relativo permitido.\n"
            "Si la producción real difiere más de este % del teórico,\n"
            "se registra como variación en el historial."
        )

        self._e_desc = QLineEdit()
        self._e_desc.setPlaceholderText("Descripción (opcional)")

        add_form.addRow("Componente:", self._combo_comp)
        add_form.addRow("Rendimiento %:", self._spin_rend)
        add_form.addRow("Merma %:", self._spin_merma)
        add_form.addRow("Tolerancia %:", self._spin_tolerancia)
        add_form.addRow("Descripción:", self._e_desc)
        gl.addLayout(add_form)

        btn_add_row = QHBoxLayout()
        btn_add = create_primary_button(self, "➕ Agregar", "Agregar componente a la receta")
        btn_add.clicked.connect(self._add_component)
        btn_del = create_secondary_button(self, "🗑 Quitar Sel.", "Quitar componente seleccionado")
        btn_del.clicked.connect(self._remove_component)
        btn_add_row.addWidget(btn_add)
        btn_add_row.addWidget(btn_del)
        btn_add_row.addStretch()
        gl.addLayout(btn_add_row)

        self._lbl_totales = QLabel("Suma: 0.00%")
        self._lbl_totales.setObjectName("subheading")
        gl.addWidget(self._lbl_totales)
        lay.addWidget(grp)

        # Dialog buttons
        bl = QHBoxLayout()
        btn_ok = create_success_button(self, "💾 Guardar Receta", "Guardar receta de producción")
        btn_ok.clicked.connect(self._guardar)
        btn_no = create_secondary_button(self, "Cancelar", "Cancelar y cerrar")
        btn_no.clicked.connect(self.reject)
        bl.addStretch()
        bl.addWidget(btn_ok)
        bl.addWidget(btn_no)
        lay.addLayout(bl)

    def _load(self) -> None:
        d = self._data
        self._e_nombre.setText(d.get("nombre_receta", ""))
        idx = self._combo_base.findData(d.get("base_product_id"))
        if idx >= 0:
            self._combo_base.setCurrentIndex(idx)
        self._comp_rows = []
        for c in self._componentes:
            self._comp_rows.append({
                "component_product_id": c.get("component_product_id"),
                "component_nombre":     c.get("component_nombre", "?"),
                "rendimiento_pct":      float(c.get("rendimiento_pct", 0)),
                "merma_pct":            float(c.get("merma_pct", 0)),
                "tolerancia_pct":       float(c.get("tolerancia_pct", 2.0)),
                "descripcion":          c.get("descripcion", ""),
                "orden":                c.get("orden", 0),
            })
        self._refresh_comp_table()

    def _add_component(self) -> None:
        comp_id = self._combo_comp.currentData()
        if not comp_id:
            QMessageBox.warning(self, "Validación", "Seleccione un componente.")
            return
        rend  = self._spin_rend.value()
        merma = self._spin_merma.value()
        if rend + merma <= 0:
            QMessageBox.warning(self, "Validación", "Rendimiento + Merma debe ser mayor a 0%.")
            return
        base_id = self._combo_base.currentData()
        if comp_id == base_id:
            QMessageBox.warning(self, "Auto-referencia",
                                "Un componente no puede ser el mismo producto base.")
            return
        if any(r["component_product_id"] == comp_id for r in self._comp_rows):
            QMessageBox.warning(self, "Duplicado", "Este componente ya está en la receta.")
            return
        comp_nombre = self._combo_comp.currentText()
        tolerancia = self._spin_tolerancia.value()
        self._comp_rows.append({
            "component_product_id": comp_id,
            "component_nombre":     comp_nombre,
            "rendimiento_pct":      rend,
            "merma_pct":            merma,
            "tolerancia_pct":       tolerancia,
            "descripcion":          self._e_desc.text().strip(),
            "orden":                len(self._comp_rows),
        })
        self._refresh_comp_table()

    def _remove_component(self) -> None:
        row = self._tbl_comp.currentRow()
        if row < 0:
            return
        self._comp_rows.pop(row)
        self._refresh_comp_table()

    def _refresh_comp_table(self) -> None:
        self._tbl_comp.setRowCount(len(self._comp_rows))
        total_rend = Decimal("0")
        total_merma = Decimal("0")
        for ri, r in enumerate(self._comp_rows):
            rend  = Decimal(str(r["rendimiento_pct"]))
            merma = Decimal(str(r["merma_pct"]))
            total_rend  += rend
            total_merma += merma
            fila_total = float(rend + merma)
            tolerancia = float(r.get("tolerancia_pct", 2.0))
            vals = [
                r.get("component_nombre", "?"),
                f"{float(rend):.3f}%",
                f"{float(merma):.3f}%",
                f"{fila_total:.3f}%",
                f"± {tolerancia:.1f}%",
                r.get("descripcion", ""),
            ]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci in (1, 2, 3, 4):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._tbl_comp.setItem(ri, ci, it)
        grand = float(total_rend + total_merma)
        ok = abs(grand - 100.0) <= 0.01
        icon = "✅" if ok else "❌ DEBE SER 100%"
        self._lbl_totales.setText(
            f"{icon}  Rendimiento total: {float(total_rend):.3f}%  |  "
            f"Merma total: {float(total_merma):.3f}%  |  "
            f"Suma: {grand:.3f}%"
        )
        self._lbl_totales.setObjectName("textSuccess" if ok else "textDanger")
        self._lbl_totales.style().unpolish(self._lbl_totales)
        self._lbl_totales.style().polish(self._lbl_totales)

    def _guardar(self) -> None:
        from repositories.recetas import (
            RecetaError, RecetaCyclicError, RecetaSelfReferenceError,
            RecetaPercentageError, RecetaDuplicadaError,
        )
        nombre = self._e_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Validación", "Nombre de receta obligatorio.")
            return
        base_id = self._combo_base.currentData()
        if not base_id:
            QMessageBox.warning(self, "Validación", "Seleccione producto base.")
            return
        if not self._comp_rows:
            QMessageBox.warning(self, "Validación", "Agregue al menos un componente.")
            return

        total = sum(
            Decimal(str(c["rendimiento_pct"])) + Decimal(str(c["merma_pct"]))
            for c in self._comp_rows
        )
        if abs(total - Decimal("100.00")) > Decimal("0.01"):
            QMessageBox.warning(
                self, "Error de Porcentaje",
                f"La suma total ({float(total):.3f}%) debe ser exactamente 100%.\n"
                "Ajuste los porcentajes antes de guardar."
            )
            return

        components = [
            {
                "component_product_id": c["component_product_id"],
                "rendimiento_pct":      c["rendimiento_pct"],
                "merma_pct":            c["merma_pct"],
                "descripcion":          c.get("descripcion", ""),
                "orden":                c.get("orden", i),
            }
            for i, c in enumerate(self._comp_rows)
        ]

        try:
            if self._data:
                self._repo.update(self._data["id"], nombre, components, self._usuario)
                QMessageBox.information(self, "Éxito", "Receta actualizada correctamente.")
            else:
                rid = self._repo.create(
                    nombre=nombre,
                    base_product_id=base_id,
                    components=components,
                    usuario=self._usuario,
                )
                QMessageBox.information(self, "Éxito", f"Receta #{rid} creada correctamente.")
            self.accept()
        except RecetaCyclicError:
            QMessageBox.warning(self, "Dependencia Cíclica",
                                "Esta configuración crea una dependencia circular entre productos.")
        except RecetaSelfReferenceError:
            QMessageBox.warning(self, "Auto-referencia",
                                "Un componente no puede ser el mismo producto base.")
        except RecetaPercentageError as exc:
            QMessageBox.warning(self, "Error de Porcentaje", str(exc))
        except RecetaDuplicadaError:
            QMessageBox.warning(self, "Receta Duplicada",
                                "Ya existe una receta activa para este producto base.")
        except RecetaError as exc:
            QMessageBox.warning(self, "Error en Receta", str(exc))
        except Exception as exc:
            logger.exception("guardar_receta")
            QMessageBox.critical(self, "Error Inesperado", str(exc))
