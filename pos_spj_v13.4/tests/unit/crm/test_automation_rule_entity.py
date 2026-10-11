"""CRMAutomationRule/CRMAutomationExecution domain entity tests (CRM-26)."""

from __future__ import annotations

import pytest

from backend.domain.crm.entities.crm_automation_execution import CRMAutomationExecution
from backend.domain.crm.entities.crm_automation_rule import CRMAutomationRule
from backend.domain.crm.enums import (
    CRMAutomationAction,
    CRMAutomationExecutionStatus,
    CRMAutomationTrigger,
)
from backend.domain.crm.exceptions import InvalidCRMAutomationRuleError


class TestCRMAutomationRuleCreate:
    def test_create_valid_rule(self):
        rule = CRMAutomationRule.create(
            "Seguimiento a leads nuevos", CRMAutomationTrigger.LEAD_CREATED,
            CRMAutomationAction.CREATE_TASK, action_config={"title": "Llamar"})
        assert rule.id
        assert rule.active is True
        assert rule.version == 1
        assert rule.action_config == {"title": "Llamar"}
        assert rule.trigger_config == {}

    def test_create_requires_name(self):
        with pytest.raises(InvalidCRMAutomationRuleError):
            CRMAutomationRule.create(
                "  ", CRMAutomationTrigger.LEAD_CREATED, CRMAutomationAction.CREATE_TASK)

    def test_create_requires_real_trigger_enum(self):
        with pytest.raises(InvalidCRMAutomationRuleError):
            CRMAutomationRule.create("X", "NOT_A_TRIGGER", CRMAutomationAction.CREATE_TASK)

    def test_create_requires_real_action_enum(self):
        with pytest.raises(InvalidCRMAutomationRuleError):
            CRMAutomationRule.create("X", CRMAutomationTrigger.LEAD_CREATED, "NOT_AN_ACTION")


class TestCRMAutomationRuleLifecycle:
    def test_deactivate_then_activate_bumps_version(self):
        rule = CRMAutomationRule.create(
            "X", CRMAutomationTrigger.LEAD_CREATED, CRMAutomationAction.CREATE_TASK)
        rule.deactivate()
        assert rule.active is False
        assert rule.version == 2
        rule.activate()
        assert rule.active is True
        assert rule.version == 3

    def test_update_config_bumps_version_and_replaces_dicts(self):
        rule = CRMAutomationRule.create(
            "X", CRMAutomationTrigger.LEAD_CREATED, CRMAutomationAction.CREATE_TASK,
            action_config={"title": "old"})
        rule.update_config(action_config={"title": "new"})
        assert rule.action_config == {"title": "new"}
        assert rule.version == 2
        # trigger_config not passed -> unchanged
        rule.update_config(trigger_config={"idle_days": 5})
        assert rule.trigger_config == {"idle_days": 5}
        assert rule.action_config == {"title": "new"}


class TestCRMAutomationExecutionRecord:
    def test_record_succeeded(self):
        execution = CRMAutomationExecution.record(
            "rule-1", "LEAD_CREATED", "LEAD", "lead-1", CRMAutomationExecutionStatus.SUCCEEDED,
            result_detail="Tarea creada", created_entity_id="task-1", operation_id="op-1")
        assert execution.id
        assert execution.status == CRMAutomationExecutionStatus.SUCCEEDED
        assert execution.created_entity_id == "task-1"


class TestRuleConfigValidation:
    """CRM-43: una regla que no puede ejecutarse no se guarda."""

    def test_action_must_apply_to_the_trigger_target(self):
        with pytest.raises(InvalidCRMAutomationRuleError, match="no aplica a clientes"):
            CRMAutomationRule.create("X", CRMAutomationTrigger.CUSTOMER_INACTIVE,
                                     CRMAutomationAction.ASSIGN_OWNER,
                                     trigger_config={"days": 30},
                                     action_config={"assignee_user_id": "u1"})

    def test_threshold_triggers_need_positive_days(self):
        for config in ({}, {"days": 0}, {"days": "x"}):
            with pytest.raises(InvalidCRMAutomationRuleError, match="cuántos días"):
                CRMAutomationRule.create("X", CRMAutomationTrigger.OPPORTUNITY_IDLE,
                                         CRMAutomationAction.CREATE_TASK, trigger_config=config)

    def test_legacy_idle_days_key_is_still_accepted(self):
        rule = CRMAutomationRule.create("X", CRMAutomationTrigger.LEAD_IDLE,
                                        CRMAutomationAction.CREATE_TASK,
                                        trigger_config={"idle_days": 3})
        assert rule.trigger_config == {"idle_days": 3}

    def test_required_action_data(self):
        cases = (
            (CRMAutomationTrigger.LEAD_CREATED, CRMAutomationAction.ASSIGN_OWNER, "asigna"),
            (CRMAutomationTrigger.CASE_CREATED, CRMAutomationAction.ESCALATE_CASE, "escala"),
            (CRMAutomationTrigger.CUSTOMER_INACTIVE, CRMAutomationAction.ADD_TAG, "etiqueta"),
            (CRMAutomationTrigger.CASE_CREATED, CRMAutomationAction.CHANGE_PRIORITY, "prioridad"),
            (CRMAutomationTrigger.LEAD_CREATED, CRMAutomationAction.SEND_NOTIFICATION,
             "quién recibe"),
        )
        for trigger, action, words in cases:
            with pytest.raises(InvalidCRMAutomationRuleError, match=words):
                CRMAutomationRule.create("X", trigger, action, trigger_config={"days": 5})

    def test_leads_have_no_critical_priority(self):
        with pytest.raises(InvalidCRMAutomationRuleError, match="CRITICAL"):
            CRMAutomationRule.create("X", CRMAutomationTrigger.LEAD_CREATED,
                                     CRMAutomationAction.CHANGE_PRIORITY,
                                     action_config={"priority": "CRITICAL"})
        rule = CRMAutomationRule.create("X", CRMAutomationTrigger.SLA_BREACHED,
                                        CRMAutomationAction.CHANGE_PRIORITY,
                                        action_config={"priority": "CRITICAL"})
        assert rule.action_config["priority"] == "CRITICAL"

    def test_update_config_is_validated_too(self):
        rule = CRMAutomationRule.create("X", CRMAutomationTrigger.LEAD_CREATED,
                                        CRMAutomationAction.ASSIGN_OWNER,
                                        action_config={"assignee_user_id": "u1"})
        with pytest.raises(InvalidCRMAutomationRuleError):
            rule.update_config(action_config={})
