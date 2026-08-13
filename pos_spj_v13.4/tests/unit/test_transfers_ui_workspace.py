import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from frontend.desktop.modules.transfers.dialogs import (
    PickingDialog, TransferApprovalDialog, TransferReceiptDialog,
    TransferRequestDialog,
)
from frontend.desktop.modules.transfers.navigation.transfers_sidebar import TRANSFERS_NAV
from frontend.desktop.modules.transfers.transfers_presenter import TransfersPresenter
from frontend.desktop.modules.transfers.transfers_view import TransfersView
from frontend.desktop.modules.transfers.transfers_view_models import (
    TransferKPIViewModel, TransferPageViewModel, TransferRowViewModel,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class Queries:
    def __init__(self): self.calls = []
    def page(self, *, page_id, search=""):
        self.calls.append((page_id, search))
        return TransferPageViewModel(
            rows=(TransferRowViewModel("id", "TRF-2026-000001", "Matriz",
                                       "Sucursal Centro", "EN TRÁNSITO",
                                       "24/07/2026 10:30"),),
            kpis=(TransferKPIViewModel("En tránsito", "1", "info"),))


class FakeCreateTransferRequestUseCase:
    """INV-12: a fake matching ``CreateTransferRequestUseCase.execute`` shape,
    so the presenter's command wiring is tested without a real DB."""
    def __init__(self): self.commands = []
    def execute(self, command):
        from types import SimpleNamespace
        self.commands.append(command)
        return SimpleNamespace(transfer_id="t1", transfer_number="TRF-2026-000002")


def test_workspace_builds_all_permitted_routes_lazily_and_supports_target_sizes(app):
    queries = Queries()
    view = TransfersView(TransfersPresenter(queries),
                         has_permission=lambda _permission: True,
                         badges={"in_transit": 1})
    assert view.sidebar.count() == len(TRANSFERS_NAV)
    for entry in TRANSFERS_NAV:
        view.show_route(entry.page_id)
    assert view.stack.count() == len(TRANSFERS_NAV)
    view.resize(1366, 768)
    assert view.minimumWidth() <= 1366 and view.minimumHeight() <= 768
    view.resize(960, 600)
    assert view.sidebar.accessibleName() == "Navegación de transferencias"


def test_sidebar_filters_permissions_and_dialogs_use_accessible_standard_inputs(app):
    view = TransfersView(TransfersPresenter(Queries()),
                         has_permission=lambda permission: permission.endswith("DASHBOARD_VIEW"))
    assert view.sidebar.count() == 2
    dialogs = [TransferRequestDialog(), TransferApprovalDialog(), PickingDialog(),
               TransferReceiptDialog()]
    assert all(dialog.objectName() == "standardDialog" for dialog in dialogs)
    assert dialogs[-1].qr.objectName() == "barcodeInput"
    assert dialogs[-1].weight.objectName() == "decimalInput"


def test_transfer_request_dialog_exposes_branch_and_product_accessors(app):
    from frontend.desktop.components.search_selector import SearchOption

    dlg = TransferRequestDialog(
        branch_options=[SearchOption(id="b1", label="Matriz"),
                        SearchOption(id="b2", label="Sucursal Centro")])
    assert dlg.origin_combo.count() == 2
    dlg.origin_combo.setCurrentIndex(0)
    dlg.destination_combo.setCurrentIndex(1)
    assert dlg.origin_branch_id() == "b1"
    assert dlg.destination_branch_id() == "b2"
    assert dlg.product_id() == ""  # nothing selected yet


def test_create_transfer_request_presenter_command_is_unavailable_without_a_use_case(app):
    presenter = TransfersPresenter(Queries())
    ok, message, data = presenter.create_transfer_request(
        origin_branch_id="b1", destination_branch_id="b2", product_id="p1", quantity="1")
    assert ok is False
    assert data == {}


def test_transfer_requests_page_wires_create_button_to_the_dialog_and_presenter(app, monkeypatch):
    from PyQt5.QtWidgets import QDialog

    import frontend.desktop.modules.transfers.pages.transfer_requests_page as page_module

    class FakeDialog:
        """Plain Python stand-in — avoids monkeypatching sip-bound Qt methods,
        which segfaults CPython under pytest."""
        def __init__(self, *a, **kw): pass
        def exec_(self): return QDialog.Accepted
        def quantity_value(self): return 1
        def weight_value(self): return 0
        def origin_branch_id(self): return "b1"
        def destination_branch_id(self): return "b2"
        def product_id(self): return "p1"

    class Presenter:
        def __init__(self):
            self.reload_calls = 0
            self.create_calls = []

        def load_page(self, page_id, search=""):
            self.reload_calls += 1
            return TransferPageViewModel(rows=(), kpis=())

        def branch_options(self): return []

        def product_options(self, query): return []

        def create_transfer_request(self, **kwargs):
            self.create_calls.append(kwargs)
            return True, "Solicitud TRF-2026-000002 creada.", {"transfer_id": "t1"}

    class FakeMessageBox:
        """Static QMessageBox.information/warning pump a nested native event
        loop that is unstable under the offscreen test platform; recording
        calls instead is enough to assert the right message type was shown."""
        calls = []
        @classmethod
        def information(cls, *args): cls.calls.append(("information", args))
        @classmethod
        def warning(cls, *args): cls.calls.append(("warning", args))

    presenter = Presenter()
    page = page_module.TransferRequestsPage(presenter)
    monkeypatch.setattr(page_module, "TransferRequestDialog", FakeDialog)
    monkeypatch.setattr(page_module, "QMessageBox", FakeMessageBox)
    page._on_create()
    assert presenter.reload_calls == 1
    assert presenter.create_calls == [{
        "origin_branch_id": "b1", "destination_branch_id": "b2",
        "product_id": "p1", "quantity": 1, "weight": 0}]
    assert FakeMessageBox.calls[0][0] == "information"
