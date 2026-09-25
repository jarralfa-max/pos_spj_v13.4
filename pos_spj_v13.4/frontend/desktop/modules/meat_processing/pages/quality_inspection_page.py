"""Calidad: lo producido que espera inspección, y la decisión del inspector.

Pestaña «Por inspeccionar»: liberar pasa lo retenido a disponible; bloquear,
mandar a reproceso o decomisar lo deja fuera de disponible y exige motivo.
Quien produjo no puede decidir (lo impide Calidad, no la pantalla).
Pestaña «Salidas»: el registro de salidas con su estado de calidad.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QInputDialog, QLabel, QMessageBox

from frontend.desktop.components import (
    ColumnSpec,
    StandardTable,
    create_danger_button,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.pages import StandardPage, TabbedPage

COLUMNS = [ColumnSpec("Producto"), ColumnSpec("Lote"), ColumnSpec("Retenido", "numeric"),
           ColumnSpec("Solicitada", "date"), ColumnSpec("Origen")]


class PendingInspectionsPage(StandardPage):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent, title="Por inspeccionar",
                         subtitle="Salidas retenidas hasta que Calidad decida.")
        self._presenter = presenter
        self.buttons = {}
        for decision, texto, fabrica in (
                ("RELEASED", "Liberar", create_primary_button),
                ("BLOCKED", "Bloquear", create_secondary_button),
                ("REWORK_REQUIRED", "Reproceso", create_secondary_button),
                ("CONDEMNED", "Decomisar", create_danger_button)):
            boton = fabrica(text=texto)
            boton.clicked.connect(lambda _=False, d=decision: self._on_decide(d))
            self.add_action(boton)
            self.buttons[decision] = boton
        self.empty = QLabel("No hay salidas por inspeccionar.", self.content)
        self.empty.setProperty("role", "muted")
        self.add_content(self.empty)
        self.table = StandardTable(COLUMNS, self.content)
        self.add_content(self.table, 1)

    def ensure_loaded(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        modelo = self._presenter.pending()
        self.table.load_rows(modelo.rows, row_ids=modelo.row_ids)
        self.empty.setVisible(not modelo.rows)

    def _on_decide(self, decision: str, *, reason: str | None = None) -> None:
        inspeccion = self.table.selected_row_id()
        if not inspeccion:
            QMessageBox.information(self, "Calidad", "Selecciona una salida de la lista.")
            return
        motivo = reason or ""
        if reason is None and self._presenter.needs_reason(decision):
            motivo, aceptado = QInputDialog.getText(self, "Calidad", "Motivo (obligatorio):")
            if not aceptado:
                return
        ok, mensaje = self._presenter.decide(inspeccion, decision, motivo)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Calidad", mensaje)
        self.refresh()


class QualityPage(TabbedPage):
    def __init__(self, pending: PendingInspectionsPage, outputs, *, title: str,
                 subtitle: str, parent=None) -> None:
        super().__init__(parent, title=title, subtitle=subtitle)
        self.title = title
        self.pending = pending
        self.outputs = outputs
        self.tabs.addTab(pending, "Por inspeccionar")
        self.tabs.addTab(outputs, "Salidas")
        self.setAccessibleName(title)
        self.setAccessibleDescription(subtitle)

    def ensure_loaded(self) -> None:
        self.pending.ensure_loaded()
        self.outputs.ensure_loaded()
