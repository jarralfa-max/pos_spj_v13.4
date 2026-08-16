"""CRMAutomationRuleRepository / CRMAutomationExecutionRepository — persists
declarative automation rules and their execution log (CRM-26, §56). Mirrors
backend/infrastructure/db/repositories/crm/customer_segment_repository.py.
``trigger_config``/``action_config`` are stored as JSON text — the domain
entity holds them as plain dicts.
"""

from __future__ import annotations

import json

from backend.domain.crm.entities.crm_automation_execution import CRMAutomationExecution
from backend.domain.crm.entities.crm_automation_rule import CRMAutomationRule
from backend.domain.crm.enums import (
    CRMAutomationAction,
    CRMAutomationExecutionStatus,
    CRMAutomationTrigger,
)
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_RULE_COLS = (
    "id, name, description, trigger_type, action_type, trigger_config, action_config,"
    " active, created_by_user_id, operation_id, created_at, updated_at, version"
)
_EXEC_COLS = (
    "id, rule_id, trigger_type, target_entity_type, target_entity_id, status,"
    " result_detail, created_entity_id, operation_id, executed_at"
)


class CRMAutomationRuleRepository(CRMRepositoryBase):
    def save(self, rule: CRMAutomationRule) -> None:
        self._execute(
            f"INSERT INTO crm_automation_rules ({_RULE_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(rule))

    def update(self, rule: CRMAutomationRule) -> None:
        self._execute(
            "UPDATE crm_automation_rules SET name=?, description=?, trigger_config=?,"
            " action_config=?, active=?, updated_at=?, version=? WHERE id=?",
            (rule.name, rule.description, json.dumps(rule.trigger_config),
             json.dumps(rule.action_config), int(rule.active), rule.updated_at,
             rule.version, rule.id))

    def get(self, rule_id: str) -> CRMAutomationRule | None:
        row = self._query_one(f"SELECT {_RULE_COLS} FROM crm_automation_rules WHERE id=?",
                              (rule_id,))
        return self._hydrate(row) if row else None

    def get_by_operation_id(self, operation_id: str) -> CRMAutomationRule | None:
        if not operation_id:
            return None
        row = self._query_one(
            f"SELECT {_RULE_COLS} FROM crm_automation_rules WHERE operation_id=?",
            (operation_id,))
        return self._hydrate(row) if row else None

    def list_active_for_trigger(self, trigger_type: CRMAutomationTrigger) -> list[CRMAutomationRule]:
        rows = self._query(
            f"SELECT {_RULE_COLS} FROM crm_automation_rules"
            " WHERE active=1 AND trigger_type=? ORDER BY created_at ASC",
            (trigger_type.value,))
        return [self._hydrate(r) for r in rows]

    def list_all(self) -> list[CRMAutomationRule]:
        rows = self._query(f"SELECT {_RULE_COLS} FROM crm_automation_rules ORDER BY created_at DESC")
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _params(rule: CRMAutomationRule) -> tuple:
        return (
            rule.id, rule.name, rule.description, rule.trigger_type.value, rule.action_type.value,
            json.dumps(rule.trigger_config), json.dumps(rule.action_config), int(rule.active),
            rule.created_by_user_id, rule.operation_id, rule.created_at, rule.updated_at,
            rule.version,
        )

    @staticmethod
    def _hydrate(row: dict) -> CRMAutomationRule:
        return CRMAutomationRule(
            id=row["id"], name=row["name"], description=row["description"] or "",
            trigger_type=CRMAutomationTrigger(row["trigger_type"]),
            action_type=CRMAutomationAction(row["action_type"]),
            trigger_config=json.loads(row["trigger_config"] or "{}"),
            action_config=json.loads(row["action_config"] or "{}"),
            active=bool(row["active"]), created_by_user_id=row["created_by_user_id"] or "",
            operation_id=row["operation_id"] or "", created_at=row["created_at"],
            updated_at=row["updated_at"], version=row["version"],
        )


class CRMAutomationExecutionRepository(CRMRepositoryBase):
    def save(self, execution: CRMAutomationExecution) -> None:
        self._execute(
            f"INSERT INTO crm_automation_executions ({_EXEC_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?)",
            self._params(execution))

    def list_for_rule(self, rule_id: str, *, limit: int = 50) -> list[CRMAutomationExecution]:
        rows = self._query(
            f"SELECT {_EXEC_COLS} FROM crm_automation_executions"
            " WHERE rule_id=? ORDER BY executed_at DESC LIMIT ?",
            (rule_id, limit))
        return [self._hydrate(r) for r in rows]

    def list_recent(self, *, limit: int = 100) -> list[CRMAutomationExecution]:
        rows = self._query(
            f"SELECT {_EXEC_COLS} FROM crm_automation_executions"
            " ORDER BY executed_at DESC LIMIT ?", (limit,))
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _params(execution: CRMAutomationExecution) -> tuple:
        return (
            execution.id, execution.rule_id, execution.trigger_type,
            execution.target_entity_type, execution.target_entity_id, execution.status.value,
            execution.result_detail, execution.created_entity_id, execution.operation_id,
            execution.executed_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CRMAutomationExecution:
        return CRMAutomationExecution(
            id=row["id"], rule_id=row["rule_id"], trigger_type=row["trigger_type"],
            target_entity_type=row["target_entity_type"],
            target_entity_id=row["target_entity_id"],
            status=CRMAutomationExecutionStatus(row["status"]),
            result_detail=row["result_detail"] or "", created_entity_id=row["created_entity_id"],
            operation_id=row["operation_id"] or "", executed_at=row["executed_at"],
        )
