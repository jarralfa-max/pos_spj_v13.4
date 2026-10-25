"""Periodos contables y cierre (§9): checklist, pre-cierre, cierre, reapertura
con motivo y autorización de diferencias materiales."""

from __future__ import annotations

from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.finance.dialogs.fields_dialog import FieldSpec, ask, ask_reason
from frontend.desktop.modules.finance.dialogs.table_dialog import TableDialog
from frontend.desktop.modules.finance.pages._page_base import FinancePage, P


class FiscalPeriodsPage(FinancePage):
    title = "Periodos y cierre"
    subtitle = "Un periodo cerrado no acepta asientos; reabrirlo exige motivo y queda auditado"
    columns = [
        ColumnSpec("Periodo", "date"),
        ColumnSpec("Estado", "status"),
        ColumnSpec("Pre-cierre", "date"),
        ColumnSpec("Cierre", "date"),
        ColumnSpec("Reapertura", "date"),
        ColumnSpec("Motivo de reapertura"),
    ]
    header_actions = [("Abrir periodo", P.PERIOD_CLOSE, "_open", False)]
    row_actions = [
        ("Revisar checklist", P.PERIOD_READ, "_checklist"),
        ("Pre-cierre", P.PERIOD_CLOSE, "_soft_close"),
        ("Cerrar", P.PERIOD_CLOSE, "_close"),
        ("Reabrir", P.PERIOD_REOPEN, "_reopen"),
    ]

    def _build_extra(self) -> None:
        self._exceptions = StandardTable([
            ColumnSpec("Periodo", "date"), ColumnSpec("Control", "status"),
            ColumnSpec("Sujeto"), ColumnSpec("Esperado", "numeric"),
            ColumnSpec("Real", "numeric"), ColumnSpec("Diferencia", "numeric"),
        ], self)
        self._exceptions.setMaximumHeight(170)
        self._layout.addWidget(self._exceptions)
        authorize = create_secondary_button(self, "Autorizar diferencia")
        authorize.clicked.connect(self._authorize_exception)
        self._guard(authorize, P.CLOSE_EXCEPTION_AUTHORIZE)
        self._layout.addWidget(authorize)

    def _load(self) -> None:
        self.set_table(self._presenter.fiscal_periods())
        exceptions = self._presenter.close_exceptions()
        self._exceptions.load_rows(exceptions.rows, row_ids=exceptions.row_ids)

    def _year_month(self) -> tuple[int, int]:
        year, month = self.selected_id().split("-")
        return int(year), int(month)

    def _open(self) -> None:
        today = self._presenter.today()
        values = ask(self, "Abrir periodo", [
            FieldSpec("year", "Año", "int", required=True, minimum=2000, maximum=2100,
                      default=today.year),
            FieldSpec("month", "Mes", "int", required=True, minimum=1, maximum=12,
                      default=today.month),
        ])
        if values:
            self.run(self._presenter.open_period(values["year"], values["month"]))

    def _checklist(self) -> bool:
        ok, result = self._presenter.close_checklist(*self._year_month())
        if not ok:
            self.notify(False, result)
            return False
        TableDialog(self, f"Checklist de cierre {self.selected_id()}", [
            ColumnSpec("Control"), ColumnSpec("Resultado", "status"), ColumnSpec("Detalle"),
        ], result, note="Los controles bloqueantes impiden cerrar; las advertencias no.").exec_()
        return True

    def _soft_close(self) -> None:
        self.run(self._presenter.close_period(*self._year_month(), soft=True))

    def _close(self) -> None:
        self.run(self._presenter.close_period(*self._year_month(), soft=False))

    def _reopen(self) -> None:
        reason = ask_reason(self, "Reabrir periodo", "Motivo de la reapertura")
        if reason:
            self.run(self._presenter.reopen_period(*self._year_month(), reason))

    def _authorize_exception(self) -> None:
        exception_id = self._exceptions.selected_row_id()
        if not exception_id:
            self.notify(False, "Elija la diferencia a autorizar.")
            return
        reason = ask_reason(self, "Autorizar diferencia de cierre", "Justificación")
        if reason:
            self.run(self._presenter.authorize_close_exception(exception_id, reason))
