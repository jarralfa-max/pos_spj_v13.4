"""Fase 6 (Ventas: Productos → Precios → Inventario → Finanzas) — el cobro.

MEDIDO ANTES DEL CAMBIO (2026-09-18, copia de la base real, sesión real)
-----------------------------------------------------------------------
Una venta de 2 Pollos quedaba COMPLETED por $200 y:
- el inventario seguía en 10: sólo SUSPENDER reservaba, y además Ventas buscaba
  la existencia con la sucursal como almacén, no en el almacén donde Compras
  recibe;
- ningún asiento: `SaleCompletedHandler` no estaba registrado y `sales_outbox`
  no tenía despachador;
- Caja no la registraba si el cajero no tenía turno, y la venta se completaba
  igual.

Decisiones del usuario: sin existencia → autorización en caliente (queda
negativo y auditado); exigir turno abierto; cajero vende, gerente autoriza.

Se prueba por la composición REAL del POS. El despacho post-commit publica en
el bus de la aplicación; aquí se sustituye por un bus LOCAL cableado con
`wire_sales`, nunca el global.
"""
from __future__ import annotations

import importlib
import json
import os
import sqlite3
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from backend.application.sales.integrations.finance_translator import sale_completed_to_finance
from backend.application.sales.integrations.wiring import dispatch_sales_outbox, wire_sales
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.use_cases.checkout_use_cases import CheckoutSaleUseCase
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
from backend.shared.events.application_bus import ApplicationEventBus
from backend.shared.ids import new_uuid
from frontend.desktop.modules.sales_pos.composition import build_sales_pos_presenter
from tests.integration._pos_ready import open_cash_shift, stock_product

_RESERVA = {"INVENTARIO.reserva.crear", "INVENTARIO.reserva.liberar", "INVENTARIO.reserva.ver"}


