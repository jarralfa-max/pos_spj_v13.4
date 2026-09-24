"""Fase 4 — factura → conciliación → cuenta por pagar, por la composición REAL.

Todo lo de aquí se reprodujo primero sobre una copia de la base real
(2026-09-18). La prueba que existía de esta cadena armaba los casos de uso a
mano, sin el servicio de tolerancias ni el bus de la app, y por eso no veía
nada de esto:

1. Sin las claves `procurement.tolerance.*` la conciliación REVENTABA: ninguna
   factura llegaba a CxP en producción (migración 266).
2. Una factura con IVA contra una orden salía SIEMPRE como diferencia de
   impuesto: la orden no guarda impuesto y se esperaba "0".
3. La factura de una compra de CONTADO creaba una CxP a un proveedor ya pagado
   y un segundo asiento.
4. La CxP nacía sin vencimiento.
5. "Liberar diferencia" generaba deuda desde cualquier estado, incluso sin
   recepción.

Se usa un bus LOCAL con el cableado del arranque: el de la app es global y
cablearlo aquí contaminaría las demás pruebas.
"""

import importlib
import sqlite3
from datetime import date, timedelta

import pytest

from backend.application.procurement.integrations.procurement_outbox_dispatcher import (
    dispatch_procurement_outbox,
)
from backend.application.procurement.integrations.wiring import wire_procurement
from backend.application.procurement.permissions import ALL_PURCHASE_PERMISSIONS
from backend.bootstrap.wiring.event_wiring import wire_procurement_downstream_bridges
from backend.infrastructure.db.schema.document_output_schema import (
    create_document_numbering_schema,
)
from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema
from backend.shared.events.application_bus import ApplicationEventBus
from frontend.desktop.modules.purchasing.enterprise_routes import build_enterprise_presenter
from tests.integration._supplier_cutover import apply_supplier_cutover
from tests.integration.procurement._purchase_context import seed_purchase_context

_266 = importlib.import_module("migrations.standalone.266_seed_procurement_invoice_tolerances")


class _Session:
    is_active = True
    active_branch_id = "br-1"
    active_warehouse_id = "wh-1"

    def __init__(self, user_id):
        self.user_id = user_id

    def tiene_permiso(self, code):
        return code in ALL_PURCHASE_PERMISSIONS


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_procurement_schema(c)
    create_document_numbering_schema(c)
    c.execute("CREATE TABLE IF NOT EXISTS configuraciones (clave TEXT PRIMARY KEY,"
              " valor TEXT, tipo TEXT, grupo TEXT, descripcion TEXT)")
    c.execute("CREATE TABLE proveedores(id TEXT PRIMARY KEY, nombre TEXT, activo INTEGER)")
    c.execute("INSERT INTO proveedores VALUES ('sup-1','Proveedor Uno',1)")
    apply_supplier_cutover(c)
    seed_purchase_context(c)
    _266.run(c)
    yield c
    c.close()


def _presenters(conn):
    """Quien crea la orden no la aprueba (separación de funciones)."""
    return (build_enterprise_presenter(conn, _Session("comprador")),
            build_enterprise_presenter(conn, _Session("gerente")))


def _publish(conn):
    """Lo que hace el arranque: republica el outbox en el bus y los puentes de
    Finanzas crean la CxP y su asiento."""
    bus = ApplicationEventBus()
    wire_procurement(bus, conn)
    wire_procurement_downstream_bridges(bus, conn)
    dispatch_procurement_outbox(conn, bus)


def _received_order(conn, quantity="10", price="50"):
    compras, gerente = _presenters(conn)
    for p in (compras, gerente):
        p._dispatch = None
    ok, msg, d = compras.create_order(supplier_id="sup-1", branch_id="br-1",
                                      warehouse_id="wh-1", lines=[{
                                          "product_id": "p1", "quantity": quantity,
                                          "purchase_nature": "INVENTORY",
                                          "unit_price": price, "estimated_unit_cost": price,
                                          "conversion_factor": "1"}])
    assert ok, msg
    po = d["entity_id"]
    assert gerente.approve_order(po)[0]
    assert compras.send_order(po)[0]
    ok, msg, _ = compras.receive_order(po, receipt_lines=[
        {"product_id": "p1", "received_quantity": quantity, "accepted_quantity": quantity}])
    assert ok, msg
    line = conn.execute("SELECT id FROM purchase_order_lines WHERE purchase_order_id=?",
                        (po,)).fetchone()[0]
    return compras, gerente, po, line


