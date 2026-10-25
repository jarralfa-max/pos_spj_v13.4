"""Dimensiones analíticas (§19): centros de costo y de utilidad, proyectos
(CAPEX) y departamentos para clasificar renglones de asiento."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.dialogs.fields_dialog import FieldSpec, ask
from frontend.desktop.modules.finance.pages._page_base import FinancePage, P

_KINDS = [("COST_CENTER", "Centro de costo"), ("PROFIT_CENTER", "Centro de utilidad"),
          ("PROJECT", "Proyecto"), ("DEPARTMENT", "Departamento")]


class DimensionsPage(FinancePage):
    title = "Dimensiones"
    subtitle = "Centros de costo, centros de utilidad, proyectos y departamentos"
    columns = [
        ColumnSpec("Dimensión", "status"),
        ColumnSpec("Código", "date"),
        ColumnSpec("Nombre"),
        ColumnSpec("Marca", "status"),
    ]
    header_actions = [("Nueva dimensión", P.SETTINGS_MANAGE, "_create", True)]

    def _load(self) -> None:
        self.set_table(self._presenter.dimensions())

    def _create(self) -> None:
        values = ask(self, "Nueva dimensión", [
            FieldSpec("kind", "Dimensión", "combo", required=True, options=_KINDS),
            FieldSpec("code", "Código", required=True),
            FieldSpec("name", "Nombre", required=True),
            FieldSpec("is_capex", "Proyecto de inversión (CAPEX)", "check"),
        ])
        if values:
            if values["kind"] != "PROJECT":
                values["is_capex"] = False
            self.run(self._presenter.create_dimension(**values))
