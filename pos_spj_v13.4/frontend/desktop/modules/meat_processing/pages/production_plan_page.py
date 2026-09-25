"""Plan de producción: un plan por sucursal y día.

Se arma con líneas manuales o sugeridas (reposición de Inventario, pronóstico
de BI), se genera, se envía a revisión, lo aprueba OTRO usuario y cada línea se
convierte en una orden de procesamiento que nace aprobada, lista para preparar.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QInputDialog, QLabel, QMessageBox

from frontend.desktop.components import (
    ColumnSpec,
    StandardTable,
    create_danger_button,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.date_input import DateInput
from frontend.desktop.components.pages import StandardPage

COLUMNS = [
    ColumnSpec("Producto"), ColumnSpec("Proceso"), ColumnSpec("Entrada / objetivo"),
    ColumnSpec("Planeado", "numeric"), ColumnSpec("Convertido", "numeric"),
    ColumnSpec("Órdenes"), ColumnSpec("Fuente"), ColumnSpec("Prioridad", "numeric"),
]

class ProductionPlanPage(StandardPage):
    def __init__(self, presenter, *, title: str, subtitle: str, parent=None) -> None:
        super().__init__(parent, title=title, subtitle=subtitle)
        self._presenter = presenter
        self.title = title
        self.setAccessibleName(title)
        self._plan_id: str | None = None

        self.day = DateInput(self.content)
        self.day.dateChanged.connect(lambda _d: self.refresh())
        self.add_content(self.day)
        self.summary = QLabel("", self.content)
        self.summary.setWordWrap(True)
        self.add_content(self.summary)

        self.buttons = {}
        for clave, texto, fabrica, accion in (
                ("create", "Crear plan del día", create_primary_button, self._on_create),
                ("add", "Agregar línea", create_secondary_button, self._on_add),
                ("suggest", "Sugerir…", create_secondary_button, self._on_suggest),
                ("remove", "Quitar línea", create_secondary_button, self._on_remove),
                ("generate", "Generar", create_secondary_button,
                 lambda: self._on_transition("generate")),
                ("submit", "Enviar a revisión", create_secondary_button,
                 lambda: self._on_transition("submit")),
                ("approve", "Aprobar", create_primary_button,
                 lambda: self._on_transition("approve")),
                ("convert", "Convertir en orden", create_primary_button, self._on_convert),
                ("cancel", "Cancelar plan", create_danger_button,
                 lambda: self._on_transition("cancel"))):
            boton = fabrica(text=texto)
            boton.clicked.connect(accion)
            self.add_action(boton)
            self.buttons[clave] = boton

        self.table = StandardTable(COLUMNS, self.content)
        self.add_content(self.table, 1)

    def ensure_loaded(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        modelo = self._presenter.plan(self.day.date_value())
        self._plan_id = modelo.plan_id
        self.summary.setText(modelo.summary)
        self.table.load_rows(modelo.rows, row_ids=modelo.row_ids)
        for clave, boton in self.buttons.items():
            habilitado = (clave in modelo.actions if clave != "suggest"
                          else "add" in modelo.actions)
            boton.setEnabled(habilitado)

    def _avisar(self, ok: bool, mensaje: str) -> None:
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Plan", mensaje)

    def _linea(self) -> str | None:
        linea = self.table.selected_row_id()
        if not linea:
            QMessageBox.information(self, "Plan", "Selecciona una línea del plan.")
        return linea

    def _on_create(self) -> None:
        ok, mensaje, _ = self._presenter.create_plan(self.day.date_value())
        self._avisar(ok, mensaje)
        self.refresh()

    def _add_line(self, prefill: dict | None = None) -> bool:
        from frontend.desktop.modules.meat_processing.dialogs_plan import AddPlanLineDialog

        dlg = AddPlanLineDialog(self, presenter=self._presenter, prefill=prefill)
        if dlg.exec_() != QDialog.Accepted:
            return False
        datos = dlg.values()
        if not datos["product_id"]:
            QMessageBox.warning(self, "Plan", "Selecciona el producto de la lista.")
            return False
        ok, mensaje, _ = self._presenter.add_line(self._plan_id, **datos)
        if not ok:
            QMessageBox.warning(self, "Plan", mensaje)
        return ok

    def _on_add(self) -> None:
        if self._add_line():
            self.refresh()

    def _on_suggest(self) -> None:
        from frontend.desktop.modules.meat_processing.dialogs_plan import PlanSuggestionsDialog

        fuentes = self._presenter.suggestion_sources()
        if not fuentes:
            QMessageBox.information(self, "Plan", "No hay fuentes de sugerencias.")
            return
        etiqueta, aceptado = QInputDialog.getItem(
            self, "Sugerir líneas", "Fuente:", [f[1] for f in fuentes], 0, False)
        if not aceptado:
            return
        clave = next(c for c, e in fuentes if e == etiqueta)
        sugerencias, nota = self._presenter.suggestions(clave)
        if not sugerencias:
            QMessageBox.information(self, "Plan", nota or "Sin sugerencias.")
            return
        dlg = PlanSuggestionsDialog(self, title=etiqueta, suggestions=sugerencias, note=nota)
        if dlg.exec_() != QDialog.Accepted:
            return
        for s in dlg.chosen():
            self._add_line({"product_id": s.product_id, "product_name": s.product_name,
                            "quantity": s.quantity, "source_type": s.source_type,
                            "source_reference_id": s.source_reference_id})
        self.refresh()

    def _on_remove(self) -> None:
        linea = self._linea()
        if linea:
            ok, mensaje, _ = self._presenter.remove_line(self._plan_id, linea)
            self._avisar(ok, mensaje)
            self.refresh()

    def _on_transition(self, accion: str) -> None:
        ok, mensaje, _ = self._presenter.transition(accion, self._plan_id)
        self._avisar(ok, mensaje)
        self.refresh()

    def _on_convert(self) -> None:
        linea = self._linea()
        if linea:
            ok, mensaje, _ = self._presenter.convert_line(self._plan_id, linea)
            self._avisar(ok, mensaje)
            self.refresh()
