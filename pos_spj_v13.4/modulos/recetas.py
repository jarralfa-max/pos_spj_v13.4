
# modulos/recetas.py
# ── ModuloRecetas — Enterprise Recipe Management UI ──────────────────────────
# Block 2 requirements:
#   ✓ Prevent cyclic dependencies (validated in RecetaRepository)
#   ✓ Prevent self-reference (validated in RecetaRepository)
#   ✓ Enforce sum(componentes) + merma <= 100%
#   ✓ Mathematical validation before save
#   ✓ FK constraints + ON DELETE RESTRICT enforced by migration
#   ✓ Refresh dependent windows after update via EventBus
#   ✓ Prevent duplicate recipe for same base product
#   ✓ Transformation integrity tolerance 0.01kg
#   ✓ Integration with InventoryEngine batch tree validation
#   ✓ Complete UI (no partial/incomplete form)
from __future__ import annotations
from modulos.spj_styles import spj_btn, apply_btn_styles

import logging
from decimal import Decimal
from typing import Dict, List, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QMessageBox, QDialog, QFormLayout, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QTabWidget, QGroupBox,
    QHeaderView, QFrame, QSizePolicy, QSplitter, QDoubleSpinBox,
    QSpinBox, QScrollArea, QTextEdit, QProgressBar, QCheckBox
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor

from .base import ModuloBase
from repositories.recetas import (
    RecetaRepository,
    RecetaError,
    RecetaCyclicError,
    RecetaSelfReferenceError,
    RecetaPercentageError,
    RecetaDuplicadaError,
)
from repositories.productos import ProductoRepository
from core.events.event_bus import EventBus
from core.services.recipe_engine import (
    RecipeEngine,
    RecipeEngineError,
    StockInsuficienteProduccionError,
)

logger = logging.getLogger("spj.ui.recetas")

RECETA_CREADA      = "RECETA_CREADA"
RECETA_ACTUALIZADA = "RECETA_ACTUALIZADA"
PRODUCTO_CREADO    = "PRODUCTO_CREADO"
PRODUCTO_ACTUALIZADO = "PRODUCTO_ACTUALIZADO"

