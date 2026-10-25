"""Estructura organizacional (auditoría enterprise, Fase 1): migración 351,
servicio con autorización en la capa de aplicación, auditoría y la unidad de la
sucursal inicial al aprovisionar."""

from __future__ import annotations

import importlib
from datetime import datetime, timezone

import pytest

from backend.application.configuracion.authorization import (
    ConfiguracionAuthorizationPolicy,
    DenyAllConfiguracionPermissionCheckerForTests,
)
from backend.application.organization.org_structure_service import (
    OrgStructureQueryService,
    OrgStructureService,
)
from backend.domain.organization.org_unit import (
    Capability,
    OrgUnitError,
    OrgUnitStatus,
    OrgUnitType,
)
from backend.domain.settings.exceptions import ConfigurationPermissionDeniedError
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
from tests.integration._born_clean_db import make_db

_351 = importlib.import_module("migrations.standalone.351_organizational_structure")
ACTOR = "01a00000-0000-7000-8000-0000000000a1"


def _provision(conn, branch_name="Sucursal Centro"):
    uc = ProvisionInstallationUseCase(
        conn, installation_repository=SqliteInstallationRepository(conn),
        recovery_code_repository=SqliteRecoveryCodeRepository(conn),
        password_hasher=BcryptPasswordHasher(), password_policy=PasswordPolicy())
    result = uc.execute(
        company_name="Carnicería SPJ", company_rfc="SPJ010101AAA", branch_name=branch_name,
        branch_address="Av. Principal 123", workstation_name="Caja 1",
        owner_username="dueno", owner_password="Correct-Horse-9!", owner_full_name="Dueño",
        owner_recovery_contact="dueno@example.com",
        now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    conn.commit()
    return result.installation


def _service(conn, *, deny=False):
    policy = (ConfiguracionAuthorizationPolicy(DenyAllConfiguracionPermissionCheckerForTests())
              if deny else ConfiguracionAuthorizationPolicy.permissive_for_tests())
    return OrgStructureService(conn, authorization=policy, actor=lambda: ACTOR,
                               audit_log=SqliteAuditLogRepository(conn))


@pytest.fixture
def db():
    """Instalación aprovisionada ANTES de la 351 (el caso de la base real), con una
    segunda sucursal legacy dada de alta a mano."""
    conn = make_db()
    inst = _provision(conn)
    conn.execute("INSERT INTO sucursales (id, nombre, activa) VALUES"
                 " ('01a00000-0000-7000-8000-0000000000b2', 'Corregidora', 1)")
    conn.commit()
    _351.run(conn)
    return conn, inst


# ── migración 351 ─────────────────────────────────────────────────────────
def test_351_backfills_every_branch_with_same_id_and_all_capabilities(db):
    conn, inst = db
    filas = conn.execute("SELECT id, company_id, unit_type, code, status FROM org_units"
                         " ORDER BY code").fetchall()
    assert [(r[0], r[2], r[3], r[4]) for r in filas] == [
        ("01a00000-0000-7000-8000-0000000000b2", "RETAIL_BRANCH", "CORREGIDORA", "ACTIVE"),
        # «Principal» la siembra el esquema base (también existe en la base real).
        ("01900000-0000-7000-8000-000000000001", "RETAIL_BRANCH", "PRINCIPAL", "ACTIVE"),
        (inst.initial_branch_id, "RETAIL_BRANCH", "SUCURSAL-CENTRO", "ACTIVE")]
    assert {r[1] for r in filas} == {inst.company_id}
    for fila in filas:
        assert OrgStructureQueryService(conn).has_capability(fila[0], Capability.POS)
        assert len(conn.execute("SELECT 1 FROM org_unit_capabilities WHERE org_unit_id=?",
                                (fila[0],)).fetchall()) == len(Capability)


def test_351_is_idempotent_and_adds_org_unit_columns(db):
    conn, _ = db
    _351.run(conn)
    assert conn.execute("SELECT COUNT(*) FROM org_units").fetchone()[0] == 3
    for tabla in ("cost_centers", "profit_centers", "hr_departments"):
        conn.execute(f"CREATE TABLE IF NOT EXISTS {tabla} (id TEXT PRIMARY KEY)")
    _351.run(conn)
    for tabla in ("cost_centers", "profit_centers", "hr_departments"):
        assert "org_unit_id" in [r[1] for r in conn.execute(f"PRAGMA table_info({tabla})")]


def test_351_without_company_skips_backfill():
    conn = make_db()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES"
                 " ('01a00000-0000-7000-8000-0000000000b3', 'Sin empresa')")
    _351.run(conn)
    assert conn.execute("SELECT COUNT(*) FROM org_units").fetchone()[0] == 0


