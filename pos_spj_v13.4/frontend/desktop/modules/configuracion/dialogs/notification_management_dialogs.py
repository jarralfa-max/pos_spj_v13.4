"""Dialogs for the "Notificaciones" section (Accounts/Templates/
Channels/Routing) — SET-20 cutover. Built entirely on `FormDialog`, same
convention as every other dialog in this package.
"""

from __future__ import annotations

from frontend.desktop.components import FormDialog, SearchableComboBox, StandardLineEdit, apply_tooltip

_CHANNELS = (("WHATSAPP", "WhatsApp"), ("SMS", "SMS"), ("EMAIL", "Correo"), ("PUSH", "Push"))


def _parse_csv(text: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in text.split(",") if item.strip())


class NotificationAccountCreateDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nueva cuenta de notificación")
        self.channel = SearchableComboBox(self, placeholder="Selecciona un canal…")
        self.channel.set_options(_CHANNELS)
        self.channel.setAccessibleName("Canal")
        self.form.addRow("Canal:", self.channel)

        self.name = StandardLineEdit(self)
        self.name.setAccessibleName("Nombre de la cuenta")
        self.form.addRow("Nombre:", self.name)

        self.credential_reference = StandardLineEdit(self)
        self.credential_reference.setAccessibleName("Referencia de credencial")
        apply_tooltip(
            self.credential_reference,
            "Nombre en SecretStoreGateway, ej. «wa_access_token». Nunca el valor del secreto.")
        self.form.addRow("Referencia de credencial:", self.credential_reference)

        self.add_button_box(ok_text="Crear cuenta")

    def values(self) -> dict:
        return {
            "channel": self.channel.current_id(), "name": self.name.text().strip(),
            "credential_reference": self.credential_reference.text().strip() or None,
        }


class NotificationAccountEditDialog(FormDialog):
    """Edits name/credential_reference — never `channel` (identity),
    same boundary every other create/edit pair in this package draws."""

    def __init__(self, parent=None, *, name: str = "", credential_reference: str | None = "") -> None:
        super().__init__(parent, title="Editar cuenta de notificación")
        self.name = StandardLineEdit(self)
        self.name.setText(name)
        self.name.setAccessibleName("Nombre de la cuenta")
        self.form.addRow("Nombre:", self.name)

        self.credential_reference = StandardLineEdit(self)
        self.credential_reference.setText(credential_reference or "")
        self.credential_reference.setAccessibleName("Referencia de credencial")
        self.form.addRow("Referencia de credencial:", self.credential_reference)

        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        return {
            "name": self.name.text().strip(),
            "credential_reference": self.credential_reference.text().strip() or None,
        }


class NotificationTemplateCreateDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nueva plantilla de notificación")
        self.code = StandardLineEdit(self)
        self.code.setAccessibleName("Código de la plantilla")
        apply_tooltip(self.code, "Ej. «pedido_confirmado» — igual al nombre del template en Meta Business.")
        self.form.addRow("Código:", self.code)

        self.channel = SearchableComboBox(self, placeholder="Selecciona un canal…")
        self.channel.set_options(_CHANNELS)
        self.channel.setAccessibleName("Canal")
        self.form.addRow("Canal:", self.channel)

        self.language = StandardLineEdit(self)
        self.language.setText("es_MX")
        self.language.setAccessibleName("Idioma")
        self.form.addRow("Idioma:", self.language)

        self.parameter_names = StandardLineEdit(self)
        self.parameter_names.setAccessibleName("Parámetros")
        apply_tooltip(self.parameter_names, "Nombres separados por coma, ej. «folio, total».")
        self.form.addRow("Parámetros:", self.parameter_names)

        self.add_button_box(ok_text="Crear plantilla")

    def values(self) -> dict:
        return {
            "code": self.code.text().strip(), "channel": self.channel.current_id(),
            "language": self.language.text().strip(), "parameter_names": _parse_csv(self.parameter_names.text()),
        }


class NotificationTemplateEditDialog(FormDialog):
    """Edits only `parameter_names` — never `code`/`channel`/`language`
    (identity fields), same boundary every other create/edit pair in
    this package draws."""

    def __init__(self, parent=None, *, parameter_names: tuple = ()) -> None:
        super().__init__(parent, title="Editar parámetros de plantilla")
        self.parameter_names = StandardLineEdit(self)
        self.parameter_names.setText(", ".join(parameter_names))
        self.parameter_names.setAccessibleName("Parámetros")
        self.form.addRow("Parámetros:", self.parameter_names)
        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        return {"parameter_names": _parse_csv(self.parameter_names.text())}


class NotificationRouteCreateDialog(FormDialog):
    def __init__(self, parent=None, *, template_options=(), account_options=()) -> None:
        super().__init__(parent, title="Nueva ruta de notificación")
        self.event_code = StandardLineEdit(self)
        self.event_code.setAccessibleName("Código de evento")
        apply_tooltip(self.event_code, "Ej. «pedido_confirmado» — el nombre del evento del ERP.")
        self.form.addRow("Evento:", self.event_code)

        self.channel = SearchableComboBox(self, placeholder="Selecciona un canal…")
        self.channel.set_options(_CHANNELS)
        self.channel.setAccessibleName("Canal")
        self.form.addRow("Canal:", self.channel)

        self.template = SearchableComboBox(self, placeholder="Selecciona una plantilla…")
        self.template.set_options([(o.entity_id, f"{o.code} ({o.channel})") for o in template_options])
        self.template.setAccessibleName("Plantilla")
        self.form.addRow("Plantilla:", self.template)

        self.account = SearchableComboBox(self, placeholder="Selecciona una cuenta…")
        self.account.set_options([(o.entity_id, f"{o.name} ({o.channel})") for o in account_options])
        self.account.setAccessibleName("Cuenta")
        self.form.addRow("Cuenta:", self.account)

        self.add_button_box(ok_text="Crear ruta")

    def values(self) -> dict:
        return {
            "event_code": self.event_code.text().strip(), "channel": self.channel.current_id(),
            "template_id": self.template.current_id(), "account_id": self.account.current_id(),
        }