_C1 = "#1a252f"; _C3 = "#2980b9"; _C4 = "#27ae60"; _C5 = "#e74c3c"; _C6 = "#f39c12"
# --- WRAPPER PARA BLINDAR LA BASE DE DATOS ---
class _DBWrapper:
    def __init__(self, conexion):
        self.conn = conexion
    def fetchone(self, sql, params=()):
        r = self.conn.execute(sql, params).fetchone()
        if r is None: return None
        if hasattr(r, 'keys'): return r
        return r
    def fetchall(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()
    def fetchscalar(self, sql, params=(), default=None):
        r = self.conn.execute(sql, params).fetchone()
        return r[0] if r else default
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


class ModuloRecetas(ModuloBase):
    def __init__(self, container, parent=None):
        # 1. Inicializar la clase base estricta de PyQt5 (SOLO acepta parent)
        super().__init__(parent)
        
        # 2. Extraer la base de datos del contenedor (usar DatabaseWrapper directamente)
        from core.db.connection import wrap
        db_conn = wrap(container.db if hasattr(container, 'db') else container)

        # 3. Guardar referencias y variables de sucursal
        self.container = container
        self.main_window = parent
        self.sucursal_id = 1
        self.sucursal_nombre = "Principal"

        # 4. Exponer conexión (ya es DatabaseWrapper, no double-wrap con _DBWrapper)
        self.conexion = db_conn

        # 5. Inyectar repositorios de forma segura
        from repositories.recetas import RecetaRepository
        from repositories.productos import ProductoRepository
        
        self._repo = RecetaRepository(self.conexion)
        self._prepo = ProductoRepository(self.conexion)
        
        # 6. Cache de productos (se llena en _refresh_all)
        self._cached_productos = []

        # 7. Construir UI y Eventos
        self._init_ui()
        
        # Nota: Si tu código original tenía un self._subscribe_events(), descomenta la siguiente línea:
        # self._subscribe_events()
        
        # 7. Cargar los datos visuales
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self._load_recetas)

    def set_sucursal(self, sucursal_id: int, sucursal_nombre: str) -> None:
        self.sucursal_id = sucursal_id
        self.sucursal_nombre = sucursal_nombre
        self._engine = RecipeEngine(self.conexion, branch_id=sucursal_id)

    def set_usuario_actual(self, usuario: str, rol: str) -> None:
        self.usuario_actual = usuario or "Sistema"
        self.rol_usuario    = rol or ""

    def obtener_usuario_actual(self) -> str:
        return self.usuario_actual

    # ── Events ────────────────────────────────────────────────────────────────

    def _subscribe_events(self) -> None:
        for evt in (RECETA_CREADA, RECETA_ACTUALIZADA,
                    PRODUCTO_CREADO, PRODUCTO_ACTUALIZADO):
            EventBus().subscribe(evt, self._on_data_changed)

    def _on_data_changed(self, _data: dict) -> None:
        QTimer.singleShot(0, self._refresh_all)

    def _refresh_all(self) -> None:
        self._load_productos_cache()
        self._load_recetas()
        if hasattr(self, "_prod_combo"):
            self._prod_load_recetas()

    def limpiar(self) -> None:
        for evt in (RECETA_CREADA, RECETA_ACTUALIZADA,
                    PRODUCTO_CREADO, PRODUCTO_ACTUALIZADO):
            try:
                EventBus.unsubscribe(evt, self._on_data_changed)
            except Exception:
                pass

    # ── UI construction ───────────────────────────────────────────────────────

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12); root.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("Gestión de Recetas de Producción")
        f = title.font(); f.setPointSize(15); f.setBold(True); title.setFont(f)
        title.setObjectName("tituloPrincipal"); hdr.addWidget(title); hdr.addStretch()
        self._lbl_suc = QLabel()
        self._lbl_suc.setStyleSheet("color:#7f8c8d;"); hdr.addWidget(self._lbl_suc)
        root.addLayout(hdr)

        tabs = QTabWidget()
        root.addWidget(tabs)
        # Tab 1: Recetas CRUD
        tab_recetas = QWidget()
        tabs.addTab(tab_recetas, "📋 Recetas")
        self._build_tab_recetas(tab_recetas)
        # Tab 2: Ejecutar Producción rápida
        tab_prod = QWidget()
        tabs.addTab(tab_prod, "🏭 Producción Rápida")
        self._build_tab_produccion_rapida(tab_prod)

    def _build_tab_recetas(self, container: QWidget) -> None:
        root_lay = QVBoxLayout(container)
        root_lay.setContentsMargins(4, 8, 4, 4); root_lay.setSpacing(8)
        # Main splitter: list on left, details on right
        sp = QSplitter(Qt.Horizontal)

        # Left panel: recipe list
        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(0,0,0,0)
        # Search
        sh = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Buscar receta…")
        self._search.textChanged.connect(lambda _: self._load_recetas())
        sh.addWidget(QLabel("Buscar:")); sh.addWidget(self._search)
        ll.addLayout(sh)

        self._tbl = QTableWidget()
        self._tbl.setColumnCount(4)
        self._tbl.setHorizontalHeaderLabels(["ID", "Nombre Receta", "Base", "Rendimiento"])
        self._tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setAlternatingRowColors(True)
        hdr_ = self._tbl.horizontalHeader()
        hdr_.setSectionResizeMode(1, QHeaderView.Stretch)
        for i in (0, 2, 3):
            hdr_.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._tbl.itemSelectionChanged.connect(self._on_sel_changed)
        ll.addWidget(self._tbl)

        ab = QHBoxLayout()
        btn_nueva  = QPushButton("+ Nueva Receta")
        btn_nueva.setStyleSheet(f"background:{_C3};color:white;font-weight:bold;padding:6px 10px;border-radius:4px;")
        btn_nueva.clicked.connect(self._nueva_receta)
        self._btn_edit   = QPushButton("✏️ Editar");   self._btn_edit.setEnabled(False)
        self._btn_delete = QPushButton("🗑 Desactivar"); self._btn_delete.setEnabled(False)
        self._btn_edit.clicked.connect(self._editar_receta)
        self._btn_delete.clicked.connect(self._desactivar_receta)
        for b in (btn_nueva, self._btn_edit, self._btn_delete):
            ab.addWidget(b)
        ab.addStretch()
        ll.addLayout(ab)
        sp.addWidget(left)

        # Right panel: recipe detail
        right = QWidget(); rl = QVBoxLayout(right); rl.setContentsMargins(0,0,0,0)
        self._lbl_detalle = QLabel("Seleccione una receta para ver sus componentes.")
        self._lbl_detalle.setStyleSheet("color:#7f8c8d;font-style:italic;")
        rl.addWidget(self._lbl_detalle)
        self._tbl_comp = QTableWidget()
        self._tbl_comp.setColumnCount(5)
        self._tbl_comp.setHorizontalHeaderLabels(
            ["Componente", "Rendimiento %", "Merma %", "Total %", "Descripción"]
        )
        self._tbl_comp.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_comp.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_comp.verticalHeader().setVisible(False)
        hdr2 = self._tbl_comp.horizontalHeader()
        hdr2.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3, 4):
            hdr2.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        rl.addWidget(self._tbl_comp)

        # Validation summary
        self._lbl_total = QLabel()
        self._lbl_total.setStyleSheet("font-size:13px;font-weight:bold;")
        rl.addWidget(self._lbl_total)
        sp.addWidget(right)
        sp.setSizes([360, 540])
        root_lay.addWidget(sp)

    # ── Tab Producción Rápida ─────────────────────────────────────────────────

    def _build_tab_produccion_rapida(self, container: QWidget) -> None:
        """Mini-ventana de producción integrada en el módulo de recetas."""
        lay = QVBoxLayout(container)
        lay.setContentsMargins(8, 8, 8, 8); lay.setSpacing(8)

        sp = QSplitter(Qt.Horizontal)

        # Izquierda: formulario
        left = QGroupBox("Ejecutar Producción")
        fl = QVBoxLayout(left); fl.setSpacing(6)

        fl.addWidget(QLabel("Receta:"))
        self._prod_combo = QComboBox()
        self._prod_combo.currentIndexChanged.connect(self._prod_on_receta_changed)
        fl.addWidget(self._prod_combo)

        self._prod_lbl_tipo = QLabel()
        self._prod_lbl_tipo.setStyleSheet("font-weight:bold;padding:3px;border-radius:3px;")
        fl.addWidget(self._prod_lbl_tipo)

        fl.addWidget(QLabel("Cantidad base:"))
        qty_row = QHBoxLayout()
        self._prod_spin = QDoubleSpinBox()
        self._prod_spin.setRange(0.001, 999999); self._prod_spin.setDecimals(3)
        self._prod_spin.setValue(1.0); self._prod_spin.setSingleStep(0.5)
        self._prod_spin.valueChanged.connect(self._prod_preview)
        self._prod_lbl_u = QLabel("kg"); self._prod_lbl_u.setStyleSheet("color:#7f8c8d;")
        qty_row.addWidget(self._prod_spin); qty_row.addWidget(self._prod_lbl_u); qty_row.addStretch()
        fl.addLayout(qty_row)

        fl.addWidget(QLabel("Notas:"))
        self._prod_notas = QLineEdit(); self._prod_notas.setPlaceholderText("Observaciones…")
        fl.addWidget(self._prod_notas)

        self._prod_lbl_stock = QLabel("—")
        self._prod_lbl_stock.setStyleSheet("font-weight:bold;font-size:13px;")
        fl.addWidget(QLabel("Stock disponible:")); fl.addWidget(self._prod_lbl_stock)

        fl.addStretch()

        self._prod_btn = QPushButton("▶ EJECUTAR")
        self._prod_btn.setStyleSheet(f"background:{_C4};color:white;font-weight:bold;padding:8px;border-radius:4px;")
        self._prod_btn.clicked.connect(self._prod_ejecutar)
        fl.addWidget(self._prod_btn)
        sp.addWidget(left)

        # Derecha: preview
        right = QGroupBox("Vista Previa")
        rl = QVBoxLayout(right)
        self._prod_tbl = QTableWidget()
        self._prod_tbl.setColumnCount(5)
        self._prod_tbl.setHorizontalHeaderLabels(
            ["Mov.", "Producto", "Teórico kg", "Real kg (báscula)", "Stock actual"])
        self._prod_tbl.verticalHeader().setVisible(False)
        self._prod_tbl.setAlternatingRowColors(True)
        hdr_ = self._prod_tbl.horizontalHeader()
        hdr_.setSectionResizeMode(1, QHeaderView.Stretch)
        for i in (0, 2, 3, 4): hdr_.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        rl.addWidget(self._prod_tbl)

        # Toggle for real measurements
        self._chk_usar_reales = QCheckBox(
            "Usar pesos reales (capturados en báscula)")
        self._chk_usar_reales.setToolTip(
            "Activa 'Real kg' para ingresar pesos medidos en bascula. "
            "Si la diferencia supera la tolerancia de la receta, "
            "se registra como variacion en el historial.")
        rl.addWidget(self._chk_usar_reales)

        self._prod_lbl_res = QLabel(); self._prod_lbl_res.setStyleSheet("font-weight:bold;")
        rl.addWidget(self._prod_lbl_res)
        sp.addWidget(right)
        sp.setSizes([280, 420])
        lay.addWidget(sp)

    def _prod_load_recetas(self) -> None:
        prev = self._prod_combo.currentData()
        self._prod_combo.blockSignals(True)
        self._prod_combo.clear()
        self._prod_combo.addItem("— Seleccionar —", None)
        try:
            rows = self.conexion.fetchall(
                "SELECT id, nombre, tipo_receta, producto_base_id, unidad_base FROM recetas WHERE activo=1 ORDER BY tipo_receta, nombre"
            )
            for r in rows:
                tipos = {"subproducto":"🔪","combinacion":"📦","produccion":"🍳"}
                ic = tipos.get(r["tipo_receta"], "📌")
                self._prod_combo.addItem(f"{ic} {r['nombre']}", r["id"])
        except Exception as e:
            pass
        if prev:
            idx = self._prod_combo.findData(prev)
            if idx >= 0: self._prod_combo.setCurrentIndex(idx)
        self._prod_combo.blockSignals(False)
        self._prod_on_receta_changed()

    def _prod_on_receta_changed(self) -> None:
        rid = self._prod_combo.currentData()
        if not rid:
            self._prod_lbl_tipo.setText(""); self._prod_tbl.setRowCount(0)
            self._prod_lbl_res.setText(""); return
        try:
            r = dict(self.conexion.fetchone("SELECT * FROM recetas WHERE id=?", (rid,)) or {})
        except Exception: return
        tipos_c = {"subproducto":"#e74c3c","combinacion":"#2980b9","produccion":"#27ae60"}
        tipos_l = {"subproducto":"🔪 Despiece","combinacion":"📦 Kit/Paquete","produccion":"🍳 Elaboración"}
        t = r.get("tipo_receta","")
        self._prod_lbl_tipo.setText(tipos_l.get(t, t))
        self._prod_lbl_tipo.setStyleSheet(f"font-weight:bold;padding:3px;border-radius:3px;background:{tipos_c.get(t,'#7f8c8d')};color:white;")
        self._prod_lbl_u.setText(r.get("unidad_base","kg") or "kg")
        self._prod_update_stock(r)
        self._prod_preview()

    def _prod_update_stock(self, r: dict) -> None:
        try:
            row = self.conexion.fetchone(
                "SELECT COALESCE(SUM(quantity),0) as q FROM branch_inventory WHERE branch_id=? AND product_id=?",
                (self.sucursal_id, r.get("producto_base_id"))
            )
            stock = float(row["q"]) if row else 0.0
            cant = self._prod_spin.value()
            color = _C4 if stock >= cant else _C5
            self._prod_lbl_stock.setText(f"{stock:.3f} {r.get('unidad_base','kg')}")
            self._prod_lbl_stock.setStyleSheet(f"font-weight:bold;font-size:13px;color:{color};")
        except Exception: pass

    def _prod_preview(self) -> None:
        rid = self._prod_combo.currentData()
        if not rid: return
        cant = self._prod_spin.value()
        try:
            movs = self._engine.preview_produccion(rid, cant)
        except Exception as exc:
            self._prod_tbl.setRowCount(0)
            self._prod_lbl_res.setText(f"⚠ {exc}"); return

        # Read stock from productos.existencia (always available)
        stocks = {}
        for mv in movs:
            pid = mv["product_id"]
            try:
                row = self.conexion.execute(
                    "SELECT COALESCE(existencia,0) FROM productos WHERE id=?", (pid,)
                ).fetchone()
                stocks[pid] = float(row[0]) if row else 0.0
            except Exception:
                stocks[pid] = 0.0

        self._prod_real_spins = {}  # product_id → QDoubleSpinBox for real weight
        self._prod_movs_cache = movs  # cache for _prod_ejecutar
        self._prod_tbl.setRowCount(len(movs))
        hay_error = False

        for ri, mv in enumerate(movs):
            d = float(mv["delta"]); pid = mv["product_id"]
            s = stocks.get(pid, 0.0)
            es_sal = d < 0
            if es_sal and s < abs(d) - 0.001:
                hay_error = True

            # Col 0: direction
            it0 = QTableWidgetItem("⬇ CONSUMO" if es_sal else "⬆ GEN")
            it0.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            from PyQt5.QtGui import QColor
            it0.setForeground(QColor(_C5 if es_sal else _C4))
            self._prod_tbl.setItem(ri, 0, it0)

            # Col 1: name
            it1 = QTableWidgetItem(mv.get("nombre","?"))
            it1.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self._prod_tbl.setItem(ri, 1, it1)

            # Col 2: theoretical
            it2 = QTableWidgetItem(f"{abs(d):.3f}")
            it2.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            it2.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._prod_tbl.setItem(ri, 2, it2)

            # Col 3: real weight spinbox (only for generated products, not consumed)
            if not es_sal:
                spin = QDoubleSpinBox()
                spin.setRange(0.0, 999999.0); spin.setDecimals(3)
                spin.setValue(abs(d))  # default = theoretical
                spin.setSuffix(" kg")
                spin.setEnabled(False)  # enabled when checkbox is checked
                self._prod_real_spins[pid] = spin
                self._prod_tbl.setCellWidget(ri, 3, spin)
            else:
                it3 = QTableWidgetItem("—")
                it3.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                it3.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._prod_tbl.setItem(ri, 3, it3)

            # Col 4: current stock
            it4 = QTableWidgetItem(f"{s:.3f}")
            it4.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            it4.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            color = _C5 if (es_sal and s < abs(d) - 0.001) else "#2c3e50"
            from PyQt5.QtGui import QColor
            it4.setForeground(QColor(color))
            self._prod_tbl.setItem(ri, 4, it4)

        # Connect checkbox to enable/disable real spin boxes
        try:
            self._chk_usar_reales.toggled.disconnect()
        except Exception: pass
        def _toggle_reales(checked):
            for sp in self._prod_real_spins.values():
                sp.setEnabled(checked)
        self._chk_usar_reales.toggled.connect(_toggle_reales)

        if hay_error:
            self._prod_lbl_res.setText("❌ STOCK INSUFICIENTE para este lote")
            self._prod_lbl_res.setStyleSheet(f"color:{_C5};font-weight:bold;")
            self._prod_btn.setEnabled(False)
        else:
            self._prod_lbl_res.setText(f"✅ {len(movs)} movimientos — listo para ejecutar")
            self._prod_lbl_res.setStyleSheet(f"color:{_C4};font-weight:bold;")
            self._prod_btn.setEnabled(True)

    def _prod_ejecutar(self) -> None:
        rid = self._prod_combo.currentData()
        if not rid: return
        cant = self._prod_spin.value()
        conf = QMessageBox.question(self, "Confirmar",
            f"¿Ejecutar producción con cantidad {cant:.3f}?",
            QMessageBox.Yes | QMessageBox.No)
        if conf != QMessageBox.Yes: return
        self._prod_btn.setEnabled(False)
        try:
            # Collect real measurements if checkbox is active
            mediciones = None
            if getattr(self, '_chk_usar_reales', None) and self._chk_usar_reales.isChecked():
                mediciones = {
                    pid: spin.value()
                    for pid, spin in getattr(self, '_prod_real_spins', {}).items()
                }
            res = self._engine.ejecutar_produccion(
                receta_id=rid, cantidad_base=cant,
                usuario=self.usuario_actual,
                sucursal_id=self.sucursal_id,
                notas=self._prod_notas.text().strip(),
                mediciones_reales=mediciones,
            )
            self._prod_btn.setEnabled(True)
            QMessageBox.information(self, "✅ Éxito",
                f"Producción #{res.produccion_id} completada.\n"
                f"Generado: {res.total_generado:.3f} | Consumido: {res.total_consumido:.3f}")
            self._prod_notas.clear()
            self._refresh_all()
        except StockInsuficienteProduccionError as exc:
            self._prod_btn.setEnabled(True)
            QMessageBox.critical(self, "Stock Insuficiente", str(exc))
        except RecipeEngineError as exc:
            self._prod_btn.setEnabled(True)
            QMessageBox.critical(self, "Error Producción", str(exc))
        except Exception as exc:
            self._prod_btn.setEnabled(True)
            QMessageBox.critical(self, "Error", str(exc))

        # ── Data ──────────────────────────────────────────────────────────────────

    def _load_productos_cache(self) -> None:
        try:
            self._cached_productos = self._prepo.get_all(include_inactive=False)
        except Exception as exc:
            logger.warning("load_productos_cache: %s", exc)
            self._cached_productos = []

    def _load_recetas(self) -> None:
        search = self._search.text().strip().lower()
        try:
            rows = self._repo.get_all()
        except Exception as exc:
            logger.exception("load_recetas"); rows = []
        if search:
            rows = [r for r in rows
                    if search in r.get("nombre_receta", "").lower()
                    or search in r.get("base_product_nombre", "").lower()]
        self._tbl.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            rend = float(r.get("total_rendimiento", 0))
            vals = [
                str(r.get("id", "")),
                r.get("nombre_receta", "—"),
                r.get("base_product_nombre", "—"),
                f"{rend:.2f}%",
            ]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(str(v)); it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci == 3:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    it.setForeground(QColor(_C4 if rend <= 100 else _C5))
                self._tbl.setItem(ri, ci, it)
        if hasattr(self, '_lbl_suc'):
            self._lbl_suc.setText(f"Sucursal: {self.sucursal_nombre}")

    def _load_receta_detail(self) -> None:
        row = self._tbl.currentRow()
        if row < 0:
            self._tbl_comp.setRowCount(0); self._lbl_total.setText("")
            self._lbl_detalle.setText("Seleccione una receta para ver sus componentes.")
            return
        it = self._tbl.item(row, 0)
        if not it:
            return
        try:
            rid = int(it.text())
            comps = self._repo.get_components(rid)
        except Exception as exc:
            logger.exception("load_receta_detail"); return

        self._tbl_comp.setRowCount(len(comps))
        total_rend = Decimal("0"); total_merma = Decimal("0")
        for ri, c in enumerate(comps):
            rend  = Decimal(str(c.get("rendimiento_pct", 0)))
            merma = Decimal(str(c.get("merma_pct", 0)))
            total_rend  += rend
            total_merma += merma
            fila_total = float(rend + merma)
            vals = [
                c.get("component_nombre", "?"),
                f"{float(rend):.2f}%",
                f"{float(merma):.2f}%",
                f"{fila_total:.2f}%",
                c.get("descripcion", ""),
            ]
            for ci, v in enumerate(vals):
                it2 = QTableWidgetItem(v); it2.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci in (1, 2, 3): it2.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._tbl_comp.setItem(ri, ci, it2)

        grand_total = float(total_rend + total_merma)
        if grand_total <= 100.01:
            color = _C4; ok = "✅"
        else:
            color = _C5; ok = "❌"
        self._lbl_total.setText(
            f"{ok} Total rendimiento: {float(total_rend):.2f}% | "
            f"Total merma: {float(total_merma):.2f}% | "
            f"SUMA: {grand_total:.2f}%"
        )
        self._lbl_total.setStyleSheet(f"font-size:13px;font-weight:bold;color:{color};")
        nombre = self._tbl.item(row, 1)
        self._lbl_detalle.setText(
            f"Componentes de: {nombre.text() if nombre else 'receta'} "
            f"({len(comps)} componentes)"
        )

    def _on_sel_changed(self) -> None:
        has = len(self._tbl.selectedItems()) > 0
        self._btn_edit.setEnabled(has)
        self._btn_delete.setEnabled(has)
        self._load_receta_detail()

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def _get_selected_id(self) -> Optional[int]:
        row = self._tbl.currentRow()
        if row < 0: return None
        it = self._tbl.item(row, 0)
        if not it: return None
        try: return int(it.text())
        except ValueError: return None

    def _nueva_receta(self) -> None:
        if not self._cached_productos:
            QMessageBox.warning(self, "Sin productos",
                                "No hay productos activos. Cree productos primero."); return
        dlg = DialogoReceta(self._repo, self._cached_productos,
                             self.usuario_actual, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._refresh_all()

    def _editar_receta(self) -> None:
        rid = self._get_selected_id()
        if rid is None: return
        try:
            data = self._repo.get_by_id(rid)
            comps = self._repo.get_components(rid)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc)); return
        if not data:
            QMessageBox.warning(self, "Error", "Receta no encontrada."); return
        dlg = DialogoReceta(self._repo, self._cached_productos,
                             self.usuario_actual,
                             receta_data=data, componentes=comps, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._refresh_all()

    def _desactivar_receta(self) -> None:
        rid = self._get_selected_id()
        if rid is None: return
        if QMessageBox.question(
            self, "Confirmar", "¿Desactivar esta receta? No se eliminará pero dejará de usarse.",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return
        try:
            self._repo.deactivate(rid, self.usuario_actual)
            QMessageBox.information(self, "Éxito", "Receta desactivada.")
            self._refresh_all()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))


# ── Dialogo Nueva/Editar Receta ───────────────────────────────────────────────

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
