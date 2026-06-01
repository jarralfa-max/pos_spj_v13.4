import sqlite3

from core.services.loyalty_service import LoyaltyService


def _service():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    svc = LoyaltyService(db, sucursal_id=1)
    svc._app.repo.ensure_raffle_tables()
    return svc, db


def _active_raffle(db, *, min_sale=0, required_customer=0, max_sale=0, max_customer=0, allowed_payment="", include_discounted=1, ticket_strategy="per_amount", tickets_per_sale=1, amount_per_ticket=100):
    db.execute(
        """
        INSERT INTO raffles(nombre,premio,monto_por_boleto,max_boletos_por_cliente,estado,financial_status,fecha_inicio,fecha_fin,sucursal_id)
        VALUES('Navidad','Canasta',100,99,'activa','reservada','2026-01-01 00:00:00','2026-12-31 23:59:59',1)
        """
    )
    rid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.execute(
        """
        INSERT INTO raffle_rules(raffle_id,requires_registered_customer,min_sale_amount,ticket_strategy,amount_per_ticket,tickets_per_sale,max_tickets_per_sale,max_tickets_per_customer,include_discounted_sales,allowed_payment_methods)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (rid, required_customer, min_sale, ticket_strategy, amount_per_ticket, tickets_per_sale, max_sale, max_customer, include_discounted, allowed_payment),
    )
    db.execute("INSERT INTO raffle_prizes(raffle_id,nombre) VALUES(?, 'Canasta')", (rid,))
    return rid


def _issue(svc, **kw):
    params = dict(venta_id=10, folio_venta="V-10", cliente_id=1, cliente_nombre="Ana", total=250, sucursal_id=1, sale_datetime="2026-06-01 12:00:00", payment_method="efectivo", items=[])
    params.update(kw)
    return svc.issue_raffle_tickets_for_sale(**params)


def test_loyalty_issues_raffle_tickets_for_active_raffle():
    svc, db = _service(); _active_raffle(db)
    tickets = _issue(svc)
    assert len(tickets) == 2
    assert tickets[0]["ticket_type"] == "raffle_ticket"
    assert db.execute("SELECT COUNT(*) FROM raffle_tickets").fetchone()[0] == 2


def test_loyalty_does_not_issue_if_no_active_raffle():
    svc, _ = _service()
    assert _issue(svc) == []


def test_loyalty_does_not_issue_if_min_sale_not_met():
    svc, db = _service(); _active_raffle(db, min_sale=300)
    assert _issue(svc, total=250) == []


def test_loyalty_does_not_issue_without_customer_when_required():
    svc, db = _service(); _active_raffle(db, required_customer=1)
    assert _issue(svc, cliente_id=0) == []


def test_loyalty_raffle_ticket_generation_is_idempotent():
    svc, db = _service(); _active_raffle(db)
    first = _issue(svc)
    second = _issue(svc)
    assert [t["numero_boleto"] for t in first] == [t["numero_boleto"] for t in second]
    assert db.execute("SELECT COUNT(*) FROM raffle_tickets").fetchone()[0] == 2


def test_loyalty_respects_max_tickets_per_sale():
    svc, db = _service(); _active_raffle(db, max_sale=1)
    assert len(_issue(svc)) == 1
    assert db.execute("SELECT COUNT(*) FROM raffle_tickets").fetchone()[0] == 1


def test_loyalty_respects_max_tickets_per_customer():
    svc, db = _service(); _active_raffle(db, max_customer=1)
    assert len(_issue(svc)) == 1
    assert _issue(svc, venta_id=11, folio_venta="V-11") == []


def test_loyalty_respects_payment_method_rules():
    svc, db = _service(); _active_raffle(db, allowed_payment="tarjeta")
    assert _issue(svc, payment_method="efectivo") == []
    assert len(_issue(svc, payment_method="tarjeta")) == 2


def test_loyalty_respects_fixed_tickets_per_sale_without_extra_rows():
    svc, db = _service(); _active_raffle(db, ticket_strategy="fixed", tickets_per_sale=3, amount_per_ticket=100)

    tickets = _issue(svc, total=1000)

    assert len(tickets) == 3
    assert db.execute("SELECT COUNT(*) FROM raffle_tickets").fetchone()[0] == 3


def test_loyalty_respects_include_discounted_sales_rule():
    svc, db = _service(); _active_raffle(db, include_discounted=0)

    assert _issue(svc, discount=10) == []
    assert _issue(svc, venta_id=11, folio_venta="V-11", items=[{"product_id": 1, "descuento": 5}]) == []


def test_loyalty_respects_eligible_branch_table():
    svc, db = _service(); rid = _active_raffle(db)
    db.execute("INSERT INTO raffle_eligible_branches(raffle_id, sucursal_id) VALUES(?, 2)", (rid,))

    assert _issue(svc, sucursal_id=1) == []
    assert len(_issue(svc, sucursal_id=2, venta_id=12, folio_venta="V-12")) == 2


def test_loyalty_respects_eligible_products_table():
    svc, db = _service(); rid = _active_raffle(db)
    db.execute("INSERT INTO raffle_eligible_products(raffle_id, product_id) VALUES(?, 7)", (rid,))

    assert _issue(svc, items=[{"product_id": 3}]) == []
    assert len(_issue(svc, venta_id=13, folio_venta="V-13", items=[{"product_id": 7}])) == 2
