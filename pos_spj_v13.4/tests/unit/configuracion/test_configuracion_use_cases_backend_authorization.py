"""SDLC-ARQ-PERM-001 — cada caso de uso de escritura de Configuración verifica
su permiso en BACKEND, antes de tocar la base o el almacén de secretos.

La tabla `EXPECTED` está congelada a partir de lo que exigía
`ConfiguracionPresenter._authorize` ANTES del cambio
(`configuracion_presenter.py` @ 1c4786a7): la pantalla y el backend exigen el
mismo código, y nadie gana ni pierde acceso por este ítem.
"""

from __future__ import annotations

import importlib
import inspect
from types import SimpleNamespace

import pytest

from backend.application.configuracion.authorization import (
    ConfiguracionActionAuthorizer,
    ConfiguracionAuthorizationPolicy,
)
from backend.application.configuracion.permissions import ConfiguracionPermissions as P
from backend.domain.settings.exceptions import ConfigurationPermissionDeniedError

_PKG = "backend.application.use_cases.configuracion."
SESSION_USER = "u-sesion"


# ── dobles ────────────────────────────────────────────────────────────────────

class _Trap:
    """Conexión / almacén / impresora que registra CUALQUIER uso."""

    def __init__(self) -> None:
        object.__setattr__(self, "calls", [])

    def __getattr__(self, name):
        def _record(*args, **kwargs):
            self.calls.append(name)
            return _Trap()
        return _record

    def __setattr__(self, name, value):
        self.calls.append(f"set:{name}")


class _RecordingDenyChecker:
    def __init__(self) -> None:
        self.asked: list[str] = []

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        self.asked.append(permission_code)
        return False


def _denying_authorizer():
    checker = _RecordingDenyChecker()
    return checker, ConfiguracionActionAuthorizer(
        ConfiguracionAuthorizationPolicy(checker), actor=lambda: SESSION_USER)


# ── tabla congelada: caso de uso → permiso (o tabla por acción) ──────────────

AG = P.APARIENCIA_GESTIONAR
CC = P.PANTALLA_CLIENTE_CONTENIDO_CREAR
CP = P.PANTALLA_CLIENTE_CAMPANA_PROGRAMAR
PG = P.PANTALLA_CLIENTE_PUBLICIDAD_GESTIONAR
NG = P.NOTIFICACIONES_GESTIONAR

