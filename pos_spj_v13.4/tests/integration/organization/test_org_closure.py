"""Cierre de pendientes de la Fase 1 (auditoría enterprise):

* sitio, `sucursales` y perfil de sucursal se escriben juntos (mismo código);
* cada cambio deja un evento en `org_outbox` que el motor de replicación lleva
  al servidor central (y la migración 352 pone la estructura que ya existía);
* centros de costo/utilidad y departamentos de RR. HH. cuelgan de una unidad.
"""

from __future__ import annotations

import importlib
import json
import sqlite3
from datetime import datetime, timezone

import pytest

from backend.application.configuracion.authorization import ConfiguracionAuthorizationPolicy
from backend.application.organization.org_structure_service import OrgStructureService
from backend.domain.organization.org_unit import OrgUnitError
from backend.domain.settings.exceptions import ConfigurationInvalidValueError
from backend.infrastructure.db.repositories.settings.audit_log_repository import (
    SqliteAuditLogRepository,
)
from backend.security.credentials.password_hasher import BcryptPasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.provisioning.installation_repository import SqliteInstallationRepository
from backend.security.provisioning.provision_installation_use_case import (
    ProvisionInstallationUseCase,
)
from backend.security.provisioning.recovery_code_repository import SqliteRecoveryCodeRepository
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db

_351 = importlib.import_module("migrations.standalone.351_organizational_structure")
_352 = importlib.import_module("migrations.standalone.352_org_outbox_and_branch_profiles")
ACTOR = "01a00000-0000-7000-8000-0000000000a1"
CORREGIDORA = "01a00000-0000-7000-8000-0000000000b2"


