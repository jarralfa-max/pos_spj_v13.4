"""Andamiaje común de las páginas de Finanzas (sobre ``WorklistPage``).

Las páginas sólo pintan widgets, capturan datos y delegan al presenter. Sin
SQL, sin reglas de negocio, sin colores en línea.

Lo que agrega a ``WorklistPage``:
- acciones con permiso visual (§28): un botón sin permiso queda deshabilitado
  y su tooltip dice qué permiso falta; la decisión real la vuelve a tomar el
  servicio de comandos;
- exportación CSV auditada (§25) de lo que la tabla muestra;
- ``run(...)``: ejecuta un comando del presenter y pinta su resultado;
- a 1366×768 (§29): a lo más ``MAX_HEADER_BUTTONS`` acciones de encabezado y
  ``MAX_ROW_BUTTONS`` de renglón como botones; las demás van en «Más acciones».
"""

from __future__ import annotations

import csv
from datetime import date

from PyQt5.QtCore import QDate
from PyQt5.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QMenu

from backend.application.finance.permissions import FinancePermissions
from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.date_range_filter import DateRange, DateRangeFilter
from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.components.worklist_page import WorklistPage

P = FinancePermissions

MAX_HEADER_BUTTONS = 2
MAX_ROW_BUTTONS = 3


def compact_combo(combo, characters: int = 22) -> None:
    """Un selector no se ensancha con su opción más larga (1366×768)."""
    combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(characters)


class FinancePage(WorklistPage):
    title: str = ""
    subtitle: str = ""
    columns: list[ColumnSpec] = []
    searchable = False
    paginated = False
    #: Muestra «Exportar CSV» (con su permiso y bitácora de auditoría).
    exportable = True
    #: Acciones de encabezado: (texto, permiso, nombre del método, primaria).
    header_actions: list[tuple[str, str | None, str, bool]] = []
    #: Acciones sobre el renglón elegido: (texto, permiso, nombre del método).
    row_actions: list[tuple[str, str | None, str]] = []
    #: Agrega un filtro «Desde / Hasta» (mes en curso por omisión).
    period_filter = False

    def __init__(self, presenter, parent=None) -> None:
        self._row_permissions: dict[str, str | None] = {}
        self._row_menu_actions: list = []
        self._row_menu_button = None
        super().__init__(presenter, parent)
        if self.status_filter and hasattr(self, "_status"):
            compact_combo(self._status, 16)

    # ── acciones ─────────────────────────────────────────────────────────
    def _allowed(self, permission: str | None) -> bool:
        return permission is None or self._presenter.can(permission)

    def _guard(self, button, permission: str | None) -> None:
        if not self._allowed(permission):
            button.setEnabled(False)
            button.setToolTip(f"Requiere el permiso {permission}")

    def _menu_action(self, menu: QMenu, text: str, permission: str | None, handler):
        action = menu.addAction(text if self._allowed(permission)
                                else f"{text} (requiere {permission})")
        action.triggered.connect(lambda _=False: handler())
        action.setEnabled(self._allowed(permission))
        return action

    def _build_actions(self) -> None:
        actions = [(text, permission, getattr(self, method), primary)
                   for text, permission, method, primary in self.header_actions]
        if self.exportable and self.columns:
            actions.append(("Exportar CSV", P.EXPORT, self._export_csv, False))
        visible = actions if len(actions) <= MAX_HEADER_BUTTONS else             actions[:MAX_HEADER_BUTTONS - 1]
        for text, permission, handler, primary in visible:
            factory = create_primary_button if primary else create_secondary_button
            button = factory(self, text)
            button.clicked.connect(lambda _=False, h=handler: h())
            self._guard(button, permission)
            self.header.add_action(button)
        if len(actions) > len(visible):
            more = create_secondary_button(self, "Más acciones")
            menu = QMenu(more)
            for text, permission, handler, _ in actions[len(visible):]:
                self._menu_action(menu, text, permission, handler)
            more.setMenu(menu)
            self.header.add_action(more)
        filters = QHBoxLayout()
        if self.period_filter:
            self._period = DateRangeFilter(self)
            first, today = self._presenter.month_bounds()
            self._period.set_range(DateRange(QDate(first.year, first.month, first.day),
                                             QDate(today.year, today.month, today.day)))
            self._period.range_changed.connect(lambda *_: self._on_filter())
            filters.addWidget(self._period)
        self._build_filters(filters)
        if filters.count():
            filters.addStretch(1)
            self._layout.addLayout(filters)

    def _build_filters(self, row: QHBoxLayout) -> None:
        """Controles de filtro propios de la página (override)."""

    def period(self) -> tuple[date, date]:
        value = self._period.value()
        return (date(value.start.year(), value.start.month(), value.start.day()),
                date(value.end.year(), value.end.month(), value.end.day()))

    def _build_row_actions(self, row: QHBoxLayout) -> None:
        actions = list(self.row_actions)
        visible = actions if len(actions) <= MAX_ROW_BUTTONS else actions[:MAX_ROW_BUTTONS - 1]
        for text, permission, method in visible:
            button = create_secondary_button(self, text)
            button.clicked.connect(getattr(self, method))
            self._row_permissions[text] = permission
            if not self._allowed(permission):
                button.setToolTip(f"Requiere el permiso {permission}")
            row.addWidget(button)
        if len(actions) > len(visible):
            more = create_secondary_button(self, "Más acciones")
            menu = QMenu(more)
            for text, permission, method in actions[len(visible):]:
                self._row_permissions[text] = permission
                action = self._menu_action(menu, text, permission, getattr(self, method))
                self._row_menu_actions.append((text, action))
            more.setMenu(menu)
            self._row_menu_button = more
            row.addWidget(more)

    def _allowed_actions(self):
        return {text for text, permission in self._row_permissions.items()
                if self._allowed(permission)}

    def _selection_changed(self):
        super()._selection_changed()
        if self._row_menu_button is None:
            return
        selected = bool(self._selected())
        allowed = self._allowed_actions()
        enabled_any = False
        for text, action in self._row_menu_actions:
            action.setEnabled(selected and text in allowed)
            enabled_any = enabled_any or action.isEnabled()
        self._row_menu_button.setEnabled(enabled_any)

    def set_table(self, model) -> None:
        """Tablas de sólo lectura (balanzas, proyecciones) no traen ids ocultos."""
        if model.rows and not model.row_ids:
            model = type(model)(model.rows, [str(i) for i in range(len(model.rows))],
                                total=getattr(model, "total", None))
        super().set_table(model)

    def run(self, result: tuple[bool, str]) -> bool:
        ok, message = result
        self.notify(ok, message)
        return ok

    # ── paginación con total del servidor (F24) ──────────────────────────
    @property
    def offset(self) -> int:
        return self._page * self.page_size

    # ── exportación auditada (§25) ───────────────────────────────────────
    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exportar a CSV", f"{self.title}.csv",
                                              "CSV (*.csv)")
        if not path:
            return
        headers = [self._table.horizontalHeaderItem(c).text()
                   for c in range(self._table.columnCount())]
        rows = [[(self._table.item(r, c).text() if self._table.item(r, c) else "")
                 for c in range(self._table.columnCount())]
                for r in range(self._table.rowCount())]
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerows(rows)
        self.run(self._presenter.record_export(self.title, path, len(rows)))