EXPECTED = {
    "appearance_management_use_cases": {
        "CreateThemeUseCase": P.TEMA_CREAR, "UpdateThemeUseCase": AG,
        "ChangeThemeStatusUseCase": AG, "CreateDesignTokenUseCase": AG,
        "UpdateDesignTokenUseCase": AG, "CreateDensityProfileUseCase": AG,
        "UpdateDensityProfileUseCase": AG, "ChangeDensityProfileStatusUseCase": AG,
        "CreateAppearancePreferenceUseCase": AG, "ChangeAppearancePreferenceStatusUseCase": AG,
    },
    "set_default_theme_use_case": {"SetDefaultThemeUseCase": P.TEMA_ACTIVAR},
    "branding_use_cases": {
        "ImportLogoUseCase": P.EMPRESA_EDITAR, "SetCompanyLogoUseCase": P.EMPRESA_EDITAR,
        "SetBranchLogoUseCase": P.EMPRESA_EDITAR,
    },
    "company_branch_use_cases": {
        "SaveCompanyProfileUseCase": P.EMPRESA_EDITAR,
        "RegisterBranchProfileUseCase": P.SUCURSAL_CREAR,
        "UpdateBranchProfileUseCase": P.SUCURSAL_EDITAR,
    },
    "customer_display_advertising_use_cases": {
        "ImportDisplayMediaUseCase": CC, "CreateContentUseCase": CC, "UpdateContentUseCase": CC,
        "ChangeContentStatusUseCase": CC, "CreateContentCampaignUseCase": CP,
        "UpdateContentCampaignUseCase": CP,
        "ChangeContentCampaignStatusUseCase": {
            "SUBMIT_FOR_APPROVAL": CP, "REJECT": P.PANTALLA_CLIENTE_CONTENIDO_APROBAR,
            "APPROVE": P.PANTALLA_CLIENTE_CONTENIDO_APROBAR, "ACTIVATE": CP,
            "DEACTIVATE": CP, "EXPIRE": CP, "ARCHIVE": CP},
        "CreateAdvertisingSlotUseCase": PG, "UpdateAdvertisingSlotUseCase": PG,
        "ChangeAdvertisingSlotStatusUseCase": PG, "AssignCampaignPlacementUseCase": PG,
        "UnassignCampaignPlacementUseCase": PG,
    },
    "device_assignment_use_cases": {
        "AssignDeviceUseCase": P.DISPOSITIVOS_ASIGNAR, "UnassignDeviceUseCase": P.DISPOSITIVOS_ASIGNAR,
    },
    "device_management_use_cases": {
        "RegisterDeviceProfileUseCase": P.DISPOSITIVOS_CREAR,
        "RegisterDeviceUseCase": P.DISPOSITIVOS_CREAR,
        "UpdateDeviceUseCase": P.DISPOSITIVOS_EDITAR,
        "ChangeDeviceStatusUseCase": {
            "ACTIVATE": P.DISPOSITIVOS_EDITAR, "DEACTIVATE": P.DISPOSITIVOS_EDITAR,
            "UNBLOCK": P.DISPOSITIVOS_EDITAR, "BLOCK": P.DISPOSITIVOS_DESHABILITAR,
            "RETIRE": P.DISPOSITIVOS_DESHABILITAR},
        "SetDeviceWindowsPrinterUseCase": P.DISPOSITIVOS_EDITAR,
    },
    "device_test_use_cases": {"TestDeviceUseCase": P.DISPOSITIVOS_PROBAR},
    "document_template_use_cases": {
        "CreateDocumentTemplateUseCase": P.DOCUMENTOS_PLANTILLA_CREAR,
        "CreateNextTemplateVersionUseCase": P.DOCUMENTOS_PLANTILLA_EDITAR,
        "ChangeTemplateVersionStatusUseCase": {
            "SUBMIT_FOR_APPROVAL": P.DOCUMENTOS_PLANTILLA_EDITAR,
            "REJECT": P.DOCUMENTOS_PLANTILLA_APROBAR, "APPROVE": P.DOCUMENTOS_PLANTILLA_APROBAR,
            "ACTIVATE": P.DOCUMENTOS_PLANTILLA_ACTIVAR, "DEACTIVATE": P.DOCUMENTOS_PLANTILLA_EDITAR,
            "EXPIRE": P.DOCUMENTOS_PLANTILLA_EDITAR, "ARCHIVE": P.DOCUMENTOS_PLANTILLA_EDITAR},
        "UpdateDocumentTemplateUseCase": P.DOCUMENTOS_PLANTILLA_EDITAR,
        "ChangeDocumentTemplateStatusUseCase": P.DOCUMENTOS_PLANTILLA_ACTIVAR,
    },
    "feature_flag_change_request_use_cases": {
        "ApproveFeatureFlagChangeRequestUseCase": P.FEATURE_FLAGS_APROBAR,
        "RejectFeatureFlagChangeRequestUseCase": P.FEATURE_FLAGS_APROBAR,
        "ApplyFeatureFlagChangeRequestUseCase": P.FEATURE_FLAGS_ACTIVAR,
    },
    "feature_flag_management_use_cases": {
        "CreateFeatureFlagUseCase": P.FEATURE_FLAGS_CREAR,
        "UpdateFeatureFlagUseCase": P.FEATURE_FLAGS_EDITAR,
        "ChangeFeatureFlagStatusUseCase": P.FEATURE_FLAGS_EDITAR,
        "RequestFeatureFlagChangeUseCase": P.FEATURE_FLAGS_EDITAR,
    },
    "integration_management_use_cases": {
        "CreateIntegrationDefinitionUseCase": P.INTEGRACIONES_CREAR,
        "UpdateIntegrationDefinitionUseCase": P.INTEGRACIONES_EDITAR,
        "ChangeIntegrationDefinitionStatusUseCase": {
            "ACTIVATE": P.INTEGRACIONES_ACTIVAR, "DEACTIVATE": P.INTEGRACIONES_DESACTIVAR},
        "CreateIntegrationInstanceUseCase": P.INTEGRACIONES_CREAR,
        "UpdateIntegrationInstanceUseCase": P.INTEGRACIONES_EDITAR,
        "ChangeIntegrationInstanceStatusUseCase": {
            "ACTIVATE": P.INTEGRACIONES_ACTIVAR, "DEACTIVATE": P.INTEGRACIONES_DESACTIVAR},
        "SetIntegrationInstanceCredentialUseCase": P.INTEGRACIONES_SECRETOS,
        "CreateWebhookEndpointUseCase": P.WEBHOOKS_GESTIONAR,
        "ChangeWebhookEndpointStatusUseCase": P.WEBHOOKS_GESTIONAR,
        "RecordIntegrationHealthCheckUseCase": P.INTEGRACIONES_PROBAR,
        "TestIntegrationConnectionUseCase": P.INTEGRACIONES_PROBAR,
    },
    "marketing_campaign_use_cases": {
        "CreateMarketingCampaignUseCase": P.DOCUMENTOS_CAMPANA_CREAR,
        "UpdateMarketingCampaignUseCase": P.DOCUMENTOS_CAMPANA_EDITAR,
        "ChangeMarketingCampaignStatusUseCase": P.DOCUMENTOS_CAMPANA_ACTIVAR,
    },
    "notification_management_use_cases": {
        name: NG for name in (
            "CreateNotificationAccountUseCase", "UpdateNotificationAccountUseCase",
            "ChangeNotificationAccountStatusUseCase", "CreateNotificationTemplateUseCase",
            "UpdateNotificationTemplateUseCase", "ChangeNotificationTemplateStatusUseCase",
            "CreateNotificationRouteUseCase", "ChangeNotificationRouteStatusUseCase")
    },
    "offline_management_use_cases": {
        name: P.OFFLINE_GESTIONAR for name in (
            "CreateCacheExpirationPolicyUseCase", "UpdateCacheExpirationPolicyUseCase",
            "ChangeCacheExpirationPolicyStatusUseCase")
    },
    "print_route_use_cases": {
        name: P.DISPOSITIVOS_RUTAS_GESTIONAR for name in (
            "CreatePrintRouteUseCase", "UpdatePrintRouteUseCase", "ChangePrintRouteStatusUseCase")
    },
    "workstation_use_cases": {
        "RegisterWorkstationUseCase": P.ESTACION_CREAR,
        "UpdateWorkstationUseCase": P.ESTACION_EDITAR,
        "ChangeWorkstationStatusUseCase": {
            "ACTIVATE": P.ESTACION_EDITAR, "DEACTIVATE": P.ESTACION_EDITAR,
            "ENTER_MAINTENANCE": P.ESTACION_EDITAR, "EXIT_MAINTENANCE": P.ESTACION_EDITAR,
            "UNBLOCK": P.ESTACION_EDITAR, "BLOCK": P.ESTACION_BLOQUEAR,
            "RETIRE": P.ESTACION_RETIRAR},
    },
}
#: Clases con `execute` que NO escriben (sólo vista previa en un directorio temporal).
NOT_WRITES = {"PreviewLogoUseCase"}

