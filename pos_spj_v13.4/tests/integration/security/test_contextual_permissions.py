"""Permisos contextuales (auditoría enterprise, Fase 2; N01/N02/N03, decisión D4).

Escenario: empresa con «Centro» (sucursal propia del cajero), una región «Norte»
con «Chihuahua» y una planta sin punto de venta. La estación está anclada a una
sucursal; cada rol vale sólo donde su ámbito llega.
"""

from __future__ import annotations

import importlib
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.application.configuracion.authorization import (
    ConfiguracionAuthorizationPolicy,
    DenyAllConfiguracionPermissionCheckerForTests,
)
from backend.application.organization.org_structure_service import OrgStructureService
from backend.application.security.access_scope import AccessScopeResolver
from backend.application.security.permission_query_service import PermissionQueryService
from backend.application.security.role_assignment_service import RoleAssignmentService
from backend.application.security.session_grant_refresh import SessionGrantRefresher
from backend.bootstrap.application_context_builder import ApplicationContextBuilder
from backend.bootstrap.application_context_errors import SiteAccessDeniedError
from backend.domain.organization.role_assignment import RoleAssignmentError
from backend.domain.settings.exceptions import ConfigurationPermissionDeniedError
from backend.infrastructure.db.repositories.security.grant_version_repository import (
    SqliteGrantVersionRepository,
)
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)
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

MIGRACIONES = ("347_permissions_audit_968e0bc", "351_organizational_structure", "352_org_outbox_and_branch_profiles",
               "353_user_role_assignments")


class _Concede:
    def has_permission(self, user_id, code):
        return True


