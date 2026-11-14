"""Arnés de aceptación: N estaciones + central (SDLC-ARQ-TEST-001).

Para los escenarios de `requisitos-arquitectura.md` §15 que piden dos terminales,
dos usuarios a la vez, caída de red o reinicio de proceso. Cada estación es una
SQLite REAL en archivo, con sus migraciones; la central es la ingesta real sobre
`MemoryCentralInbox`, el libro en memoria cuyo contrato se valida contra PostgreSQL
en `tests/integration/central_pg/`. No reemplaza a esas pruebas: PostgreSQL real
sigue corriendo sólo en CI.

    def test_algo(multi_station):
        norte, sur = multi_station.stations(2)
        evento = norte.record_cash_fact()
        norte.sync()
        assert multi_station.central.has_event(evento["event_id"])
        norte.restart()                 # reinicio de proceso: la cola sobrevive

`central.offline = True` tira la red y `central.lose_next_response()` confirma en el
servidor y pierde la respuesta. Los escenarios de negocio los aporta cada ítem; las
tablas que necesite se agregan por estación con `schema=`.
"""
from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path
from typing import Callable

import pytest

from backend.application.sync.central_ingestion import CentralIngestionService
from backend.application.sync.replication_outbox import (
    ReplicationCycleResult,
    ReplicationOutboxService,
)
from backend.application.sync.station_admin import CentralStationAdmin
from backend.domain.cash_register.events import CashEvents, cash_event_payload
from backend.infrastructure.db.repositories.cash_register.unit_of_work import (
    CashRegisterUnitOfWork,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.shared.ids import new_uuid
from tests.unit.central_sync.memory_inbox import MemoryCentralInbox


class Central:
    """La central en un proceso: autentica y procesa como la API, sin HTTP."""

    def __init__(self) -> None:
        self.inbox = MemoryCentralInbox()
        self.offline = False
        self._lose_responses = 0

    def lose_next_response(self) -> None:
        """El servidor confirma y la respuesta no llega a la estación."""
        self._lose_responses += 1

    def has_event(self, event_id: str) -> bool:
        return event_id in self.inbox.facts

    def facts_of(self, station_id: str) -> list[dict]:
        return [hecho for hecho in self.inbox.facts.values()
                if hecho["station_id"] == station_id]

    def enroll(self, *, station_id: str, branch_id: str, name: str):
        return CentralStationAdmin(self.inbox).register(
            station_id=station_id, branch_id=branch_id, display_name=name)

    def transport_for(self, emitida) -> "_DirectTransport":
        return _DirectTransport(self, emitida)


class _DirectTransport:
    def __init__(self, central: Central, emitida) -> None:
        self._central = central
        self._emitida = emitida

    def push(self, *, station_id, branch_id, envelopes):
        central = self._central
        if central.offline:
            raise ConnectionError("sin red (simulado)")
        servicio = CentralIngestionService(central.inbox)
        estacion = servicio.authenticate(self._emitida.station_id, self._emitida.secret)
        acuses = servicio.ingest(estacion, [s.to_dict() for s in envelopes]).acks
        if central._lose_responses:
            central._lose_responses -= 1
            raise ConnectionError("respuesta perdida (simulado)")
        return acuses


def _base_schema(conn: sqlite3.Connection) -> None:
    importlib.import_module(
        "migrations.standalone.175_cash_register_bounded_context_schema").run(conn)
    create_inventory_schema(conn)
    importlib.import_module("migrations.standalone.350_replication_engine").run(conn)
    conn.commit()


class Station:
    """Una terminal con su propia SQLite en archivo."""

    def __init__(self, *, path: Path, central: Central, branch_id: str, name: str,
                 schema: Callable[[sqlite3.Connection], None] | None = None) -> None:
        self.path = path
        self.central = central
        self.branch_id = branch_id
        self.station_id = new_uuid()
        self.conn = self._open()
        _base_schema(self.conn)
        if schema is not None:
            schema(self.conn)
            self.conn.commit()
        ReplicationOutboxService.register_station(
            self.conn, station_id=self.station_id, branch_id=branch_id)
        self.conn.commit()
        self._emitida = central.enroll(station_id=self.station_id, branch_id=branch_id, name=name)
        self.service = ReplicationOutboxService(central.transport_for(self._emitida))

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def record_cash_fact(self) -> dict:
        """Un hecho real en el outbox de Caja de esta estación."""
        evento = cash_event_payload(CashEvents.HARDWARE_DIAGNOSED, operation_id=new_uuid(),
                                    entity_id=new_uuid(), branch_id=self.branch_id,
                                    user_id=new_uuid())
        with CashRegisterUnitOfWork(self.conn) as uow:
            uow.events.add(evento)
            uow.outbox.enqueue(evento)
        return evento

    def sync(self, **kwargs) -> ReplicationCycleResult:
        return self.service.synchronize(self.conn, station_id=self.station_id, **kwargs)

    def queue(self) -> dict:
        return ReplicationOutboxService.status(self.conn, station_id=self.station_id)

    def restart(self) -> None:
        """Reinicio de proceso: conexión nueva sobre el mismo archivo."""
        self.conn.close()
        self.conn = self._open()
        self.service = ReplicationOutboxService(self.central.transport_for(self._emitida))

    def close(self) -> None:
        self.conn.close()


class MultiStationHarness:
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self.central = Central()
        self._stations: list[Station] = []

    def station(self, *, branch_id: str | None = None,
                schema: Callable[[sqlite3.Connection], None] | None = None) -> Station:
        numero = len(self._stations) + 1
        estacion = Station(path=self._directory / f"estacion_{numero}.sqlite",
                           central=self.central, branch_id=branch_id or new_uuid(),
                           name=f"Caja {numero}", schema=schema)
        self._stations.append(estacion)
        return estacion

    def stations(self, count: int, *, branch_id: str | None = None,
                 schema: Callable[[sqlite3.Connection], None] | None = None) -> list[Station]:
        return [self.station(branch_id=branch_id, schema=schema) for _ in range(count)]

    def close(self) -> None:
        for estacion in self._stations:
            estacion.close()


@pytest.fixture
def multi_station(tmp_path):
    arnes = MultiStationHarness(tmp_path)
    yield arnes
    arnes.close()
