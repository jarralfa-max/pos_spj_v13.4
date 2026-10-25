"""Depreciación (§17): corridas mensuales registradas; una corrida por periodo
y activo (repetirla no duplica)."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.dialogs.fields_dialog import FieldSpec, ask
from frontend.desktop.modules.finance.pages._page_base import FinancePage, P


class DepreciationPage(FinancePage):
    title = "Depreciación"
    subtitle = "Corridas mensuales con su asiento por activo"
    columns = [
        ColumnSpec("Periodo", "date"),
        ColumnSpec("Activos", "numeric"),
        ColumnSpec("Importe", "numeric"),
        ColumnSpec("Ejecutó", "date"),
        ColumnSpec("Fecha", "date"),
    ]
    header_actions = [("Correr depreciación", P.ASSET_DEPRECIATE, "_run", True)]

    def _load(self) -> None:
        self.set_table(self._presenter.depreciation_runs())

    def _run(self) -> None:
        today = self._presenter.today()
        values = ask(self, "Correr depreciación del mes", [
            FieldSpec("year", "Año", "int", required=True, minimum=2000, maximum=2100,
                      default=today.year),
            FieldSpec("month", "Mes", "int", required=True, minimum=1, maximum=12,
                      default=today.month),
        ])
        if values:
            self.run(self._presenter.run_depreciation(values["year"], values["month"]))