#: Argumentos posicionales extra del constructor (almacenes, impresoras).
_EXTRA_CTOR_ARGS = {
    "SetIntegrationInstanceCredentialUseCase": 1, "TestIntegrationConnectionUseCase": 1,
    "ImportDisplayMediaUseCase": 1, "ImportLogoUseCase": 1, "SetDeviceWindowsPrinterUseCase": 1,
}


def _cases():
    for module, classes in EXPECTED.items():
        for name, expected in classes.items():
            if isinstance(expected, dict):
                for action, permission in expected.items():
                    yield pytest.param(module, name, action, permission, id=f"{name}[{action}]")
            else:
                yield pytest.param(module, name, None, expected, id=name)


_CLAIMED_ACTOR_PARAMS = {"approver_user_id", "requested_by_user_id", "created_by_user_id",
                         "assigned_by_user_id", "actor_user_id"}


@pytest.mark.parametrize(("module", "name", "action", "permission"), list(_cases()))
def test_use_case_denies_in_backend_with_the_screen_permission_and_touches_nothing(
        module, name, action, permission):
    checker, authorization = _denying_authorizer()
    cls = getattr(importlib.import_module(_PKG + module), name)
    connection, extra = _Trap(), [_Trap() for _ in range(_EXTRA_CTOR_ARGS.get(name, 0))]
    use_case = cls(connection, *extra, authorization=authorization)
    connection.calls.clear()
    for trap in extra:
        trap.calls.clear()
    kwargs = _execute_kwargs(cls, action)

    with pytest.raises(ConfigurationPermissionDeniedError):
        use_case.execute(**kwargs)

    assert checker.asked == [permission]
    assert connection.calls == []
    assert all(trap.calls == [] for trap in extra)


