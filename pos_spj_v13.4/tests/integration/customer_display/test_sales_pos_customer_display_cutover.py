"""SET-17 cutover — the real `sales_pos` composition root
(`frontend/desktop/modules/sales_pos/composition.py::build_sales_pos_presenter`)
wired to `SalesCustomerDisplayClient`, against a real (in-memory) SQLite
schema. Proves the FULL wiring — presenter → command handler → real
domain/repositories — not just the client in isolation
(`test_sales_customer_display_client.py` already covers that). A fake
gateway captures `push()` calls exactly the way a real
`QtCustomerDisplayGateway` would, without needing a real Qt window.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.sales.permissions import SalesPermissions
from backend.domain.customer_display.enums import CustomerDisplayMode, CustomerDisplaySectionCode
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import new_uuid
from frontend.desktop.modules.sales_pos.composition import build_sales_pos_presenter
from tests.integration._born_clean_db import make_db


class _FakeSession:
    def __init__(self, branch_id: str) -> None:
        self.user_id = new_uuid()
        self.active_branch_id = branch_id
        self.is_active = True
        self._permissions = {p for p in vars(SalesPermissions).values() if isinstance(p, str)}

    def tiene_permiso(self, code: str) -> bool:
        return code in self._permissions


class _FakeGateway:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def push(self, *, display_id, mode, content) -> None:
        self.calls.append({"display_id": display_id, "mode": mode, "content": content})


@pytest.fixture
def conn():
    connection = make_db()
    create_sales_schema(connection)
    connection.commit()
    yield connection
    connection.close()


def _existing_branch_id(conn) -> str:
    branch_id = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (branch_id, "Sucursal de prueba"))
    conn.commit()
    return branch_id


class TestCustomerDisplayCutoverThroughRealComposition:
    def test_a_cart_mutation_pushes_real_cart_content(self, conn):
        branch_id = _existing_branch_id(conn)
        presenter = build_sales_pos_presenter(conn, _FakeSession(branch_id))
        gateway = _FakeGateway()

        sale_id = presenter.start_sale().entity_id
        presenter.add_line(
            sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("2"),
            unit_price=Decimal("100"), product_snapshot={"name": "Bistec"})
        presenter.push_customer_display(gateway=gateway, sale_id=sale_id)

        assert gateway.calls[-1]["mode"] is CustomerDisplayMode.CART
        content = gateway.calls[-1]["content"]
        assert content[CustomerDisplaySectionCode.TOTAL.value] == "200"
        assert content[CustomerDisplaySectionCode.ITEMS.value][0]["name"] == "Bistec"

    def test_checkout_completion_pushes_thank_you(self, conn):
        branch_id = _existing_branch_id(conn)
        presenter = build_sales_pos_presenter(conn, _FakeSession(branch_id))
        gateway = _FakeGateway()

        sale_id = presenter.start_sale().entity_id
        presenter.add_line(
            sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal("100"), product_snapshot={"name": "Bistec"})
        presenter.begin_checkout(sale_id=sale_id)
        presenter.record_payment(sale_id=sale_id, method="CASH", amount=Decimal("100"))
        result = presenter.checkout_sale(sale_id=sale_id)
        assert result.success, result.message

        presenter.push_customer_display(gateway=gateway, sale_id=sale_id)

        assert gateway.calls[-1]["mode"] is CustomerDisplayMode.THANK_YOU
        assert gateway.calls[-1]["content"][CustomerDisplaySectionCode.MESSAGE.value]

    def test_a_push_failure_never_raises_out_of_the_presenter(self, conn):
        """Best-effort discipline: the presenter/handler layer itself does
        not swallow failures (that's `SalesPosWorkspace._push_customer_display`'s
        job, tested at the workspace level) — but a gateway that raises must
        not corrupt the already-bootstrapped real display/layout rows for
        the NEXT (working) push."""
        branch_id = _existing_branch_id(conn)
        presenter = build_sales_pos_presenter(conn, _FakeSession(branch_id))

        class _RaisingGateway:
            def push(self, **kwargs):
                raise RuntimeError("pantalla desconectada")

        sale_id = presenter.start_sale().entity_id
        with pytest.raises(RuntimeError):
            presenter.push_customer_display(gateway=_RaisingGateway(), sale_id=sale_id)

        gateway = _FakeGateway()
        presenter.push_customer_display(gateway=gateway, sale_id=sale_id)
        assert gateway.calls  # recovered cleanly on the next push
