"""Impuestos (§22): códigos, tasas con vigencia y su cuenta contable. Ningún
porcentaje vive en código; cada producto/categoría/canal se liga por regla."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.dialogs.fields_dialog import FieldSpec, ask
from frontend.desktop.modules.finance.pages._page_base import FinancePage, P


class TaxesPage(FinancePage):
    title = "Impuestos"
    subtitle = "Códigos de impuesto, tasa vigente y reglas de aplicación"
    columns = [
        ColumnSpec("Código", "date"),
        ColumnSpec("Nombre"),
        ColumnSpec("Tipo", "status"),
        ColumnSpec("Dirección", "status"),
        ColumnSpec("Tasa vigente", "numeric"),
        ColumnSpec("Reglas"),
        ColumnSpec("Estado", "status"),
    ]
    header_actions = [("Nuevo impuesto", P.SETTINGS_MANAGE, "_create", True)]

    def _load(self) -> None:
        self.set_table(self._presenter.taxes())

    def _create(self) -> None:
        p = self._presenter
        values = ask(self, "Nuevo código de impuesto", [
            FieldSpec("code", "Código", required=True, placeholder="Ej. IEPS8"),
            FieldSpec("name", "Nombre", required=True),
            FieldSpec("kind", "Tipo", "combo", required=True, options=p.tax_kind_options()),
            FieldSpec("direction", "Dirección", "combo", required=True,
                      options=p.tax_direction_options()),
            FieldSpec("rate_percent", "Tasa (%)", "decimal", required=True, placeholder="16"),
            FieldSpec("effective_from", "Vigente desde", "date", required=True,
                      default=p.today()),
            FieldSpec("account_id", "Cuenta contable del impuesto", "combo", required=True,
                      options=p.postable_accounts("ASSET", "LIABILITY")),
        ])
        if values:
            self.run(p.create_tax_code(**values))
