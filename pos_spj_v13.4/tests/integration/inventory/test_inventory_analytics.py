"""INV-24 — inventory BI: KPIs, charts, freshness, export (§55)."""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.dto.charts.chart_data import ChartState
from backend.application.inventory.analytics import InventoryAnalyticsService
from backend.application.inventory.use_cases import (
    PostInventoryMovementUseCase,
    RegisterWasteUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import MovementType, WasteType
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _receive(conn, product, qty, wh="w1", op=None):
    op = op or f"r-{product}-{wh}"
    line = InventoryMovementLine.create(product_id=product, quantity=Decimal(qty),
                                        to_location_id="loc1")
    mv = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id=wh,
        source_module="procurement", source_document_type="GR", source_document_id=op,
        operation_id=op, created_by_user_id="u1", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")


@pytest.fixture
def seeded(conn):
    _receive(conn, "p1", "10", wh="w1")
    _receive(conn, "p2", "4", wh="w2")
    RegisterWasteUseCase().execute(
        conn, product_id="p1", branch_id="b1", warehouse_id="w1",
        waste_type=WasteType.DAMAGE, quantity=Decimal("2"), operation_id="w1",
        actor_user_id="u1", location_id="loc1")
    return conn


class TestAnalytics:
    def test_kpis(self, seeded):
        kpis = {k.key: k.value for k in InventoryAnalyticsService(seeded).kpis(branch_id="b1")}
        # 10 - 2 waste + 4 = 12 available across warehouses
        assert kpis["available"] == "12"
        assert "reserved" in kpis and kpis["critical"] in ("0", "1", "2")

    def test_stock_by_status_chart_is_valid_donut(self, seeded):
        dto = InventoryAnalyticsService(seeded).stock_by_status_chart(branch_id="b1")
        assert dto.chart_type == "donut" and dto.state == ChartState.READY
        assert "AVAILABLE" in dto.categories and dto.series[0].data

    def test_stock_by_warehouse_chart(self, seeded):
        dto = InventoryAnalyticsService(seeded).stock_by_warehouse_chart(branch_id="b1")
        assert set(dto.categories) == {"w1", "w2"}

    def test_waste_chart(self, seeded):
        dto = InventoryAnalyticsService(seeded).waste_by_type_chart(branch_id="b1")
        assert "DAMAGE" in dto.categories and dto.series[0].semantic == "danger"

    def test_movements_chart(self, seeded):
        dto = InventoryAnalyticsService(seeded).movements_by_type_chart(branch_id="b1")
        assert "PURCHASE_RECEIPT" in dto.categories

    def test_empty_branch_yields_empty_chart(self, conn):
        dto = InventoryAnalyticsService(conn).stock_by_status_chart(branch_id="none")
        assert dto.state == ChartState.EMPTY and dto.is_empty()

    def test_freshness_live_after_recent_movement(self, seeded):
        fresh = InventoryAnalyticsService(seeded).freshness(branch_id="b1")
        assert fresh.state in ("LIVE", "FRESH") and fresh.last_source_event_at is not None

    def test_freshness_unknown_without_data(self, conn):
        assert InventoryAnalyticsService(conn).freshness(branch_id="b1").state == "UNKNOWN"

    def test_export_csv_has_header_and_rows(self, seeded):
        csv_text = InventoryAnalyticsService(seeded).export_availability_csv(branch_id="b1")
        lines = csv_text.strip().splitlines()
        assert lines[0].startswith("product_id,warehouse_id,inventory_status")
        assert any("p1" in ln for ln in lines[1:])
