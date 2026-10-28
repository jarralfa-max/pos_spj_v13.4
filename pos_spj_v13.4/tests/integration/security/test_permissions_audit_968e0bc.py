"""Auditoría global de permisos 968e0bc (PER-01 … PER-08) — pruebas de contrato.

Cada bloque fija el comportamiento que la auditoría pidió y que se midió roto:
ver docs/refactor/PERM-AUD_auditoria_968e0bc.md.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

from backend.application.commands.settings_commands import (
    SaveRoleCommand,
    SaveRolePermissionsCommand,
    SaveUserCommand,
    SaveUserPermissionsCommand,
    SetUserActiveCommand,
)
from backend.application.configuracion.authorization import (
    ConfiguracionAuthorizationPolicy,
    SessionPermissionChecker,
)
from backend.application.configuracion.settings_services import (
    RoleManagementService,
    UserManagementService,
)
from backend.application.security.authorizer_permission_checker import (
    AuthorizerPermissionChecker,
)
from backend.application.security.permission_catalog import (
    CANONICAL_MODULE_PERMISSIONS,
    FLAT_CODE_CONTEXTS,
)
from backend.application.security.permission_query_service import (
    PermissionQueryService,
    explain_permissions,
)
from backend.application.security.role_permission_matrix import catalog_codes, role_mode
from backend.application.security.session_grant_refresh import SessionGrantRefresher
from backend.application.security.user_permission_matrix import UserPermissionMatrixQuery
from backend.application.use_cases.save_role_permissions_use_case import (
    SaveRolePermissionsUseCase,
)
from backend.application.use_cases.save_role_use_case import SaveRoleUseCase
from backend.application.use_cases.save_user_permissions_use_case import (
    SaveUserPermissionsUseCase,
)
from backend.domain.settings.exceptions import (
    ConfigurationInvalidValueError,
    ConfigurationPermissionDeniedError,
)
from backend.infrastructure.db.repositories.security.grant_version_repository import (
    SqliteGrantVersionRepository,
)
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)
from backend.infrastructure.db.repositories.settings.user_directory_repository import (
    SqliteUserDirectoryRepository,
)
from backend.security.permissions.codes import is_granted, normalize_permission
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db

APP_ROOT = Path(__file__).resolve().parents[3]
MIG347 = importlib.import_module("migrations.standalone.347_permissions_audit_968e0bc")

ADMIN = "01900000-0000-7000-8000-0000000000a1"
GERENTE = "01900000-0000-7000-8000-0000000000a2"
CAJERO = "01900000-0000-7000-8000-0000000000a3"
OWNER = "01900000-0000-7000-8000-0000000000aa"


# ── fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture
def conn():
    c = make_db()
    importlib.import_module("migrations.standalone.047_v13_schema").up(c)
    MIG347.run(c)
    yield c
    c.close()


def _branch(conn, nombre="Centro"):
    bid = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre, activa) VALUES (?,?,1)", (bid, nombre))
    return bid


def _user(conn, rol, *, branch=None):
    uid = new_uuid()
    branch = branch or conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()[0]
    conn.execute("INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id, activo)"
                 " VALUES (?,?,?,?,?,?,1)", (uid, rol, f"{rol}-{uid[-6:]}", "x", rol, branch))
    return uid


def _grant_role(conn, role_id, code):
    modulo, accion = code.split(".", 1)
    conn.execute("INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                 " VALUES (?,?,?,?,1)", (new_uuid(), role_id, modulo, accion))


def _codes(conn, user_id, branch_id=None):
    return PermissionQueryService(SqlitePermissionRepository(conn)).permission_codes_for_user(
        user_id, branch_id)


class _Session:
    def __init__(self, user_id, granted=(), *, active=True, branch="b1"):
        self.user_id = user_id
        self.active_branch_id = branch
        self.is_active = active
        self._granted = frozenset(normalize_permission(c) for c in granted)

    def tiene_permiso(self, code):
        return is_granted(self._granted, code)


class _Grants:
    def __init__(self, allowed):
        self._allowed = set(allowed)

    def has_permission(self, user_id, code):
        return user_id in self._allowed


def _production_python():
    for root in ("backend", "frontend"):
        for path in (APP_ROOT / root).rglob("*.py"):
            if "__pycache__" not in path.parts:
                yield path


# ── PER-01 — RR. HH. ya no falla abierto ────────────────────────────────────
def test_hr_policy_without_checker_denies_paying_payroll():
    from backend.domain.hr.exceptions import PermissionDeniedError
    from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy, HRPermission

    with pytest.raises(PermissionDeniedError):
        AuthorizationPolicy().require("sin_sesion", HRPermission.PAYROLL_PAY)


def test_hr_session_checker_is_bound_to_the_session_user():
    from backend.application.hr.session_authorization import HRSessionPermissionChecker

    checker = HRSessionPermissionChecker(_Session("a", {"RRHH.nomina.pagar"}))
    assert checker.has_permission("a", "RRHH.nomina.pagar")
    assert not checker.has_permission("b", "RRHH.nomina.pagar")


def test_hr_routes_wire_the_session_checker_not_an_empty_policy():
    src = (APP_ROOT / "frontend/desktop/modules/hr/hr_routes.py").read_text(encoding="utf-8")
    assert "AuthorizationPolicy(HRSessionPermissionChecker(session_context))" in src


# ── PER-02 — sin política, falla cerrada ────────────────────────────────────
def _permissive_call(node) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "permissive_for_tests")


def test_no_production_constructor_defaults_to_a_permissive_policy():
    """`x or Policy.permissive_for_tests()` y `... else Policy.permissive_for_tests()`
    eran el default de ~130 constructores. Ninguno debe volver."""
    culpables = []
    for path in _production_python():
        for nodo in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.BoolOp) and isinstance(nodo.op, ast.Or)                     and any(_permissive_call(v) for v in nodo.values):
                culpables.append(f"{path.relative_to(APP_ROOT)}:{nodo.lineno}")
            if isinstance(nodo, ast.IfExp) and _permissive_call(nodo.orelse):
                culpables.append(f"{path.relative_to(APP_ROOT)}:{nodo.lineno}")
    assert culpables == []


@pytest.mark.unwired_fails_closed
def test_an_unwired_inventory_use_case_fails_closed():
    from backend.application.inventory.permissions import InventoryPermissions
    from backend.application.inventory.use_cases.lot_use_cases import RegisterInventoryLotUseCase
    from backend.application.inventory.use_cases.post_inventory_movement import (
        PostInventoryMovementUseCase,
    )
    from backend.domain.inventory.exceptions import InventoryConfigurationError

    for uc in (PostInventoryMovementUseCase(), RegisterInventoryLotUseCase()):
        with pytest.raises(InventoryConfigurationError):
            uc._auth.require("u1", InventoryPermissions.MOVEMENT_CREATE)


@pytest.mark.unwired_fails_closed
def test_unwired_meat_products_pricing_suppliers_and_configuracion_fail_closed():
    from backend.application.meat_processing.permissions import MeatProcessingPermissions
    from backend.application.meat_processing.use_cases.execution_use_cases import (
        StartProcessExecutionUseCase,
    )
    from backend.domain.meat_processing.exceptions import MeatProcessingConfigurationError
    from backend.application.pricing.authorization.policy import PricingAuthorizationPolicy
    from backend.application.pricing.permissions import PricingPermissions
    from backend.application.suppliers.authorization import SupplierAuthorizationPolicy
    from backend.application.suppliers.permissions import SupplierPermissions
    from backend.domain.pricing.exceptions import PricingPermissionDeniedError
    from backend.domain.suppliers.exceptions import PermissionDeniedError
    from frontend.desktop.modules.configuracion.configuracion_presenter import (
        ConfiguracionPresenter,
    )

    with pytest.raises(MeatProcessingConfigurationError):
        StartProcessExecutionUseCase()._auth.require("u1", MeatProcessingPermissions.VIEW)
    with pytest.raises(PricingPermissionDeniedError):
        PricingAuthorizationPolicy().require("u1", PricingPermissions.PRICE_EDIT)
    with pytest.raises(PermissionDeniedError):
        SupplierAuthorizationPolicy().require("u1", SupplierPermissions.APPROVE)
    presenter = ConfiguracionPresenter(None, session_context=_Session("u1"))
    assert presenter._authorize("CONFIGURACION.usuario.permisos") is not None


def test_integration_grants_are_nominated_and_bound_to_the_operator():
    from backend.application.inventory.integration_grants import inventory_integration_policy
    from backend.application.inventory.permissions import InventoryPermissions as P

    compras = inventory_integration_policy("procurement", "op-1")
    assert compras.has_permission("op-1", P.MOVEMENT_CREATE)
    assert compras.has_permission("op-1", P.LOT_CREATE)
    assert not compras.has_permission("otro", P.MOVEMENT_CREATE)   # sólo el operador
    assert not compras.has_permission("op-1", P.ADJUSTMENT_APPROVE)  # sólo lo concedido
    ventas = inventory_integration_policy("sales", "cajero-1")
    assert ventas.has_permission("cajero-1", P.MOVEMENT_CREATE)
    assert not ventas.has_permission("cajero-1", P.LOT_CREATE)
    sin_operador = inventory_integration_policy("sales", "")
    assert not sin_operador.has_permission("", P.MOVEMENT_CREATE)
    with pytest.raises(PermissionError):
        inventory_integration_policy("modulo_inventado", "op-1")


def test_live_purchase_stock_entry_posts_through_the_procurement_grant():
    """La entrada de stock de cada compra (vivo en `wire_procurement`) ya no
    depende del default permisivo: usa la concesión nominada de Compras."""
    from backend.application.event_handlers.inventory.purchase_receipt_handler import (
        PurchaseReceiptHandler,
    )

    handler = PurchaseReceiptHandler(None)
    assert handler._uc is None and handler._lot_uc is None
    src = (APP_ROOT / "backend/application/event_handlers/inventory/"
           "purchase_receipt_handler.py").read_text(encoding="utf-8")
    assert 'integration_use_case(PostInventoryMovementUseCase, "procurement", user)' in src


def test_sales_inventory_client_never_posts_with_an_unwired_use_case():
    src = (APP_ROOT / "backend/infrastructure/integrations/sales_inventory_client.py"
           ).read_text(encoding="utf-8")
    assert "PostInventoryMovementUseCase()" not in src
    assert src.count("_sale_movement_use_case(PostInventoryMovementUseCase") == 3


# ── PER-03 — el verificador de sesión ata el actor ──────────────────────────
def test_configuracion_checker_does_not_answer_for_another_user():
    checker = SessionPermissionChecker(_Session("actor-A", {"CONFIGURACION.rol.permisos"}))
    assert checker.has_permission("actor-A", "CONFIGURACION.rol.permisos")
    assert not checker.has_permission("actor-B", "CONFIGURACION.rol.permisos")
    assert not SessionPermissionChecker(
        _Session("actor-A", {"*"}, active=False)).has_permission("actor-A", "X.y")


def test_products_checker_does_not_answer_for_another_user():
    from backend.application.products.authorization.permission_bridge import (
        SessionPermissionChecker as ProductsChecker,
    )

    from backend.application.products.permissions import ProductPermissions

    checker = ProductsChecker(_Session("a", {"PRODUCTOS.ver"}))
    assert checker.has_permission("a", ProductPermissions.VIEW)
    assert not checker.has_permission("b", ProductPermissions.VIEW)


def test_a_substituted_actor_cannot_edit_a_third_party_role(conn):
    sesion_de_a = _Session("actor-A", {"CONFIGURACION.rol.permisos", "POS.ver"})
    auth = ConfiguracionAuthorizationPolicy(SessionPermissionChecker(sesion_de_a))
    with pytest.raises(ConfigurationPermissionDeniedError):
        SaveRolePermissionsUseCase(conn, auth).execute(SaveRolePermissionsCommand(
            operation_id=new_uuid(), branch_id="b", user_id="actor-B", role_id=CAJERO,
            permissions=({"module": "POS", "action": "ver", "allowed": True},)))


# ── PER-04 — todo lo exigible es otorgable ──────────────────────────────────
def test_no_flat_code_contexts_remain():
    assert FLAT_CODE_CONTEXTS == ()


def test_every_code_a_context_requires_is_grantable_from_configuracion():
    from backend.application.security.permission_catalog import _CONTEXT_PERMISSION_MODULES
    from backend.domain.hr.policies.authorization_policy import HR_PERMISSIONS

    otorgables = {normalize_permission(c) for c in catalog_codes()}
    faltan = []
    for dotted in _CONTEXT_PERMISSION_MODULES:
        modulo = importlib.import_module(dotted)
        for nombre in dir(modulo):
            if nombre.startswith("ALL_") and nombre.endswith("_PERMISSIONS"):
                faltan += [c for c in getattr(modulo, nombre)
                           if normalize_permission(c) not in otorgables]
    faltan += [c for c in HR_PERMISSIONS if normalize_permission(c) not in otorgables]
    assert faltan == []


def test_flat_code_translation_matches_the_new_constants():
    from backend.application.losses.permissions import ALL_LOSS_PERMISSIONS
    from backend.application.suppliers.permissions import ALL_SUPPLIER_PERMISSIONS
    from backend.application.transfers.permissions import ALL_TRANSFER_PERMISSIONS

    destinos = {f"{m}.{a}" for m, a in MIG347.FLAT_CODE_TRANSLATION.values()}
    assert destinos == set(ALL_LOSS_PERMISSIONS | ALL_SUPPLIER_PERMISSIONS
                           | ALL_TRANSFER_PERMISSIONS)
    assert len(destinos) == len(MIG347.FLAT_CODE_TRANSLATION)  # 1:1, nada se amplía


def test_transfers_lifecycle_is_no_longer_denied_to_everyone():
    from backend.application.transfers.permissions import TransferPermissions as P
    from backend.application.transfers.session_authorization import (
        TransferSessionPermissionChecker,
    )

    admin = TransferSessionPermissionChecker(_Session("adm", {"*"}))
    for code in (P.APPROVE, P.PICK, P.DISPATCH, P.RECEIVE):
        assert admin.has_permission("adm", code), code
    gerente = TransferSessionPermissionChecker(_Session("g", {"TRANSFERENCIAS.ver",
                                                              "TRANSFERENCIAS.crear"}))
    assert gerente.has_permission("g", P.REQUEST_CREATE)
    assert gerente.has_permission("g", P.RECEIVE_VIEW)
    assert not gerente.has_permission("g", P.APPROVE)
    concedido = TransferSessionPermissionChecker(_Session("g", {P.APPROVE}))
    assert concedido.has_permission("g", P.APPROVE)


def test_losses_view_grants_only_read_pages():
    from backend.application.losses.permissions import LossPermissions as P
    from backend.application.losses.session_authorization import LossSessionPermissionChecker

    lectura = LossSessionPermissionChecker(_Session("g", {"MERMA.ver"}))
    assert lectura.has_permission("g", P.REGISTRATION_VIEW)
    for sensible in (P.APPROVE, P.REPORT, P.VIEW_COST, P.VIEW_AUDIT, P.VIEW_ALL_BRANCHES):
        assert not lectura.has_permission("g", sensible), sensible
    assert LossSessionPermissionChecker(_Session("g", {P.APPROVE})).has_permission("g", P.APPROVE)


def test_suppliers_keep_the_coarse_fallback_and_hide_bank_data():
    from backend.application.suppliers.permissions import SupplierPermissions as P
    from backend.application.suppliers.session_authorization import (
        SupplierSessionPermissionChecker,
    )

    grueso = SupplierSessionPermissionChecker(_Session("g", {"PROVEEDORES.editar"}))
    assert grueso.has_permission("g", P.APPROVE)
    assert not grueso.has_permission("g", P.VIEW_BANK)
    fino = SupplierSessionPermissionChecker(_Session("g", {P.VIEW_BANK}))
    assert fino.has_permission("g", P.VIEW_BANK)


def test_migration_translates_stored_flat_codes(conn):
    conn.execute("INSERT INTO usuario_permisos (id, usuario_id, modulo, accion, permitido)"
                 " VALUES (?, 'u1', '', 'LOSSES_APPROVE', 1)", (new_uuid(),))
    conn.execute("INSERT INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                 " VALUES (?, ?, '', 'TRANSFERS_RECEIVE', 1)", (new_uuid(), GERENTE))
    MIG347.run(conn)
    assert conn.execute("SELECT modulo, accion FROM usuario_permisos WHERE usuario_id='u1'"
                        ).fetchall()[0][:] == ("MERMA", "aprobar")
    assert conn.execute("SELECT COUNT(*) FROM rol_permisos WHERE rol_id=? AND modulo="
                        "'TRANSFERENCIAS' AND accion='recibir'", (GERENTE,)).fetchone()[0] == 1


# ── PER-05 — el RBAC heredado no vuelve ─────────────────────────────────────
def test_the_legacy_rbac_module_is_gone_and_nobody_reads_its_tables():
    assert not (APP_ROOT / "security" / "rbac.py").exists()
    lectura = re.compile(r"\b(FROM|JOIN|INTO|UPDATE)\s+(usuarios_roles|roles_permisos)\b",
                         re.IGNORECASE)
    culpables = []
    for path in _production_python():
        texto = path.read_text(encoding="utf-8")
        if "security.rbac" in texto or lectura.search(texto):
            culpables.append(str(path.relative_to(APP_ROOT)))
    assert culpables == []


def test_delivery_alerts_reach_users_by_their_real_role(conn):
    from backend.infrastructure.integrations.orders_delivery_internal_notifier import (
        OrdersDeliveryInternalNotifier,
    )

    centro, norte = _branch(conn), _branch(conn, "Norte")
    gerente = _user(conn, "gerente", branch=centro)
    asignado = _user(conn, "gerente", branch=norte)
    conn.execute("INSERT INTO usuarios_sucursales (usuario_id, sucursal_id) VALUES (?,?)",
                 (asignado, centro))
    _user(conn, "cajero", branch=centro)
    escritas = OrdersDeliveryInternalNotifier(conn).notify_roles(
        roles=("gerente",), branch_id=centro, tipo="x", titulo="x", cuerpo="x")
    assert escritas == 2
    destinatarios = {r[0] for r in conn.execute("SELECT empleado_id FROM notification_inbox")}
    assert destinatarios == {gerente, asignado}


# ── PER-06 — unicidad y precedencia ─────────────────────────────────────────
def test_duplicate_overrides_are_rejected_by_the_database(conn):
    conn.execute("INSERT INTO usuario_permisos (id, usuario_id, modulo, accion, permitido)"
                 " VALUES (?, 'u1', 'POS', 'ver', 1)", (new_uuid(),))
    with pytest.raises(Exception):
        conn.execute("INSERT INTO usuario_permisos (id, usuario_id, modulo, accion, permitido)"
                     " VALUES (?, 'u1', 'POS', 'ver', 0)", (new_uuid(),))


def test_migration_dedupes_keeping_the_denial():
    c = make_db()
    for permitido in (1, 0, 1):
        c.execute("INSERT INTO usuario_permisos (id, usuario_id, modulo, accion, permitido)"
                  " VALUES (?, 'u1', 'pos', 'VER', ?)", (new_uuid(), permitido))
    MIG347.run(c)
    filas = c.execute("SELECT modulo, accion, permitido FROM usuario_permisos").fetchall()
    assert [tuple(f) for f in filas] == [("POS", "ver", 0)]
    MIG347.run(c)  # idempotente
    c.close()


def test_branch_grant_restores_a_user_denial_and_says_so(conn):
    _grant_role(conn, CAJERO, "POS.ver")
    centro = _branch(conn)
    cajero = _user(conn, "cajero")
    conn.execute("INSERT INTO usuario_permisos (id, usuario_id, modulo, accion, permitido)"
                 " VALUES (?,?,?,?,0)", (new_uuid(), cajero, "POS", "ver"))
    conn.execute("INSERT INTO usuario_sucursal_permisos"
                 " (id, usuario_id, sucursal_id, modulo, accion, permitido) VALUES (?,?,?,?,?,1)",
                 (new_uuid(), cajero, centro, "POS", "ver"))
    assert "POS.VER" not in _codes(conn, cajero)
    assert "POS.VER" in _codes(conn, cajero, centro)
    servicio = PermissionQueryService(SqlitePermissionRepository(conn))
    info = explain_permissions(servicio, cajero, ["POS.ver"], centro)["POS.ver"]
    assert info.effective and info.origin == "SUCURSAL" and info.restores_denial


# ── PER-07 — una sola regla, roles reservados, cuentas raíz ─────────────────
def test_one_grant_rule_for_session_authorizer_and_scope():
    from backend.application.inventory.execution_context import InventoryExecutionContext
    from backend.application.inventory.permissions import InventoryPermissions as P

    assert is_granted(frozenset({"INVENTARIO.*"}), "INVENTARIO.lote.crear")
    assert is_granted(frozenset({"*"}), "CUALQUIER.cosa")
    concedido = InventoryExecutionContext(
        actor_user_id="u", active_branch_id="b",
        permissions=frozenset({normalize_permission(P.VIEW_ALL_BRANCHES)}))
    assert concedido.has_global_scope  # antes: False por mayúsculas
    assert InventoryExecutionContext(actor_user_id="u", active_branch_id="b",
                                     permissions=frozenset({"*"})).has_global_scope


def test_the_owner_is_full_access_everywhere(conn):
    dueno = _user(conn, "system_owner")
    assert _codes(conn, dueno) == frozenset({"*"})
    assert role_mode("system_owner") == "FULL_ACCESS"
    assert AuthorizerPermissionChecker(conn).has_permission(dueno, "MERMA.aprobar")


def test_reserved_role_names_cannot_be_taken_or_left(conn):
    roles = RoleManagementService(SqliteUserDirectoryRepository(conn))
    with pytest.raises(ValueError):
        roles.save_role(role_id=None, name="Admin", description="")
    with pytest.raises(ValueError):
        roles.save_role(role_id=CAJERO, name="administrador", description="")
    with pytest.raises(ValueError):
        roles.save_role(role_id=ADMIN, name="jefe", description="")


def test_renaming_a_role_keeps_its_users(conn):
    cajero = _user(conn, "cajero")
    _grant_role(conn, CAJERO, "POS.ver")
    RoleManagementService(SqliteUserDirectoryRepository(conn)).save_role(
        role_id=CAJERO, name="cajera", description="")
    assert conn.execute("SELECT rol FROM usuarios WHERE id=?", (cajero,)).fetchone()[0] == "cajera"
    assert "POS.VER" in _codes(conn, cajero)


def test_root_accounts_and_full_access_assignment_are_guarded(conn):
    branch = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()[0]
    usuarios = UserManagementService(SqliteUserDirectoryRepository(conn))
    dueno, gerente, cajero = (_user(conn, "system_owner"), _user(conn, "gerente"),
                              _user(conn, "cajero"))
    datos = dict(username="x", name="x", email="", branch_id=branch, active=True,
                 employee_id=None, password_hash=None)
    with pytest.raises(ValueError):   # un gerente no fabrica administradores
        usuarios.save_user(user_id=cajero, role="admin", actor=gerente, **datos)
    with pytest.raises(ValueError):   # sólo el dueño asigna el rol de dueño
        usuarios.save_user(user_id=cajero, role="system_owner", actor=_user(conn, "admin"),
                           **datos)
    with pytest.raises(ValueError):   # la cuenta del dueño no cambia de rol
        usuarios.save_user(user_id=dueno, role="cajero", actor=dueno, **datos)
    with pytest.raises(ValueError):   # ni se desactiva
        usuarios.set_user_active(dueno, False, actor=gerente)
    usuarios.save_user(user_id=cajero, role="admin", actor=dueno, **datos)
    assert conn.execute("SELECT rol FROM usuarios WHERE id=?", (cajero,)).fetchone()[0] == "admin"


@pytest.mark.unwired_fails_closed
def test_user_and_role_use_cases_revalidate_in_the_backend(conn):
    servicio = RoleManagementService(SqliteUserDirectoryRepository(conn))
    with pytest.raises(Exception):
        SaveRoleUseCase(servicio).execute(SaveRoleCommand(
            operation_id=new_uuid(), branch_id="b", user_name="alguien", role_id="",
            name="supervisor", description=""))
    sin_permiso = ConfiguracionAuthorizationPolicy(_Grants(()))
    with pytest.raises(ConfigurationPermissionDeniedError):
        SaveRoleUseCase(servicio, sin_permiso).execute(SaveRoleCommand(
            operation_id=new_uuid(), branch_id="b", user_name="alguien", role_id="",
            name="supervisor", description=""))


# ── PER-08 — permiso efectivo, ámbito de sucursal y sesiones abiertas ───────
def test_explanation_matches_what_the_session_loads(conn):
    _grant_role(conn, GERENTE, "POS.ver")
    _grant_role(conn, GERENTE, "CAJA.ver")
    centro = _branch(conn)
    gerente = _user(conn, "gerente")
    conn.execute("INSERT INTO usuario_permisos (id, usuario_id, modulo, accion, permitido)"
                 " VALUES (?,?,?,?,0)", (new_uuid(), gerente, "CAJA", "ver"))
    conn.execute("INSERT INTO usuario_permisos (id, usuario_id, modulo, accion, permitido)"
                 " VALUES (?,?,?,?,1)", (new_uuid(), gerente, "MERMA", "aprobar"))
    conn.execute("INSERT INTO usuario_sucursal_permisos"
                 " (id, usuario_id, sucursal_id, modulo, accion, permitido) VALUES (?,?,?,?,?,0)",
                 (new_uuid(), gerente, centro, "POS", "ver"))
    servicio = PermissionQueryService(SqlitePermissionRepository(conn))
    for sucursal in (None, centro):
        sesion = _codes(conn, gerente, sucursal)
        for code, info in explain_permissions(servicio, gerente, sorted(catalog_codes()),
                                              sucursal).items():
            assert info.effective == is_granted(sesion, code), (sucursal, code)


def test_branch_exceptions_are_editable_and_audited(conn):
    centro = _branch(conn)
    dueno, cajero = _user(conn, "system_owner"), _user(conn, "cajero")
    auth = ConfiguracionAuthorizationPolicy(_Grants({dueno}))
    version = SqliteGrantVersionRepository(conn).current()
    SaveUserPermissionsUseCase(conn, auth).execute(SaveUserPermissionsCommand(
        operation_id=new_uuid(), branch_id="b", user_id=dueno, target_user_id=cajero,
        scope_branch_id=centro,
        permissions=({"module": "MERMA", "action": "reportar", "state": "GRANT"},)))
    assert "MERMA.REPORTAR" in _codes(conn, cajero, centro)
    assert "MERMA.REPORTAR" not in _codes(conn, cajero)
    assert SqliteGrantVersionRepository(conn).current() == version + 1
    matriz = UserPermissionMatrixQuery(conn).matrix(cajero, centro)
    assert matriz.state("MERMA.reportar") == "GRANT"
    assert matriz.effective_label("MERMA.reportar").startswith("Sí — excepción en la sucursal")
    with pytest.raises(ConfigurationInvalidValueError):
        SaveUserPermissionsUseCase(conn, auth).execute(SaveUserPermissionsCommand(
            operation_id=new_uuid(), branch_id="b", user_id=dueno, target_user_id=cajero,
            scope_branch_id=new_uuid(),
            permissions=({"module": "MERMA", "action": "reportar", "state": "GRANT"},)))


def _adapter(conn, user_id, roles, refresher):
    from backend.bootstrap.application_context import ApplicationContext, FeatureContext
    from backend.bootstrap.legacy_session_adapter import LegacySessionAdapter

    contexto = ApplicationContext(
        installation_id="i", company_id="c", branch_id="b1", branch_name="Matriz",
        workstation_id="ws", workstation_type="pos", user_id=user_id, user_name="u",
        roles=roles, permissions=_codes(conn, user_id, "b1"),
        feature_context=FeatureContext(), session_id="s")
    return LegacySessionAdapter(contexto, grant_refresher=refresher)


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_an_open_session_loses_a_revoked_permission(conn):
    _grant_role(conn, CAJERO, "POS.ver")
    # La sesión opera «b1»: el cajero tiene que ser de esa sucursal. Desde la
    # Fase 2 de la auditoría enterprise un rol sólo vale donde su ámbito llega.
    owner, cajero = _user(conn, "system_owner"), _user(conn, "cajero", branch="b1")
    reloj = _Clock()
    sesion = _adapter(conn, cajero, ("cajero",), SessionGrantRefresher(conn, clock=reloj))
    assert sesion.tiene_permiso("POS.ver")
    SaveUserPermissionsUseCase(conn, ConfiguracionAuthorizationPolicy(_Grants({owner}))).execute(
        SaveUserPermissionsCommand(
            operation_id=new_uuid(), branch_id="b", user_id=owner, target_user_id=cajero,
            permissions=({"module": "POS", "action": "ver", "state": "DENY"},)))
    assert sesion.tiene_permiso("POS.ver")   # aún dentro del intervalo
    reloj.t += 10
    assert not sesion.tiene_permiso("POS.ver")


def test_deactivating_an_account_revokes_its_open_session_even_for_admins(conn):
    admin = _user(conn, "admin")
    reloj = _Clock()
    sesion = _adapter(conn, admin, ("admin",), SessionGrantRefresher(conn, clock=reloj))
    assert sesion.tiene_permiso("CUALQUIER.cosa") and sesion.is_active
    UserManagementService(SqliteUserDirectoryRepository(conn),
                          grant_versions=SqliteGrantVersionRepository(conn)).set_user_active(
        admin, False, actor="otro")
    reloj.t += 10
    assert not sesion.tiene_permiso("CUALQUIER.cosa")
    assert not sesion.is_active


def test_the_live_app_wires_the_refresher():
    src = (APP_ROOT / "frontend/desktop/app.py").read_text(encoding="utf-8")
    assert "grant_refresher=SessionGrantRefresher(connection)" in src


def test_migration_347_is_registered():
    src = (APP_ROOT / "migrations/engine.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    assert "migrations.standalone.347_permissions_audit_968e0bc" in src and tree


# ── Pendientes cerrados después (2026-10-23) ────────────────────────────────
def test_migration_348_retires_the_empty_legacy_rbac_tables():
    mig348 = importlib.import_module("migrations.standalone.348_retire_legacy_rbac_tables")
    c = make_db()  # m000 ya no las crea
    existentes = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not existentes & set(mig348.LEGACY_RBAC_TABLES)
    c.execute("CREATE TABLE usuarios_roles (usuario_id TEXT, rol_id TEXT, sucursal_id TEXT)")
    c.execute("CREATE TABLE permisos (id TEXT PRIMARY KEY, codigo TEXT, modulo TEXT)")
    mig348.run(c)
    assert not {r[0] for r in c.execute("SELECT name FROM sqlite_master")} & {
        "usuarios_roles", "permisos"}
    # Con filas no se borra nada (otra instalación): se revisa a mano.
    c.execute("CREATE TABLE usuarios_roles (usuario_id TEXT, rol_id TEXT, sucursal_id TEXT)")
    c.execute("INSERT INTO usuarios_roles VALUES ('u','r','s')")
    mig348.run(c)
    assert c.execute("SELECT COUNT(*) FROM usuarios_roles").fetchone()[0] == 1
    c.close()


def test_the_uuid_cutover_skips_tables_that_no_longer_exist():
    import sqlite3

    from backend.infrastructure.db.uuid_cutover import TableSpec, UuidCutover

    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE roles (id TEXT PRIMARY KEY)")
    corte = UuidCutover(c, [TableSpec("roles", pk="id"), TableSpec("permisos", pk="id")])
    assert set(corte._specs) == {"roles"}


def test_matrix_labels_are_shown_with_accents():
    from backend.application.security.role_permission_matrix import action_label

    assert action_label("accion_correctiva.ver") == "Acción correctiva: ver"
    assert action_label("analisis.ver") == "Análisis: ver"
    assert action_label("clasificaciones.gestionar") == "Clasificaciones: gestionar"
