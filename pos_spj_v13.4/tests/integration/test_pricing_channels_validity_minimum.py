"""Fase 5 (Products → Pricing) — lo que el mostrador y Delivery COBRAN.

MEDIDO ANTES DEL CAMBIO (2026-09-18, copia de la base real)
-----------------------------------------------------------
1. Vigencia ignorada: un precio de sucursal programado a 30 días se cobraba
   desde el día en que se capturaba, y uno vencido se seguía cobrando.
2. Canal ignorado: una lista de WhatsApp a 120 se cobraba también en el
   mostrador (el motor tomaba "la" lista de canal activa, cualquiera).
3. Delivery no pasaba cliente ni cantidad al motor: ni listas de cliente ni
   precios por volumen, aunque el §20 exige el mismo motor que el mostrador.
4. Un descuento dejaba Pollo (mínimo 95) en 90 sin pedir nada, y la
   autorización en caliente era inalcanzable desde el mostrador.

Decisiones del usuario: "Bajo el mínimo pide autorización" y "Sí, agregar
cliente al pedido".
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, timedelta
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from backend.application.orders_delivery.use_cases.capture_order_use_cases import (
    CaptureOrderUseCase,
)
from backend.application.pricing.authorization.policy import PricingAuthorizationPolicy
from backend.application.pricing.use_cases.price_list_use_cases import CreatePriceListUseCase
from backend.domain.orders_delivery.enums import OrderChannel
from backend.domain.pricing.entities.price_list import PriceList
from backend.domain.pricing.entities.product_price import ProductPrice, VolumePrice
from backend.domain.pricing.enums import SALE_CHANNELS, PriceListKind
from backend.domain.pricing.exceptions import InvalidPriceListError
from backend.domain.pricing.value_objects.money import Money
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.repositories.pricing.pricing_repository import PricingRepository
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.orders_delivery_schema import (
    create_orders_delivery_schema,
)
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import new_uuid
from frontend.desktop.modules.sales_pos.composition import build_sales_pos_presenter
from tests.integration._audit_trail_table import create_audit_logs_table
from tests.integration.orders_delivery.test_capture_order import (
    SUCURSAL,
    USUARIO,
    Catalogo,
    _politica,
)

HOY = date.today()


class _SesionPOS:
    """El cajero: tiene la sesión abierta y todos los permisos de SU operación."""

    def __init__(self):
        self.user_id = new_uuid()
        self.active_branch_id = SUCURSAL
        self.is_active = True

    def tiene_permiso(self, code: str) -> bool:
        return True


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_products_schema(c)
    create_pricing_schema(c)
    create_inventory_schema(c)
    create_orders_delivery_schema(c)
    create_audit_logs_table(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def catalogo(conn):
    return Catalogo(conn)


def _lista_activa(conn, code, kind, *, channel=None) -> PriceList:
    lista = PriceList(code=code, name=code, kind=kind, channel=channel)
    lista.submit()
    lista.approve(approved_by_user_id=new_uuid())
    lista.activate()
    PricingRepository(conn).save_list(lista)
    conn.commit()
    return lista


def _precio(conn, lista, producto, precio, *, branch_id="", minimo=None,
            desde=None, hasta=None) -> ProductPrice:
    pp = ProductPrice(price_list_id=lista.id, product_id=producto,
                      sale_price=Money(Decimal(precio)), branch_id=branch_id,
                      min_price=Money(Decimal(minimo)) if minimo else None,
                      effective_from=desde.isoformat() if desde else None,
                      effective_to=hasta.isoformat() if hasta else None)
    PricingRepository(conn).save_price(pp)
    conn.commit()
    return pp


def _cobro_pos(conn, producto, *, cantidad="1", sesion=None):
    """Lo que cobra el mostrador por una línea, por la composición real."""
    presenter = build_sales_pos_presenter(conn, session_context=sesion or _SesionPOS())
    venta = presenter.start_sale().entity_id
    r = presenter.add_line(sale_id=venta, product_id=producto, quantity=Decimal(cantidad),
                           unit_price=Decimal("1"), product_snapshot={"name": "x"})
    assert r.success, r.message
    return presenter.get_sale(venta).lines[0].unit_price


def _pedido(conn, producto, *, canal="POS", cantidad="1", cliente=None):
    r = CaptureOrderUseCase(_politica()).execute(
        conn, branch_id=SUCURSAL, channel=canal, fulfillment_type="COUNTER",
        lines=[{"product_id": producto, "quantity": cantidad}], actor_user_id=USUARIO,
        operation_id=new_uuid(), contact_name="Ana", customer_id=cliente)
    assert r.success, r.message
    return CustomerOrderRepository(conn).get(r.entity_id)


# ── 1. vigencia ─────────────────────────────────────────────────────────────
def test_un_precio_programado_no_se_cobra_antes_de_su_fecha(conn, catalogo):
    pollo = catalogo.producto("Pollo", precio="100")
    _precio(conn, catalogo.lista, pollo, "90", branch_id=SUCURSAL,
            desde=HOY + timedelta(days=30))

    assert _cobro_pos(conn, pollo) == Decimal("100")
    assert _pedido(conn, pollo).lines[0].unit_price_snapshot == Decimal("100")


def test_un_precio_vencido_ya_no_se_cobra(conn, catalogo):
    pollo = catalogo.producto("Pollo", precio="100")
    _precio(conn, catalogo.lista, pollo, "90", branch_id=SUCURSAL,
            desde=HOY - timedelta(days=10), hasta=HOY - timedelta(days=1))

    assert _cobro_pos(conn, pollo) == Decimal("100")


def test_un_precio_vigente_de_sucursal_si_se_cobra(conn, catalogo):
    pollo = catalogo.producto("Pollo", precio="100")
    _precio(conn, catalogo.lista, pollo, "90", branch_id=SUCURSAL,
            desde=HOY - timedelta(days=1), hasta=HOY + timedelta(days=1))

    assert _cobro_pos(conn, pollo) == Decimal("90")


# ── 2. canal ────────────────────────────────────────────────────────────────
def test_la_lista_de_whatsapp_no_se_cobra_en_el_mostrador(conn, catalogo):
    pollo = catalogo.producto("Pollo", precio="100")
    whatsapp = _lista_activa(conn, "WA", PriceListKind.CHANNEL, channel="WHATSAPP")
    _precio(conn, whatsapp, pollo, "120")

    assert _cobro_pos(conn, pollo) == Decimal("100")
    assert _pedido(conn, pollo, canal="POS").lines[0].unit_price_snapshot == Decimal("100")


def test_la_lista_de_whatsapp_si_se_cobra_en_un_pedido_de_whatsapp(conn, catalogo):
    pollo = catalogo.producto("Pollo", precio="100")
    whatsapp = _lista_activa(conn, "WA", PriceListKind.CHANNEL, channel="whatsapp")
    _precio(conn, whatsapp, pollo, "120")

    assert _pedido(conn, pollo, canal="WHATSAPP").lines[0].unit_price_snapshot == \
        Decimal("120")


# ── 3. Delivery: cliente y volumen ─────────────────────────────────────────
def test_el_pedido_guarda_al_cliente_y_le_cobra_su_lista(conn, catalogo):
    pollo = catalogo.producto("Pollo", precio="100")
    mayoreo = _lista_activa(conn, "MAYOREO", PriceListKind.CUSTOMER)
    _precio(conn, mayoreo, pollo, "85")
    cliente = new_uuid()
    PricingRepository(conn).assign_customer_list(cliente, mayoreo.id)
    conn.commit()

    pedido = _pedido(conn, pollo, cliente=cliente)

    assert pedido.customer_id == cliente
    assert pedido.lines[0].unit_price_snapshot == Decimal("85")
    # Sin cliente, el mismo producto va a precio de lista.
    assert _pedido(conn, pollo).lines[0].unit_price_snapshot == Decimal("100")


def test_el_pedido_aplica_el_precio_por_volumen(conn, catalogo):
    pollo = catalogo.producto("Pollo")
    pp = _precio(conn, catalogo.lista, pollo, "100")
    PricingRepository(conn).save_volume(VolumePrice(
        product_price_id=pp.id, min_quantity=Decimal("10"), price=Money(Decimal("80"))))
    conn.commit()

    assert _pedido(conn, pollo, cantidad="12").lines[0].unit_price_snapshot == Decimal("80")
    assert _pedido(conn, pollo, cantidad="2").lines[0].unit_price_snapshot == Decimal("100")


# ── 4. precio mínimo en descuentos del mostrador ────────────────────────────
def _seed_autorizador(conn, *, permisos=(("POS", "descuento.sobrescribir"),)) -> str:
    """Las tablas REALES contra las que `AuthorizerPermissionChecker` resuelve."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS usuarios (id TEXT PRIMARY KEY, rol TEXT);
        CREATE TABLE IF NOT EXISTS roles (id TEXT PRIMARY KEY, nombre TEXT);
        CREATE TABLE IF NOT EXISTS rol_permisos (
            rol_id TEXT, modulo TEXT, accion TEXT, permitido INTEGER);
        """)
    gerente, rol = new_uuid(), new_uuid()
    conn.execute("INSERT INTO usuarios (id, rol) VALUES (?,?)", (gerente, "gerente"))
    conn.execute("INSERT INTO roles (id, nombre) VALUES (?,?)", (rol, "gerente"))
    conn.executemany(
        "INSERT INTO rol_permisos (rol_id, modulo, accion, permitido) VALUES (?,?,?,1)",
        [(rol, m, a) for m, a in permisos])
    conn.commit()
    return gerente


@pytest.fixture
def venta_pollo(conn, catalogo):
    """Pollo a 100 con mínimo 95, una pieza en una venta del mostrador."""
    pollo = catalogo.producto("Pollo")
    _precio(conn, catalogo.lista, pollo, "100", minimo="95")
    presenter = build_sales_pos_presenter(conn, session_context=_SesionPOS())
    venta = presenter.start_sale().entity_id
    assert presenter.add_line(sale_id=venta, product_id=pollo, quantity=Decimal("1"),
                              unit_price=Decimal("100"),
                              product_snapshot={"name": "Pollo"}).success
    linea = presenter.get_sale(venta).lines[0].id
    return presenter, venta, linea


def _descuentos_auditados(conn):
    return [json.loads(r[0])["payload"] for r in conn.execute(
        "SELECT payload_json FROM sales_outbox WHERE event_name='SALE_DISCOUNT_APPLIED'")]


def test_un_descuento_que_deja_el_precio_bajo_el_minimo_pide_autorizacion(conn, venta_pollo):
    presenter, venta, linea = venta_pollo

    r = presenter.apply_line_discount(sale_id=venta, line_id=linea,
                                      discount_amount=Decimal("10"))

    assert not r.success and r.error_code == "BELOW_MINIMUM"
    assert presenter.get_sale(venta).total == Decimal("100")  # no se guardó nada
    assert _descuentos_auditados(conn) == []


def test_un_descuento_que_respeta_el_minimo_no_pide_nada(conn, venta_pollo):
    presenter, venta, linea = venta_pollo

    r = presenter.apply_line_discount(sale_id=venta, line_id=linea,
                                      discount_amount=Decimal("5"))

    assert r.success, r.message
    assert presenter.get_sale(venta).total == Decimal("95")


def test_el_descuento_de_la_venta_tambien_respeta_el_minimo(conn, venta_pollo):
    presenter, venta, _ = venta_pollo

    r = presenter.apply_sale_discount(sale_id=venta, discount_amount=Decimal("10"))

    assert not r.success and r.error_code == "BELOW_MINIMUM"


def test_otro_usuario_con_permiso_y_motivo_autoriza_y_queda_auditado(conn, venta_pollo):
    """El camino real: el gerente NO tiene la sesión (la tiene el cajero) y aun
    así autoriza, porque sus permisos se resuelven desde `rol_permisos`. Antes
    el verificador de sesión lo denegaba siempre."""
    presenter, venta, linea = venta_pollo
    gerente = _seed_autorizador(conn)

    r = presenter.apply_line_discount(
        sale_id=venta, line_id=linea, discount_amount=Decimal("10"),
        authorizer_user_id=gerente, reason="cliente frecuente")

    assert r.success, r.message
    assert presenter.get_sale(venta).total == Decimal("90")
    [evento] = _descuentos_auditados(conn)
    assert evento["authorized_by"] == gerente
    assert evento["reason"] == "cliente frecuente"
    assert evento["below_minimum"] == [{
        "line_id": linea, "product_id": evento["below_minimum"][0]["product_id"],
        "effective_unit_price": "90.00", "minimum_price": "95.00"}]


def test_bajo_el_minimo_sin_motivo_no_se_autoriza(conn, venta_pollo):
    presenter, venta, linea = venta_pollo
    gerente = _seed_autorizador(conn)

    r = presenter.apply_line_discount(sale_id=venta, line_id=linea,
                                      discount_amount=Decimal("10"),
                                      authorizer_user_id=gerente)

    # La autorización en caliente ya exigía motivo; bajo el mínimo el caso de
    # uso lo exige además por su cuenta.
    assert not r.success
    assert "motivo" in r.message
    assert presenter.get_sale(venta).total == Decimal("100")


def test_un_autorizador_sin_el_permiso_no_autoriza(conn, venta_pollo):
    presenter, venta, linea = venta_pollo
    cualquiera = _seed_autorizador(conn, permisos=(("POS", "descuento"),))

    r = presenter.apply_line_discount(
        sale_id=venta, line_id=linea, discount_amount=Decimal("10"),
        authorizer_user_id=cualquiera, reason="x")

    assert not r.success
    assert presenter.get_sale(venta).total == Decimal("100")


def test_el_cajero_no_se_autoriza_a_si_mismo(conn, venta_pollo):
    presenter, venta, linea = venta_pollo

    r = presenter.apply_line_discount(
        sale_id=venta, line_id=linea, discount_amount=Decimal("10"),
        authorizer_user_id=presenter.current_user_id(), reason="yo mismo")

    assert not r.success and r.error_code == "SEGREGATION_OF_DUTIES"


def test_una_linea_con_precio_de_cliente_bajo_el_minimo_no_bloquea_otra(conn, catalogo):
    """El precio de la lista de cliente ya bajo el mínimo es decisión de
    Precios: sin descuento en ESA línea, no debe bloquear descontar otra."""
    pollo = catalogo.producto("Pollo")
    _precio(conn, catalogo.lista, pollo, "100", minimo="95")
    res = catalogo.producto("Res")
    _precio(conn, catalogo.lista, res, "200", minimo="150")
    mayoreo = _lista_activa(conn, "MAYOREO", PriceListKind.CUSTOMER)
    _precio(conn, mayoreo, pollo, "80")
    cliente = new_uuid()
    PricingRepository(conn).assign_customer_list(cliente, mayoreo.id)
    conn.commit()

    presenter = build_sales_pos_presenter(conn, session_context=_SesionPOS())
    venta = presenter.start_sale().entity_id
    # El cliente se asigna antes de agregar líneas, como en el mostrador.
    from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork
    with SalesUnitOfWork(conn) as uow:
        sale = uow.sales.get(venta)
        sale.assign_customer(cliente)
        uow.sales.save(sale)
    for producto in (pollo, res):
        assert presenter.add_line(sale_id=venta, product_id=producto, quantity=Decimal("1"),
                                  unit_price=Decimal("1"), product_snapshot={}).success
    lineas = {l.product_id: l for l in presenter.get_sale(venta).lines}
    assert lineas[pollo].unit_price == Decimal("80")

    r = presenter.apply_line_discount(sale_id=venta, line_id=lineas[res].id,
                                      discount_amount=Decimal("20"))

    assert r.success, r.message


# ── 5. listas de canal ──────────────────────────────────────────────────────
class _Todo:
    def has_permission(self, user_id, code):
        return True


def test_una_lista_de_canal_sin_canal_no_se_crea(conn):
    r = CreatePriceListUseCase(PricingAuthorizationPolicy(_Todo())).execute(
        conn, actor_user_id="u1", code="CANAL", name="Canal", kind="CHANNEL",
        operation_id=new_uuid())

    assert not r.success and r.error_code == "VALIDATION"


def test_el_canal_se_guarda_con_el_codigo_canonico(conn):
    r = CreatePriceListUseCase(PricingAuthorizationPolicy(_Todo())).execute(
        conn, actor_user_id="u1", code="WA", name="WhatsApp", kind="CHANNEL",
        channel=" whatsapp ", operation_id=new_uuid())

    assert r.success, r.message
    assert PricingRepository(conn).get_list(r.entity_id).channel == "WHATSAPP"


def test_un_canal_desconocido_no_se_acepta(conn):
    r = CreatePriceListUseCase(PricingAuthorizationPolicy(_Todo())).execute(
        conn, actor_user_id="u1", code="X", name="X", kind="CHANNEL", channel="Mostrador",
        operation_id=new_uuid())

    assert not r.success


def test_una_lista_de_canal_sin_canal_no_se_activa_pero_si_se_lee():
    """La base real tiene una lista de canal sin canal: leerla no revienta,
    activarla sí se impide (sería una lista que no rige en ninguna venta)."""
    lista = PriceList(code="C", name="C", kind=PriceListKind.CHANNEL)
    lista.submit()
    lista.approve(approved_by_user_id="mgr")
    with pytest.raises(InvalidPriceListError):
        lista.activate()


def test_los_canales_de_precio_son_canales_reales_de_venta():
    """Si un código de `SALE_CHANNELS` no existiera en `OrderChannel`, esa
    lista no coincidiría con ningún pedido."""
    assert set(SALE_CHANNELS) <= {c.value for c in OrderChannel}
