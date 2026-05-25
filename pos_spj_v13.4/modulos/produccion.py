
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
from core.events.event_bus import get_bus
from modulos.design_tokens import Colors, Spacing
from modulos.ui_components import (
    create_primary_button, create_success_button, create_danger_button,
    FilterBar, LoadingIndicator, EmptyStateWidget
)

import logging
from typing import Dict, List, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QGroupBox, QSplitter,
    QMessageBox, QLineEdit, QTabWidget,
    QDialog, QFormLayout
    , QInputDialog
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont

from .base import ModuloBase
from core.events.event_bus import EventBus
from core.services.recipe_engine import (
    RecipeEngine,
    RecipeEngineError,
    RecetaNoEncontradaError,
    StockInsuficienteProduccionError,
    ProduccionDuplicadaError,
)
import core.services.production_query_service as _pqs

logger = logging.getLogger("spj.ui.produccion")
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


def _norm_tipo_receta(value: str) -> str:
    return str(value or "").strip().lower()


def _build_lote_balance_preview(movs_teoricos: list, reales: dict[int, float]) -> dict:
    expected = {}
    for m in movs_teoricos:
        if float(m.get("delta", 0)) > 0:
            expected[int(m["product_id"])] = expected.get(int(m["product_id"]), 0.0) + float(m["delta"])
    total_exp = sum(expected.values())
    total_real = sum(float(v or 0) for v in reales.values())
    return {
        "expected": expected,
        "total_expected": total_exp,
        "total_real": total_real,
        "difference": round(total_real - total_exp, 4),
    }


