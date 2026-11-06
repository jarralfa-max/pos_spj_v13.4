"""SDLC-ARQ-PERM-003 — un solo resolvedor de alcance.

`BranchScopeQueryService` usaba `usuarios_sucursales` + la sucursal propia e
ignoraba `user_role_assignments` y la jerarquía; `AccessScopeResolver` sí los
usa. Según qué módulo preguntara, el mismo usuario alcanzaba sucursales
distintas, y una asignación revocada en uno seguía vigente en el otro. Además el
checker de Transferencias dejaba pasar una operación sin sucursal.

Mismo escenario que `test_contextual_permissions.py`: Centro, y la región Norte
con Chihuahua. Sin dobles: lo que puede fallar es justo la lectura real.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.application.security.access_scope import AccessScopeResolver
from backend.application.security.branch_scope_query_service import BranchScopeQueryService
from backend.application.transfers.authorization import TransferAuthorizationPolicy
from backend.application.transfers.permissions import TransferPermissions
from backend.application.transfers.session_scope_checker import TransferSessionScopeChecker
from backend.domain.transfers.exceptions import PermissionDeniedError
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)
from backend.shared.ids import new_uuid
from tests.integration.security.test_contextual_permissions import (  # noqa: F401 (fixture)
    _asignar,
    org,
)


def _alcance_del_servicio(o, user):
    return BranchScopeQueryService(o.conn).allowed_branch_ids(user)


def _alcance_de_la_sesion(o, user):
    """`None` = toda la empresa, igual que el contrato del servicio."""
    reach = AccessScopeResolver(SqlitePermissionRepository(o.conn)).reach(user)
    return None if reach.company_wide else reach.site_ids


def _coinciden(o, user):
    permitidas = _alcance_del_servicio(o, user)
    esperado = _alcance_de_la_sesion(o, user)
    assert (permitidas if permitidas is None else frozenset(permitidas)) == esperado
    return esperado


class TestUnSoloAlcance:
    def test_solo_sucursal_propia(self, org):
        assert _coinciden(org, org.cajero) == {org.centro}

    def test_asignacion_directa(self, org):
        # `_born_clean_db` no incluye la migración 047, que crea esta tabla.
        org.conn.execute("CREATE TABLE IF NOT EXISTS usuarios_sucursales"
                         " (usuario_id TEXT, sucursal_id TEXT)")
        org.conn.execute("INSERT INTO usuarios_sucursales (usuario_id, sucursal_id) VALUES (?,?)",
                         (org.cajero, org.chihuahua))
        assert _coinciden(org, org.cajero) == {org.centro, org.chihuahua}

    def test_rol_en_una_sucursal(self, org):
        _asignar(org, org.cajero, "t_gerente", "ORG_UNIT", org.chihuahua)
        assert _coinciden(org, org.cajero) == {org.centro, org.chihuahua}

    def test_rol_en_una_region_alcanza_lo_que_cuelga_de_ella(self, org):
        _asignar(org, org.cajero, "t_gerente", "ORG_UNIT", org.norte)
        assert _coinciden(org, org.cajero) == {org.centro, org.chihuahua}

    def test_rol_de_toda_la_empresa(self, org):
        _asignar(org, org.cajero, "t_gerente", "COMPANY", org.empresa)
        assert _coinciden(org, org.cajero) is None

    def test_el_dueno_es_de_toda_la_empresa(self, org):
        assert _coinciden(org, org.dueno) is None

    def test_una_asignacion_vencida_no_cuenta_en_ninguno(self, org):
        ayer = date.today() - timedelta(days=1)
        _asignar(org, org.cajero, "t_gerente", "ORG_UNIT", org.chihuahua, hasta=ayer)
        assert _coinciden(org, org.cajero) == {org.centro}

    def test_una_asignacion_revocada_no_sigue_vigente_en_el_otro(self, org):
        _asignar(org, org.cajero, "t_gerente", "ORG_UNIT", org.chihuahua)
        org.conn.execute("UPDATE user_role_assignments SET status='REVOKED',"
                         " revoked_at='2026-01-02' WHERE user_id=?", (org.cajero,))
        assert _coinciden(org, org.cajero) == {org.centro}

    def test_un_usuario_desconocido_no_alcanza_nada(self, org):
        assert _alcance_del_servicio(org, new_uuid()) == ()

    def test_sin_tablas_de_seguridad_falla_cerrado(self):
        import sqlite3
        conn = sqlite3.connect(":memory:")
        assert BranchScopeQueryService(conn).allowed_branch_ids(new_uuid()) == ()


class TestCheckerDeTransferencias:
    def test_sin_sucursal_falla_cerrado(self, org):
        checker = TransferSessionScopeChecker(org.conn)
        assert checker.can_access_transfer_scope(user_id=org.cajero, branch_id=None) is False
        assert checker.can_access_transfer_scope(user_id=org.cajero, branch_id="  ") is False

    def test_sin_sucursal_pasa_solo_el_alcance_global(self, org):
        checker = TransferSessionScopeChecker(org.conn)
        assert checker.can_access_transfer_scope(user_id=org.dueno, branch_id=None) is True

    def test_sin_usuario_nunca(self, org):
        checker = TransferSessionScopeChecker(org.conn)
        assert checker.can_access_transfer_scope(user_id="", branch_id=None) is False
        assert checker.can_access_transfer_scope(user_id="", branch_id=org.centro) is False

    def test_usa_el_resolvedor_canonico(self, org):
        _asignar(org, org.cajero, "t_gerente", "ORG_UNIT", org.norte)
        checker = TransferSessionScopeChecker(org.conn)
        assert checker.can_access_transfer_scope(user_id=org.cajero, branch_id=org.chihuahua)

    def test_el_dueno_opera_en_cualquier_sucursal(self, org):
        """El docstring ya lo prometía, pero sin permiso inyectado el servicio
        lo dejaba en su sucursal propia."""
        checker = TransferSessionScopeChecker(org.conn)
        assert checker.can_access_transfer_scope(user_id=org.dueno, branch_id=org.chihuahua)


class _Concede:
    def has_permission(self, user_id, code):
        return True


class TestPoliticaDeTransferencias:
    def _policy(self, o):
        return TransferAuthorizationPolicy(_Concede(), TransferSessionScopeChecker(o.conn))

    def test_una_pata_declarada_sin_sucursal_se_niega(self, org):
        with pytest.raises(PermissionDeniedError, match="origen"):
            self._policy(org).require(user_id=org.cajero, branch_id=None,
                                      permission_code=TransferPermissions.DISPATCH)

    def test_un_destino_declarado_vacio_se_niega(self, org):
        with pytest.raises(PermissionDeniedError, match="destino"):
            self._policy(org).require(user_id=org.cajero, branch_id=org.centro,
                                      destination_branch_id="",
                                      permission_code=TransferPermissions.DISPATCH)

    def test_una_operacion_de_una_sola_pata_no_exige_destino(self, org):
        self._policy(org).require(user_id=org.cajero, branch_id=org.centro,
                                  permission_code=TransferPermissions.DISPATCH)

    def test_lo_que_no_recae_en_una_sucursal_no_pide_alcance(self, org):
        """Imprimir y generar sugerencias no declaran pata, y la autorización en
        caliente valida al autorizador sin sucursal: siguen funcionando."""
        self._policy(org).require(user_id=org.cajero,
                                  permission_code=TransferPermissions.PRINT)
        grant = self._policy(org).authorize_exception(
            requested_by=new_uuid(), authorized_by=org.cajero,
            permission_code=TransferPermissions.RECEIVE_OVER_TOLERANCE, reason="Conteo validado",
            operation_id=new_uuid(), transfer_id=new_uuid())
        assert grant.authorized_by == org.cajero
