"""SDLC-SET-001: anclar la sucursal de la instalación mueve la sesión EN CALIENTE.

Antes la página llamaba `main_win.aplicar_sucursal_activa(...)`, un método que no
existe, tras `hasattr` + `except: pass`: la sesión seguía operando la sucursal
anterior hasta reiniciar. Aquí se recorre el camino real: ventana de
`build_application_window`, página Empresa, caso de uso y contexto de sesión.
"""
from __future__ import annotations

import dataclasses
import importlib
import os
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication, QDialog  # noqa: E402

from backend.application.configuracion.authorization import (  # noqa: E402
    ConfiguracionAuthorizationPolicy,
)
from backend.application.configuracion.permissions import ConfiguracionPermissions  # noqa: E402
from backend.application.organization.org_structure_service import OrgStructureService  # noqa: E402
from backend.bootstrap.application_context_builder import ApplicationContextBuilder  # noqa: E402
from backend.bootstrap.health.health_status import HealthReport, HealthStatus  # noqa: E402
from backend.bootstrap.legacy_session_adapter import LegacySessionAdapter  # noqa: E402
from backend.infrastructure.db.repositories.settings.installation_branch_repository import (  # noqa: E402
    SqliteInstallationBranchRepository,
)
from backend.security.credentials.password_hasher import BcryptPasswordHasher  # noqa: E402
from backend.security.credentials.password_policy import PasswordPolicy  # noqa: E402
from backend.security.provisioning.installation_repository import SqliteInstallationRepository  # noqa: E402
from backend.security.provisioning.provision_installation_use_case import (  # noqa: E402
    ProvisionInstallationUseCase,
)
from backend.security.provisioning.recovery_code_repository import SqliteRecoveryCodeRepository  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402
from frontend.desktop.components.dialogs import MessageDialog  # noqa: E402
from frontend.desktop.modules.configuracion.pages import empresa_page  # noqa: E402
from frontend.desktop.modules.configuracion.shell_registration import (  # noqa: E402
    CONFIGURACION_ROUTE_ID,
)
from frontend.desktop.modules.sales_pos.shell_registration import SALES_POS_ROUTE_ID  # noqa: E402
from frontend.desktop.shell.desktop_shell_window_composition import (  # noqa: E402
    build_application_window,
)
from tests.integration._born_clean_db import make_db  # noqa: E402

MIGRACIONES = ("347_permissions_audit_968e0bc", "351_organizational_structure",
               "352_org_outbox_and_branch_profiles", "353_user_role_assignments")


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def org():
    conn = make_db()
    for nombre in MIGRACIONES:
        importlib.import_module(f"migrations.standalone.{nombre}").run(conn)
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
    conn.execute("UPDATE configuraciones SET valor=? WHERE clave='sucursal_instalacion_id'",
                 (centro,))
    conn.commit()
    return SimpleNamespace(conn=conn, centro=centro, chihuahua=chihuahua.id, planta=planta.id,
                           dueno=dueno)


def _gerente_local(org) -> str:
    """Usuario con Configuración, pero cuyo rol sólo vale en su sucursal propia."""
    rol_id, uid = new_uuid(), new_uuid()
    org.conn.execute("INSERT INTO roles (id, nombre) VALUES (?, 't_gerente_local')", (rol_id,))
    for permiso in (ConfiguracionPermissions.GENERAL_VIEW, ConfiguracionPermissions.EMPRESA_VIEW,
                    ConfiguracionPermissions.EMPRESA_EDITAR, ConfiguracionPermissions.USUARIOS_VIEW,
                    # SDLC-ARQ-TERM-002: re-anclar ya no basta con editar la empresa.
                    ConfiguracionPermissions.ESTACION_REANCLAR):
        modulo, accion = permiso.split(".", 1)
        org.conn.execute(
            "INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
            " VALUES (?,?,?,?,1)", (new_uuid(), rol_id, modulo, accion))
    org.conn.execute(
        "INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id, activo)"
        " VALUES (?,?,?,?,?,?,1)",
        (uid, "Gerente", f"gerente-{uid[-6:]}", "x", "t_gerente_local", org.centro))
    org.conn.commit()
    return uid


def _ventana(org, user_id, rol):
    auth = SimpleNamespace(
        credentials=SimpleNamespace(id=user_id, role=rol, branch_id=org.centro,
                                    full_name="Usuario", username="usuario"),
        session=SimpleNamespace(session_id=new_uuid(), workstation_id="ws-1"))
    context = ApplicationContextBuilder(org.conn).build(auth)
    session = LegacySessionAdapter(context)
    window = build_application_window(
        context=context, connection=org.conn, session_context=session,
        health_report=HealthReport(overall_status=HealthStatus.HEALTHY, checks=(),
                                   generated_at=datetime.now(timezone.utc)))
    return window, session


def _pagina_empresa(window):
    view = window.navigate(CONFIGURACION_ROUTE_ID).view
    view.show_route("config_empresa")
    return view._pages["config_empresa"]


