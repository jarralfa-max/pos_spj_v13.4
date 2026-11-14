"""El arnés multi-terminal hace lo que promete (SDLC-ARQ-TEST-001).

No son los escenarios de §15 —cada ítem aporta el suyo— sino la prueba de que el
arnés sí aísla estaciones, persiste la cola y simula las fallas de red.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.shared.ids import new_uuid
from tests.integration.multi_station import multi_station  # noqa: F401 - fixture


def _manana() -> datetime:
    """Pasado el respaldo entre reintentos."""
    return datetime.now(timezone.utc) + timedelta(days=1)


def test_each_station_has_its_own_database_and_identity(multi_station):  # noqa: F811
    norte, sur = multi_station.stations(2)
    assert norte.path != sur.path and norte.station_id != sur.station_id

    norte.record_cash_fact()

    assert norte.conn.execute("SELECT COUNT(*) FROM cash_outbox").fetchone()[0] == 1
    assert sur.conn.execute("SELECT COUNT(*) FROM cash_outbox").fetchone()[0] == 0


def test_a_fact_reaches_the_central_ledger_under_its_station(multi_station):  # noqa: F811
    norte, sur = multi_station.stations(2)
    evento_norte, evento_sur = norte.record_cash_fact(), sur.record_cash_fact()

    norte.sync()
    sur.sync()

    central = multi_station.central
    assert central.has_event(evento_norte["event_id"])
    assert central.has_event(evento_sur["event_id"])
    assert len(central.facts_of(norte.station_id)) == 1
    assert len(central.facts_of(sur.station_id)) == 1


def test_two_terminals_can_share_a_branch(multi_station):  # noqa: F811
    sucursal = new_uuid()
    uno, dos = multi_station.stations(2, branch_id=sucursal)
    eventos = [uno.record_cash_fact(), dos.record_cash_fact()]

    uno.sync()
    dos.sync()

    assert uno.branch_id == dos.branch_id == sucursal
    assert all(multi_station.central.has_event(e["event_id"]) for e in eventos)


def test_the_queue_survives_a_network_outage_and_a_process_restart(multi_station):  # noqa: F811
    estacion = multi_station.station()
    central = multi_station.central
    evento = estacion.record_cash_fact()

    central.offline = True
    estacion.sync()
    assert not central.has_event(evento["event_id"])

    estacion.restart()
    central.offline = False
    estacion.sync(now=_manana())

    assert central.has_event(evento["event_id"])


def test_a_lost_response_is_settled_without_duplicating_the_fact(multi_station):  # noqa: F811
    estacion = multi_station.station()
    central = multi_station.central
    evento = estacion.record_cash_fact()

    central.lose_next_response()
    estacion.sync()
    assert central.has_event(evento["event_id"])     # el servidor sí lo guardó

    estacion.sync(now=_manana())

    assert len(central.facts_of(estacion.station_id)) == 1
