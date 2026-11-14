"""SDLC-ARQ-PERM-002 — nadie otorga fuera de su alcance.

La guarda de escalada revisaba QUÉ se otorga (permisos que el actor no tiene),
pero no DÓNDE: un gerente de Centro podía dar un rol en toda la empresa o en
Chihuahua, y editar excepciones de un usuario de otra sucursal.

Mismo escenario que `test_contextual_permissions.py`. El gerente tiene de verdad
los permisos del rol que otorga: lo único que puede detenerlo es el alcance.
"""
from __future__ import annotations

import importlib
import json

import pytest

from backend.application.commands.settings_commands import SaveUserPermissionsCommand
from backend.application.configuracion.authorization import ConfiguracionAuthorizationPolicy
from backend.application.use_cases.save_user_permissions_use_case import (
    SaveUserPermissionsUseCase,
)
from backend.domain.organization.role_assignment import RoleAssignmentError
from backend.domain.settings.exceptions import ConfigurationPermissionDeniedError
from backend.shared.ids import new_uuid
from tests.integration.security.test_contextual_permissions import (  # noqa: F401 (fixture)
    _Concede,
    _asignar,
    _rol,
    _servicio,
    _usuario,
    org,
)


@pytest.fixture
def escenario(org):  # noqa: F811
    """`gerente` de Centro con los permisos de `t_cajero`; un cajero en cada lado."""
    gerente = _usuario(org.conn, "t_cajero", org.centro)
    org.gerente = gerente
    org.de_chihuahua = _usuario(org.conn, "t_gerente", org.chihuahua)
    org.conn.commit()
    return org


def _denegados(o):
    return o.conn.execute("SELECT usuario, detalles, valor_despues FROM audit_logs"
                          " WHERE accion='ROLE_ASSIGNMENT_DENIED'").fetchall()


def _asignaciones(o, user):
    return o.conn.execute("SELECT COUNT(*) FROM user_role_assignments WHERE user_id=?"
                          " AND status='ACTIVE'", (user,)).fetchone()[0]


def _otorga(o, *, a, scope_type, scope_id, actor=None):
    return _servicio(o, actor or o.gerente).assign(
        user_id=a, role_id=_rol(o.conn, "t_cajero"), scope_type=scope_type, scope_id=scope_id,
        reason="Cobertura")


class TestAsignarRol:
    def test_el_gerente_de_centro_asigna_en_centro(self, escenario):
        o = escenario
        _otorga(o, a=o.cajero, scope_type="ORG_UNIT", scope_id=o.centro)
        assert _asignaciones(o, o.cajero) == 1
        assert _denegados(o) == []

    def test_no_asigna_en_otra_sucursal(self, escenario):
        o = escenario
        with pytest.raises(RoleAssignmentError, match="alcance"):
            _otorga(o, a=o.cajero, scope_type="ORG_UNIT", scope_id=o.chihuahua)
        assert _asignaciones(o, o.cajero) == 0

    def test_no_asigna_en_toda_la_empresa(self, escenario):
        o = escenario
        with pytest.raises(RoleAssignmentError, match="alcance"):
            _otorga(o, a=o.cajero, scope_type="COMPANY", scope_id=o.empresa)
        assert _asignaciones(o, o.cajero) == 0

    def test_no_asigna_en_una_region_que_no_cubre_entera(self, escenario):
        o = escenario
        with pytest.raises(RoleAssignmentError, match="alcance"):
            _otorga(o, a=o.cajero, scope_type="ORG_UNIT", scope_id=o.norte)

    def test_no_asigna_a_un_usuario_fuera_de_su_alcance(self, escenario):
        """El ámbito es suyo, pero el usuario es de otra sucursal."""
        o = escenario
        with pytest.raises(RoleAssignmentError, match="alcance"):
            _otorga(o, a=o.de_chihuahua, scope_type="ORG_UNIT", scope_id=o.centro)

    def test_quien_tiene_la_region_asigna_dentro_de_ella(self, escenario):
        o = escenario
        regional = _usuario(o.conn, "t_cajero", o.centro)
        _asignar(o, regional, "t_cajero", "ORG_UNIT", o.norte)
        _otorga(o, actor=regional, a=o.de_chihuahua, scope_type="ORG_UNIT", scope_id=o.chihuahua)
        assert _asignaciones(o, o.de_chihuahua) == 1

    def test_el_dueno_asigna_en_cualquier_ambito(self, escenario):
        o = escenario
        _otorga(o, actor=o.dueno, a=o.cajero, scope_type="COMPANY", scope_id=o.empresa)
        assert _asignaciones(o, o.cajero) == 1

    def test_el_rechazo_queda_auditado_con_motivo(self, escenario):
        o = escenario
        with pytest.raises(RoleAssignmentError):
            _otorga(o, a=o.cajero, scope_type="COMPANY", scope_id=o.empresa)
        filas = _denegados(o)
        assert len(filas) == 1
        assert filas[0]["usuario"] == o.gerente
        assert "alcance" in filas[0]["detalles"]
        despues = json.loads(filas[0]["valor_despues"])
        assert despues["user_id"] == o.cajero
        assert despues["scope_type"] == "COMPANY"