class _Dialogo:
    """El diálogo de anclaje, ya aceptado con la sucursal elegida."""
    destino = ""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def exec_(self) -> int:
        return QDialog.Accepted

    def values(self) -> dict:
        return {"branch_id": type(self).destino}


@pytest.fixture
def avisos(monkeypatch):
    registro: list[tuple[str, str]] = []
    monkeypatch.setattr(empresa_page, "SetInstallationBranchDialog", _Dialogo)
    monkeypatch.setattr(MessageDialog, "question",
                        staticmethod(lambda *a, **k: MessageDialog.Yes))
    monkeypatch.setattr(MessageDialog, "information",
                        staticmethod(lambda _p, _t, texto: registro.append(("info", texto))))
    monkeypatch.setattr(MessageDialog, "warning",
                        staticmethod(lambda _p, _t, texto: registro.append(("warn", texto))))
    return registro


def _anclar(pagina, destino: str) -> None:
    _Dialogo.destino = destino
    pagina._on_anchor_installation()


def _rutas(window) -> set[str]:
    return {item.route_id for item in window.sidebar._all_items}


def test_anchoring_moves_the_open_session_to_the_anchored_branch(app, org, avisos):
    window, session = _ventana(org, org.dueno, "system_owner")
    assert session.active_branch_id == org.centro

    _anclar(_pagina_empresa(window), org.chihuahua)

    assert SqliteInstallationBranchRepository(org.conn).get()[0] == org.chihuahua
    assert session.active_branch_id == org.chihuahua
    assert session.sucursal_nombre == "Chihuahua"
    context = window.router.current_context
    assert (context.branch_id, context.branch_name) == (org.chihuahua, "Chihuahua")
    assert "Chihuahua" in window.top_bar._context_label.text()
    assert "Chihuahua" in window.status_bar._workstation_label.text()
    assert [nivel for nivel, _ in avisos] == ["info"]
    assert "Chihuahua" in avisos[0][1]


def test_the_session_takes_the_capabilities_of_the_new_site_and_the_menu_follows(app, org, avisos):
    window, session = _ventana(org, org.dueno, "system_owner")
    assert SALES_POS_ROUTE_ID in _rutas(window)

    _anclar(_pagina_empresa(window), org.planta)

    assert session.active_branch_id == org.planta
    assert not window.router.current_context.site_allows_module("sales_pos")
    assert not session.tiene_permiso("DELIVERY.ver")     # sin SALES en una planta
    assert SALES_POS_ROUTE_ID not in _rutas(window)


def test_a_user_without_a_role_at_the_new_site_loses_the_session_explicitly(app, org, avisos):
    window, session = _ventana(org, _gerente_local(org), "t_gerente_local")
    cierres: list[bool] = []
    window.logout_requested.connect(lambda: cierres.append(True))

    _anclar(_pagina_empresa(window), org.chihuahua)

    assert SqliteInstallationBranchRepository(org.conn).get()[0] == org.chihuahua
    assert [nivel for nivel, _ in avisos] == ["warn"]
    assert "Chihuahua" in avisos[0][1] and "cerrar" in avisos[0][1].lower()
    assert cierres == [True]
    # No se fabrica un contexto en la sucursal nueva para quien no tiene rol ahí.
    assert session.active_branch_id == org.centro


def test_a_user_who_cannot_see_the_screen_at_the_new_site_is_moved_out_of_it(app, org, avisos):
    uid = _gerente_local(org)
    rol_id = new_uuid()
    org.conn.execute("INSERT INTO roles (id, nombre) VALUES (?, 't_cajero_norte')", (rol_id,))
    org.conn.execute("INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                     " VALUES (?,?,'INVENTARIO','ver',1)", (new_uuid(), rol_id))
    org.conn.execute(
        "INSERT INTO user_role_assignments (id, user_id, role_id, scope_type, scope_id,"
        " valid_from, valid_until, status, reason, created_at) VALUES"
        " (?,?,?,'ORG_UNIT',?,NULL,NULL,'ACTIVE','prueba','2026-01-01')",
        (new_uuid(), uid, rol_id, org.chihuahua))
    org.conn.commit()
    window, session = _ventana(org, uid, "t_gerente_local")

    _anclar(_pagina_empresa(window), org.chihuahua)

    assert session.active_branch_id == org.chihuahua
    assert not session.tiene_permiso(ConfiguracionPermissions.EMPRESA_EDITAR)
    assert window.router.current_route_id != CONFIGURACION_ROUTE_ID
    assert window.router.current_route_still_allowed()


def test_the_session_adapter_only_accepts_a_context_of_the_same_session(app, org):
    _window, session = _ventana(org, org.dueno, "system_owner")
    otro = dataclasses.replace(window_context(_window), session_id=new_uuid())
    with pytest.raises(ValueError):
        session.rebind(otro)
    assert session.active_branch_id == org.centro


def window_context(window):
    return window.router.current_context
