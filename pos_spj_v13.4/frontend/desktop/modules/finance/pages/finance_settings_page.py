"""Parámetros de Finanzas (§24): todo umbral y regla configurable vive aquí,
con motivo y auditoría de cada cambio; nada queda fijo en código."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.dialogs.fields_dialog import FieldSpec, ask
from frontend.desktop.modules.finance.pages._page_base import FinancePage, P


class FinanceSettingsPage(FinancePage):
    title = "Parámetros financieros"
    subtitle = "Moneda base, segregación, umbrales de autorización, tolerancias y horizontes"
    columns = [ColumnSpec("Parámetro"), ColumnSpec("Valor")]
    row_actions = [("Cambiar", P.SETTINGS_MANAGE, "_change")]

    def _load(self) -> None:
        self.set_table(self._presenter.settings_rows())

    def _change(self) -> None:
        key = self.selected_id()
        p = self._presenter
        current = p.setting_value(key)
        label = self._table.item(self._table.currentRow(), 0).text()
        if p.setting_is_bool(key):
            field = FieldSpec("value", label, "check", default=current == "1")
        elif key == "rounding_account_id":
            field = FieldSpec("value", label, "combo", required=True,
                              options=p.postable_accounts(), default=current)
        elif key == "base_currency_code":
            field = FieldSpec("value", label, "combo", required=True,
                              options=p.currency_options(), default=current)
        else:
            field = FieldSpec("value", label, "decimal", default=current,
                              placeholder="Vacío: sin límite / no aplica")
        values = ask(self, "Cambiar parámetro", [
            field, FieldSpec("reason", "Motivo del cambio", "multiline", required=True)])
        if values is None:
            return
        value = values["value"]
        if isinstance(value, bool):
            value = "1" if value else "0"
        self.run(p.update_setting(key, value or "", values["reason"]))
