"""SET-1 — ConfiguracionAuthorizationPolicy (permission gate + hot
authorization). Pure application layer — no DB, no PyQt. Mirrors
`tests/unit/inventory/test_authorization.py`'s shape (the established
Compras/Inventory authorization standard).
"""

from __future__ import annotations

import pytest

from backend.application.configuracion.authorization import (
    AllowAllConfiguracionPermissionCheckerForTests,
    ConfiguracionAuthorizationPolicy,
    DenyAllConfiguracionPermissionCheckerForTests,
    SessionPermissionChecker,
)
from backend.application.configuracion.permissions import ConfiguracionPermissions
from backend.domain.settings.exceptions import (
    ConfigurationAuthorizationConfigurationError,
    ConfigurationPermissionDeniedError,
    ConfigurationSegregationOfDutiesError,
)
from backend.shared.ids import new_uuid


class _FakeChecker:
    def __init__(self, grants: set[tuple[str, str]]) -> None:
        self._grants = grants

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return (user_id, permission_code) in self._grants


class TestRequire:
    def test_require_raises_when_no_checker_wired(self):
        policy = ConfiguracionAuthorizationPolicy()
        with pytest.raises(ConfigurationAuthorizationConfigurationError):
            policy.require("user-1", ConfiguracionPermissions.DISPOSITIVOS_CREAR)

    def test_require_raises_for_unknown_permission_code(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        with pytest.raises(ConfigurationPermissionDeniedError):
            policy.require("user-1", "CONFIGURACION.no_existe")

    def test_require_raises_without_authenticated_user(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        with pytest.raises(ConfigurationPermissionDeniedError):
            policy.require("", ConfiguracionPermissions.DISPOSITIVOS_CREAR)

    def test_require_raises_when_checker_denies(self):
        policy = ConfiguracionAuthorizationPolicy(DenyAllConfiguracionPermissionCheckerForTests())
        with pytest.raises(ConfigurationPermissionDeniedError):
            policy.require("user-1", ConfiguracionPermissions.DISPOSITIVOS_CREAR)

    def test_require_passes_when_checker_grants(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        policy.require("user-1", ConfiguracionPermissions.DISPOSITIVOS_CREAR)  # does not raise

    def test_permissive_for_tests_grants_everything(self):
        policy = ConfiguracionAuthorizationPolicy.permissive_for_tests()
        policy.require("anyone", ConfiguracionPermissions.EMPRESA_EDITAR)


class TestHasPermission:
    def test_has_permission_false_without_checker(self):
        policy = ConfiguracionAuthorizationPolicy()
        assert policy.has_permission("user-1", ConfiguracionPermissions.DISPOSITIVOS_CREAR) is False

    def test_has_permission_false_without_user(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        assert policy.has_permission("", ConfiguracionPermissions.DISPOSITIVOS_CREAR) is False

    def test_has_permission_false_for_unknown_code(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        assert policy.has_permission("user-1", "CONFIGURACION.no_existe") is False

    def test_has_permission_reflects_checker(self):
        checker = _FakeChecker({("user-1", ConfiguracionPermissions.DISPOSITIVOS_CREAR)})
        policy = ConfiguracionAuthorizationPolicy(checker)
        assert policy.has_permission("user-1", ConfiguracionPermissions.DISPOSITIVOS_CREAR) is True
        assert policy.has_permission("user-2", ConfiguracionPermissions.DISPOSITIVOS_CREAR) is False


class TestAuthorizeException:
    def test_grants_and_returns_authorization_grant(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        operation_id = new_uuid()
        grant = policy.authorize_exception(
            authorizer_user_id="reviewer-2", requested_by="editor-1",
            permission_code=ConfiguracionPermissions.DOCUMENTOS_PLANTILLA_APROBAR,
            operation_id=operation_id, reason="Aprobación de plantilla fiscal",
        )
        assert grant.authorized_by == "reviewer-2"
        assert grant.requested_by == "editor-1"
        assert grant.operation_id == operation_id

    def test_rejects_same_user_as_requester_and_authorizer(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        with pytest.raises(ConfigurationSegregationOfDutiesError):
            policy.authorize_exception(
                authorizer_user_id="editor-1", requested_by="editor-1",
                permission_code=ConfiguracionPermissions.DOCUMENTOS_PLANTILLA_APROBAR,
                operation_id=new_uuid(), reason="x",
            )

    def test_requires_an_authorizer(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        with pytest.raises(ConfigurationPermissionDeniedError):
            policy.authorize_exception(
                authorizer_user_id="", requested_by="editor-1",
                permission_code=ConfiguracionPermissions.DOCUMENTOS_PLANTILLA_APROBAR,
                operation_id=new_uuid(), reason="x",
            )

    def test_authorizer_must_hold_the_permission(self):
        policy = ConfiguracionAuthorizationPolicy(DenyAllConfiguracionPermissionCheckerForTests())
        with pytest.raises(ConfigurationPermissionDeniedError):
            policy.authorize_exception(
                authorizer_user_id="reviewer-2", requested_by="editor-1",
                permission_code=ConfiguracionPermissions.DOCUMENTOS_PLANTILLA_APROBAR,
                operation_id=new_uuid(), reason="x",
            )


class _FakeSession:
    def __init__(self, *, is_active: bool, grants: set[str]) -> None:
        self.is_active = is_active
        self._grants = grants

    def tiene_permiso(self, codigo_permiso: str) -> bool:
        return codigo_permiso in self._grants


class TestSessionPermissionChecker:
    def test_false_when_session_is_none(self):
        checker = SessionPermissionChecker(None)
        assert checker.has_permission("user-1", ConfiguracionPermissions.DISPOSITIVOS_CREAR) is False

    def test_false_when_session_inactive(self):
        session = _FakeSession(is_active=False, grants={ConfiguracionPermissions.DISPOSITIVOS_CREAR})
        checker = SessionPermissionChecker(session)
        assert checker.has_permission("user-1", ConfiguracionPermissions.DISPOSITIVOS_CREAR) is False

    def test_delegates_to_session_tiene_permiso(self):
        session = _FakeSession(is_active=True, grants={ConfiguracionPermissions.DISPOSITIVOS_CREAR})
        checker = SessionPermissionChecker(session)
        assert checker.has_permission("user-1", ConfiguracionPermissions.DISPOSITIVOS_CREAR) is True
        assert checker.has_permission("user-1", ConfiguracionPermissions.EMPRESA_EDITAR) is False
