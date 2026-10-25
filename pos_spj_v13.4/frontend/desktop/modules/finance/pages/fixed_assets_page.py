"""Activos fijos (§17): capitalización, suspensión, reactivación y baja
(desecho, venta con utilidad o pérdida, castigo)."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.dialogs.fields_dialog import FieldSpec, ask, ask_reason
from frontend.desktop.modules.finance.pages._page_base import FinancePage, P

_STATUS = [("ACTIVE", "Activo"), ("SUSPENDED", "Suspendido"), ("DISPOSED", "Dado de baja"),
           ("SOLD", "Vendido"), ("WRITTEN_OFF", "Castigado")]
_OUTCOMES = [("DISPOSED", "Desecho / baja"), ("SOLD", "Venta"), ("WRITTEN_OFF", "Castigo")]


class FixedAssetsPage(FinancePage):
    title = "Activos fijos"
    subtitle = "Costo, depreciación acumulada y valor en libros"
    status_filter = _STATUS
    columns = [
        ColumnSpec("Código", "date"),
        ColumnSpec("Activo"),
        ColumnSpec("Categoría"),
        ColumnSpec("Capitalizado", "date"),
        ColumnSpec("Costo", "numeric"),
        ColumnSpec("Depreciación", "numeric"),
        ColumnSpec("Valor en libros", "numeric"),
        ColumnSpec("Estado", "status"),
        ColumnSpec("Último periodo", "date"),
    ]
    header_actions = [("Capitalizar activo", P.ASSET_MANAGE, "_capitalize", True)]
    row_actions = [
        ("Suspender", P.ASSET_MANAGE, "_suspend"),
        ("Reactivar", P.ASSET_MANAGE, "_resume"),
        ("Dar de baja", P.ASSET_MANAGE, "_dispose"),
    ]

    def _load(self) -> None:
        self.set_table(self._presenter.fixed_assets(status=self._status_id()))

    def _allowed_actions(self):
        allowed = super()._allowed_actions()
        status = self._presenter.asset_status(self.selected_id()) if self.selected_id() else ""
        by_status = {"ACTIVE": {"Suspender", "Dar de baja"},
                     "SUSPENDED": {"Reactivar", "Dar de baja"}}
        return allowed & by_status.get(status, set())

    def _capitalize(self) -> None:
        p = self._presenter
        values = ask(self, "Capitalizar activo", [
            FieldSpec("name", "Nombre", required=True),
            FieldSpec("asset_code", "Código / etiqueta"),
            FieldSpec("asset_category_id", "Categoría", "combo",
                      options=p.asset_category_options()),
            FieldSpec("acquisition_cost", "Costo de adquisición", "money", required=True),
            FieldSpec("residual_value", "Valor residual", "money", allow_zero=True),
            FieldSpec("useful_life_months", "Vida útil (meses)", "int", required=True,
                      minimum=1, maximum=600, default=36),
            FieldSpec("capitalization_date", "Fecha de capitalización", "date", required=True,
                      default=p.today()),
            FieldSpec("paid_from_treasury_account_id", "Pagado desde", "combo",
                      options=p.treasury_accounts(money_only=True)),
            FieldSpec("supplier_id", "O a crédito del proveedor", "search",
                      provider=p.supplier_options),
            FieldSpec("document_number", "Factura del proveedor"),
            FieldSpec("project_id", "Proyecto (CAPEX)", "combo",
                      options=p.dimension_options("projects")),
        ], validator=lambda v: None if bool(v["supplier_id"]) != bool(
            v["paid_from_treasury_account_id"]) else
            "Indique la cuenta que pagó o el proveedor a crédito; uno solo.")
        if values:
            self.run(p.capitalize_asset(**values))

    def _suspend(self) -> None:
        reason = ask_reason(self, "Suspender activo")
        if reason:
            self.run(self._presenter.suspend_asset(self.selected_id(), reason))

    def _resume(self) -> None:
        self.run(self._presenter.resume_asset(self.selected_id()))

    def _dispose(self) -> None:
        p = self._presenter
        values = ask(self, "Baja de activo", [
            FieldSpec("outcome", "Forma de baja", "combo", required=True, options=_OUTCOMES),
            FieldSpec("proceeds", "Importe cobrado (venta)", "money", allow_zero=True),
            FieldSpec("treasury_account_id", "Cuenta que recibe (venta)", "combo",
                      options=p.treasury_accounts(money_only=True)),
            FieldSpec("reason", "Motivo", "multiline", required=True),
        ])
        if values:
            if values["outcome"] != "SOLD":
                values["proceeds"], values["treasury_account_id"] = None, None
            self.run(p.dispose_asset(self.selected_id(), **values))
