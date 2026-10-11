"""Cotizaciones (CRM-43, §50) con la base completa y el presentador REAL por rol.

Decisiones del usuario (2026-10-09) que se fijan aquí:
* aceptada → Pedido tipo «Cotización convertida» a precios cotizados;
* precio bajo lista → la aprueba OTRA persona con permiso; a lista no se aprueba;
* roles como el CRM (cajero las suyas sin aprobar; gerente su sucursal y aprueba);
* vive dentro de Clientes y CRM.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from backend.application.crm.background_cycle import run_crm_background_cycle
from tests.integration.crm43.conftest import add_branch, add_product, new_customer, presenter_for

_SOON = (date.today() + timedelta(days=15)).isoformat()


def _customer(owner, name="Restaurante El Sol"):
    return new_customer(owner, name)


def _quote(presenter, customer, lines=(), **kw):
    result = presenter.run("create_quote", customer_id=customer, branch_id=presenter.branch_id(),
                           valid_until=_SOON, lines=list(lines), **kw)
    assert result.success, result.message
    return result.entity_id


def _status(conn, quote_id):
    return conn.execute("SELECT status FROM quotes WHERE id=?", (quote_id,)).fetchone()[0]


class TestLifecycle:
    def test_list_price_quote_needs_no_approval_and_becomes_an_order(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = _customer(owner)
        steak = add_product(conn, "Arrachera", "250.00", unit="KG")
        soda = add_product(conn, "Refresco", "20.00")
        quote = _quote(owner, customer, [{"product_id": steak, "quantity": "2.5"},
                                         {"product_id": soda, "quantity": "10"}])

        submitted = owner.run("submit_quote", quote_id=quote)
        assert submitted.success and _status(conn, quote) == "APPROVED"
        assert owner.run("send_quote", quote_id=quote).success
        assert owner.run("accept_quote", quote_id=quote).success
        converted = owner.run("convert_quote", quote_id=quote, fulfillment_type="PICKUP")
        assert converted.success, converted.message

        order = conn.execute(
            "SELECT id, order_type, channel, quote_id, customer_id, status, grand_total"
            " FROM customer_orders WHERE quote_id=?", (quote,)).fetchone()
        assert tuple(order)[1:6] == ("QUOTE_CONVERTED", "SALES_REP", quote, customer, "DRAFT")
        assert Decimal(order["grand_total"]) == Decimal("825.00")
        weights = conn.execute("SELECT requested_weight, requested_quantity, unit_price_snapshot"
                               " FROM customer_order_lines WHERE order_id=? ORDER BY CAST(unit_price_snapshot AS REAL)",
                               (order["id"],)).fetchall()
        assert [tuple(w) for w in weights] == [(None, "10.000", "20.00"),
                                               ("2.500", None, "250.00")]
        assert _status(conn, quote) == "CONVERTED"
        again = owner.run("convert_quote", quote_id=quote, fulfillment_type="PICKUP")
        assert again.success and again.entity_id == order["id"]
        assert conn.execute("SELECT COUNT(*) FROM customer_orders WHERE quote_id=?",
                            (quote,)).fetchone()[0] == 1

    def test_price_below_list_needs_someone_else_to_approve(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = _customer(owner)
        product = add_product(conn, "Costilla", "180.00", unit="KG", min_price="150.00")
        cashier, _ = presenter_for(conn, "cajero")
        quote = _quote(cashier, customer, [{"product_id": product, "quantity": "5",
                                            "unit_price": "140.00"}])
        detail = cashier.read("quote_detail", quote_id=quote).quote
        assert detail.requires_approval and detail.lines[0].below_minimum
        assert detail.discount_total == Decimal("200.00")

        assert "aprobación" in cashier.run("submit_quote", quote_id=quote).message
        assert _status(conn, quote) == "PENDING_APPROVAL"
        denied = cashier.run("approve_quote", quote_id=quote)
        assert not denied.success and denied.error_code == "PERMISSION_DENIED"
        assert not cashier.run("send_quote", quote_id=quote).success

        manager, _ = presenter_for(conn, "gerente")
        assert [q.id for q in manager.read("quote_approvals")] == [quote]
        assert manager.run("approve_quote", quote_id=quote, note="Cliente frecuente").success
        assert _status(conn, quote) == "APPROVED"

    def test_creator_never_approves_own_prices(self, conn):
        manager, _ = presenter_for(conn, "gerente")
        owner, _ = presenter_for(conn, "system_owner")
        customer = _customer(owner)
        product = add_product(conn, "Chorizo", "90.00")
        quote = _quote(manager, customer, [{"product_id": product, "quantity": "3",
                                            "unit_price": "80"}])
        manager.run("submit_quote", quote_id=quote)
        own = manager.run("approve_quote", quote_id=quote)
        assert not own.success and own.error_code == "SEGREGATION"
        assert owner.run("approve_quote", quote_id=quote).success

    def test_returned_to_draft_can_be_corrected(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = _customer(owner)
        product = add_product(conn, "Pollo", "70.00", unit="KG")
        cashier, _ = presenter_for(conn, "cajero")
        quote = _quote(cashier, customer, [{"product_id": product, "quantity": "4",
                                            "unit_price": "60"}])
        cashier.run("submit_quote", quote_id=quote)
        manager, _ = presenter_for(conn, "gerente")
        assert manager.run("return_quote_to_draft", quote_id=quote,
                           reason="Muy bajo; máximo 10% de descuento").success
        line = cashier.read("quote_detail", quote_id=quote).quote.lines[0]
        assert cashier.run("update_quote_line", quote_id=quote, line_id=line.id,
                           unit_price="70.00").success
        assert cashier.run("submit_quote", quote_id=quote).success
        assert _status(conn, quote) == "APPROVED"

    def test_rejected_quote_gets_a_new_version_with_fresh_list_prices(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = _customer(owner)
        product = add_product(conn, "Queso", "100.00")
        quote = _quote(owner, customer, [{"product_id": product, "quantity": "2"}])
        owner.run("submit_quote", quote_id=quote)
        owner.run("send_quote", quote_id=quote)
        assert owner.run("reject_quote", quote_id=quote, reason="Muy caro").success
        conn.execute("UPDATE product_price SET sale_price='95.00' WHERE product_id=?", (product,))
        conn.commit()

        revised = owner.run("revise_quote", quote_id=quote, valid_until=_SOON)
        assert revised.success, revised.message
        new = owner.read("quote_detail", quote_id=revised.entity_id).quote
        assert new.quote_number.endswith("/2") and new.revision == 2
        assert new.status.value == "DRAFT" and new.parent_quote_id == quote
        assert new.lines[0].list_price == Decimal("95.00")
        assert new.lines[0].unit_price == Decimal("95.00")

    def test_expired_quote_closes_itself(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = _customer(owner)
        product = add_product(conn, "Tortilla", "25.00", unit="KG")
        quote = _quote(owner, customer, [{"product_id": product, "quantity": "1"}])
        owner.run("submit_quote", quote_id=quote)
        owner.run("send_quote", quote_id=quote)
        conn.execute("UPDATE quotes SET valid_until=? WHERE id=?",
                     ((date.today() - timedelta(days=1)).isoformat(), quote))
        conn.commit()

        assert run_crm_background_cycle(conn).quotes_expired == 1
        assert _status(conn, quote) == "EXPIRED"
        late = owner.run("accept_quote", quote_id=quote)
        assert not late.success


class TestRules:
    def test_public_customer_cannot_be_quoted(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        public = conn.execute("SELECT id FROM customers WHERE customer_type='PUBLIC_CUSTOMER'"
                              ).fetchone()
        customer = public[0] if public else new_customer(
            owner, "Público", customer_type="PUBLIC_CUSTOMER")
        result = owner.run("create_quote", customer_id=customer, branch_id=owner.branch_id(),
                           valid_until=_SOON, lines=[])
        assert not result.success and "público en general" in result.message

    def test_product_not_sold_in_branch_or_without_price_is_refused(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = _customer(owner)
        north = add_branch(conn, "Norte")
        elsewhere = add_product(conn, "Sólo en el norte", "10.00", branch=north)
        quote = _quote(owner, customer)
        refused = owner.run("add_quote_line", quote_id=quote, product_id=elsewhere, quantity="1")
        assert not refused.success and "no se vende en esta sucursal" in refused.message

    def test_past_validity_is_refused(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = _customer(owner)
        result = owner.run("create_quote", customer_id=customer, branch_id=owner.branch_id(),
                           valid_until=(date.today() - timedelta(days=1)).isoformat())
        assert not result.success and "fecha pasada" in result.message

    def test_quote_from_opportunity_takes_its_customer(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = _customer(owner)
        opp = owner.run("create_opportunity", customer_id=customer, name="Banquete fin de año",
                        origin_branch_id=owner.branch_id()).entity_id
        result = owner.run("create_quote", opportunity_id=opp, branch_id=owner.branch_id(),
                           valid_until=_SOON)
        assert result.success, result.message
        assert [q.id for q in owner.read("quotes", opportunity_id=opp)] == [result.entity_id]
        row = conn.execute("SELECT customer_id FROM quotes WHERE id=?",
                           (result.entity_id,)).fetchone()
        assert row[0] == customer


class TestScopeAndRoles:
    def test_cashier_sees_and_edits_only_own_quotes(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = _customer(owner)
        product = add_product(conn, "Salchicha", "50.00")
        cashier, _ = presenter_for(conn, "cajero")
        other, _ = presenter_for(conn, "cajero")
        mine = _quote(cashier, customer)
        theirs = _quote(other, customer)

        assert [q.id for q in cashier.read("quotes")] == [mine]
        denied = cashier.run("add_quote_line", quote_id=theirs, product_id=product, quantity="1")
        assert denied.error_code == "OUT_OF_SCOPE"
        manager, _ = presenter_for(conn, "gerente")
        assert {q.id for q in manager.read("quotes")} == {mine, theirs}

    def test_read_only_and_warehouse(self, conn):
        reader, _ = presenter_for(conn, "solo_lectura")
        assert reader.can("COTIZACIONES.ver") and not reader.can("COTIZACIONES.crear")
        warehouse, _ = presenter_for(conn, "almacen")
        assert not warehouse.can("COTIZACIONES.ver")


class TestDocumentsAndHistory:
    def test_pdf_only_after_approval(self, conn, tmp_path):
        owner, _ = presenter_for(conn, "system_owner")
        customer = _customer(owner)
        product = add_product(conn, "Bistec", "190.00", unit="KG")
        quote = _quote(owner, customer, [{"product_id": product, "quantity": "3"}],
                       notes="Entrega el sábado. Pago contra entrega.")
        path = str(tmp_path / "cot.pdf")
        draft = owner.run("export_quote_pdf", quote_id=quote, path=path)
        assert not draft.success and not os.path.exists(path)
        owner.run("submit_quote", quote_id=quote)
        assert owner.run("export_quote_pdf", quote_id=quote, path=path).success
        with open(path, "rb") as fh:
            assert fh.read(4) == b"%PDF"

    def test_customer_history_lists_canonical_quotes(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = _customer(owner)
        quote = _quote(owner, customer)
        history = owner.read("quote_history", customer_id=customer)
        assert [h["id"] for h in history] == [quote]

    def test_legacy_quotes_are_copied_once(self, conn):
        import importlib
        owner, _ = presenter_for(conn, "system_owner")
        customer = _customer(owner)
        legacy_customer = "legacy-cli-1"
        conn.execute("UPDATE customers SET legacy_customer_id=? WHERE id=?",
                     (legacy_customer, customer))
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("INSERT INTO cotizaciones (id, folio, cliente_id, total, estado,"
                     " fecha_vencimiento) VALUES ('old-1', 'C-7', ?, 500, 'pendiente', ?)",
                     (legacy_customer, _SOON))
        conn.execute("INSERT INTO cotizaciones_detalle (id, cotizacion_id, nombre, cantidad,"
                     " precio_unitario, subtotal) VALUES ('d1', 'old-1', 'Pierna', 2, 250, 500)")
        conn.commit()
        migration = importlib.import_module("migrations.standalone.318_quotes_bounded_context")
        migration.run(conn)
        migration.run(conn)
        rows = conn.execute("SELECT status, total, notes FROM quotes WHERE legacy_quote_id='old-1'"
                            ).fetchall()
        assert [(r[0], r[1]) for r in rows] == [("SENT", "500.00")]
        assert "Folio anterior: C-7" in rows[0][2]