class TestRevocarRol:
    def test_no_revoca_fuera_de_su_alcance(self, escenario):
        o = escenario
        a = _otorga(o, actor=o.dueno, a=o.de_chihuahua, scope_type="ORG_UNIT",
                    scope_id=o.chihuahua)
        with pytest.raises(RoleAssignmentError, match="alcance"):
            _servicio(o, o.gerente).revoke(a.id, reason="Quitar")
        assert _asignaciones(o, o.de_chihuahua) == 1
        assert len(_denegados(o)) == 1

    def test_revoca_dentro_de_su_alcance(self, escenario):
        o = escenario
        a = _otorga(o, actor=o.dueno, a=o.cajero, scope_type="ORG_UNIT", scope_id=o.centro)
        _servicio(o, o.gerente).revoke(a.id, reason="Terminó")
        assert _asignaciones(o, o.cajero) == 0


def _guardar(o, *, actor, objetivo, scope=None):
    return SaveUserPermissionsUseCase(
        o.conn, ConfiguracionAuthorizationPolicy(_Concede())).execute(
        SaveUserPermissionsCommand(
            operation_id=new_uuid(), branch_id="b", user_id=actor, target_user_id=objetivo,
            scope_branch_id=scope,
            permissions=({"module": "POS", "action": "ver", "state": "GRANT"},)))


@pytest.fixture
def con_excepciones(escenario):
    importlib.import_module("migrations.standalone.047_v13_schema").up(escenario.conn)
    importlib.import_module("migrations.standalone.224_configuracion_security_schema").run(
        escenario.conn)
    return escenario


def _rechazos(o):
    return o.conn.execute("SELECT user_id, reason FROM configuracion_audit_log"
                          " WHERE action='ACTUALIZAR_PERMISOS_DENEGADO'").fetchall()


class TestExcepcionesPorUsuario:
    def test_dentro_de_su_alcance_se_guarda(self, con_excepciones):
        o = con_excepciones
        assert _guardar(o, actor=o.gerente, objetivo=o.cajero, scope=o.centro).success is True
        assert _rechazos(o) == []

    def test_sin_ambito_si_el_usuario_es_solo_suyo(self, con_excepciones):
        o = con_excepciones
        assert _guardar(o, actor=o.gerente, objetivo=o.cajero).success is True

    def test_no_edita_a_un_usuario_de_otra_sucursal(self, con_excepciones):
        o = con_excepciones
        with pytest.raises(ConfigurationPermissionDeniedError, match="alcance"):
            _guardar(o, actor=o.gerente, objetivo=o.de_chihuahua)
        assert len(_rechazos(o)) == 1

    def test_no_edita_en_una_sucursal_fuera_de_su_alcance(self, con_excepciones):
        o = con_excepciones
        with pytest.raises(ConfigurationPermissionDeniedError, match="alcance"):
            _guardar(o, actor=o.gerente, objetivo=o.cajero, scope=o.chihuahua)
        assert "alcance" in _rechazos(o)[0]["reason"]

    def test_una_excepcion_global_exige_cubrir_todo_lo_que_el_usuario_alcanza(
            self, con_excepciones):
        """Sin sucursal la excepción vale en todas las del usuario: si también
        opera en Chihuahua, un gerente de Centro no la concede ahí de paso."""
        o = con_excepciones
        _asignar(o, o.cajero, "t_gerente", "ORG_UNIT", o.chihuahua)
        with pytest.raises(ConfigurationPermissionDeniedError, match="alcance"):
            _guardar(o, actor=o.gerente, objetivo=o.cajero)
        assert _guardar(o, actor=o.gerente, objetivo=o.cajero, scope=o.centro).success is True

    def test_el_dueno_edita_a_cualquiera(self, con_excepciones):
        o = con_excepciones
        assert _guardar(o, actor=o.dueno, objetivo=o.de_chihuahua,
                        scope=o.chihuahua).success is True
