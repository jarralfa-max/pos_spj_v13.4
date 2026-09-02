"""SET-1 — ConfiguracionPresenter permission enforcement + audit trail.
Pure presenter-level tests (no PyQt, no DB): stub use cases stand in for
the real backend ones so this only exercises the presenter's own
authorization/audit wiring. Widget-level coverage stays in
`tests/unit/test_configuracion_ui_workspace.py`; use-case/domain coverage
stays in `tests/integration/configuracion/`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.application.configuracion.authorization import (
    AllowAllConfiguracionPermissionCheckerForTests,
    ConfiguracionAuthorizationPolicy,
    DenyAllConfiguracionPermissionCheckerForTests,
)
from backend.application.configuracion.permissions import ConfiguracionPermissions
from frontend.desktop.modules.configuracion.configuracion_presenter import ConfiguracionPresenter


@dataclass
class _Device:
    code: str = "PRN-01"
    status: object = field(default_factory=lambda: type("S", (), {"value": "BLOCKED"})())


class _RecordingUseCase:
    def __init__(self, result=None):
        self.calls = []
        self._result = result

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        return self._result


class _RecordingAuditLog:
    def __init__(self):
        self.records = []

    def record(self, **kwargs):
        self.records.append(kwargs)


class _Session:
    def __init__(self, user_id="user-1"):
        self.user_id = user_id


@dataclass
class _Workstation:
    code: str = "POS-01"
    status: object = field(default_factory=lambda: type("S", (), {"value": "BLOCKED"})())


@dataclass
class _Assignment:
    id: str = "a1"
    workstation_id: str = "w1"
    device_id: str = "d1"
    role: object = field(default_factory=lambda: type("R", (), {"value": "PRIMARY_RECEIPT_PRINTER"})())


@dataclass
class _PrintRoute:
    id: str = "r1"
    document_type: str = "SALE_TICKET"
    primary_device_id: str = "d1"
    fallback_device_ids: tuple = ()
    active: bool = True


@dataclass
class _DocumentTemplate:
    id: str = "tpl1"
    name: str = "Ticket de venta"
    active: bool = True


@dataclass
class _MarketingCampaign:
    id: str = "c1"
    code: str = "goal_near"
    active: bool = True


def _presenter(*, policy=None, audit_log=None, **use_cases):
    class _Queries:
        def get_device(self, device_id):
            return None

        def get_workstation(self, workstation_id):
            return None

    return ConfiguracionPresenter(
        _Queries(), session_context=_Session(), authorization=policy,
        audit_log_repository=audit_log, **use_cases,
    )


class TestNoAuthorizationWiredIsBackwardCompatible:
    """A presenter built without `authorization` (every pre-SET-1 test in
    this repo) must keep behaving exactly as before — enforcement is
    opt-in via the new constructor param, not a breaking default."""

    def test_command_proceeds_without_a_policy(self):
        uc = _RecordingUseCase(result=_Device())
        presenter = _presenter(register_device_uc=uc)
        ok, _ = presenter.register_device(branch_id="b1", profile_id="p1", code="PRN-01")
        assert ok is True
        assert len(uc.calls) == 1


class TestPermissionDenialBlocksTheUseCase:
    def test_register_device_denied(self):
        policy = ConfiguracionAuthorizationPolicy(DenyAllConfiguracionPermissionCheckerForTests())
        uc = _RecordingUseCase(result=_Device())
        presenter = _presenter(policy=policy, register_device_uc=uc)
        ok, message = presenter.register_device(branch_id="b1", profile_id="p1", code="PRN-01")
        assert ok is False
        assert ConfiguracionPermissions.DISPOSITIVOS_CREAR in message or "permiso" in message.lower()
        assert uc.calls == []

    def test_save_company_profile_denied(self):
        policy = ConfiguracionAuthorizationPolicy(DenyAllConfiguracionPermissionCheckerForTests())
        uc = _RecordingUseCase(result=type("C", (), {"legal_name": "SPJ"})())
        presenter = _presenter(policy=policy, save_company_profile_uc=uc)
        ok, _ = presenter.save_company_profile(legal_name="SPJ")
        assert ok is False
        assert uc.calls == []

    def test_change_device_status_denied_uses_action_specific_permission(self):
        # BLOCK requires DISPOSITIVOS.deshabilitar; a checker that only
        # grants DISPOSITIVOS.editar must still deny it.
        class _EditOnlyChecker:
            def has_permission(self, user_id, code):
                return code == ConfiguracionPermissions.DISPOSITIVOS_EDITAR

        policy = ConfiguracionAuthorizationPolicy(_EditOnlyChecker())
        uc = _RecordingUseCase(result=_Device())
        presenter = _presenter(policy=policy, change_device_status_uc=uc)
        ok, _ = presenter.change_device_status(device_id="d1", action="BLOCK")
        assert ok is False
        assert uc.calls == []
        # But ACTIVATE (gated by DISPOSITIVOS.editar) is allowed.
        ok, _ = presenter.change_device_status(device_id="d1", action="ACTIVATE")
        assert ok is True
        assert len(uc.calls) == 1

    def test_change_workstation_status_denied_uses_action_specific_permission(self):
        # RETIRE requires CONFIGURACION.estacion.retirar; a checker that
        # only grants estacion.editar must still deny it.
        class _EditOnlyChecker:
            def has_permission(self, user_id, code):
                return code == ConfiguracionPermissions.ESTACION_EDITAR

        policy = ConfiguracionAuthorizationPolicy(_EditOnlyChecker())
        uc = _RecordingUseCase(result=_Workstation())
        presenter = _presenter(policy=policy, change_workstation_status_uc=uc)
        ok, _ = presenter.change_workstation_status(workstation_id="w1", action="RETIRE")
        assert ok is False
        assert uc.calls == []
        ok, _ = presenter.change_workstation_status(workstation_id="w1", action="ACTIVATE")
        assert ok is True
        assert len(uc.calls) == 1

    def test_assign_device_denied(self):
        policy = ConfiguracionAuthorizationPolicy(DenyAllConfiguracionPermissionCheckerForTests())
        uc = _RecordingUseCase(result=_Assignment())
        presenter = _presenter(policy=policy, assign_device_uc=uc)
        ok, _ = presenter.assign_device(workstation_id="w1", device_id="d1", role="SCALE")
        assert ok is False
        assert uc.calls == []

    def test_unassign_device_denied(self):
        policy = ConfiguracionAuthorizationPolicy(DenyAllConfiguracionPermissionCheckerForTests())
        uc = _RecordingUseCase(result=_Assignment())
        presenter = _presenter(policy=policy, unassign_device_uc=uc)
        ok, _ = presenter.unassign_device(assignment_id="a1")
        assert ok is False
        assert uc.calls == []

    def test_create_print_route_denied(self):
        policy = ConfiguracionAuthorizationPolicy(DenyAllConfiguracionPermissionCheckerForTests())
        uc = _RecordingUseCase(result=_PrintRoute())
        presenter = _presenter(policy=policy, create_print_route_uc=uc)
        ok, _ = presenter.create_print_route(document_type="SALE_TICKET", primary_device_id="d1")
        assert ok is False
        assert uc.calls == []

    def test_update_print_route_denied(self):
        policy = ConfiguracionAuthorizationPolicy(DenyAllConfiguracionPermissionCheckerForTests())
        uc = _RecordingUseCase(result=_PrintRoute())
        presenter = _presenter(policy=policy, update_print_route_uc=uc)
        ok, _ = presenter.update_print_route(route_id="r1", primary_device_id="d1")
        assert ok is False
        assert uc.calls == []

    def test_change_print_route_status_denied(self):
        policy = ConfiguracionAuthorizationPolicy(DenyAllConfiguracionPermissionCheckerForTests())
        uc = _RecordingUseCase(result=_PrintRoute())
        presenter = _presenter(policy=policy, change_print_route_status_uc=uc)
        ok, _ = presenter.change_print_route_status(route_id="r1", action="ACTIVATE")
        assert ok is False
        assert uc.calls == []

    def test_update_document_template_denied(self):
        policy = ConfiguracionAuthorizationPolicy(DenyAllConfiguracionPermissionCheckerForTests())
        uc = _RecordingUseCase(result=_DocumentTemplate())
        presenter = _presenter(policy=policy, update_document_template_uc=uc)
        ok, _ = presenter.update_document_template(template_id="tpl1", name="X", module="ventas")
        assert ok is False
        assert uc.calls == []

    def test_change_document_template_status_denied(self):
        policy = ConfiguracionAuthorizationPolicy(DenyAllConfiguracionPermissionCheckerForTests())
        uc = _RecordingUseCase(result=_DocumentTemplate())
        presenter = _presenter(policy=policy, change_document_template_status_uc=uc)
        ok, _ = presenter.change_document_template_status(template_id="tpl1", action="DEACTIVATE")
        assert ok is False
        assert uc.calls == []

    def test_create_marketing_campaign_denied(self):
        policy = ConfiguracionAuthorizationPolicy(DenyAllConfiguracionPermissionCheckerForTests())
        uc = _RecordingUseCase(result=_MarketingCampaign())
        presenter = _presenter(policy=policy, create_marketing_campaign_uc=uc)
        ok, _ = presenter.create_marketing_campaign(code="goal_near", category="FOMO", message_template="X")
        assert ok is False
        assert uc.calls == []

    def test_update_marketing_campaign_denied(self):
        policy = ConfiguracionAuthorizationPolicy(DenyAllConfiguracionPermissionCheckerForTests())
        uc = _RecordingUseCase(result=_MarketingCampaign())
        presenter = _presenter(policy=policy, update_marketing_campaign_uc=uc)
        ok, _ = presenter.update_marketing_campaign(campaign_id="c1", message_template="X")
        assert ok is False
        assert uc.calls == []

    def test_change_marketing_campaign_status_denied(self):
        policy = ConfiguracionAuthorizationPolicy(DenyAllConfiguracionPermissionCheckerForTests())
        uc = _RecordingUseCase(result=_MarketingCampaign())
        presenter = _presenter(policy=policy, change_marketing_campaign_status_uc=uc)
        ok, _ = presenter.change_marketing_campaign_status(campaign_id="c1", action="DEACTIVATE")
        assert ok is False
        assert uc.calls == []


class TestPermissionGrantAllowsTheUseCase:
    def test_register_device_allowed(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        uc = _RecordingUseCase(result=_Device())
        presenter = _presenter(policy=policy, register_device_uc=uc)
        ok, _ = presenter.register_device(branch_id="b1", profile_id="p1", code="PRN-01")
        assert ok is True
        assert len(uc.calls) == 1

    def test_assign_device_allowed(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        uc = _RecordingUseCase(result=_Assignment())
        presenter = _presenter(policy=policy, assign_device_uc=uc)
        ok, _ = presenter.assign_device(workstation_id="w1", device_id="d1", role="SCALE")
        assert ok is True
        assert len(uc.calls) == 1
        assert uc.calls[0]["assigned_by_user_id"] == "user-1"

    def test_create_print_route_allowed(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        uc = _RecordingUseCase(result=_PrintRoute())
        presenter = _presenter(policy=policy, create_print_route_uc=uc)
        ok, _ = presenter.create_print_route(document_type="SALE_TICKET", primary_device_id="d1")
        assert ok is True
        assert len(uc.calls) == 1

    def test_update_document_template_allowed(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        uc = _RecordingUseCase(result=_DocumentTemplate())
        presenter = _presenter(policy=policy, update_document_template_uc=uc)
        ok, _ = presenter.update_document_template(template_id="tpl1", name="X", module="ventas")
        assert ok is True
        assert len(uc.calls) == 1

    def test_create_marketing_campaign_allowed(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        uc = _RecordingUseCase(result=_MarketingCampaign())
        presenter = _presenter(policy=policy, create_marketing_campaign_uc=uc)
        ok, _ = presenter.create_marketing_campaign(code="goal_near", category="FOMO", message_template="X")
        assert ok is True
        assert len(uc.calls) == 1

    def test_update_marketing_campaign_allowed(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        uc = _RecordingUseCase(result=_MarketingCampaign())
        presenter = _presenter(policy=policy, update_marketing_campaign_uc=uc)
        ok, _ = presenter.update_marketing_campaign(campaign_id="c1", message_template="X")
        assert ok is True
        assert len(uc.calls) == 1


class TestAuditTrailForCriticalTransitions:
    def test_device_block_is_audited(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        audit_log = _RecordingAuditLog()
        uc = _RecordingUseCase(result=_Device())
        presenter = _presenter(policy=policy, audit_log=audit_log, change_device_status_uc=uc)
        ok, _ = presenter.change_device_status(device_id="d1", action="BLOCK", reason="manipulación")
        assert ok is True
        assert len(audit_log.records) == 1
        assert audit_log.records[0]["entity_type"] == "device"
        assert audit_log.records[0]["action"] == "BLOCK"

    def test_device_rename_is_not_audited(self):
        # update_device is permission-gated but not on the audit checklist
        # (routine edit, not a critical state transition).
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        audit_log = _RecordingAuditLog()
        uc = _RecordingUseCase(result=_Device())
        presenter = _presenter(policy=policy, audit_log=audit_log, update_device_uc=uc)
        ok, _ = presenter.update_device(device_id="d1", name="Nueva", notes="")
        assert ok is True
        assert audit_log.records == []

    def test_audit_failure_does_not_break_the_command(self):
        class _BrokenAuditLog:
            def record(self, **kwargs):
                raise RuntimeError("boom")

        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        uc = _RecordingUseCase(result=_Device())
        presenter = _presenter(policy=policy, audit_log=_BrokenAuditLog(), change_device_status_uc=uc)
        ok, _ = presenter.change_device_status(device_id="d1", action="RETIRE")
        assert ok is True

    def test_workstation_retire_is_audited(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        audit_log = _RecordingAuditLog()
        uc = _RecordingUseCase(result=_Workstation())
        presenter = _presenter(policy=policy, audit_log=audit_log, change_workstation_status_uc=uc)
        ok, _ = presenter.change_workstation_status(workstation_id="w1", action="RETIRE")
        assert ok is True
        assert len(audit_log.records) == 1
        assert audit_log.records[0]["entity_type"] == "workstation"
        assert audit_log.records[0]["action"] == "RETIRE"

    def test_workstation_maintenance_is_not_audited(self):
        # ENTER_MAINTENANCE is permission-gated but not a critical
        # block/retire-style transition — not on the audit checklist.
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        audit_log = _RecordingAuditLog()
        uc = _RecordingUseCase(result=_Workstation())
        presenter = _presenter(policy=policy, audit_log=audit_log, change_workstation_status_uc=uc)
        ok, _ = presenter.change_workstation_status(workstation_id="w1", action="ENTER_MAINTENANCE")
        assert ok is True
        assert audit_log.records == []

    def test_assign_device_is_always_audited(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        audit_log = _RecordingAuditLog()
        uc = _RecordingUseCase(result=_Assignment())
        presenter = _presenter(policy=policy, audit_log=audit_log, assign_device_uc=uc)
        ok, _ = presenter.assign_device(workstation_id="w1", device_id="d1", role="SCALE")
        assert ok is True
        assert len(audit_log.records) == 1
        assert audit_log.records[0]["entity_type"] == "workstation_device_assignment"
        assert audit_log.records[0]["action"] == "ASSIGN"

    def test_unassign_device_is_always_audited(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        audit_log = _RecordingAuditLog()
        uc = _RecordingUseCase(result=_Assignment())
        presenter = _presenter(policy=policy, audit_log=audit_log, unassign_device_uc=uc)
        ok, _ = presenter.unassign_device(assignment_id="a1")
        assert ok is True
        assert len(audit_log.records) == 1
        assert audit_log.records[0]["entity_type"] == "workstation_device_assignment"
        assert audit_log.records[0]["action"] == "UNASSIGN"

    def test_create_print_route_is_always_audited(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        audit_log = _RecordingAuditLog()
        uc = _RecordingUseCase(result=_PrintRoute())
        presenter = _presenter(policy=policy, audit_log=audit_log, create_print_route_uc=uc)
        ok, _ = presenter.create_print_route(document_type="SALE_TICKET", primary_device_id="d1")
        assert ok is True
        assert len(audit_log.records) == 1
        assert audit_log.records[0]["entity_type"] == "print_route"
        assert audit_log.records[0]["action"] == "CREATE"

    def test_change_print_route_status_is_always_audited(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        audit_log = _RecordingAuditLog()
        uc = _RecordingUseCase(result=_PrintRoute(active=False))
        presenter = _presenter(policy=policy, audit_log=audit_log, change_print_route_status_uc=uc)
        ok, _ = presenter.change_print_route_status(route_id="r1", action="DEACTIVATE")
        assert ok is True
        assert len(audit_log.records) == 1
        assert audit_log.records[0]["entity_type"] == "print_route"
        assert audit_log.records[0]["action"] == "DEACTIVATE"

    def test_change_document_template_status_is_always_audited(self):
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        audit_log = _RecordingAuditLog()
        uc = _RecordingUseCase(result=_DocumentTemplate(active=False))
        presenter = _presenter(policy=policy, audit_log=audit_log, change_document_template_status_uc=uc)
        ok, _ = presenter.change_document_template_status(template_id="tpl1", action="DEACTIVATE")
        assert ok is True
        assert len(audit_log.records) == 1
        assert audit_log.records[0]["entity_type"] == "document_template"
        assert audit_log.records[0]["action"] == "DEACTIVATE"

    def test_update_document_template_is_not_audited(self):
        # Renaming/redescribing a template family is a routine edit, same
        # boundary as Device.rename()/Workstation.update_details().
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        audit_log = _RecordingAuditLog()
        uc = _RecordingUseCase(result=_DocumentTemplate())
        presenter = _presenter(policy=policy, audit_log=audit_log, update_document_template_uc=uc)
        ok, _ = presenter.update_document_template(template_id="tpl1", name="X", module="ventas")
        assert ok is True
        assert audit_log.records == []

    def test_change_marketing_campaign_status_is_always_audited(self):
        # A campaign starting/stopping to print on live tickets is a
        # critical transition, same weight as the template family toggle.
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        audit_log = _RecordingAuditLog()
        uc = _RecordingUseCase(result=_MarketingCampaign(active=False))
        presenter = _presenter(policy=policy, audit_log=audit_log, change_marketing_campaign_status_uc=uc)
        ok, _ = presenter.change_marketing_campaign_status(campaign_id="c1", action="DEACTIVATE")
        assert ok is True
        assert len(audit_log.records) == 1
        assert audit_log.records[0]["entity_type"] == "marketing_campaign"
        assert audit_log.records[0]["action"] == "DEACTIVATE"

    def test_create_and_update_marketing_campaign_are_not_audited(self):
        # Routine content edits, same boundary as template rename.
        policy = ConfiguracionAuthorizationPolicy(AllowAllConfiguracionPermissionCheckerForTests())
        audit_log = _RecordingAuditLog()
        create_uc = _RecordingUseCase(result=_MarketingCampaign())
        update_uc = _RecordingUseCase(result=_MarketingCampaign())
        presenter = _presenter(
            policy=policy, audit_log=audit_log, create_marketing_campaign_uc=create_uc,
            update_marketing_campaign_uc=update_uc,
        )
        presenter.create_marketing_campaign(code="goal_near", category="FOMO", message_template="X")
        presenter.update_marketing_campaign(campaign_id="c1", message_template="X")
        assert audit_log.records == []