def _execute_kwargs(cls, action, claimed=SESSION_USER):
    kwargs = {}
    for param in inspect.signature(cls.execute).parameters.values():
        if param.name == "self":
            continue
        if param.name == "action":
            kwargs["action"] = action
        elif param.name in _CLAIMED_ACTOR_PARAMS:
            kwargs[param.name] = claimed
        elif param.default is inspect.Parameter.empty:
            kwargs[param.name] = "x"
    return kwargs


def test_expected_table_covers_every_write_use_case():
    """Si alguien agrega un caso de uso a Configuración, entra a esta tabla."""
    import pkgutil
    import backend.application.use_cases.configuracion as pkg

    found = set()
    for info in pkgutil.iter_modules(pkg.__path__):
        module = importlib.import_module(_PKG + info.name)
        for name, obj in vars(module).items():
            if (inspect.isclass(obj) and obj.__module__ == module.__name__
                    and callable(getattr(obj, "execute", None))):
                found.add(name)
    declared = {name for classes in EXPECTED.values() for name in classes}
    assert found - NOT_WRITES == declared


def test_action_tables_cover_every_enum_member():
    """Cada miembro del enum de estado tiene su permiso: ninguna acción queda
    sin autorizar por omisión."""
    from backend.application.use_cases.configuracion import (
        customer_display_advertising_use_cases as cd,
        device_management_use_cases as dm,
        document_template_use_cases as dt,
        integration_management_use_cases as im,
        workstation_use_cases as ws,
    )
    pairs = [
        (cd.ContentCampaignStatusAction, cd.CONTENT_CAMPAIGN_STATUS_PERMISSIONS),
        (dm.DeviceStatusAction, dm.DEVICE_STATUS_PERMISSIONS),
        (dt.TemplateVersionAction, dt.TEMPLATE_VERSION_STATUS_PERMISSIONS),
        (im.IntegrationDefinitionStatusAction, im.INTEGRATION_DEFINITION_STATUS_PERMISSIONS),
        (im.IntegrationInstanceStatusAction, im.INTEGRATION_INSTANCE_STATUS_PERMISSIONS),
        (ws.WorkstationStatusAction, ws.WORKSTATION_STATUS_PERMISSIONS),
    ]
    for enum_cls, table in pairs:
        assert set(table) == set(enum_cls), enum_cls.__name__


@pytest.mark.parametrize(("module", "name", "param"), [
    ("feature_flag_change_request_use_cases", "ApproveFeatureFlagChangeRequestUseCase", "approver_user_id"),
    ("feature_flag_management_use_cases", "RequestFeatureFlagChangeUseCase", "requested_by_user_id"),
    ("document_template_use_cases", "CreateDocumentTemplateUseCase", "created_by_user_id"),
    ("device_assignment_use_cases", "AssignDeviceUseCase", "assigned_by_user_id"),
    ("device_test_use_cases", "TestDeviceUseCase", "actor_user_id"),
])
def test_claimed_actor_must_be_session_actor_even_with_permission(module, name, param):
    """Con el permiso concedido, declarar OTRO actor se niega (no se puede
    aprobar «en nombre de» otro usuario)."""
    session = SimpleNamespace(user_id=SESSION_USER, is_active=True, tiene_permiso=lambda code: True)
    authorization = ConfiguracionActionAuthorizer.for_session(session)
    cls = getattr(importlib.import_module(_PKG + module), name)
    connection = _Trap()
    use_case = cls(connection, authorization=authorization)
    connection.calls.clear()
    kwargs = _execute_kwargs(cls, None, claimed="otro-usuario")

    with pytest.raises(ConfigurationPermissionDeniedError, match="no es el de la sesión"):
        use_case.execute(**kwargs)
    assert connection.calls == []


