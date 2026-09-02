"""Dialogs for the "Empresa y sucursales" section — 5th real CRUD wired
for Configuración (SET-5 follow-up). Built entirely on `FormDialog`
(FASE DS-3), never a raw `QDialog`.
"""

from __future__ import annotations

from datetime import time as time_type

from PyQt5.QtWidgets import QCheckBox, QHBoxLayout, QWidget

from frontend.desktop.components import (
    FormDialog,
    SearchableComboBox,
    StandardLineEdit,
    StandardTextArea,
    TimeInput,
    apply_tooltip,
)

_DAYS = (("MON", "Lun"), ("TUE", "Mar"), ("WED", "Mié"), ("THU", "Jue"), ("FRI", "Vie"), ("SAT", "Sáb"), ("SUN", "Dom"))


class CompanyProfileDialog(FormDialog):
    def __init__(self, parent=None, *, profile=None) -> None:
        super().__init__(parent, title="Empresa")
        self.legal_name = StandardLineEdit(self)
        self.legal_name.setAccessibleName("Razón social")
        self.form.addRow("Razón social:", self.legal_name)

        self.commercial_name = StandardLineEdit(self)
        self.commercial_name.setAccessibleName("Nombre comercial")
        self.form.addRow("Nombre comercial:", self.commercial_name)

        self.tax_id = StandardLineEdit(self)
        self.tax_id.setAccessibleName("RFC")
        self.form.addRow("RFC:", self.tax_id)

        self.business_name = StandardLineEdit(self)
        self.business_name.setAccessibleName("Razón de negocio")
        self.form.addRow("Giro/negocio:", self.business_name)

        self.default_currency = StandardLineEdit(self)
        self.default_currency.setAccessibleName("Moneda predeterminada")
        apply_tooltip(self.default_currency, "Código ISO 4217 de 3 letras, ej. «MXN».")
        self.form.addRow("Moneda:", self.default_currency)

        self.default_timezone = StandardLineEdit(self)
        self.default_timezone.setAccessibleName("Zona horaria predeterminada")
        apply_tooltip(self.default_timezone, "IANA, ej. «America/Chihuahua».")
        self.form.addRow("Zona horaria:", self.default_timezone)

        self.default_locale = StandardLineEdit(self)
        self.default_locale.setAccessibleName("Configuración regional predeterminada")
        apply_tooltip(self.default_locale, "Formato «xx-XX», ej. «es-MX».")
        self.form.addRow("Configuración regional:", self.default_locale)

        self.fiscal_regime_reference = StandardLineEdit(self)
        self.fiscal_regime_reference.setAccessibleName("Régimen fiscal")
        self.form.addRow("Régimen fiscal:", self.fiscal_regime_reference)

        self.address = StandardLineEdit(self)
        self.address.setAccessibleName("Dirección")
        self.form.addRow("Dirección:", self.address)

        self.phone = StandardLineEdit(self)
        self.phone.setAccessibleName("Teléfono")
        self.form.addRow("Teléfono:", self.phone)

        self.email = StandardLineEdit(self)
        self.email.setAccessibleName("Correo electrónico")
        self.form.addRow("Correo:", self.email)

        self.website = StandardLineEdit(self)
        self.website.setAccessibleName("Sitio web")
        apply_tooltip(self.website, "Debe iniciar con http:// o https://.")
        self.form.addRow("Sitio web:", self.website)

        self.logo_asset_id = StandardLineEdit(self)
        self.logo_asset_id.setAccessibleName("ID de asset del logo")
        apply_tooltip(
            self.logo_asset_id,
            "Referencia (UUID) a un asset ya registrado en otro sistema — §15: nunca una ruta de "
            "archivo arbitraria. Déjalo vacío si no hay logo todavía.",
        )
        self.form.addRow("Logo (ID de asset):", self.logo_asset_id)

        if profile is not None:
            self.legal_name.setText(profile.legal_name)
            self.commercial_name.setText(profile.commercial_name)
            self.tax_id.setText(profile.tax_id)
            self.business_name.setText(profile.business_name)
            self.default_currency.setText(profile.default_currency)
            self.default_timezone.setText(profile.default_timezone)
            self.default_locale.setText(profile.default_locale)
            self.fiscal_regime_reference.setText(profile.fiscal_regime_reference or "")
            self.address.setText(profile.address)
            self.phone.setText(profile.phone or "")
            self.email.setText(profile.email or "")
            self.website.setText(profile.website or "")
            self.logo_asset_id.setText(profile.logo_asset_id or "")

        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        return {
            "legal_name": self.legal_name.text().strip(),
            "commercial_name": self.commercial_name.text().strip(),
            "tax_id": self.tax_id.text().strip(), "business_name": self.business_name.text().strip(),
            "default_currency": self.default_currency.text().strip(),
            "default_timezone": self.default_timezone.text().strip(),
            "default_locale": self.default_locale.text().strip(),
            "fiscal_regime_reference": self.fiscal_regime_reference.text().strip(),
            "address": self.address.text().strip(), "phone": self.phone.text().strip(),
            "email": self.email.text().strip(), "website": self.website.text().strip(),
            "logo_asset_id": self.logo_asset_id.text().strip(),
        }


