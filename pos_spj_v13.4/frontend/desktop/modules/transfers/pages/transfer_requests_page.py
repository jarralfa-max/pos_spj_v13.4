"""Solicitudes page — the one workflow action wired so far (INV-12): create a
transfer request. Every other page in this module stays the generic
read-only shell (``workspace_pages.py``) until later INV-12.x phases wire
their own actions the same way."""
from PyQt5.QtWidgets import QDialog, QMessageBox

from frontend.desktop.modules.transfers.dialogs import TransferRequestDialog

from .base_page import TransferWorkspacePage


class TransferRequestsPage(TransferWorkspacePage):
    page_id = "transfers_requests"
    title = "Solicitudes"
    subtitle = "Necesidades de traslado y prioridades."
    action_text = "Nueva solicitud"

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(presenter, parent)
        self.action_button.clicked.connect(self._on_create)

    def _on_create(self) -> None:
        dlg = TransferRequestDialog(
            self, branch_options=self._presenter.branch_options(),
            product_provider=self._presenter.product_options)
        if dlg.exec_() != QDialog.Accepted:
            return
        quantity = dlg.quantity_value()
        if not quantity:
            QMessageBox.warning(self, "Solicitudes", "Captura una cantidad mayor a cero.")
            return
        ok, message, _ = self._presenter.create_transfer_request(
            origin_branch_id=dlg.origin_branch_id(),
            destination_branch_id=dlg.destination_branch_id(),
            product_id=dlg.product_id(), quantity=quantity, weight=dlg.weight_value())
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Solicitudes", message)
        if ok:
            self.reload()


__all__ = ["TransferRequestsPage"]
