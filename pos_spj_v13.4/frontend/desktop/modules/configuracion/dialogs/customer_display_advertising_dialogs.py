"""Dialogs for the "Pantalla del cliente" section's advertising cards
(Contenido/Campañas/Slots/Asignaciones) — SET-18 cutover. Built entirely
on `FormDialog`, same convention as every other dialog in this package.

The "Definir vigencia" checkbox gating the two `DateTimeInput`s mirrors
`company_branch_dialogs.py::_BranchHoursFields`'s exact pattern: a
campaign's `starts_at`/`ends_at` window is optional (both-or-neither),
same both-set-or-both-`None` shape `BranchProfile`'s operating hours
already established.
"""

from __future__ import annotations

from datetime import datetime

from PyQt5.QtWidgets import QCheckBox

from frontend.desktop.components import DateTimeInput, FormDialog, SearchableComboBox, StandardLineEdit

_CONTENT_TYPES = (("TEXT", "Texto"), ("IMAGE", "Imagen"), ("VIDEO", "Video"), ("HTML", "HTML"))
_MODES = (
    ("IDLE", "Inactiva"), ("CART", "Carrito"), ("PAYMENT_PENDING", "Pago pendiente"),
    ("THANK_YOU", "Agradecimiento"),
)


def _iso(value) -> str | None:
    return value.isoformat(timespec="seconds") if value is not None else None


class _ScheduleField:
    def _build_schedule_field(self) -> None:
        self.has_schedule = QCheckBox("Definir vigencia (opcional)", self)
        self.form.addRow("", self.has_schedule)

        self.starts_at = DateTimeInput(self, default_now=True)
        self.starts_at.setEnabled(False)
        self.form.addRow("Inicio:", self.starts_at)

        self.ends_at = DateTimeInput(self, default_now=True)
        self.ends_at.setEnabled(False)
        self.form.addRow("Fin:", self.ends_at)

        self.has_schedule.toggled.connect(self.starts_at.setEnabled)
        self.has_schedule.toggled.connect(self.ends_at.setEnabled)

    def _schedule_values(self) -> dict:
        if not self.has_schedule.isChecked():
            return {"starts_at": None, "ends_at": None}
        return {"starts_at": _iso(self.starts_at.datetime_value()), "ends_at": _iso(self.ends_at.datetime_value())}


class ContentCreateDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nuevo contenido")
        self.title_field = StandardLineEdit(self)
        self.title_field.setAccessibleName("Título del contenido")
        self.form.addRow("Título:", self.title_field)

        self.content_type = SearchableComboBox(self, placeholder="Selecciona un tipo…")
        self.content_type.set_options(_CONTENT_TYPES)
        self.content_type.setAccessibleName("Tipo de contenido")
        self.form.addRow("Tipo:", self.content_type)

        self.body = StandardLineEdit(self)
        self.body.setAccessibleName("Contenido")
        self.form.addRow("Contenido:", self.body)

        self.duration_seconds = StandardLineEdit(self)
        self.duration_seconds.setText("10")
        self.duration_seconds.setAccessibleName("Duración en segundos")
        self.form.addRow("Duración (s):", self.duration_seconds)

        self.add_button_box(ok_text="Crear contenido")

    def values(self) -> dict:
        try:
            duration = int(self.duration_seconds.text().strip() or "10")
        except ValueError:
            duration = 10
        return {
            "title": self.title_field.text().strip(), "content_type": self.content_type.current_id(),
            "body": self.body.text().strip(), "duration_seconds": duration,
        }


class ContentEditDialog(FormDialog):
    def __init__(self, parent=None, *, title: str = "", body: str = "", duration_seconds: int = 10) -> None:
        super().__init__(parent, title="Editar contenido")
        self.title_field = StandardLineEdit(self)
        self.title_field.setText(title)
        self.title_field.setAccessibleName("Título del contenido")
        self.form.addRow("Título:", self.title_field)

        self.body = StandardLineEdit(self)
        self.body.setText(body)
        self.body.setAccessibleName("Contenido")
        self.form.addRow("Contenido:", self.body)

        self.duration_seconds = StandardLineEdit(self)
        self.duration_seconds.setText(str(duration_seconds))
        self.duration_seconds.setAccessibleName("Duración en segundos")
        self.form.addRow("Duración (s):", self.duration_seconds)

        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        try:
            duration = int(self.duration_seconds.text().strip() or "10")
        except ValueError:
            duration = 10
        return {
            "title": self.title_field.text().strip(), "body": self.body.text().strip(),
            "duration_seconds": duration,
        }