class _Cajero:
    def __init__(self, branch_id, permisos=None):
        self.user_id = new_uuid()
        self.active_branch_id = branch_id
        self.is_active = True
        self._permisos = set(permisos if permisos is not None else (
            {p for p in vars(SalesPermissions).values() if isinstance(p, str)} | _RESERVA))

    def tiene_permiso(self, code):
        return code in self._permisos


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_products_schema(c)
    create_pricing_schema(c)
    create_inventory_schema(c)
    create_finance_schema(c)
    bootstrap_finance(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def bus(conn, monkeypatch):
    """Bus LOCAL con Ventas cableada; el despacho post-commit del POS lo usa."""
    local = ApplicationEventBus()
    wire_sales(local, conn)
    import backend.shared.events.application_bus as modulo
    monkeypatch.setattr(modulo, "get_bus", lambda: local)
    return local


def _almacen(conn, branch_id, *, ventas=True) -> str:
    wh = new_uuid()
    conn.execute(
        "INSERT INTO warehouses (id, code, name, branch_id, warehouse_type, status,"
        " allow_sales_allocation, allow_purchase_receipt, allow_production, allow_quarantine,"
        " created_at, updated_at) VALUES (?,?,?,?,'STORE','ACTIVE',?,1,0,0,"
        " '2026-09-18','2026-09-18')", (wh, f"W-{wh[-4:]}", f"Almacén {wh[-4:]}", branch_id,
                                        1 if ventas else 0))
    conn.commit()
    return wh


def _precio_y_costo(conn, producto, *, precio="100", costo="50"):
    repo = PricingRepository(conn)
    lista = repo.active_list_of_kind(PriceListKind.BASE)
    if lista is None:
        lista = PriceList(code="BASE", name="Base", kind=PriceListKind.BASE)
        lista.submit(); lista.approve(approved_by_user_id="mgr"); lista.activate()
        repo.save_list(lista)
    repo.save_price(ProductPrice(price_list_id=lista.id, product_id=producto,
                                 sale_price=Money(Decimal(precio))))
    if costo is not None:
        repo.save_cost(ProductCost(product_id=producto, branch_id=None,
                                   average_cost=Money(Decimal(costo))))
    conn.commit()


def _venta_pagada(presenter, producto, cantidad):
    sid = presenter.start_sale().entity_id
    r = presenter.add_line(sale_id=sid, product_id=producto, quantity=Decimal(cantidad),
                           unit_price=Decimal("1"), product_snapshot={"name": "Pollo"})
    assert r.success, r.message
    total = presenter.get_sale(sid).total
    assert presenter.begin_checkout(sale_id=sid).success
    assert presenter.record_payment(sale_id=sid, method="CASH", amount=total).success
    return sid


def _saldo(conn, producto, warehouse_id):
    fila = conn.execute("SELECT quantity FROM inventory_balances WHERE product_id=? AND"
                        " warehouse_id=?", (producto, warehouse_id)).fetchone()
    return None if fila is None else Decimal(fila[0])


def _asientos(conn):
    return {r["description"].split(" ")[0] + (" de venta" if "Costo" in r["description"] else ""):
            [(Decimal(l["debit_amount"]), Decimal(l["credit_amount"])) for l in conn.execute(
                "SELECT debit_amount, credit_amount FROM journal_lines WHERE journal_entry_id=?"
                " ORDER BY line_index", (r["id"],))]
            for r in conn.execute("SELECT id, description FROM journal_entries ORDER BY rowid")}


@pytest.fixture
def mostrador(conn, bus):
    branch = new_uuid()
    wh = _almacen(conn, branch)
    pollo = new_uuid()
    _precio_y_costo(conn, pollo)
    stock_product(conn, product_id=pollo, branch_id=branch, quantity="10", warehouse_id=wh)
    cajero = _Cajero(branch)
    open_cash_shift(conn, branch_id=branch, cashier_user_id=cajero.user_id)
    return build_sales_pos_presenter(conn, session_context=cajero), pollo, wh, branch


# ── la venta normal mueve inventario, caja y contabilidad ──────────────────
def test_una_venta_descuenta_del_almacen_de_venta_y_asienta_ingreso_y_costo(conn, mostrador):
    presenter, pollo, wh, branch = mostrador
    sid = _venta_pagada(presenter, pollo, "2")

    r = presenter.checkout_sale(sale_id=sid)

    assert r.success, r.message
    assert _saldo(conn, pollo, wh) == Decimal("8")
    # Nunca de la sucursal como almacén (la fila vieja que nadie llena).
    assert _saldo(conn, pollo, branch) is None
    salida = conn.execute(
        "SELECT ll.quantity, ll.unit_cost FROM inventory_ledger l JOIN inventory_ledger_lines ll"
        " ON ll.movement_id=l.id WHERE l.movement_type='SALE_ISSUE'").fetchone()
    assert (Decimal(salida[0]), Decimal(salida[1])) == (Decimal("2"), Decimal("50"))
    asientos = _asientos(conn)
    assert asientos["Venta"] == [(Decimal("200"), Decimal("0")), (Decimal("0"), Decimal("200"))]
    assert asientos["Costo de venta"] == [(Decimal("100"), Decimal("0")),
                                         (Decimal("0"), Decimal("100"))]
    caja = conn.execute("SELECT movement_type, amount FROM cash_ledger_entries").fetchall()
    assert [(m, Decimal(a)) for m, a in caja] == [("CASH_SALE", Decimal("200"))]
    assert conn.execute("SELECT COUNT(*) FROM sales_outbox WHERE status='PENDING'").fetchone()[0] == 0


def test_repetir_el_despacho_no_duplica_asientos(conn, mostrador, bus):
    presenter, pollo, _, _ = mostrador
    sid = _venta_pagada(presenter, pollo, "1")
    assert presenter.checkout_sale(sale_id=sid).success
    conn.execute("UPDATE sales_outbox SET status='PENDING'")
    conn.commit()

    dispatch_sales_outbox(conn, bus)

    assert conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0] == 2


# ── turno de caja ───────────────────────────────────────────────────────────
def test_sin_turno_abierto_no_se_cobra_ni_se_mueve_nada(conn, bus):
    branch = new_uuid()
    wh = _almacen(conn, branch)
    pollo = new_uuid()
    _precio_y_costo(conn, pollo)
    stock_product(conn, product_id=pollo, branch_id=branch, quantity="10", warehouse_id=wh)
    presenter = build_sales_pos_presenter(conn, session_context=_Cajero(branch))

    assert presenter.open_shift_problem()  # la pantalla avisa antes de cobrar
    sid = _venta_pagada(presenter, pollo, "2")
    r = presenter.checkout_sale(sale_id=sid)

    assert not r.success and r.error_code == "NO_OPEN_CASH_SHIFT"
    assert presenter.get_sale(sid).status == "CHECKOUT_PENDING"
    assert _saldo(conn, pollo, wh) == Decimal("10")
    assert conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0] == 0