class SetInstallationBranchDialog(FormDialog):
    def __init__(self, parent=None, *, branch_options=()) -> None:
        super().__init__(parent, title="Sucursal de la instalación")
        self.branch = SearchableComboBox(self, placeholder="Selecciona una sucursal…")
        self.branch.set_options(list(branch_options))
        self.branch.setAccessibleName("Sucursal de la instalación")
        apply_tooltip(
            self.branch,
            "El login y los módulos de esta terminal operarán sobre la sucursal seleccionada.",
        )
        self.form.addRow("Sucursal:", self.branch)

        self.add_button_box(ok_text="Anclar")

    def values(self) -> dict:
        return {"branch_id": self.branch.current_id()}


class _BranchHoursFields:
    """Shared "Horarios" fields — a checkbox gates two `TimeInput`s plus
    a row of day checkboxes, since `BranchProfile` requires opening/
    closing time either both set or both `None` (§16)."""

    def _build_hours_fields(self) -> None:
        self.define_hours = QCheckBox("Definir horario de operación", self)
        self.form.addRow("", self.define_hours)

        self.opening_time = TimeInput(self)
        self.opening_time.setEnabled(False)
        self.form.addRow("Apertura:", self.opening_time)

        self.closing_time = TimeInput(self)
        self.closing_time.setEnabled(False)
        self.form.addRow("Cierre:", self.closing_time)

        days_row = QWidget(self)
        days_layout = QHBoxLayout(days_row)
        days_layout.setContentsMargins(0, 0, 0, 0)
        self.day_checkboxes: dict[str, QCheckBox] = {}
        for code, label in _DAYS:
            checkbox = QCheckBox(label, days_row)
            checkbox.setEnabled(False)
            checkbox.setAccessibleName(f"Día de operación: {label}")
            self.day_checkboxes[code] = checkbox
            days_layout.addWidget(checkbox)
        self.form.addRow("Días:", days_row)

        self.define_hours.toggled.connect(self._on_define_hours_toggled)

    def _on_define_hours_toggled(self, checked: bool) -> None:
        self.opening_time.setEnabled(checked)
        self.closing_time.setEnabled(checked)
        for checkbox in self.day_checkboxes.values():
            checkbox.setEnabled(checked)

    def _hours_values(self) -> dict:
        if not self.define_hours.isChecked():
            return {"opening_time": None, "closing_time": None, "operation_days": ()}
        opening = self.opening_time.time()
        closing = self.closing_time.time()
        days = tuple(code for code, checkbox in self.day_checkboxes.items() if checkbox.isChecked())
        return {
            "opening_time": time_type(opening.hour(), opening.minute()),
            "closing_time": time_type(closing.hour(), closing.minute()),
            "operation_days": days,
        }

    def _prefill_hours(self, *, opening_time: str | None, closing_time: str | None, operation_days) -> None:
        if not opening_time or not closing_time:
            return
        self.define_hours.setChecked(True)
        self.opening_time.set_time_text(opening_time[:5])
        self.closing_time.set_time_text(closing_time[:5])
        for code in operation_days:
            if code in self.day_checkboxes:
                self.day_checkboxes[code].setChecked(True)


