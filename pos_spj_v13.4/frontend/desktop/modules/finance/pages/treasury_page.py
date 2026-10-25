"""Tesorería (§13): saldo, comprometido y disponible por cuenta; alta y
mantenimiento de cuentas; transferencias y movimientos bancarios."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.dialogs.bank_transfer_dialog import BankTransferDialog
from frontend.desktop.modules.finance.dialogs.fields_dialog import FieldSpec, ask, ask_reason
from frontend.desktop.modules.finance.pages._page_base import FinancePage, P


class TreasuryPage(FinancePage):
    title = "Cuentas de tesorería"
    subtitle = "El disponible descuenta pagos programados y autorizados"
    columns = [
        ColumnSpec("Cuenta"),
        ColumnSpec("Tipo", "status"),
        ColumnSpec("Número", "date"),
        ColumnSpec("Moneda", "status"),
        ColumnSpec("Saldo", "numeric"),
        ColumnSpec("Comprometido", "numeric"),
        ColumnSpec("Disponible", "numeric"),
        ColumnSpec("Saldo conciliado", "numeric"),
        ColumnSpec("Conciliado al", "date"),
    ]
    header_actions = [
        ("Transferencia", P.TREASURY_TRANSFER, "_transfer", True),
        ("Movimiento bancario", P.TREASURY_MOVEMENT, "_movement", False),
        ("Nueva cuenta", P.TREASURY_MANAGE, "_create", False),
    ]
    row_actions = [
        ("Editar", P.TREASURY_MANAGE, "_edit"),
        ("Desactivar", P.TREASURY_MANAGE, "_deactivate"),
    ]

    def _load(self) -> None:
        self.set_kpis(self._presenter.treasury_totals())
        self.set_table(self._presenter.treasury_position())

    def _transfer(self) -> None:
        dialog = BankTransferDialog(self, self._presenter.treasury_accounts(money_only=True))
        if dialog.exec_():
            self.run(self._presenter.register_treasury_transfer(**dialog.data()))

    def _movement(self) -> None:
        p = self._presenter
        values = ask(self, "Movimiento bancario", [
            FieldSpec("treasury_account_id", "Cuenta", "combo", required=True,
                      options=p.treasury_accounts(money_only=True)),
            FieldSpec("kind", "Tipo de movimiento", "combo", required=True,
                      options=p.movement_kind_options()),
            FieldSpec("amount", "Importe", "money", required=True),
            FieldSpec("counterpart_account_id", "Contrapartida (vacío: la del perfil)", "combo",
                      options=p.postable_accounts()),
            FieldSpec("reference", "Referencia"),
            FieldSpec("description", "Concepto"),
        ])
        if values:
            self.run(p.register_treasury_movement(**values))

    def _create(self) -> None:
        p = self._presenter
        values = ask(self, "Nueva cuenta de tesorería", [
            FieldSpec("name", "Nombre", required=True),
            FieldSpec("account_type", "Tipo", "combo", required=True,
                      options=p.treasury_type_options()),
            FieldSpec("ledger_account_id", "Cuenta espejo del mayor", "combo", required=True,
                      options=p.postable_accounts("ASSET", "LIABILITY")),
            FieldSpec("bank_name", "Banco"),
            FieldSpec("account_number", "Número de cuenta (se guarda enmascarado)"),
            FieldSpec("restricted", "Fondos restringidos (no disponibles)", "check"),
            FieldSpec("allows_overdraft", "Permite sobregiro pactado", "check"),
        ])
        if values:
            self.run(p.create_treasury_account(**values))

    def _edit(self) -> None:
        values = ask(self, "Editar cuenta de tesorería", [
            FieldSpec("name", "Nombre"),
            FieldSpec("bank_name", "Banco"),
            FieldSpec("account_number", "Número de cuenta nuevo (vacío: no cambia)"),
            FieldSpec("reason", "Motivo del cambio", "multiline", required=True),
        ])
        if values:
            changes = {k: v for k, v in values.items() if v}
            self.run(self._presenter.update_treasury_account(self.selected_id(), **changes))

    def _deactivate(self) -> None:
        reason = ask_reason(self, "Desactivar cuenta de tesorería")
        if reason:
            self.run(self._presenter.update_treasury_account(self.selected_id(), active=False,
                                                             reason=reason))