def test_unknown_action_is_denied_without_touching_anything():
    from backend.application.use_cases.configuracion.device_management_use_cases import (
        ChangeDeviceStatusUseCase,
    )
    authorization = ConfiguracionActionAuthorizer.permissive_for_tests()
    connection = _Trap()
    use_case = ChangeDeviceStatusUseCase(connection, authorization=authorization)
    connection.calls.clear()
    with pytest.raises(ConfigurationPermissionDeniedError, match="sin permiso definido"):
        use_case.execute(device_id="d-1", action="DESTRUIR")
    assert connection.calls == []


# ── fuera del paquete: anclaje de sucursal y diseñador de tickets ────────────

class _ReanchorUow:
    """UoW de re-anclaje que registra todo: sólo debe auditar el rechazo."""

    def __init__(self, calls: list) -> None:
        self._calls = calls
        self.installation_branch = SimpleNamespace(
            get=lambda: None, set=lambda *a, **k: calls.append("set"))
        self.audit_log = SimpleNamespace(record=lambda **k: calls.append(("audit", k["details"])))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _reanchor_uc(authorization):
    from backend.application.use_cases.set_installation_branch_use_case import (
        SetInstallationBranchUseCase,
    )
    calls: list = []
    return calls, SetInstallationBranchUseCase(lambda: _ReanchorUow(calls),
                                               authorization=authorization)


def test_set_installation_branch_denied_without_estacion_reanclar():
    """Integración ronda 1: con SDLC-ARQ-TERM-002 el permiso es
    `CONFIGURACION.estacion.reanclar` (antes `EMPRESA_EDITAR`, PERM-001)."""
    from backend.application.commands.settings_commands import SetInstallationBranchCommand
    from backend.shared.ids import new_uuid
    checker = _RecordingDenyChecker()
    calls, use_case = _reanchor_uc(ConfiguracionAuthorizationPolicy(checker))
    with pytest.raises(ConfigurationPermissionDeniedError):
        use_case.execute(SetInstallationBranchCommand(
            operation_id="op-1", branch_id=new_uuid(), user_name=SESSION_USER))
    assert checker.asked == [P.ESTACION_REANCLAR]
    assert "set" not in calls
    assert [c[0] for c in calls] == ["audit"] and "PERMISSION_DENIED" in calls[0][1]


def test_set_installation_branch_rejects_a_foreign_declared_actor():
    from backend.application.commands.settings_commands import SetInstallationBranchCommand
    from backend.application.configuracion.authorization import SessionPermissionChecker
    from backend.shared.ids import new_uuid
    session = SimpleNamespace(user_id=SESSION_USER, is_active=True, tiene_permiso=lambda code: True)
    calls, use_case = _reanchor_uc(
        ConfiguracionAuthorizationPolicy(SessionPermissionChecker(session)))
    with pytest.raises(ConfigurationPermissionDeniedError):
        use_case.execute(SetInstallationBranchCommand(
            operation_id="op-1", branch_id=new_uuid(), user_name="otro-usuario"))
    assert "set" not in calls


@pytest.mark.parametrize(("method", "kwargs", "permission"), [
    ("print_test", dict(layout_json="{}", document_type="SALE_TICKET", branch_id=None),
     P.DOCUMENTOS_PLANTILLA_EDITAR),
    ("import_logo", dict(source_path="x.png", remove_background=False, actor_user_id=SESSION_USER),
     P.EMPRESA_EDITAR),
    ("set_company_logo", dict(asset_id=None), P.EMPRESA_EDITAR),
    ("set_branch_logo", dict(branch_id="b-1", asset_id=None, actor_user_id=SESSION_USER),
     P.EMPRESA_EDITAR),
])
def test_ticket_designer_writes_are_denied_without_permission(method, kwargs, permission):
    from backend.application.use_cases.configuracion.ticket_designer_service import (
        TicketDesignerService,
    )
    checker, authorization = _denying_authorizer()
    connection = _Trap()
    service = TicketDesignerService(connection, authorization=authorization)
    with pytest.raises(ConfigurationPermissionDeniedError):
        getattr(service, method)(**kwargs)
    assert checker.asked == [permission]
    assert connection.calls == []
