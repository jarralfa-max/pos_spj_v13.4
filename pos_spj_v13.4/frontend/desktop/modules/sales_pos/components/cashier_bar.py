"""CashierBar (POS-19) — top bar of the Sales/POS screen.

Structurally mirrors the legacy `modulos/ventas.py::init_ui` cashier bar
(`docs/refactor/sales_pos_layout_inventory.md` §1: title, status badge,
hardware buttons, corte-Z shortcut) but every value comes from the real
presenter (SALES-9's `count_suspended`, SALES-12's `device_health`) instead
of the legacy widget's static/never-rebound labels (a real, documented gap
in the current screen — see `docs/refactor/sales_pos_visual_contract.md`
§4.1/§4.3: the "● Abierto" badge and the repurposed "Terminal" button are
set once at init and never reflect live state). This component does NOT
inherit that gap.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel

from frontend.desktop.components import StatusBadge, create_secondary_button
from frontend.desktop.themes.tokens import Spacing


class CashierBar(QFrame):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("posCashierBar")
        self._presenter = presenter

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.XS, Spacing.MD, Spacing.XS)
        layout.setSpacing(Spacing.SM)

        title = QLabel("🛒 Punto de Venta", self)
        title.setObjectName("posCashierTitle")
        layout.addWidget(title)

        self._suspended_badge = StatusBadge("Suspendidas: 0", self, status="neutral")
        layout.addWidget(self._suspended_badge)

        layout.addStretch(1)

        self._device_badge = StatusBadge("Dispositivos", self, status="neutral")
        layout.addWidget(self._device_badge)

        self._btn_diagnostics = create_secondary_button(self, "⚙ Diagnóstico")
        self._btn_diagnostics.clicked.connect(self.refresh_device_health)
        layout.addWidget(self._btn_diagnostics)

    def refresh_suspended_count(self) -> None:
        count = self._presenter.count_suspended()
        self._suspended_badge.setText(f"Suspendidas: {count}")
        self._suspended_badge.set_status("warning" if count > 0 else "neutral")

    def refresh_device_health(self) -> None:
        devices = self._presenter.device_health()
        if not devices:
            self._device_badge.setText("Dispositivos: N/D")
            self._device_badge.set_status("neutral")
            return
        configured = sum(1 for d in devices if d.configured)
        total = len(devices)
        self._device_badge.setText(f"Dispositivos: {configured}/{total}")
        self._device_badge.set_status("success" if configured == total else "warning")