class ModuloProduccion(ModuloBase):
    """
    Ventana de producción industrial. Tabs:
        [0] Ejecutar Producción   — formulario + preview
        [1] Historial             — registro de producciones pasadas
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
        self._svc            = self._build_svc()
        self._recetas_cache: List[Dict] = []
        self._init_ui()
        self._subscribe_events()
        QTimer.singleShot(0, self._refresh_all)

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _build_svc(self):
        """Create ProductionApplicationService wrapping the current engine."""
        try:
            from core.services.production_application_service import ProductionApplicationService
            return ProductionApplicationService(
                recipe_engine     = self._engine,
                production_uc     = getattr(self.container, 'uc_produccion', None) if self.container else None,
                production_engine = getattr(self.container, 'production_engine', None) if self.container else None,
            )
        except Exception:
            return None

    def set_sucursal(self, sucursal_id: int, sucursal_nombre: str) -> None:
        self.sucursal_id     = sucursal_id
        self.sucursal_nombre = sucursal_nombre
        self._db_wrapped = self.conexion
        self._engine = RecipeEngine(self._db_wrapped, branch_id=sucursal_id)
        self._svc    = self._build_svc()

    def set_usuario_actual(self, usuario: str, rol: str = "") -> None:
        self.usuario_actual = usuario or "Sistema"

    def obtener_usuario_actual(self) -> str:
        return self.usuario_actual

    def limpiar(self) -> None:
        for evt in ("PRODUCCION_COMPLETADA", "RECETA_CREADA", "RECETA_ACTUALIZADA",
                    "INVENTARIO_ACTUALIZADO"):
            try: EventBus.unsubscribe(evt, self._on_data_changed)
            except Exception as e:
                logger.debug("No se pudo desuscribir evento %s: %s", evt, e)

    def _subscribe_events(self) -> None:
        for evt in ("PRODUCCION_COMPLETADA", "RECETA_CREADA", "RECETA_ACTUALIZADA",
                    "INVENTARIO_ACTUALIZADO"):
            EventBus().subscribe(evt, self._on_data_changed)

    def _on_data_changed(self, _data: dict) -> None:
        QTimer.singleShot(0, self._refresh_all)

    def _refresh_all(self) -> None:
        self._lbl_suc.setText(f"Sucursal: {self.sucursal_nombre}")
        self._load_recetas()
        self._load_historial()
        if hasattr(self, '_rec_tabla'):
            self._cargar_lista_recetas()
        if hasattr(self, '_stats_lbl_vals'):
            self._actualizar_stats_bar()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        ttl = QLabel("🔪 Procesamiento Cárnico")
        ttl.setObjectName("heading")
        self._lbl_suc = QLabel()
        self._lbl_suc.setObjectName("textSecondary")
        hdr.addWidget(ttl); hdr.addStretch(); hdr.addWidget(self._lbl_suc)
        root.addLayout(hdr)

        # Stats bar — KPIs en tiempo real
        self._stats_bar = self._crear_stats_produccion()
        root.addWidget(self._stats_bar)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_tab_produccion(), "🏭 Ejecutar Producción")
        self._tabs.addTab(self._build_tab_historial(),  "📋 Historial")
        self._tabs.addTab(self._build_tab_carnica(),    "🥩 Cárnica / Lotes")
        # FASE 7: Gestión de recetas se movió a Productos > Tab Receta.
        root.addWidget(self._tabs)

    def _crear_stats_produccion(self) -> 'QFrame':
        """
        Barra de KPIs de producción cárnica.
        Sigue el estándar visual de finanzas_unificadas._crear_fin_kpi_bar.
        Sin hardcodeo: usa Colors.NEUTRAL tokens.
        """
        from PyQt5.QtWidgets import QFrame as _F, QHBoxLayout as _H, QVBoxLayout as _V, QLabel as _L

        N = Colors.NEUTRAL
        bar = _F()
        bar.setObjectName("prodStatsBar")
        bar.setFixedHeight(68)
        bar.setStyleSheet(
            f"QFrame#prodStatsBar {{ "
            f"background:{N.DARK_CARD}; "
            f"border-radius:8px; "
            f"border:1px solid {N.DARK_BORDER}; }}"
        )

        lay = _H(bar)
        lay.setContentsMargins(Spacing.LG, Spacing.SM, Spacing.LG, Spacing.SM)
        lay.setSpacing(0)

        # Definición inicial de KPIs (valores placeholder)
        kpis = [
            ("producciones_hoy", "Producciones hoy", "—",    Colors.PRIMARY_BASE),
            ("kg_procesados",    "Kg procesados",    "—",    Colors.SUCCESS_BASE),
            ("merma_dia",        "Merma del día",    "—",    Colors.WARNING_BASE),
            ("rendimiento",      "Rendimiento",      "—",    Colors.SUCCESS_BASE),
            ("lotes_activos",    "Lotes activos",    "—",    Colors.INFO_BASE),
        ]

        # Guardar referencias a los QLabel de valor para actualizaciones en vivo
        self._stats_lbl_vals: dict = {}

        for i, (key, label, valor, color) in enumerate(kpis):
            if i > 0:
                sep = _F()
                sep.setFrameShape(_F.VLine)
                sep.setFixedWidth(1)
                sep.setStyleSheet(f"background:{N.SLATE_700}; border:none;")
                lay.addWidget(sep)
                lay.addSpacing(Spacing.LG)

            col = _V()
            col.setSpacing(2)

            lbl_v = _L(valor)
            lbl_v.setStyleSheet(
                f"color:{color}; font-size:18px; font-weight:700; background:transparent;"
            )
            lbl_l = _L(label.upper())
            lbl_l.setStyleSheet(
                f"color:{N.SLATE_500}; font-size:9px; font-weight:700; "
                f"letter-spacing:0.5px; background:transparent;"
            )

            self._stats_lbl_vals[key] = (lbl_v, color)  # (label_widget, color_ok)
            col.addWidget(lbl_v)
            col.addWidget(lbl_l)
            lay.addLayout(col)

            if i < len(kpis) - 1:
                lay.addSpacing(Spacing.LG)

        lay.addStretch()

        # Cargar valores reales en diferido para no bloquear arranque
        QTimer.singleShot(50, self._actualizar_stats_bar)
        return bar

    def _actualizar_stats_bar(self) -> None:
        """Actualiza los QLabels de la stats bar con datos del servicio de query."""
        if not hasattr(self, '_stats_lbl_vals'):
            return

        db = self.conexion
        if not db:
            return

        vals = _pqs.get_daily_kpis(db)

        # ── Formatear y actualizar QLabels ───────────────────────────────────
        kg_p  = vals.get("kg_procesados", 0)
        merma = vals.get("merma_dia", 0)
        rend  = vals.get("rendimiento", 0.0)

        formatos = {
            "producciones_hoy": (
                str(vals.get("producciones_hoy", 0)),
                Colors.PRIMARY_BASE,
            ),
            "kg_procesados": (
                f"{kg_p:.1f} kg",
                Colors.SUCCESS_BASE,
            ),
            "merma_dia": (
                f"{merma:.1f} kg",
                Colors.DANGER_BASE if merma > 0 else Colors.SUCCESS_BASE,
            ),
            "rendimiento": (
                f"{rend:.1f}%",
                Colors.SUCCESS_BASE if rend >= 90 else Colors.WARNING_BASE,
            ),
            "lotes_activos": (
                str(vals.get("lotes_activos", 0)),
                Colors.INFO_BASE,
            ),
        }

        for key, (lbl_w, _default_color) in self._stats_lbl_vals.items():
            if key in formatos:
                texto, color = formatos[key]
                lbl_w.setText(texto)
                lbl_w.setStyleSheet(
                    f"color:{color}; font-size:18px; font-weight:700; background:transparent;"
                )

    # ── TAB: Ejecutar Producción ──────────────────────────────────────────────

    def _build_tab_produccion(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        sp = QSplitter(Qt.Horizontal)

        # ── Izquierda: formulario ─────────────────────────────────────────────
        left = QGroupBox("Configuración de Producción")
        fl = QVBoxLayout(left)
        fl.setSpacing(8)

        # Receta
        fl.addWidget(QLabel("Receta:"))
        self._combo_receta = QComboBox()
        self._combo_receta.currentIndexChanged.connect(self._on_receta_changed)
        fl.addWidget(self._combo_receta)

        # Info receta
        self._lbl_tipo = QLabel()
        self._lbl_tipo.setObjectName("badge")
        fl.addWidget(self._lbl_tipo)

        self._lbl_base = QLabel()
        self._lbl_base.setObjectName("caption")
        fl.addWidget(self._lbl_base)

        # Cantidad base
        fl.addWidget(QLabel("Cantidad base:"))
        qty_row = QHBoxLayout()
        self._spin_cant = QDoubleSpinBox()
        self._spin_cant.setRange(0.001, 999999)
        self._spin_cant.setDecimals(3)
        self._spin_cant.setValue(1.0)
        self._spin_cant.setSingleStep(0.5)
        self._spin_cant.valueChanged.connect(self._on_cant_changed)
        self._lbl_unidad = QLabel("kg")
        self._lbl_unidad.setObjectName("textSecondary")
        qty_row.addWidget(self._spin_cant)
        qty_row.addWidget(self._lbl_unidad)
        qty_row.addStretch()
        fl.addLayout(qty_row)

        # Notas
        fl.addWidget(QLabel("Notas (opcional):"))
        self._e_notas = QLineEdit()
        self._e_notas.setPlaceholderText("Observaciones de esta producción…")
        fl.addWidget(self._e_notas)

        fl.addStretch()

        # Stock disponible del producto base
        self._grp_stock = QGroupBox("Stock disponible")
        sl = QVBoxLayout(self._grp_stock)
        self._lbl_stock = QLabel("—")
        self._lbl_stock.setObjectName("subheading")
        sl.addWidget(self._lbl_stock)
        fl.addWidget(self._grp_stock)

        # Botones
        btn_preview = create_primary_button(self, "🔍 Vista Previa", "Ver movimientos antes de ejecutar producción")
        btn_preview.clicked.connect(self._preview)
        fl.addWidget(btn_preview)

        self._btn_ejecutar = create_success_button(self, "▶ EJECUTAR PRODUCCIÓN", "Ejecutar producción con validación de stock")
        self._btn_ejecutar.clicked.connect(self._ejecutar)
        fl.addWidget(self._btn_ejecutar)

        sp.addWidget(left)

        # ── Derecha: preview de movimientos ──────────────────────────────────
        right = QGroupBox("Vista Previa de Movimientos")
        rl = QVBoxLayout(right)

        self._tbl_prev = QTableWidget()
        self._tbl_prev.setColumnCount(5)
        self._tbl_prev.setHorizontalHeaderLabels(
            ["Movimiento", "Producto", "Cantidad", "Unidad", "Stock Actual"]
        )
        self._tbl_prev.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_prev.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_prev.verticalHeader().setVisible(False)
        self._tbl_prev.setAlternatingRowColors(True)
        hdr = self._tbl_prev.horizontalHeader()
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        for i in (0, 2, 3, 4):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        rl.addWidget(self._tbl_prev)

        # Resumen
        self._lbl_resumen = QLabel()
        self._lbl_resumen.setObjectName("subheading")
        rl.addWidget(self._lbl_resumen)

        sp.addWidget(right)
        sp.setSizes([300, 500])
        lay.addWidget(sp)
        return w

    # ── TAB: Historial ────────────────────────────────────────────────────────

    def _build_tab_historial(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        # Filtros
        fh = QHBoxLayout()
        self._hist_filter = FilterBar(self, placeholder="Receta, usuario o producto base…")
        self._hist_filter.filters_changed.connect(lambda _v: self._load_historial())
        self._search_hist = self._hist_filter.search
        fh.addWidget(self._hist_filter, 1)
        btn_ref = QPushButton("🔄 Actualizar")
        btn_ref.clicked.connect(self._load_historial)
        fh.addWidget(btn_ref)
        fh.addStretch()
        lay.addLayout(fh)
        self._hist_loading = LoadingIndicator("Cargando historial de producción…", self)
        self._hist_loading.hide()
        lay.addWidget(self._hist_loading)

        sp = QSplitter(Qt.Horizontal)

        # Lista de producciones
        self._tbl_hist = QTableWidget()
        self._tbl_hist.setColumnCount(7)
        self._tbl_hist.setHorizontalHeaderLabels(
            ["ID", "Fecha", "Receta", "Tipo", "Base", "Cantidad", "Usuario"]
        )
        self._tbl_hist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_hist.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_hist.verticalHeader().setVisible(False)
        self._tbl_hist.setAlternatingRowColors(True)
        hdr2 = self._tbl_hist.horizontalHeader()
        hdr2.setSectionResizeMode(2, QHeaderView.Stretch)
        for i in (0, 1, 3, 4, 5, 6):
            hdr2.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._tbl_hist.itemSelectionChanged.connect(self._on_hist_sel)
        sp.addWidget(self._tbl_hist)
        self._hist_empty = EmptyStateWidget(
            "Sin producciones",
            "No hay registros de producción para el filtro aplicado.",
            "📭",
            self,
        )
        self._hist_empty.hide()

        # Detalle
        right = QGroupBox("Detalle de Producción")
        rl = QVBoxLayout(right)
        self._tbl_det = QTableWidget()
        self._tbl_det.setColumnCount(5)
        self._tbl_det.setHorizontalHeaderLabels(
            ["Tipo", "Producto", "Cantidad", "Unidad", "Rendimiento %"]
        )
        self._tbl_det.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_det.verticalHeader().setVisible(False)
        self._tbl_det.setAlternatingRowColors(True)
        hdr3 = self._tbl_det.horizontalHeader()
        hdr3.setSectionResizeMode(1, QHeaderView.Stretch)
        for i in (0, 2, 3, 4):
            hdr3.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        rl.addWidget(self._tbl_det)
        self._lbl_det_info = QLabel()
        self._lbl_det_info.setObjectName("caption")
        rl.addWidget(self._lbl_det_info)
        sp.addWidget(right)
        sp.setSizes([480, 340])

        lay.addWidget(sp)
        lay.addWidget(self._hist_empty)
        return w

    # ── Datos ─────────────────────────────────────────────────────────────────

    def _build_tab_carnica(self) -> QWidget:
        """Tab de producción cárnica — integra lógica de produccion_carnica.py."""
        from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
            QGroupBox, QFormLayout, QLabel, QComboBox, QDoubleSpinBox,
            QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox)
        w = QWidget(); lay = QVBoxLayout(w)

        grp_in = QGroupBox("Ingresar lote a producción cárnica")
        form = QFormLayout(grp_in)

        self._car_cmb_producto = QComboBox()
        self._car_spin_peso    = QDoubleSpinBox(); self._car_spin_peso.setRange(0.001,9999); self._car_spin_peso.setDecimals(3); self._car_spin_peso.setSuffix(" kg")
        self._car_spin_merma   = QDoubleSpinBox(); self._car_spin_merma.setRange(0,100); self._car_spin_merma.setDecimals(1); self._car_spin_merma.setSuffix(" %")
        form.addRow("Producto:", self._car_cmb_producto)
        form.addRow("Peso bruto:", self._car_spin_peso)
        form.addRow("Merma esperada:", self._car_spin_merma)
        lay.addWidget(grp_in)

        btn_row = QHBoxLayout()
        btn_proc = create_danger_button(self, "⚙️ Procesar lote cárnico", "Procesar lote de producción cárnica con cálculo de merma")
        btn_row.addWidget(btn_proc); btn_row.addStretch()
        lay.addLayout(btn_row)

        self._car_tabla = QTableWidget(); self._car_tabla.setColumnCount(5)
        self._car_tabla.setHorizontalHeaderLabels(["Fecha","Producto","Bruto kg","Merma kg","Neto kg"])
        hh = self._car_tabla.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        lay.addWidget(self._car_tabla)

        btn_proc.clicked.connect(self._procesar_lote_carnico)
        self._cargar_productos_carnica()
        self._cargar_hist_carnica()
        return w

    def _cargar_productos_carnica(self):
        self._car_cmb_producto.clear()
        conn = self._conexion if hasattr(self, '_conexion') else (
            self.conexion if hasattr(self, 'conexion') else None)
        if not conn:
            return
        for r in _pqs.get_productos_activos(conn):
            self._car_cmb_producto.addItem(r["nombre"], r["id"])

    def _on_refresh(self, event_type: str, data: dict) -> None:
        """Auto-refresh al recibir eventos del EventBus."""
        try:
            self._cargar_hist_carnica()
        except Exception as exc:
            logger.debug("No se pudo refrescar historial cárnico: %s", exc)

    def _cargar_hist_carnica(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        conn = self._conexion if hasattr(self, '_conexion') else (
            self.conexion if hasattr(self, 'conexion') else None)
        if not conn:
            self._car_tabla.setRowCount(0)
            return
        rows = _pqs.get_historial_carnica(conn)
        self._car_tabla.setRowCount(0)
        for i, r in enumerate(rows):
            self._car_tabla.insertRow(i)
            for j, v in enumerate([r["fecha"], r["producto"],
                                    r["peso_bruto"], r["merma"], r["peso_neto"]]):
                self._car_tabla.setItem(i, j, QTableWidgetItem(str(v) if v else ""))

    def _procesar_lote_carnico(self):
        """
        Delega al RecipeEngine — registra la producción con trazabilidad completa.
        Busca la receta activa del producto seleccionado (tipo subproducto).
        """
        prod_id = self._car_cmb_producto.currentData()
        if not prod_id:
            QMessageBox.warning(self, "Aviso", "Selecciona un producto."); return

        peso = self._car_spin_peso.value()
        if peso <= 0:
            QMessageBox.warning(self, "Aviso", "El peso debe ser mayor a cero."); return

        conn = getattr(self, '_conexion', None) or getattr(self, 'conexion', None)
        if not conn: return

        # Find active recipe for this base product
        rec_row = _pqs.get_receta_by_product_id(conn, prod_id)

        if not rec_row:
            QMessageBox.warning(
                self, "Sin receta",
                "Este producto no tiene una receta activa.\n"
                "Créala desde Productos > Tab Receta antes de registrar producción.")
            return

        receta_id  = rec_row["id"]
        receta_nom = rec_row["nombre_receta"]

        # Preview before confirming (teórico)
        _suc = getattr(self, 'sucursal_id', 1)
        _usr = getattr(self, 'usuario_actual', '') or getattr(self, 'usuario', 'Sistema')
        try:
            if self._svc is not None:
                preview = self._svc.preview_receta(receta_id, peso)
            else:
                preview = self._engine.preview_produccion(receta_id, peso)
        except Exception as _pe:
            QMessageBox.critical(self, "Error al previsualizar", str(_pe)); return

        # Capturar salida real por componente antes de cerrar lote
        reales = {}
        for m in preview:
            if float(m.get("delta", 0)) <= 0:
                continue
            ptxt = f"Peso real de salida para {m['nombre']} (kg):"
            val, ok = QInputDialog.getDouble(self, "Captura real", ptxt, abs(float(m["delta"])), 0.0, 99999.0, 3)
            if not ok:
                return
            reales[int(m["product_id"])] = float(val)

        bal = _build_lote_balance_preview(preview, reales)
        lines = [f"Receta: {receta_nom}", f"Entrada: {peso:.3f} kg", ""]
        for m in preview:
            arrow = "▼ SALIDA" if m['delta'] < 0 else "▲ ENTRADA"
            lines.append(f"{arrow}  {m['nombre']}: {abs(m['delta']):.3f} kg")
        lines += ["", "Captura REAL:", *(f"• #{pid}: {kg:.3f} kg" for pid, kg in reales.items())]
        lines += [f"Teórico total: {bal['total_expected']:.3f} kg",
                  f"Real total: {bal['total_real']:.3f} kg",
                  f"Diferencia: {bal['difference']:+.3f} kg"]

        resp = QMessageBox.question(self, "Confirmar producción",
            "\n".join(lines) + "\n\n¿Ejecutar?",
            QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes: return

        try:
            # FASE 8: flujo real por lote (sin ejecutar_produccion directa)
            if self._svc is None:
                raise RuntimeError("ProductionApplicationService no disponible para flujo por lote.")
            opened = self._svc.abrir_lote(
                producto_origen_id=prod_id,
                peso_kg=peso,
                sucursal_id=_suc,
                usuario=_usr,
                receta_id=receta_id,
            )
            if not getattr(opened, "ok", False):
                raise RuntimeError(getattr(opened, "error", "No se pudo abrir lote"))
            batch_id = opened.batch_id
            for pid, kg in reales.items():
                self._svc.agregar_subproducto(batch_id=batch_id, producto_id=pid, peso_kg=kg, is_waste=False)
            merma_kg = max(0.0, peso - bal["total_real"])
            if merma_kg > 0:
                self._svc.agregar_subproducto(batch_id=batch_id, producto_id=prod_id, peso_kg=merma_kg, is_waste=True)
            y = self._svc.preview_lote(batch_id)
            res = self._svc.cerrar_lote(batch_id=batch_id, sucursal_id=_suc, usuario=_usr)
            if not getattr(res, "ok", False):
                raise RuntimeError(getattr(res, "error", "No se pudo cerrar lote"))
            try:
                get_bus().publish("PRODUCCION_REGISTRADA", {"event_type": "PRODUCCION_REGISTRADA"})
            except Exception as exc:
                logger.debug("No se pudo publicar PRODUCCION_REGISTRADA: %s", exc)

            # Build result summary
            result_lines = [
                f"Lote {res.folio} cerrado",
                f"Rendimiento: {getattr(res, 'rendimiento_pct', 0):.2f}%",
                f"Merma registrada: {merma_kg:.3f} kg",
                "",
                f"Diferencia esperado vs real: {bal['difference']:+.3f} kg",
            ]
            QMessageBox.information(self, "✅ Producción Registrada",
                "\n".join(result_lines))
            self._cargar_hist_carnica()

        except Exception as e:
            QMessageBox.critical(self, "Error en producción", str(e))



    def _load_recetas(self) -> None:
        try:
            self._recetas_cache = _pqs.get_recetas_for_combo(self.conexion)
        except Exception as exc:
            logger.warning("load_recetas: %s", exc)
            self._recetas_cache = []

        prev_id = self._combo_receta.currentData()
        self._combo_receta.blockSignals(True)
        self._combo_receta.clear()
        self._combo_receta.addItem("— Seleccionar receta —", None)
        for r in self._recetas_cache:
            tipo_raw = _norm_tipo_receta(r.get("tipo_receta", ""))
            tipo_lbl = TIPO_LABELS.get(tipo_raw, tipo_raw)
            self._combo_receta.addItem(
                f"{r['nombre']}  [{tipo_lbl}]", r["id"]
            )
        # Restaurar selección previa
        if prev_id:
            idx = self._combo_receta.findData(prev_id)
            if idx >= 0:
                self._combo_receta.setCurrentIndex(idx)
        self._combo_receta.blockSignals(False)
        self._on_receta_changed()

    def _get_receta_actual(self) -> Optional[Dict]:
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
        tipo = _norm_tipo_receta(r.get("tipo_receta", ""))
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
            pid = r.get("producto_base_id")
            if not pid:
                self._lbl_stock.setText("—")
                return
            stock = _pqs.get_stock(self.conexion, pid, self.sucursal_id)
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
            self._lbl_resumen.setText("⚠ Seleccione una receta para ver la vista previa.")
            self._btn_ejecutar.setEnabled(False)
            return
        cant = self._spin_cant.value()
        try:
            if self._svc is not None:
                movs = self._svc.preview_receta(r["id"], cant)
            else:
                movs = self._engine.preview_produccion(r["id"], cant)
        except Exception as exc:
            self._tbl_prev.setRowCount(0)
            self._lbl_resumen.setText(f"⚠ {exc}")
            self._btn_ejecutar.setEnabled(False)
            return

        # Obtener stocks actuales
        try:
            prod_ids = list({m["product_id"] for m in movs})
            stocks = _pqs.get_stocks_for_products(self.conexion, prod_ids, self.sucursal_id)
        except Exception:
            stocks = {}

        self._tbl_prev.setRowCount(len(movs))
        total_in = 0.0; total_out = 0.0
        hay_error = False

        for ri, mov in enumerate(movs):
            delta = float(mov["delta"])
            pid = mov["product_id"]
            stock_act = stocks.get(pid, 0.0)
            es_salida = delta < 0

            if es_salida and stock_act < abs(delta) - 0.001:
                hay_error = True

            tipo_str = "⬇ CONSUMO" if es_salida else "⬆ GENERADO"
            tipo_color = Colors.DANGER_BASE if es_salida else Colors.SUCCESS_BASE
            stock_color = Colors.DANGER_BASE if (es_salida and stock_act < abs(delta)) else Colors.SUCCESS_BASE

            vals = [
                tipo_str,
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
            # Usar objectName para estilos dinámicos en lugar de setStyleSheet
            self._lbl_resumen.setObjectName("textDanger")
            self._lbl_resumen.style().unpolish(self._lbl_resumen)
            self._lbl_resumen.style().polish(self._lbl_resumen)
            self._btn_ejecutar.setEnabled(False)
        else:
            self._lbl_resumen.setText(
                f"✅ OK | Consumo: {total_out:.3f} | Generado: {total_in:.3f} | "
                f"Movimientos: {len(movs)}"
            )
            # Usar objectName para estilos dinámicos en lugar de setStyleSheet
            self._lbl_resumen.setObjectName("textSuccess")
            self._lbl_resumen.style().unpolish(self._lbl_resumen)
            self._lbl_resumen.style().polish(self._lbl_resumen)
            self._btn_ejecutar.setEnabled(True)

    # ── Ejecutar ──────────────────────────────────────────────────────────────

    def _ejecutar(self) -> None:
        r = self._get_receta_actual()
        if not r:
            QMessageBox.warning(self, "Validación", "Seleccione una receta.")
            return
        cant = self._spin_cant.value()
        tipo = _norm_tipo_receta(r.get("tipo_receta", ""))
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
            if self._svc is not None:
                resultado = self._svc.ejecutar_produccion(
                    receta_id    = r["id"],
                    cantidad_base= cant,
                    usuario      = self.usuario_actual,
                    sucursal_id  = self.sucursal_id,
                    notas        = self._e_notas.text().strip(),
                )
            else:
                resultado = self._engine.ejecutar_produccion(
                    receta_id=r["id"],
                    cantidad_base=cant,
                    usuario=self.usuario_actual,
                    sucursal_id=self.sucursal_id,
                    notas=self._e_notas.text().strip(),
                )
            self._btn_ejecutar.setText("▶ EJECUTAR PRODUCCIÓN")
            self._btn_ejecutar.setEnabled(True)

            # Mostrar resultado
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
            self._btn_ejecutar.setText("▶ EJECUTAR PRODUCCIÓN")
            self._btn_ejecutar.setEnabled(True)
            QMessageBox.critical(self, "Stock Insuficiente", str(exc))
        except ProduccionDuplicadaError as exc:
            self._btn_ejecutar.setText("▶ EJECUTAR PRODUCCIÓN")
            self._btn_ejecutar.setEnabled(True)
            QMessageBox.warning(self, "Producción Duplicada", str(exc))
        except RecetaNoEncontradaError as exc:
            self._btn_ejecutar.setText("▶ EJECUTAR PRODUCCIÓN")
            self._btn_ejecutar.setEnabled(True)
            QMessageBox.warning(self, "Receta No Encontrada", str(exc))
        except RecipeEngineError as exc:
            self._btn_ejecutar.setText("▶ EJECUTAR PRODUCCIÓN")
            self._btn_ejecutar.setEnabled(True)
            QMessageBox.critical(self, "Error de Producción", str(exc))
        except Exception as exc:
            self._btn_ejecutar.setText("▶ EJECUTAR PRODUCCIÓN")
            self._btn_ejecutar.setEnabled(True)
            logger.exception("ejecutar_produccion")
            QMessageBox.critical(self, "Error Inesperado", str(exc))

    # ── Historial ─────────────────────────────────────────────────────────────

    def _load_historial(self) -> None:
        if hasattr(self, "_hist_loading"):
            self._hist_loading.show()
        search = (self._search_hist.text() if hasattr(self, "_search_hist") else "").strip().lower()
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
                rows = [r for r in rows
                        if search in r.get("receta_nombre", "").lower()
                        or search in r.get("usuario", "").lower()
                        or search in r.get("producto_base_nombre", "").lower()]

            self._tbl_hist.setRowCount(len(rows))
            if hasattr(self, "_hist_empty"):
                self._hist_empty.setVisible(len(rows) == 0)
            for ri, r in enumerate(rows):
                tipo = _norm_tipo_receta(r.get("tipo_receta", ""))
                tipo_color = TIPO_COLOR.get(tipo, Colors.TEXT_SECONDARY)
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
                    # Guardar produccion_id en col 0
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
        total_in = 0.0; total_out = 0.0

        for ri, d in enumerate(detalles):
            tipo = d.get("tipo", "salida")
            cant = float(d.get("cantidad_generada", 0))
            rend = float(d.get("rendimiento_aplicado", 0))
            es_entrada = tipo == "entrada"
            color = Colors.SUCCESS_BASE if es_entrada else Colors.DANGER_BASE

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
