"""Proyección central de la estructura organizacional, sin PostgreSQL.

Los hechos salen del servicio REAL de la estación (`org_outbox`) y pasan por el
mismo lector de fuentes del motor de replicación. La batería contra PostgreSQL
real está en `tests/integration/central_pg/test_org_projection_pg.py` (CI).
"""

from __future__ import annotations

import importlib
import json
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from backend.application.configuracion.authorization import ConfiguracionAuthorizationPolicy
from backend.application.organization.org_structure_service import OrgStructureService
from backend.application.sync.central_projection import (
    ORG_UNIT_EVENTS,
    CentralProjector,
    ProjectionError,
    org_unit_row,
)
from backend.infrastructure.sync.replication_sources import DEFAULT_SOURCES
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db

ESTACION, SUCURSAL_ESTACION = new_uuid(), new_uuid()
T0 = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


def _estacion():
    conn = make_db()
    conn.execute("INSERT INTO company_profiles (id, legal_name, default_currency,"
                 " default_timezone, default_locale, created_at, updated_at) VALUES"
                 " (?, 'JUANIS', 'MXN', 'America/Mexico_City', 'es-MX', 'x', 'x')",
                 (new_uuid(),))
    conn.commit()
    for m in ("351_organizational_structure", "352_org_outbox_and_branch_profiles"):
        importlib.import_module(f"migrations.standalone.{m}").run(conn)
    return conn


def _hechos(conn) -> list[dict]:
    fuente = next(f for f in DEFAULT_SOURCES if f.table == "org_outbox")
    hechos = []
    for fila in conn.execute("SELECT * FROM org_outbox ORDER BY created_at, rowid"):
        evento, _ = fuente.normalize(dict(fila), station_branch_id=SUCURSAL_ESTACION)
        hechos.append({"event_id": evento["event_id"], "event_type": evento["event_name"],
                       "aggregate_id": evento["entity_id"], "branch_id": evento["branch_id"],
                       "station_id": ESTACION, "occurred_at": T0,
                       "payload": json.loads(json.dumps(evento["payload"]))})
    return hechos


class _Memoria:
    def __init__(self, hechos):
        self.hechos, self.registro, self.unidades = list(hechos), {}, {}

    def pending_facts(self, *, projector, limit):
        return [h for h in self.hechos if (h["event_id"], projector) not in self.registro][:limit]

    @contextmanager
    def savepoint(self):
        yield

    def log(self, *, event_id, projector, status, error):
        self.registro[(event_id, projector)] = (status, error)

    def upsert_org_unit(self, row):
        # Misma regla que el UPSERT de PostgreSQL: sólo una foto más reciente reemplaza.
        actual = self.unidades.get(row["unit_id"])
        if actual is None or actual["updated_at"] <= row["updated_at"]:
            self.unidades[row["unit_id"]] = row

    def commit(self):
        pass


def test_station_org_changes_project_to_the_latest_snapshot():
    conn = _estacion()
    svc = OrgStructureService(conn, authorization=ConfiguracionAuthorizationPolicy
                              .permissive_for_tests(), actor=lambda: new_uuid())
    region = svc.create_unit(unit_type="REGION", code="NORTE", name="Norte")
    sucursal = svc.create_branch(code="CHI", name="Chihuahua", parent_id=region.id)
    svc.set_capability(sucursal.id, "CRM", enabled=False, reason="Sin clientes aquí")
    memoria = _Memoria(_hechos(conn))
    corrida = CentralProjector(memoria).run_once()
    assert corrida.errors == 0 and corrida.projected == len(memoria.hechos)
    fila = memoria.unidades[sucursal.id]
    assert (fila["parent_id"], fila["code"], fila["unit_type"]) == (region.id, "CHI",
                                                                    "RETAIL_BRANCH")
    assert "CRM" not in fila["capabilities"] and "POS" in fila["capabilities"]
    # «Principal» (sembrada por el esquema base y respaldada por la 351) llegó con
    # el ORG_UNIT_REGISTERED de la 352.
    assert sorted(u["code"] for u in memoria.unidades.values()) == ["CHI", "NORTE", "PRINCIPAL"]
    assert fila["source_branch_id"] == SUCURSAL_ESTACION


def test_an_older_snapshot_does_not_undo_a_newer_one():
    memoria = _Memoria([])
    base = {"unit_id": new_uuid(), "company_id": new_uuid(), "unit_type": "REGION",
            "code": "R1", "name": "Nueva", "status": "ACTIVE", "capabilities": ["BI"]}
    nuevo = {"event_id": new_uuid(), "event_type": "ORG_UNIT_UPDATED", "branch_id": new_uuid(),
             "payload": {**base, "updated_at": "2026-10-25T12:00:00+00:00"}}
    viejo = {"event_id": new_uuid(), "event_type": "ORG_UNIT_CREATED", "branch_id": new_uuid(),
             "payload": {**base, "name": "Vieja", "updated_at": "2026-10-25T11:00:00+00:00"}}
    memoria.hechos = [nuevo, viejo]
    CentralProjector(memoria).run_once()
    assert memoria.unidades[base["unit_id"]]["name"] == "Nueva"


def test_org_unit_row_rejects_incomplete_or_invalid_facts():
    bueno = {"event_id": new_uuid(), "branch_id": new_uuid(), "payload": {
        "unit_id": new_uuid(), "company_id": new_uuid(), "unit_type": "WAREHOUSE",
        "code": "ALM", "name": "Almacén", "status": "ACTIVE", "updated_at": "x",
        "capabilities": ["RECEIVING", "INVENTORY"]}}
    assert org_unit_row(bueno)["capabilities"] == ["INVENTORY", "RECEIVING"]
    with pytest.raises(ProjectionError, match="code"):
        org_unit_row({**bueno, "payload": {**bueno["payload"], "code": ""}})
    with pytest.raises(ProjectionError, match="inválido"):
        org_unit_row({**bueno, "payload": {**bueno["payload"], "unit_type": "TIENDA"}})
    assert {"ORG_UNIT_REGISTERED", "ORG_UNIT_CAPABILITIES_CHANGED"} <= set(ORG_UNIT_EVENTS)
