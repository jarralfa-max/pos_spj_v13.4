"""SDLC-ARQ-PERM-001 — `ConfiguracionActionAuthorizer`, lo que cada caso de
uso de escritura de Configuración verifica en backend."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.application.configuracion.authorization import (
    ConfiguracionActionAuthorizer,
    ConfiguracionAuthorizationPolicy,
    DenyAllConfiguracionPermissionCheckerForTests,
)
from backend.application.configuracion.permissions import ConfiguracionPermissions as P
from backend.application.security.unwired_policy import unwired
from backend.domain.settings.exceptions import (
    ConfigurationAuthorizationConfigurationError,
    ConfigurationPermissionDeniedError,
)


def _session(user_id="u-1", grants=(), active=True):
    return SimpleNamespace(user_id=user_id, is_active=active,
                           tiene_permiso=lambda code: code in grants)


def test_session_authorizer_returns_the_session_actor_when_granted():
    authz = ConfiguracionActionAuthorizer.for_session(
        _session(grants={P.INTEGRACIONES_SECRETOS}))
    assert authz.require(P.INTEGRACIONES_SECRETOS) == "u-1"


def test_session_authorizer_denies_without_the_permission():
    authz = ConfiguracionActionAuthorizer.for_session(_session(grants={P.INTEGRACIONES_VIEW}))
    with pytest.raises(ConfigurationPermissionDeniedError):
        authz.require(P.INTEGRACIONES_SECRETOS)


@pytest.mark.parametrize("session", [None, _session(active=False, grants={P.FEATURE_FLAGS_CREAR}),
                                     _session(user_id="", grants={P.FEATURE_FLAGS_CREAR})])
def test_no_live_session_is_denied(session):
    authz = ConfiguracionActionAuthorizer.for_session(session)
    with pytest.raises(ConfigurationPermissionDeniedError):
        authz.require(P.FEATURE_FLAGS_CREAR)


def test_claimed_actor_different_from_session_is_denied_even_with_permission():
    authz = ConfiguracionActionAuthorizer.for_session(
        _session(grants={P.FEATURE_FLAGS_APROBAR}))
    with pytest.raises(ConfigurationPermissionDeniedError, match="no es el de la sesión"):
        authz.require(P.FEATURE_FLAGS_APROBAR, claimed_actor="otro-usuario")


@pytest.mark.parametrize("claimed", ["u-1", "", None])
def test_claimed_actor_equal_or_empty_passes(claimed):
    authz = ConfiguracionActionAuthorizer.for_session(
        _session(grants={P.FEATURE_FLAGS_APROBAR}))
    assert authz.require(P.FEATURE_FLAGS_APROBAR, claimed_actor=claimed) == "u-1"


def test_unknown_permission_code_is_denied():
    authz = ConfiguracionActionAuthorizer.permissive_for_tests()
    with pytest.raises(ConfigurationPermissionDeniedError, match="desconocido"):
        authz.require("CONFIGURACION.no_existe")


def test_without_policy_fails_closed():
    with pytest.raises(ConfigurationAuthorizationConfigurationError):
        ConfiguracionActionAuthorizer().require(P.FEATURE_FLAGS_CREAR)


@pytest.mark.unwired_fails_closed
def test_unwired_default_fails_closed_in_production():
    with pytest.raises(ConfigurationAuthorizationConfigurationError):
        unwired(ConfiguracionActionAuthorizer).require(P.FEATURE_FLAGS_CREAR)


def test_deny_all_policy_denies():
    authz = ConfiguracionActionAuthorizer(
        ConfiguracionAuthorizationPolicy(DenyAllConfiguracionPermissionCheckerForTests()),
        actor=lambda: "u-1")
    with pytest.raises(ConfigurationPermissionDeniedError):
        authz.require(P.TEMA_CREAR)


def test_require_mapped_uses_the_action_table_and_accepts_enum_or_value():
    from backend.application.use_cases.configuracion.device_management_use_cases import (
        DeviceStatusAction,
    )
    table = {DeviceStatusAction.BLOCK: P.DISPOSITIVOS_DESHABILITAR,
             DeviceStatusAction.ACTIVATE: P.DISPOSITIVOS_EDITAR}
    authz = ConfiguracionActionAuthorizer.for_session(
        _session(grants={P.DISPOSITIVOS_DESHABILITAR}))
    assert authz.require_mapped(table, DeviceStatusAction.BLOCK) == "u-1"
    assert authz.require_mapped(table, "BLOCK") == "u-1"
    with pytest.raises(ConfigurationPermissionDeniedError):
        authz.require_mapped(table, DeviceStatusAction.ACTIVATE)


def test_require_mapped_denies_an_action_without_permission():
    authz = ConfiguracionActionAuthorizer.permissive_for_tests()
    with pytest.raises(ConfigurationPermissionDeniedError, match="sin permiso definido"):
        authz.require_mapped({}, "DESTRUIR")


def test_permissive_for_tests_echoes_the_claimed_actor():
    authz = ConfiguracionActionAuthorizer.permissive_for_tests()
    assert authz.require(P.TEMA_CREAR, claimed_actor="aprobador") == "aprobador"
    assert authz.require(P.TEMA_CREAR)
