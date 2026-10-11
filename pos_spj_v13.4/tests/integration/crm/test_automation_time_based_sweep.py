"""EvaluateTimeBasedAutomationTriggersUseCase — LEAD_IDLE (CRM-26, §56).

Desde CRM-43 el barrido lo corre el ciclo de fondo de la aplicación
(``run_crm_background_cycle``) y cubre los siete disparadores por tiempo; esas
pruebas, con la base completa, están en
tests/integration/crm43/test_crm43_automation_background.py. Aquí queda el
caso base sobre el esquema CRM solo, más la garantía de no repetir."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.use_cases.automation_use_cases import (
    CreateAutomationRuleUseCase,
    EvaluateTimeBasedAutomationTriggersUseCase,
)
from backend.application.crm.use_cases.lead_use_cases import CreateLeadUseCase
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


class TestLeadIdleSweep:
    def test_idle_lead_fires_rule(self, crm_conn):
        CreateAutomationRuleUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, name="Leads inactivos",
            trigger_type=CRMAutomationTrigger.LEAD_IDLE.value, action_type="CREATE_TASK",
            trigger_config={"idle_days": 3}, action_config={"title": "Reactivar lead"},
            operation_id="op-idle-rule")
        result = CreateLeadUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, display_name="Lead Viejo", operation_id="op-idle-lead")
        lead_id = result.entity_id
        stale = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(timespec="seconds")
        crm_conn.execute("UPDATE leads SET updated_at=? WHERE id=?", (stale, lead_id))
        crm_conn.commit()

        executions = EvaluateTimeBasedAutomationTriggersUseCase().execute(
            crm_conn, operation_id="op-sweep-1")

        matching = [e for e in executions if e.target_entity_id == lead_id]
        assert matching, "idle lead should have fired the LEAD_IDLE rule"
        assert matching[0].status == CRMAutomationExecutionStatus.SUCCEEDED

    def test_fresh_lead_does_not_fire(self, crm_conn):
        CreateAutomationRuleUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, name="Leads inactivos",
            trigger_type=CRMAutomationTrigger.LEAD_IDLE.value, action_type="CREATE_TASK",
            trigger_config={"idle_days": 3}, operation_id="op-idle-rule-2")
        result = CreateLeadUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, display_name="Lead Nuevo", operation_id="op-idle-lead-2")

        executions = EvaluateTimeBasedAutomationTriggersUseCase().execute(
            crm_conn, operation_id="op-sweep-2")

        assert not [e for e in executions if e.target_entity_id == result.entity_id]

    def test_no_active_rules_returns_empty_without_scanning(self, crm_conn):
        executions = EvaluateTimeBasedAutomationTriggersUseCase().execute(
            crm_conn, operation_id="op-sweep-3")
        assert executions == []


    def test_second_sweep_does_not_fire_the_same_lead_again(self, crm_conn):
        CreateAutomationRuleUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, name="Leads inactivos",
            trigger_type=CRMAutomationTrigger.LEAD_IDLE.value, action_type="CREATE_TASK",
            trigger_config={"days": 3}, operation_id="op-idle-rule-4")
        lead_id = CreateLeadUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, display_name="Lead Viejo",
            operation_id="op-idle-lead-4").entity_id
        stale = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(timespec="seconds")
        crm_conn.execute("UPDATE leads SET updated_at=?, created_at=? WHERE id=?",
                         (stale, stale, lead_id))
        crm_conn.commit()
        sweep = EvaluateTimeBasedAutomationTriggersUseCase()

        first = sweep.execute(crm_conn, operation_id="op-sweep-4a")
        second = sweep.execute(crm_conn, operation_id="op-sweep-4b")

        assert [e.target_entity_id for e in first] == [lead_id]
        assert second == []
        with CRMUnitOfWork(crm_conn) as uow:
            tasks = uow.tasks.list_for_related_entity("LEAD", lead_id)
        assert len(tasks) == 1
