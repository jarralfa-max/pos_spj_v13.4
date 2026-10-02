"""CashierBar — la barra superior del POS (contrato visual §1):

    Punto de Venta · Cajero · Sucursal · Caja · Suspendidas
                         ··· Báscula · Impresora · Terminal · Diagnóstico ·
                             Pantalla del cliente · Corte Z

Re-auditoría POS (2026-10-01), medido con captura sobre la base real: la barra
sólo decía "Punto de Venta", "Suspendidas" y un "Dispositivos" genérico — no
había cajero, sucursal, estado de caja, indicadores por dispositivo ni acceso a
Corte Z, todo exigido por el contrato. Cada valor viene del presentador (sesión,
turno de caja, `DeviceHealthQueryService`); la barra no prueba hardware (§51).
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel

from frontend.desktop.components import (
    IconProvider,
    Icons,
    StatusBadge,
    apply_tooltip,
    create_secondary_button,
)
from frontend.desktop.themes.tokens import Spacing

#: Indicadores de dispositivo visibles en la barra, en orden (§51).
BAR_DEVICES = (("scale", "Báscula"), ("printer", "Impresora"), ("payment_terminal", "Terminal"))


class CashierBar(QFrame):
    customer_display_toggled = pyqtSignal(bool)
    z_cut_requested = pyqtSignal()

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("posCashierBar")
        self._presenter = presenter

        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.XS, Spacing.MD, Spacing.XS)
        layout.setSpacing(Spacing.SM)

        title = QLabel("Punto de Venta", self)
        title.setAccessibleName("Punto de Venta")
        title.setObjectName("posCashierTitle")
        title.setProperty("role", "sectionTitle")
        layout.addWidget(title)

        self._cashier = QLabel("", self)
        self._cashier.setObjectName("posCashierName")
        layout.addWidget(self._cashier)

        self._branch = QLabel("", self)
        self._branch.setObjectName("posBranchName")
        self._branch.setProperty("role", "muted")
        layout.addWidget(self._branch)

        self._shift_badge = StatusBadge("Caja: —", self, status="neutral")
        layout.addWidget(self._shift_badge)

        self._suspended_badge = StatusBadge("Suspendidas: 0", self, status="neutral")
        self._suspended_badge.setVisible(False)
        layout.addWidget(self._suspended_badge)

        layout.addStretch(1)

        self._device_badges: dict[str, StatusBadge] = {}
        for kind, label in BAR_DEVICES:
            badge = StatusBadge(f"{label}: —", self, status="neutral")
            layout.addWidget(badge)
            self._device_badges[kind] = badge

        self._btn_diagnostics = create_secondary_button(
            self, "", tooltip="Diagnóstico: volver a leer el estado de los dispositivos")
        self._btn_diagnostics.setAccessibleName("Diagnóstico de dispositivos")
        IconProvider.bind(self._btn_diagnostics, Icons.DEVICE)
        self._btn_diagnostics.clicked.connect(self.refresh_device_health)
        layout.addWidget(self._btn_diagnostics)

        self._btn_customer_display = create_secondary_button(
            self, "Pantalla", tooltip="Abrir o cerrar la pantalla del cliente")
        IconProvider.bind(self._btn_customer_display, Icons.DISPLAY)
        self._btn_customer_display.setCheckable(True)
        self._btn_customer_display.toggled.connect(self.customer_display_toggled.emit)
        layout.addWidget(self._btn_customer_display)

        self._btn_z_cut = create_secondary_button(
            self, "Corte Z", tooltip="Ir a Caja para hacer el corte de tu turno")
        self._btn_z_cut.setObjectName("posZCut")
        IconProvider.bind(self._btn_z_cut, Icons.CASH)
        self._btn_z_cut.clicked.connect(self.z_cut_requested)
        layout.addWidget(self._btn_z_cut)

        self.refresh_identity()

    def refresh_identity(self) -> None:
        cajero = self._presenter.cashier_name()
        self._cashier.setText(cajero)
        apply_tooltip(self._cashier, f"Cajero: {cajero}" if cajero else "Sin cajero")
        sucursal = self._presenter.branch_name()
        self._branch.setText(sucursal)
        apply_tooltip(self._branch, f"Sucursal: {sucursal}" if sucursal else "Sin sucursal")

    def refresh_shift_status(self) -> None:
        problema = self._presenter.open_shift_problem()
        if problema:
            self._shift_badge.setText("Caja: cerrada")
            self._shift_badge.set_status("danger")
            apply_tooltip(self._shift_badge, problema)
        else:
            self._shift_badge.setText("Caja: abierta")
            self._shift_badge.set_status("success")
            apply_tooltip(self._shift_badge, "Tu turno de caja está abierto.")

    def refresh_suspended_count(self) -> None:
        count = self._presenter.count_suspended()
        self._suspended_badge.setText(f"Suspendidas: {count}")
        self._suspended_badge.set_status("warning" if count > 0 else "neutral")
        # El contador vive también en "Reanudar (n)"; aquí sólo cuando hay.
        self._suspended_badge.setVisible(count > 0)

    def refresh_device_health(self) -> None:
        devices = {d.device_type: d for d in self._presenter.device_health()}
        for kind, label in BAR_DEVICES:
            badge = self._device_badges[kind]
            device = devices.get(kind)
            if device is None:
                badge.setText(f"{label}: N/D")
                badge.set_status("neutral")
                apply_tooltip(badge, "Sin permiso de diagnóstico o sin registro de dispositivos.")
                continue
            badge.setText(f"{label}: {'lista' if device.configured else 'falta'}")
            badge.set_status("success" if device.configured else "warning")
            apply_tooltip(badge, device.detail)
