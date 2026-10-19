"""Operational geometry and interaction regressions, using real Qt widgets."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from decimal import Decimal
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from backend.application.sales.permissions import SalesPermissions
from backend.shared.ids import new_uuid
from frontend.desktop.modules.sales_pos.sales_pos_presenter import SalesPosPresenter
from frontend.desktop.modules.sales_pos.sales_pos_workspace import SalesPosWorkspace
from frontend.desktop.themes.theme_manager import ThemeManager


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def presenter():
    session = SimpleNamespace(user_id=new_uuid(), active_branch_id=new_uuid(),
                              is_active=True, tiene_permiso=lambda _: True)
    return SalesPosPresenter(session_context=session)


def lines():
    return [SimpleNamespace(id=new_uuid(), product_id=new_uuid(),
            product_snapshot={"name": "Pechuga fresca"}, quantity=Decimal("1.250"),
            quantity_unit="KG", unit_price=Decimal("95"), discount_total=Decimal("5"),
            line_total=Decimal("113.75")) for _ in range(5)]


@pytest.mark.parametrize("size", [(1280, 720), (1366, 768), (1600, 900), (1920, 1080)])
@pytest.mark.parametrize("theme,density", [("light", "comfortable"), ("dark", "touch")])
def test_footer_visible_and_three_cart_rows_in_available_shell_area(app, size, theme, density):
    ThemeManager.instance().apply(app, theme, density=density)
    view = SalesPosWorkspace(presenter())
    # Reserve real estate for taskbar and shell/navigation above the module.
    view.resize(size[0] - 180, size[1] - 100)
    view.show()
    view.checkout.cart.set_lines(lines())
    app.processEvents()
    area = view.module_layout.viewport
    assert area.verticalScrollBar().maximum() == 0
    table = view.checkout.cart._table
    assert table.viewport().height() >= sum(table.rowHeight(i) for i in range(3))
    for button in (view.checkout.actions.btn_cobrar, view.checkout.actions.btn_suspender,
                   view.checkout.actions.btn_reanudar, view.checkout.actions.btn_cancelar):
        rect = button.rect()
        assert view.rect().contains(button.mapTo(view, rect.bottomRight()))
        assert button.isVisible()
    view.close()


def test_remove_discount_uses_selected_uuid_and_permission(app):
    view = SalesPosWorkspace(presenter())
    rows = lines()
    view.checkout.cart.set_lines(rows)
    view.checkout.cart.select_line(rows[3].id)
    seen = []
    view.checkout.cart.discount_remove_requested.connect(seen.append)
    view.checkout.cart._tools.aboutToShow.emit()
    assert view.checkout.cart.btn_remove_discount._menu_action.isEnabled()
    view.checkout.cart.btn_remove_discount._menu_action.trigger()
    assert seen == [rows[3].id]
    rows[3].discount_total = Decimal("0")
    view.checkout.cart.set_lines(rows)
    view.checkout.cart.select_line(rows[3].id)
    assert not view.checkout.cart.btn_remove_discount.isEnabled()
    view.close()


def test_product_card_keyboard_selection_does_not_move_grid(app):
    view = SalesPosWorkspace(presenter())
    grid = view.catalog._grid
    product = SimpleNamespace(product_id=new_uuid(), name="Pechuga", sku="P01", unit="KG",
             effective_price=Decimal("95"), available_quantity=Decimal("20"), priced=True,
             sellable=True, stock_state="AVAILABLE", warnings=(), image_reference=None)
    view.show()
    app.processEvents()
    grid.set_products([product])
    app.processEvents()
    card = grid._cards[0]
    seen = []
    grid.product_selected.connect(seen.append)
    before = card.geometry()
    QTest.keyClick(card, Qt.Key_Return)
    assert seen == [product]
    assert card.property("selected") is True
    assert card.geometry() == before
    view.close()


def test_scale_io_does_not_block_ui_or_deliver_after_stop(app):
    from threading import Event
    from PyQt5.QtCore import QTimer
    from backend.application.sales.scale_reading_service import ScaleReadingService
    from backend.domain.inventory.value_objects.catch_weight import WeightReading
    from frontend.desktop.modules.sales_pos.scale_monitor import ScaleMonitor
    release = Event()
    started = Event()
    class Gateway:
        def read(self):
            started.set()
            release.wait(2)
            return WeightReading(Decimal(".850"))
    service = ScaleReadingService(Gateway())
    monitor = ScaleMonitor(service)
    seen, responsive = [], []
    monitor.changed.connect(seen.append)
    monitor.start()
    worker = monitor._worker
    try:
        assert started.wait(1)
        QTimer.singleShot(0, lambda: responsive.append(True))
        QTest.qWait(20)
        assert responsive
        monitor.stop()
        count = len(seen)
        release.set()
        assert worker.wait(1000)
        app.processEvents()
        assert len(seen) == count
        assert service.current().status == "DISCONNECTED"
    finally:
        release.set()
        worker.wait(1000)
        monitor.stop()