def test_351_seeds_permissions_by_role():
    conn = make_db()
    for rol in ("admin", "gerente", "cajero"):
        conn.execute("INSERT OR IGNORE INTO roles (id, nombre) VALUES (?, ?)",
                     (f"01a00000-0000-7000-8000-00000000{len(rol):04d}", rol))
    _351.run(conn)

    def acciones(rol):
        return {r[0] for r in conn.execute(
            "SELECT p.accion FROM rol_permisos p JOIN roles r ON r.id = p.rol_id"
            " WHERE r.nombre=? AND p.modulo='CONFIGURACION' AND p.accion LIKE 'organizacion.%'",
            (rol,))}
    assert acciones("admin") == set(_351.ACCIONES)
    assert acciones("gerente") == {"organizacion.ver"}
    assert acciones("cajero") == set()


def test_new_installation_gets_its_initial_unit_from_provisioning():
    conn = make_db()
    _351.run(conn)
    inst = _provision(conn, branch_name="Matriz")
    unidad = OrgStructureQueryService(conn).get(inst.initial_branch_id)
    assert unidad is not None and unidad.company_id == inst.company_id
    assert unidad.code == "MATRIZ" and unidad.unit_type is OrgUnitType.RETAIL_BRANCH
    assert OrgStructureQueryService(conn).has_capability(unidad.id, Capability.CASH)


# ── servicio ──────────────────────────────────────────────────────────────
def test_creating_a_site_unit_creates_its_branch_row(db):
    conn, inst = db
    svc = _service(conn)
    region = svc.create_unit(unit_type="REGION", code="BAJIO", name="Región Bajío")
    planta = svc.create_unit(unit_type=OrgUnitType.PRODUCTION_PLANT, code="PLANTA-QRO",
                             name="Planta Querétaro", parent_id=region.id)
    # El sitio nuevo ya es un `branch_id` válido para todos los módulos (N12).
    assert conn.execute("SELECT nombre, activa FROM sucursales WHERE id=?",
                        (planta.id,)).fetchone()[:] == ("Planta Querétaro", 1)
    # Una región sólo agrupa: no tiene fila de sucursal.
    assert conn.execute("SELECT 1 FROM sucursales WHERE id=?", (region.id,)).fetchone() is None
    q = OrgStructureQueryService(conn)
    assert q.has_capability(planta.id, Capability.PRODUCTION)
    assert not q.has_capability(planta.id, Capability.POS)
    assert q.operating_site_ids_under(region.id) == [planta.id]
    arbol = svc.tree()
    assert [(n.unit.code, n.depth) for n in arbol if n.unit.code in ("BAJIO", "PLANTA-QRO")] == [
        ("BAJIO", 0), ("PLANTA-QRO", 1)]
    assert [n.unit.id for n in arbol if n.is_installation_site] == [inst.initial_branch_id]


def test_codes_are_unique_within_the_company(db):
    conn, _ = db
    svc = _service(conn)
    with pytest.raises(OrgUnitError, match="ya lo usa"):
        svc.create_unit(unit_type="WAREHOUSE", code="corregidora", name="Otro")
    otra = svc.create_unit(unit_type="WAREHOUSE", code="ALM-1", name="Almacén 1")
    with pytest.raises(OrgUnitError, match="ya lo usa"):
        svc.update_unit(otra.id, name="Almacén 1", code="CORREGIDORA")


def test_move_rename_and_audit_trail(db):
    conn, inst = db
    svc = _service(conn)
    region = svc.create_unit(unit_type="REGION", code="NORTE", name="Norte")
    svc.move_unit(inst.initial_branch_id, region.id)
    svc.update_unit(inst.initial_branch_id, name="Centro Histórico")
    assert conn.execute("SELECT nombre FROM sucursales WHERE id=?",
                        (inst.initial_branch_id,)).fetchone()[0] == "Centro Histórico"
    acciones = [r[0] for r in conn.execute(
        "SELECT accion FROM audit_logs WHERE entidad='org_unit' AND entidad_id=?"
        " ORDER BY rowid", (inst.initial_branch_id,))]
    assert acciones == ["ORG_UNIT_MOVED", "ORG_UNIT_UPDATED"]
    with pytest.raises(OrgUnitError, match="ciclo"):
        svc.move_unit(region.id, region.id)


def test_installation_site_and_open_shifts_block_closing(db):
    conn, inst = db
    svc = _service(conn)
    with pytest.raises(OrgUnitError, match="sucursal de esta instalación"):
        svc.deactivate(inst.initial_branch_id, reason="Remodelación")
    with pytest.raises(OrgUnitError, match="motivo"):
        svc.close("01a00000-0000-7000-8000-0000000000b2", reason="  ")
    cerrada = svc.close("01a00000-0000-7000-8000-0000000000b2", reason="Cierre definitivo")
    assert cerrada.status is OrgUnitStatus.CLOSED
    assert conn.execute("SELECT activa FROM sucursales WHERE id=?",
                        (cerrada.id,)).fetchone()[0] == 0
    with pytest.raises(OrgUnitError, match="cerrada"):
        svc.reactivate(cerrada.id, reason="Error")