def _invoice(p, *, po=None, line=None, tax="0", total="500", number="F-1", **extra):
    ok, msg, d = p.capture_invoice(
        supplier_id="sup-1", invoice_number=number, total=total, purchase_order_id=po,
        lines=[{"product_id": "p1", "invoiced_quantity": "10", "unit_price": "50",
                "tax": tax, "purchase_order_line_id": line, **extra}])
    assert ok, msg
    return d["entity_id"]


def _payables(conn):
    return conn.execute("SELECT original_amount, issue_date, due_date FROM payables"
                        ).fetchall()


class TestTolerancesAreConfigured:
    def test_without_the_seeded_tolerances_matching_crashed(self, conn):
        """Fija el defecto: sin la 266 la conciliación reventaba y la pantalla
        decía "Error inesperado"."""
        conn.execute("DELETE FROM configuraciones WHERE clave LIKE 'procurement.tolerance%'")
        conn.commit()
        compras, _g, po, line = _received_order(conn)
        ok, msg, _ = compras.match_invoice(_invoice(compras, po=po, line=line))
        assert not ok and "inesperado" in msg

    def test_with_266_a_clean_invoice_matches(self, conn):
        compras, _g, po, line = _received_order(conn)
        ok, msg, d = compras.match_invoice(_invoice(compras, po=po, line=line))
        assert ok, msg
        assert d["match_result"] == "MATCHED"

    def test_the_migration_never_overwrites_an_admin_value(self, conn):
        conn.execute("UPDATE configuraciones SET valor='2'"
                     " WHERE clave='procurement.tolerance.price.default'")
        conn.commit()
        _266.run(conn)
        assert conn.execute("SELECT valor FROM configuraciones"
                            " WHERE clave='procurement.tolerance.price.default'"
                            ).fetchone()[0] == "2"


class TestTaxAgainstAnOrder:
    def test_an_invoice_with_iva_matches_and_becomes_a_payable(self, conn):
        """Antes: TAX_VARIANCE siempre, y nunca CxP."""
        compras, _g, po, line = _received_order(conn)
        ok, msg, d = compras.match_invoice(
            _invoice(compras, po=po, line=line, tax="80", total="580"))
        assert ok and d["match_result"] == "MATCHED", msg
        _publish(conn)
        assert [r[0] for r in _payables(conn)] == ["580.00"]

    def test_price_is_still_compared_exactly(self, conn):
        compras, _g, po, line = _received_order(conn)
        ok, _m, d = compras.capture_invoice(
            supplier_id="sup-1", invoice_number="F-CARO", total="550", purchase_order_id=po,
            lines=[{"product_id": "p1", "invoiced_quantity": "10", "unit_price": "55",
                    "tax": "0", "purchase_order_line_id": line}])
        assert ok
        assert compras.match_invoice(d["entity_id"])[2]["match_result"] == "PRICE_VARIANCE"


class TestDueDate:
    def test_due_date_uses_the_supplier_credit_days(self, conn):
        conn.execute("INSERT INTO supplier_commercial_terms (id, supplier_id, credit_days,"
                     " is_credit) VALUES ('t1','sup-1',15,1)")
        conn.commit()
        compras, _g, po, line = _received_order(conn)
        compras.match_invoice(_invoice(compras, po=po, line=line))
        _publish(conn)
        [(_monto, emision, vence)] = _payables(conn)
        assert date.fromisoformat(vence) == date.fromisoformat(emision) + timedelta(days=15)

    def test_a_supplier_without_terms_is_due_the_same_day(self, conn):
        compras, _g, po, line = _received_order(conn)
        compras.match_invoice(_invoice(compras, po=po, line=line))
        _publish(conn)
        [(_monto, emision, vence)] = _payables(conn)
        assert vence == emision


