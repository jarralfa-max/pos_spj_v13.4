"""Fase 7 (§15-19) end-to-end: a customer buys a product with 0 direct
stock, but the store has its disassembled parts on hand. The live POS must
reconstruct it from those parts and complete the sale — the exact scenario
the master prompt's own worked example describes (whole chicken <-
breast/leg/wing on hand).

Goes through `suspend_sale` -> `resume_sale` -> checkout rather than a
straight checkout, because of a real, PRE-EXISTING, separate gap this test
run surfaced: `CheckoutSaleUseCase` only confirms an inventory reservation
if `sale.inventory_reservation_id` is already set, and `SalesInventoryClient.
reserve_for_sale` (where this fase's reconstruction top-up lives) is
currently only ever called from `SuspendSaleUseCase` — a normal, never-
suspended checkout never reserves or decrements inventory at all today.
That is a Fase-6-scope Sales/Inventory wiring gap, not something this fase
introduces or should fix — flagged in memory, not silently worked around by
pretending checkout already reserves. This test exercises the path that
DOES actually reserve today, which is exactly where this fase's own hook
lives and is proven to run correctly.
"""

from __future__ import annotations

import os
import sqlite3
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from backend.application.inventory.queries.availability_query_service import (
    InventoryAvailabilityQueryService,
)
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_recipe_commands import (
    CreateRecipeCommand,
    RecipeVersionTransitionCommand,
    SetReverseReconstructionAllowedCommand,
)
from backend.application.products.use_cases.product_recipe_use_cases import (
    ActivateRecipeVersionUseCase,
    ApproveRecipeVersionUseCase,
    CreateProductRecipeUseCase,
    SetReverseReconstructionAllowedUseCase,
    SubmitRecipeVersionUseCase,
)
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.sales.permissions import SalesPermissions
from backend.domain.inventory.entities.inventory_balance import InventoryBalance
from backend.domain.inventory.enums import InventoryStatus
from backend.domain.pricing.entities.product_cost import ProductCost
from backend.domain.pricing.value_objects.money import Money
from backend.infrastructure.db.repositories.inventory.unit_of_work import InventoryUnitOfWork
from backend.infrastructure.db.repositories.pricing.pricing_repository import PricingRepository
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import new_uuid
from frontend.desktop.modules.sales_pos.composition import build_sales_pos_presenter

_UNIT = "unit-kg"


class _AllowAllChecker:
    def has_permission(self, user_id, code):
        return True


class _FakeSession:
    def __init__(self, permissions, branch_id):
        self.user_id = new_uuid()
        self.active_branch_id = branch_id
        self.is_active = True
        self._permissions = set(permissions)

    def tiene_permiso(self, code: str) -> bool:
        return code in self._permissions


def _all_permissions_session(branch_id) -> _FakeSession:
    codes = {v for v in vars(SalesPermissions).values() if isinstance(v, str)}
    codes |= {v for v in vars(InventoryPermissions).values() if isinstance(v, str)}
    return _FakeSession(codes, branch_id)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_products_schema(c)
    create_pricing_schema(c)
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _stock(conn, *, product_id, branch_id, quantity):
    bal = InventoryBalance.empty(
        product_id=product_id, branch_id=branch_id, warehouse_id=branch_id,
        inventory_status=InventoryStatus.AVAILABLE, location_id=branch_id)
    bal.apply_delta(quantity=Decimal(quantity))
    with InventoryUnitOfWork(conn) as uow:
        uow.balances.upsert(bal)


def _cost(conn, *, product_id, branch_id, amount):
    PricingRepository(conn).save_cost(ProductCost(
        product_id=product_id, branch_id=branch_id, average_cost=Money(Decimal(amount))))


def _available(conn, product_id, branch_id) -> Decimal:
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id=product_id, branch_id=branch_id).available


def _disassembly_recipe(conn, *, product_id, outputs, creator="alice", approver="bob") -> None:
    auth = ProductsAuthorizationPolicy(_AllowAllChecker())
    created = CreateProductRecipeUseCase(conn, auth).execute(CreateRecipeCommand(
        operation_id=new_uuid(), product_id=product_id, recipe_type="DISASSEMBLY",
        name="Despiece", user_id=creator, outputs=outputs))
    assert created.success, created.message
    recipe_id, version_id = created.recipe_id, created.version_id

    def _transition(use_case_cls, user_id):
        result = use_case_cls(conn, auth).execute(RecipeVersionTransitionCommand(
            operation_id=new_uuid(), version_id=version_id, user_id=user_id))
        assert result.success, result.message

    _transition(SubmitRecipeVersionUseCase, creator)
    _transition(ApproveRecipeVersionUseCase, approver)
    _transition(ActivateRecipeVersionUseCase, approver)

    toggled = SetReverseReconstructionAllowedUseCase(conn, auth).execute(
        SetReverseReconstructionAllowedCommand(
            operation_id=new_uuid(), recipe_id=recipe_id, allowed=True, user_id=approver))
    assert toggled.success, toggled.message