# ── sin existencia: autorización en caliente ────────────────────────────────
def _autorizador(conn, *, permisos=(("POS", "venta.sin_existencia"),)) -> str:
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
    conn.executemany("INSERT INTO rol_permisos (rol_id, modulo, accion, permitido)"
                     " VALUES (?,?,?,1)", [(rol, m, a) for m, a in permisos])
    conn.commit()
    return gerente


def test_sin_existencia_pide_autorizacion_y_no_deja_nada_retenido(conn, mostrador):
    presenter, pollo, wh, _ = mostrador
    sid = _venta_pagada(presenter, pollo, "20")

    r = presenter.checkout_sale(sale_id=sid)

    assert not r.success and r.error_code == "STOCK_AUTHORIZATION_REQUIRED"
    assert "disponible 10" in r.message
    assert presenter.get_sale(sid).status == "CHECKOUT_PENDING"
    fila = conn.execute("SELECT quantity, reserved_quantity FROM inventory_balances"
                        " WHERE product_id=?", (pollo,)).fetchone()
    assert (Decimal(fila[0]), Decimal(fila[1])) == (Decimal("10"), Decimal("0"))


def test_con_autorizacion_y_motivo_se_cobra_y_queda_negativo_y_auditado(conn, mostrador):
    presenter, pollo, wh, _ = mostrador
    gerente = _autorizador(conn)
    sid = _venta_pagada(presenter, pollo, "20")

    r = presenter.checkout_sale(sale_id=sid, authorizer_user_id=gerente,
                                reason="llega mercancía en la tarde")

    assert r.success, r.message
    assert _saldo(conn, pollo, wh) == Decimal("-10")
    evento = json.loads(conn.execute(
        "SELECT payload_json FROM sales_outbox WHERE event_name='SALE_COMPLETED'").fetchone()[0])
    assert evento["payload"]["inventory_settlement"] == "WITHOUT_STOCK_AUTHORIZED"
    assert evento["payload"]["stock_authorized_by"] == gerente
    assert evento["payload"]["stock_authorization_reason"] == "llega mercancía en la tarde"
    # El costo de venta se asienta completo aunque la existencia no alcanzara.
    assert _asientos(conn)["Costo de venta"][0] == (Decimal("1000"), Decimal("0"))


@pytest.mark.parametrize("caso", ["sin_motivo", "sin_permiso", "el_mismo_cajero"])
def test_la_autorizacion_sin_existencia_se_valida(conn, mostrador, caso):
    presenter, pollo, wh, _ = mostrador
    autoriza = {"sin_motivo": lambda: _autorizador(conn),
                "sin_permiso": lambda: _autorizador(conn, permisos=(("POS", "ver"),)),
                "el_mismo_cajero": presenter.current_user_id}[caso]()
    sid = _venta_pagada(presenter, pollo, "20")

    r = presenter.checkout_sale(sale_id=sid, authorizer_user_id=autoriza,
                                reason=None if caso == "sin_motivo" else "x")

    assert not r.success
    assert _saldo(conn, pollo, wh) == Decimal("10")


# ── almacén de venta ────────────────────────────────────────────────────────
def test_con_dos_almacenes_de_venta_no_se_adivina(conn, bus):
    branch = new_uuid()
    _almacen(conn, branch)
    _almacen(conn, branch)
    pollo = new_uuid()
    _precio_y_costo(conn, pollo)
    cajero = _Cajero(branch)
    open_cash_shift(conn, branch_id=branch, cashier_user_id=cajero.user_id)
    presenter = build_sales_pos_presenter(conn, session_context=cajero)
    sid = _venta_pagada(presenter, pollo, "1")

    r = presenter.checkout_sale(sale_id=sid)

    assert not r.success
    assert "varios almacenes" in r.message


