"""SET-17 cutover — `SalesCustomerDisplayClient` against a real (in-memory)
SQLite schema combining Sales with the born-clean Customer Display schema
(migration 217). Confirms: lazy bootstrap of a `CustomerDisplay` and a
default `DisplayLayout` per mode on first use; reuse (no duplicate rows)
on subsequent calls; content is filtered to only enabled sections; `LOGO`
never appears (disabled by default — no real logo-asset infrastructure
exists); `current_mode` persists after a push; an IDLE push (no sale)
still resolves/bootstraps correctly. Also covers the real FK constraint
found while writing these tests: `customer_displays.workstation_id`
REFERENCES `workstations(id)` — an orphan UUID is never accepted, so
bootstrapping requires a real `branch_id` to create a real `Workstation`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.sales.authorization import AllowAllSalesPermissionCheckerForTests, SalesAuthorizationPolicy
from backend.application.sales.dto import CustomerDisplayLineDTO, CustomerDisplayStateDTO
from backend.application.sales.use_cases.cart_use_cases import AddSaleLineUseCase, StartSaleUseCase
from backend.domain.customer_display.enums import CustomerDisplayMode, CustomerDisplaySectionCode
from backend.domain.settings.entities.workstation import Workstation
from backend.domain.settings.enums import WorkstationType
from backend.infrastructure.db.repositories.customer_display.customer_display_repository import (
    SqliteCustomerDisplayRepository,
)
from backend.infrastructure.db.repositories.customer_display.display_layout_repository import (
    SqliteDisplayLayoutRepository,
)
from backend.infrastructure.db.repositories.settings.workstation_repository import SqliteWorkstationRepository
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.infrastructure.integrations.sales_customer_display_client import (
    CustomerDisplayBootstrapError,
    SalesCustomerDisplayClient,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


def _allow_all() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


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


def _cart_state(sale_id="sale-1") -> CustomerDisplayStateDTO:
    return CustomerDisplayStateDTO(
        sale_id=sale_id, screen="CART", customer_name="Juan Pérez",
        lines=(CustomerDisplayLineDTO(name="Bistec", quantity=Decimal("2"),
                                       unit_price=Decimal("100"), line_total=Decimal("200")),),
        subtotal=Decimal("200"), discount_total=Decimal("0"), total=Decimal("200"), message="",
    )


class TestBootstrap:
    def test_first_push_bootstraps_a_display_and_a_layout(self, conn):
        branch_id = _existing_branch_id(conn)
        client = SalesCustomerDisplayClient(conn)
        gateway = _FakeGateway()

        client.push_sale_state(gateway, state=_cart_state(), branch_id=branch_id)

        displays = SqliteCustomerDisplayRepository(conn).list_active()
        assert len(displays) == 1
        layout = SqliteDisplayLayoutRepository(conn).get_active_for_mode(CustomerDisplayMode.CART)
        assert layout is not None

    def test_second_push_reuses_the_bootstrapped_display_no_duplicates(self, conn):
        branch_id = _existing_branch_id(conn)
        client = SalesCustomerDisplayClient(conn)
        gateway = _FakeGateway()

        client.push_sale_state(gateway, state=_cart_state(), branch_id=branch_id)
        client.push_sale_state(gateway, state=_cart_state(), branch_id=branch_id)

        assert len(SqliteCustomerDisplayRepository(conn).list_active()) == 1
        assert len(SqliteWorkstationRepository(conn).list_active()) == 1

    def test_display_links_to_the_first_active_workstation_if_one_exists(self, conn):
        branch_id = _existing_branch_id(conn)
        workstation = Workstation.create(
            branch_id=branch_id, code="POS-01", name="Caja 1", workstation_type=WorkstationType.POS)
        SqliteWorkstationRepository(conn).save(workstation)
        conn.commit()

        client = SalesCustomerDisplayClient(conn)
        client.push_sale_state(_FakeGateway(), state=_cart_state(), branch_id=branch_id)

        display = SqliteCustomerDisplayRepository(conn).list_active()[0]
        assert display.workstation_id == workstation.id
        # the existing workstation was reused, no second one created
        assert len(SqliteWorkstationRepository(conn).list_active()) == 1

    def test_bootstraps_a_real_workstation_against_the_given_branch_when_none_exists(self, conn):
        branch_id = _existing_branch_id(conn)
        client = SalesCustomerDisplayClient(conn)

        client.push_sale_state(_FakeGateway(), state=_cart_state(), branch_id=branch_id)

        workstations = SqliteWorkstationRepository(conn).list_active()
        assert len(workstations) == 1
        assert workstations[0].branch_id == branch_id
        display = SqliteCustomerDisplayRepository(conn).list_active()[0]
        assert display.workstation_id == workstations[0].id

    def test_raises_a_clear_error_instead_of_an_orphan_fk_insert_when_no_branch_given(self, conn):
        client = SalesCustomerDisplayClient(conn)

        with pytest.raises(CustomerDisplayBootstrapError):
            client.push_sale_state(_FakeGateway(), state=_cart_state(), branch_id=None)


class TestContentFiltering:
    def test_content_contains_only_default_enabled_sections(self, conn):
        branch_id = _existing_branch_id(conn)
        client = SalesCustomerDisplayClient(conn)
        gateway = _FakeGateway()

        client.push_sale_state(gateway, state=_cart_state(), branch_id=branch_id)

        content = gateway.calls[0]["content"]
        assert CustomerDisplaySectionCode.LOGO.value not in content
        assert content[CustomerDisplaySectionCode.CUSTOMER_NAME.value] == "Juan Pérez"
        assert content[CustomerDisplaySectionCode.TOTAL.value] == "200"

    def test_logo_never_appears_no_real_asset_infrastructure(self, conn):
        branch_id = _existing_branch_id(conn)
        client = SalesCustomerDisplayClient(conn)
        gateway = _FakeGateway()

        client.push_sale_state(gateway, state=_cart_state(), branch_id=branch_id)
        client.push_sale_state(gateway, state=_cart_state(), branch_id=branch_id)

        for call in gateway.calls:
            assert CustomerDisplaySectionCode.LOGO.value not in call["content"]

    def test_idle_push_with_no_state_sends_empty_content(self, conn):
        branch_id = _existing_branch_id(conn)
        client = SalesCustomerDisplayClient(conn)
        gateway = _FakeGateway()

        client.push_sale_state(gateway, state=None, branch_id=branch_id)

        assert gateway.calls[0]["mode"] is CustomerDisplayMode.IDLE
        assert gateway.calls[0]["content"] == {}


class TestModePersistence:
    def test_current_mode_persists_after_push(self, conn):
        branch_id = _existing_branch_id(conn)
        client = SalesCustomerDisplayClient(conn)
        client.push_sale_state(_FakeGateway(), state=_cart_state(), branch_id=branch_id)

        display = SqliteCustomerDisplayRepository(conn).list_active()[0]
        assert display.current_mode is CustomerDisplayMode.CART

    def test_mode_transitions_to_thank_you_on_a_new_push(self, conn):
        branch_id = _existing_branch_id(conn)
        client = SalesCustomerDisplayClient(conn)
        client.push_sale_state(_FakeGateway(), state=_cart_state(), branch_id=branch_id)

        thank_you_state = CustomerDisplayStateDTO(
            sale_id="sale-1", screen="THANK_YOU", customer_name="Juan Pérez", lines=(),
            subtotal=Decimal("200"), discount_total=Decimal("0"), total=Decimal("200"),
            message="¡Gracias por su compra!",
        )
        client.push_sale_state(_FakeGateway(), state=thank_you_state, branch_id=branch_id)

        display = SqliteCustomerDisplayRepository(conn).list_active()[0]
        assert display.current_mode is CustomerDisplayMode.THANK_YOU
        layout = SqliteDisplayLayoutRepository(conn).get_active_for_mode(CustomerDisplayMode.THANK_YOU)
        assert layout is not None


class TestRealSaleIntegration:
    def test_pushes_real_cart_state_from_a_live_sale(self, conn):
        from backend.application.sales.queries.customer_display_query_service import (
            CustomerDisplayQueryService,
        )

        branch_id = _existing_branch_id(conn)
        cashier = new_uuid()
        sale_id = StartSaleUseCase(_allow_all()).execute(
            conn, branch_id=branch_id, cashier_user_id=cashier,
            operation_id=new_uuid(), actor_user_id=cashier).entity_id
        AddSaleLineUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("2"),
            unit_price=Decimal("100"), actor_user_id=cashier, operation_id=new_uuid(),
            product_snapshot={"name": "Bistec"})

        state = CustomerDisplayQueryService(conn, _allow_all()).current_state(
            sale_id, requester_user_id=cashier)
        client = SalesCustomerDisplayClient(conn)
        gateway = _FakeGateway()

        client.push_sale_state(gateway, state=state, branch_id=branch_id)

        content = gateway.calls[0]["content"]
        assert content[CustomerDisplaySectionCode.TOTAL.value] == "200"
        assert content[CustomerDisplaySectionCode.ITEMS.value][0]["name"] == "Bistec"
