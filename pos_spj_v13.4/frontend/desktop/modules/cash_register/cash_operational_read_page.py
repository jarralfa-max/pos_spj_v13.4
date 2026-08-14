"""Shared CASH-23 read-only operational pages for Caja."""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.components.tooltip import apply_tooltip
from frontend.desktop.components.view_states import ViewState, create_state_widget
from frontend.desktop.modules.cash_register.presentation import status_label, user_facing_error


class CashOperationalReadPage(QWidget):
    """Render a real backend-backed read model for secondary Caja sections."""

    def __init__(self, *, presenter, section_key: str, title: str,
                 subtitle: str, parent=None):
        super().__init__(parent)
        self._presenter = presenter
        self._section_key = section_key
        root = QVBoxLayout(self)

        refresh = create_secondary_button(
            self,
            "Actualizar",
            tooltip=f"Refresca {title} desde el backend canonico de Caja.",
        )
        refresh.clicked.connect(self.refresh)
        root.addWidget(PageHeader(
            self,
            title=title,
            subtitle=subtitle,
            actions=[refresh],
        ))
        self._kpis = KPIBar(self)
        root.addWidget(self._kpis)
        self._state_host = QVBoxLayout()
        root.addLayout(self._state_host)
        self._table = StandardTable([
            ColumnSpec("Principal"),
            ColumnSpec("Referencia"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Fecha", "date"),
        ], self)
        root.addWidget(self._table)
        self.setAccessibleName(title)
        self.setAccessibleDescription(subtitle)
        self.refresh()

    def refresh(self) -> None:
        self._clear_state()
        try:
            section = self._presenter.cash_operational_section(self._section_key)
        except Exception as exc:
            self._table.load_rows([])
            self._kpis.set_cards([KPIDTO("rows", "Registros", "0")])
            self._set_state(ViewState.ERROR, user_facing_error(exc))
            return

        rows = list(section.rows)
        self._kpis.set_cards([
            KPIDTO("rows", "Registros", str(len(rows))),
            KPIDTO("section", "Seccion", section.title),
        ])
        self._table.load_rows(
            [
                [row.primary, row.secondary, status_label(row.status), row.occurred_at]
                for row in rows
            ],
            row_ids=[row.id for row in rows],
        )
        if not rows:
            self._set_state(
                ViewState.EMPTY,
                "No hay registros para mostrar con los filtros y permisos actuales.",
            )

    def _set_state(self, state: ViewState, message: str) -> None:
        widget = create_state_widget(state, self, message=message)
        apply_tooltip(widget, message, help_id=f"cash_register.{self._section_key}.state")
        self._state_host.addWidget(widget)

    def _clear_state(self) -> None:
        while self._state_host.count():
            item = self._state_host.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