def test_un_almacen_no_habilitado_para_venta_no_cuenta(conn, bus):
    """Sólo `allow_sales_allocation`: el almacén de sólo recepción no es de
    donde vende el mostrador."""
    branch = new_uuid()
    solo_compras = _almacen(conn, branch, ventas=False)
    venta = _almacen(conn, branch)
    pollo = new_uuid()
    _precio_y_costo(conn, pollo)
    stock_product(conn, product_id=pollo, branch_id=branch, quantity="3", warehouse_id=venta)
    stock_product(conn, product_id=pollo, branch_id=branch, quantity="9",
                  warehouse_id=solo_compras)
    cajero = _Cajero(branch)
    open_cash_shift(conn, branch_id=branch, cashier_user_id=cajero.user_id)
    presenter = build_sales_pos_presenter(conn, session_context=cajero)
    sid = _venta_pagada(presenter, pollo, "2")

    assert presenter.checkout_sale(sale_id=sid).success
    assert (_saldo(conn, pollo, venta), _saldo(conn, pollo, solo_compras)) == (
        Decimal("1"), Decimal("9"))


# ── Pedidos/Delivery: ni descuenta ni exige turno ───────────────────────────
def test_el_cobro_de_un_pedido_no_vuelve_a_descontar_inventario(conn, mostrador):
    """Pedidos descuenta por su propio cliente de inventario (ORD-8) y el
    repartidor liquida el efectivo: el cobro de su venta no debe descontar otra
    vez ni pedir turno de mostrador."""
    presenter, pollo, wh, _ = mostrador
    sid = _venta_pagada(presenter, pollo, "2")
    from backend.application.sales.authorization import SalesAuthorizationPolicy

    r = CheckoutSaleUseCase(SalesAuthorizationPolicy.permissive_for_tests(),
                            settle_inventory=False, require_cash_shift=False).execute(
        conn, sale_id=sid, actor_user_id=presenter.current_user_id(), operation_id=new_uuid())

    assert r.success, r.message
    assert _saldo(conn, pollo, wh) == Decimal("10")
    src = open(importlib.import_module(
        "backend.infrastructure.integrations.orders_delivery_sales_client").__file__,
        encoding="utf-8").read()
    assert "settle_inventory=False, require_cash_shift=False" in src


# ── traducción y despacho ───────────────────────────────────────────────────
def _sobre(**payload):
    return {"event_id": new_uuid(), "operation_id": new_uuid(), "entity_id": new_uuid(),
            "branch_id": new_uuid(), "timestamp": "2026-09-18T12:00:00+00:00",
            "payload": {"total": "90", "discount_total": "10", "tax_total": "0",
                        "payments": [], "change": "0", "cogs_total": "0", **payload}}


def test_el_efectivo_se_liquida_neto_del_cambio_y_mixto_por_metodo():
    finanzas = sale_completed_to_finance(_sobre(
        payments=[{"method": "CASH", "amount": "100"}, {"method": "CARD", "amount": "40"},
                  {"method": "TRANSFER", "amount": "0"}],
        change="50"))

    assert finanzas["settlements"] == [{"type": "CASH", "amount": "50"},
                                       {"type": "CARD", "amount": "40"}]
    assert (finanzas["gross_total"], finanzas["discount_total"], finanzas["net_total"]) == (
        "100", "10", "90")


def test_un_metodo_de_pago_sin_traduccion_no_se_asienta_a_ciegas():
    with pytest.raises(ValueError):
        sale_completed_to_finance(_sobre(payments=[{"method": "TRUEQUE", "amount": "90"}]))


def test_si_finanzas_falla_el_evento_queda_pendiente(conn):
    local = ApplicationEventBus()

    def _falla(_):
        raise RuntimeError("perfil contable ausente")

    local.subscribe("SALE_COMPLETED", _falla)
    _encolar(conn, "SALE_COMPLETED")

    resumen = dispatch_sales_outbox(conn, local)

    assert resumen["failed"] == 1
    assert _estado(conn) == "PENDING"


