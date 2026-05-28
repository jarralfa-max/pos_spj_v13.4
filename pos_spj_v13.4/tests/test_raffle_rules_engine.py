import sqlite3
from core.services.loyalty_service import LoyaltyService
from pathlib import Path


def _db():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE configuraciones(clave TEXT PRIMARY KEY, valor TEXT)')
    return db


def _svc():
    return LoyaltyService(_db())


def _mk_raffle(svc, **rules):
    rid = svc.create_raffle_with_rules(
        {"nombre":"R", "premio":"P", "premio_costo_estimado":10, "presupuesto_maximo":20, "ventas_objetivo":20, "monto_por_boleto":10, "estado":"activa", "financial_status":"reservada", "fecha_inicio":"2026-01-01 00:00:00", "fecha_fin":"2026-12-31 23:59:59", "sucursal_id":1},
        rules,
        [{"nombre":"P1","cantidad":1,"costo_estimado":10,"orden":1}],
        {"branches":[1]},
    )
    return rid


def test_no_ticket_before_start_date():
    svc = _svc(); rid = _mk_raffle(svc)
    out = svc.process_raffles_for_sale(1,1,'F',100,1,sale_datetime='2025-01-01 00:00:00')
    assert out == []


def test_min_sale_amount_required():
    svc = _svc(); rid = _mk_raffle(svc, min_sale_amount=200)
    out = svc.process_raffles_for_sale(1,1,'F',100,1,sale_datetime='2026-06-01 10:00:00')
    assert out == []


def test_no_ticket_after_end_date():
    svc = _svc(); rid = _mk_raffle(svc)
    out = svc.process_raffles_for_sale(1, 1, 'F', 100, 1, sale_datetime='2027-01-01 00:00:00')
    assert out == []


def test_no_ticket_without_registered_customer_when_required():
    svc = _svc(); rid = _mk_raffle(svc, requires_registered_customer=1)
    out = svc.process_raffles_for_sale(1, 0, 'F', 100, 1, sale_datetime='2026-06-01 10:00:00')
    assert out == []


def test_per_amount_ticket_strategy():
    svc = _svc(); rid = _mk_raffle(svc, ticket_strategy='per_amount', amount_per_ticket=50)
    out = svc.process_raffles_for_sale(1,1,'F',120,1,sale_datetime='2026-06-01 10:00:00')
    assert len(out) == 2


def test_per_sale_ticket_strategy():
    svc = _svc(); rid = _mk_raffle(svc, ticket_strategy='per_sale', tickets_per_sale=3)
    out = svc.process_raffles_for_sale(1, 1, 'F', 120, 1, sale_datetime='2026-06-01 10:00:00')
    assert len(out) == 3


def test_max_tickets_per_sale():
    svc = _svc(); rid = _mk_raffle(svc, ticket_strategy='per_sale', tickets_per_sale=5, max_tickets_per_sale=2)
    out = svc.process_raffles_for_sale(1, 1, 'F', 120, 1, sale_datetime='2026-06-01 10:00:00')
    assert len(out) == 2


def test_max_tickets_per_customer_global():
    svc = _svc(); rid = _mk_raffle(svc, ticket_strategy='per_sale', tickets_per_sale=2, max_tickets_per_customer=2)
    out1 = svc.process_raffles_for_sale(1,1,'F',120,1,sale_datetime='2026-06-01 10:00:00')
    out2 = svc.process_raffles_for_sale(2,1,'F2',120,1,sale_datetime='2026-06-01 10:05:00')
    assert len(out1) == 2
    assert out2 == []


def test_branch_eligibility():
    svc = _svc(); rid = _mk_raffle(svc)
    out = svc.process_raffles_for_sale(1, 1, 'F', 100, 2, sale_datetime='2026-06-01 10:00:00')
    assert out == []


def test_payment_method_eligibility():
    svc = _svc(); rid = _mk_raffle(svc, allowed_payment_methods='tarjeta')
    out = svc.process_raffles_for_sale(1, 1, 'F', 100, 1, payment_method='efectivo', sale_datetime='2026-06-01 10:00:00')
    assert out == []


def test_product_eligibility():
    svc = _svc(); rid = _mk_raffle(svc)
    svc.db.execute("INSERT INTO raffle_eligible_products(raffle_id, product_id) VALUES(?,?)", (rid, 999))
    out = svc.process_raffles_for_sale(1, 1, 'F', 100, 1, items=[{"product_id": 1}], sale_datetime='2026-06-01 10:00:00')
    assert out == []


def test_create_raffle_with_multiple_prizes():
    svc = _svc()
    rid = svc.create_raffle_with_rules(
        {"nombre":"R2", "premio":"P", "premio_costo_estimado":30, "presupuesto_maximo":40, "ventas_objetivo":40, "monto_por_boleto":10, "estado":"activa", "financial_status":"reservada", "fecha_inicio":"2026-01-01 00:00:00", "fecha_fin":"2026-12-31 23:59:59", "sucursal_id":1},
        {"ticket_strategy":"per_sale","tickets_per_sale":1},
        [{"nombre":"P1","cantidad":1,"costo_estimado":10,"orden":1},{"nombre":"P2","cantidad":2,"costo_estimado":20,"orden":2}],
        {"branches":[1]},
    )
    prizes = svc._app.repo.list_raffle_prizes(rid)
    assert len(prizes) == 2


def test_select_winner_assigns_prize():
    svc = _svc(); rid = _mk_raffle(svc)
    svc.generate_tickets_for_sale(rid, 1, 1, 'F', 100, 1)
    svc.close_raffle(rid, 'u')
    w = svc.select_winner(rid, 'u')
    assert w.get('id', 0) > 0


def test_cannot_select_more_winners_than_prize_quantity():
    svc = _svc()
    rid = svc.create_raffle_with_rules(
        {"nombre":"R", "premio":"P", "premio_costo_estimado":10, "presupuesto_maximo":20, "ventas_objetivo":20, "monto_por_boleto":10, "estado":"activa", "financial_status":"reservada", "fecha_inicio":"2026-01-01 00:00:00", "fecha_fin":"2026-12-31 23:59:59", "sucursal_id":1},
        {"ticket_strategy":"per_sale","tickets_per_sale":1},
        [{"nombre":"P1","cantidad":1,"costo_estimado":10,"orden":1}],
        {"branches":[1]},
    )
    svc.generate_tickets_for_sale(rid, 1, 1, 'F1', 100, 1)
    svc.generate_tickets_for_sale(rid, 2, 2, 'F2', 100, 1)
    svc.close_raffle(rid, 'u')
    w1 = svc.select_winner(rid, 'u', random_seed='a')
    w2 = svc.select_winner(rid, 'u', random_seed='b')
    assert w1.get('id', 0) > 0
    assert w2 == {}


def test_ui_new_raffle_no_fixed_values():
    source = Path(__file__).resolve().parents[1] / "modulos" / "fidelidad_config.py"
    content = source.read_text(encoding="utf-8")
    assert "create_raffle_with_rules(" in content
    assert '"premio": "Premio"' not in content


def test_ticket_snapshot_contains_raffle_tickets():
    svc = _svc(); rid = _mk_raffle(svc, ticket_strategy='per_sale', tickets_per_sale=1)
    out = svc.process_raffles_for_sale(9, 1, 'F9', 100, 1, sale_datetime='2026-06-01 10:00:00')
    assert out and "raffle" in out[0] and "numero_boleto" in out[0]