class TestCashPurchaseIsNotADebt:
    def test_the_invoice_of_a_cash_purchase_creates_no_payable(self, conn):
        """EL DOBLE REGISTRO. La compra de contado ya se pagó y se asentó; su
        factura es el soporte fiscal, no una deuda nueva."""
        from decimal import Decimal

        from frontend.desktop.modules.purchasing.direct_purchase_routes import (
            build_direct_purchase_presenter,
        )
        from frontend.desktop.modules.purchasing.direct_purchase_view_models import CartLineVM

        rapida = build_direct_purchase_presenter(conn, _Session("comprador"))
        rapida._dispatch = None
        ok, msg, d = rapida.create(
            supplier_id="sup-1", lines=[CartLineVM("p1", "Pollo", Decimal("10"), Decimal("50"))],
            mode="DIRECT_WITH_IMMEDIATE_RECEIPT", payment_condition="IMMEDIATE_PAYMENT",
            branch_id="br-1", warehouse_id="wh-1")
        assert ok, msg
        assert rapida.confirm(d["entity_id"], "BANK_TRANSFER")[0]
        line = conn.execute("SELECT id FROM direct_purchase_lines WHERE direct_purchase_id=?",
                            (d["entity_id"],)).fetchone()[0]
        compras, _g = _presenters(conn)
        compras._dispatch = None
        ok, msg, inv = compras.capture_invoice(
            supplier_id="sup-1", invoice_number="F-CONTADO", total="500",
            direct_purchase_id=d["entity_id"],
            lines=[{"product_id": "p1", "invoiced_quantity": "10", "unit_price": "50",
                    "tax": "0", "direct_purchase_line_id": line}])
        assert ok, msg
        ok, msg, res = compras.match_invoice(inv["entity_id"])
        assert ok and res["match_result"] == "MATCHED" and "pagó de contado" in msg
        _publish(conn)
        assert _payables(conn) == []
        # Un solo asiento: el del pago de contado.
        assert conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0] == 1


class TestWhatCanBeReleased:
    def test_an_invoice_without_receipt_cannot_be_released(self, conn):
        """Generaría deuda por mercancía que no llegó."""
        compras, gerente = _presenters(conn)
        for p in (compras, gerente):
            p._dispatch = None
        ok, msg, d = compras.create_order(supplier_id="sup-1", branch_id="br-1",
                                          warehouse_id="wh-1", lines=[{
                                              "product_id": "p1", "quantity": "10",
                                              "purchase_nature": "INVENTORY",
                                              "unit_price": "50", "conversion_factor": "1"}])
        po = d["entity_id"]
        gerente.approve_order(po)
        compras.send_order(po)
        line = conn.execute("SELECT id FROM purchase_order_lines WHERE purchase_order_id=?",
                            (po,)).fetchone()[0]
        inv = _invoice(compras, po=po, line=line)
        assert compras.match_invoice(inv)[2]["match_result"] == "MISSING_RECEIPT"
        ok, msg, _ = gerente.release_variance(inv, captured_by_user_id="comprador",
                                              reason="urge")
        assert not ok and "recepción" in msg

    def test_an_unmatched_invoice_cannot_be_released(self, conn):
        compras, gerente, po, line = _received_order(conn)
        inv = _invoice(compras, po=po, line=line)
        ok, msg, _ = gerente.release_variance(inv, captured_by_user_id="comprador",
                                              reason="urge")
        assert not ok and "no se ha conciliado" in msg

    def test_a_real_price_variance_is_released_into_a_dated_payable(self, conn):
        compras, gerente, po, line = _received_order(conn)
        ok, _m, d = compras.capture_invoice(
            supplier_id="sup-1", invoice_number="F-CARO", total="550", purchase_order_id=po,
            lines=[{"product_id": "p1", "invoiced_quantity": "10", "unit_price": "55",
                    "tax": "0", "purchase_order_line_id": line}])
        compras.match_invoice(d["entity_id"])
        ok, msg, _ = gerente.release_variance(d["entity_id"], captured_by_user_id="comprador",
                                              reason="aumento pactado")
        assert ok, msg
        _publish(conn)
        [(monto, emision, vence)] = _payables(conn)
        assert monto == "550.00" and vence == emision
