"""InvoiceRequestDialog — datos fiscales para pedir la factura de una venta
cobrada (§45). Ventas sólo REGISTRA la solicitud; el CFDI es de Fiscal.

Campos opcionales a propósito: vacíos, `RequestInvoiceUseCase` toma el perfil
fiscal del cliente asignado y, si no hay, factura a público en general. No hay
catálogo de usos de CFDI en este repositorio, así que el uso se escribe (p. ej.
G03) en vez de ofrecer una lista inventada aquí.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components import (
    FormField,
    StandardDialog,
    StandardForm,
    StandardLineEdit,
    TaxIdentifierInput,
)


class InvoiceRequestDialog(StandardDialog):
    def __init__(self, *, folio: str, total_text: str, parent=None) -> None:
        super().__init__(parent, title=f"Factura — venta {folio}")
        self.setObjectName("posInvoiceDialog")
        self.tax_identifier: str | None = None
        self.legal_name: str | None = None
        self.cfdi_use: str | None = None

        info = QLabel(f"Total {total_text}. Deja los datos vacíos para usar el perfil fiscal "
                      "del cliente o facturar a público en general.", self)
        info.setWordWrap(True)
        info.setProperty("role", "subtitle")
        self.content_layout().addWidget(info)

        form = StandardForm(self)
        self._rfc = TaxIdentifierInput(self)
        form.add_field("rfc", FormField("RFC", self._rfc))
        self._name = StandardLineEdit(self, placeholder="Razón social")
        form.add_field("legal_name", FormField("Razón social", self._name))
        self._use = StandardLineEdit(self, placeholder="p. ej. G03")
        form.add_field("cfdi_use", FormField("Uso de CFDI", self._use))
        self.content_layout().addWidget(form)

        box = self.add_button_box(ok_text="Solicitar factura")
        box.accepted.disconnect()
        box.accepted.connect(self._submit)

    def set_values(self, *, rfc: str = "", legal_name: str = "", cfdi_use: str = "") -> None:
        self._rfc.setText(rfc)
        self._name.setText(legal_name)
        self._use.setText(cfdi_use)

    def _submit(self) -> None:
        self.tax_identifier = (self._rfc.text() or "").strip().upper() or None
        self.legal_name = self._name.value().strip() or None
        self.cfdi_use = self._use.value().strip().upper() or None
        self.accept()