def test_sin_consumidor_una_venta_completada_no_se_da_por_despachada(conn):
    """Si el cableado de arranque fallara, el bus no tendría a nadie."""
    _encolar(conn, "SALE_COMPLETED")
    _encolar(conn, "SALE_STARTED")

    resumen = dispatch_sales_outbox(conn, ApplicationEventBus())

    assert resumen["without_consumer"] == 1
    assert dict(conn.execute("SELECT event_name, status FROM sales_outbox").fetchall()) == {
        "SALE_COMPLETED": "PENDING", "SALE_STARTED": "DISPATCHED"}


def _encolar(conn, evento):
    from backend.infrastructure.db.repositories.sales.outbox_repository import (
        SalesOutboxRepository,
    )
    SalesOutboxRepository(conn).enqueue(event_id=new_uuid(), event_name=evento,
                                        payload_json=json.dumps(_sobre()),
                                        operation_id=new_uuid())
    conn.commit()


def _estado(conn):
    return conn.execute("SELECT status FROM sales_outbox").fetchone()[0]


# ── crédito: una sola CxC ───────────────────────────────────────────────────
def test_la_venta_a_credito_asienta_la_cxc_sin_duplicar_la_que_registro_ventas(conn):
    from datetime import date

    from backend.application.event_handlers.finance.sale_completed_handler import (
        SaleCompletedHandler,
    )
    from backend.application.use_cases.finance.receivable_use_cases import (
        CreateReceivableUseCase,
    )
    venta, cliente = new_uuid(), new_uuid()
    # Lo que hace `SalesCreditClient.register` al cobrar a crédito.
    CreateReceivableUseCase().execute(
        conn, customer_id=cliente, amount="300", document_number="F-1",
        issue_date=date(2026, 9, 18), source_module="sales", source_document_id=venta,
        operation_id=f"{venta}:receivable")
    sobre = _sobre(total="300", discount_total="0", customer_id=cliente, sale_id=venta,
                   payments=[{"method": "CREDIT", "amount": "300"}])

    SaleCompletedHandler(conn).handle(sale_completed_to_finance(sobre))

    assert conn.execute("SELECT COUNT(*) FROM receivables").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0] == 1


# ── migración 268 ───────────────────────────────────────────────────────────
m268 = importlib.import_module("migrations.standalone.268_seed_pos_role_permissions")


def test_268_cubre_todo_el_vocabulario_del_pos():
    from backend.application.sales.permissions import ALL_SALES_PERMISSIONS
    assert {f"POS.{a}" for a in m268._POS_TODAS} == set(ALL_SALES_PERMISSIONS)


def test_268_cajero_vende_y_gerente_autoriza():
    c = sqlite3.connect(":memory:")
    c.executescript("""
        CREATE TABLE roles (id TEXT PRIMARY KEY, nombre TEXT);
        CREATE TABLE rol_permisos (id TEXT, rol_id TEXT, modulo TEXT, accion TEXT,
            permitido INTEGER, UNIQUE(rol_id, modulo, accion));
        INSERT INTO roles VALUES ('r-caj', 'Cajero'), ('r-ger', 'gerente');
    """)
    m268.run(c)
    m268.run(c)  # idempotente

    def acciones(rol):
        return {f"{m}.{a}" for m, a in c.execute(
            "SELECT modulo, accion FROM rol_permisos WHERE rol_id=?", (rol,))}

    cajero, gerente = acciones("r-caj"), acciones("r-ger")
    assert {SalesPermissions.LINE_ADD, SalesPermissions.SALE_COMPLETE,
            SalesPermissions.PAYMENT_CASH, "INVENTARIO.reserva.crear"} <= cajero
    assert not {SalesPermissions.SALE_CANCEL, SalesPermissions.SALE_WITHOUT_STOCK,
                SalesPermissions.DISCOUNT_OVERRIDE, SalesPermissions.PAYMENT_CREDIT,
                SalesPermissions.REVERSE} & cajero
    assert {SalesPermissions.SALE_WITHOUT_STOCK, SalesPermissions.DISCOUNT_OVERRIDE,
            SalesPermissions.SALE_CANCEL} <= gerente
    # Roles ausentes (admin, system_owner) se omiten: nunca se crean.
    assert c.execute("SELECT COUNT(*) FROM roles").fetchone()[0] == 2


def test_268_esta_registrada():
    from migrations.engine import MIGRATIONS
    assert "268" in {m.version for m in MIGRATIONS}
