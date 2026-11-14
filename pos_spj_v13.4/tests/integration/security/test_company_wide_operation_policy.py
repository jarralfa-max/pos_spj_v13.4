"""SDLC-ARQ-PERM-004 — política aprobada por el responsable (2026-11-02).

* El dueño y las cuentas con rol de toda la empresa SÍ operan el POS de cualquier
  sucursal sin asignación operativa explícita.
* Los roles de acceso total siguen siendo RESERVADOS por nombre, no roles normales
  con todos los permisos.

Estas pruebas fijan esa política: no separar «consulta global» de «operación en
el sitio» es una decisión, no un descuido.
"""
from __future__ import annotations

import pytest

from backend.bootstrap.application_context_builder import ApplicationContextBuilder
from backend.bootstrap.application_context_errors import SiteAccessDeniedError
from backend.bootstrap.legacy_session_adapter import LegacySessionAdapter
from backend.bootstrap.permission_evaluator import PermissionEvaluator
from backend.security.permissions.principals import is_full_access_role, is_reserved_role_name
from tests.integration.security.test_contextual_permissions import (  # noqa: F401 (fixture)
    _anclar,
    _asignar,
    _login,
    org,
)


def test_el_dueno_opera_el_pos_de_una_sucursal_sin_asignacion(org):  # noqa: F811
    _anclar(org, org.chihuahua)
    ctx = ApplicationContextBuilder(org.conn).build(
        _login(org, org.dueno, "system_owner", org.centro))
    assert PermissionEvaluator(ctx).has_permission("POS.venta.completar")


def test_un_rol_de_toda_la_empresa_opera_en_cualquier_sucursal(org):  # noqa: F811
    _asignar(org, org.cajero, "t_cajero", "COMPANY", org.empresa)
    _anclar(org, org.chihuahua)
    ctx = ApplicationContextBuilder(org.conn).build(_login(org, org.cajero, "t_cajero", org.centro))
    assert ctx.branch_id == org.chihuahua
    assert PermissionEvaluator(ctx).has_permission("POS.ver")


def test_un_rol_de_sucursal_no_opera_fuera_de_ella(org):  # noqa: F811
    """El contraste: el acceso a cualquier sitio es del ámbito, no de ser cajero."""
    _anclar(org, org.chihuahua)
    with pytest.raises(SiteAccessDeniedError):
        ApplicationContextBuilder(org.conn).build(_login(org, org.cajero, "t_cajero", org.centro))


@pytest.mark.parametrize("rol", ("system_owner", "admin", "superadmin", "administrador"))
def test_los_roles_de_acceso_total_son_reservados(rol):
    assert is_full_access_role(rol) and is_reserved_role_name(rol)


def test_ningun_rol_normal_concede_acceso_total_por_su_nombre():
    assert not is_full_access_role("gerente")


def test_la_lista_de_nombres_es_gerente_ya_no_existe():
    """Sin ningún lector: otra lista de nombres que conceden, ahora retirada."""
    assert not hasattr(LegacySessionAdapter, "es_gerente")