class BranchProfileCreateDialog(FormDialog, _BranchHoursFields):
    def __init__(self, parent=None, *, branch_options=()) -> None:
        super().__init__(parent, title="Nueva sucursal")
        self.branch = SearchableComboBox(self, placeholder="Selecciona una sucursal…")
        self.branch.set_options([(o.entity_id, o.name) for o in branch_options])
        self.branch.setAccessibleName("Sucursal")
        apply_tooltip(
            self.branch,
            "Registra el perfil de gobierno de una sucursal ya existente — no crea una nueva.",
        )
        self.form.addRow("Sucursal:", self.branch)

        self.code = StandardLineEdit(self)
        self.code.setAccessibleName("Código")
        self.form.addRow("Código:", self.code)

        self.name = StandardLineEdit(self)
        self.name.setAccessibleName("Nombre")
        self.form.addRow("Nombre:", self.name)

        self.address = StandardLineEdit(self)
        self.address.setAccessibleName("Dirección")
        self.form.addRow("Dirección:", self.address)

        self.phone = StandardLineEdit(self)
        self.phone.setAccessibleName("Teléfono")
        self.form.addRow("Teléfono:", self.phone)

        self.timezone = StandardLineEdit(self)
        self.timezone.setAccessibleName("Zona horaria")
        self.form.addRow("Zona horaria:", self.timezone)

        self.locale = StandardLineEdit(self)
        self.locale.setAccessibleName("Configuración regional")
        self.form.addRow("Configuración regional:", self.locale)

        self._build_hours_fields()

        self.ticket_header = StandardTextArea(self)
        self.ticket_header.setAccessibleName("Encabezado de ticket")
        self.form.addRow("Encabezado de ticket:", self.ticket_header)

        self.ticket_footer = StandardTextArea(self)
        self.ticket_footer.setAccessibleName("Pie de ticket")
        self.form.addRow("Pie de ticket:", self.ticket_footer)

        self.add_button_box(ok_text="Registrar")

    def values(self) -> dict:
        return {
            "branch_id": self.branch.current_id(), "code": self.code.text().strip(),
            "name": self.name.text().strip(), "address": self.address.text().strip(),
            "phone": self.phone.text().strip(), "timezone": self.timezone.text().strip(),
            "locale": self.locale.text().strip(), **self._hours_values(),
            "ticket_header": self.ticket_header.toPlainText().strip(),
            "ticket_footer": self.ticket_footer.toPlainText().strip(),
        }


class BranchProfileEditDialog(FormDialog, _BranchHoursFields):
    def __init__(self, parent=None, *, profile=None) -> None:
        super().__init__(parent, title="Editar sucursal")
        self.name = StandardLineEdit(self)
        self.name.setAccessibleName("Nombre")
        self.form.addRow("Nombre:", self.name)

        self.address = StandardLineEdit(self)
        self.address.setAccessibleName("Dirección")
        self.form.addRow("Dirección:", self.address)

        self.phone = StandardLineEdit(self)
        self.phone.setAccessibleName("Teléfono")
        self.form.addRow("Teléfono:", self.phone)

        self.timezone = StandardLineEdit(self)
        self.timezone.setAccessibleName("Zona horaria")
        self.form.addRow("Zona horaria:", self.timezone)

        self.locale = StandardLineEdit(self)
        self.locale.setAccessibleName("Configuración regional")
        self.form.addRow("Configuración regional:", self.locale)

        self._build_hours_fields()

        self.ticket_header = StandardTextArea(self)
        self.ticket_header.setAccessibleName("Encabezado de ticket")
        self.form.addRow("Encabezado de ticket:", self.ticket_header)

        self.ticket_footer = StandardTextArea(self)
        self.ticket_footer.setAccessibleName("Pie de ticket")
        self.form.addRow("Pie de ticket:", self.ticket_footer)

        if profile is not None:
            self.name.setText(profile.name)
            self.address.setText(profile.address)
            self.phone.setText(profile.phone or "")
            self.timezone.setText(profile.timezone)
            self.locale.setText(profile.locale)
            self._prefill_hours(
                opening_time=profile.opening_time, closing_time=profile.closing_time,
                operation_days=profile.operation_days,
            )
            self.ticket_header.setPlainText(profile.ticket_header)
            self.ticket_footer.setPlainText(profile.ticket_footer)

        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        return {
            "name": self.name.text().strip(), "address": self.address.text().strip(),
            "phone": self.phone.text().strip(), "timezone": self.timezone.text().strip(),
            "locale": self.locale.text().strip(), **self._hours_values(),
            "ticket_header": self.ticket_header.toPlainText().strip(),
            "ticket_footer": self.ticket_footer.toPlainText().strip(),
        }