def _provision(conn):
    ProvisionInstallationUseCase(
        conn, installation_repository=SqliteInstallationRepository(conn),
        recovery_code_repository=SqliteRecoveryCodeRepository(conn),
        password_hasher=BcryptPasswordHasher(), password_policy=PasswordPolicy(),
    ).execute(company_name="Carnicería SPJ", company_rfc="SPJ010101AAA",
              branch_name="Sucursal Centro", branch_address="Av. 1", workstation_name="Caja 1",
              owner_username="dueno", owner_password="Correct-Horse-9!",
              owner_full_name="Dueño", owner_recovery_contact="d@example.com",
              now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    conn.commit()


def _service(conn):
    return OrgStructureService(conn, authorization=ConfiguracionAuthorizationPolicy
                               .permissive_for_tests(), actor=lambda: ACTOR,
                               audit_log=SqliteAuditLogRepository(conn))


@pytest.fixture
def db():
    """Base aprovisionada antes de la 351 + una sucursal legacy sin perfil; luego
    351 y 352, como la actualización real."""
    conn = make_db()
    _provision(conn)
    conn.execute("INSERT INTO sucursales (id, nombre, activa) VALUES (?, 'Corregidora', 1)",
                 (CORREGIDORA,))
    conn.commit()
    _351.run(conn)
    _352.run(conn)
    return conn


def _perfil(conn, branch_id):
    return conn.execute("SELECT code, name, active, timezone FROM branch_profiles"
                        " WHERE branch_id=?", (branch_id,)).fetchone()


def _eventos(conn, unit_id):
    return [json.loads(r[0]) for r in conn.execute(
        "SELECT payload_json FROM org_outbox WHERE entity_id=? ORDER BY created_at, rowid",
        (unit_id,))]


# ── perfil de sucursal ────────────────────────────────────────────────────
def test_352_gives_every_site_a_profile_with_its_unit_code(db):
    assert _perfil(db, CORREGIDORA)[:3] == ("CORREGIDORA", "Corregidora", 1)
    sin_perfil = db.execute("SELECT COUNT(*) FROM org_units u WHERE unit_type <> 'REGION'"
                            " AND NOT EXISTS (SELECT 1 FROM branch_profiles b"
                            " WHERE b.branch_id = u.id)").fetchone()[0]
    assert sin_perfil == 0


def test_new_branch_is_unit_branch_row_and_profile_with_one_code(db):
    svc = _service(db)
    u = svc.create_branch(code="norte", name="Sucursal Norte")
    assert db.execute("SELECT nombre FROM sucursales WHERE id=?", (u.id,)).fetchone()[0] == \
        "Sucursal Norte"
    code, name, active, zona = _perfil(db, u.id)
    assert (code, name, active) == ("NORTE", "Sucursal Norte", 1)
    assert zona   # zona horaria de la empresa
    # Renombrar la unidad renombra la sucursal y el perfil; cerrarla los desactiva.
    svc.update_unit(u.id, name="Norte II", code="NTE")
    assert _perfil(db, u.id)[:2] == ("NTE", "Norte II")
    svc.close(u.id, reason="Cierre")
    assert _perfil(db, u.id)[2] == 0


def test_editing_the_profile_updates_the_unit(db):
    from backend.application.use_cases.configuracion.company_branch_use_cases import (
        UpdateBranchProfileUseCase,
    )
    UpdateBranchProfileUseCase(db).execute(branch_id=CORREGIDORA, name="Corregidora Centro",
                                           code="CRG")
    fila = db.execute("SELECT code, name FROM org_units WHERE id=?", (CORREGIDORA,)).fetchone()
    assert tuple(fila) == ("CRG", "Corregidora Centro")
    assert db.execute("SELECT nombre FROM sucursales WHERE id=?",
                      (CORREGIDORA,)).fetchone()[0] == "Corregidora Centro"
    assert _eventos(db, CORREGIDORA)[-1]["event_name"] == "ORG_UNIT_UPDATED"


def test_a_profile_code_taken_by_another_unit_changes_nothing(db):
    from backend.application.use_cases.configuracion.company_branch_use_cases import (
        UpdateBranchProfileUseCase,
    )
    _service(db).create_unit(unit_type="REGION", code="BAJIO", name="Bajío")
    with pytest.raises(ConfigurationInvalidValueError, match="BAJIO"):
        UpdateBranchProfileUseCase(db).execute(branch_id=CORREGIDORA, name="X", code="BAJIO")
    assert _perfil(db, CORREGIDORA)[:2] == ("CORREGIDORA", "Corregidora")


# ── hacia el servidor central ─────────────────────────────────────────────
def test_352_queues_the_existing_structure_once(db):
    for uid in (CORREGIDORA,):
        eventos = _eventos(db, uid)
        assert [e["event_name"] for e in eventos] == ["ORG_UNIT_REGISTERED"]
        assert eventos[0]["payload"]["code"] == "CORREGIDORA"
        assert len(eventos[0]["payload"]["capabilities"]) == 11
        assert "branch_id" not in eventos[0]["payload"]
    antes = db.execute("SELECT COUNT(*) FROM org_outbox").fetchone()[0]
    _352.run(db)
    assert db.execute("SELECT COUNT(*) FROM org_outbox").fetchone()[0] == antes


def test_every_command_emits_a_full_snapshot(db):
    svc = _service(db)
    region = svc.create_unit(unit_type="REGION", code="SUR", name="Sur")
    alm = svc.create_unit(unit_type="WAREHOUSE", code="ALM-S", name="Almacén Sur",
                          parent_id=region.id)
    svc.set_capability(alm.id, "PURCHASING", enabled=True, reason="Compra directa")
    svc.move_unit(alm.id, None)
    nombres = [e["event_name"] for e in _eventos(db, alm.id)]
    assert nombres == ["ORG_UNIT_CREATED", "ORG_UNIT_CAPABILITIES_CHANGED", "ORG_UNIT_MOVED"]
    ultimo = _eventos(db, alm.id)[-1]
    assert ultimo["payload"]["parent_id"] is None and "PURCHASING" in \
        ultimo["payload"]["capabilities"]
    assert ultimo["user_id"] == ACTOR


def test_a_failed_command_leaves_no_event(db):
    antes = db.execute("SELECT COUNT(*) FROM org_outbox").fetchone()[0]
    with pytest.raises(OrgUnitError):
        _service(db).create_unit(unit_type="RETAIL_BRANCH", code="MAL", name="Mal",
                                 capabilities=["POS"])
    assert db.execute("SELECT COUNT(*) FROM org_outbox").fetchone()[0] == antes


def test_replication_reads_org_events_with_the_station_branch(db):
    from backend.infrastructure.sync.replication_sources import DEFAULT_SOURCES
    fuente = next(f for f in DEFAULT_SOURCES if f.table == "org_outbox")
    filas = fuente.pending_rows(db, limit=50) if db.execute(
        "SELECT 1 FROM sqlite_master WHERE name='replication_envelopes'").fetchone() else None
    if filas is None:
        importlib.import_module("migrations.standalone.350_replication_engine").run(db)
        filas = fuente.pending_rows(db, limit=50)
    estacion = new_uuid()
    evento, agregado = fuente.normalize(filas[0], station_branch_id=estacion)
    assert agregado == "organization.org_unit"
    assert evento["branch_id"] == estacion   # el central exige la sucursal de la estación
    assert evento["entity_id"] == evento["payload"]["unit_id"]


def test_provisioning_queues_the_initial_unit():
    conn = make_db()
    _351.run(conn)
    _352.run(conn)
    _provision(conn)
    sucursal = conn.execute("SELECT initial_branch_id FROM installation").fetchone()[0]
    assert [e["event_name"] for e in _eventos(conn, sucursal)] == ["ORG_UNIT_CREATED"]
    assert _perfil(conn, sucursal)[0] == "SUCURSAL-CENTRO"


# ── Finanzas y RR. HH. ────────────────────────────────────────────────────
def _finanzas():
    from backend.infrastructure.db.schema.finance_schema import create_finance_schema
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_finance_schema(conn)
    _351.create_org_structure_schema(conn)
    ahora = "2026-10-25T00:00:00+00:00"
    empresa = new_uuid()
    unidades = {"sucursal": (new_uuid(), "RETAIL_BRANCH"), "region": (new_uuid(), "REGION")}
    for codigo, (uid, tipo) in unidades.items():
        conn.execute("INSERT INTO org_units (id, company_id, unit_type, code, name, status,"
                     " created_at, updated_at) VALUES (?,?,?,?,?,'ACTIVE',?,?)",
                     (uid, empresa, tipo, codigo.upper(), codigo, ahora, ahora))
    return conn, {k: v[0] for k, v in unidades.items()}


def test_cost_and_profit_centers_hang_from_an_org_unit():
    from backend.application.finance.authorization import (
        AllowAllFinancePermissionCheckerForTests,
        FinanceAuthorizationPolicy,
    )
    from backend.application.finance.finance_commands import FinanceCommandService
    from backend.application.use_cases.finance.finance_configuration_use_cases import (
        ManageDimensionsUseCase,
    )
    from backend.domain.finance.exceptions import FinanceDomainError
    conn, ids = _finanzas()
    svc = FinanceCommandService(
        connection_provider=lambda: conn, use_cases={"dimensions": ManageDimensionsUseCase()},
        authorization=FinanceAuthorizationPolicy(AllowAllFinancePermissionCheckerForTests()),
        actor_provider=lambda: ACTOR)
    svc.create_dimension(kind="COST_CENTER", code="CC-SUC", name="Operación",
                         org_unit_id=ids["sucursal"])
    svc.create_dimension(kind="PROFIT_CENTER", code="PC-REG", name="Región",
                         org_unit_id=ids["region"])
    filas = {r["code"]: (r["branch_id"], r["org_unit_id"]) for r in conn.execute(
        "SELECT code, branch_id, org_unit_id FROM cost_centers UNION ALL"
        " SELECT code, branch_id, org_unit_id FROM profit_centers")}
    # Un sitio: su id ES el branch_id de los asientos. Una región: sin branch_id.
    assert filas["CC-SUC"] == (ids["sucursal"], ids["sucursal"])
    assert filas["PC-REG"] == (None, ids["region"])
    with pytest.raises(FinanceDomainError, match="no existe"):
        svc.create_dimension(kind="COST_CENTER", code="CC-X", name="X", org_unit_id=new_uuid())


def test_finance_contract_does_not_depend_on_columns_added_after_345():
    from backend.infrastructure.db.schema.finance_schema import (
        create_finance_schema,
        finance_schema_differences,
    )
    conn = sqlite3.connect(":memory:")
    create_finance_schema(conn)
    # Una base anterior a la 351: centros sin `org_unit_id`.
    for tabla in ("cost_centers", "profit_centers"):
        conn.execute(f"DROP TABLE {tabla}")
    conn.execute("CREATE TABLE cost_centers (id TEXT PRIMARY KEY, code TEXT, name TEXT,"
                 " parent_id TEXT, branch_id TEXT, active INTEGER, created_at TEXT)")
    conn.execute("CREATE TABLE profit_centers (id TEXT PRIMARY KEY, code TEXT, name TEXT,"
                 " branch_id TEXT, active INTEGER, created_at TEXT)")
    assert "cost_centers" not in finance_schema_differences(conn)
    assert "profit_centers" not in finance_schema_differences(conn)


def test_hr_department_belongs_to_an_org_unit():
    from backend.application.use_cases.hr.employee_use_cases import ManageCatalogUseCase
    from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy
    from backend.infrastructure.db.schema.hr_schema import create_hr_schema

    class _Concede:
        def has_permission(self, user_id, permission_code):
            return True

    conn, ids = _finanzas()
    create_hr_schema(conn)
    uc = ManageCatalogUseCase(AuthorizationPolicy(_Concede()))
    oficina = uc.create_department(conn, actor_user_id=ACTOR, code="DIR", name="Dirección",
                                   org_unit_id=ids["region"])
    tienda = uc.create_department(conn, actor_user_id=ACTOR, code="VTA", name="Ventas",
                                  branch_id=ids["sucursal"])
    assert oficina.success and tienda.success
    filas = {r[0]: (r[1], r[2]) for r in conn.execute(
        "SELECT code, branch_id, org_unit_id FROM hr_departments")}
    assert filas["DIR"] == (None, ids["region"])
    assert filas["VTA"] == (ids["sucursal"], ids["sucursal"])   # la sucursal de la sesión
    malo = uc.create_department(conn, actor_user_id=ACTOR, code="X", name="X",
                                org_unit_id=new_uuid())
    assert not malo.success