class ContentCampaignCreateDialog(FormDialog, _ScheduleField):
    def __init__(self, parent=None, *, content_options=()) -> None:
        super().__init__(parent, title="Nueva campaña de contenido")
        self.name = StandardLineEdit(self)
        self.name.setAccessibleName("Nombre de la campaña")
        self.form.addRow("Nombre:", self.name)

        self.content = SearchableComboBox(self, placeholder="Selecciona un contenido…")
        self.content.set_options([(o.entity_id, o.title) for o in content_options])
        self.content.setAccessibleName("Contenido")
        self.form.addRow("Contenido:", self.content)

        self._build_schedule_field()
        self.add_button_box(ok_text="Crear campaña")

    def values(self) -> dict:
        return {
            "name": self.name.text().strip(), "content_id": self.content.current_id(),
            **self._schedule_values(),
        }


class ContentCampaignEditDialog(FormDialog, _ScheduleField):
    """Edits only the schedule window — `name`/`content_id` stay
    immutable after creation, same identity-vs-mutable boundary
    `MarketingCampaignEditDialog` already draws around `code`/`category`."""

    def __init__(self, parent=None, *, starts_at: str | None = None, ends_at: str | None = None) -> None:
        super().__init__(parent, title="Editar vigencia de campaña")
        self._build_schedule_field()
        self.has_schedule.setChecked(bool(starts_at or ends_at))
        if starts_at:
            self.starts_at.set_datetime_value(datetime.fromisoformat(starts_at))
        if ends_at:
            self.ends_at.set_datetime_value(datetime.fromisoformat(ends_at))
        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        return self._schedule_values()


class AdvertisingSlotCreateDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nuevo slot publicitario")
        self.code = StandardLineEdit(self)
        self.code.setAccessibleName("Código del slot")
        self.form.addRow("Código:", self.code)

        self.mode = SearchableComboBox(self, placeholder="Selecciona un modo…")
        self.mode.set_options(_MODES)
        self.mode.setAccessibleName("Modo de pantalla")
        self.form.addRow("Modo:", self.mode)

        self.display_order = StandardLineEdit(self)
        self.display_order.setText("0")
        self.display_order.setAccessibleName("Orden de despliegue")
        self.form.addRow("Orden:", self.display_order)

        self.add_button_box(ok_text="Crear slot")

    def values(self) -> dict:
        try:
            order = int(self.display_order.text().strip() or "0")
        except ValueError:
            order = 0
        return {"code": self.code.text().strip(), "mode": self.mode.current_id(), "display_order": order}


class AdvertisingSlotEditDialog(FormDialog):
    """Edits only `display_order` — `code`/`mode` stay immutable after
    creation, same identity boundary every other create/edit pair in
    this package draws."""

    def __init__(self, parent=None, *, display_order: int = 0) -> None:
        super().__init__(parent, title="Editar orden del slot")
        self.display_order = StandardLineEdit(self)
        self.display_order.setText(str(display_order))
        self.display_order.setAccessibleName("Orden de despliegue")
        self.form.addRow("Orden:", self.display_order)
        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        try:
            order = int(self.display_order.text().strip() or "0")
        except ValueError:
            order = 0
        return {"display_order": order}


class CampaignPlacementAssignDialog(FormDialog):
    def __init__(self, parent=None, *, campaign_options=(), slot_options=()) -> None:
        super().__init__(parent, title="Asignar campaña a slot")
        self.campaign = SearchableComboBox(self, placeholder="Selecciona una campaña…")
        self.campaign.set_options([(o.entity_id, o.name) for o in campaign_options])
        self.campaign.setAccessibleName("Campaña")
        self.form.addRow("Campaña:", self.campaign)

        self.slot = SearchableComboBox(self, placeholder="Selecciona un slot…")
        self.slot.set_options([(o.entity_id, f"{o.code} ({o.mode})") for o in slot_options])
        self.slot.setAccessibleName("Slot")
        self.form.addRow("Slot:", self.slot)

        self.add_button_box(ok_text="Asignar")

    def values(self) -> dict:
        return {"campaign_id": self.campaign.current_id(), "slot_id": self.slot.current_id()}
