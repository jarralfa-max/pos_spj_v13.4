"""P0-E — Compras→Inventario: gate real de inspección.

Before this slice, ``PurchaseReceiptHandler`` could route a received line into
the ``PENDING_INSPECTION`` bucket via an explicit ``quality_hold`` flag on the
payload — but nothing ever set that flag (grep confirmed zero producers), and
even if it had, no use case existed that could ever move stock back OUT of
that bucket (``SetLotQualityStatusUseCase`` operates on a different bucket —
see ``lot_quality_projection.py``: a lot's default quality status maps to
AVAILABLE, not PENDING_INSPECTION). This closes both ends:

1. The receipt handler now asks the product's own quality profile
   (``QualityProductConfigQueryService.inspection_required``, §34 — read-only,
   the permitted direction) when no explicit flag is present.
2. ``InspectReceiptUseCase`` (new) approves (→ AVAILABLE) or rejects
   (→ QUALITY_BLOCKED) a held balance, identified by its real
   ``inventory_balances.id`` — the only thing that can release it.
"""

from __future__ import annotations

from decimal import Decimal

import sqlite3

import pytest

from backend.application.event_handlers.inventory.purchase_receipt_handler import (
    PurchaseReceiptHandler,
)
from backend.application.event_handlers.inventory.purchase_stock_entry_bridge import (
    CanonicalPurchaseStockEntryHandler,
)
from backend.application.inventory.authorization import (
    AllowAllInventoryPermissionCheckerForTests,
    DenyAllInventoryPermissionCheckerForTests,
    InventoryAuthorizationPolicy,
)
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
    GenerateReplenishmentSuggestionsUseCase,
    InspectReceiptUseCase,
)
from backend.domain.inventory.enums import InventoryStatus
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
        CREATE TABLE product_quality_profiles (
            product_id TEXT PRIMARY KEY, inspection_required INTEGER DEFAULT 0,
            temperature_required INTEGER DEFAULT 0, weight_check_required INTEGER DEFAULT 0,
            organoleptic_check_required INTEGER DEFAULT 0,
            microbiological_test_required INTEGER DEFAULT 0,
            fat_pct_min TEXT, fat_pct_max TEXT, moisture_pct_min TEXT, moisture_pct_max TEXT,
            color_requirement TEXT, odor_requirement TEXT, packaging_requirement TEXT,
            documentation_requirement TEXT, quarantine_required INTEGER DEFAULT 0,
            updated_at TEXT
        );
        CREATE TABLE product_logistics_profiles (
            product_id TEXT PRIMARY KEY, gross_weight TEXT, net_weight TEXT,
            weight_unit TEXT, dimensions TEXT, storage_temp_min TEXT, storage_temp_max TEXT,
            storage_temp_unit TEXT, transport_temp_min TEXT, transport_temp_max TEXT,
            transport_temp_unit TEXT, fragile INTEGER DEFAULT 0, perishable INTEGER DEFAULT 0,
            frozen INTEGER DEFAULT 0, chilled INTEGER DEFAULT 0, stackable INTEGER DEFAULT 0,
            shelf_life_days INTEGER, open_package_shelf_life_days INTEGER,
            requires_cold_chain INTEGER DEFAULT 0, updated_at TEXT
        );
        CREATE TABLE product_shelf_life_profiles (
            id TEXT PRIMARY KEY, product_id TEXT, shelf_life_days INTEGER,
            minimum_remaining_for_receipt INTEGER, minimum_remaining_for_sale INTEGER,
            storage_condition TEXT, opened_shelf_life_days INTEGER,
            frozen_shelf_life_days INTEGER, thawed_shelf_life_days INTEGER,
            effective_from TEXT, effective_to TEXT, created_at TEXT
        );
        """
    )
    c.execute(
        "INSERT INTO products (id, name, code, base_unit_id, lifecycle_status) "
        "VALUES ('p1', 'Pechuga de pollo', 'POLLO-001', 'kg', 'ACTIVE')")
    c.execute(
        "INSERT INTO products (id, name, code, base_unit_id, lifecycle_status) "
        "VALUES ('p2', 'Servilletas', 'SERV-001', 'PZA', 'ACTIVE')")
    c.commit()
    return c


def _require_inspection(conn, product_id="p1"):
    conn.execute(
        "INSERT INTO product_quality_profiles (product_id, inspection_required) "
        "VALUES (?, 1)", (product_id,))
    conn.commit()


def _presenter(conn, **overrides):
    kwargs = dict(
        connection_provider=lambda: conn,
        availability_service_factory=InventoryAvailabilityQueryService,
        replenishment_query_factory=ReplenishmentQueryService,
        generate_suggestions_uc=GenerateReplenishmentSuggestionsUseCase(),
        warehouse_query_factory=WarehouseQueryService,
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
        inspect_receipt_uc=InspectReceiptUseCase(),
        session_context=_Session(),
    )
    kwargs.update(overrides)
    return InventoryPresenter(**kwargs)


class TestReceiptRoutesToInspection:
    def test_product_requiring_inspection_lands_pending(self, conn):
        _require_inspection(conn, "p1")
        handler = CanonicalPurchaseStockEntryHandler(conn)
        handler.handle({
            "branch_id": "b1", "warehouse_id": "w1", "document_number": "GR-1",
            "goods_receipt_id": "GR-1",
            "operation_id": "op-1", "user_id": "u1",
            "lines": [{"product_id": "p1", "quantity": "5", "unit_cost": "10"}],
        })
        rows = StockQueryService(conn).list_on_hand(branch_id="b1")
        assert len(rows) == 1
        assert rows[0]["inventory_status"] == InventoryStatus.PENDING_INSPECTION.value

    def test_product_without_inspection_profile_lands_available(self, conn):
        handler = CanonicalPurchaseStockEntryHandler(conn)
        handler.handle({
            "branch_id": "b1", "warehouse_id": "w1", "document_number": "GR-2",
            "goods_receipt_id": "GR-2",
            "operation_id": "op-2", "user_id": "u1",
            "lines": [{"product_id": "p2", "quantity": "3", "unit_cost": "2"}],
        })
        rows = StockQueryService(conn).list_on_hand(branch_id="b1")
        assert len(rows) == 1
        assert rows[0]["inventory_status"] == InventoryStatus.AVAILABLE.value

    def test_explicit_quality_hold_overrides_regardless_of_profile(self, conn):
        handler = CanonicalPurchaseStockEntryHandler(conn)
        handler.handle({
            "branch_id": "b1", "warehouse_id": "w1", "document_number": "GR-3",
            "goods_receipt_id": "GR-3",
            "operation_id": "op-3", "user_id": "u1", "quality_hold": True,
            "lines": [{"product_id": "p2", "quantity": "1", "unit_cost": "2"}],
        })
        rows = StockQueryService(conn).list_on_hand(branch_id="b1")
        assert rows[0]["inventory_status"] == InventoryStatus.PENDING_INSPECTION.value

    def test_missing_quality_profile_table_degrades_to_available(self, conn):
        """§5.4 fail-closed-but-not-crash: if Products' quality read fails for
        any reason, the receipt still posts (to AVAILABLE) instead of raising
        — a broken cross-context read must never block procurement."""
        conn.execute("DROP TABLE product_quality_profiles")
        conn.commit()
        handler = CanonicalPurchaseStockEntryHandler(conn)
        handler.handle({
            "branch_id": "b1", "warehouse_id": "w1", "document_number": "GR-4",
            "goods_receipt_id": "GR-4",
            "operation_id": "op-4", "user_id": "u1",
            "lines": [{"product_id": "p1", "quantity": "1", "unit_cost": "5"}],
        })
        rows = StockQueryService(conn).list_on_hand(branch_id="b1")
        assert rows[0]["inventory_status"] == InventoryStatus.AVAILABLE.value


class TestInspectReceiptUseCase:
    def _held_balance_id(self, conn, *, quantity=Decimal("5")):
        _require_inspection(conn, "p1")
        PurchaseReceiptHandler(conn).handle({
            "branch_id": "b1", "warehouse_id": "w1", "goods_receipt_id": "gr-1",
            "operation_id": "op-1", "user_id": "u1",
            "lines": [{"product_id": "p1", "quantity": str(quantity),
                       "to_location_id": "w1"}],
        })
        rows = StockQueryService(conn).list_on_hand(branch_id="b1")
        return rows[0]["id"]

    def test_pass_moves_balance_to_available(self, conn):
        balance_id = self._held_balance_id(conn)
        result = InspectReceiptUseCase().execute(
            conn, balance_id=balance_id, passed=True, operation_id="insp-1",
            actor_user_id="qa")
        assert result.success, result.message
        dto = InventoryAvailabilityQueryService(conn).get_availability(
            product_id="p1", branch_id="b1", warehouse_id="w1")
        assert dto.available == Decimal("5")

    def test_fail_moves_balance_to_quality_blocked(self, conn):
        balance_id = self._held_balance_id(conn)
        result = InspectReceiptUseCase().execute(
            conn, balance_id=balance_id, passed=False, operation_id="insp-2",
            actor_user_id="qa", reason="Olor extraño")
        assert result.success, result.message
        dto = InventoryAvailabilityQueryService(conn).get_availability(
            product_id="p1", branch_id="b1", warehouse_id="w1")
        assert dto.available == Decimal("0")
        rows = StockQueryService(conn).list_on_hand(branch_id="b1")
        assert rows[0]["inventory_status"] == InventoryStatus.QUALITY_BLOCKED.value

    def test_balance_not_found_fails(self, conn):
        result = InspectReceiptUseCase().execute(
            conn, balance_id="does-not-exist", passed=True, operation_id="insp-3",
            actor_user_id="qa")
        assert not result.success
        assert result.error_code == "BALANCE_NOT_FOUND"

    def test_balance_not_pending_fails(self, conn):
        # p2 tiene perfil sin inspección: aterriza en AVAILABLE directamente.
        CanonicalPurchaseStockEntryHandler(conn).handle({
            "branch_id": "b1", "warehouse_id": "w1", "document_number": "GR-5",
            "goods_receipt_id": "GR-5",
            "operation_id": "op-5", "user_id": "u1",
            "lines": [{"product_id": "p2", "quantity": "1", "unit_cost": "2"}],
        })
        balance_id = StockQueryService(conn).list_on_hand(branch_id="b1")[0]["id"]
        result = InspectReceiptUseCase().execute(
            conn, balance_id=balance_id, passed=True, operation_id="insp-4",
            actor_user_id="qa")
        assert not result.success
        assert result.error_code == "NOT_PENDING_INSPECTION"

    def test_permission_denied_when_checker_denies(self, conn):
        balance_id = self._held_balance_id(conn)
        policy = InventoryAuthorizationPolicy(DenyAllInventoryPermissionCheckerForTests())
        result = InspectReceiptUseCase(authorization=policy).execute(
            conn, balance_id=balance_id, passed=True, operation_id="insp-5",
            actor_user_id="qa")
        assert not result.success
        assert result.error_code == "PERMISSION_DENIED"

    def test_allow_all_checker_permits(self, conn):
        balance_id = self._held_balance_id(conn)
        policy = InventoryAuthorizationPolicy(AllowAllInventoryPermissionCheckerForTests())
        result = InspectReceiptUseCase(authorization=policy).execute(
            conn, balance_id=balance_id, passed=True, operation_id="insp-6",
            actor_user_id="qa")
        assert result.success, result.message


class TestPresenterInspectStock:
    def _held_balance_id(self, conn, *, quantity=Decimal("5")):
        _require_inspection(conn, "p1")
        PurchaseReceiptHandler(conn).handle({
            "branch_id": "b1", "warehouse_id": "w1", "goods_receipt_id": "gr-1",
            "operation_id": "op-1", "user_id": "u1",
            "lines": [{"product_id": "p1", "quantity": str(quantity),
                       "to_location_id": "w1"}],
        })
        rows = StockQueryService(conn).list_on_hand(branch_id="b1")
        return rows[0]["id"]

    def test_inspect_stock_pass(self, conn):
        balance_id = self._held_balance_id(conn)
        pres = _presenter(conn)
        ok, message, _ = pres.inspect_stock(balance_id=balance_id, passed=True)
        assert ok, message

    def test_inspect_stock_reject_with_reason(self, conn):
        balance_id = self._held_balance_id(conn)
        pres = _presenter(conn)
        ok, message, _ = pres.inspect_stock(
            balance_id=balance_id, passed=False, reason="Empaque dañado")
        assert ok, message

    def test_inspect_stock_without_selection_fails(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.inspect_stock(balance_id="", passed=True)
        assert not ok
        assert "Selecciona" in message

    def test_inspect_stock_unavailable_when_not_wired(self, conn):
        pres = _presenter(conn, inspect_receipt_uc=None)
        ok, message, _ = pres.inspect_stock(balance_id="b-1", passed=True)
        assert not ok
        assert "no disponible" in message


class TestStockPageInspectionActions:
    def _held_balance(self, conn, *, quantity=Decimal("5")):
        _require_inspection(conn, "p1")
        PurchaseReceiptHandler(conn).handle({
            "branch_id": "b1", "warehouse_id": "w1", "goods_receipt_id": "gr-1",
            "operation_id": "op-1", "user_id": "u1",
            "lines": [{"product_id": "p1", "quantity": str(quantity),
                       "to_location_id": "w1"}],
        })

    def test_approve_button_moves_row_to_available(self, conn):
        pytest.importorskip("PyQt5")
        from unittest.mock import patch

        from PyQt5.QtWidgets import QApplication, QDialog

        from frontend.desktop.modules.inventory.pages import StockPage

        self._held_balance(conn)
        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = StockPage(pres)
        page.refresh()
        assert page._table.rowCount() == 1
        page._table.selectRow(0)

        with patch("frontend.desktop.modules.inventory.pages.stock_page"
                   ".ConfirmationDialog.exec_", return_value=QDialog.Accepted), \
             patch("frontend.desktop.modules.inventory.pages.stock_page"
                   ".QMessageBox.information"):
            page._on_approve_inspection()

        page.refresh()
        assert page._table.item(0, 2).text() == "Disponible"
        del app

    def test_reject_button_moves_row_to_quality_blocked(self, conn):
        pytest.importorskip("PyQt5")
        from unittest.mock import MagicMock, patch

        from PyQt5.QtWidgets import QApplication, QDialog

        from frontend.desktop.modules.inventory.pages import StockPage

        self._held_balance(conn)
        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = StockPage(pres)
        page.refresh()
        page._table.selectRow(0)

        dlg = MagicMock()
        dlg.exec_.return_value = QDialog.Accepted
        dlg.reason.return_value = "Empaque roto"

        with patch("frontend.desktop.modules.inventory.pages.stock_page"
                   ".BlockReasonDialog", return_value=dlg), \
             patch("frontend.desktop.modules.inventory.pages.stock_page"
                   ".QMessageBox.information"):
            page._on_reject_inspection()

        page.refresh()
        assert page._table.item(0, 2).text() == "Bloqueado calidad"
        del app

    def test_cannot_inspect_a_row_that_is_already_available(self, conn):
        """Guardia real: sólo filas «Por inspección» pueden inspeccionarse."""
        pytest.importorskip("PyQt5")
        from unittest.mock import patch

        from PyQt5.QtWidgets import QApplication

        from frontend.desktop.modules.inventory.pages import StockPage

        CanonicalPurchaseStockEntryHandler(conn).handle({
            "branch_id": "b1", "warehouse_id": "w1", "document_number": "GR-6",
            "goods_receipt_id": "GR-6",
            "operation_id": "op-6", "user_id": "u1",
            "lines": [{"product_id": "p2", "quantity": "1", "unit_cost": "2"}],
        })
        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = StockPage(pres)
        page.refresh()
        page._table.selectRow(0)

        with patch("frontend.desktop.modules.inventory.pages.stock_page"
                   ".QMessageBox.information") as info, \
             patch.object(pres, "inspect_stock") as inspect_stock:
            page._on_approve_inspection()
        info.assert_called_once()
        inspect_stock.assert_not_called()
        del app

    def test_requires_selection_before_acting(self, conn):
        pytest.importorskip("PyQt5")
        from unittest.mock import patch

        from PyQt5.QtWidgets import QApplication

        from frontend.desktop.modules.inventory.pages import StockPage

        app = QApplication.instance() or QApplication([])
        pres = _presenter(conn)
        page = StockPage(pres)
        page.refresh()

        with patch("frontend.desktop.modules.inventory.pages.stock_page"
                   ".QMessageBox.information") as info, \
             patch.object(pres, "inspect_stock") as inspect_stock:
            page._on_approve_inspection()
        info.assert_called_once()
        inspect_stock.assert_not_called()
        del app
