"""Página genérica de un registro de Fidelidad (LOY-29).

Una sola clase para todas las listas del módulo: interpreta un `RecordPageSpec`
sobre el andamiaje canónico `WorklistPage` (búsqueda, filtro por estado,
paginación, estado vacío). Las acciones sin fila seleccionada van en la
cabecera; las que actúan sobre la fila, debajo de la tabla y sólo se habilitan
con una selección. Una acción para la que el usuario no tiene permiso NO se
muestra (y el caso de uso la rechazaría de todos modos).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from PyQt5.QtWidgets import QDialog, QHBoxLayout

from frontend.desktop.components.buttons import (
    create_danger_button,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.dialogs import ConfirmationDialog
from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.components.worklist_page import WorklistPage
from frontend.desktop.modules.fidelidad.records.action_dialog import ActionDialog
from frontend.desktop.modules.fidelidad.records.labels import label_for, options_for
from frontend.desktop.modules.fidelidad.records.specs import ActionSpec, RecordPageSpec

_TABLE_KIND = {"numeric": "numeric", "money": "numeric", "date": "date", "status": "status",
               "enum": "status"}


def format_value(value, kind: str, enum_cls=None) -> str:
    if value is None or value == "":
        return "—"
    if kind in ("status", "enum"):
        return label_for(enum_cls, value)
    if kind == "bool":
        return "Sí" if bool(int(value)) else "No"
    if kind == "date":
        texto = str(value).replace("T", " ")
        return texto[:16]
    if kind in ("numeric", "money"):
        try:
            numero = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return str(value)
        if kind == "money":
            return f"$ {numero:,.2f}"
        normalizado = numero.normalize()
        return f"{normalizado:f}" if normalizado == normalizado.to_integral() else str(normalizado)
    return str(value)


@dataclass
class _Dialogs:
    """Fábricas de diálogos modales. Las pruebas las sustituyen para no bloquear."""

    action = ActionDialog
    confirm = ConfirmationDialog


class LoyaltyRecordPage(WorklistPage):
    paginated = True

    def __init__(self, presenter, spec: RecordPageSpec, parent=None) -> None:
        self.spec = spec
        self.title = spec.title
        self.subtitle = spec.subtitle
        self.empty_message = spec.empty_message
        self.searchable = spec.searchable
        self.columns = [ColumnSpec(c.header, _TABLE_KIND.get(c.kind, "text"))
                        for c in spec.columns]
        self.status_filter = options_for(spec.status_enum) if spec.status_enum else []
        self.dialogs = _Dialogs()
        self._rows_by_id: dict[str, dict] = {}
        self._presenter_ref = presenter
        self._allowed = [a for a in spec.actions if presenter.can(a.permission)]
        super().__init__(presenter, parent)
        self.setObjectName(f"fidelidadRecordPage_{spec.key}")
        self.setAccessibleName(spec.title)
        self.setAccessibleDescription(spec.subtitle)

    # ── acciones ───────────────────────────────────────────────────────────
    def _build_actions(self) -> None:
        cabecera = [a for a in self._allowed if a.selection_param is None]
        if not cabecera:
            return
        fila = QHBoxLayout()
        for action in cabecera:
            fila.addWidget(self._button(action))
        fila.addStretch(1)
        self._layout.addLayout(fila)

    def _build_row_actions(self, row: QHBoxLayout) -> None:
        for action in self._allowed:
            if action.selection_param is not None:
                row.addWidget(self._button(action))

    def _button(self, action: ActionSpec):
        factory = {"primary": create_primary_button, "danger": create_danger_button}.get(
            action.variant, create_secondary_button)
        button = factory(self, action.label)
        button.setObjectName(f"fidelidadAction_{action.command}")
        button.clicked.connect(lambda _=False, a=action: self.run_action(a))
        return button

    def run_action(self, action: ActionSpec) -> None:
        kwargs = dict(action.fixed)
        if action.selection_param:
            row = self.selected_row()
            if row is None:
                self._notify(False, "Selecciona un registro primero.")
                return
            kwargs[action.selection_param] = row.get(action.selection_column)
            for parametro, columna in action.selection_extra.items():
                kwargs[parametro] = row.get(columna)
        if action.fields:
            dialog = self.dialogs.action(action, self._presenter, self)
            if dialog.exec_() != QDialog.Accepted:
                return
            valores = dialog.values()
            if valores is None:
                return
            kwargs.update(valores)
        elif action.confirm:
            dialog = self.dialogs.confirm(self, title=action.label, message=action.confirm)
            if dialog.exec_() != QDialog.Accepted:
                return
        result = self._presenter.run_command(action.command, **kwargs)
        ok = bool(getattr(result, "success", False))
        mensaje = (getattr(result, "message", "") or "") if not ok else (
            getattr(result, "message", "") or action.success)
        self._notify(ok, mensaje or ("Listo." if ok else "No se pudo completar la acción."))

    # ── datos ──────────────────────────────────────────────────────────────
    def _load(self) -> None:
        resultado = self._presenter.records(
            self.spec.record, query=self._search.query() if self.searchable else "",
            status=self._status_id(), page=self._page)
        filas = list(resultado.rows)
        self._rows_by_id = {str(f["id"]): f for f in filas}
        modelo = SimpleNamespace(
            rows=[[format_value(f.get(c.key), c.kind, c.enum or self.spec.status_enum
                                if c.kind == "status" else c.enum)
                   for c in self.spec.columns] for f in filas],
            row_ids=[str(f["id"]) for f in filas], total=resultado.total)
        self.page_size = getattr(resultado, "page_size", self.page_size)
        self.set_table(modelo)

    def selected_row(self) -> dict | None:
        row_id = self._selected()
        return self._rows_by_id.get(str(row_id)) if row_id else None


__all__ = ["LoyaltyRecordPage", "format_value"]
