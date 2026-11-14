"""SDLC-ARQ-TERM-001 · la terminal tiene identidad propia, no la del hostname.

Fuente canónica: `workstations` (decisión 2026-11-02). Renombrar el equipo no
cambia la estación. Nunca se abre un `.db` real: cada prueba usa una copia en
memoria del esquema born-clean.
"""
from __future__ import annotations

import importlib
import sqlite3
from types import SimpleNamespace

import pytest

import backend.bootstrap.terminal_identity as terminal_identity
from backend.bootstrap.application_context import ApplicationContext
from backend.bootstrap.application_context_builder import ApplicationContextBuilder
from backend.bootstrap.legacy_session_adapter import LegacySessionAdapter
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.db.repositories.settings.terminal_identity_repository import (
    TERMINAL_ID_KEY,
)
from backend.shared.app_version import VERSION
from backend.shared.ids import is_uuidv7, new_uuid
from backend.shared.sync.replication_envelope import ENVELOPE_VERSION
from tests.integration.configuracion import _reanchor_support as s

_392 = importlib.import_module("migrations.standalone.392_terminal_identity")


@pytest.fixture(scope="module")
def template():
    conn = s.build_template()
    yield conn
    conn.close()


@pytest.fixture
def conn(template):
    copia = s.copy_of(template)
    yield copia
    copia.close()


@pytest.fixture
def host(monkeypatch):
    actual = {"nombre": "CAJA-01"}
    monkeypatch.setattr(terminal_identity, "default_workstation_id", lambda: actual["nombre"])
    return actual


def _login(conn):
    """El login real: la sesión nace con la identidad de la terminal."""
    sucursal = s.ancla(conn)
    cajero = s.usuario(conn, "cajero", sucursal)
    resultado = s.login(cajero, "cajero", sucursal)
    resultado.session = SimpleNamespace(
        workstation_id=terminal_identity.current_terminal_id(conn),
        session_id=resultado.session.session_id)
    return ApplicationContextBuilder(conn).build(resultado)


def _fila(conn, terminal_id):
    return dict(conn.execute("SELECT * FROM workstations WHERE id=?", (terminal_id,)).fetchone())


def test_the_session_uses_a_persistent_uuid_not_the_host_name(conn, host):
    ctx = _login(conn)
    assert is_uuidv7(ctx.workstation_id)
    assert ctx.workstation_id != host["nombre"]


def test_renaming_the_host_does_not_change_the_identity(conn, host):
    antes = _login(conn).workstation_id
    host["nombre"] = "OTRO-NOMBRE"
    despues = _login(conn).workstation_id
    assert despues == antes
    assert conn.execute("SELECT count(*) FROM workstations").fetchone()[0] == 1
    assert _fila(conn, antes)["device_identifier"] == "OTRO-NOMBRE"


def test_the_terminal_row_has_type_scope_status_and_versions(conn, host):
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY)")
    conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('392')")
    fila = _fila(conn, _login(conn).workstation_id)
    assert fila["workstation_type"] == "POS"
    assert fila["branch_id"] == s.ancla(conn)
    assert fila["status"] == "ACTIVE"
    assert fila["application_version"] == VERSION
    assert fila["schema_version"] == "392"
    assert fila["protocol_version"] == str(ENVELOPE_VERSION)


def test_legacy_session_adapter_stops_returning_none(conn, host):
    ctx = _login(conn)
    assert isinstance(ctx, ApplicationContext)
    assert LegacySessionAdapter(ctx).workstation_id == ctx.workstation_id


def test_a_re_anchored_station_keeps_its_id_and_moves_its_scope(conn, host):
    antes = _login(conn).workstation_id
    otra = s.sucursal(conn, "Otra")
    conn.execute("UPDATE configuraciones SET valor=? WHERE clave='sucursal_instalacion_id'",
                 (otra,))
    conn.commit()
    assert _login(conn).workstation_id == antes
    assert _fila(conn, antes)["branch_id"] == otra


def test_a_repair_session_has_an_identity_but_no_row_without_a_branch(conn, host):
    propia = s.sucursal(conn, "Propia")
    s.quitar_ancla(conn)
    dueno = s.usuario(conn, "system_owner", propia)
    resultado = s.login(dueno, "system_owner", propia)
    resultado.session = SimpleNamespace(
        workstation_id=terminal_identity.current_terminal_id(conn),
        session_id=resultado.session.session_id)
    ctx = ApplicationContextBuilder(conn).build(resultado)
    assert is_uuidv7(ctx.workstation_id)
    assert conn.execute("SELECT count(*) FROM workstations").fetchone()[0] == 0


def test_a_blocked_terminal_is_not_reactivated_by_logging_in(conn, host):
    """Validar el estado al entrar es SDLC-ARQ-TERM-003; aquí sólo no se pisa."""
    terminal = _login(conn).workstation_id
    conn.execute("UPDATE workstations SET status='BLOCKED' WHERE id=?", (terminal,))
    conn.commit()
    _login(conn)
    assert _fila(conn, terminal)["status"] == "BLOCKED"


def test_a_schema_without_the_tables_falls_back_quietly():
    c = sqlite3.connect(":memory:")
    assert terminal_identity.current_terminal_id(c) == ""
    c.close()


# ── migración 392 ────────────────────────────────────────────────────────────
def _sin_identidad(conn):
    conn.execute("DELETE FROM configuraciones WHERE clave=?", (TERMINAL_ID_KEY,))
    conn.commit()


