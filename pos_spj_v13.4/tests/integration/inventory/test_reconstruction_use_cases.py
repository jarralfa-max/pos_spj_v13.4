"""Fase 7 (§15-19) — ReconstructBaseProductUseCase: the real write side of
reverse recipe reconstruction, against real Products/Inventory/Pricing
schemas on one connection."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.queries.availability_query_service import (
    InventoryAvailabilityQueryService,
)
from backend.application.inventory.use_cases.reconstruction_use_cases import (
    ReconstructBaseProductUseCase,
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
from backend.domain.inventory.entities.inventory_balance import InventoryBalance
from backend.domain.inventory.enums import InventoryStatus
from backend.domain.pricing.entities.product_cost import ProductCost
from backend.domain.pricing.value_objects.money import Money
from backend.infrastructure.db.repositories.inventory.unit_of_work import InventoryUnitOfWork
from backend.infrastructure.db.repositories.pricing.pricing_repository import PricingRepository
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.shared.ids import new_uuid

_UNIT = "unit-kg"
_BRANCH = "b1"


class _AllowAllChecker:
    def has_permission(self, user_id, code):
        return True


def _perms() -> InventoryAuthorizationPolicy:
    return InventoryAuthorizationPolicy.permissive_for_tests()


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    create_inventory_schema(c)
    create_pricing_schema(c)
    c.commit()
    yield c
    c.close()


def _stock(conn, *, product_id, quantity, branch_id=_BRANCH):
    bal = InventoryBalance.empty(
        product_id=product_id, branch_id=branch_id, warehouse_id=branch_id,
        inventory_status=InventoryStatus.AVAILABLE, location_id=branch_id)
    bal.apply_delta(quantity=Decimal(quantity))
    with InventoryUnitOfWork(conn) as uow:
        uow.balances.upsert(bal)


def _cost(conn, *, product_id, amount, branch_id=_BRANCH):
    PricingRepository(conn).save_cost(ProductCost(
        product_id=product_id, branch_id=branch_id, average_cost=Money(Decimal(amount))))


def _available(conn, product_id, branch_id=_BRANCH) -> Decimal:
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id=product_id, branch_id=branch_id).available


def _disassembly_recipe(conn, *, product_id, outputs, creator="alice", approver="bob") -> str:
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
    return version_id


def _chicken_outputs(breast, leg, wing):
    return [
        {"product_id": breast, "output_type": "MAIN_PRODUCT", "quantity": "1.2", "unit_id": _UNIT},
        {"product_id": leg, "output_type": "CO_PRODUCT", "quantity": "0.8", "unit_id": _UNIT},
        {"product_id": wing, "output_type": "CO_PRODUCT", "quantity": "0.4", "unit_id": _UNIT},
    ]


class TestReconstructBaseProductUseCase:
    def test_reconstructs_and_consumes_the_right_components(self, conn):
        chicken, breast, leg, wing = new_uuid(), new_uuid(), new_uuid(), new_uuid()
        _disassembly_recipe(conn, product_id=chicken, outputs=_chicken_outputs(breast, leg, wing))
        _stock(conn, product_id=breast, quantity="12")
        _stock(conn, product_id=leg, quantity="8")
        _stock(conn, product_id=wing, quantity="4")
        _cost(conn, product_id=breast, amount="80")
        _cost(conn, product_id=leg, amount="60")
        _cost(conn, product_id=wing, amount="40")

        result = ReconstructBaseProductUseCase(_perms()).execute(
            conn, product_id=chicken, quantity=Decimal("2"), branch_id=_BRANCH,
            warehouse_id=_BRANCH, actor_user_id="u1", operation_id="recon-1")

        assert result.success, result.message
        # 2 chickens need 2.4kg breast, 1.6kg leg, 0.8kg wing.
        assert _available(conn, breast) == Decimal("12") - Decimal("2.4")
        assert _available(conn, leg) == Decimal("8") - Decimal("1.6")
        assert _available(conn, wing) == Decimal("4") - Decimal("0.8")
        assert _available(conn, chicken) == Decimal("2")

        # cost = (2.4*80 + 1.6*60 + 0.8*40) / 2 = (192+96+32)/2 = 160
        assert Decimal(result.data["unit_cost"]) == Decimal("160")

    def test_insufficient_component_stock_leaves_nothing_committed(self, conn):
        chicken, breast, leg, wing = new_uuid(), new_uuid(), new_uuid(), new_uuid()
        _disassembly_recipe(conn, product_id=chicken, outputs=_chicken_outputs(breast, leg, wing))
        _stock(conn, product_id=breast, quantity="12")
        _stock(conn, product_id=leg, quantity="8")
        _stock(conn, product_id=wing, quantity="0.1")  # not enough for even 1 chicken (needs 0.4)
        _cost(conn, product_id=breast, amount="80")
        _cost(conn, product_id=leg, amount="60")
        _cost(conn, product_id=wing, amount="40")

        result = ReconstructBaseProductUseCase(_perms()).execute(
            conn, product_id=chicken, quantity=Decimal("1"), branch_id=_BRANCH,
            warehouse_id=_BRANCH, actor_user_id="u1", operation_id="recon-2")

        assert not result.success
        # breast/leg reservations (attempted before the failing wing) must
        # have been released, not left dangling.
        assert _available(conn, breast) == Decimal("12")
        assert _available(conn, leg) == Decimal("8")
        assert _available(conn, chicken) == Decimal("0")

    def test_missing_component_cost_fails_closed_not_invented(self, conn):
        chicken, breast, leg, wing = new_uuid(), new_uuid(), new_uuid(), new_uuid()
        _disassembly_recipe(conn, product_id=chicken, outputs=_chicken_outputs(breast, leg, wing))
        _stock(conn, product_id=breast, quantity="12")
        _stock(conn, product_id=leg, quantity="8")
        _stock(conn, product_id=wing, quantity="4")
        _cost(conn, product_id=breast, amount="80")
        _cost(conn, product_id=leg, amount="60")
        # wing cost deliberately NOT configured

        result = ReconstructBaseProductUseCase(_perms()).execute(
            conn, product_id=chicken, quantity=Decimal("1"), branch_id=_BRANCH,
            warehouse_id=_BRANCH, actor_user_id="u1", operation_id="recon-3")

        assert not result.success
        assert result.error_code == "MISSING_COMPONENT_COST"
        assert _available(conn, breast) == Decimal("12")
        assert _available(conn, leg) == Decimal("8")

    def test_no_reversible_recipe_fails_closed(self, conn):
        result = ReconstructBaseProductUseCase(_perms()).execute(
            conn, product_id=new_uuid(), quantity=Decimal("1"), branch_id=_BRANCH,
            warehouse_id=_BRANCH, actor_user_id="u1", operation_id="recon-4")

        assert not result.success
        assert result.error_code == "NOT_RECONSTRUCTIBLE"

    def test_idempotent_retry_does_not_double_reconstruct(self, conn):
        chicken, breast, leg, wing = new_uuid(), new_uuid(), new_uuid(), new_uuid()
        _disassembly_recipe(conn, product_id=chicken, outputs=_chicken_outputs(breast, leg, wing))
        _stock(conn, product_id=breast, quantity="12")
        _stock(conn, product_id=leg, quantity="8")
        _stock(conn, product_id=wing, quantity="4")
        _cost(conn, product_id=breast, amount="80")
        _cost(conn, product_id=leg, amount="60")
        _cost(conn, product_id=wing, amount="40")

        uc = ReconstructBaseProductUseCase(_perms())
        first = uc.execute(conn, product_id=chicken, quantity=Decimal("1"), branch_id=_BRANCH,
                           warehouse_id=_BRANCH, actor_user_id="u1", operation_id="recon-5")
        assert first.success
        second = uc.execute(conn, product_id=chicken, quantity=Decimal("1"), branch_id=_BRANCH,
                            warehouse_id=_BRANCH, actor_user_id="u1", operation_id="recon-5")
        assert second.success
        assert second.data.get("already_processed") or second.entity_id == first.entity_id

        # Only ONE chicken's worth of parts consumed, not two.
        assert _available(conn, breast) == Decimal("12") - Decimal("1.2")
        assert _available(conn, chicken) == Decimal("1")
