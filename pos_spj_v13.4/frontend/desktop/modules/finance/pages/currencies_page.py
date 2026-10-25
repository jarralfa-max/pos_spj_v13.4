"""Monedas y tipos de cambio (§23): un asiento en moneda extranjera se
convierte a la moneda base con el tipo de cambio vigente de su fecha."""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.finance.dialogs.fields_dialog import FieldSpec, ask
from frontend.desktop.modules.finance.pages._page_base import FinancePage, P


class CurrenciesPage(FinancePage):
    title = "Monedas y tipos de cambio"
    subtitle = "Tipos de cambio registrados (los más recientes primero)"
    columns = [
        ColumnSpec("Fecha", "date"),
        ColumnSpec("De", "status"),
        ColumnSpec("A", "status"),
        ColumnSpec("Tipo de cambio", "numeric"),
        ColumnSpec("Fuente"),
    ]
    header_actions = [("Registrar tipo de cambio", P.SETTINGS_MANAGE, "_register", True)]

    def _build_extra(self) -> None:
        label = QLabel("Monedas", self)
        label.setProperty("role", "muted")
        self._layout.addWidget(label)
        self._currencies = StandardTable([
            ColumnSpec("Código", "date"), ColumnSpec("Nombre"),
            ColumnSpec("Decimales", "numeric"), ColumnSpec("Activa", "status")], self)
        self._currencies.setMaximumHeight(140)
        self._layout.addWidget(self._currencies)

    def _load(self) -> None:
        data = self._presenter.currencies_and_rates()
        self.set_table(data["rates"])
        self._currencies.load_rows(data["currencies"].rows)

    def _register(self) -> None:
        p = self._presenter
        currencies = p.currency_options()
        values = ask(self, "Tipo de cambio", [
            FieldSpec("from_currency", "De", "combo", required=True, options=currencies),
            FieldSpec("to_currency", "A", "combo", required=True, options=currencies,
                      default=p.base_currency()),
            FieldSpec("rate", "Tipo de cambio", "decimal", required=True, placeholder="18.25"),
            FieldSpec("effective_date", "Vigente desde", "date", required=True,
                      default=p.today()),
            FieldSpec("source", "Fuente (p. ej. DOF, Banxico)"),
        ], validator=lambda v: "Elija dos monedas distintas."
           if v["from_currency"] == v["to_currency"] else None)
        if values:
            self.run(p.register_exchange_rate(**values))
