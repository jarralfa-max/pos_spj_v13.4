"""Fase 7 (§15-19) — SellableAvailabilityQueryService: direct + reconstructible
availability, composed from real Products recipes and real Inventory balances."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.inventory.queries.sellable_availability_query_service import (
    SellableAvailabilityQueryService,
)
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_recipe_commands import (
    CreateRecipeCommand,
    RecipeVersionTransitionCommand,
)
from backend.application.products.use_cases.product_recipe_use_cases import (
    ActivateRecipeVersionUseCase,
    ApproveRecipeVersionUseCase,
    CreateProductRecipeUseCase,
    SubmitRecipeVersionUseCase,
)
from backend.domain.inventory.entities.inventory_balance import InventoryBalance
from backend.domain.inventory.enums import InventoryStatus
from backend.infrastructure.db.repositories.inventory.unit_of_work import InventoryUnitOfWork
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.shared.ids import new_uuid
from tests.integration._reversible_cutting import reversible_cutting_scheme

_UNIT = "unit-kg"


class _AllowAllChecker:
    def has_permission(self, user_id, code):
        return True


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _stock(conn, *, product_id, branch_id, quantity, reserved="0"):
    bal = InventoryBalance.empty(
        product_id=product_id, branch_id=branch_id, warehouse_id=branch_id,
        inventory_status=InventoryStatus.AVAILABLE, location_id=branch_id)
    bal.apply_delta(quantity=Decimal(quantity))
    if reserved != "0":
        bal.reserve(quantity=Decimal(reserved))
    with InventoryUnitOfWork(conn) as uow:
        uow.balances.upsert(bal)


def _despiece(conn, *, product_id, outputs, reversible=True, **_) -> str:
    """Despiece REVERSIBLE activo (esquema de corte, la fuente desde la Fase 7
    del 2026-09-19). Devuelve el id de la versión."""
    return reversible_cutting_scheme(conn, product_id=product_id, outputs=outputs,
                                     reversible=reversible)[1]


def _chicken_outputs(breast="breast", leg="leg", wing="wing"):
    return [
        {"product_id": breast, "output_type": "MAIN_PRODUCT", "quantity": "1.2", "unit_id": _UNIT},
        {"product_id": leg, "output_type": "CO_PRODUCT", "quantity": "0.8", "unit_id": _UNIT},
        {"product_id": wing, "output_type": "CO_PRODUCT", "quantity": "0.4", "unit_id": _UNIT},
    ]


class TestSellableAvailability:
    def test_direct_only_when_no_recipe_exists(self, conn):
        chicken = new_uuid()
        _stock(conn, product_id=chicken, branch_id="b1", quantity="5")

        result = SellableAvailabilityQueryService(conn).get_sellable_availability(
            product_id=chicken, branch_id="b1")

        assert result.direct == Decimal("5")
        assert result.reconstructible == Decimal("0")
        assert result.available_to_promise == Decimal("5")
        assert result.cutting_scheme_version_id is None

    def test_reconstructible_when_direct_stock_is_zero(self, conn):
        chicken, breast, leg, wing = new_uuid(), new_uuid(), new_uuid(), new_uuid()
        version_id = _despiece(
            conn, product_id=chicken, outputs=_chicken_outputs(breast, leg, wing))
        _stock(conn, product_id=breast, branch_id="b1", quantity="12")
        _stock(conn, product_id=leg, branch_id="b1", quantity="8")
        _stock(conn, product_id=wing, branch_id="b1", quantity="1.2")  # bottleneck -> 3

        result = SellableAvailabilityQueryService(conn).get_sellable_availability(
            product_id=chicken, branch_id="b1")

        assert result.direct == Decimal("0")
        assert result.reconstructible == Decimal("3")
        assert result.available_to_promise == Decimal("3")
        assert result.cutting_scheme_version_id == version_id

    def test_direct_and_reconstructible_combine(self, conn):
        chicken, breast, leg, wing = new_uuid(), new_uuid(), new_uuid(), new_uuid()
        _despiece(conn, product_id=chicken, outputs=_chicken_outputs(breast, leg, wing))
        _stock(conn, product_id=chicken, branch_id="b1", quantity="2")
        _stock(conn, product_id=breast, branch_id="b1", quantity="12")
        _stock(conn, product_id=leg, branch_id="b1", quantity="8")
        _stock(conn, product_id=wing, branch_id="b1", quantity="1.2")  # 3 reconstructible

        result = SellableAvailabilityQueryService(conn).get_sellable_availability(
            product_id=chicken, branch_id="b1")

        assert result.direct == Decimal("2")
        assert result.reconstructible == Decimal("3")
        assert result.available_to_promise == Decimal("5")

    def test_component_reservations_reduce_reconstructible_capacity(self, conn):
        """A part already reserved for its OWN direct sale must not also be
        counted as available for reconstruction — no double-booking."""
        chicken, breast, leg, wing = new_uuid(), new_uuid(), new_uuid(), new_uuid()
        _despiece(conn, product_id=chicken, outputs=_chicken_outputs(breast, leg, wing))
        _stock(conn, product_id=breast, branch_id="b1", quantity="12")
        _stock(conn, product_id=leg, branch_id="b1", quantity="8")
        _stock(conn, product_id=wing, branch_id="b1", quantity="2", reserved="1.6")  # only 0.4 free -> 1

        result = SellableAvailabilityQueryService(conn).get_sellable_availability(
            product_id=chicken, branch_id="b1")

        assert result.reconstructible == Decimal("1")

    def test_recipe_not_marked_reversible_yields_zero(self, conn):
        chicken, breast, leg, wing = new_uuid(), new_uuid(), new_uuid(), new_uuid()
        _despiece(conn, product_id=chicken, outputs=_chicken_outputs(breast, leg, wing),
                            reversible=False)
        _stock(conn, product_id=breast, branch_id="b1", quantity="12")
        _stock(conn, product_id=leg, branch_id="b1", quantity="8")
        _stock(conn, product_id=wing, branch_id="b1", quantity="1.2")

        result = SellableAvailabilityQueryService(conn).get_sellable_availability(
            product_id=chicken, branch_id="b1")

        assert result.reconstructible == Decimal("0")
        assert result.cutting_scheme_version_id is None

    def test_a_disassembly_recipe_is_no_longer_a_source(self, conn):
        """Fase 7 (decisión del usuario): la fuente es el ESQUEMA DE CORTE, el
        despiece que ejecuta Cárnico. Una receta de Desensamble activa, con las
        mismas salidas, ya no arma nada."""
        auth = ProductsAuthorizationPolicy(_AllowAllChecker())
        chicken, breast, leg, wing = new_uuid(), new_uuid(), new_uuid(), new_uuid()
        created = CreateProductRecipeUseCase(conn, auth).execute(CreateRecipeCommand(
            operation_id=new_uuid(), product_id=chicken, recipe_type="DISASSEMBLY",
            name="Despiece", user_id="alice", outputs=_chicken_outputs(breast, leg, wing)))
        assert created.success, created.message
        for caso, quien in ((SubmitRecipeVersionUseCase, "alice"),
                            (ApproveRecipeVersionUseCase, "bob"),
                            (ActivateRecipeVersionUseCase, "bob")):
            assert caso(conn, auth).execute(RecipeVersionTransitionCommand(
                operation_id=new_uuid(), version_id=created.version_id, user_id=quien)).success
        for parte in (breast, leg, wing):
            _stock(conn, product_id=parte, branch_id="b1", quantity="12")

        result = SellableAvailabilityQueryService(conn).get_sellable_availability(
            product_id=chicken, branch_id="b1")

        assert result.reconstructible == Decimal("0")

    def test_two_reversible_despieces_are_ambiguous_and_never_guessed(self, conn):
        chicken, breast, leg, wing = new_uuid(), new_uuid(), new_uuid(), new_uuid()
        _despiece(conn, product_id=chicken, outputs=_chicken_outputs(breast, leg, wing))
        _despiece(conn, product_id=chicken, outputs=_chicken_outputs(breast, leg, wing))
        for parte in (breast, leg, wing):
            _stock(conn, product_id=parte, branch_id="b1", quantity="12")

        result = SellableAvailabilityQueryService(conn).get_sellable_availability(
            product_id=chicken, branch_id="b1")

        assert result.reconstructible == Decimal("0")

    def test_an_inactive_despiece_version_does_not_count(self, conn):
        chicken, breast, leg, wing = new_uuid(), new_uuid(), new_uuid(), new_uuid()
        reversible_cutting_scheme(conn, product_id=chicken, activate=False,
                                  outputs=_chicken_outputs(breast, leg, wing))
        for parte in (breast, leg, wing):
            _stock(conn, product_id=parte, branch_id="b1", quantity="12")

        result = SellableAvailabilityQueryService(conn).get_sellable_availability(
            product_id=chicken, branch_id="b1")

        assert result.reconstructible == Decimal("0")
