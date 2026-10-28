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


    # ── registro de equipos (auditoría enterprise, Fase 4) ──────────────
    # Mismo contrato que `PostgresCentralInboxRepository`: la invitación se
    # consume con «sólo si sigue PENDIENTE y vigente».
    def _inv(self):
        if not hasattr(self, "invitations"):
            self.invitations, self.device_log = {}, []
        return self.invitations

    def list_stations(self):
        return [dict(e) for e in self.stations.values()]

    def insert_invitation(self, row):
        self._inv()[row["id"]] = {**row, "status": "PENDING", "consumed_at": None,
                                  "consumed_station_id": None}

    def invitation_by_hash(self, token_hash):
        return next((dict(i) for i in self._inv().values() if i["token_hash"] == token_hash),
                    None)

    def consume_invitation(self, invitation_id, *, station_id, now):
        inv = self._inv().get(invitation_id)
        if inv is None or inv["status"] != "PENDING" or inv["expires_at"] <= now:
            return False
        inv.update(status="CONSUMED", consumed_at=now, consumed_station_id=station_id)
        return True

    def revoke_invitation(self, invitation_id):
        inv = self._inv().get(invitation_id)
        if inv is None or inv["status"] != "PENDING":
            return False
        inv["status"] = "REVOKED"
        return True

    def list_invitations(self, *, now):
        return [dict(i) for i in self._inv().values()]

    def register_device_station(self, *, station_id, branch_id, display_name, public_key,
                                workstation_type, capabilities, is_admin, invitation_id):
        self.register_station(station_id=station_id, branch_id=branch_id,
                              display_name=display_name, credential_hash="!")
        self.stations[station_id].update(
            public_key=public_key, key_algorithm="ed25519", workstation_type=workstation_type,
            capabilities=list(capabilities), is_admin_station=bool(is_admin),
            enrolled_via=invitation_id, replaced_by=None)

    def rotate_station_key(self, station_id, *, public_key, invitation_id):
        self.stations[station_id].update(public_key=public_key, key_algorithm="ed25519",
                                         enrolled_via=invitation_id)

    def mark_replaced(self, station_id, *, replaced_by, now):
        self.stations[station_id].update(status="RETIRED", replaced_by=replaced_by)

    def reassign_station(self, station_id, *, branch_id):
        self.stations[station_id]["branch_id"] = branch_id

    def report_heartbeat(self, station_id, *, app_version, pending_events, last_sync_at, now):
        self.stations[station_id].update(app_version=app_version, pending_events=pending_events,
                                         last_sync_at=last_sync_at, last_seen_at=now)

    def add_device_event(self, *, station_id, invitation_id, event, actor_station, actor_user,
                         detail, now):
        self._inv()
        self.device_log.append({"station_id": station_id, "invitation_id": invitation_id,
                                "event": event, "actor_station": actor_station,
                                "actor_user": actor_user, "detail": dict(detail),
                                "occurred_at": now})

    def device_events(self, station_id):
        self._inv()
        return [e for e in self.device_log if e["station_id"] == station_id]
