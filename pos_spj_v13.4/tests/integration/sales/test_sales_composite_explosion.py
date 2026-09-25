"""Vender un COMPUESTO consume sus componentes (decisión del usuario, 2026-09-24).

Productos define la composición: receta de «Explosión de venta» o combo virtual.
Ventas reserva y descuenta los componentes; el costo de venta es el de los
componentes; una devolución repone los componentes; Inventario promete lo que
alcanza el componente más escaso.

Reglas heredadas de las pruebas de la cadena legacy borrada
(`test_combo_sale_deducts_components`, `test_virtual_stock_for_combo`,
`test_recipe_resolver`): el compuesto no se descuenta a sí mismo; un producto
simple se descuenta a sí mismo; los compuestos anidados se expanden; un ciclo
no recursa sin fin (ahora es un error claro, no un descuento del compuesto);
el disponible del compuesto lo limita el componente más escaso, y es 0 sin
existencia de algún componente.
"""
from __future__ import annotations

import importlib
import json
import sqlite3
from decimal import Decimal

import pytest

from backend.application.inventory.queries.sellable_availability_query_service import (
    SellableAvailabilityQueryService,
)
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_bundle_commands import (
    BundleVersionTransitionCommand,
    CreateBundleCommand,
)
from backend.application.products.commands.product_recipe_commands import (
    CreateRecipeCommand,
    RecipeVersionTransitionCommand,
)
from backend.application.products.queries.sales_fulfillment_query_service import (
    CompositeDefinitionError,
    SalesFulfillmentQueryService,
)
from backend.application.products.use_cases.product_bundle_use_cases import (
    ActivateBundleVersionUseCase,
    ApproveBundleVersionUseCase,
    CreateProductBundleUseCase,
    SubmitBundleVersionUseCase,
)
from backend.application.products.use_cases.product_recipe_use_cases import (
    ActivateRecipeVersionUseCase,
    ApproveRecipeVersionUseCase,
    CreateProductRecipeUseCase,
    SubmitRecipeVersionUseCase,
)
from backend.application.sales.integrations.wiring import wire_sales
from backend.application.sales.permissions import SalesPermissions
from backend.application.services.finance.finance_bootstrap import bootstrap_finance
from backend.domain.pricing.entities.price_list import PriceList
from backend.domain.pricing.entities.product_cost import ProductCost
from backend.domain.pricing.entities.product_price import ProductPrice
from backend.domain.pricing.enums import PriceListKind
from backend.domain.pricing.value_objects.money import Money
from backend.infrastructure.db.repositories.pricing.pricing_repository import PricingRepository
from backend.infrastructure.db.schema.finance_schema import create_finance_schema
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.infrastructure.integrations.sales_inventory_client import SalesInventoryClient
from backend.shared.events.application_bus import ApplicationEventBus
from backend.shared.ids import new_uuid
from tests.integration._pos_ready import open_cash_shift, stock_product

_KG = "unit-kg"
_RESERVA = {"INVENTARIO.reserva.crear", "INVENTARIO.reserva.liberar", "INVENTARIO.reserva.ver"}


class _Todo:
    def has_permission(self, user_id, code):
        return True


