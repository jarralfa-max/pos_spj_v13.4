"""Alertas de Fidelidad: lo que espera aprobación o atención (LOY-29).

Cada alerta cuenta el mismo estado que muestra la lista de su pantalla
(`LoyaltyRecordsQueryService.alerts`); «Abrir» lleva a esa pantalla.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, StandardTable
from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.view_states import ViewState, create_state_widget
from frontend.desktop.components.pages import StandardPage
from frontend.desktop.themes.tokens import Spacing

_SEVERIDAD = {"danger": "Urgente", "warning": "Atención", "info": "Aviso"}


class FidelidadAlertsPage(StandardPage):
    def __init__(self, presenter, parent=None, *,
                 navigate: Callable[[str], None] | None = None) -> None:
        super().__init__(parent, title="Alertas", subtitle="Aprobaciones pendientes, fraude, vencimientos y fallas.")
        self.setObjectName("fidelidadAlertsPage")
        self.setAccessibleName("Alertas de Fidelidad")
        self._presenter = presenter
        self._navigate = navigate
        self._routes: dict[str, str] = {}
        self._loaded = False

        layout = self.content_layout
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)
        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._status.hide()
        layout.addWidget(self._status)

        self._stack = QStackedWidget(self)
        self.table = StandardTable([ColumnSpec("Prioridad", "status"), ColumnSpec("Área"),
                                    ColumnSpec("Aviso"), ColumnSpec("Cantidad", "numeric")], self)
        self.table.doubleClicked.connect(lambda *_: self._open())
        self._stack.addWidget(self.table)
        self._stack.addWidget(create_state_widget(ViewState.EMPTY, self, message="Nada pendiente."))
        layout.addWidget(self._stack, stretch=1)

        acciones = QHBoxLayout()
        actualizar = create_secondary_button(self, "Actualizar")
        actualizar.clicked.connect(self.reload)
        acciones.addWidget(actualizar)
        if navigate is not None:
            abrir = create_secondary_button(self, "Abrir")
            abrir.clicked.connect(self._open)
            acciones.addWidget(abrir)
        acciones.addStretch(1)
        layout.addLayout(acciones)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        try:
            alertas = self._presenter.alerts()
        except Exception as exc:  # visible, nunca silencioso
            self._status.setProperty("state", "ERROR")
            self._status.setText(f"No fue posible cargar las alertas: {exc}")
            self._status.show()
            return
        self._status.hide()
        ids = [f"{a.route_id}#{i}" for i, a in enumerate(alertas)]
        self._routes = {rid: a.route_id for rid, a in zip(ids, alertas)}
        self.table.load_rows([[_SEVERIDAD.get(a.severity, a.severity), a.area, a.message,
                               str(a.count)] for a in alertas], row_ids=ids)
        self._stack.setCurrentIndex(0 if alertas else 1)
        self._loaded = True

    def _open(self) -> None:
        row_id = self.table.selected_row_id()
        if row_id and self._navigate is not None:
            self._navigate(self._routes[row_id])


__all__ = ["FidelidadAlertsPage"]
