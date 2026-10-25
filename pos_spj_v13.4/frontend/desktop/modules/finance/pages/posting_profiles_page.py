"""Perfiles contables (§21): qué cuenta usa cada rol de cada integración.
Cambiar un rol crea una versión nueva con vigencia; los asientos ya
contabilizados no se reexpresan."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.dialogs.fields_dialog import FieldSpec, ask
from frontend.desktop.modules.finance.pages._page_base import FinancePage, P


class PostingProfilesPage(FinancePage):
    title = "Perfiles contables"
    subtitle = "Cuenta por rol de cada integración (Ventas, Compras, Caja, Nómina…)"
    searchable = True
    columns = [
        ColumnSpec("Perfil", "date"),
        ColumnSpec("Descripción"),
        ColumnSpec("Rol"),
        ColumnSpec("Cuenta"),
        ColumnSpec("Desde", "date"),
        ColumnSpec("Hasta", "date"),
        ColumnSpec("Vigencia", "status"),
    ]
    row_actions = [("Cambiar cuenta", P.SETTINGS_MANAGE, "_change")]

    def _load(self) -> None:
        model = self._presenter.posting_profiles()
        needle = self._search.query().strip().lower()
        if needle:
            pairs = [(r, i) for r, i in zip(model.rows, model.row_ids)
                     if needle in " ".join(r).lower()]
            model = type(model)([r for r, _ in pairs], [i for _, i in pairs])
        self.set_table(model)

    def _change(self) -> None:
        profile_id, role = self.selected_id().split("|", 1)
        p = self._presenter
        values = ask(self, f"Cambiar cuenta del rol {role}", [
            FieldSpec("account_id", "Cuenta", "combo", required=True,
                      options=p.postable_accounts(),
                      default=p.profile_accounts(profile_id).get(role)),
            FieldSpec("effective_from", "Vigente desde", "date", required=True,
                      default=p.today()),
            FieldSpec("reason", "Motivo", "multiline", required=True),
        ])
        if values:
            self.run(p.update_posting_profile(profile_id, role, values["account_id"],
                                              values["effective_from"], values["reason"]))
