"""Dialogs for the "Rutas de impresión" action on the Dispositivos
section — SET-8's Routing/Failover pillar had zero UI before this round.

There's no multi-choice combo component in this repo yet, so the
fallback chain is entered as comma-separated device *codes* (not raw
UUIDs) and resolved against the same `device_options` list the primary
picker already has — no new backend endpoint needed for that
resolution, it's a dialog-level convenience.
"""

from __future__ import annotations

from frontend.desktop.components import FormDialog, SearchableComboBox, StandardLineEdit, apply_tooltip


class _FallbackCodesField:
    """Shared by create/edit dialogs: turns a comma-separated device-code
    string into a tuple of device ids, using the same `device_options`
    the primary selector was built from. Unknown codes are ignored
    (rather than raising mid-dialog) — the use case's own domain
    validation (`PrintRoute.create/set_fallback_chain`) is the real
    source of truth for what's a legal id."""

    def _build_fallback_field(self, device_options) -> None:
        self._code_to_id = {o.code: o.entity_id for o in device_options}
        self.fallback_codes = StandardLineEdit(self)
        self.fallback_codes.setAccessibleName("Dispositivos de respaldo")
        apply_tooltip(
            self.fallback_codes,
            "Opcional. Códigos de dispositivo separados por coma, en orden de preferencia. "
            "Ej. «PRN-02, PRN-03».",
        )
        self.form.addRow("Respaldo (opcional):", self.fallback_codes)

    def _fallback_device_ids(self) -> tuple[str, ...]:
        codes = [c.strip() for c in self.fallback_codes.text().split(",") if c.strip()]
        return tuple(self._code_to_id[c] for c in codes if c in self._code_to_id)


class PrintRouteCreateDialog(FormDialog, _FallbackCodesField):
    def __init__(self, parent=None, *, device_options=(), branch_options=()) -> None:
        super().__init__(parent, title="Nueva ruta de impresión")
        self.document_type = StandardLineEdit(self)
        self.document_type.setAccessibleName("Tipo de documento")
        apply_tooltip(self.document_type, "Ej. «SALE_TICKET», «PURCHASE_ORDER».")
        self.form.addRow("Tipo de documento:", self.document_type)

        self.primary_device = SearchableComboBox(self, placeholder="Selecciona un dispositivo…")
        self.primary_device.set_options([(o.entity_id, f"{o.name} ({o.code})") for o in device_options])
        self.primary_device.setAccessibleName("Dispositivo principal")
        self.form.addRow("Principal:", self.primary_device)

        self._build_fallback_field(device_options)

        self.branch = SearchableComboBox(self, placeholder="Todas las sucursales…")
        self.branch.set_options([(o.entity_id, o.name) for o in branch_options])
        self.branch.setAccessibleName("Sucursal (ámbito)")
        self.form.addRow("Sucursal (opcional):", self.branch)

        self.module = StandardLineEdit(self)
        self.module.setAccessibleName("Módulo")
        apply_tooltip(self.module, "Opcional. Ej. «ventas», «compras».")
        self.form.addRow("Módulo (opcional):", self.module)

        self.channel = StandardLineEdit(self)
        self.channel.setAccessibleName("Canal")
        apply_tooltip(self.channel, "Opcional. Ej. «mostrador», «whatsapp».")
        self.form.addRow("Canal (opcional):", self.channel)

        self.add_button_box(ok_text="Crear ruta")

    def values(self) -> dict:
        return {
            "document_type": self.document_type.text().strip(),
            "primary_device_id": self.primary_device.current_id(),
            "fallback_device_ids": self._fallback_device_ids(),
            "branch_id": self.branch.current_id(),
            "module": self.module.text().strip() or None,
            "channel": self.channel.text().strip() or None,
        }


class PrintRouteEditDialog(FormDialog, _FallbackCodesField):
    def __init__(
        self, parent=None, *, device_options=(), primary_device_code: str = "",
        fallback_codes: str = "",
    ) -> None:
        super().__init__(parent, title="Editar ruta de impresión")
        self.primary_device = SearchableComboBox(self, placeholder="Selecciona un dispositivo…")
        self.primary_device.set_options([(o.entity_id, f"{o.name} ({o.code})") for o in device_options])
        self.primary_device.setAccessibleName("Dispositivo principal")
        for option in device_options:
            if option.code == primary_device_code:
                self.primary_device.set_current_id(option.entity_id)
                break
        self.form.addRow("Principal:", self.primary_device)

        self._build_fallback_field(device_options)
        self.fallback_codes.setText(fallback_codes)

        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        return {
            "primary_device_id": self.primary_device.current_id(),
            "fallback_device_ids": self._fallback_device_ids(),
        }
