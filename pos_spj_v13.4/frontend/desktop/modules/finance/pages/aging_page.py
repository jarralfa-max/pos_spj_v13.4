"""Antigüedad de saldos (§11–12): CxC y CxP por cubeta de vencimiento. Un
documento sin vencimiento se muestra aparte, nunca como «al corriente»."""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.finance.pages._page_base import FinancePage

_COLUMNS = [ColumnSpec("Antigüedad"), ColumnSpec("Documentos", "numeric"),
            ColumnSpec("Saldo", "numeric")]


class AgingPage(FinancePage):
    title = "Antigüedad de saldos"
    subtitle = "Cuentas por cobrar y por pagar a la fecha de hoy"
    columns = _COLUMNS

    def _build_extra(self) -> None:
        label = QLabel("Cuentas por pagar", self)
        label.setProperty("role", "muted")
        self._layout.addWidget(label)
        self._payables = StandardTable(_COLUMNS, self)
        self._layout.addWidget(self._payables)

    def _load(self) -> None:
        self.header.set_subtitle("Arriba: cuentas por cobrar · abajo: cuentas por pagar")
        self.set_table(self._presenter.receivable_aging())
        self._payables.load_rows(self._presenter.payable_aging().rows)