def test_checkout_reconstructs_a_zero_stock_product_from_its_parts(conn):
    branch_id = new_uuid()
    chicken, breast, leg, wing = new_uuid(), new_uuid(), new_uuid(), new_uuid()
    _disassembly_recipe(conn, product_id=chicken, outputs=[
        {"product_id": breast, "output_type": "MAIN_PRODUCT", "quantity": "1.2", "unit_id": _UNIT},
        {"product_id": leg, "output_type": "CO_PRODUCT", "quantity": "0.8", "unit_id": _UNIT},
        {"product_id": wing, "output_type": "CO_PRODUCT", "quantity": "0.4", "unit_id": _UNIT},
    ])
    _stock(conn, product_id=breast, branch_id=branch_id, quantity="12")
    _stock(conn, product_id=leg, branch_id=branch_id, quantity="8")
    _stock(conn, product_id=wing, branch_id=branch_id, quantity="4")
    _cost(conn, product_id=breast, branch_id=branch_id, amount="80")
    _cost(conn, product_id=leg, branch_id=branch_id, amount="60")
    _cost(conn, product_id=wing, branch_id=branch_id, amount="40")
    # chicken itself: zero direct stock, confirmed before the sale.
    assert _available(conn, chicken, branch_id) == Decimal("0")

    presenter = build_sales_pos_presenter(conn, session_context=_all_permissions_session(branch_id))
    sale_id = presenter.start_sale().entity_id

    added = presenter.add_line(
        sale_id=sale_id, product_id=chicken, quantity=Decimal("2"),
        unit_price=Decimal("250.00"), product_snapshot={"name": "Pollo entero"})
    assert added.success, added.message

    # Reservation (and this fase's reconstruction top-up) only actually runs
    # via suspend today — see module docstring.
    suspended = presenter.suspend_sale(sale_id=sale_id)
    assert suspended.success, suspended.message
    resumed = presenter.resume_sale(sale_id=sale_id)
    assert resumed.success, resumed.message

    begin = presenter.begin_checkout(sale_id=sale_id)
    assert begin.success, begin.message
    payment = presenter.record_payment(sale_id=sale_id, method="CASH", amount=Decimal("500.00"))
    assert payment.success, payment.message
    checkout = presenter.checkout_sale(sale_id=sale_id)
    assert checkout.success, checkout.message

    sale = presenter.get_sale(sale_id)
    assert sale.status == "COMPLETED"

    # 2 chickens consumed 2.4kg breast, 1.6kg leg, 0.8kg wing — physically real.
    assert _available(conn, breast, branch_id) == Decimal("12") - Decimal("2.4")
    assert _available(conn, leg, branch_id) == Decimal("8") - Decimal("1.6")
    assert _available(conn, wing, branch_id) == Decimal("4") - Decimal("0.8")
    # The 2 reconstructed chickens were then sold (reserved -> issued), so
    # direct availability of the chicken itself is back to zero — not stuck
    # holding phantom stock.
    assert _available(conn, chicken, branch_id) == Decimal("0")


def test_checkout_fails_cleanly_when_parts_are_also_insufficient(conn):
    """No silent partial sale, no phantom stock — the normal "insufficient
    availability" path still applies when reconstruction can't cover it."""
    branch_id = new_uuid()
    chicken, breast, leg, wing = new_uuid(), new_uuid(), new_uuid(), new_uuid()
    _disassembly_recipe(conn, product_id=chicken, outputs=[
        {"product_id": breast, "output_type": "MAIN_PRODUCT", "quantity": "1.2", "unit_id": _UNIT},
        {"product_id": leg, "output_type": "CO_PRODUCT", "quantity": "0.8", "unit_id": _UNIT},
        {"product_id": wing, "output_type": "CO_PRODUCT", "quantity": "0.4", "unit_id": _UNIT},
    ])
    _stock(conn, product_id=breast, branch_id=branch_id, quantity="1")  # not enough for even 1
    _stock(conn, product_id=leg, branch_id=branch_id, quantity="1")
    _stock(conn, product_id=wing, branch_id=branch_id, quantity="1")
    _cost(conn, product_id=breast, branch_id=branch_id, amount="80")
    _cost(conn, product_id=leg, branch_id=branch_id, amount="60")
    _cost(conn, product_id=wing, branch_id=branch_id, amount="40")

    presenter = build_sales_pos_presenter(conn, session_context=_all_permissions_session(branch_id))
    sale_id = presenter.start_sale().entity_id
    added = presenter.add_line(
        sale_id=sale_id, product_id=chicken, quantity=Decimal("1"),
        unit_price=Decimal("250.00"), product_snapshot={"name": "Pollo entero"})
    assert added.success, added.message

    suspended = presenter.suspend_sale(sale_id=sale_id)
    assert not suspended.success

    # Nothing was consumed — the failed reconstruction attempt released
    # whatever it provisionally reserved.
    assert _available(conn, breast, branch_id) == Decimal("1")
    assert _available(conn, leg, branch_id) == Decimal("1")
    assert _available(conn, wing, branch_id) == Decimal("1")