class _Cajero:
    def __init__(self, branch_id):
        self.user_id = new_uuid()
        self.active_branch_id = branch_id
        self.is_active = True
        self._p = {p for p in vars(SalesPermissions).values() if isinstance(p, str)} | _RESERVA

    def tiene_permiso(self, code):
        return code in self._p


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_products_schema(c)
    create_pricing_schema(c)
    importlib.import_module("migrations.standalone.151_pricing_cost_tracked_quantity").run(c)
    create_inventory_schema(c)
    create_finance_schema(c)
    bootstrap_finance(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def bus(conn, monkeypatch):
    local = ApplicationEventBus()
    wire_sales(local, conn)
    import backend.shared.events.application_bus as modulo
    monkeypatch.setattr(modulo, "get_bus", lambda: local)
    return local


def _producto(conn, nombre):
    pid = new_uuid()
    conn.execute(
        "INSERT INTO products (id, code, name, name_normalized, product_type, lifecycle_status,"
        " base_unit_id, sellable, internal_only) VALUES (?,?,?,?,?,?,?,1,0)",
        (pid, f"C-{pid[-6:]}", nombre, nombre.lower(), "RESALE_PRODUCT", "ACTIVE", _KG))
    conn.commit()
    return pid


def _costo(conn, producto, monto):
    PricingRepository(conn).save_cost(ProductCost(
        product_id=producto, branch_id=None, average_cost=Money(Decimal(monto))))
    conn.commit()


def _precio(conn, producto, monto):
    repo = PricingRepository(conn)
    lista = repo.active_list_of_kind(PriceListKind.BASE)
    if lista is None:
        lista = PriceList(code="BASE", name="Base", kind=PriceListKind.BASE)
        lista.submit(); lista.approve(approved_by_user_id="mgr"); lista.activate()
        repo.save_list(lista)
    repo.save_price(ProductPrice(price_list_id=lista.id, product_id=producto,
                                 sale_price=Money(Decimal(monto))))
    conn.commit()


def _receta_de_venta(conn, producto, componentes):
    auth = ProductsAuthorizationPolicy(_Todo())
    r = CreateProductRecipeUseCase(conn, auth).execute(CreateRecipeCommand(
        operation_id=new_uuid(), product_id=producto, recipe_type="SALES_EXPLOSION",
        name="Kit", components=[{"component_product_id": p, "quantity": q, "unit_id": _KG}
                                for p, q in componentes], user_id="alice"))
    assert r.success, r.message
    for caso, quien in ((SubmitRecipeVersionUseCase, "alice"), (ApproveRecipeVersionUseCase, "bob"),
                        (ActivateRecipeVersionUseCase, "bob")):
        assert caso(conn, auth).execute(RecipeVersionTransitionCommand(
            operation_id=new_uuid(), version_id=r.version_id, user_id=quien)).success


def _combo(conn, producto, componentes, tipo="FIXED_COMBO"):
    auth = ProductsAuthorizationPolicy(_Todo())
    r = CreateProductBundleUseCase(conn, auth).execute(CreateBundleCommand(
        operation_id=new_uuid(), product_id=producto, bundle_type=tipo, name="Combo",
        components=[{"component_product_id": p, "quantity": q, "unit_id": _KG}
                    for p, q in componentes], user_id="alice"))
    assert r.success, r.message
    for caso, quien in ((SubmitBundleVersionUseCase, "alice"), (ApproveBundleVersionUseCase, "bob"),
                        (ActivateBundleVersionUseCase, "bob")):
        res = caso(conn, auth).execute(BundleVersionTransitionCommand(
            operation_id=new_uuid(), version_id=r.version_id, user_id=quien))
        assert res.success, res.message


def _saldo(conn, producto):
    fila = conn.execute("SELECT SUM(CAST(quantity AS REAL)) FROM inventory_balances"
                        " WHERE product_id=?", (producto,)).fetchone()[0]
    return Decimal(str(fila or 0)).quantize(Decimal("0.001"))


def _kit_asador(conn, branch):
    kit = _producto(conn, "Kit asador")
    arrachera, chorizo, carbon = (_producto(conn, n) for n in ("Arrachera", "Chorizo", "Carbón"))
    _receta_de_venta(conn, kit, [(arrachera, "1"), (chorizo, "0.5"), (carbon, "1")])
    for parte, cantidad, costo in ((arrachera, "10", "180"), (chorizo, "4", "90"),
                                   (carbon, "6", "40")):
        stock_product(conn, product_id=parte, branch_id=branch, quantity=cantidad)
        _costo(conn, parte, costo)
    return kit, arrachera, chorizo, carbon


def _cobrar(conn, branch, producto, cantidad, pago="1000"):
    from frontend.desktop.modules.sales_pos.composition import build_sales_pos_presenter

    cajero = _Cajero(branch)
    open_cash_shift(conn, branch_id=branch, cashier_user_id=cajero.user_id)
    pos = build_sales_pos_presenter(conn, session_context=cajero)
    sid = pos.start_sale().entity_id
    assert pos.add_line(sale_id=sid, product_id=producto, quantity=Decimal(cantidad),
                        unit_price=Decimal("1"), product_snapshot={"name": "x"}).success
    assert pos.begin_checkout(sale_id=sid).success
    assert pos.record_payment(sale_id=sid, method="CASH", amount=Decimal(pago)).success
    return pos.checkout_sale(sale_id=sid), sid


def test_selling_a_kit_consumes_its_components_not_itself(conn, bus):
    branch = new_uuid()
    kit, arrachera, chorizo, carbon = _kit_asador(conn, branch)
    _precio(conn, kit, "400")

    r, _ = _cobrar(conn, branch, kit, "2")

    assert r.success, r.message
    assert (_saldo(conn, arrachera), _saldo(conn, chorizo), _saldo(conn, carbon)) == (
        Decimal("8.000"), Decimal("3.000"), Decimal("4.000"))
    assert _saldo(conn, kit) == Decimal("0.000")
    assert conn.execute("SELECT COUNT(*) FROM inventory_reservation WHERE product_id=?",
                        (kit,)).fetchone()[0] == 0


def test_the_cost_of_selling_a_kit_is_the_cost_of_its_components(conn, bus):
    branch = new_uuid()
    kit, *_ = _kit_asador(conn, branch)
    _precio(conn, kit, "400")

    r, _ = _cobrar(conn, branch, kit, "2")

    assert r.success, r.message
    evento = json.loads(conn.execute("SELECT payload_json FROM sales_outbox"
                                     " WHERE event_name='SALE_COMPLETED'").fetchone()[0])
    # (1×180 + 0.5×90 + 1×40) × 2 = 530
    assert evento["payload"]["cogs_total"] == "530.00"
    assert evento["payload"]["cogs_missing_products"] == []


def test_a_virtual_combo_is_exploded_too(conn, bus):
    branch = new_uuid()
    combo = _producto(conn, "Caja parrillera")
    costilla, salchicha = _producto(conn, "Costilla"), _producto(conn, "Salchicha")
    _combo(conn, combo, [(costilla, "2"), (salchicha, "1")], tipo="MEAT_BOX")
    for parte in (costilla, salchicha):
        stock_product(conn, product_id=parte, branch_id=branch, quantity="10")
        _costo(conn, parte, "100")
    _precio(conn, combo, "350")

    r, _ = _cobrar(conn, branch, combo, "3", pago="1050")

    assert r.success, r.message
    assert (_saldo(conn, costilla), _saldo(conn, salchicha)) == (Decimal("4.000"),
                                                                 Decimal("7.000"))


def test_a_stocked_kit_sells_from_its_own_stock(conn):
    kit = _producto(conn, "Kit armado")
    parte = _producto(conn, "Parte")
    _combo(conn, kit, [(parte, "1")], tipo="STOCKED_KIT")
    assert SalesFulfillmentQueryService(conn).explode(kit, "2") == {kit: Decimal("2")}


def test_a_simple_product_is_fulfilled_by_itself(conn):
    simple = _producto(conn, "Bistec")
    assert SalesFulfillmentQueryService(conn).explode(simple, "1.5") == {simple: Decimal("1.5")}


def test_nested_composites_expand_to_what_is_stocked(conn):
    carne, tortilla, salsa = (_producto(conn, n) for n in ("Carne", "Tortilla", "Salsa"))
    taco = _producto(conn, "Orden de tacos")
    paquete = _producto(conn, "Paquete familiar")
    _receta_de_venta(conn, taco, [(carne, "0.2"), (tortilla, "5")])
    _combo(conn, paquete, [(taco, "3"), (salsa, "1")])

    assert SalesFulfillmentQueryService(conn).explode(paquete, "2") == {
        carne: Decimal("1.2"), tortilla: Decimal("30"), salsa: Decimal("2")}


def test_a_cycle_fails_clearly_instead_of_recursing(conn, monkeypatch):
    a, b = _producto(conn, "A"), _producto(conn, "B")
    servicio = SalesFulfillmentQueryService(conn)
    from backend.application.products.queries.sales_fulfillment_query_service import (
        FulfillmentLine,
    )
    monkeypatch.setattr(servicio, "_one_level", lambda pid, q: [
        FulfillmentLine(b if pid == a else a, q)])
    with pytest.raises(CompositeDefinitionError):
        servicio.explode(a, "1")


def test_a_product_with_both_a_sales_recipe_and_a_combo_is_refused(conn):
    doble = _producto(conn, "Doble")
    parte = _producto(conn, "Parte")
    _receta_de_venta(conn, doble, [(parte, "1")])
    _combo(conn, doble, [(parte, "2")])
    with pytest.raises(CompositeDefinitionError):
        SalesFulfillmentQueryService(conn).explode(doble, "1")


def test_what_can_be_promised_is_limited_by_the_scarcest_component(conn):
    branch = new_uuid()
    kit, arrachera, chorizo, carbon = _kit_asador(conn, branch)   # 10 / 4 (0.5 c/u) / 6
    atp = SellableAvailabilityQueryService(conn).get_sellable_availability(
        product_id=kit, branch_id=branch, warehouse_id=branch)
    assert atp.composite_buildable == Decimal("6")                # el carbón manda
    assert atp.available_to_promise == Decimal("6")


def test_a_component_without_stock_means_nothing_to_promise(conn):
    branch = new_uuid()
    kit = _producto(conn, "Kit")
    con, sin = _producto(conn, "Con"), _producto(conn, "Sin")
    _receta_de_venta(conn, kit, [(con, "1"), (sin, "1")])
    stock_product(conn, product_id=con, branch_id=branch, quantity="9")
    atp = SellableAvailabilityQueryService(conn).get_sellable_availability(
        product_id=kit, branch_id=branch, warehouse_id=branch)
    assert atp.available_to_promise == Decimal("0")


def test_returning_a_kit_restocks_its_components(conn):
    branch = new_uuid()
    kit, arrachera, chorizo, carbon = _kit_asador(conn, branch)
    cliente = SalesInventoryClient(conn, branch_id=branch, actor_user_id=new_uuid())
    cliente.restore_for_return(
        product_id=kit, quantity=Decimal("1"), sale_id=new_uuid(), operation_id=new_uuid(),
        actor_user_id=new_uuid(), reason_code="RETURN", source_document_type="SALE_RETURN")
    conn.commit()
    assert (_saldo(conn, arrachera), _saldo(conn, chorizo), _saldo(conn, carbon)) == (
        Decimal("11.000"), Decimal("4.500"), Decimal("7.000"))
    assert _saldo(conn, kit) == Decimal("0.000")
