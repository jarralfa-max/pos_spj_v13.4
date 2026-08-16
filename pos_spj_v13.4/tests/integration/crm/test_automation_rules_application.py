"""CRM Automation Rules (§56, CRM-26) — rule CRUD + evaluation entry
points, including the real wiring into CreateLeadUseCase/
MoveOpportunityStageUseCase/CreateServiceCaseUseCase."""

from __future__ import annotations

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.use_cases.automation_use_cases import (
    SYSTEM_AUTOMATION_ACTOR,
    ActivateAutomationRuleUseCase,
    CreateAutomationRuleUseCase,
    DeactivateAutomationRuleUseCase,
    EvaluateEventTriggerUseCase,
)
from backend.application.crm.use_cases.lead_use_cases import CreateLeadUseCase
from backend.application.crm.use_cases.opportunity_use_cases import (
    AssignOpportunityUseCase,
    CreateOpportunityUseCase,
    MoveOpportunityStageUseCase,
)
from backend.domain.crm.enums import CRMAutomationExecutionStatus, CRMAutomationTrigger
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork

_ACTOR = "user-automation-admin"


class _AllowAllForActor:
    def __init__(self, user_id: str) -> None:
        self._user_id = user_id

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return user_id == self._user_id


def _admin_policy() -> CRMAuthorizationPolicy:
    return CRMAuthorizationPolicy(_AllowAllForActor(_ACTOR))


def _create_rule(conn, *, trigger: str, action: str, trigger_config=None, action_config=None,
                 op_suffix="rule"):
    result = CreateAutomationRuleUseCase(_admin_policy()).execute(
        conn, actor_user_id=_ACTOR, name=f"Regla {op_suffix}", trigger_type=trigger,
        action_type=action, trigger_config=trigger_config, action_config=action_config,
        operation_id=f"op-{op_suffix}")
    assert result.success, result.message
    return result.entity_id


class TestAutomationRuleCRUD:
    def test_create_rule_succeeds(self, crm_conn):
        rule_id = _create_rule(
            crm_conn, trigger=CRMAutomationTrigger.LEAD_CREATED.value,
            action="CREATE_TASK", action_config={"title": "Llamar al lead"})
        with CRMUnitOfWork(crm_conn) as uow:
            rule = uow.automation_rules.get(rule_id)
        assert rule is not None
        assert rule.active is True
        assert rule.action_config["title"] == "Llamar al lead"

    def test_create_rule_denied_without_permission(self, crm_conn):
        result = CreateAutomationRuleUseCase(CRMAuthorizationPolicy()).execute(
            crm_conn, actor_user_id=_ACTOR, name="X",
            trigger_type=CRMAutomationTrigger.LEAD_CREATED.value, action_type="CREATE_TASK",
            operation_id="op-denied")
        assert not result.success
        assert result.error_code == "PERMISSION_DENIED"

    def test_deactivate_then_reactivate_rule(self, crm_conn):
        rule_id = _create_rule(crm_conn, trigger=CRMAutomationTrigger.LEAD_CREATED.value,
                               action="CREATE_TASK", op_suffix="toggle")
        DeactivateAutomationRuleUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, rule_id=rule_id, operation_id="op-deact")
        with CRMUnitOfWork(crm_conn) as uow:
            assert uow.automation_rules.get(rule_id).active is False
        ActivateAutomationRuleUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, rule_id=rule_id, operation_id="op-react")
        with CRMUnitOfWork(crm_conn) as uow:
            assert uow.automation_rules.get(rule_id).active is True


