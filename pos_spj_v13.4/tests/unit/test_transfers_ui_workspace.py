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
