# modulos/dialogs/receta_dialog.py — FASE 3
"""
DialogoReceta — Editor de recetas de producción.

Extracted from modulos/produccion.py to keep UI layer lean.
Receives RecipeService (application layer) — never touches RecetaRepository directly.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Dict, List, Optional

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QLabel, QLineEdit, QComboBox,
    QDoubleSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox,
)
from PyQt5.QtCore import Qt

from modulos.ui_components import (
    create_primary_button, create_success_button, create_secondary_button,
)
from repositories.recetas import (
    RecetaError, RecetaCyclicError, RecetaSelfReferenceError,
    RecetaPercentageError, RecetaDuplicadaError,
)

logger = logging.getLogger("spj.ui.dialogs.receta")


class DialogoReceta(QDialog):
    """
    Modal dialog to create or edit a production recipe.

    Receives a RecipeService instance — all persistence delegated through it.
    """

    def __init__(
        self,
        service,                           # RecipeService
        productos: List[Dict],
        usuario: str,
        receta_data: Optional[Dict] = None,
        componentes: Optional[List[Dict]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._service    = service
        self._productos  = productos
        self._usuario    = usuario
        self._data       = receta_data
        self._componentes = componentes or []
        self._comp_rows: List[Dict] = []
        self.setWindowTitle("Nueva Receta" if not receta_data else "Editar Receta")
        self.setMinimumWidth(700)
        self.setMinimumHeight(550)
        self._build_ui()
        if receta_data:
            self._load()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)

        fl = QFormLayout()
        self._e_nombre = QLineEdit()
        self._e_nombre.setPlaceholderText("Nombre de la receta…")

        self._combo_base = QComboBox()
        self._combo_base.addItem("— Seleccionar producto base —", None)
        for p in self._productos:
            self._combo_base.addItem(
                f"{p['nombre']} [{p.get('unidad', 'kg')}]", p["id"]
            )

        self._combo_tipo_receta = QComboBox()
        self._combo_tipo_receta.addItem("SUBPRODUCTO — Para productos procesables", "SUBPRODUCTO")
        self._combo_tipo_receta.addItem("COMBINACION — Para productos compuestos",  "COMBINACION")
        self._combo_tipo_receta.addItem("PRODUCCION  — Para productos producidos",  "PRODUCCION")

        fl.addRow("Nombre Receta*:",  self._e_nombre)
        fl.addRow("Producto Base*:",  self._combo_base)
        fl.addRow("Tipo Receta*:",    self._combo_tipo_receta)
        lay.addLayout(fl)

        # Components group
        grp = QGroupBox("Componentes (SUBPRODUCTO usa %, COMBINACION/PRODUCCION usan cantidad)")
        gl = QVBoxLayout(grp)

        self._tbl_comp = QTableWidget()
        self._tbl_comp.setColumnCount(8)
        self._tbl_comp.setHorizontalHeaderLabels(
            ["Componente", "Cantidad", "Unidad", "Rendimiento %", "Merma %", "Total %", "Tolerancia %", "Descripción"]
        )
        self._tbl_comp.verticalHeader().setVisible(False)
        self._tbl_comp.setAlternatingRowColors(True)
        hdr = self._tbl_comp.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3, 4, 5, 6, 7):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        gl.addWidget(self._tbl_comp)

        # Add-component row
        add_row = QHBoxLayout()
        self._combo_comp = QComboBox()
        self._combo_comp.addItem("— Componente —", None)
        for p in self._productos:
            self._combo_comp.addItem(p["nombre"], p["id"])

        self._spin_rend = QDoubleSpinBox()
        self._spin_rend.setRange(0, 100); self._spin_rend.setDecimals(3); self._spin_rend.setSuffix(" %")

        self._spin_merma = QDoubleSpinBox()
        self._spin_merma.setRange(0, 100); self._spin_merma.setDecimals(3); self._spin_merma.setSuffix(" %")
        self._spin_cantidad = QDoubleSpinBox()
        self._spin_cantidad.setRange(0, 99999); self._spin_cantidad.setDecimals(3); self._spin_cantidad.setValue(1.0)
        self._e_unidad = QLineEdit("kg")

        self._spin_tolerancia = QDoubleSpinBox()
        self._spin_tolerancia.setRange(0.1, 20.0); self._spin_tolerancia.setDecimals(1)
        self._spin_tolerancia.setSuffix(" %"); self._spin_tolerancia.setValue(2.0)
        self._spin_tolerancia.setToolTip(
            "Error relativo permitido.\n"
            "Si la producción real difiere más de este % del teórico,\n"
            "se registra como variación en el historial."
        )

        self._e_desc = QLineEdit()
        self._e_desc.setPlaceholderText("Descripción (opcional)")

        btn_add = create_primary_button(self, "➕ Agregar", "Agregar componente a la receta")
        btn_add.clicked.connect(self._add_component)
        btn_del = create_secondary_button(self, "🗑 Quitar Sel.", "Quitar componente seleccionado")
        btn_del.clicked.connect(self._remove_component)

        for w, lbl in [
            (self._combo_comp, "Comp:"),
            (QLabel("Rend:"), None), (self._spin_rend, None),
            (QLabel("Merma:"), None), (self._spin_merma, None),
            (QLabel("Cant:"), None), (self._spin_cantidad, None),
            (QLabel("Und:"), None), (self._e_unidad, None),
            (QLabel("Toler:"), None), (self._spin_tolerancia, None),
            (self._e_desc, None),
            (btn_add, None), (btn_del, None),
        ]:
            if lbl is not None:
                add_row.addWidget(QLabel(lbl))
            add_row.addWidget(w)
        gl.addLayout(add_row)

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
        bl.addStretch(); bl.addWidget(btn_ok); bl.addWidget(btn_no)
        lay.addLayout(bl)

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        d = self._data
        self._e_nombre.setText(d.get("nombre_receta", ""))

        idx = self._combo_base.findData(d.get("base_product_id"))
        if idx >= 0:
            self._combo_base.setCurrentIndex(idx)

        tipo = (d.get("tipo_receta") or "SUBPRODUCTO").upper()
        idx_t = self._combo_tipo_receta.findData(tipo)
        if idx_t >= 0:
            self._combo_tipo_receta.setCurrentIndex(idx_t)

        self._comp_rows = []
        for c in self._componentes:
            self._comp_rows.append({
                "component_product_id": c.get("component_product_id"),
                "component_nombre":     c.get("component_nombre", "?"),
                "rendimiento_pct":      float(c.get("rendimiento_pct", 0)),
                "merma_pct":            float(c.get("merma_pct", 0)),
                "cantidad":             float(c.get("cantidad", 0)),
                "unidad":               c.get("unidad", "kg"),
                "component_role":       c.get("component_role", ""),
                "factor_costo":         float(c.get("factor_costo", 1.0)),
                "tolerancia_pct":       float(c.get("tolerancia_pct", 2.0)),
                "descripcion":          c.get("descripcion", ""),
                "orden":                c.get("orden", 0),
            })
        self._refresh_comp_table()

    # ── Component row management ──────────────────────────────────────────────

    def _add_component(self) -> None:
        comp_id = self._combo_comp.currentData()
        if not comp_id:
            QMessageBox.warning(self, "Validación", "Seleccione un componente.")
            return
        rend  = self._spin_rend.value()
        merma = self._spin_merma.value()
        cantidad = self._spin_cantidad.value()
        tipo = self._combo_tipo_receta.currentData() or "SUBPRODUCTO"
        if tipo == "SUBPRODUCTO":
            if rend + merma <= 0:
                QMessageBox.warning(self, "Validación", "Rendimiento + Merma debe ser mayor a 0%.")
                return
        else:
            if cantidad <= 0:
                QMessageBox.warning(self, "Validación", "La cantidad del componente debe ser positiva.")
                return
        base_id = self._combo_base.currentData()
        if comp_id == base_id:
            QMessageBox.warning(self, "Auto-referencia",
                                "Un componente no puede ser el mismo producto base.")
            return
        if any(r["component_product_id"] == comp_id for r in self._comp_rows):
            QMessageBox.warning(self, "Duplicado",
                                "Este componente ya está en la receta.")
            return
        self._comp_rows.append({
            "component_product_id": comp_id,
            "component_nombre":     self._combo_comp.currentText(),
            "rendimiento_pct":      rend,
            "merma_pct":            merma,
            "cantidad":             cantidad,
            "unidad":               self._e_unidad.text().strip() or "kg",
            "component_role":       "",
            "factor_costo":         1.0,
            "tolerancia_pct":       self._spin_tolerancia.value(),
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
            fila_total  = float(rend + merma)
            tolerancia  = float(r.get("tolerancia_pct", 2.0))
            vals = [
                r.get("component_nombre", "?"),
                f"{float(r.get('cantidad', 0)):.3f}",
                r.get("unidad", "kg"),
                f"{float(rend):.3f}%",
                f"{float(merma):.3f}%",
                f"{fila_total:.3f}%",
                f"± {tolerancia:.1f}%",
                r.get("descripcion", ""),
            ]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci in (1, 3, 4, 5, 6):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._tbl_comp.setItem(ri, ci, it)

        grand = float(total_rend + total_merma)
        ok    = abs(grand - 100.0) <= 0.01
        icon  = "✅" if ok else "❌ DEBE SER 100%"
        self._lbl_totales.setText(
            f"{icon}  Rendimiento total: {float(total_rend):.3f}%  |  "
            f"Merma total: {float(total_merma):.3f}%  |  "
            f"Suma: {grand:.3f}%"
        )
        self._lbl_totales.setObjectName("textSuccess" if ok else "textDanger")
        self._lbl_totales.style().unpolish(self._lbl_totales)
        self._lbl_totales.style().polish(self._lbl_totales)

    # ── Save ──────────────────────────────────────────────────────────────────

    def _guardar(self) -> None:
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

        tipo_receta = self._combo_tipo_receta.currentData() or "SUBPRODUCTO"
        if tipo_receta == "SUBPRODUCTO":
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
                "cantidad":             c.get("cantidad", 0),
                "unidad":               c.get("unidad", "kg"),
                "component_role":       c.get("component_role", ""),
                "factor_costo":         c.get("factor_costo", 1.0),
                "descripcion":          c.get("descripcion", ""),
                "orden":                c.get("orden", i),
            }
            for i, c in enumerate(self._comp_rows)
        ]

        # UI-level duplicate check: offer edit of existing recipe
        if not self._data:
            existente = self._service.get_recipe_for_product(base_id)
            if existente:
                resp = QMessageBox.question(
                    self, "Receta ya existe",
                    f"El producto ya tiene la receta activa "
                    f"«{existente.get('nombre_receta', '#' + str(existente['id']))}».\n\n"
                    "¿Desea abrir esa receta para editarla?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if resp == QMessageBox.Yes:
                    self._data = existente
                    self._e_nombre.setText(existente.get("nombre_receta", ""))
                else:
                    return

        try:
            if self._data:
                self._service.update_recipe(self._data["id"], nombre, components, self._usuario)
                QMessageBox.information(self, "Éxito", "Receta actualizada correctamente.")
            else:
                rid = self._service.create_recipe(
                    nombre=nombre,
                    base_product_id=base_id,
                    components=components,
                    usuario=self._usuario,
                    tipo_receta=tipo_receta,
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
            QMessageBox.warning(self, "Validación de receta", self._to_business_recipe_error(exc))
        except RecetaDuplicadaError:
            QMessageBox.warning(self, "Receta Duplicada",
                                "Ya existe una receta activa para este producto base.\n"
                                "Cierre este diálogo y use el botón «Editar» sobre la receta existente.")
        except RecetaError as exc:
            QMessageBox.warning(self, "Error en receta", self._to_business_recipe_error(exc))
        except Exception as exc:
            logger.exception("guardar_receta")
            QMessageBox.critical(
                self, "Error inesperado",
                "No se pudo guardar la receta en este momento. Intente nuevamente."
            )
    @staticmethod
    def _to_business_recipe_error(exc: Exception) -> str:
        raw = str(exc or "").upper()
        if "TIPO_RECETA" in raw and "COMPUESTO" in raw:
            return "Este producto debe ser COMPUESTO para tener receta de combinación."
        if "TIPO_RECETA" in raw and "PROCESABLE" in raw:
            return "Este producto debe ser PROCESABLE para tener receta de despiece."
        if "TIPO_RECETA" in raw and "PRODUCIDO" in raw:
            return "Este producto debe ser PRODUCIDO para tener receta de producción."
        if "COMPONENT_PRODUCT_ID" in raw or "COMPONENT_NOT_FOUND" in raw:
            return "Falta seleccionar un componente válido para la receta."
        if "CANTIDAD_DEBE_SER_POSITIVA" in raw:
            return "La cantidad del componente debe ser mayor a cero."
        if "TOTAL_RENDIMIENTO_MUST_BE_100" in raw:
            return "En recetas de despiece, rendimiento + merma debe sumar 100%."
        if "TOTAL_RENDIMIENTO_EXCEEDS_100" in raw or "COMPONENT_EXCEEDS_100" in raw:
            return "Los porcentajes de rendimiento y merma no pueden superar 100%."
        return "No se pudo guardar la receta. Revise los datos ingresados."
