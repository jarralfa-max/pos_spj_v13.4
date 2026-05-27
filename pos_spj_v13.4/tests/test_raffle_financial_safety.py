import sqlite3
from pathlib import Path

import pytest
import time

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


def _setup_closed_raffle_with_winner(db, financial_status="reservada"):
    repo = LoyaltyRepository(db)
    repo.ensure_raffle_tables()
    raffle_id = repo.create_raffle(
        {
            "nombre": "R-F2",
            "monto_por_boleto": 10,
            "premio_costo_estimado": 10,
            "presupuesto_maximo": 20,
            "financial_status": financial_status,
            "estado": "cerrada",
            "premio": "P",
        }
    )
    repo.generate_tickets_for_sale(raffle_id, 33, 1, "F33", 20, 1)
    repo.select_winner(raffle_id, "u", "seed-f2")
    winner_id = db.execute("SELECT id FROM raffle_winners LIMIT 1").fetchone()[0]
    return raffle_id, winner_id


def test_no_deliver_prize_without_real_reserve():
    db = _db()
    svc = _service(db)
    _raffle_id, winner_id = _setup_closed_raffle_with_winner(db)

    with pytest.raises(ValueError):
        svc.mark_prize_delivered(winner_id, "u", 10.0, "ref:no-reserve")


def test_deliver_prize_with_reserve_works():
    db = _db()
    svc = _service(db)
    raffle_id, winner_id = _setup_closed_raffle_with_winner(db)

    assert svc.reserve_raffle_budget(raffle_id, 20.0, "u", "ref:reserve") is True
    assert svc.mark_prize_delivered(winner_id, "u", 10.0, "ref:deliver") is True


def test_deliver_prize_twice_no_duplicate_event_or_ledger():
    db = _db()
    svc = _service(db)
    raffle_id, winner_id = _setup_closed_raffle_with_winner(db)
    assert svc.reserve_raffle_budget(raffle_id, 20.0, "u", "ref:reserve-2") is True

    bus = event_bus.get_bus()
    events = []

    def _capture(payload: dict):
        events.append(payload)

    bus.subscribe(event_bus.RAFFLE_PRIZE_DELIVERED, _capture, priority=999, label="test_capture_prize")

    assert svc.mark_prize_delivered(winner_id, "u", 10.0, "ref:deliver-2") is True
    assert svc.mark_prize_delivered(winner_id, "u", 10.0, "ref:deliver-2") is False

    delivered_rows = db.execute(
        "SELECT COUNT(*) FROM raffle_financial_ledger WHERE raffle_id=? AND tipo='prize_delivered' AND referencia='ref:deliver-2'",
        (raffle_id,),
    ).fetchone()[0]
    assert delivered_rows <= 1
    for _ in range(20):
        if len(events) == 1:
            break
        time.sleep(0.01)
    assert len(events) == 1


def test_raffle_budget_ledger_net():
    db = _db()
    svc = _service(db)
    raffle_id = svc.create_raffle({
        "nombre": "R-Net", "monto_por_boleto": 10, "premio_costo_estimado": 10,
        "presupuesto_maximo": 50, "ventas_objetivo": 50,
    })
    assert svc.reserve_raffle_budget(raffle_id, 50, "u", "ref:r") is True
    assert svc.release_raffle_budget(raffle_id, 20, "u", "ref:rel") is True
    repo = LoyaltyRepository(db)
    repo.db.execute(
        "INSERT OR IGNORE INTO raffle_financial_ledger(raffle_id,tipo,monto,referencia) VALUES(?,?,?,?)",
        (raffle_id, "prize_delivered", 10.0, "ref:d"),
    )
    summary = svc.get_raffle_summary()
    assert float(summary["pasivo_promocional"]) == 20.0


def test_max_boletos_por_cliente_global():
    db = _db()
    repo = LoyaltyRepository(db)
    repo.ensure_raffle_tables()
    raffle_id = repo.create_raffle({
        "nombre": "R-Max", "monto_por_boleto": 10, "premio_costo_estimado": 10,
        "presupuesto_maximo": 50, "financial_status": "reservada", "estado": "activa",
        "max_boletos_por_cliente": 1,
    })
    tickets = repo.generate_tickets_for_sale(raffle_id, 77, 1, "F77", 100, 1)
    assert len(tickets) == 1


def test_sale_completed_generates_raffle_tickets_once():
    db = _db()
    svc = _service(db)
    raffle_id = svc.create_raffle({
        "nombre": "R-Sale", "monto_por_boleto": 10, "premio_costo_estimado": 10,
        "presupuesto_maximo": 50, "financial_status": "reservada", "estado": "activa",
    })
    first = svc.process_raffles_for_sale(900, 1, "F900", 20, 1)
    second = svc.process_raffles_for_sale(900, 1, "F900", 20, 1)
    assert len(first) == 2
    assert second == []


def test_sale_cancelled_cancels_raffle_tickets():
    db = _db()
    svc = _service(db)
    svc.create_raffle({
        "nombre": "R-Cancel", "monto_por_boleto": 10, "premio_costo_estimado": 10,
        "presupuesto_maximo": 50, "financial_status": "reservada", "estado": "activa",
    })
    svc.process_raffles_for_sale(901, 1, "F901", 20, 1)
    cancelled = svc.cancel_tickets_for_sale(901, "cancel test")
    assert cancelled == 2
    assert db.execute("SELECT COUNT(*) FROM raffle_tickets WHERE venta_id=901 AND estado='cancelado'").fetchone()[0] == 2


def test_ticket_includes_raffle_tickets():
    src = Path(__file__).resolve().parents[1] / 'core' / 'services' / 'sales_service.py'
    text = src.read_text(encoding='utf-8')
    assert 'raffle_tickets_snapshot' in text
    assert 'raffle_tickets_lines' in text


def test_ui_no_sql_direct():
    src = Path(__file__).resolve().parents[1] / 'modulos' / 'fidelidad_config.py'
    text = src.read_text(encoding='utf-8')
    assert 'SELECT ' not in text
    assert '_app.repo' not in text


def test_ui_raffle_buttons_connected():
    src = Path(__file__).resolve().parents[1] / 'modulos' / 'fidelidad_config.py'
    text = src.read_text(encoding='utf-8')
    for handler in (
        '_on_nueva_rifa', '_on_reservar_presupuesto', '_on_activar_rifa',
        '_on_cerrar_rifa', '_on_seleccionar_ganador', '_on_entregar_premio', '_on_ver_boletos',
    ):
        assert handler in text