def _estacion(conn, *, dispositivo="", status="ACTIVE"):
    estacion = new_uuid()
    conn.execute(
        "INSERT INTO workstations (id, branch_id, code, name, workstation_type,"
        " device_identifier, status, created_at, updated_at)"
        " VALUES (?,?,?,?,'POS',?,?,'t','t')",
        (estacion, s.ancla(conn), f"C-{estacion[-6:]}", "Caja", dispositivo, status))
    conn.commit()
    return estacion


def _identidad(conn):
    return conn.execute("SELECT valor FROM configuraciones WHERE clave=?",
                        (TERMINAL_ID_KEY,)).fetchone()[0]


def test_migration_is_registered_and_idempotent(conn):
    from migrations.engine import MIGRATIONS

    assert "392" in {m.version for m in MIGRATIONS}
    _sin_identidad(conn)
    _392.run(conn)
    primero = _identidad(conn)
    _392.run(conn)
    assert is_uuidv7(primero) and _identidad(conn) == primero


def test_migration_adds_the_version_columns_to_an_older_table():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE workstations (id TEXT PRIMARY KEY, status TEXT,"
              " device_identifier TEXT)")
    c.execute("CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT)")
    _392.run(c)
    _392.run(c)
    columnas = {f[1] for f in c.execute("PRAGMA table_info(workstations)")}
    assert {"schema_version", "protocol_version"} <= columnas
    c.close()


def test_migration_adopts_the_row_of_this_machine(conn, monkeypatch):
    monkeypatch.setattr(_392, "_hostname", lambda: "CAJA-01")
    _estacion(conn, dispositivo="OTRA-MAQUINA")
    mia = _estacion(conn, dispositivo="CAJA-01")
    _sin_identidad(conn)
    _392.run(conn)
    assert _identidad(conn) == mia


def test_migration_adopts_the_only_unbound_station(conn, monkeypatch):
    """La fila que creó la pantalla de cliente: conservarla conserva su pantalla."""
    monkeypatch.setattr(_392, "_hostname", lambda: "CAJA-01")
    unica = _estacion(conn)
    _sin_identidad(conn)
    _392.run(conn)
    assert _identidad(conn) == unica


def test_migration_never_adopts_a_station_of_another_machine(conn, monkeypatch):
    monkeypatch.setattr(_392, "_hostname", lambda: "CAJA-01")
    ajena = _estacion(conn, dispositivo="OTRA-MAQUINA")
    _sin_identidad(conn)
    _392.run(conn)
    assert _identidad(conn) != ajena


def test_migration_moves_the_update_settings_off_the_host_name(conn, monkeypatch):
    importlib.import_module("migrations.standalone.338_software_updates").run(conn)
    monkeypatch.setattr(_392, "_hostname", lambda: "CAJA-01")
    conn.execute("INSERT INTO software_station_settings (id, workstation_key, channel,"
                 " updated_at) VALUES (?,?,'pilot','t')", (new_uuid(), "CAJA-01"))
    conn.commit()
    _sin_identidad(conn)
    _392.run(conn)
    assert conn.execute("SELECT workstation_key, channel FROM software_station_settings"
                        ).fetchone()[0:2] == (_identidad(conn), "pilot")


# ── lo que cambia al dejar de ser None ───────────────────────────────────────
def _venta_suspendida(conn, sucursal, estacion):
    venta = new_uuid()
    conn.execute(
        "INSERT INTO sales (id, branch_id, cashier_user_id, operation_id, status,"
        " suspended_workstation_id, created_at)"
        " VALUES (?,?,?,?,'SUSPENDED',?,'2026-11-06T08:00:00+00:00')",
        (venta, sucursal, new_uuid(), new_uuid(), estacion))
    conn.commit()
    return venta


def test_sales_suspended_before_the_terminal_had_an_id_stay_visible(conn):
    from backend.infrastructure.db.schema.sales_schema import create_sales_schema

    create_sales_schema(conn)
    sucursal, terminal = s.ancla(conn), new_uuid()
    vieja = _venta_suspendida(conn, sucursal, None)
    propia = _venta_suspendida(conn, sucursal, terminal)
    _venta_suspendida(conn, sucursal, new_uuid())     # de otra terminal
    repo = SaleRepository(conn)
    assert repo.count_suspended(branch_id=sucursal, workstation_id=terminal) == 2
    assert {v.id for v in repo.list_suspended(branch_id=sucursal, workstation_id=terminal)} == {
        vieja, propia}


def test_a_terminal_without_an_assigned_scale_uses_the_branch_scale(conn, host):
    """Antes el id era None y resolvía la báscula de la sucursal; con un id real,
    sin asignación, el POS se quedaba sin báscula."""
    from backend.application.sales.authorization import (
        AllowAllSalesPermissionCheckerForTests,
        SalesAuthorizationPolicy,
    )
    from backend.application.sales.queries.scale_configuration_query import (
        ScaleConfigurationQuery,
    )
    from backend.application.use_cases.configuracion.device_management_use_cases import (
        RegisterDeviceProfileUseCase,
        RegisterDeviceUseCase,
    )

    ctx = _login(conn)
    perfil = RegisterDeviceProfileUseCase(conn).execute(
        name="Rhino", device_type="SCALE", connection_type="USB", model="BAR-8RS",
        protocol="RHINO_BAR_8RS", serial_port="COM7", baud_rate=9600)
    bascula = RegisterDeviceUseCase(conn).execute(
        branch_id=ctx.branch_id, profile_id=perfil.id, code="SCALE-A", name="Báscula")
    consulta = ScaleConfigurationQuery(
        conn, SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests()))
    dispositivo, _ = consulta.resolve(actor_user_id=new_uuid(), branch_id=ctx.branch_id,
                                      workstation_id=ctx.workstation_id)
    assert dispositivo.id == bascula.id
