"""POS-22 prerequisite verification — proves the exact call sequence
`frontend/desktop/modules/sales_pos/dialogs/payment_dialog.py::PaymentDialog`
performs (`begin_checkout` → `record_payment`(s) → `checkout_sale`) actually
succeeds against the REAL wiring `composition.py::build_sales_pos_presenter`
produces, not just against hand-called use cases (already covered by
`tests/unit/test_sales_checkout.py`). Before this dialog existed, nothing in
`sales_pos/` ever called `record_payment`/`begin_checkout` — "Cobrar" always
failed `SalePaymentPolicy.ensure_fully_paid` with zero payments recorded.
`create_sales_pos_view` is also exercised once here to prove
`modulos/ventas_pos.py::ModuloVentasPos` — now wired into
`interfaz/main_window.py` in place of the retired `modulos/ventas.py` — can
actually build a real widget against a real connection, headless.
"""

from __future__ import annotations

import os
import sqlite3
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from backend.application.sales.permissions import SalesPermissions
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import new_uuid
from frontend.desktop.modules.sales_pos.composition import build_sales_pos_presenter, create_sales_pos_view


class _FakeSession:
    def __init__(self, permissions):
        self.user_id = new_uuid()
        self.active_branch_id = new_uuid()
        self.is_active = True
        self._permissions = set(permissions)

    def tiene_permiso(self, code: str) -> bool:
        return code in self._permissions


def _all_permissions_session() -> _FakeSession:
    return _FakeSession({v for v in vars(SalesPermissions).values() if isinstance(v, str)})


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    # CatalogPanel.load_categories() (SALES-7/19) is called from
    # `SalesPosWorkspace.__init__` unconditionally — the widget-construction
    # test below needs these tables even though the payment-flow tests don't
    # touch the catalog at all.
    create_products_schema(c)
    create_pricing_schema(c)
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


class TestPresenterCheckoutFlow:
    """Exactly the sequence `PaymentDialog._confirm` performs."""

    def test_single_cash_payment_completes_the_sale(self, conn):
        session = _all_permissions_session()
        presenter = build_sales_pos_presenter(conn, session_context=session)

        start = presenter.start_sale()
        assert start.success, start.message
        sale_id = start.entity_id

        add = presenter.add_line(
            sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal("150.00"), product_snapshot={"name": "Producto"})
        assert add.success, add.message

        checkout_begin = presenter.begin_checkout(sale_id=sale_id)
        assert checkout_begin.success, checkout_begin.message

        payment = presenter.record_payment(sale_id=sale_id, method="CASH", amount=Decimal("150.00"))
        assert payment.success, payment.message

        checkout = presenter.checkout_sale(sale_id=sale_id)
        assert checkout.success, checkout.message

        sale = presenter.get_sale(sale_id)
        assert sale.status == "COMPLETED"
        assert sale.total_paid == Decimal("150.00")

    def test_mixed_payment_two_methods_completes_the_sale(self, conn):
        """No dedicated "Mixed" method exists — recording two different
        methods is what makes `Sale.is_mixed_payment` true, exactly what
        `PaymentDialog` relies on by letting the cashier add two lines."""
        session = _all_permissions_session()
        presenter = build_sales_pos_presenter(conn, session_context=session)

        sale_id = presenter.start_sale().entity_id
        presenter.add_line(
            sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal("200.00"), product_snapshot={"name": "Producto"})
        presenter.begin_checkout(sale_id=sale_id)

        first = presenter.record_payment(sale_id=sale_id, method="CASH", amount=Decimal("120.00"))
        assert first.success, first.message
        second = presenter.record_payment(sale_id=sale_id, method="CARD", amount=Decimal("80.00"),
                                           reference="AUTH123")
        assert second.success, second.message

        checkout = presenter.checkout_sale(sale_id=sale_id)
        assert checkout.success, checkout.message

        sale = presenter.get_sale(sale_id)
        assert sale.status == "COMPLETED"
        assert sale.is_mixed_payment is True

    def test_checkout_fails_cleanly_with_no_payment_recorded(self, conn):
        """The exact failure this whole phase exists to prevent from ever
        reaching a real cashier silently: clicking Cobrar with nothing
        recorded must fail with a real, readable error, not a crash."""
        session = _all_permissions_session()
        presenter = build_sales_pos_presenter(conn, session_context=session)

        sale_id = presenter.start_sale().entity_id
        presenter.add_line(
            sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal("50.00"), product_snapshot={"name": "Producto"})
        presenter.begin_checkout(sale_id=sale_id)

        checkout = presenter.checkout_sale(sale_id=sale_id)
        assert checkout.success is False
        assert checkout.error_code == "PAYMENT_INCOMPLETE"


class TestModuloVentasPosRealConstruction:
    def test_builds_a_real_widget_against_a_real_connection(self, conn):
        QtWidgets = pytest.importorskip(
            "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        session = _all_permissions_session()

        widget = create_sales_pos_view(conn, session_context=session, printer_service=None)
        app.processEvents()
        try:
            assert widget.isVisible() is False  # not shown, but constructed without error
            assert widget._sale_id is None  # no sale started until the widget is actually shown
        finally:
            widget.close()

    def test_construction_does_not_crash_before_login(self, conn):
        """Real regression: `interfaz/main_window.py::_conectar` constructs
        every module screen eagerly at app startup, BEFORE any user is
        authenticated (`session_context.user_id` empty). The original
        POS-22 wiring called `_start_new_sale()` from `__init__`, which
        reached `SalesPosPresenter.count_suspended()` → `SalesAuthorizationPolicy.
        require()` with an empty `requester_user_id` — that raises
        `SalesPermissionDeniedError` instead of degrading, crashing the
        whole module load in the real app (`Error cargando módulo POS`)."""
        QtWidgets = pytest.importorskip(
            "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        unauthenticated_session = _FakeSession(permissions=())
        unauthenticated_session.user_id = ""

        widget = create_sales_pos_view(conn, session_context=unauthenticated_session, printer_service=None)
        app.processEvents()
        try:
            assert widget._sale_id is None
        finally:
            widget.close()

    def test_showing_the_widget_after_login_starts_a_real_sale(self, conn):
        QtWidgets = pytest.importorskip(
            "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        session = _all_permissions_session()

        widget = create_sales_pos_view(conn, session_context=session, printer_service=None)
        widget.show()
        app.processEvents()
        try:
            assert widget._sale_id is not None
        finally:
            widget.close()