def test_region_with_active_children_cannot_be_deactivated(db):
    conn, inst = db
    svc = _service(conn)
    region = svc.create_unit(unit_type="REGION", code="SUR", name="Sur")
    alm = svc.create_unit(unit_type="WAREHOUSE", code="ALM-S", name="Almacén Sur",
                          parent_id=region.id)
    with pytest.raises(OrgUnitError, match="dependiente"):
        svc.deactivate(region.id, reason="Reorganización")
    svc.deactivate(alm.id, reason="Reorganización")
    svc.deactivate(region.id, reason="Reorganización")
    with pytest.raises(OrgUnitError, match="Reactive primero"):
        svc.reactivate(alm.id, reason="Vuelve")


def test_capabilities_change_with_reason_and_rules(db):
    conn, inst = db
    svc = _service(conn)
    alm = svc.create_unit(unit_type="WAREHOUSE", code="ALM-2", name="Almacén 2")
    caps = svc.set_capability(alm.id, "PURCHASING", enabled=True, reason="Compra directa")
    assert Capability.PURCHASING in caps
    with pytest.raises(OrgUnitError, match="POS requiere"):
        svc.set_capability(alm.id, Capability.POS, enabled=True, reason="Mostrador")
    region = svc.create_unit(unit_type="REGION", code="OESTE", name="Oeste")
    with pytest.raises(OrgUnitError, match="no opera"):
        svc.set_capability(region.id, Capability.INVENTORY, enabled=True, reason="x")
    with pytest.raises(OrgUnitError, match="POS requiere"):
        svc.set_capability(inst.initial_branch_id, Capability.SALES, enabled=False,
                           reason="Sólo almacén")
    fila = conn.execute("SELECT accion, detalles FROM audit_logs WHERE entidad_id=?"
                        " AND accion LIKE 'ORG_UNIT_CAPABILITY%'", (alm.id,)).fetchone()
    assert fila[0] == "ORG_UNIT_CAPABILITY_GRANTED" and "Compra directa" in fila[1]


def test_every_command_and_the_tree_are_authorized_in_the_application_layer(db):
    conn, inst = db
    svc = _service(conn, deny=True)
    for accion in (
        lambda: svc.tree(),
        lambda: svc.create_unit(unit_type="REGION", code="X1", name="X"),
        lambda: svc.update_unit(inst.initial_branch_id, name="X"),
        lambda: svc.move_unit(inst.initial_branch_id, None),
        lambda: svc.deactivate(inst.initial_branch_id, reason="x"),
        lambda: svc.close(inst.initial_branch_id, reason="x"),
        lambda: svc.set_capability(inst.initial_branch_id, "BI", enabled=False, reason="x"),
    ):
        with pytest.raises(ConfigurationPermissionDeniedError):
            accion()
    assert conn.execute("SELECT COUNT(*) FROM org_units").fetchone()[0] == 3


def test_failed_command_rolls_back_both_rows(db):
    conn, _ = db
    svc = _service(conn)
    with pytest.raises(OrgUnitError):
        svc.create_unit(unit_type="RETAIL_BRANCH", code="NUEVA", name="Nueva",
                        capabilities=["POS"])   # POS sin SALES/CASH
    assert conn.execute("SELECT COUNT(*) FROM sucursales WHERE nombre='Nueva'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM org_units WHERE code='NUEVA'").fetchone()[0] == 0


def test_several_capability_changes_are_one_operation(db):
    conn, inst = db
    svc = _service(conn)
    sitio = inst.initial_branch_id
    # BI se quitaría, pero SALES no puede irse mientras POS siga: no queda ninguno.
    with pytest.raises(OrgUnitError, match="POS requiere"):
        svc.apply_capability_changes(sitio, [("BI", False), ("SALES", False)], reason="x")
    assert OrgStructureQueryService(conn).has_capability(sitio, Capability.BI)
    caps = svc.apply_capability_changes(
        sitio, [("POS", False), ("SALES", False), ("CASH", False)], reason="Sólo almacén")
    assert not caps & {Capability.POS, Capability.SALES, Capability.CASH}
    assert conn.execute("SELECT COUNT(*) FROM audit_logs WHERE entidad_id=? AND accion ="
                        " 'ORG_UNIT_CAPABILITY_REVOKED'", (sitio,)).fetchone()[0] == 3
