"""P0-D pilot — canonical product search wired into "Nueva cuarentena".

InventoryPresenter.product_options() delegates to ProductQueryService (the
same canonical search used elsewhere in the app), never a hand-typed UUID
(§P0-04). open_quarantine() is the first Inventario "create" command wired
through it, completing the Cuarentena page's open→release/dispose cycle
started in the P0-B slice.
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
    CreateLocationUseCase,
    CreateWarehouseUseCase,
    DisposeQuarantineUseCase,
    GenerateReplenishmentSuggestionsUseCase,
    PostInventoryMovementUseCase,
    QuarantineStockUseCase,
    ReleaseQuarantineUseCase,
    SetReplenishmentRuleUseCase,
)
from backend.application.queries.product_query_service import ProductQueryService
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import MovementType, WarehouseType
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
    c.commit()
    return c


def _seed_stock(conn):
    # to_location_id="w1": without an explicit location_id, open_quarantine()
    # leaves QuarantineStockUseCase to default location_id to warehouse_id —
    # stock must live there for the status transfer to find an available
    # balance. A real location selector was added in the Cuarentena P0-C
    # follow-up (see TestOpenQuarantineWithRealLocation below).
    line = InventoryMovementLine.create(product_id="p1", quantity=Decimal("10"),
                                        to_location_id="w1")
    mv = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
        source_module="procurement", source_document_type="GR", source_document_id="g1",
        operation_id="g1", created_by_user_id="u1", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")


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


class TestProductOptions:
    def test_finds_product_by_name(self, conn):
        options = _presenter(conn).product_options("pollo")
        assert len(options) == 1
        assert options[0].id == "p1"
        assert options[0].label == "Pechuga de pollo"

    def test_finds_product_by_code(self, conn):
        options = _presenter(conn).product_options("POLLO-001")
        assert len(options) == 1 and options[0].id == "p1"

    def test_no_match_returns_empty(self, conn):
        assert _presenter(conn).product_options("inexistente") == []

    def test_returns_empty_when_not_wired(self, conn):
        pres = _presenter(conn, product_query_factory=None)
        assert pres.product_options("pollo") == []


class TestOpenQuarantine:
    def test_open_quarantine_creates_visible_open_quarantine(self, conn):
        _seed_stock(conn)
        pres = _presenter(conn)
        ok, message, data = pres.open_quarantine(
            product_id="p1", reason="QUALITY_FAILURE", quantity=Decimal("2"),
            reason_note="Olor extraño")
        assert ok, message
        vm = pres.quarantines()
        assert vm.total == 1
        assert vm.rows[0][0] == "Pechuga de pollo"  # nombre resuelto, no el UUID

    def test_open_quarantine_uses_session_branch_and_warehouse(self, conn):
        _seed_stock(conn)
        pres = _presenter(conn)
        ok, _, data = pres.open_quarantine(
            product_id="p1", reason="QUALITY_FAILURE", quantity=Decimal("1"))
        assert ok
        # sin branch/warehouse explícitos, usó default_branch()/default_warehouse()
        # de la sesión (b1/w1) — nunca fabricados.
        row = conn.execute(
            "SELECT branch_id, warehouse_id FROM inventory_quarantine WHERE id=?",
            (data["entity_id"],)).fetchone()
        assert row["branch_id"] == "b1" and row["warehouse_id"] == "w1"

    def test_open_quarantine_without_product_fails_without_calling_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.open_quarantine(
            product_id="", reason="QUALITY_FAILURE", quantity=Decimal("1"))
        assert not ok
        assert "producto" in message.lower()

    def test_open_quarantine_invalid_reason_fails(self, conn):
        _seed_stock(conn)
        pres = _presenter(conn)
        ok, message, _ = pres.open_quarantine(
            product_id="p1", reason="NOT_A_REAL_REASON", quantity=Decimal("1"))
        assert not ok
        assert "motivo" in message.lower()

    def test_open_quarantine_unavailable_when_not_wired(self, conn):
        pres = _presenter(conn, open_quarantine_uc=None)
        ok, message, _ = pres.open_quarantine(
            product_id="p1", reason="QUALITY_FAILURE", quantity=Decimal("1"))
        assert not ok
        assert "no disponible" in message


class TestLocationOptions:
    """P0-C (Cuarentena) follow-up: a real, bounded location picker — the
    audit's §P0-04 principle ('the user shouldn't have to know or type
    UUIDs') applies just as much to locations as to products."""

    def _provisioned_warehouse(self, conn):
        wid = CreateWarehouseUseCase().execute(
            conn, code="WH1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        lid = CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="A1", name="Anaquel 1",
            actor_user_id="u1").entity_id
        return wid, lid

    def test_lists_active_locations_of_the_warehouse(self, conn):
        wid, lid = self._provisioned_warehouse(conn)
        # §20: CreateWarehouseUseCase también aprovisiona las ubicaciones
        # técnicas (TECH:*) del almacén — el picker las lista igual (son
        # ubicaciones activas reales), la manual "A1" debe estar entre ellas.
        options = _presenter(conn).location_options(warehouse_id=wid)
        manual = [o for o in options if o.id == lid]
        assert len(manual) == 1
        assert "A1" in manual[0].label

    def test_defaults_to_session_warehouse_when_not_given(self, conn):
        # La sesión de prueba usa warehouse_id="w1" — sin almacén provisto,
        # ninguna ubicación real existe ahí (es un id fabricado de prueba).
        assert _presenter(conn).location_options() == []

    def test_empty_without_warehouse_factory(self, conn):
        pres = _presenter(conn, warehouse_query_factory=None)
        wid, _ = self._provisioned_warehouse(conn)
        assert pres.location_options(warehouse_id=wid) == []

    def test_has_no_manual_locations_when_none_were_created(self, conn):
        # §20: el almacén siempre trae sus ubicaciones técnicas (TECH:*)
        # auto-aprovisionadas — "sin ubicaciones" ahora significa "sin
        # ninguna manual", no una lista vacía.
        wid = CreateWarehouseUseCase().execute(
            conn, code="WH2", name="Vacío", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        options = _presenter(conn).location_options(warehouse_id=wid)
        assert all(o.label.startswith("TECH:") for o in options)


class TestOpenQuarantineWithRealLocation:
    """Demuestra el cierre de la limitación documentada en la slice 3: con
    un ``location_id`` real, la cuarentena encuentra el saldo donde vive de
    verdad, no sólo cuando coincide por casualidad con el almacén completo."""

    def _stock_at_real_location(self, conn):
        wid = CreateWarehouseUseCase().execute(
            conn, code="WH1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        lid = CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="A1", name="Anaquel 1",
            actor_user_id="u1").entity_id
        line = InventoryMovementLine.create(product_id="p1", quantity=Decimal("10"),
                                            to_location_id=lid)
        mv = InventoryMovement.create(
            movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id=wid,
            source_module="procurement", source_document_type="GR", source_document_id="g1",
            operation_id="g1", created_by_user_id="u1", lines=[line])
        PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")
        return wid, lid

    def test_without_location_id_fails_when_stock_lives_elsewhere(self, conn):
        wid, _lid = self._stock_at_real_location(conn)
        pres = _presenter(conn)
        ok, message, _ = pres.open_quarantine(
            product_id="p1", reason="QUALITY_FAILURE", quantity=Decimal("2"),
            warehouse_id=wid)  # sin location_id: cae al almacén completo, no ahí
        assert not ok
        assert "negativo" in message.lower()

    def test_with_location_id_finds_the_real_balance(self, conn):
        wid, lid = self._stock_at_real_location(conn)
        pres = _presenter(conn)
        ok, message, _ = pres.open_quarantine(
            product_id="p1", reason="QUALITY_FAILURE", quantity=Decimal("2"),
            warehouse_id=wid, location_id=lid)
        assert ok, message
        assert pres.quarantines().total == 1


class TestQuarantinePageOpenAction:
    def test_page_open_dialog_creates_quarantine_and_refreshes(self, conn):
        pytest.importorskip("PyQt5")
        from decimal import Decimal as D
        from unittest.mock import patch

        from PyQt5.QtWidgets import QApplication, QDialog

        from frontend.desktop.modules.inventory.pages import QuarantinePage

        _seed_stock(conn)
        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = QuarantinePage(pres)
        page.refresh()
        assert page._table.rowCount() == 0

        def _fake_exec(self):
            self.product.set_selected_label("p1", "Pechuga de pollo")
            self.quantity.set_decimal(D("3"))
            return QDialog.Accepted

        with patch("frontend.desktop.modules.inventory.dialogs.OpenQuarantineDialog.exec_",
                   _fake_exec, create=True), \
             patch("frontend.desktop.modules.inventory.pages.quarantine_page"
                   ".QMessageBox.information") as info_mock, \
             patch("frontend.desktop.modules.inventory.pages.quarantine_page"
                   ".QMessageBox.warning") as warn_mock:
            page._on_open()

        assert not warn_mock.called, "open_quarantine failed: revisar seed/ubicación"
        assert info_mock.called
        assert page._table.rowCount() == 1
        assert pres.quarantines().total == 1

    def test_page_open_dialog_lists_real_locations_and_uses_the_selected_one(self, conn):
        """P0-C (Cuarentena) follow-up: eligiendo una ubicación real del
        combo, la cuarentena encuentra el saldo aunque no viva en el
        almacén completo (el caso que la slice 3 dejó documentado como
        limitación explícita)."""
        pytest.importorskip("PyQt5")
        from decimal import Decimal as D
        from unittest.mock import patch

        from PyQt5.QtWidgets import QApplication, QDialog

        from frontend.desktop.modules.inventory.pages import QuarantinePage

        wid = CreateWarehouseUseCase().execute(
            conn, code="WH1", name="Central", branch_id="b1",
            warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1").entity_id
        lid = CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="A1", name="Anaquel 1",
            actor_user_id="u1").entity_id
        line = InventoryMovementLine.create(product_id="p1", quantity=Decimal("10"),
                                            to_location_id=lid)
        mv = InventoryMovement.create(
            movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id=wid,
            source_module="procurement", source_document_type="GR", source_document_id="g1",
            operation_id="g1", created_by_user_id="u1", lines=[line])
        PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")

        class _RealWarehouseSession:
            user_id = "u1"
            branch_id = "b1"
            warehouse_id = wid

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn, session_context=_RealWarehouseSession())
        page = QuarantinePage(pres)
        page.refresh()

        def _fake_exec(self):
            self.product.set_selected_label("p1", "Pechuga de pollo")
            self.quantity.set_decimal(D("3"))
            idx = self.location_combo.findData(lid)
            assert idx >= 0, "la ubicación real debe aparecer en el combo"
            self.location_combo.setCurrentIndex(idx)
            return QDialog.Accepted

        with patch("frontend.desktop.modules.inventory.dialogs.OpenQuarantineDialog.exec_",
                   _fake_exec, create=True), \
             patch("frontend.desktop.modules.inventory.pages.quarantine_page"
                   ".QMessageBox.information") as info_mock, \
             patch("frontend.desktop.modules.inventory.pages.quarantine_page"
                   ".QMessageBox.warning") as warn_mock:
            page._on_open()

        assert not warn_mock.called, "open_quarantine failed: revisar ubicación seleccionada"
        assert info_mock.called
        assert pres.quarantines().total == 1
        del app
