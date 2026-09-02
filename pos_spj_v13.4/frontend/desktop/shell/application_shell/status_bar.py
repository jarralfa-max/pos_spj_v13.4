"""StatusBar — SHELL-11.

Bottom strip of `ApplicationWindow`: connectivity (`ApplicationContext.offline_status`,
plus whether the currently displayed route is running in `degraded_offline`
mode per SHELL-10's `NavigationResult`), and workstation/branch identity.
A real `QStatusBar` so it composes naturally with `ApplicationWindow`'s
`QMainWindow` base via `setStatusBar()`.
"""
from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QStatusBar

from frontend.desktop.components.status_badge import StatusBadge


class StatusBar(QStatusBar):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("applicationStatusBar")

        self._connectivity_badge = StatusBadge("En línea", status="success")
        self._workstation_label = QLabel("")
        self._workstation_label.setObjectName("statusBarWorkstation")

        self.addWidget(self._connectivity_badge)
        self.addPermanentWidget(self._workstation_label)

    def set_offline_status(self, offline_status: str, *, degraded: bool = False) -> None:
        # `degraded` only ever fires when offline_status == "OFFLINE" (see
        # DesktopRouter._check_offline, SHELL-10) — it's the more specific
        # signal ("this route works, just with reduced functionality") and
        # takes priority over the blanket "Sin conexión", which would
        # otherwise wrongly suggest the route is unusable.
        if degraded:
            text, status = "Conexión limitada", "warning"
        elif offline_status == "OFFLINE":
            text, status = "Sin conexión", "danger"
        else:
            text, status = "En línea", "success"
        self._connectivity_badge.setText(text)
        self._connectivity_badge.set_status(status)

    def set_workstation(self, workstation_id: str, branch_name: str) -> None:
        self._workstation_label.setText(f"{branch_name} · {workstation_id}")

    @property
    def connectivity_text(self) -> str:
        return self._connectivity_badge.text()

    @property
    def workstation_text(self) -> str:
        return self._workstation_label.text()
