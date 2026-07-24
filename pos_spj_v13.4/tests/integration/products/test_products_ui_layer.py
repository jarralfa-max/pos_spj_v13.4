"""PROD-18 — capa UI de Productos: navegación, view_models, presenter, catalog read."""

import pathlib
import sqlite3

import pytest

from backend.application.products.permissions import ALL_PRODUCT_PERMISSIONS
from backend.application.products.queries.catalog_read_service import (
    ProductCatalogReadService,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema
from frontend.desktop.modules.products.navigation import PRODUCTS_NAV, visible_entries
from frontend.desktop.modules.products.presenter import ProductsPresenter
from frontend.desktop.modules.products.view_models import (
    catalog_table,
    lifecycle_es,
    lifecycle_variant,
    product_type_es,
)


# ── navegación (§42) ─────────────────────────────────────────────────────────
class TestNavigation:
    def test_all_permissions_are_canonical(self):
        for entry in PRODUCTS_NAV:
            assert entry.permission in ALL_PRODUCT_PERMISSIONS, entry.page_id

    def test_titles_are_spanish_and_unique(self):
        ids = [e.page_id for e in PRODUCTS_NAV]
        assert len(ids) == len(set(ids))
        assert all(e.title and e.tooltip for e in PRODUCTS_NAV)

    def test_visible_entries_filtered_by_permission(self):
        from backend.application.products.permissions import ProductPermissions
        allowed = {ProductPermissions.VIEW}
        vis = visible_entries(lambda p: p in allowed)
        assert all(e.permission == ProductPermissions.VIEW for e in vis)
        assert any(e.page_id == "products_catalog" for e in vis)
        assert not any(e.page_id == "products_species" for e in vis)


# ── view models (es-MX) ──────────────────────────────────────────────────────
class TestViewModels:
    def test_type_and_lifecycle_labels(self):
        assert product_type_es("PRIMARY_CUT") == "Corte primario"
        assert lifecycle_es("ACTIVE") == "Activo"
        assert lifecycle_variant("BLOCKED") == "danger"

    def test_catalog_table_maps_rows(self):
        vm = catalog_table([
            {"id": "p1", "code": "ABR", "name": "Refresco",
             "product_type": "RESALE_PRODUCT", "lifecycle_status": "ACTIVE", "is_meat": False}])
        assert vm.total == 1 and vm.row_ids == ["p1"]
        assert vm.rows[0] == ["ABR", "Refresco", "Reventa", "Activo", "No"]


# ── presenter + catalog read service ─────────────────────────────────────────
@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    for pid, ptype, status, meat in [
        ("p1", "RESALE_PRODUCT", "ACTIVE", None),
        ("p2", "PRIMARY_CUT", "ACTIVE", "bov"),
        ("p3", "SEMI_FINISHED_GOOD", "DRAFT", None),
    ]:
        c.execute("INSERT INTO products (id,code,name,name_normalized,product_type,"
                  "lifecycle_status,base_unit_id,category_id,species_id,internal_only) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (pid, pid.upper(), pid, pid, ptype, status, "kg", "c1", meat,
                   1 if pid == "p3" else 0))
    c.commit()
    yield c
    c.close()


class TestPresenter:
    def _presenter(self, conn):
        return ProductsPresenter(read_service_factory=lambda: ProductCatalogReadService(conn))

    def test_overview_kpis(self, conn):
        kpis = {k.key: k.value for k in self._presenter(conn).overview_kpis()}
        assert kpis["active"] == "2" and kpis["meat"] == "1" and kpis["internal"] == "1"

    def test_catalog_view_model(self, conn):
        vm = self._presenter(conn).catalog()
        assert vm.total == 3

    def test_catalog_search(self, conn):
        vm = self._presenter(conn).catalog(query="p2")
        assert vm.total == 1

    def test_overview_kpis_defensive_on_error(self):
        class _Bad:
            def overview_counts(self): raise RuntimeError("db down")
        p = ProductsPresenter(read_service_factory=lambda: _Bad())
        assert p.overview_kpis() == []


# ── guardrail: UI sin SQL ni repositorios ────────────────────────────────────
class TestUiHasNoSql:
    def test_ui_files_have_no_sql_or_db(self):
        base = pathlib.Path(__file__).resolve().parents[2] / "frontend/desktop/modules/products"
        offenders = []
        for path in base.rglob("*.py"):
            src = path.read_text(encoding="utf-8").lower()
            if "import sqlite3" in src or "execute(" in src or "select " in src:
                offenders.append(path.name)
            if "repositories" in src:
                offenders.append(path.name + " (repo import)")
        assert not offenders, f"UI de Productos con SQL/DB: {offenders}"