class TestEvaluateEventTriggerCreateTask:
    def test_active_rule_creates_task_and_logs_success(self, crm_conn):
        _create_rule(
            crm_conn, trigger=CRMAutomationTrigger.LEAD_CREATED.value, action="CREATE_TASK",
            action_config={"title": "Seguimiento inicial", "due_in_hours": 2})
        result = CreateLeadUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, display_name="Lead Automático",
            operation_id="op-lead-1")
        assert result.success, result.message
        lead_id = result.entity_id

        with CRMUnitOfWork(crm_conn) as uow:
            tasks = [t for t in uow.tasks.list_open_for_related("LEAD", lead_id)] \
                if hasattr(uow.tasks, "list_open_for_related") else None
            executions = uow.automation_executions.list_recent()

        matching = [e for e in executions if e.target_entity_id == lead_id]
        assert len(matching) == 1
        assert matching[0].status == CRMAutomationExecutionStatus.SUCCEEDED
        assert matching[0].created_entity_id  # a real task id was created

    def test_inactive_rule_does_not_fire(self, crm_conn):
        rule_id = _create_rule(crm_conn, trigger=CRMAutomationTrigger.LEAD_CREATED.value,
                               action="CREATE_TASK", op_suffix="inactive")
        DeactivateAutomationRuleUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, rule_id=rule_id, operation_id="op-deact-2")
        result = CreateLeadUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, display_name="Lead Sin Regla",
            operation_id="op-lead-2")
        assert result.success
        with CRMUnitOfWork(crm_conn) as uow:
            executions = uow.automation_executions.list_recent()
        assert not [e for e in executions if e.target_entity_id == result.entity_id]

    def test_unsupported_target_entity_type_is_skipped_not_failed(self, crm_conn):
        rule_id = _create_rule(crm_conn, trigger=CRMAutomationTrigger.CUSTOMER_INACTIVE.value,
                               action="CREATE_TASK", op_suffix="badtarget")
        executions = EvaluateEventTriggerUseCase().execute(
            crm_conn, trigger=CRMAutomationTrigger.CUSTOMER_INACTIVE, target_entity_type="CUSTOMER",
            target_entity_id="cust-1", operation_id="op-skip")
        assert len(executions) == 1
        assert executions[0].status == CRMAutomationExecutionStatus.SKIPPED
        assert executions[0].rule_id == rule_id


class TestEvaluateEventTriggerAssignOwner:
    def test_opportunity_stage_change_fires_assign_owner_rule(self, crm_conn):
        _create_rule(
            crm_conn, trigger=CRMAutomationTrigger.OPPORTUNITY_STAGE_CHANGED.value,
            action="ASSIGN_OWNER", action_config={"assignee_user_id": "user-vendedor-2"},
            op_suffix="assign")
        create_result = CreateOpportunityUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, customer_id="cust-1", name="Oportunidad Test",
            operation_id="op-opp-1")
        assert create_result.success, create_result.message
        opp_id = create_result.entity_id
        with CRMUnitOfWork(crm_conn) as uow:
            stages = uow.stage_definitions.list_active_ordered()
        to_stage = stages[1] if len(stages) > 1 else stages[0]

        move_result = MoveOpportunityStageUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, opportunity_id=opp_id, to_stage_id=to_stage.id,
            operation_id="op-move-1", override=True, reason="avance de prueba")
        assert move_result.success, move_result.message

        with CRMUnitOfWork(crm_conn) as uow:
            opportunity = uow.opportunities.get(opp_id)
            executions = uow.automation_executions.list_recent()
        assert opportunity.owner_user_id == "user-vendedor-2"
        matching = [e for e in executions if e.target_entity_id == opp_id]
        assert matching and matching[0].status == CRMAutomationExecutionStatus.SUCCEEDED


class TestEvaluateEventTriggerEscalateCase:
    def test_case_created_fires_escalate_case_rule(self, crm_and_service_conn):
        conn = crm_and_service_conn
        _create_rule(
            conn, trigger=CRMAutomationTrigger.CASE_CREATED.value, action="ESCALATE_CASE",
            action_config={"escalated_to_user_id": "user-supervisor-1", "reason": "CRITICAL_CASE"},
            op_suffix="escalate")
        from backend.application.customer_service.use_cases.service_case_use_cases import (
            CreateServiceCaseUseCase,
        )
        result = CreateServiceCaseUseCase(_admin_policy()).execute(
            conn, actor_user_id=_ACTOR, customer_id="cust-1", case_type="QUESTION",
            subject="Caso de prueba", operation_id="op-case-1")
        assert result.success, result.message
        case_id = result.entity_id

        with CRMUnitOfWork(conn) as uow:
            executions = uow.automation_executions.list_recent()
        matching = [e for e in executions if e.target_entity_id == case_id]
        assert matching, "no automation execution logged for the new case"
        assert matching[0].status == CRMAutomationExecutionStatus.SUCCEEDED
        assert matching[0].result_detail == "Caso escalado"
