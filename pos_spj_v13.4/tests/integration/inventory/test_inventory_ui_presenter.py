"""INV-25 — InventoryPresenter over the real backend + Qt page smoke (offscreen)."""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.analytics import InventoryAnalyticsService
from backend.application.inventory.queries import (
    InventoryAvailabilityQueryService,
    ReplenishmentQueryService,
    WarehouseQueryService,
)
from backend.application.inventory.use_cases import (
    CreateLocationUseCase,
    CreateWarehouseUseCase,
    GenerateReplenishmentSuggestionsUseCase,
    PostInventoryMovementUseCase,
    SetReplenishmentRuleUseCase,
)
from backend.domain.inventory.enums import WarehouseType
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import MovementType
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from frontend.desktop.modules.inventory.presenter import InventoryPresenter


class _Session:
    user_id = "u1"
    branch_id = "b1"
    warehouse_id = "w1"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _seed(conn):
    SetReplenishmentRuleUseCase().execute(
        conn, product_id="p1", branch_id="b1", warehouse_id="w1",
        reorder_point=Decimal("10"), target_quantity=Decimal("30"), actor_user_id="u1")
    line = InventoryMovementLine.create(product_id="p1", quantity=Decimal("5"),
                                        to_location_id="loc1")
    mv = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
        source_module="procurement", source_document_type="GR", source_document_id="g1",
        operation_id="g1", created_by_user_id="u1", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")


def _presenter(conn):
    return InventoryPresenter(
        connection_provider=lambda: conn,
        availability_service_factory=InventoryAvailabilityQueryService,
        replenishment_query_factory=ReplenishmentQueryService,
        generate_suggestions_uc=GenerateReplenishmentSuggestionsUseCase(),
        warehouse_query_factory=WarehouseQueryService,
        analytics_factory=InventoryAnalyticsService,
        session_context=_Session())


class TestPresenter:
    def test_availability_view_model(self, conn):
        _seed(conn)
        vm = _presenter(conn).availability(product_ids=["p1"])
        assert vm.total == 1 and vm.rows[0][0] == "p1"
        assert vm.rows[0][3].startswith("5")  # available

    def test_generate_then_list_suggestions(self, conn):
        _seed(conn)
        pres = _presenter(conn)
        ok, _msg, data = pres.generate_suggestions()
        assert ok and data["count"] == 1
        vm = pres.open_suggestions()
        assert vm.total == 1 and vm.rows[0][3] == "Compra"  # source localized

    def test_replenishment_kpis(self, conn):
        _seed(conn)
        pres = _presenter(conn)
        pres.generate_suggestions()
        kpis = {k.key: k.value for k in pres.replenishment_kpis()}
        assert kpis["open"] == "1"

    def test_analytics_kpis_and_export(self, conn):
        _seed(conn)
        pres = _presenter(conn)
        kpis = {k.key: k.value for k in pres.inventory_kpis()}
        assert kpis["available"] == "5"
        charts = pres.analytics_charts()
        assert len(charts) == 4
        assert "product_id" in pres.export_availability_csv()
        assert pres.freshness().state in ("LIVE", "FRESH")

    def test_warehouses_and_location_tree(self, conn):
        wid = CreateWarehouseUseCase().execute(
            conn, code="WH1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        aisle = CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="A1", name="Pasillo", actor_user_id="u1").entity_id
        CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="A1-R1", name="Rack", actor_user_id="u1",
            parent_location_id=aisle, level=1)
        pres = _presenter(conn)
        assert pres.warehouses().rows[0][0] == "WH1"
        tree = pres.location_tree(warehouse_id=wid)
        assert tree.total == 2 and tree.rows[1][0].startswith("· ")


class TestPagesSmoke:
    def test_pages_build_and_refresh(self, conn):
        pytest.importorskip("PyQt5")
        from PyQt5.QtWidgets import QApplication
        # NOTE: InventoryAnalyticsPage is intentionally excluded — it builds
        # HtmlChartView (QtWebEngine), which hangs under headless offscreen. Its
        # data path is covered by test_analytics_kpis_and_export via the presenter.
        from frontend.desktop.modules.inventory.pages import (
            InventoryDashboardPage,
            LocationsPage,
            ReplenishmentPage,
            WarehousesPage,
        )
        _seed(conn)
        wid = CreateWarehouseUseCase().execute(
            conn, code="WH1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="A1", name="Pasillo", actor_user_id="u1")
        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        pres.generate_suggestions()
        dash = InventoryDashboardPage(pres, product_ids=["p1"])
        dash.refresh()
        assert dash._table.rowCount() == 1
        page = ReplenishmentPage(pres)
        page.refresh()
        assert page._table.rowCount() == 1
        wh_page = WarehousesPage(pres)
        wh_page.refresh()
        assert wh_page._table.rowCount() == 1
        loc_page = LocationsPage(pres, warehouse_id=wid)
        loc_page.refresh()
        assert loc_page._table.rowCount() == 1
        del app
