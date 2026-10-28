"""Estructura organizacional de punta a punta contra PostgreSQL REAL (auditoría
enterprise, cierre de la Fase 1; CI `central-postgres`).

La estación da de alta una región y una sucursal con el servicio real, cambia
una capacidad y sincroniza por la API central: el servidor queda con la foto
más reciente de cada unidad (`central_org_units`) y los sitios en
`central_org_sites`.
"""

from __future__ import annotations

import importlib
import os
import random
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")
DSN = os.environ.get("SPJ_TEST_PG_DSN", "")
pytestmark = pytest.mark.skipif(not DSN, reason="sin PostgreSQL de prueba (SPJ_TEST_PG_DSN)")

import migrations.engine as engine  # noqa: E402
from backend.infrastructure.db.database import (  # noqa: E402
    DatabaseSettings,
    create_connection_factory,
)
from backend.shared.ids import new_uuid  # noqa: E402


@pytest.fixture
def conectar():
    nombre = f"t_{uuid.uuid4().hex[:12]}"
    base = create_connection_factory(DatabaseSettings.postgresql(DSN))
    c = base()
    with c.cursor() as cur:
        cur.execute(f"CREATE SCHEMA {nombre}")
        cur.execute(f"SET search_path TO {nombre}")
    c.commit()
    engine.up_postgresql(c)
    c.close()

    def abrir():
        x = base()
        with x.cursor() as cur:
            cur.execute(f"SET search_path TO {nombre}")
        x.commit()
        return x

    yield abrir
    c = base()
    with c.cursor() as cur:
        cur.execute(f"DROP SCHEMA {nombre} CASCADE")
    c.commit()
    c.close()


def _estacion(station_id: str, branch_id: str):
    from backend.application.sync.replication_outbox import ReplicationOutboxService
    from tests.integration._born_clean_db import make_db

    conn = make_db()
    conn.execute("INSERT INTO company_profiles (id, legal_name, default_currency,"
                 " default_timezone, default_locale, created_at, updated_at) VALUES"
                 " (?, 'JUANIS', 'MXN', 'America/Mexico_City', 'es-MX', 'x', 'x')",
                 (new_uuid(),))
    conn.commit()
    for m in ("350_replication_engine", "351_organizational_structure",
              "352_org_outbox_and_branch_profiles"):
        importlib.import_module(f"migrations.standalone.{m}").run(conn)
    ReplicationOutboxService.register_station(conn, station_id=station_id, branch_id=branch_id)
    conn.commit()
    return conn


def test_org_structure_reaches_the_central_server(conectar):
    from fastapi.testclient import TestClient

    from backend.api.central_app import CentralSyncWorkflow, create_central_app
    from backend.application.configuracion.authorization import (
        ConfiguracionAuthorizationPolicy,
    )
    from backend.application.organization.org_structure_service import OrgStructureService
    from backend.application.sync.replication_outbox import ReplicationOutboxService
    from backend.application.sync.station_admin import CentralStationAdmin
    from backend.infrastructure.central.projection_repository import (
        PostgresCentralProjectionRepository,
    )
    from backend.infrastructure.central.sync_inbox_repository import (
        PostgresCentralInboxRepository,
    )
    from backend.infrastructure.sync.http_transport import HttpReplicationTransport

    pg = conectar()
    emitida = CentralStationAdmin(PostgresCentralInboxRepository(pg)).register(
        station_id=new_uuid(), branch_id=new_uuid())
    pg.close()
    estacion = _estacion(emitida.station_id, emitida.branch_id)
    svc = OrgStructureService(estacion, authorization=ConfiguracionAuthorizationPolicy
                              .permissive_for_tests(), actor=lambda: new_uuid())
    region = svc.create_unit(unit_type="REGION", code="NORTE", name="Norte")
    sucursal = svc.create_branch(code="CHI", name="Chihuahua", parent_id=region.id)
    svc.set_capability(sucursal.id, "CRM", enabled=False, reason="Sin clientes aquí")

    app = create_central_app(CentralSyncWorkflow(conectar, PostgresCentralInboxRepository,
                                                 PostgresCentralProjectionRepository))
    motor = ReplicationOutboxService(HttpReplicationTransport(
        "http://testserver", station_id=emitida.station_id, secret=emitida.secret,
        client=TestClient(app, base_url="http://testserver"), allow_insecure_localhost=True),
        rng=random.Random(3))
    resultado = motor.synchronize(estacion, station_id=emitida.station_id)
    # Principal (352) + región + sucursal creadas + cambio de capacidad.
    assert (resultado.synced, resultado.dead) == (4, 0), resultado

    pg = conectar()
    with pg.cursor() as cur:
        cur.execute("SELECT count(*) FROM central_projection_log WHERE status='ERROR'")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT parent_id::text, code, status, capabilities, source_branch_id::text"
                    " FROM central_org_units WHERE unit_id=%s", (sucursal.id,))
        padre, codigo, estado, capacidades, origen = cur.fetchone()
        assert (padre, codigo, estado, origen) == (region.id, "CHI", "ACTIVE", emitida.branch_id)
        assert "POS" in capacidades and "CRM" not in capacidades
        cur.execute("SELECT code FROM central_org_sites ORDER BY code")
        assert [r[0] for r in cur.fetchall()] == ["CHI", "PRINCIPAL"]   # la región no es sitio
    pg.close()
    estacion.close()
