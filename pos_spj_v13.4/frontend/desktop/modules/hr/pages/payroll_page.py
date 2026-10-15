"""Nómina — secuencia canónica Generar → Revisar → Autorizar → Pagar.

Cada acción es un botón distinto; nunca un solo botón que genere-autorice-pague.
La separación de funciones y la idempotencia las garantiza el dominio.
Auditoría RRHH HR-29: la corrida se revisa por empleado antes de autorizar y
pagar exige método, referencia y confirmar el importe.
"""

from __future__ import annotations

from frontend.desktop.components.buttons import (
    create_danger_button,
    create_primary_button,
    create_secondary_button,
    create_success_button,
)
from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.hr.dialogs.hr_dialogs import (
    GeneratePayrollDialog,
    PayrollDetailDialog,
    PayrollPaymentDialog,
)
from frontend.desktop.modules.hr.pages._page_base import HRPage
from backend.shared.ids import new_uuid


class PayrollPage(HRPage):
    title = "Nómina"
    subtitle = "Corridas de nómina y su ciclo de revisión, autorización y pago"
    columns = [
        ColumnSpec("Periodo", "text"),
        ColumnSpec("Percepciones", "numeric"),
        ColumnSpec("Deducciones", "numeric"),
        ColumnSpec("Neto", "numeric"),
        ColumnSpec("Estado", "status"),
    ]

    def _build_actions(self) -> None:
        self._add_action(create_primary_button(self, "Generar corrida"), "payroll_generate",
                         self._generate)
        self._add_action(create_secondary_button(self, "Ver detalle"), "payroll_view",
                         self._detail)
        self._add_action(create_secondary_button(self, "Autorizar"), "payroll_authorize",
                         self._authorize)
        self._add_action(create_success_button(self, "Pagar"), "payroll_pay", self._pay)
        self._add_action(create_danger_button(self, "Cancelar"), "payroll_cancel", self._cancel)
        self._add_action(create_secondary_button(self, "Recibos PDF"), "payroll_receipt",
                         lambda: self._receipts_pdf(None))
        self._add_action(create_secondary_button(self, "Imprimir recibos"), "payroll_receipt",
                         lambda: self._receipts_ticket(None))
        self._add_action(create_secondary_button(self, "Complementaria"),
                         "payroll_complementary", self._complementary)
        self._add_action(create_danger_button(self, "Revertir pago"), "payroll_reverse_payment",
                         self._reverse_payment)

    def _load(self) -> None:
        self.set_table(self._presenter.payroll_runs())

    def _generate(self) -> None:
        operation_id = new_uuid()   # estable mientras el diálogo siga abierto
        dialog = GeneratePayrollDialog(self, on_submit=lambda values: self._presenter.generate_payroll(
            operation_id=operation_id, **values))
        if dialog.exec_():
            self.notify(True, getattr(dialog, "submitted_message", "Corrida generada"))
            self.reload()

    def _selected_or_warn(self) -> str | None:
        run_id = self.selected_id()
        if not run_id:
            self.notify(False, "Seleccione una corrida.")
        return run_id

    def _detail(self) -> None:
        run_id = self._selected_or_warn()
        if not run_id:
            return
        detail = self._presenter.payroll_detail(run_id)
        if detail is None:
            self.notify(False, "La corrida no está al alcance de tu sesión.")
            return
        receipts = self._allowed("payroll_receipt")
        PayrollDetailDialog(
            detail, self,
            on_receipt_pdf=(lambda ids: self._receipts_pdf(ids, run_id=run_id)) if receipts else None,
            on_receipt_ticket=(lambda ids: self._receipts_ticket(ids, run_id=run_id))
            if receipts else None).exec_()

    def _receipts_pdf(self, employee_ids, *, run_id=None):
        from PyQt5.QtWidgets import QFileDialog
        run_id = run_id or self._selected_or_warn()
        if not run_id:
            return False, "Seleccione una corrida."
        path, _ = QFileDialog.getSaveFileName(self, "Guardar recibos de nómina",
                                              "recibos_nomina.pdf", "PDF (*.pdf)")
        if not path:
            return False, "Sin archivo seleccionado."
        result = self._presenter.export_receipts_pdf(run_id, path, employee_ids=employee_ids)
        self.notify(*result)
        return result

    def _receipts_ticket(self, employee_ids, *, run_id=None):
        run_id = run_id or self._selected_or_warn()
        if not run_id:
            return False, "Seleccione una corrida."
        result = self._presenter.print_receipts(run_id, employee_ids=employee_ids)
        self.notify(*result)
        return result

    def _complementary(self) -> None:
        from frontend.desktop.components.dialogs import FormDialog
        run_id = self._selected_or_warn()
        if not run_id:
            return
        reason, ok = FormDialog.get_text(
            self, "Corrida complementaria",
            "Motivo (se paga sólo la diferencia a favor de cada empleado):")
        if ok:
            done, message = self._presenter.generate_complementary(run_id, reason=reason.strip())
            self.notify(done, message)
            if done:
                self.reload()

    def _reverse_payment(self) -> None:
        from frontend.desktop.components.dialogs import FormDialog
        run_id = self._selected_or_warn()
        if not run_id:
            return
        reason, ok = FormDialog.get_text(
            self, "Revertir pago de nómina",
            "Motivo del reverso (el asiento contable se revierte):")
        if ok:
            done, message = self._presenter.reverse_payment(run_id, reason=reason.strip())
            self.notify(done, message)
            if done:
                self.reload()

    def _authorize(self) -> None:
        run_id = self._selected_or_warn()
        if run_id:
            ok, msg = self._presenter.authorize_payroll(run_id)
            self.notify(ok, msg)
            if ok:
                self.reload()

    def _pay(self) -> None:
        run_id = self._selected_or_warn()
        if not run_id:
            return
        detail = self._presenter.payroll_detail(run_id)
        if detail is None:
            self.notify(False, "La corrida no está al alcance de tu sesión.")
            return
        operation_id = new_uuid()
        dialog = PayrollPaymentDialog(detail, self, on_submit=lambda values: self._presenter.pay_payroll(
            run_id, operation_id=operation_id, **values))
        if dialog.exec_():
            self.notify(True, getattr(dialog, "submitted_message", "Nómina pagada"))
            self.reload()

    def _cancel(self) -> None:
        run_id = self._selected_or_warn()
        if run_id:
            ok, msg = self._presenter.cancel_payroll(run_id)
            self.notify(ok, msg)
            if ok:
                self.reload()
