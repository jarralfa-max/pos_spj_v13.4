"""P0-D — Integración con Productos.

Two capabilities that close real gaps found while auditing the module:

1. ``resolve_barcode`` — exact, deterministic resolution for scanner input
   (``product_options`` is fuzzy substring search, meant for typing/filtering,
   not for a barcode scan that must resolve unambiguously or not at all).
2. Product-name enrichment — six read tables (`availability`, `stock`,
   `quarantines`, `catch_weight`, `expiring`, `open_suggestions`) displayed
   the raw ``product_id`` UUID instead of the product's name. The presenter
   now bulk-resolves names via ``ProductQueryService.get_names()`` and the
   view models fall back to the id only if resolution fails — never a blank
   cell, never a crash, never worse than before.
"""

from __future__ import annotations

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.analytics import InventoryAnalyticsService
from backend.application.inventory.queries import (
    AdjustmentQueryService,
    AlertQueryService,
    AuditQueryService,
    ColdChainQueryService,
    CountQueryService,
    ExpiryQueryService,
    InventoryAvailabilityQueryService,
    LotQueryService,
    MovementQueryService,
    QuarantineQueryService,
    ReceiptQueryService,
    ReplenishmentQueryService,
    ReservationQueryService,
    SettingsQueryService,
    StockQueryService,
    TraceabilityQueryService,
    TransferQueryService,
    WarehouseQueryService,
    WeightQueryService,
)
from backend.application.inventory.use_cases import (
    DisposeQuarantineUseCase,
    GenerateReplenishmentSuggestionsUseCase,
    PostInventoryMovementUseCase,
    QuarantineStockUseCase,
    RegisterInventoryLotUseCase,
    ReleaseQuarantineUseCase,
    SetReplenishmentRuleUseCase,
)
from backend.application.queries.product_query_service import ProductQueryService
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import LotOrigin, MovementType, QuarantineReason
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
    c.executescript(
        """
        CREATE TABLE products (
            id TEXT PRIMARY KEY, name TEXT, code TEXT, category_id TEXT,
            base_unit_id TEXT, lifecycle_status TEXT DEFAULT 'ACTIVE',
            product_type TEXT
        );
        CREATE TABLE product_categories (id TEXT PRIMARY KEY, name TEXT);
        CREATE TABLE price_list (id TEXT PRIMARY KEY, code TEXT);
        CREATE TABLE product_price (
            product_id TEXT, branch_id TEXT, price_list_id TEXT, sale_price TEXT
        );
        CREATE TABLE product_barcodes (
            product_id TEXT, active INTEGER DEFAULT 1, barcode_value TEXT
        );
        """
    )
    c.execute(
        "INSERT INTO products (id, name, code, base_unit_id, lifecycle_status) "
        "VALUES ('p1', 'Pechuga de pollo', 'POLLO-001', 'kg', 'ACTIVE')")
    c.execute("INSERT INTO product_barcodes (product_id, active, barcode_value) "
               "VALUES ('p1', 1, '7501234567890')")
    c.commit()
    return c


def _presenter(conn, **overrides):
    kwargs = dict(
        connection_provider=lambda: conn,
        availability_service_factory=InventoryAvailabilityQueryService,
        replenishment_query_factory=ReplenishmentQueryService,
        generate_suggestions_uc=GenerateReplenishmentSuggestionsUseCase(),
        warehouse_query_factory=WarehouseQueryService,
        analytics_factory=InventoryAnalyticsService,
        lot_query_factory=LotQueryService,
        movement_query_factory=MovementQueryService,
        expiry_query_factory=ExpiryQueryService,
        traceability_query_factory=TraceabilityQueryService,
        stock_query_factory=StockQueryService,
        quarantine_query_factory=QuarantineQueryService,
        reservation_query_factory=ReservationQueryService,
        cold_chain_query_factory=ColdChainQueryService,
        audit_query_factory=AuditQueryService,
        transfer_query_factory=TransferQueryService,
        weight_query_factory=WeightQueryService,
        receipt_query_factory=ReceiptQueryService,
        count_query_factory=CountQueryService,
        adjustment_query_factory=AdjustmentQueryService,
        alert_query_factory=AlertQueryService,
        settings_query_factory=SettingsQueryService,
        release_quarantine_uc=ReleaseQuarantineUseCase(),
        dispose_quarantine_uc=DisposeQuarantineUseCase(),
        open_quarantine_uc=QuarantineStockUseCase(),
        product_query_factory=ProductQueryService.from_connection,
        session_context=_Session(),
    )
    kwargs.update(overrides)
    return InventoryPresenter(**kwargs)


def _receive_stock(conn, *, quantity=Decimal("5"), weight=0, lot_id=None,
                   location_id="loc1", operation_id="g1"):
    line = InventoryMovementLine.create(
        product_id="p1", quantity=quantity, weight=weight, lot_id=lot_id,
        to_location_id=location_id)
    mv = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
        source_module="procurement", source_document_type="GR", source_document_id="g1",
        operation_id=operation_id, created_by_user_id="u1", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")


