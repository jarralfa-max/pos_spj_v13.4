"""DeliverySettingsPage (PASS 6) — Configuración de Pedidos/Reparto.

QUÉ SE CONFIGURA AQUÍ, Y QUÉ NO
-------------------------------
Las zonas de entrega: la única configuración del área con datos y reglas reales.
`SetOrderDeliveryAddressUseCase` resuelve con ellas la zona y el costo de envío de
cada domicilio, y hasta ahora nadie podía crearlas.

No hay pantalla para lo demás porque no hay nada real detrás: los canales y las
modalidades son enums del dominio, las reglas de notificación son una política
estática (`DeliveryNotificationPolicy`), y la tolerancia de ajuste de peso no tiene
parámetro registrado (`CatchWeightAdjustmentPolicy` la recibe del llamador). La
página lo dice en vez de enseñar controles que no guardarían nada.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components import create_primary_button, create_secondary_button
from frontend.desktop.components.dialogs import ConfirmationDialog
from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.components.worklist_page import WorklistPage
from frontend.desktop.modules.orders_delivery.dialogs.delivery_zone_dialog import (
    DeliveryZoneDialog,
)

SCOPE_NOTE = (
    "Los canales, las modalidades de entrega y las reglas de notificación están "
    "definidos en el sistema y no se configuran desde aquí. La tolerancia de ajuste "
    "de peso tampoco tiene todavía un parámetro registrado."
)

ACTION_EDIT = "Editar"
ACTION_DEACTIVATE = "Desactivar"
ACTION_ACTIVATE = "Activar"


class DeliverySettingsPage(WorklistPage):
    searchable = False
    paginated = False
    status_filter: list[tuple] = []
    columns = [
        ColumnSpec("Zona"),
        ColumnSpec("Códigos postales"),
        ColumnSpec("Pedido mínimo", "numeric"),
        ColumnSpec("Costo de envío", "numeric"),
        ColumnSpec("Envío gratis desde", "numeric"),
        ColumnSpec("Tiempo estimado"),
        ColumnSpec("Distancia máxima"),
        ColumnSpec("Estado", "status"),
    ]

    def __init__(self, presenter, *, title: str, subtitle: str, empty_message: str,
                 parent=None) -> None:
        self.title = title
        self.subtitle = subtitle
        self.empty_message = empty_message
        super().__init__(presenter, parent)
        self.setAccessibleName(title)
        self.setAccessibleDescription(subtitle)

    # construcción --------------------------------------------------------------
    def _build_actions(self) -> None:
        self.new_zone_button = create_primary_button(self, "Nueva zona")
        self.new_zone_button.clicked.connect(self._new_zone)
        self.new_zone_button.setEnabled(self._presenter.can_manage())
        self.header.add_action(self.new_zone_button)

    def _build_extra(self) -> None:
        self.scope_note = QLabel(SCOPE_NOTE, self)
        self.scope_note.setWordWrap(True)
        self.scope_note.setProperty("role", "muted")
        self._layout.addWidget(self.scope_note)

    def _build_row_actions(self, row) -> None:
        self.edit_button = create_secondary_button(self, ACTION_EDIT)
        self.edit_button.clicked.connect(self._edit_zone)
        self.deactivate_button = create_secondary_button(self, ACTION_DEACTIVATE)
        self.deactivate_button.clicked.connect(lambda: self._set_active(False))
        self.activate_button = create_secondary_button(self, ACTION_ACTIVATE)
        self.activate_button.clicked.connect(lambda: self._set_active(True))
        for button in (self.edit_button, self.deactivate_button, self.activate_button):
            row.addWidget(button)

    def _allowed_actions(self):
        if not self._presenter.can_manage():
            return set()
        zona = self._presenter.zone(self._selected())
        if zona is None:
            return set()
        return {ACTION_EDIT, ACTION_DEACTIVATE} if zona.active else {ACTION_EDIT, ACTION_ACTIVATE}

    def _load(self) -> None:
        self.set_table(self._presenter.zones())

    # acciones ----------------------------------------------------------------------
    def _new_zone(self) -> None:
        dialog = DeliveryZoneDialog(self)
        if dialog.exec_():
            self._result(*self._presenter.create_zone(dialog.data()))

    def _edit_zone(self) -> None:
        zona = self._presenter.zone(self._selected())
        if zona is None:
            return
        dialog = DeliveryZoneDialog(self, zone=zona)
        if dialog.exec_():
            self._result(*self._presenter.update_zone(zona.id, dialog.data()))

    def _set_active(self, active: bool) -> None:
        zona = self._presenter.zone(self._selected())
        if zona is None:
            return
        if not active:
            confirmacion = ConfirmationDialog(
                self, title="Desactivar zona",
                message=(f"Los domicilios con códigos de «{zona.name}» dejarán de resolver "
                         "costo de envío hasta que otra zona los cubra."),
                confirm_text=ACTION_DEACTIVATE)
            if not confirmacion.exec_():
                return
        self._result(*self._presenter.set_zone_active(zona.id, active))

    def _result(self, ok: bool, message: str) -> None:
        self.notify(ok, message)
        if ok:
            self.reload()
