"""Nuevo pedido: `CaptureOrderUseCase` y el catálogo de captura.

LO QUE SE FIJA
--------------
- El precio sale de Pricing en el servidor; el que traiga la línea se ignora. Un
  producto sin precio vigente, o no habilitado en la sucursal, se rechaza y no se
  guarda nada.
- Un producto cuya unidad es de peso se pide por peso.
- Pedido y dirección se guardan en UNA transacción: si la zona no cubre el código
  postal no queda ni el pedido ni la dirección. Y el pedido así capturado se puede
  confirmar, porque ya trae dirección.
- Permiso real de sesión, idempotencia por `operation_id`.

Productos, unidades y precios se siembran en los esquemas canónicos de Productos y
Pricing, con las entidades de Pricing.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.permissions import (
    ALL_ORDERS_DELIVERY_PERMISSIONS,
    OrdersDeliveryPermissions as P,
)
from backend.application.orders_delivery.queries.order_capture_catalog_query_service import (
    OrderCaptureCatalogQueryService,
)
from backend.application.orders_delivery.session_authorization import (
    OrdersDeliverySessionPermissionChecker,
)
from backend.application.orders_delivery.use_cases.capture_order_use_cases import (
    CaptureOrderUseCase,
)
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    ConfirmCustomerOrderUseCase,
)
from backend.domain.orders_delivery.delivery_zone import DeliveryZone
from backend.domain.orders_delivery.enums import OrderStatus
from backend.domain.orders_delivery.value_objects.order_quantity import OrderQuantity
from backend.domain.pricing.entities.price_list import PriceList
from backend.domain.pricing.entities.product_price import ProductPrice
from backend.domain.pricing.enums import PriceListKind
from backend.domain.pricing.value_objects.money import Money
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.delivery_zone_repository import (
    DeliveryZoneRepository,
)
from backend.infrastructure.db.repositories.pricing.pricing_repository import PricingRepository
from backend.infrastructure.db.schema.orders_delivery_schema import (
    create_orders_delivery_schema,
)
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.shared.ids import new_uuid
from tests.integration._audit_trail_table import create_audit_logs_table

SUCURSAL = new_uuid()
OTRA_SUCURSAL = new_uuid()
USUARIO = new_uuid()


class _Sesion:
    is_active = True
    user_id = USUARIO
    active_branch_id = SUCURSAL

    def __init__(self, permisos=ALL_ORDERS_DELIVERY_PERMISSIONS):
        self.permisos = frozenset(permisos)

    def tiene_permiso(self, code):
        return code in self.permisos


def _politica(permisos=ALL_ORDERS_DELIVERY_PERMISSIONS):
    return OrdersDeliveryAuthorizationPolicy(OrdersDeliverySessionPermissionChecker(_Sesion(permisos)))


class Catalogo:
    """Siembra de productos, unidades y precios en los esquemas canónicos."""

    def __init__(self, conn):
        self.conn = conn
        repo = PricingRepository(conn)
        self.lista = PriceList(code="BASE", name="Base", kind=PriceListKind.BASE)
        self.lista.submit()
        self.lista.approve(approved_by_user_id=new_uuid())
        self.lista.activate()
        repo.save_list(self.lista)
        self.pza = self._unidad("PZA", "COUNT")
        self.kg = self._unidad("KG", "WEIGHT")

    def _unidad(self, code, dimension):
        uid = new_uuid()
        self.conn.execute("INSERT INTO units_of_measure (id, code, name, dimension, active)"
                          " VALUES (?,?,?,?,1)", (uid, code, code, dimension))
        return uid

    def producto(self, nombre, *, precio=None, unidad=None, branch_id=SUCURSAL):
        pid = new_uuid()
        self.conn.execute(
            "INSERT INTO products (id, code, name, name_normalized, product_type, lifecycle_status,"
            " base_unit_id, sellable, internal_only) VALUES (?,?,?,?,?,?,?,1,0)",
            (pid, f"C-{pid[-6:]}", nombre, nombre.lower(), "RESALE_PRODUCT", "ACTIVE",
             unidad or self.pza))
        self.conn.execute("INSERT INTO branch_product (id, product_id, branch_id, enabled)"
                          " VALUES (?,?,?,1)", (new_uuid(), pid, branch_id))
        if precio is not None:
            PricingRepository(self.conn).save_price(ProductPrice(
                price_list_id=self.lista.id, product_id=pid, sale_price=Money(Decimal(precio))))
        self.conn.commit()
        return pid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    create_pricing_schema(c)
    create_orders_delivery_schema(c)
    create_audit_logs_table(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def catalogo(conn):
    return Catalogo(conn)


def _capturar(conn, lineas, *, politica=None, modalidad="COUNTER", direccion=None,
              operation_id=None):
    return CaptureOrderUseCase(politica or _politica()).execute(
        conn, branch_id=SUCURSAL, channel="POS", fulfillment_type=modalidad, lines=lineas,
        actor_user_id=USUARIO, operation_id=operation_id or new_uuid(), contact_name="Ana",
        address=direccion)


def _pedidos(conn):
    return conn.execute("SELECT COUNT(*) FROM customer_orders").fetchone()[0]


def _direccion(codigo="06000"):
    return {"recipient_name": "Ana", "recipient_phone": "5555555555", "street": "Reforma",
            "exterior_number": "100", "postal_code": codigo}


def _zona(conn, codigo="06000", costo="35"):
    DeliveryZoneRepository(conn).save(DeliveryZone.create(
        branch_id=SUCURSAL, name="Centro", postal_codes=(codigo,), delivery_fee=Decimal(costo)))
    conn.commit()


# -- catálogo ------------------------------------------------------------------------
def test_the_catalog_lists_what_can_be_ordered_with_price_and_unit(conn, catalogo):
    catalogo.producto("Arrachera", precio="320", unidad=catalogo.kg)
    catalogo.producto("Tortillas")                       # sin precio
    catalogo.producto("Chorizo", precio="90", branch_id=OTRA_SUCURSAL)  # otra sucursal

    items = {i.name: i for i in OrderCaptureCatalogQueryService(conn).search(branch_id=SUCURSAL)}

    assert set(items) == {"Arrachera", "Tortillas"}
    assert (items["Arrachera"].price, items["Arrachera"].unit_code, items["Arrachera"].weighed) == (
        Decimal("320"), "KG", True)
    assert (items["Tortillas"].price, items["Tortillas"].weighed) == (None, False)


# -- precio y líneas ----------------------------------------------------------------
def test_the_price_comes_from_pricing_not_from_the_capture(conn, catalogo):
    refresco = catalogo.producto("Refresco", precio="25")

    resultado = _capturar(conn, [{"product_id": refresco, "quantity": "2", "unit_price": "1"}])

    assert resultado.success, resultado.message
    pedido = CustomerOrderRepository(conn).get(resultado.entity_id)
    assert pedido.lines[0].unit_price_snapshot == Decimal("25")
    assert pedido.totals.subtotal == Decimal("50")


def test_a_product_without_a_price_is_refused_and_nothing_is_saved(conn, catalogo):
    con_precio = catalogo.producto("Refresco", precio="25")
    sin_precio = catalogo.producto("Tortillas")

    resultado = _capturar(conn, [{"product_id": con_precio, "quantity": "1"},
                                 {"product_id": sin_precio, "quantity": "1"}])

    assert resultado.error_code == "PRODUCT_NOT_AVAILABLE"
    assert "Tortillas" in resultado.message
    assert _pedidos(conn) == 0


def test_a_product_of_another_branch_is_refused(conn, catalogo):
    ajeno = catalogo.producto("Chorizo", precio="90", branch_id=OTRA_SUCURSAL)

    assert _capturar(conn, [{"product_id": ajeno, "quantity": "1"}]).error_code == (
        "PRODUCT_NOT_AVAILABLE")
    assert _pedidos(conn) == 0


def test_a_weighed_product_is_ordered_by_weight(conn, catalogo):
    arrachera = catalogo.producto("Arrachera", precio="320", unidad=catalogo.kg)

    resultado = _capturar(conn, [{"product_id": arrachera, "quantity": "1.5"}])

    assert resultado.success, resultado.message
    [linea] = CustomerOrderRepository(conn).get(resultado.entity_id).lines
    assert linea.requested_weight == OrderQuantity(Decimal("1.5"), "KG")
    assert linea.requested_quantity is None


@pytest.mark.parametrize("lineas, codigo", [
    ([], "EMPTY_ORDER"),
    ("cantidad_invalida", "INVALID_QUANTITY"),
], ids=["sin_lineas", "cantidad_invalida"])
def test_an_incomplete_order_is_refused(conn, catalogo, lineas, codigo):
    if lineas == "cantidad_invalida":
        lineas = [{"product_id": catalogo.producto("Refresco", precio="25"), "quantity": "abc"}]

    assert _capturar(conn, lineas).error_code == codigo
    assert _pedidos(conn) == 0


# -- dirección en la misma transacción -------------------------------------------------
def test_a_home_delivery_saves_order_and_address_together(conn, catalogo):
    _zona(conn, "06000", costo="35")
    refresco = catalogo.producto("Refresco", precio="25")

    resultado = _capturar(conn, [{"product_id": refresco, "quantity": "4"}],
                          modalidad="HOME_DELIVERY", direccion=_direccion("06000"))

    assert resultado.success, resultado.message
    pedido = CustomerOrderRepository(conn).get(resultado.entity_id)
    assert pedido.delivery_address_id is not None
    assert (pedido.delivery_fee, pedido.totals.grand_total) == (Decimal("35"), Decimal("135"))
    assert conn.execute("SELECT COUNT(*) FROM order_addresses").fetchone()[0] == 1
    confirmado = ConfirmCustomerOrderUseCase(_politica()).execute(
        conn, order_id=pedido.id, actor_user_id=USUARIO, operation_id=new_uuid())
    assert confirmado.success, confirmado.message
    assert CustomerOrderRepository(conn).get(pedido.id).status is OrderStatus.CONFIRMED


def test_when_no_zone_covers_the_address_nothing_is_saved(conn, catalogo):
    _zona(conn, "06000")
    refresco = catalogo.producto("Refresco", precio="25")

    resultado = _capturar(conn, [{"product_id": refresco, "quantity": "1"}],
                          modalidad="HOME_DELIVERY", direccion=_direccion("99999"))

    assert resultado.error_code == "DELIVERY_ZONE_NOT_AVAILABLE"
    assert _pedidos(conn) == 0
    assert conn.execute("SELECT COUNT(*) FROM order_addresses").fetchone()[0] == 0


def test_a_home_delivery_without_address_is_refused(conn, catalogo):
    refresco = catalogo.producto("Refresco", precio="25")

    resultado = _capturar(conn, [{"product_id": refresco, "quantity": "1"}],
                          modalidad="HOME_DELIVERY")

    assert resultado.error_code == "DELIVERY_ADDRESS_REQUIRED"
    assert _pedidos(conn) == 0


def test_a_counter_order_ignores_any_address(conn, catalogo):
    refresco = catalogo.producto("Refresco", precio="25")

    resultado = _capturar(conn, [{"product_id": refresco, "quantity": "1"}],
                          direccion=_direccion("99999"))

    assert resultado.success, resultado.message
    assert CustomerOrderRepository(conn).get(resultado.entity_id).delivery_address_id is None


# -- permiso, idempotencia y auditoría ------------------------------------------------------
def test_capturing_requires_the_create_permission(conn, catalogo):
    refresco = catalogo.producto("Refresco", precio="25")

    resultado = _capturar(conn, [{"product_id": refresco, "quantity": "1"}],
                          politica=_politica({P.VIEW_OWN_BRANCH}))

    assert resultado.error_code == "PERMISSION_DENIED"
    assert _pedidos(conn) == 0


def test_the_same_operation_is_captured_once(conn, catalogo):
    refresco = catalogo.producto("Refresco", precio="25")
    operacion = new_uuid()

    primero = _capturar(conn, [{"product_id": refresco, "quantity": "1"}], operation_id=operacion)
    segundo = _capturar(conn, [{"product_id": refresco, "quantity": "1"}], operation_id=operacion)

    assert primero.entity_id == segundo.entity_id
    assert _pedidos(conn) == 1


def test_the_capture_is_audited_with_its_address(conn, catalogo):
    _zona(conn, "06000")
    refresco = catalogo.producto("Refresco", precio="25")

    _capturar(conn, [{"product_id": refresco, "quantity": "1"}],
              modalidad="HOME_DELIVERY", direccion=_direccion("06000"))

    acciones = [r[0] for r in conn.execute(
        "SELECT accion FROM audit_logs WHERE modulo='DELIVERY' ORDER BY rowid").fetchall()]
    assert acciones == ["ORDER_CREATED", "ORDER_DELIVERY_ADDRESS_SET"]