class TestResolveBarcode:
    def test_resolves_exact_barcode_to_product(self, conn):
        option = _presenter(conn).resolve_barcode("7501234567890")
        assert option is not None
        assert option.id == "p1"
        assert option.label == "Pechuga de pollo"

    def test_unknown_barcode_returns_none(self, conn):
        assert _presenter(conn).resolve_barcode("0000000000000") is None

    def test_blank_barcode_returns_none_without_calling_backend(self, conn):
        assert _presenter(conn).resolve_barcode("") is None

    def test_returns_none_when_not_wired(self, conn):
        pres = _presenter(conn, product_query_factory=None)
        assert pres.resolve_barcode("7501234567890") is None

    def test_inactive_barcode_does_not_resolve(self, conn):
        conn.execute("UPDATE product_barcodes SET active=0 WHERE barcode_value=?",
                     ("7501234567890",))
        conn.commit()
        assert _presenter(conn).resolve_barcode("7501234567890") is None


class TestProductQueryServiceGetNames:
    """Unit-level: the batch lookup itself, independent of the presenter."""

    def test_get_names_resolves_known_ids(self, conn):
        svc = ProductQueryService.from_connection(conn)
        assert svc.get_names(["p1"]) == {"p1": "Pechuga de pollo"}

    def test_get_names_skips_unknown_ids(self, conn):
        svc = ProductQueryService.from_connection(conn)
        assert svc.get_names(["p1", "does-not-exist"]) == {"p1": "Pechuga de pollo"}

    def test_get_names_empty_input_returns_empty(self, conn):
        svc = ProductQueryService.from_connection(conn)
        assert svc.get_names([]) == {}

    def test_resolve_barcode_unknown_returns_none(self, conn):
        svc = ProductQueryService.from_connection(conn)
        assert svc.resolve_barcode("does-not-exist") is None


class TestProductNamesInTables:
    """§P0-D item 3: every table keyed by product_id shows the resolved
    name, falling back to the id only if resolution genuinely fails."""

    def test_availability_shows_product_name(self, conn):
        _receive_stock(conn)
        vm = _presenter(conn).availability(product_ids=["p1"])
        assert vm.rows[0][0] == "Pechuga de pollo"

    def test_availability_falls_back_to_id_without_product_factory(self, conn):
        _receive_stock(conn)
        pres = _presenter(conn, product_query_factory=None)
        vm = pres.availability(product_ids=["p1"])
        assert vm.rows[0][0] == "p1"

    def test_availability_falls_back_to_id_for_unknown_product(self, conn):
        pres = _presenter(conn)
        vm = pres.availability(product_ids=["ghost-id"])
        assert vm.rows[0][0] == "ghost-id"

    def test_stock_shows_product_name(self, conn):
        _receive_stock(conn)
        vm = _presenter(conn).stock()
        assert vm.total == 1
        assert vm.rows[0][0] == "Pechuga de pollo"

    def test_catch_weight_shows_product_name(self, conn):
        _receive_stock(conn, weight=Decimal("2.5"))
        vm = _presenter(conn).catch_weight()
        assert vm.total == 1
        assert vm.rows[0][0] == "Pechuga de pollo"

    def test_quarantines_shows_product_name_and_lot_code(self, conn):
        lot_id = RegisterInventoryLotUseCase().execute(
            conn, product_id="p1", lot_code="L-1", origin_type=LotOrigin.PURCHASE,
            operation_id="lot-1", actor_user_id="u1", branch_id="b1").entity_id
        _receive_stock(conn, lot_id=lot_id, location_id="w1")
        result = QuarantineStockUseCase().execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            reason=QuarantineReason.QUALITY_FAILURE, quantity=Decimal("1"),
            operation_id="q-1", actor_user_id="u1", location_id="w1", lot_id=lot_id)
        assert result.success, result.message
        vm = _presenter(conn).quarantines()
        assert vm.total == 1
        assert vm.rows[0][0] == "Pechuga de pollo"
        assert vm.rows[0][1] == "L-1"  # lot_code resuelto, no el UUID del lote

    def test_expiring_shows_product_name(self, conn):
        from datetime import date, timedelta
        lot_id = RegisterInventoryLotUseCase().execute(
            conn, product_id="p1", lot_code="L-2", origin_type=LotOrigin.PURCHASE,
            operation_id="lot-2", actor_user_id="u1", branch_id="b1",
            expiration_date=(date.today() + timedelta(days=1)).isoformat()).entity_id
        _receive_stock(conn, lot_id=lot_id, location_id="loc1")
        vm = _presenter(conn).expiring()
        assert vm.total == 1
        assert vm.rows[0][0] == "Pechuga de pollo"

    def test_open_suggestions_shows_product_name(self, conn):
        SetReplenishmentRuleUseCase().execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            reorder_point=Decimal("10"), target_quantity=Decimal("30"),
            actor_user_id="u1")
        _receive_stock(conn, quantity=Decimal("2"))  # bajo el punto de reorden
        pres = _presenter(conn)
        pres.generate_suggestions()
        vm = pres.open_suggestions()
        assert vm.total == 1
        assert vm.rows[0][0] == "Pechuga de pollo"
