"""AlertExplorerPage (§14/§46-50, BI-28) — "Alertas": "Evaluar alertas"
action lists whatever real `AnalyticalAlert`s `AlertExplorerPresenter`
produces from today's actual dashboard KPIs (often none — a real, honest
empty result, not a placeholder), plus lifecycle action buttons that apply
BI-20's real transition functions to the selected alert (session-only — no
persistence exists for `AnalyticalAlert` yet, see the presenter's own
docstring).
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    KPIBar,
    PageHeader,
    StandardLineEdit,
    StandardTable,
    create_danger_button,
    create_ghost_button,
    create_primary_button,
    create_success_button,
)
from frontend.desktop.modules.business_intelligence.presenters.alert_explorer_presenter import (
    AlertTransitionError,
    map_alert_kpis,
)


class AlertExplorerPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Inteligencia de Negocios — Alertas")
        self.setAccessibleDescription("Alertas activas contra los indicadores del negocio.")
        self._presenter = presenter
        self._loaded = False
        self._alerts_by_id: dict = {}

        root = QVBoxLayout(self)
        root.addWidget(PageHeader(
            title="Alertas", subtitle="Alertas activas contra los indicadores del negocio.",
            parent=self))

        actions = QHBoxLayout()
        actions.addStretch(1)
        evaluate = create_primary_button(self, "Evaluar alertas")
        evaluate.clicked.connect(self.refresh)
        actions.addWidget(evaluate)
        root.addLayout(actions)

        self.table = StandardTable(
            [ColumnSpec("Tipo"), ColumnSpec("Severidad"), ColumnSpec("Estado"),
             ColumnSpec("Mensaje")], self)
        self.table.itemSelectionChanged.connect(self._select_alert)
        root.addWidget(self.table)

        self.kpis = KPIBar(cards=[])
        root.addWidget(self.kpis)

        self.reason = StandardLineEdit(self, placeholder="Motivo (requerido para resolver/descartar)")
        root.addWidget(self.reason)

        lifecycle = QHBoxLayout()
        self.btn_acknowledge = create_ghost_button(self, "Reconocer")
        self.btn_start_progress = create_ghost_button(self, "Iniciar progreso")
        self.btn_resolve = create_success_button(self, "Resolver")
        self.btn_dismiss = create_danger_button(self, "Descartar")
        for button, action in (
            (self.btn_acknowledge, "acknowledge"), (self.btn_start_progress, "start_progress"),
            (self.btn_resolve, "resolve"), (self.btn_dismiss, "dismiss"),
        ):
            button.clicked.connect(lambda _checked=False, a=action: self._apply_transition(a))
            lifecycle.addWidget(button)
        root.addLayout(lifecycle)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self._loaded = True

    def refresh(self) -> None:
        try:
            alerts = self._presenter.evaluate_all()
        except Exception as exc:  # noqa: BLE001 - surface, never crash the page
            QMessageBox.warning(self, "Alertas", str(exc))
            return
        self._alerts_by_id = {alert.id: alert for alert in alerts}
        self._render_table()
        self.kpis.set_cards([])

    def _render_table(self) -> None:
        alerts = list(self._alerts_by_id.values())
        self.table.load_rows(
            [[a.alert_type.value, a.severity.value, a.status.value, a.message] for a in alerts],
            row_ids=[a.id for a in alerts])

    def _select_alert(self) -> None:
        alert_id = self.table.selected_row_id()
        alert = self._alerts_by_id.get(alert_id) if alert_id else None
        self.kpis.set_cards(map_alert_kpis(alert) if alert is not None else [])

    def _apply_transition(self, action: str) -> None:
        alert_id = self.table.selected_row_id()
        alert = self._alerts_by_id.get(alert_id) if alert_id else None
        if alert is None:
            QMessageBox.information(self, "Alertas", "Selecciona una alerta primero.")
            return
        try:
            updated = self._presenter.apply_transition(alert, action, reason=self.reason.value())
        except AlertTransitionError as exc:
            QMessageBox.warning(self, "Alertas", str(exc))
            return
        self._alerts_by_id[updated.id] = updated
        self._render_table()
        self.kpis.set_cards(map_alert_kpis(updated))
