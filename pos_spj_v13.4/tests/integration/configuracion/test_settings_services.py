"""Usuarios, roles y sucursal de instalación, contra el esquema REAL.

Cubre lo que reemplazó a `core/services/configuration_settings_service.py` y a
la parte de `repositories/config_repository.py` que lo alimentaba. Se monta la
base con la cadena de migraciones completa: lo que puede fallar aquí es la
correspondencia entre el SQL y las tablas, y un doble no probaría nada de eso.
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.application.configuracion.settings_services import (
    CompanyProfileService,
    RoleManagementService,
    UserManagementService,
)
from backend.infrastructure.db.repositories.settings.audit_log_repository import (
    SqliteAuditLogRepository,
)
from backend.infrastructure.db.repositories.settings.installation_branch_repository import (
    SqliteInstallationBranchRepository,
)
from backend.infrastructure.db.repositories.settings.user_directory_repository import (
    SqliteUserDirectoryRepository,
)
from backend.shared.ids import new_uuid


@pytest.fixture(scope="module")
def migrated_db(tmp_path_factory):
    from migrations.engine import up

    conn = sqlite3.connect(tmp_path_factory.mktemp("cfg") / "erp.db")
    conn.row_factory = sqlite3.Row
    up(conn)
    yield conn
    conn.close()


@pytest.fixture
def conn(migrated_db):
    yield migrated_db
    migrated_db.rollback()


@pytest.fixture
def branch_id(conn):
    return conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()["id"]


@pytest.fixture
def users(conn):
    return UserManagementService(SqliteUserDirectoryRepository(conn))


@pytest.fixture
def roles(conn):
    return RoleManagementService(SqliteUserDirectoryRepository(conn))


@pytest.fixture
def company(conn):
    return CompanyProfileService(SqliteInstallationBranchRepository(conn))


# ── usuarios ────────────────────────────────────────────────────────────────
def test_save_user_creates_with_a_uuidv7_identity(users, branch_id):
    from backend.shared.ids import is_uuidv7

    user_id = users.save_user(
        user_id=None, username="ana", name="Ana Ruiz", email="ana@spj.mx",
        role="cajero", branch_id=branch_id, active=True, employee_id=None,
        password_hash="hash",
    )
    assert is_uuidv7(user_id)


def test_save_user_updates_instead_of_duplicating(users, conn, branch_id):
    user_id = users.save_user(
        user_id=None, username="beto", name="Beto", email="b@spj.mx", role="cajero",
        branch_id=branch_id, active=True, employee_id=None, password_hash="h")
    users.save_user(
        user_id=user_id, username="beto", name="Beto Pérez", email="b@spj.mx",
        role="gerente", branch_id=branch_id, active=True, employee_id=None,
        password_hash=None)

    rows = conn.execute("SELECT nombre, rol FROM usuarios WHERE id=?", (user_id,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["nombre"] == "Beto Pérez" and rows[0]["rol"] == "gerente"


def test_saving_without_a_password_hash_keeps_the_existing_one(users, conn, branch_id):
    """`password_hash=None` significa "no tocar", no "borrar".

    Si la columna se incluyera siempre en el UPDATE, cada edición del
    formulario que no rellena la contraseña la dejaría vacía y el usuario no
    podría volver a entrar.
    """
    user_id = users.save_user(
        user_id=None, username="caro", name="Caro", email="c@spj.mx", role="cajero",
        branch_id=branch_id, active=True, employee_id=None, password_hash="ORIGINAL")
    users.save_user(
        user_id=user_id, username="caro", name="Caro Gil", email="c@spj.mx",
        role="cajero", branch_id=branch_id, active=True, employee_id=None,
        password_hash=None)

    row = conn.execute("SELECT password_hash FROM usuarios WHERE id=?", (user_id,)).fetchone()
    assert row["password_hash"] == "ORIGINAL"


def test_set_user_active_toggles_the_account(users, conn, branch_id):
    user_id = users.save_user(
        user_id=None, username="dani", name="Dani", email="d@spj.mx", role="cajero",
        branch_id=branch_id, active=True, employee_id=None, password_hash="h")
    users.set_user_active(user_id, False)
    assert conn.execute("SELECT activo FROM usuarios WHERE id=?", (user_id,)).fetchone()["activo"] == 0


def test_get_user_form_data_returns_the_editable_fields(users, branch_id):
    user_id = users.save_user(
        user_id=None, username="eva", name="Eva", email="e@spj.mx", role="cajero",
        branch_id=branch_id, active=True, employee_id=None, password_hash="h")
    usuario, nombre, email, rol, sucursal, activo, empleado = users.get_user_form_data(user_id)
    assert (usuario, nombre, email, rol, sucursal, activo) == (
        "eva", "Eva", "e@spj.mx", "cajero", branch_id, 1)
    assert empleado is None


def test_list_users_includes_the_lockout_columns(users, branch_id):
    """La pantalla las usa para explicar por qué una cuenta no entra."""
    users.save_user(
        user_id=None, username="fer", name="Fer", email="f@spj.mx", role="cajero",
        branch_id=branch_id, active=True, employee_id=None, password_hash="h")
    fila = next(row for row in users.list_users() if row[1] == "fer")
    assert len(fila) == 10
    assert fila[8] == 0          # intentos_fallidos
    assert fila[9] is None       # bloqueado_hasta


# ── identidad: fallar cerrado ───────────────────────────────────────────────
def test_a_branch_that_does_not_exist_is_rejected(users):
    """Un UUIDv7 con forma válida pero sin fila detrás dejaría al usuario
    asignado a una sucursal inexistente: entraría sin sucursal activa y no
    vería ningún módulo, sin ningún error que lo explicara."""
    with pytest.raises(ValueError, match="sucursal existente"):
        users.save_user(
            user_id=None, username="x", name="X", email="x@spj.mx", role="cajero",
            branch_id=new_uuid(), active=True, employee_id=None, password_hash="h")


@pytest.mark.parametrize("identidad", ["1", "none", "NO-ES-UUID", "0190-corto"])
def test_non_uuidv7_identities_are_rejected(users, branch_id, identidad):
    with pytest.raises(ValueError):
        users.save_user(
            user_id=identidad, username="y", name="Y", email="y@spj.mx", role="cajero",
            branch_id=branch_id, active=True, employee_id=None, password_hash="h")


# ── roles y selectores ──────────────────────────────────────────────────────
def test_seeded_system_roles_are_listed(roles):
    nombres = set(roles.role_names())
    assert {"admin", "gerente", "cajero", "almacen"} <= nombres


def test_list_roles_counts_only_active_users(roles, users, conn, branch_id):
    def contar(nombre: str) -> int:
        return next(row[3] for row in roles.list_roles() if row[1] == nombre)

    antes = contar("cajero")
    user_id = users.save_user(
        user_id=None, username="gus", name="Gus", email="g@spj.mx", role="cajero",
        branch_id=branch_id, active=True, employee_id=None, password_hash="h")
    assert contar("cajero") == antes + 1

    users.set_user_active(user_id, False)
    assert contar("cajero") == antes


def test_save_role_creates_and_updates(roles, conn):
    role_id = roles.save_role(role_id=None, name="auditor", description="Sólo lectura")
    roles.save_role(role_id=role_id, name="auditor", description="Revisión interna")
    rows = conn.execute("SELECT descripcion FROM roles WHERE id=?", (role_id,)).fetchall()
    assert len(rows) == 1 and rows[0]["descripcion"] == "Revisión interna"


def test_branch_selector_skips_corrupt_identities(roles, conn):
    """`'None'` como texto es lo que aparece cuando alguien guardó `str(None)`.
    Pasaría un filtro `IS NOT NULL` y llegaría al desplegable como si fuera una
    sucursal real."""
    conn.execute("INSERT INTO sucursales (id, nombre, activa) VALUES ('None','Corrupta',1)")
    assert "None" not in {bid for bid, _ in roles.active_branches_for_selector()}


# ── sucursal de la instalación ──────────────────────────────────────────────
def test_set_and_get_installation_branch(company, conn, branch_id):
    assert company.set_installation_branch(branch_id)[0] == branch_id
    assert company.get_installation_branch()[0] == branch_id


def test_an_inactive_branch_cannot_be_anchored(company, conn, branch_id):
    """Anclar a una sucursal dada de baja dejaría la instalación sin poder
    abrir sesión, y el error aparecería en el login, lejos de aquí."""
    conn.execute("UPDATE sucursales SET activa=0 WHERE id=?", (branch_id,))
    with pytest.raises(ValueError, match="activa"):
        company.set_installation_branch(branch_id)


def test_get_returns_none_when_the_anchored_branch_disappeared(company, conn, branch_id):
    """Sin el JOIN contra `sucursales` esto devolvería un id huérfano que el
    arranque trataría como una sucursal válida."""
    company.set_installation_branch(branch_id)
    conn.execute("DELETE FROM sucursales WHERE id=?", (branch_id,))
    assert company.get_installation_branch() is None


# ── auditoría ───────────────────────────────────────────────────────────────
def test_audit_log_returns_newest_first_and_honours_the_limit(conn):
    for n in range(3):
        conn.execute(
            "INSERT INTO audit_logs (id, accion, modulo, usuario, detalles, fecha)"
            " VALUES (?,?,?,?,?,?)",
            (new_uuid(), f"accion{n}", "CONFIGURACION", "admin", f"d{n}",
             f"2026-01-0{n + 1} 10:00:00"),
        )
    filas = SqliteAuditLogRepository(conn).recent(limit=2)
    assert len(filas) == 2
    assert filas[0][3] == "accion2"


# ── el camino REAL de escritura: a través de los casos de uso ───────────────
# Los servicios no se invocan nunca directamente en producción; los llaman
# `SaveUserUseCase`, `SetUserActiveUseCase` y `SaveRoleUseCase`, que les pasan
# `operation_id` y `actor`. Probar sólo los servicios habría dejado pasar un
# `TypeError` por firma incompatible — que es justo lo que ocurrió al escribir
# esto la primera vez.
@pytest.fixture
def audit(conn):
    return SqliteAuditLogRepository(conn)


def test_save_user_use_case_runs_end_to_end_and_audits(conn, audit, branch_id):
    from backend.application.commands.settings_commands import SaveUserCommand
    from backend.application.use_cases.save_user_use_case import SaveUserUseCase

    service = UserManagementService(SqliteUserDirectoryRepository(conn), audit)
    command = SaveUserCommand(
        operation_id=new_uuid(), branch_id=branch_id, user_name="admin",
        user_id="", username="hugo", full_name="Hugo", email="h@spj.mx",
        role="cajero", active=True, employee_id=None, password_hash="h",
    )
    result = SaveUserUseCase(service).execute(command)

    assert result.success
    anotacion = audit.recent(limit=1)[0]
    assert anotacion[1] == "admin"            # usuario
    assert anotacion[3] == "usuario.crear"    # accion
    assert command.operation_id in anotacion[4]


def test_set_user_active_use_case_runs_end_to_end_and_audits(conn, audit, branch_id):
    from backend.application.commands.settings_commands import SetUserActiveCommand
    from backend.application.use_cases.set_user_active_use_case import SetUserActiveUseCase

    service = UserManagementService(SqliteUserDirectoryRepository(conn), audit)
    user_id = service.save_user(
        user_id=None, username="ivan", name="Iván", email="i@spj.mx", role="cajero",
        branch_id=branch_id, active=True, employee_id=None, password_hash="h")

    result = SetUserActiveUseCase(service).execute(SetUserActiveCommand(
        operation_id=new_uuid(), branch_id=branch_id, user_name="admin",
        user_id=user_id, active=False))

    assert result.success
    assert conn.execute("SELECT activo FROM usuarios WHERE id=?", (user_id,)).fetchone()["activo"] == 0
    assert audit.recent(limit=1)[0][3] == "usuario.desactivar"


def test_save_role_use_case_runs_end_to_end_and_audits(conn, audit, branch_id):
    from backend.application.commands.settings_commands import SaveRoleCommand
    from backend.application.use_cases.save_role_use_case import SaveRoleUseCase

    service = RoleManagementService(SqliteUserDirectoryRepository(conn), audit)
    result = SaveRoleUseCase(service).execute(SaveRoleCommand(
        operation_id=new_uuid(), branch_id=branch_id, user_name="admin",
        role_id="", name="supervisor", description="Turno"))

    assert result.success
    assert audit.recent(limit=1)[0][3] == "rol.crear"


def test_an_operation_without_an_actor_is_still_attributable(conn, audit, branch_id):
    """`audit_logs.usuario` es NOT NULL: una anotación sin autor sería peor que
    inútil, así que una operación automática queda como 'Sistema'."""
    service = UserManagementService(SqliteUserDirectoryRepository(conn), audit)
    service.save_user(
        user_id=None, username="auto", name="Auto", email="a@spj.mx", role="cajero",
        branch_id=branch_id, active=True, employee_id=None, password_hash="h",
        operation_id=new_uuid(), actor="")
    assert audit.recent(limit=1)[0][1] == "Sistema"
