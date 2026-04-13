
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
from core.services.auto_audit import audit_write
from modulos.spj_styles import spj_btn, apply_btn_styles

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QGroupBox, QSplitter,
    QMessageBox, QTextEdit, QLineEdit, QTabWidget, QFrame,
    QScrollArea, QProgressBar, QDialog, QFormLayout, QCheckBox
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

logger = logging.getLogger("spj.ui.produccion")

_DARK  = "#1a252f"
_BLUE  = "#2980b9"
_GREEN = "#27ae60"
_RED   = "#e74c3c"
_GOLD  = "#f39c12"
_GRAY  = "#7f8c8d"

TIPO_LABELS = {
    "subproducto": "🔪 Despiece / Subproductos",
    "combinacion": "📦 Kit / Paquete / Combo",
    "produccion":  "🍳 Producción / Elaboración",
}
TIPO_COLOR = {
    "subproducto": _RED,
    "combinacion": _BLUE,
    "produccion":  _GREEN,
}


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
        try: self.conn.commit()
        except Exception: pass
    def rollback(self):
        try: self.conn.rollback()
        except Exception: pass
    from contextlib import contextmanager
    @contextmanager
    def transaction(self, name=""):
        import uuid as _u
        sp = f"sp_{_u.uuid4().hex[:8]}"
        self.conn.execute(f"SAVEPOINT {sp}")
        try:
            yield self
            self.conn.execute(f"RELEASE SAVEPOINT {sp}")
        except Exception:
            try: self.conn.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            except Exception: pass
            raise


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
        self._recetas_cache: List[Dict] = []
        self._init_ui()
        self._subscribe_events()
        QTimer.singleShot(0, self._refresh_all)

    # ── Setup ─────────────────────────────────────────────────────────────────

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
            try: EventBus.unsubscribe(evt, self._on_data_changed)
            except Exception: pass

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

    # ── UI ────────────────────────────────────────────────────────────────────

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        ttl = QLabel("🔪 Procesamiento Cárnico")
        f = ttl.font(); f.setPointSize(15); f.setBold(True); ttl.setFont(f)
        ttl.setObjectName("tituloPrincipal")
        self._lbl_suc = QLabel()
        self._lbl_suc.setStyleSheet(f"color:{_GRAY};")
        hdr.addWidget(ttl); hdr.addStretch(); hdr.addWidget(self._lbl_suc)
        root.addLayout(hdr)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_tab_produccion(), "🏭 Ejecutar Producción")
        self._tabs.addTab(self._build_tab_historial(),  "📋 Historial")
        self._tabs.addTab(self._build_tab_carnica(),    "🥩 Cárnica / Lotes")
        self._tabs.addTab(self._build_tab_recetas(),    "📋 Recetas")
        root.addWidget(self._tabs)

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
        self._lbl_tipo.setStyleSheet("font-weight:bold; padding:4px; border-radius:4px;")
        fl.addWidget(self._lbl_tipo)

        self._lbl_base = QLabel()
        self._lbl_base.setStyleSheet(f"color:{_GRAY}; font-size:12px;")
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
        self._lbl_unidad.setStyleSheet(f"color:{_GRAY};")
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
        self._lbl_stock.setStyleSheet("font-size:14px; font-weight:bold;")
        sl.addWidget(self._lbl_stock)
        fl.addWidget(self._grp_stock)

        # Botones
        btn_preview = QPushButton("🔍 Vista Previa")
        btn_preview.setStyleSheet(f"background:{_BLUE};color:white;font-weight:bold;padding:8px;border-radius:4px;")
        btn_preview.clicked.connect(self._preview)
        fl.addWidget(btn_preview)

        self._btn_ejecutar = QPushButton("▶ EJECUTAR PRODUCCIÓN")
        self._btn_ejecutar.setStyleSheet(
            f"background:{_GREEN};color:white;font-size:14px;font-weight:bold;"
            f"padding:10px;border-radius:4px;"
        )
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
        self._lbl_resumen.setStyleSheet("font-weight:bold; padding:4px;")
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
        fh.addWidget(QLabel("Buscar:"))
        self._search_hist = QLineEdit()
        self._search_hist.setPlaceholderText("Receta o usuario…")
        self._search_hist.textChanged.connect(self._load_historial)
        fh.addWidget(self._search_hist)
        btn_ref = QPushButton("🔄 Actualizar")
        btn_ref.clicked.connect(self._load_historial)
        fh.addWidget(btn_ref)
        fh.addStretch()
        lay.addLayout(fh)

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
        self._lbl_det_info.setStyleSheet(f"color:{_GRAY}; font-size:12px;")
        rl.addWidget(self._lbl_det_info)
        sp.addWidget(right)
        sp.setSizes([480, 340])

        lay.addWidget(sp)
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
        btn_proc = QPushButton("⚙️ Procesar lote cárnico"); btn_proc.setStyleSheet("background:#c0392b;color:white;font-weight:bold;padding:7px;")
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
        try:
            conn = self._conexion if hasattr(self,'_conexion') else                    (self.conexion if hasattr(self,'conexion') else None)
            if not conn: return
            rows = conn.execute(
                "SELECT id, nombre FROM productos WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            for r in rows:
                self._car_cmb_producto.addItem(r[1] if hasattr(r,'keys') else r[1], r[0] if hasattr(r,'keys') else r[0])
        except Exception: pass

    def _on_refresh(self, event_type: str, data: dict) -> None:
        """Auto-refresh al recibir eventos del EventBus."""
        try: self._cargar_hist_carnica()
        except Exception: pass

    def _cargar_hist_carnica(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        try:
            conn = self._conexion if hasattr(self,'_conexion') else                    (self.conexion if hasattr(self,'conexion') else None)
            if not conn: self._car_tabla.setRowCount(0); return
            rows = conn.execute("""
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
        rec_row = conn.execute(
            "SELECT id, nombre_receta FROM product_recipes "
            "WHERE base_product_id=? AND is_active=1 LIMIT 1",
            (prod_id,)).fetchone()

        if not rec_row:
            QMessageBox.warning(
                self, "Sin receta",
                "Este producto no tiene una receta activa.\n"
                "Crea la receta en el módulo Recetas antes de registrar producción.")
            return

        receta_id   = rec_row[0] if not hasattr(rec_row, 'keys') else rec_row['id']
        receta_nom  = rec_row[1] if not hasattr(rec_row, 'keys') else rec_row['nombre_receta']

        # Preview before confirming
        try:
            from core.services.recipe_engine import RecipeEngine
            engine = RecipeEngine(self.container.db,
                                  branch_id=getattr(self,'sucursal_id',1))
            preview = engine.preview_produccion(receta_id, peso)
        except Exception as _pe:
            QMessageBox.critical(self, "Error al previsualizar", str(_pe)); return

        # Build confirmation message
        lines = [f"Receta: {receta_nom}", f"Entrada: {peso:.3f} kg", ""]
        for m in preview:
            arrow = "▼ SALIDA" if m['delta'] < 0 else "▲ ENTRADA"
            lines.append(f"{arrow}  {m['nombre']}: {abs(m['delta']):.3f} kg")

        resp = QMessageBox.question(self, "Confirmar producción",
            "\n".join(lines) + "\n\n¿Ejecutar?",
            QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes: return

        try:
            res = engine.ejecutar_produccion(
                receta_id=receta_id,
                cantidad_base=peso,
                usuario=getattr(self,'usuario_actual','') or getattr(self,'usuario','Sistema'),
                sucursal_id=getattr(self,'sucursal_id',1),
                notas=f"Lote cárnico produccion.py",
            )
            try: get_bus().publish("PRODUCCION_REGISTRADA", {"event_type": "PRODUCCION_REGISTRADA"})
            except Exception: pass

            # Build result summary
            result_lines = [
                f"Producción #{res.produccion_id} registrada",
                f"Total generado:  {res.total_generado:.3f} kg",
                f"Total consumido: {res.total_consumido:.3f} kg",
                "",
            ]
            for comp in res.componentes:
                arrow = "▲" if comp.tipo == "entrada" else "▼"
                result_lines.append(f"{arrow} {comp.nombre}: {comp.cantidad:.3f} kg")

            QMessageBox.information(self, "✅ Producción Registrada",
                "\n".join(result_lines))
            self._cargar_hist_carnica()

        except Exception as e:
            QMessageBox.critical(self, "Error en producción", str(e))

    def _build_tab_recetas(self) -> QWidget:
        """Tab de recetas — CRUD completo con DialogoReceta de recetas.py."""
        from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
            QLabel, QLineEdit, QPushButton, QTableWidget,
            QTableWidgetItem, QHeaderView, QSplitter, QMessageBox)
        from PyQt5.QtCore import Qt

        w = QWidget(); lay = QVBoxLayout(w)

        info = QLabel("Gestión de recetas para producción y despiece cárnico. "
                       "Cada receta define insumos, rendimientos y subproductos.")
        info.setWordWrap(True)
        info.setStyleSheet("color:#555;background:#f0f4ff;padding:5px;border-radius:5px;font-size:11px;")
        lay.addWidget(info)

        # Botones principales
        btn_row = QHBoxLayout()
        btn_nueva = QPushButton("➕ Nueva receta")
        btn_nueva.setStyleSheet("background:#27ae60;color:white;font-weight:bold;padding:5px 12px;border-radius:4px;")
        btn_editar = QPushButton("✏️ Editar receta")
        btn_editar.setStyleSheet("background:#e67e22;color:white;font-weight:bold;padding:5px 12px;border-radius:4px;")
        btn_ver = QPushButton("👁️ Ver detalle")
        btn_desact = QPushButton("🗑️ Desactivar")
        btn_desact.setStyleSheet("background:#e74c3c;color:white;font-weight:bold;padding:5px 12px;border-radius:4px;")
        btn_refresh = QPushButton("🔄")
        btn_row.addWidget(btn_nueva); btn_row.addWidget(btn_editar)
        btn_row.addWidget(btn_ver); btn_row.addWidget(btn_desact)
        btn_row.addStretch(); btn_row.addWidget(btn_refresh)
        lay.addLayout(btn_row)

        # Tabla recetas
        self._rec_tabla = QTableWidget(); self._rec_tabla.setColumnCount(5)
        self._rec_tabla.setHorizontalHeaderLabels(
            ["ID", "Nombre", "Producto base", "Rendimiento", "Componentes"])
        hh = self._rec_tabla.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self._rec_tabla.setColumnHidden(0, True)
        self._rec_tabla.setSelectionBehavior(self._rec_tabla.SelectRows)
        self._rec_tabla.setAlternatingRowColors(True)
        lay.addWidget(self._rec_tabla)

        btn_nueva.clicked.connect(self._receta_nueva)
        btn_editar.clicked.connect(self._receta_editar)
        btn_ver.clicked.connect(self._ver_detalle_receta)
        btn_desact.clicked.connect(self._receta_desactivar)
        btn_refresh.clicked.connect(self._cargar_lista_recetas)
        self._cargar_lista_recetas()
        return w

    def _cargar_lista_recetas(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        try:
            conn = self._conexion if hasattr(self, '_conexion') else (
                self.conexion if hasattr(self, 'conexion') else None)
            if not conn:
                return
            rows = conn.execute("""
                SELECT r.id, r.nombre,
                       COALESCE(p.nombre, ''),
                       COALESCE(r.rendimiento_esperado_pct, 0),
                       (SELECT COUNT(*) FROM recipe_components WHERE recipe_id=r.id)
                FROM recetas r
                LEFT JOIN productos p ON p.id = r.producto_id
                WHERE COALESCE(r.is_active, 1) = 1
                ORDER BY r.nombre LIMIT 200
            """).fetchall()
        except Exception:
            try:
                rows = conn.execute("""
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
        for i, r in enumerate(rows):
            self._rec_tabla.insertRow(i)
            vals = [str(r[0]), r[1], r[2], f"{r[3]:.1f}%", str(r[4])]
            for j, v in enumerate(vals):
                self._rec_tabla.setItem(i, j, QTableWidgetItem(v))

    def _receta_nueva(self):
        """Abre DialogoReceta (integrado en este módulo) para crear receta completa."""
        conn = self._conexion if hasattr(self, '_conexion') else (
            self.conexion if hasattr(self, 'conexion') else None)
        if not conn:
            return
        try:
            from repositories.recetas import RecetaRepository
            repo = RecetaRepository(conn)
            productos = conn.execute(
                "SELECT id, nombre, unidad FROM productos WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            prods = [{'id': p[0], 'nombre': p[1], 'unidad': p[2] or 'kg'} for p in productos]
            usuario = getattr(self, 'usuario_actual', 'Sistema') or 'Sistema'
            dlg = DialogoReceta(repo, prods, usuario, parent=self)
            if dlg.exec_() == dlg.Accepted:
                self._cargar_lista_recetas()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo abrir editor de recetas:\n{e}")

    def _receta_editar(self):
        """Abre DialogoReceta (integrado en este módulo) para editar la receta seleccionada."""
        row = self._rec_tabla.currentRow()
        if row < 0:
            QMessageBox.information(self, "Aviso", "Selecciona una receta.")
            return
        rid = int(self._rec_tabla.item(row, 0).text())
        conn = self._conexion if hasattr(self, '_conexion') else (
            self.conexion if hasattr(self, 'conexion') else None)
        if not conn:
            return
        try:
            from repositories.recetas import RecetaRepository
            repo = RecetaRepository(conn)
            productos = conn.execute(
                "SELECT id, nombre, unidad FROM productos WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            prods = [{'id': p[0], 'nombre': p[1], 'unidad': p[2] or 'kg'} for p in productos]
            usuario = getattr(self, 'usuario_actual', 'Sistema') or 'Sistema'
            # Cargar datos de receta existente
            receta_row = conn.execute("SELECT * FROM recetas WHERE id=?", (rid,)).fetchone()
            receta_data = dict(receta_row) if receta_row else None
            comps = conn.execute(
                "SELECT * FROM recipe_components WHERE recipe_id=?", (rid,)
            ).fetchall()
            componentes = [dict(c) for c in comps] if comps else []
            dlg = DialogoReceta(repo, prods, usuario,
                                receta_data=receta_data,
                                componentes=componentes, parent=self)
            if dlg.exec_() == dlg.Accepted:
                self._cargar_lista_recetas()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo abrir editor:\n{e}")

    def _receta_desactivar(self):
        """Desactiva la receta seleccionada (soft delete)."""
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
        conn = self._conexion if hasattr(self, '_conexion') else (
            self.conexion if hasattr(self, 'conexion') else None)
        if not conn:
            return
        try:
            conn.execute("UPDATE recetas SET is_active=0 WHERE id=?", (rid,))
            try:
                conn.commit()
            except Exception:
                pass
            self._cargar_lista_recetas()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _nueva_receta_simple(self):
        """Fallback: crear receta con diálogo simple (sin DialogoReceta)."""
        from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
            QVBoxLayout, QLineEdit, QComboBox, QDoubleSpinBox, QMessageBox)
        conn = self._conexion if hasattr(self, '_conexion') else (
            self.conexion if hasattr(self, 'conexion') else None)
        if not conn:
            return
        dlg = QDialog(self); dlg.setWindowTitle("Nueva Receta"); dlg.setMinimumWidth(360)
        lay = QVBoxLayout(dlg); form = QFormLayout()
        txt_nombre = QLineEdit(); txt_nombre.setPlaceholderText("Nombre de la receta")
        cmb_producto = QComboBox()
        try:
            prods = conn.execute(
                "SELECT id, nombre FROM productos WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            for p in prods:
                cmb_producto.addItem(p[1], p[0])
        except Exception:
            pass
        spin_rend = QDoubleSpinBox()
        spin_rend.setRange(0, 100); spin_rend.setSuffix("%"); spin_rend.setDecimals(1)
        form.addRow("Nombre *:", txt_nombre)
        form.addRow("Producto base:", cmb_producto)
        form.addRow("Rendimiento esperado:", spin_rend)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() != QDialog.Accepted:
            return
        nombre = txt_nombre.text().strip()
        if not nombre:
            return
        try:
            conn.execute(
                "INSERT INTO recetas(nombre, producto_id, rendimiento_esperado_pct) VALUES(?,?,?)",
                (nombre, cmb_producto.currentData(), spin_rend.value()))
            try:
                conn.commit()
            except Exception:
                pass
            self._cargar_lista_recetas()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _ver_detalle_receta(self):
        # [spj-dedup] from PyQt5.QtWidgets import QMessageBox
        row = self._rec_tabla.currentRow()
        if row < 0: return
        rid = int(self._rec_tabla.item(row, 0).text())
        nombre = self._rec_tabla.item(row, 1).text()
        conn = self._conexion if hasattr(self,'_conexion') else                (self.conexion if hasattr(self,'conexion') else None)
        if not conn: return
        try:
            comps = conn.execute("""
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
                QMessageBox.information(self,"Sin componentes",
                    f"La receta '{nombre}' no tiene componentes registrados."); return
            txt = f"Receta: {nombre}\n\nComponentes:\n"
            for c in comps:
                txt += f"  • {c[0]}: {c[1]} {c[2] or 'u'} (merma {c[3]:.1f}%)\n"
            QMessageBox.information(self,"Detalle receta", txt)
        except Exception as e:
            QMessageBox.critical(self,"Error",str(e))


    def _load_recetas(self) -> None:
        try:
            rows = self.conexion.fetchall("""
                SELECT r.id, r.nombre, r.tipo_receta, r.producto_base_id,
                       r.peso_promedio_kg, r.unidad_base,
                       p.nombre AS prod_nombre, p.unidad AS prod_unidad
                FROM recetas r
                LEFT JOIN productos p ON p.id = r.producto_base_id
                WHERE r.activo = 1
                ORDER BY r.tipo_receta, r.nombre
            """)
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
        tipo = r.get("tipo_receta", "")
        color = TIPO_COLOR.get(tipo, _GRAY)
        self._lbl_tipo.setText(TIPO_LABELS.get(tipo, tipo))
        self._lbl_tipo.setStyleSheet(
            f"font-weight:bold;padding:4px;border-radius:4px;"
            f"background:{color};color:white;"
        )
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
            color = _GREEN if ok else _RED
            self._lbl_stock.setText(f"{stock:.3f} {unidad}")
            self._lbl_stock.setStyleSheet(
                f"font-size:14px;font-weight:bold;color:{color};"
            )
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

        # Obtener stocks actuales
        stocks = {}
        try:
            prod_ids = list({m["product_id"] for m in movs})
            for pid in prod_ids:
                row = self.conexion.fetchone("""
                    SELECT COALESCE(SUM(quantity), 0) as q
                    FROM branch_inventory
                    WHERE branch_id = ? AND product_id = ?
                """, (self.sucursal_id, pid))
                stocks[pid] = float(row["q"]) if row else 0.0
        except Exception:
            pass

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
            tipo_color = _RED if es_salida else _GREEN
            stock_color = _RED if (es_salida and stock_act < abs(delta)) else _GREEN

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
            self._lbl_resumen.setStyleSheet(f"color:{_RED};font-weight:bold;")
            self._btn_ejecutar.setEnabled(False)
        else:
            self._lbl_resumen.setText(
                f"✅ OK | Consumo: {total_out:.3f} | Generado: {total_in:.3f} | "
                f"Movimientos: {len(movs)}"
            )
            self._lbl_resumen.setStyleSheet(f"color:{_GREEN};font-weight:bold;")
            self._btn_ejecutar.setEnabled(True)

    # ── Ejecutar ──────────────────────────────────────────────────────────────

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
        search = (self._search_hist.text() if hasattr(self, "_search_hist") else "").strip().lower()
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
                # Guardar produccion_id en col 0
                if ci == 0:
                    it.setData(Qt.UserRole, r.get("id"))
                self._tbl_hist.setItem(ri, ci, it)

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
class DialogoReceta(QDialog):

    def __init__(
        self,
        repo: RecetaRepository,
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
        self._comp_rows: List[Dict] = []  # working copy
        self.setWindowTitle("Nueva Receta" if not receta_data else "Editar Receta")
        self.setMinimumWidth(700); self.setMinimumHeight(550)
        self._build_ui()
        if receta_data:
            self._load()

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)

        # Header form
        fl = QFormLayout()
        self._e_nombre = QLineEdit()
        self._e_nombre.setPlaceholderText("Nombre de la receta…")
        self._combo_base = QComboBox()
        self._combo_base.addItem("— Seleccionar producto base —", None)
        for p in self._productos:
            self._combo_base.addItem(
                f"{p['nombre']} [{p.get('unidad','kg')}]", p["id"]
            )
        fl.addRow("Nombre Receta*:", self._e_nombre)
        fl.addRow("Producto Base*:", self._combo_base)
        lay.addLayout(fl)

        # Components table
        grp = QGroupBox("Componentes (suma rendimiento + merma ≤ 100%)")
        gl = QVBoxLayout(grp)

        self._tbl_comp = QTableWidget()
        self._tbl_comp.setColumnCount(6)
        self._tbl_comp.setHorizontalHeaderLabels(
            ["Componente", "Rendimiento %", "Merma %", "Total %", "Tolerancia %", "Descripción"]
        )
        self._tbl_comp.verticalHeader().setVisible(False)
        self._tbl_comp.setAlternatingRowColors(True)
        hdr = self._tbl_comp.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3, 4, 5): hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        gl.addWidget(self._tbl_comp)

        # Add component form
        add_row = QHBoxLayout()
        self._combo_comp = QComboBox()
        self._combo_comp.addItem("— Componente —", None)
        for p in self._productos:
            self._combo_comp.addItem(f"{p['nombre']}", p["id"])
        self._spin_rend  = QDoubleSpinBox(); self._spin_rend.setRange(0, 100); self._spin_rend.setDecimals(3); self._spin_rend.setSuffix(" %")
        self._spin_merma = QDoubleSpinBox(); self._spin_merma.setRange(0, 100); self._spin_merma.setDecimals(3); self._spin_merma.setSuffix(" %")
        self._e_desc     = QLineEdit(); self._e_desc.setPlaceholderText("Descripción (opcional)")
        btn_add = QPushButton("➕ Agregar")
        btn_add.clicked.connect(self._add_component)
        btn_add.setStyleSheet(f"background:{_C3};color:white;padding:4px 10px;border-radius:3px;")
        btn_del = QPushButton("🗑 Quitar Sel.")
        btn_del.clicked.connect(self._remove_component)
        self._spin_tolerancia = QDoubleSpinBox()
        self._spin_tolerancia.setRange(0.1, 20.0); self._spin_tolerancia.setDecimals(1)
        self._spin_tolerancia.setSuffix(" %"); self._spin_tolerancia.setValue(2.0)
        self._spin_tolerancia.setToolTip(
            "Error relativo permitido.\n"
            "Si la producción real difiere más de este % del teórico,\n"
            "se registra como variación en el historial.")
        for w, lbl in [(self._combo_comp,"Comp:"), (QLabel("Rend:"), None),
                       (self._spin_rend,None), (QLabel("Merma:"),None),
                       (self._spin_merma,None), (QLabel("Toler:"),None),
                       (self._spin_tolerancia,None), (self._e_desc,None),
                       (btn_add,None), (btn_del,None)]:
            if lbl is not None: add_row.addWidget(QLabel(lbl))
            add_row.addWidget(w)
        gl.addLayout(add_row)

        # Totals
        self._lbl_totales = QLabel("Suma: 0.00%")
        self._lbl_totales.setStyleSheet("font-size:13px;font-weight:bold;")
        gl.addWidget(self._lbl_totales)
        lay.addWidget(grp)

        # Buttons
        bl = QHBoxLayout()
        btn_ok = QPushButton("💾 Guardar Receta"); btn_ok.clicked.connect(self._guardar)
        btn_no = QPushButton("Cancelar"); btn_no.clicked.connect(self.reject)
        btn_ok.setStyleSheet(f"background:{_C4};color:white;font-weight:bold;padding:6px 14px;border-radius:4px;")
        bl.addStretch(); bl.addWidget(btn_ok); bl.addWidget(btn_no)
        lay.addLayout(bl)

    def _load(self) -> None:
        d = self._data
        self._e_nombre.setText(d.get("nombre_receta", ""))
        idx = self._combo_base.findData(d.get("base_product_id"))
        if idx >= 0: self._combo_base.setCurrentIndex(idx)
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
            QMessageBox.warning(self, "Validación", "Seleccione un componente."); return
        rend  = self._spin_rend.value()
        merma = self._spin_merma.value()
        if rend + merma <= 0:
            QMessageBox.warning(self, "Validación",
                                "Rendimiento + Merma debe ser mayor a 0%."); return
        base_id = self._combo_base.currentData()
        if comp_id == base_id:
            QMessageBox.warning(self, "Auto-referencia",
                                "Un componente no puede ser el mismo producto base."); return
        # Check duplicate
        if any(r["component_product_id"] == comp_id for r in self._comp_rows):
            QMessageBox.warning(self, "Duplicado",
                                "Este componente ya está en la receta."); return
        comp_nombre = self._combo_comp.currentText()
        tolerancia = self._spin_tolerancia.value() if hasattr(self, '_spin_tolerancia') else 2.0
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
        if row < 0: return
        self._comp_rows.pop(row)
        self._refresh_comp_table()

    def _refresh_comp_table(self) -> None:
        self._tbl_comp.setRowCount(len(self._comp_rows))
        total_rend = Decimal("0"); total_merma = Decimal("0")
        for ri, r in enumerate(self._comp_rows):
            rend  = Decimal(str(r["rendimiento_pct"]))
            merma = Decimal(str(r["merma_pct"]))
            total_rend  += rend; total_merma += merma
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
                it = QTableWidgetItem(v); it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci in (1, 2, 3, 4): it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._tbl_comp.setItem(ri, ci, it)
        grand = float(total_rend + total_merma)
        ok = grand <= 100.01
        color = _C4 if ok else _C5
        icon  = "✅" if ok else "❌ EXCEDE 100%"
        self._lbl_totales.setText(
            f"{icon}  Rendimiento total: {float(total_rend):.3f}%  |  "
            f"Merma total: {float(total_merma):.3f}%  |  "
            f"Suma: {grand:.3f}%"
        )
        self._lbl_totales.setStyleSheet(f"font-size:13px;font-weight:bold;color:{color};")

    def _guardar(self) -> None:
        nombre = self._e_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Validación", "Nombre de receta obligatorio."); return
        base_id = self._combo_base.currentData()
        if not base_id:
            QMessageBox.warning(self, "Validación", "Seleccione producto base."); return
        if not self._comp_rows:
            QMessageBox.warning(self, "Validación", "Agregue al menos un componente."); return

        # Pre-validate totals client-side
        total = sum(
            Decimal(str(c["rendimiento_pct"])) + Decimal(str(c["merma_pct"]))
            for c in self._comp_rows
        )
        if total > Decimal("100.01"):
            QMessageBox.warning(
                self, "Error de Porcentaje",
                f"La suma total ({float(total):.3f}%) excede el 100%.\n"
                "Ajuste los porcentajes antes de guardar."
            ); return

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
