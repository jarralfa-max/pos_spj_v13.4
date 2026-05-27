import sqlite3

import pytest

from core.events import event_bus
from core.services.loyalty_service import LoyaltyService
from repositories.loyalty_repository import LoyaltyRepository


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE configuraciones(clave TEXT PRIMARY KEY, valor TEXT)")
    return db


def _service(db):
    return LoyaltyService(db)


def _active_raffle_payload():
    return {
        "nombre": "Rifa QA",
        "monto_por_boleto": 10,
        "premio_costo_estimado": 10,
        "presupuesto_maximo": 20,
        "financial_status": "reservada",
        "estado": "activa",
    }


def test_no_activate_raffle_without_budget():
    db = _db()
    svc = _service(db)
    raffle_id = svc.create_raffle(
        {
            "nombre": "R1",
            "premio_costo_estimado": 100,
            "presupuesto_maximo": 100,
            "monto_por_boleto": 10,
            "financial_status": "presupuestada",
        }
    )

    with pytest.raises(ValueError):
        svc.activate_raffle(raffle_id, "u")


def test_no_activate_raffle_if_prize_cost_exceeds_budget():
    db = _db()
    svc = _service(db)

    with pytest.raises(ValueError):
        svc.create_raffle(
            {
                "nombre": "R1",
                "premio_costo_estimado": 200,
                "presupuesto_maximo": 100,
                "monto_por_boleto": 10,
            }
        )


def test_reserve_budget_idempotent():
    db = _db()
    svc = _service(db)
    raffle_id = svc.create_raffle(
        {
            "nombre": "R1",
            "premio_costo_estimado": 50,
            "presupuesto_maximo": 100,
            "monto_por_boleto": 10,
        }
    )

    assert svc.reserve_raffle_budget(raffle_id, 100, "u", "ref1") is True
    assert svc.reserve_raffle_budget(raffle_id, 100, "u", "ref1") is False


def test_generate_tickets_for_sale_idempotent():
    db = _db()
    repo = LoyaltyRepository(db)
    repo.ensure_raffle_tables()
    raffle_id = repo.create_raffle(_active_raffle_payload())

    first = repo.generate_tickets_for_sale(raffle_id, 1, 1, "F1", 20, 1)
    second = repo.generate_tickets_for_sale(raffle_id, 1, 1, "F1", 20, 1)

    assert len(first) == 2
    assert len(second) == 0


def test_cancel_sale_cancels_tickets_not_delete():
    db = _db()
    repo = LoyaltyRepository(db)
    repo.ensure_raffle_tables()
    raffle_id = repo.create_raffle(_active_raffle_payload())

    repo.generate_tickets_for_sale(raffle_id, 2, 1, "F2", 20, 1)
    cancelled = repo.cancel_tickets_for_sale(2, "cancel")

    assert cancelled == 2
    assert db.execute("SELECT COUNT(*) FROM raffle_tickets WHERE venta_id=2").fetchone()[0] == 2
    assert db.execute("SELECT COUNT(*) FROM raffle_tickets WHERE venta_id=2 AND estado='cancelado'").fetchone()[0] == 2


def test_cannot_select_winner_before_close():
    db = _db()
    svc = _service(db)

    with pytest.raises(ValueError):
        svc.validate_winner_selection({"estado": "activa"})


def test_cannot_deliver_prize_without_reserve():
    db = _db()
    svc = _service(db)

    with pytest.raises(ValueError):
        svc.validate_prize_delivery({"financial_status": "presupuestada"}, {"id": 1})


def test_prize_delivery_liquidates_liability_once():
    db = _db()
    repo = LoyaltyRepository(db)
    repo.ensure_raffle_tables()
    raffle_id = repo.create_raffle(
        {
            "nombre": "R",
            "monto_por_boleto": 10,
            "premio_costo_estimado": 10,
            "presupuesto_maximo": 20,
            "financial_status": "reservada",
            "estado": "cerrada",
            "premio": "P",
        }
    )

    repo.generate_tickets_for_sale(raffle_id, 3, 1, "F3", 20, 1)
    repo.select_winner(raffle_id, "u", "seed")
    winner_id = db.execute("SELECT id FROM raffle_winners LIMIT 1").fetchone()[0]

    assert repo.mark_prize_delivered(winner_id, "u", 10) is True
    assert repo.mark_prize_delivered(winner_id, "u", 10) is False


def test_raffle_summary_kpis():
    db = _db()
    repo = LoyaltyRepository(db)
    repo.ensure_raffle_tables()

    summary = repo.get_raffle_summary()

    expected = {
        "rifas_activas",
        "boletos_emitidos",
        "boletos_cancelados",
        "premios_pendientes",
        "pasivo_promocional",
        "presupuesto_usado",
        "roi_estimado",
    }
    assert expected.issubset(summary.keys())


def test_event_bus_has_raffle_events():
    for name in (
        "RAFFLE_CREATED",
        "RAFFLE_BUDGET_RESERVED",
        "RAFFLE_ACTIVATED",
        "RAFFLE_TICKET_GRANTED",
        "RAFFLE_TICKET_CANCELLED",
        "RAFFLE_CLOSED",
        "RAFFLE_WINNER_SELECTED",
        "RAFFLE_PRIZE_DELIVERED",
        "RAFFLE_BUDGET_RELEASED",
    ):
        assert hasattr(event_bus, name)
