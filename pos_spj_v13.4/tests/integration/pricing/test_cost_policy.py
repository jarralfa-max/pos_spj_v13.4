"""FASE 12 Compras/Costeo (2026-09-29): política de costo multi-sucursal (§30, §32).

* La proyección mantiene SIEMPRE el promedio de empresa y el de cada sucursal,
  cada uno con su propia existencia real (movimientos posteados de verdad).
* La política (GLOBAL por omisión / PER_BRANCH) decide cuál costo reportan
  Precios, Ventas y Compras. Cambiarla no recalcula nada: rige de inmediato.
* El precio de venta NUNCA cambia por un cambio de costo (§30).
"""

import json
import os
import sqlite3
from decimal import Decimal

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.inventory.use_cases import PostInventoryMovementUseCase  # noqa: E402
from backend.application.pricing.authorization.policy import PricingAuthorizationPolicy  # noqa: E402
from backend.application.pricing.cost_policy import (  # noqa: E402
    CostPolicy,
    CostPolicySettings,
    ProductCostingService,
)
from backend.application.pricing.event_handlers.product_cost_projection_handler import (  # noqa: E402
    ProductCostProjectionHandler,
)
from backend.application.pricing.queries.pricing_read_facade import PricingReadFacade  # noqa: E402
from backend.application.pricing.use_cases.cost_policy_use_cases import (  # noqa: E402
    SetCostPolicyUseCase,
)
from backend.application.procurement.queries.purchase_template_read_service import (  # noqa: E402
    ProductPurchaseCostReadService,
)
from backend.domain.inventory.entities.inventory_movement import (  # noqa: E402
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import MovementType  # noqa: E402
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema  # noqa: E402
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema  # noqa: E402
from tests.integration._governed_settings import ensure_governance, set_setting


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    create_pricing_schema(c)
    c.execute("ALTER TABLE product_cost ADD COLUMN tracked_quantity TEXT")  # migración 151
    c.execute("CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT,"
              " tipo TEXT, grupo TEXT, descripcion TEXT)")
    c.execute("CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT)")
    c.executemany("INSERT INTO sucursales VALUES (?,?)", [("b1", "Centro"), ("b2", "Norte")])
    ensure_governance(c)
    c.commit()
    yield c
    c.close()


def _post(conn, kind, qty, op, *, branch, into=True):
    line = InventoryMovementLine.create(
        product_id="p1", quantity=Decimal(qty),
        **({"to_location_id": f"loc-{branch}"} if into else {"from_location_id": f"loc-{branch}"}))
    movement = InventoryMovement.create(
        movement_type=kind, branch_id=branch, warehouse_id=f"w-{branch}",
        source_module="test", source_document_type="DOC", source_document_id=op,
        operation_id=op, created_by_user_id="u1", lines=[line])
    result = PostInventoryMovementUseCase().execute(conn, movement, actor_user_id="u1")
    assert result.success, result.message


def _receive(conn, qty, cost, op, *, branch):
    _post(conn, MovementType.PURCHASE_RECEIPT, qty, op, branch=branch)
    ProductCostProjectionHandler(conn).handle({
        "event_id": f"evt-{op}", "operation_id": op, "branch_id": branch,
        "lines": [{"product_id": "p1", "quantity": qty, "unit_cost": cost}]})


def _two_branches(conn):
    _receive(conn, "10", "40", "rec-b1", branch="b1")
    _receive(conn, "10", "60", "rec-b2", branch="b2")


def _set(conn, policy):
    result = SetCostPolicyUseCase().execute(conn, actor_user_id="u1", operation_id=f"op-{policy}",
                                            policy=policy)
    assert result.success, result.message
    return result


def _q(value):
    return None if value is None else Decimal(value).quantize(Decimal("0.01"))


# ── la proyección mantiene empresa y sucursal ─────────────────────────────────

def test_company_and_branch_averages_are_both_kept(conn):
    _two_branches(conn)
    view = ProductCostingService(conn).cost_view("p1", "b1")
    assert _q(view.company_average_cost) == Decimal("50.00")
    assert _q(view.branch_average_cost) == Decimal("40.00")
    assert _q(ProductCostingService(conn).cost_view("p1", "b2").branch_average_cost) == \
        Decimal("60.00")
    assert _q(view.company_last_purchase_cost) == Decimal("60.00")   # la última de empresa
    assert _q(view.branch_last_purchase_cost) == Decimal("40.00")


def test_branch_average_uses_that_branch_real_stock(conn):
    _two_branches(conn)
    _post(conn, MovementType.SALE_ISSUE, "5", "sale-b1", branch="b1", into=False)
    _receive(conn, "5", "70", "rec-b1-2", branch="b1")
    view = ProductCostingService(conn).cost_view("p1", "b1")
    assert _q(view.branch_average_cost) == Decimal("55.00")    # (5×40 + 5×70) / 10
    assert _q(view.company_average_cost) == Decimal("55.00")   # (15×50 + 5×70) / 20


# ── la política decide qué costo se reporta ───────────────────────────────────

def test_global_is_the_default_and_ignores_the_branch_row(conn):
    _two_branches(conn)
    assert CostPolicySettings(conn).current() is CostPolicy.GLOBAL
    facade = PricingReadFacade(conn)
    assert _q(facade.average_cost("p1", branch_id="b1")) == Decimal("50.00")
    assert Decimal(ProductPurchaseCostReadService(conn).historical_cost("p1", branch_id="b1")) == 50


def test_per_branch_reports_the_branch_cost_and_falls_back_to_company(conn):
    _two_branches(conn)
    _set(conn, "PER_BRANCH")
    facade = PricingReadFacade(conn)
    assert _q(facade.average_cost("p1", branch_id="b1")) == Decimal("40.00")
    assert _q(facade.average_cost("p1", branch_id="b2")) == Decimal("60.00")
    assert _q(facade.average_cost("p1", branch_id="b9")) == Decimal("50.00")  # sin historia
    assert _q(facade.average_cost("p1")) == Decimal("50.00")                   # sin sucursal
    assert Decimal(ProductPurchaseCostReadService(conn).historical_cost("p1", branch_id="b2")) == 60
    _set(conn, "GLOBAL")                                # y de regreso, sin recalcular
    assert _q(facade.average_cost("p1", branch_id="b1")) == Decimal("50.00")


def test_changing_the_policy_is_audited_validated_and_permissioned(conn):
    result = _set(conn, "PER_BRANCH")
    assert result.data["changed"] is True
    payload = json.loads(conn.execute(
        "SELECT payload FROM pricing_outbox WHERE event_name='COST_POLICY_CHANGED'"
    ).fetchone()[0])
    assert (payload["previous"], payload["policy"], payload["user_id"]) == (
        "GLOBAL", "PER_BRANCH", "u1")
    assert _set(conn, "PER_BRANCH").data["changed"] is False            # sin cambio
    bad = SetCostPolicyUseCase().execute(conn, actor_user_id="u1", operation_id="x",
                                         policy="FIFO")
    assert not bad.success and bad.error_code == "VALIDATION"

    class Deny:
        def has_permission(self, user_id, code):
            return False

    denied = SetCostPolicyUseCase(PricingAuthorizationPolicy(Deny())).execute(
        conn, actor_user_id="u2", operation_id="y", policy="GLOBAL")
    assert not denied.success and denied.error_code == "PERMISSION_DENIED"
    assert CostPolicySettings(conn).current() is CostPolicy.PER_BRANCH


# ── §30: el costo nunca mueve el precio de venta ──────────────────────────────

def test_a_cost_update_never_touches_the_sale_price(conn):
    conn.execute("INSERT INTO price_list (id, code, name, kind, status) VALUES"
                 " ('l1','BASE','Base','BASE','ACTIVE')")
    conn.execute("INSERT INTO product_price (id, price_list_id, product_id, branch_id,"
                 " sale_price, sale_price_currency) VALUES ('pp1','l1','p1','','99','MXN')")
    conn.commit()
    _two_branches(conn)
    _receive(conn, "10", "500", "rec-caro", branch="b1")
    assert conn.execute("SELECT sale_price FROM product_price WHERE id='pp1'"
                        ).fetchone()[0] == "99"
    assert conn.execute("SELECT COUNT(*) FROM price_change_log WHERE field <> 'cost'"
                        ).fetchone()[0] == 0


# ── pantallas ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _Session:
    user_id = "u1"

    def tiene_permiso(self, code):
        return True


def _presenter(conn):
    from backend.application.pricing.queries.pricing_read_service import PricingReadService
    from frontend.desktop.modules.pricing.presenter import PricingPresenter
    return PricingPresenter(read_service_factory=lambda: PricingReadService(conn),
                            connection_provider=lambda: conn,
                            use_cases={"set_cost_policy": SetCostPolicyUseCase()},
                            session_context=_Session())


def test_settings_page_changes_the_policy(app, conn):
    from frontend.desktop.modules.pricing.pages.settings_page import PricingSettingsPage
    page = PricingSettingsPage(_presenter(conn))
    assert page.cost_policy.current_id() == "GLOBAL" and page.save_cost_policy.isVisibleTo(page)
    assert page.table.item(0, 0).text() == "Política de costo"
    assert page.table.item(0, 1).text() == "Global"
    page.cost_policy.set_current_id("PER_BRANCH")
    page._save_cost_policy()
    assert CostPolicySettings(conn).current() is CostPolicy.PER_BRANCH
    assert page.cost_policy_notice.property("state") == "success"
    assert page.table.item(0, 1).text() == "Por sucursal"


def test_costs_page_shows_company_and_branch_rows_by_name(app, conn):
    _two_branches(conn)
    vm = _presenter(conn).costs()
    scopes = sorted(row[1] for row in vm.rows)
    assert scopes == ["Centro", "Empresa", "Norte"]
    assert len(set(vm.row_ids)) == 3
