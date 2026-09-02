"""Dialogs for the "Integraciones" section (Definitions/Instances/
Credentials/Health/Webhooks) — SET-19 cutover. Built entirely on
`FormDialog`, same convention as every other dialog in this package.

There's no repeatable-row widget in this component library, so
`config`/`required_credential_names` are entered as comma-separated
text — same open-ended-list-as-text convention
`marketing_campaign_dialogs.py`/`print_route_dialogs.py` already
established, applied here to a different shape.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QCheckBox

from frontend.desktop.components import FormDialog, SearchableComboBox, StandardLineEdit, apply_tooltip

_CATEGORIES = (
    ("MESSAGING", "Mensajería"), ("PAYMENTS", "Pagos"), ("FISCAL", "Fiscal"),
    ("LOCATION", "Ubicación"), ("EMAIL", "Correo"), ("SMS", "SMS"), ("OTHER", "Otro"),
)

_SIGNATURE_SCHEMES = (
    ("NONE", "Sin firma"), ("HMAC_SHA256_HEADER", "HMAC-SHA256 (encabezado)"),
    ("MERCADOPAGO_TS_V1", "MercadoPago ts/v1"),
)


def _parse_csv(text: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in text.split(",") if item.strip())


class IntegrationDefinitionCreateDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nueva definición de integración")
        self.code = StandardLineEdit(self)
        self.code.setAccessibleName("Código de la definición")
        self.form.addRow("Código:", self.code)

        self.name = StandardLineEdit(self)
        self.name.setAccessibleName("Nombre de la definición")
        self.form.addRow("Nombre:", self.name)

        self.category = SearchableComboBox(self, placeholder="Selecciona una categoría…")
        self.category.set_options(_CATEGORIES)
        self.category.setAccessibleName("Categoría")
        self.form.addRow("Categoría:", self.category)

        self.required_credential_names = StandardLineEdit(self)
        self.required_credential_names.setAccessibleName("Credenciales requeridas")
        apply_tooltip(
            self.required_credential_names,
            "Nombres separados por coma, ej. «api_key, api_secret». Nunca el valor del secreto.")
        self.form.addRow("Credenciales requeridas:", self.required_credential_names)

        self.add_button_box(ok_text="Crear definición")

    def values(self) -> dict:
        return {
            "code": self.code.text().strip(), "name": self.name.text().strip(),
            "category": self.category.current_id(),
            "required_credential_names": _parse_csv(self.required_credential_names.text()),
        }


class IntegrationDefinitionEditDialog(FormDialog):
    """Edits name/required_credential_names — never `code` or
    `category` (identity fields), same boundary
    `DocumentTemplateEditDialog` draws around `document_type`."""

    def __init__(self, parent=None, *, name: str = "", required_credential_names: tuple = ()) -> None:
        super().__init__(parent, title="Editar definición de integración")
        self.name = StandardLineEdit(self)
        self.name.setText(name)
        self.name.setAccessibleName("Nombre de la definición")
        self.form.addRow("Nombre:", self.name)

        self.required_credential_names = StandardLineEdit(self)
        self.required_credential_names.setText(", ".join(required_credential_names))
        self.required_credential_names.setAccessibleName("Credenciales requeridas")
        self.form.addRow("Credenciales requeridas:", self.required_credential_names)

        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        return {
            "name": self.name.text().strip(),
            "required_credential_names": _parse_csv(self.required_credential_names.text()),
        }


class _ConfigField:
    def _build_config_field(self, initial: dict | None = None) -> None:
        self.config = StandardLineEdit(self)
        self.config.setAccessibleName("Configuración")
        apply_tooltip(
            self.config,
            "Ajustes no sensibles separados por coma, ej. «phone_id=123, region=mx». "
            "Nunca contraseñas/tokens/secretos — usa Credenciales para eso.")
        if initial:
            self.config.setText(", ".join(f"{k}={v}" for k, v in initial.items()))
        self.form.addRow("Configuración:", self.config)

    def _parsed_config(self) -> dict:
        config = {}
        for entry in _parse_csv(self.config.text()):
            key, sep, value = entry.partition("=")
            if sep and key.strip():
                config[key.strip()] = value.strip()
        return config


class IntegrationInstanceCreateDialog(FormDialog, _ConfigField):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nueva instancia de integración")
        self.name = StandardLineEdit(self)
        self.name.setAccessibleName("Nombre de la instancia")
        self.form.addRow("Nombre:", self.name)

        self._build_config_field()
        self.add_button_box(ok_text="Crear instancia")

    def values(self) -> dict:
        return {"name": self.name.text().strip(), "config": self._parsed_config()}


class IntegrationInstanceEditDialog(FormDialog, _ConfigField):
    def __init__(self, parent=None, *, name: str = "", config: dict | None = None) -> None:
        super().__init__(parent, title="Editar instancia de integración")
        self.name = StandardLineEdit(self)
        self.name.setText(name)
        self.name.setAccessibleName("Nombre de la instancia")
        self.form.addRow("Nombre:", self.name)

        self._build_config_field(config)
        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        return {"name": self.name.text().strip(), "config": self._parsed_config()}


class SetCredentialDialog(FormDialog):
    """`secret_value` is intentionally never pre-filled — this dialog
    only ever WRITES to `SecretStoreGateway` (`set_secret`), never reads
    a raw value back, matching that gateway's own "UI must not call
    get_secret()" rule."""

    def __init__(self, parent=None, *, credential_name: str = "", secret_name: str = "") -> None:
        super().__init__(parent, title="Configurar credencial")
        self.credential_name = StandardLineEdit(self)
        self.credential_name.setText(credential_name)
        self.credential_name.setReadOnly(bool(credential_name))
        self.credential_name.setAccessibleName("Nombre de la credencial")
        self.form.addRow("Credencial:", self.credential_name)

        self.secret_name = StandardLineEdit(self)
        self.secret_name.setText(secret_name or credential_name)
        self.secret_name.setAccessibleName("Referencia del secreto")
        apply_tooltip(self.secret_name, "El nombre bajo el cual se guarda en el almacén de secretos.")
        self.form.addRow("Referencia:", self.secret_name)

        self.secret_value = StandardLineEdit(self)
        self.secret_value.setAccessibleName("Valor del secreto")
        apply_tooltip(self.secret_value, "Déjalo en blanco para mantener el secreto ya guardado y solo actualizar la referencia.")
        self.form.addRow("Nuevo valor (opcional):", self.secret_value)

        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        return {
            "credential_name": self.credential_name.text().strip(),
            "secret_name": self.secret_name.text().strip(),
            "secret_value": self.secret_value.text().strip() or None,
        }


class WebhookEndpointCreateDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nuevo webhook")
        self.code = StandardLineEdit(self)
        self.code.setAccessibleName("Código del webhook")
        self.form.addRow("Código:", self.code)

        self.path = StandardLineEdit(self)
        self.path.setAccessibleName("Ruta del webhook")
        apply_tooltip(self.path, "Ej. «/webhooks/mercadopago». Debe iniciar con «/».")
        self.form.addRow("Ruta:", self.path)

        self.signature_scheme = SearchableComboBox(self, placeholder="Selecciona un esquema…")
        self.signature_scheme.set_options(_SIGNATURE_SCHEMES)
        self.signature_scheme.setAccessibleName("Esquema de firma")
        self.form.addRow("Firma:", self.signature_scheme)

        self.signing_secret_reference = StandardLineEdit(self)
        self.signing_secret_reference.setAccessibleName("Referencia del secreto de firma")
        apply_tooltip(
            self.signing_secret_reference,
            "Obligatorio si el esquema de firma no es «Sin firma». Nunca el valor del secreto.")
        self.form.addRow("Referencia de firma:", self.signing_secret_reference)

        self.add_button_box(ok_text="Crear webhook")

    def values(self) -> dict:
        return {
            "code": self.code.text().strip(), "path": self.path.text().strip(),
            "signature_scheme": self.signature_scheme.current_id(),
            "signing_secret_reference": self.signing_secret_reference.text().strip() or None,
        }


class RecordHealthCheckDialog(FormDialog):
    """Manual only — no live network probing. Same "pruebas" boundary
    SET-8/9/10 already established for hardware this repo can't safely
    call out to blind."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Registrar chequeo de salud")
        self.success = QCheckBox("Chequeo exitoso", self)
        self.success.setChecked(True)
        self.form.addRow("", self.success)

        self.message = StandardLineEdit(self)
        self.message.setAccessibleName("Mensaje del chequeo")
        self.form.addRow("Mensaje:", self.message)

        self.add_button_box(ok_text="Registrar")

    def values(self) -> dict:
        return {"success": self.success.isChecked(), "message": self.message.text().strip()}
