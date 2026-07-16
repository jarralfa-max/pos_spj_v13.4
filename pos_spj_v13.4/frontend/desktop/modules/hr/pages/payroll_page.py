"""Nómina — secuencia canónica Generar → Autorizar → Pagar.

Cada acción es un botón distinto; nunca un solo botón que genere-autorice-pague.
La separación de funciones y la idempotencia las garantiza el dominio.
"""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.hr.dialogs.hr_dialogs import GeneratePayrollDialog
from frontend.desktop.modules.hr.pages._page_base import HRPage
from modulos.ui_components import (
    create_danger_button,
    create_primary_button,
    create_secondary_button,
    create_success_button,
)


class PayrollPage(HRPage):
    title = "Nómina"
    subtitle = "Corridas de nómina y su ciclo de autorización y pago"
    columns = [
        ColumnSpec("Periodo", "text"),
        ColumnSpec("Percepciones", "numeric"),
        ColumnSpec("Deducciones", "numeric"),
        ColumnSpec("Neto", "numeric"),
        ColumnSpec("Estado", "status"),
    ]

    def _build_actions(self) -> None:
        generate = create_primary_button(self, "Generar corrida")
        generate.clicked.connect(self._generate)
        self.header.add_action(generate)
        authorize = create_secondary_button(self, "Autorizar")
        authorize.clicked.connect(self._authorize)
        self.header.add_action(authorize)
        pay = create_success_button(self, "Pagar")
        pay.clicked.connect(self._pay)
        self.header.add_action(pay)
        cancel = create_danger_button(self, "Cancelar")
        cancel.clicked.connect(self._cancel)
        self.header.add_action(cancel)

    def _load(self) -> None:
        self.set_table(self._presenter.payroll_runs())

    def _generate(self) -> None:
        dialog = GeneratePayrollDialog(self)
        if dialog.exec_():
            ok, msg = self._presenter.generate_payroll(**dialog.values())
            self.notify(ok, msg)

    def _selected_or_warn(self) -> str | None:
        run_id = self.selected_id()
        if not run_id:
            self.notify(False, "Seleccione una corrida.")
        return run_id

    def _authorize(self) -> None:
        run_id = self._selected_or_warn()
        if run_id:
            self.notify(*self._presenter.authorize_payroll(run_id))

    def _pay(self) -> None:
        run_id = self._selected_or_warn()
        if run_id:
            self.notify(*self._presenter.pay_payroll(run_id))

    def _cancel(self) -> None:
        run_id = self._selected_or_warn()
        if run_id:
            self.notify(*self._presenter.cancel_payroll(run_id))
