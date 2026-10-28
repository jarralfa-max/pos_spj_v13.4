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
        ColumnSpec("Marca / unidad", "status"),
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
            # Centros de costo y de utilidad: de qué unidad organizacional son
            # (sucursal, planta, región, oficina). Vacío = de toda la empresa.
            FieldSpec("org_unit_id", "Unidad organizacional", "combo",
                      options=[("", "(Toda la empresa)"),
                               *self._presenter.org_unit_options()]),
        ])
        if values:
            if values["kind"] != "PROJECT":
                values["is_capex"] = False
            if values["kind"] not in ("COST_CENTER", "PROFIT_CENTER"):
                values["org_unit_id"] = None
            values["org_unit_id"] = values.get("org_unit_id") or None
            self.run(self._presenter.create_dimension(**values))
