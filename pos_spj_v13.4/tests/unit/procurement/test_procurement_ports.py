"""FASE 2 — Crear puertos: ProcurementProductCatalogPort must let Compras
replace manual product-id typing with real search-and-select against the
canonical catalog, never the legacy ``productos`` table."""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.procurement.adapters.product_catalog_adapter import (
    ProcurementProductCatalogAdapter,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema


@pytest.fixture
def products_conn():
    conn = sqlite3.connect(":memory:")
    create_products_schema(conn)
    conn.execute(
        "INSERT INTO products (id, code, name, product_type, lifecycle_status,"
        " base_unit_id, purchasable, sellable) VALUES"
        " ('p1','COD-1','Pollo entero','INVENTORY','ACTIVE','KG',1,1)")
    conn.execute(
        "INSERT INTO products (id, code, name, product_type, lifecycle_status,"
        " base_unit_id, purchasable, sellable) VALUES"
        " ('p2','COD-2','Servicio de limpieza','SERVICE','ACTIVE','PZA',0,0)")
    conn.execute(
        "INSERT INTO products (id, code, name, product_type, lifecycle_status,"
        " base_unit_id, purchasable, sellable) VALUES"
        " ('p3','COD-3','Producto descontinuado','INVENTORY','DISCONTINUED',"
        " 'PZA',1,0)")
    yield conn
    conn.close()


def test_search_finds_purchasable_products_by_name(products_conn):
    adapter = ProcurementProductCatalogAdapter(products_conn)
    results = adapter.search("Pollo")
    assert [r.product_id for r in results] == ["p1"]
    assert results[0].code == "COD-1" and results[0].purchase_unit == "KG"


def test_search_excludes_non_purchasable_and_discontinued_products(products_conn):
    adapter = ProcurementProductCatalogAdapter(products_conn)
    assert adapter.search("Servicio de limpieza") == []  # purchasable=0
    assert adapter.search("descontinuado") == []  # lifecycle_status != ACTIVE


def test_search_by_code(products_conn):
    adapter = ProcurementProductCatalogAdapter(products_conn)
    results = adapter.search("COD-1")
    assert [r.product_id for r in results] == ["p1"]


def test_search_with_blank_query_returns_nothing_never_the_whole_catalog(products_conn):
    adapter = ProcurementProductCatalogAdapter(products_conn)
    assert adapter.search("") == []
    assert adapter.search("   ") == []


def test_resolve_returns_active_product_by_id(products_conn):
    adapter = ProcurementProductCatalogAdapter(products_conn)
    option = adapter.resolve("p1")
    assert option is not None
    assert option.name == "Pollo entero" and option.purchasable is True


def test_resolve_returns_none_for_missing_or_discontinued_product(products_conn):
    adapter = ProcurementProductCatalogAdapter(products_conn)
    assert adapter.resolve("does-not-exist") is None
    assert adapter.resolve("p3") is None  # DISCONTINUED — never resolved as buyable
    assert adapter.resolve("") is None


def test_adapter_degrades_gracefully_when_products_schema_is_absent():
    """A caller on a connection without the products schema yet (an
    un-migrated install, or a narrow test fixture) gets an empty result,
    never a crash and never an invented product."""
    conn = sqlite3.connect(":memory:")
    adapter = ProcurementProductCatalogAdapter(conn)
    assert adapter.search("anything") == []
    assert adapter.resolve("anything") is None
    conn.close()


# ── SupplierProcurementProfilePort / ProcurementFinancePort / ───────────────
# ── InventoryReceiptStatusPort ──────────────────────────────────────────────

from backend.application.procurement.adapters.supplier_profile_adapter import (
    InventoryReceiptStatusAdapter,
    SupplierFinanceAdapter,
    SupplierProfileAdapter,
)
from backend.application.procurement.ports import (
    InventoryReceiptStatus,
    InventoryReceiptStatusPort,
    ProcurementFinancePort,
    SupplierFinancialStanding,
    SupplierProcurementProfile,
    SupplierProcurementProfilePort,
)
from backend.infrastructure.db.schema.finance_schema import create_finance_schema
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.supplier_schema import create_supplier_schema


def test_fake_supplier_profile_satisfies_port_structurally():
    """No inheritance required — a fake with the right method signature
    conforms to the Protocol (structural typing, per ports.py's docstring)."""
    class _Fake:
        def profile(self, supplier_id: str) -> SupplierProcurementProfile | None:
            return SupplierProcurementProfile(
                supplier_id=supplier_id, legal_name="Acme", trade_name=None,
                status="ACTIVE", purchasing_enabled=True, financially_blocked=False,
                risk_level="LOW", rating_grade="A", active_blocks=())

    port: SupplierProcurementProfilePort = _Fake()
    assert port.profile("s1").legal_name == "Acme"


def test_fake_procurement_finance_satisfies_port_structurally():
    class _Fake:
        def financial_standing(self, supplier_id: str) -> SupplierFinancialStanding:
            return SupplierFinancialStanding(
                supplier_id=supplier_id, balance="0.00", overdue="0.00", open_documents=0)

    port: ProcurementFinancePort = _Fake()
    assert port.financial_standing("s1").balance == "0.00"


def test_fake_inventory_receipt_status_satisfies_port_structurally():
    class _Fake:
        def status_for_receipt(self, goods_receipt_id: str) -> InventoryReceiptStatus | None:
            return InventoryReceiptStatus(
                goods_receipt_id=goods_receipt_id, status="POSTED", occurred_at="2026-01-01")

    port: InventoryReceiptStatusPort = _Fake()
    assert port.status_for_receipt("gr1").status == "POSTED"


@pytest.fixture
def supplier_conn():
    conn = sqlite3.connect(":memory:")
    create_supplier_schema(conn)
    conn.execute(
        "INSERT INTO supplier_master (id, supplier_code, legal_name, trade_name,"
        " tax_identifier, status, risk_level, rating_grade, created_at, updated_at)"
        " VALUES ('s1','SUP-1','Acme SA de CV','Acme','AAA010101AAA','ACTIVE',"
        " 'LOW','A','2026-01-01','2026-01-01')")
    conn.execute(
        "INSERT INTO supplier_blocks (id, supplier_id, block_type, reason,"
        " effective_at, created_by_user_id, active) VALUES"
        " ('b1','s1','PAYMENT_BLOCK','Adeudo vencido','2026-01-01','u1',1)")
    yield conn
    conn.close()


def test_supplier_profile_adapter_composes_header_and_eligibility(supplier_conn):
    adapter = SupplierProfileAdapter(supplier_conn)
    profile = adapter.profile("s1")
    assert profile is not None
    assert profile.legal_name == "Acme SA de CV"
    assert profile.status == "ACTIVE"
    assert profile.risk_level == "LOW" and profile.rating_grade == "A"
    assert profile.active_blocks == ("PAYMENT_BLOCK",)
    # No `proveedores` row and no migration 178 → eligibility degrades to
    # permissive defaults (SupplierDirectoryQueryService's own fallback),
    # never invents a block.
    assert profile.purchasing_enabled is True
    assert profile.financially_blocked is False


def test_supplier_profile_adapter_returns_none_for_missing_supplier(supplier_conn):
    adapter = SupplierProfileAdapter(supplier_conn)
    assert adapter.profile("does-not-exist") is None


def test_supplier_profile_adapter_degrades_when_supplier_schema_absent():
    conn = sqlite3.connect(":memory:")
    adapter = SupplierProfileAdapter(conn)
    assert adapter.profile("anything") is None
    conn.close()


def test_supplier_profile_adapter_reflects_proveedores_eligibility(supplier_conn):
    """Where the legacy ``proveedores`` row exists too, eligibility/blocked
    flags come from it via SupplierDirectoryQueryService.get_eligibility."""
    supplier_conn.execute(
        "CREATE TABLE proveedores (id TEXT PRIMARY KEY, activo INTEGER,"
        " compras_habilitadas INTEGER, bloqueado_financiero INTEGER)")
    supplier_conn.execute(
        "INSERT INTO proveedores (id, activo, compras_habilitadas,"
        " bloqueado_financiero) VALUES ('s1', 1, 0, 1)")
    adapter = SupplierProfileAdapter(supplier_conn)
    profile = adapter.profile("s1")
    assert profile.purchasing_enabled is False
    assert profile.financially_blocked is True


@pytest.fixture
def payables_conn():
    conn = sqlite3.connect(":memory:")
    create_finance_schema(conn)
    conn.execute(
        "INSERT INTO financial_documents (id, document_type, document_number,"
        " issue_date, currency_code, total_amount, outstanding_amount, status,"
        " supplier_id, source_module, source_document_id, operation_id,"
        " created_at, updated_at) VALUES"
        " ('fd1','SUPPLIER_INVOICE','FAC-1','2026-01-01','MXN','1500.00','1500.00',"
        " 'OPEN','s1','PROCUREMENT','po1','op-fd1','2026-01-01','2026-01-01')")
    conn.execute(
        "INSERT INTO payables (id, supplier_id, financial_document_id, original_amount,"
        " outstanding_amount, currency_code, issue_date, due_date, status,"
        " operation_id, created_at, updated_at) VALUES"
        " ('pay1','s1','fd1','1500.00','1500.00','MXN','2026-01-01','2020-01-01',"
        " 'OPEN','op-pay1','2026-01-01','2026-01-01')")
    yield conn
    conn.close()


def test_supplier_finance_adapter_wraps_summary(payables_conn):
    adapter = SupplierFinanceAdapter(payables_conn)
    standing = adapter.financial_standing("s1")
    assert standing.supplier_id == "s1"
    assert standing.balance == "1500.00"
    assert standing.overdue == "1500.00"  # due_date is in the past
    assert standing.open_documents == 1


def test_supplier_finance_adapter_zeros_when_payables_absent():
    """Same tolerance as SupplierFinancialSummaryQueryService itself — an
    un-migrated/finance-less connection never crashes, never invents debt."""
    conn = sqlite3.connect(":memory:")
    adapter = SupplierFinanceAdapter(conn)
    standing = adapter.financial_standing("s1")
    assert standing.balance == "0.00" and standing.overdue == "0.00"
    assert standing.open_documents == 0
    conn.close()


@pytest.fixture
def receipts_conn():
    conn = sqlite3.connect(":memory:")
    create_inventory_schema(conn)
    conn.execute(
        "INSERT INTO inventory_ledger (id, movement_type, branch_id, warehouse_id,"
        " source_module, source_document_type, source_document_id, operation_id,"
        " created_by_user_id, status, occurred_at) VALUES"
        " ('m1','PURCHASE_RECEIPT','br1','wh1','PROCUREMENT','PURCHASE_ORDER','po1',"
        " 'op-m1','u1','POSTED','2026-01-01T10:00:00+00:00')")
    yield conn
    conn.close()


def test_inventory_receipt_status_adapter_finds_posted_receipt(receipts_conn):
    adapter = InventoryReceiptStatusAdapter(receipts_conn)
    status = adapter.status_for_receipt("po1")
    assert status is not None
    assert status.status == "POSTED"
    assert status.occurred_at == "2026-01-01T10:00:00+00:00"


def test_inventory_receipt_status_adapter_none_when_not_yet_posted(receipts_conn):
    adapter = InventoryReceiptStatusAdapter(receipts_conn)
    assert adapter.status_for_receipt("po-never-received") is None


def test_inventory_receipt_status_adapter_degrades_when_inventory_schema_absent():
    conn = sqlite3.connect(":memory:")
    adapter = InventoryReceiptStatusAdapter(conn)
    assert adapter.status_for_receipt("anything") is None
    conn.close()
