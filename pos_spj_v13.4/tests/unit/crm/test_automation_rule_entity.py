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
