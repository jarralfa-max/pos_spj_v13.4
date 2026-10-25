"""Libro central EN MEMORIA para pruebas sin PostgreSQL (SIMULACIÓN).

Respeta el contrato de `CentralInboxRepository` como lo cumple PostgreSQL:
`event_id` único, `(station_id, sequence_no)` único, SAVEPOINT que revierte sólo
lo de ese sobre. La prueba de que PostgreSQL real se comporta igual está en
`tests/integration/central_pg/test_central_ingestion_pg.py` (corre en el CI).
"""

from __future__ import annotations

import copy
from contextlib import contextmanager


class MemoryCentralInbox:
    def __init__(self) -> None:
        self.stations: dict[str, dict] = {}
        self.facts: dict[str, dict] = {}
        self.conflicts: list[dict] = []
        self.heads: dict[tuple, dict] = {}
        self.commits = 0
        self.fail_on: str | None = None   # event_id cuyo insert falla (error de almacenamiento)

    # estaciones
    def get_station(self, station_id):
        e = self.stations.get(station_id)
        return None if e is None else dict(e)

    def register_station(self, *, station_id, branch_id, display_name, credential_hash):
        if station_id in self.stations:
            raise ValueError("duplicada")
        self.stations[station_id] = {"id": station_id, "branch_id": branch_id,
                                     "credential_hash": credential_hash, "status": "ACTIVE",
                                     "last_sequence": 0, "display_name": display_name}

    def set_station_status(self, station_id, status, *, now):
        self.stations[station_id]["status"] = status
        return True

    def touch_station(self, station_id, *, now):
        secuencias = {f["sequence_no"] for f in self.facts.values()
                      if f["station_id"] == station_id}
        n = self.stations[station_id]["last_sequence"]
        while n + 1 in secuencias:
            n += 1
        self.stations[station_id].update(last_sequence=n, last_seen_at=now)

    # transacciones
    @contextmanager
    def savepoint(self):
        copia = copy.deepcopy((self.facts, self.conflicts, self.heads))
        try:
            yield
        except Exception:
            self.facts, self.conflicts, self.heads = copia
            raise

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    # hechos
    def fact_hash(self, event_id):
        f = self.facts.get(event_id)
        return None if f is None else f["content_hash"]

    def event_for_sequence(self, station_id, sequence_no):
        return next((eid for eid, f in self.facts.items()
                     if f["station_id"] == station_id and f["sequence_no"] == sequence_no), None)

    def insert_fact(self, envelope, *, station_id, status, error_code, now):
        if self.fail_on == envelope.event_id:
            raise RuntimeError("disco lleno (simulado)")
        if envelope.event_id in self.facts:
            return False
        if self.event_for_sequence(station_id, envelope.sequence_no) is not None:
            raise RuntimeError("UNIQUE (station_id, sequence_no)")
        self.facts[envelope.event_id] = {
            "station_id": station_id, "sequence_no": envelope.sequence_no,
            "content_hash": envelope.content_hash, "status": status, "error_code": error_code,
            "aggregate": (envelope.aggregate_type, envelope.aggregate_id),
            "aggregate_version": envelope.aggregate_version, "payload": dict(envelope.payload)}
        return True

    def station_head(self, aggregate_type, aggregate_id, station_id):
        versiones = [f["aggregate_version"] for f in self.facts.values()
                     if f["aggregate"] == (aggregate_type, aggregate_id)
                     and f["station_id"] == station_id and f["status"] == "APPLIED"]
        return max(versiones) if versiones else None

    def advance_head(self, envelope, *, station_id, now):
        self.heads[(envelope.aggregate_type, envelope.aggregate_id)] = {
            "last_version": envelope.aggregate_version, "last_event_id": envelope.event_id,
            "last_station_id": station_id}

    def add_conflict(self, *, event_id, kind, details, now):
        self.conflicts.append({"event_id": event_id, "kind": kind, "details": dict(details)})