@pytest.fixture
def org():
    conn = make_db()
    for m in MIGRACIONES:
        importlib.import_module(f"migrations.standalone.{m}").run(conn)
    ProvisionInstallationUseCase(
        conn, installation_repository=SqliteInstallationRepository(conn),
        recovery_code_repository=SqliteRecoveryCodeRepository(conn),
        password_hasher=BcryptPasswordHasher(), password_policy=PasswordPolicy(),
    ).execute(company_name="SPJ", company_rfc="SPJ010101AAA", branch_name="Centro",
              branch_address="x", workstation_name="Caja 1", owner_username="dueno",
              owner_password="Correct-Horse-9!", owner_full_name="Dueño",
              owner_recovery_contact="d@example.com",
              now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    conn.commit()
    centro = conn.execute("SELECT initial_branch_id FROM installation").fetchone()[0]
    dueno = conn.execute("SELECT id FROM usuarios WHERE usuario='dueno'").fetchone()[0]
    svc = OrgStructureService(conn, authorization=ConfiguracionAuthorizationPolicy
                              .permissive_for_tests(), actor=lambda: dueno)
    norte = svc.create_unit(unit_type="REGION", code="NORTE", name="Norte")
    chihuahua = svc.create_branch(code="CHI", name="Chihuahua", parent_id=norte.id)
    planta = svc.create_unit(unit_type="PRODUCTION_PLANT", code="PLANTA", name="Planta")
    ids = SimpleNamespace(conn=conn, centro=centro, norte=norte.id, chihuahua=chihuahua.id,
                          planta=planta.id, dueno=dueno,
                          empresa=conn.execute("SELECT company_id FROM installation")
                          .fetchone()[0])
    # Roles de prueba con UN permiso cada uno (los sembrados traen muchos y se
    # solapan): así se ve qué rol concedió qué.
    for rol, codigos in (("t_cajero", ("POS.ver",)), ("t_gerente", ("INVENTARIO.ver",))):
        rol_id = new_uuid()
        conn.execute("INSERT INTO roles (id, nombre) VALUES (?, ?)", (rol_id, rol))
        for codigo in codigos:
            modulo, accion = codigo.split(".", 1)
            conn.execute("INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion,"
                         " permitido) VALUES (?,?,?,?,1)", (new_uuid(), rol_id, modulo, accion))
    ids.cajero = _usuario(conn, "t_cajero", centro)
    conn.commit()
    return ids


def _rol(conn, nombre):
    fila = conn.execute("SELECT id FROM roles WHERE nombre=?", (nombre,)).fetchone()
    return fila[0]


def _usuario(conn, rol, sucursal):
    uid = new_uuid()
    conn.execute("INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id,"
                 " activo) VALUES (?,?,?,?,?,?,1)", (uid, rol, f"{rol}-{uid[-6:]}", "x", rol,
                                                     sucursal))
    return uid


def _asignar(o, user, rol, scope_type, scope_id, *, desde=None, hasta=None):
    conn = o.conn
    conn.execute("INSERT INTO user_role_assignments (id, user_id, role_id, scope_type, scope_id,"
                 " valid_from, valid_until, status, reason, created_at) VALUES"
                 " (?,?,?,?,?,?,?,'ACTIVE','prueba','2026-01-01')",
                 (new_uuid(), user, _rol(conn, rol), scope_type, scope_id,
                  desde.isoformat() if desde else None, hasta.isoformat() if hasta else None))
    conn.commit()


def _codigos(o, user, sitio):
    return PermissionQueryService(SqlitePermissionRepository(o.conn)).permission_codes_for_user(
        user, sitio)


def _servicio(o, actor, *, negar=False):
    politica = (ConfiguracionAuthorizationPolicy(DenyAllConfiguracionPermissionCheckerForTests())
                if negar else ConfiguracionAuthorizationPolicy(_Concede()))
    return RoleAssignmentService(o.conn, authorization=politica, actor=lambda: actor,
                                 audit_log=SqliteAuditLogRepository(o.conn),
                                 grant_versions=SqliteGrantVersionRepository(o.conn))


# ── ámbito de los roles ───────────────────────────────────────────────────
def test_a_role_only_grants_inside_its_scope(org):
    assert "POS.VER" in _codigos(org, org.cajero, org.centro)
    assert _codigos(org, org.cajero, org.chihuahua) == frozenset()


def test_a_region_assignment_reaches_its_branches_but_not_the_rest(org):
    _asignar(org, org.cajero, "t_gerente", "ORG_UNIT", org.norte)
    en_chi = _codigos(org, org.cajero, org.chihuahua)
    assert "INVENTARIO.VER" in en_chi and "POS.VER" not in en_chi   # el cajero no viaja
    en_centro = _codigos(org, org.cajero, org.centro)
    assert "POS.VER" in en_centro and "INVENTARIO.VER" not in en_centro
    alcance = AccessScopeResolver(SqlitePermissionRepository(org.conn)).reach(org.cajero)
    assert alcance.site_ids == {org.centro, org.chihuahua} and not alcance.company_wide


def test_company_scope_covers_every_site_explicitly(org):
    ceo = _usuario(org.conn, "solo_lectura", None)   # N02: sin sucursal propia
    assert not AccessScopeResolver(SqlitePermissionRepository(org.conn)).covers(ceo, org.centro)
    _asignar(org, ceo, "t_gerente", "COMPANY", org.empresa)
    for sitio in (org.centro, org.chihuahua, org.planta):
        assert "INVENTARIO.VER" in _codigos(org, ceo, sitio)


def test_expired_future_and_revoked_assignments_grant_nothing(org):
    hoy = date.today()
    _asignar(org, org.cajero, "t_gerente", "ORG_UNIT", org.norte, hasta=hoy - timedelta(days=1))
    otro = _usuario(org.conn, "t_cajero", org.centro)
    _asignar(org, otro, "t_gerente", "ORG_UNIT", org.norte, desde=hoy + timedelta(days=1))
    assert _codigos(org, org.cajero, org.chihuahua) == frozenset()
    assert _codigos(org, otro, org.chihuahua) == frozenset()


def test_an_inactive_site_is_not_covered_by_its_region(org):
    _asignar(org, org.cajero, "t_gerente", "ORG_UNIT", org.norte)
    OrgStructureService(org.conn, authorization=ConfiguracionAuthorizationPolicy
                        .permissive_for_tests(), actor=lambda: org.dueno).deactivate(
        org.chihuahua, reason="Remodelación")
    assert _codigos(org, org.cajero, org.chihuahua) == frozenset()


# ── sitio de la sesión (N01) ──────────────────────────────────────────────
def _login(o, user, rol, sucursal):
    return SimpleNamespace(
        credentials=SimpleNamespace(id=user, branch_id=sucursal, role=rol, full_name=rol,
                                    username=rol),
        session=SimpleNamespace(session_id=new_uuid(), workstation_id="ws"))


def _anclar(o, sitio):
    o.conn.execute("UPDATE configuraciones SET valor=? WHERE clave='sucursal_instalacion_id'",
                   (sitio,))
    o.conn.commit()


def test_the_session_operates_the_station_site_not_the_users_home(org):
    _asignar(org, org.cajero, "t_gerente", "ORG_UNIT", org.norte)
    _anclar(org, org.chihuahua)
    ctx = ApplicationContextBuilder(org.conn).build(_login(org, org.cajero, "t_cajero", org.centro))
    assert (ctx.branch_id, ctx.branch_name) == (org.chihuahua, "Chihuahua")
    assert ctx.roles == ("t_gerente",)
    assert "INVENTARIO.VER" in ctx.permissions and "POS.VER" not in ctx.permissions
    assert ctx.assigned_branch_ids == {org.centro, org.chihuahua}


def test_a_user_without_a_role_at_the_station_site_cannot_open_a_session(org):
    _anclar(org, org.chihuahua)
    with pytest.raises(SiteAccessDeniedError, match="Chihuahua"):
        ApplicationContextBuilder(org.conn).build(_login(org, org.cajero, "t_cajero", org.centro))


def test_the_owner_is_company_wide_and_reaches_every_site(org):
    _anclar(org, org.chihuahua)
    ctx = ApplicationContextBuilder(org.conn).build(
        _login(org, org.dueno, "system_owner", org.centro))
    assert ctx.branch_id == org.chihuahua and ctx.is_admin()
    assert {org.centro, org.chihuahua, org.planta} <= ctx.assigned_branch_ids


def test_site_capabilities_gate_modules_and_exclusive_permission_families(org):
    from backend.bootstrap.permission_evaluator import PermissionEvaluator
    _anclar(org, org.planta)
    ctx = ApplicationContextBuilder(org.conn).build(
        _login(org, org.dueno, "system_owner", org.centro))
    assert not ctx.site_allows_module("sales_pos")       # una planta no tiene POS
    assert ctx.site_allows_module("meat_processing") and ctx.site_allows_module("products")
    ev = PermissionEvaluator(ctx)
    assert ev.has_permission("PRODUCCION.ver")
    assert not ev.has_permission("DELIVERY.ver")         # sin SALES: Pedidos bloqueado
    _anclar(org, org.centro)
    ctx = ApplicationContextBuilder(org.conn).build(
        _login(org, org.dueno, "system_owner", org.centro))
    assert ctx.site_allows_module("sales_pos")           # sucursal respaldada: todo


def test_an_open_session_drops_a_revoked_admin_role(org):
    """Antes `is_admin()` miraba los roles del inicio de sesión: un administrador
    degradado seguía saltándose todas las comprobaciones hasta cerrar sesión."""
    from backend.bootstrap.legacy_session_adapter import LegacySessionAdapter

    class _Reloj:
        t = 0.0

        def __call__(self):
            return self.t

    jefe = _usuario(org.conn, "t_cajero", org.centro)
    _asignar(org, jefe, "admin", "ORG_UNIT", org.centro)
    reloj = _Reloj()
    ctx = ApplicationContextBuilder(org.conn).build(_login(org, jefe, "t_cajero", org.centro))
    sesion = LegacySessionAdapter(ctx, grant_refresher=SessionGrantRefresher(org.conn,
                                                                            clock=reloj))
    assert sesion.es_admin and sesion.tiene_permiso("FINANZAS.ver")
    aid = org.conn.execute("SELECT id FROM user_role_assignments WHERE user_id=?",
                           (jefe,)).fetchone()[0]
    _servicio(org, org.dueno).revoke(aid, reason="Ya no es administrador")
    reloj.t += 10
    assert not sesion.tiene_permiso("FINANZAS.ver") and not sesion.es_admin
    assert sesion.tiene_permiso("POS.ver")               # sigue siendo cajero


# ── otorgar y revocar ─────────────────────────────────────────────────────
def test_granting_and_revoking_are_authorized_audited_and_refresh_sessions(org):
    svc = _servicio(org, org.dueno)
    version = SqliteGrantVersionRepository(org.conn).current()
    a = svc.assign(user_id=org.cajero, role_id=_rol(org.conn, "t_gerente"),
                   scope_type="ORG_UNIT", scope_id=org.norte, reason="Cubre la región")
    assert SqliteGrantVersionRepository(org.conn).current() != version
    assert "INVENTARIO.VER" in _codigos(org, org.cajero, org.chihuahua)
    with pytest.raises(RoleAssignmentError, match="Ya tiene"):
        svc.assign(user_id=org.cajero, role_id=_rol(org.conn, "t_gerente"),
                   scope_type="ORG_UNIT", scope_id=org.norte, reason="otra vez")
    svc.revoke(a.id, reason="Terminó la cobertura")
    assert _codigos(org, org.cajero, org.chihuahua) == frozenset()
    acciones = [r[0] for r in org.conn.execute(
        "SELECT accion FROM audit_logs WHERE entidad='user_role_assignment' ORDER BY rowid")]
    assert acciones == ["ROLE_ASSIGNMENT_GRANTED", "ROLE_ASSIGNMENT_REVOKED"]
    filas = svc.list_for_user(org.cajero)
    assert filas[0]["status"] == "REVOKED" and filas[0]["scope_name"] == "Norte"


def test_escalation_and_scope_rules(org):
    svc_dueno = _servicio(org, org.dueno)
    with pytest.raises(RoleAssignmentError, match="sí mismo"):
        svc_dueno.assign(user_id=org.dueno, role_id=_rol(org.conn, "t_gerente"),
                         scope_type="COMPANY", scope_id=org.empresa, reason="x")
    with pytest.raises(RoleAssignmentError, match="dueño"):
        svc_dueno.assign(user_id=org.cajero, role_id=_rol(org.conn, "system_owner"),
                         scope_type="COMPANY", scope_id=org.empresa, reason="x")
    with pytest.raises(RoleAssignmentError, match="esta empresa"):
        svc_dueno.assign(user_id=org.cajero, role_id=_rol(org.conn, "t_gerente"),
                         scope_type="COMPANY", scope_id=new_uuid(), reason="x")
    with pytest.raises(RoleAssignmentError, match="no existe"):
        svc_dueno.assign(user_id=org.cajero, role_id=_rol(org.conn, "t_gerente"),
                         scope_type="ORG_UNIT", scope_id=new_uuid(), reason="x")
    # Un gerente (sin acceso total) no otorga admin ni roles con permisos que no tiene.
    gerente = _usuario(org.conn, "t_gerente", org.centro)
    svc_gerente = _servicio(org, gerente)
    with pytest.raises(RoleAssignmentError, match="acceso total"):
        svc_gerente.assign(user_id=org.cajero, role_id=_rol(org.conn, "admin"),
                           scope_type="ORG_UNIT", scope_id=org.centro, reason="x")
    with pytest.raises(RoleAssignmentError, match="POS.ver"):
        svc_gerente.assign(user_id=org.cajero, role_id=_rol(org.conn, "t_cajero"),
                           scope_type="ORG_UNIT", scope_id=org.chihuahua, reason="x")


def test_every_assignment_operation_is_authorized_in_the_application_layer(org):
    svc = _servicio(org, org.dueno, negar=True)
    for accion in (lambda: svc.list_for_user(org.cajero), lambda: svc.scope_options(),
                   lambda: svc.role_options(),
                   lambda: svc.assign(user_id=org.cajero, role_id=_rol(org.conn, "t_gerente"),
                                      scope_type="COMPANY", scope_id=org.empresa, reason="x"),
                   lambda: svc.revoke(new_uuid(), reason="x")):
        with pytest.raises(ConfigurationPermissionDeniedError):
            accion()


def test_353_seeds_the_assignment_permission_for_admin_roles(org):
    filas = {r[0] for r in org.conn.execute(
        "SELECT r.nombre FROM rol_permisos p JOIN roles r ON r.id=p.rol_id"
        " WHERE p.modulo='CONFIGURACION' AND p.accion='usuario.asignaciones'")}
    assert filas == {"admin", "system_owner"}
