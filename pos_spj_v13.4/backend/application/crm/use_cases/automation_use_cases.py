"""CRM Automation Rules (§56, CRM-26): rule CRUD + the two evaluation
entry points (reactive/event-driven, and derived/time-based).

Rule CRUD (CreateAutomationRuleUseCase/UpdateAutomationRuleUseCase/
ActivateAutomationRuleUseCase/DeactivateAutomationRuleUseCase) follows the
same shape as every other use case in this package: permission-gated,
CRMUnitOfWork, audit + outbox.

Evaluation (EvaluateEventTriggerUseCase/
EvaluateTimeBasedAutomationTriggersUseCase) is system-triggered — no
actor_user_id/permission check on the entry point itself, same reasoning
CRM-13's sales_event_handlers.py already established: this reacts to
another operation's outcome, not a direct human action. Each individual
ACTION a rule fires still goes through its target use case's OWN
permission check — evaluation doesn't bypass authorization globally, it
authorizes narrowly as the well-known SYSTEM_AUTOMATION actor, granted
*only* the single permission the specific action about to run needs (see
_SingleActionPermissionChecker below). This is deliberately NOT
AllowAllCRMPermissionCheckerForTests (test-only, forbidden in production
per its own docstring) — each dispatch is scoped to one action, one
permission, and independently audited via CRMAutomationExecution plus the
target use case's own audit.record().
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.result import CRMResult
from backend.domain.crm.entities.crm_automation_execution import CRMAutomationExecution
from backend.domain.crm.entities.crm_automation_rule import CRMAutomationRule
from backend.domain.crm.enums import (
    TIME_BASED_TRIGGERS,
    CRMAutomationAction,
    CRMAutomationExecutionStatus,
    CRMAutomationTrigger,
)
from backend.domain.crm.events import CRMEvents, build_event_payload
from backend.domain.crm.exceptions import CRMDomainError, InvalidCRMAutomationRuleError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork

#: Well-known pseudo-actor for automation-fired actions — same "system
#: caller" convention already used elsewhere (api/routers/clientes.py's
#: _WHATSAPP_BOT_ACTOR). Never a real logged-in user; every downstream use
#: case's own audit.record(actor_user_id=...) records this literal value,
#: making automation-originated changes traceable, not anonymous.
SYSTEM_AUTOMATION_ACTOR = "SYSTEM_AUTOMATION"


class _SingleActionPermissionChecker:
    """Grants exactly one permission code, only to SYSTEM_AUTOMATION_ACTOR.
    Built fresh per action dispatch — never a blanket allow-all."""

    def __init__(self, permission_code: str) -> None:
        self._permission_code = permission_code

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return user_id == SYSTEM_AUTOMATION_ACTOR and permission_code == self._permission_code


def _system_policy(permission_code: str) -> CRMAuthorizationPolicy:
    return CRMAuthorizationPolicy(_SingleActionPermissionChecker(permission_code))


class _BaseUseCase:
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()

    def _emit(self, uow, event_name: str, rule_id: str, operation_id: str,
              actor_user_id: str, **extra) -> None:
        payload = build_event_payload(event_name, operation_id=operation_id,
                                      user_id=actor_user_id, automation_rule_id=rule_id, **extra)
        uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload), operation_id)


# ── Rule CRUD (§56) ──────────────────────────────────────────────────────────

class CreateAutomationRuleUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, name: str, trigger_type: str,
        action_type: str, operation_id: str, trigger_config: dict | None = None,
        action_config: dict | None = None, description: str = "",
    ) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.AUTOMATION_RULES_CREATE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            existing = uow.automation_rules.get_by_operation_id(operation_id)
            if existing is not None:
                return CRMResult.ok("Regla ya registrada", entity_id=existing.id,
                                    operation_id=operation_id)
            try:
                rule = CRMAutomationRule.create(
                    name, CRMAutomationTrigger(trigger_type), CRMAutomationAction(action_type),
                    trigger_config=trigger_config, action_config=action_config,
                    description=description, created_by_user_id=actor_user_id,
                    operation_id=operation_id)
            except (CRMDomainError, ValueError) as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.automation_rules.save(rule)
            uow.audit.record(action="AUTOMATION_RULE_CREATED", actor_user_id=actor_user_id,
                             operation_id=operation_id,
                             after_json=json.dumps({"rule_id": rule.id, "name": rule.name}))
            self._emit(uow, "AUTOMATION_RULE_CREATED", rule.id, operation_id, actor_user_id)
        return CRMResult.ok("Regla de automatización creada", entity_id=rule.id,
                            operation_id=operation_id)


class UpdateAutomationRuleUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, rule_id: str, operation_id: str,
        trigger_config: dict | None = None, action_config: dict | None = None,
    ) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.AUTOMATION_RULES_EDIT)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            rule = uow.automation_rules.get(rule_id)
            if rule is None:
                return CRMResult.fail("La regla no existe", "NOT_FOUND", operation_id=operation_id)
            rule.update_config(trigger_config=trigger_config, action_config=action_config)
            uow.automation_rules.update(rule)
            uow.audit.record(action="AUTOMATION_RULE_UPDATED", actor_user_id=actor_user_id,
                             operation_id=operation_id, after_json=json.dumps({"rule_id": rule.id}))
            self._emit(uow, "AUTOMATION_RULE_UPDATED", rule.id, operation_id, actor_user_id)
        return CRMResult.ok("Regla actualizada", entity_id=rule_id, operation_id=operation_id)


class ActivateAutomationRuleUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, rule_id: str,
                operation_id: str) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.AUTOMATION_RULES_ACTIVATE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            rule = uow.automation_rules.get(rule_id)
            if rule is None:
                return CRMResult.fail("La regla no existe", "NOT_FOUND", operation_id=operation_id)
            rule.activate()
            uow.automation_rules.update(rule)
            uow.audit.record(action="AUTOMATION_RULE_ACTIVATED", actor_user_id=actor_user_id,
                             operation_id=operation_id)
            self._emit(uow, "AUTOMATION_RULE_ACTIVATED", rule.id, operation_id, actor_user_id)
        return CRMResult.ok("Regla activada", entity_id=rule_id, operation_id=operation_id)


class DeactivateAutomationRuleUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, rule_id: str,
                operation_id: str) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.AUTOMATION_RULES_DEACTIVATE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            rule = uow.automation_rules.get(rule_id)
            if rule is None:
                return CRMResult.fail("La regla no existe", "NOT_FOUND", operation_id=operation_id)
            rule.deactivate()
            uow.automation_rules.update(rule)
            uow.audit.record(action="AUTOMATION_RULE_DEACTIVATED", actor_user_id=actor_user_id,
                             operation_id=operation_id)
            self._emit(uow, "AUTOMATION_RULE_DEACTIVATED", rule.id, operation_id, actor_user_id)
        return CRMResult.ok("Regla desactivada", entity_id=rule_id, operation_id=operation_id)


# ── Action executors (§56's 7 actions) ───────────────────────────────────────
# Each returns (status, result_detail, created_entity_id). Never raises —
# the caller wraps every dispatch, an unhandled exception becomes a FAILED
# execution row, not a crash of whatever real operation triggered the rule.

def _exec_create_task(connection, rule, target_entity_type, target_entity_id, operation_id):
    if target_entity_type not in ("LEAD", "OPPORTUNITY", "CASE"):
        return (CRMAutomationExecutionStatus.SKIPPED,
                f"CREATE_TASK no soporta target_entity_type={target_entity_type}", None)
    from backend.application.crm.use_cases.task_use_cases import CreateCRMTaskUseCase
    cfg = rule.action_config
    title = cfg.get("title") or f"Seguimiento automático: {rule.name}"
    due_in_hours = float(cfg.get("due_in_hours", 24))
    due_at = (datetime.now(timezone.utc) + timedelta(hours=due_in_hours)).isoformat(timespec="seconds")
    uc = CreateCRMTaskUseCase(_system_policy(CRMPermissions.TASKS_CREATE))
    result = uc.execute(
        connection, actor_user_id=SYSTEM_AUTOMATION_ACTOR, related_entity_type=target_entity_type,
        related_entity_id=target_entity_id, title=title, due_at=due_at,
        operation_id=f"{operation_id}-task", assigned_user_id=cfg.get("assigned_user_id"),
        description=cfg.get("description", ""))
    status = CRMAutomationExecutionStatus.SUCCEEDED if result.success else CRMAutomationExecutionStatus.FAILED
    return status, result.message, result.entity_id


def _exec_assign_owner(connection, rule, target_entity_type, target_entity_id, operation_id):
    assignee = rule.action_config.get("assignee_user_id")
    if not assignee:
        return (CRMAutomationExecutionStatus.SKIPPED,
                "ASSIGN_OWNER requiere action_config.assignee_user_id", None)
    if target_entity_type == "LEAD":
        from backend.application.crm.use_cases.lead_use_cases import AssignLeadUseCase
        uc = AssignLeadUseCase(_system_policy(CRMPermissions.LEADS_ASSIGN))
        result = uc.execute(connection, actor_user_id=SYSTEM_AUTOMATION_ACTOR, lead_id=target_entity_id,
                            operation_id=f"{operation_id}-assign", assignee_user_id=assignee,
                            reason=f"Automatización: {rule.name}")
    elif target_entity_type == "OPPORTUNITY":
        from backend.application.crm.use_cases.opportunity_use_cases import AssignOpportunityUseCase
        uc = AssignOpportunityUseCase(_system_policy(CRMPermissions.OPPORTUNITIES_ASSIGN))
        result = uc.execute(connection, actor_user_id=SYSTEM_AUTOMATION_ACTOR,
                            opportunity_id=target_entity_id, assignee_user_id=assignee,
                            operation_id=f"{operation_id}-assign")
    else:
        return (CRMAutomationExecutionStatus.SKIPPED,
                f"ASSIGN_OWNER no soporta target_entity_type={target_entity_type}"
                " (propietario de Customer pertenece al stack de Customer Master, no CRM)", None)
    status = CRMAutomationExecutionStatus.SUCCEEDED if result.success else CRMAutomationExecutionStatus.FAILED
    return status, result.message, result.entity_id


def _exec_send_notification(connection, rule, target_entity_type, target_entity_id, operation_id):
    """§25: "CRM define recordatorio/destinatario... no enviar directamente
    desde widgets." A CRMReminder always attaches to a task or activity —
    it has no independent target of its own (same reasoning CRM-6/CRM-12
    already documented for reminders). Only fires when the rule's own
    config supplies one to attach to (e.g. chained after a CREATE_TASK rule
    via action_config.task_id); otherwise this is a documented gap, not a
    silent no-op."""
    cfg = rule.action_config
    task_id = cfg.get("task_id")
    recipient = cfg.get("recipient_user_id")
    if not task_id or not recipient:
        return (CRMAutomationExecutionStatus.SKIPPED,
                "SEND_NOTIFICATION requiere action_config.task_id y recipient_user_id"
                " (CRMReminder no tiene destino propio, siempre cuelga de una tarea/actividad)", None)
    from backend.application.crm.use_cases.reminder_use_cases import CreateCRMReminderUseCase
    from backend.domain.crm.enums import ReminderChannel
    uc = CreateCRMReminderUseCase(_system_policy(CRMPermissions.REMINDERS_CREATE))
    result = uc.execute(
        connection, actor_user_id=SYSTEM_AUTOMATION_ACTOR,
        channel=cfg.get("channel", ReminderChannel.IN_APP.value), remind_at=cfg.get(
            "remind_at", datetime.now(timezone.utc).isoformat(timespec="seconds")),
        recipient_user_id=recipient, operation_id=f"{operation_id}-reminder", task_id=task_id,
        message=cfg.get("message", f"Automatización: {rule.name}"))
    status = CRMAutomationExecutionStatus.SUCCEEDED if result.success else CRMAutomationExecutionStatus.FAILED
    return status, result.message, result.entity_id


def _exec_escalate_case(connection, rule, target_entity_type, target_entity_id, operation_id):
    if target_entity_type != "CASE":
        return (CRMAutomationExecutionStatus.SKIPPED,
                f"ESCALATE_CASE no soporta target_entity_type={target_entity_type}", None)
    cfg = rule.action_config
    escalated_to = cfg.get("escalated_to_user_id")
    if not escalated_to:
        return (CRMAutomationExecutionStatus.SKIPPED,
                "ESCALATE_CASE requiere action_config.escalated_to_user_id", None)
    from backend.application.customer_service.use_cases.escalate_service_case_use_case import (
        EscalateServiceCaseUseCase,
    )
    uc = EscalateServiceCaseUseCase(_system_policy(CRMPermissions.CASES_ESCALATE))
    result = uc.execute(
        connection, actor_user_id=SYSTEM_AUTOMATION_ACTOR, case_id=target_entity_id,
        reason=cfg.get("reason", "SLA_BREACHED"), escalated_to_user_id=escalated_to,
        operation_id=f"{operation_id}-escalate", detail=f"Automatización: {rule.name}")
    status = CRMAutomationExecutionStatus.SUCCEEDED if result.success else CRMAutomationExecutionStatus.FAILED
    return status, result.message, result.entity_id


def _exec_add_tag(connection, rule, target_entity_type, target_entity_id, operation_id):
    if target_entity_type != "CUSTOMER":
        return (CRMAutomationExecutionStatus.SKIPPED,
                f"ADD_TAG no soporta target_entity_type={target_entity_type}"
                " (las etiquetas son de Customer, no de Lead/Opportunity/Case)", None)
    tag_id = rule.action_config.get("tag_id")
    if not tag_id:
        return CRMAutomationExecutionStatus.SKIPPED, "ADD_TAG requiere action_config.tag_id", None
    from backend.application.crm.use_cases.tag_use_cases import AssignCustomerTagUseCase
    uc = AssignCustomerTagUseCase(_system_policy(CRMPermissions.TAGS_ASSIGN))
    result = uc.execute(connection, actor_user_id=SYSTEM_AUTOMATION_ACTOR, customer_id=target_entity_id,
                        tag_id=tag_id, operation_id=f"{operation_id}-tag")
    status = CRMAutomationExecutionStatus.SUCCEEDED if result.success else CRMAutomationExecutionStatus.FAILED
    return status, result.message, result.entity_id


def _exec_add_to_segment(connection, rule, target_entity_type, target_entity_id, operation_id):
    if target_entity_type != "CUSTOMER":
        return (CRMAutomationExecutionStatus.SKIPPED,
                f"ADD_TO_SEGMENT no soporta target_entity_type={target_entity_type}", None)
    segment_id = rule.action_config.get("segment_id")
    if not segment_id:
        return (CRMAutomationExecutionStatus.SKIPPED,
                "ADD_TO_SEGMENT requiere action_config.segment_id", None)
    from backend.application.crm.use_cases.segment_use_cases import AddCustomerToSegmentUseCase
    from backend.domain.crm.enums import SegmentMembershipSource
    uc = AddCustomerToSegmentUseCase(_system_policy(CRMPermissions.SEGMENTS_ASSIGN))
    result = uc.execute(connection, actor_user_id=SYSTEM_AUTOMATION_ACTOR, customer_id=target_entity_id,
                        segment_id=segment_id, operation_id=f"{operation_id}-segment",
                        source=SegmentMembershipSource.RULE_BASED.value)
    status = CRMAutomationExecutionStatus.SUCCEEDED if result.success else CRMAutomationExecutionStatus.FAILED
    return status, result.message, result.entity_id


def _exec_change_priority(connection, rule, target_entity_type, target_entity_id, operation_id):
    # No CRM use case exposes a standalone "change priority" mutation for
    # Lead or Opportunity today (Lead.priority is set at creation; no
    # UpdatePriority-style use case exists) — a real, documented gap, not
    # silently faked. §56 names the action; building the missing use case
    # is future work, not invented here under an unrelated phase's cover.
    return (CRMAutomationExecutionStatus.SKIPPED,
            "CHANGE_PRIORITY: no existe un caso de uso de cambio de prioridad para"
            f" {target_entity_type} todavía — acción declarada, no implementada", None)


_ACTION_EXECUTORS = {
    CRMAutomationAction.CREATE_TASK: _exec_create_task,
    CRMAutomationAction.ASSIGN_OWNER: _exec_assign_owner,
    CRMAutomationAction.SEND_NOTIFICATION: _exec_send_notification,
    CRMAutomationAction.ESCALATE_CASE: _exec_escalate_case,
    CRMAutomationAction.ADD_TAG: _exec_add_tag,
    CRMAutomationAction.ADD_TO_SEGMENT: _exec_add_to_segment,
    CRMAutomationAction.CHANGE_PRIORITY: _exec_change_priority,
}


def _run_rule(connection, rule: CRMAutomationRule, target_entity_type: str,
              target_entity_id: str, operation_id: str) -> CRMAutomationExecution:
    executor = _ACTION_EXECUTORS.get(rule.action_type)
    if executor is None:
        status, detail, created_id = (
            CRMAutomationExecutionStatus.SKIPPED,
            f"Acción {rule.action_type.value} sin ejecutor registrado", None)
    else:
        try:
            status, detail, created_id = executor(
                connection, rule, target_entity_type, target_entity_id, operation_id)
        except Exception as exc:  # nunca bloquear la operación real que disparó la regla
            status, detail, created_id = CRMAutomationExecutionStatus.FAILED, str(exc), None
    execution = CRMAutomationExecution.record(
        rule.id, rule.trigger_type.value, target_entity_type, target_entity_id, status,
        result_detail=detail, created_entity_id=created_id, operation_id=operation_id)
    with CRMUnitOfWork(connection) as uow:
        uow.automation_executions.save(execution)
    return execution


# ── Evaluation entry points ──────────────────────────────────────────────────

def fire_event_trigger(connection, trigger: CRMAutomationTrigger, target_entity_type: str,
                       target_entity_id: str, operation_id: str) -> None:
    """Safe wrapper for CreateLeadUseCase/MoveOpportunityStageUseCase/
    CreateServiceCaseUseCase to call right after their own event commits.
    Swallows and logs any exception — a misconfigured or failing automation
    rule must never block the real domain operation that triggered it, same
    defensive shape as every advisory/eager-side-effect call already
    established in this pipeline (CRM-21's eligibility check, CRM-25's
    eager CRM bridge)."""
    import logging
    try:
        EvaluateEventTriggerUseCase().execute(
            connection, trigger=trigger, target_entity_type=target_entity_type,
            target_entity_id=target_entity_id, operation_id=operation_id)
    except Exception as exc:
        logging.getLogger("spj.crm.automation").debug(
            "Automation evaluation failed for %s %s/%s: %s",
            trigger, target_entity_type, target_entity_id, exc)


class EvaluateEventTriggerUseCase:
    """Reactive: called right after a REAL domain event fires (LEAD_CREATED,
    OPPORTUNITY_STAGE_CHANGED, CASE_CREATED — the only three §56 triggers
    that are genuine discrete state changes today, see
    backend/domain/crm/enums.py's EVENT_TRIGGERS). No actor_user_id/
    permission check on this entry point itself — system-triggered, same
    as sales_event_handlers.py. Never raises."""

    def execute(self, connection, *, trigger: CRMAutomationTrigger, target_entity_type: str,
                target_entity_id: str, operation_id: str) -> list[CRMAutomationExecution]:
        with CRMUnitOfWork(connection) as uow:
            rules = uow.automation_rules.list_active_for_trigger(trigger)
        return [_run_rule(connection, rule, target_entity_type, target_entity_id, operation_id)
                for rule in rules]


class EvaluateTimeBasedAutomationTriggersUseCase:
    """Derived/computed triggers (LEAD_IDLE, OPPORTUNITY_IDLE,
    OPPORTUNITY_OVERDUE, CUSTOMER_INACTIVE, SLA_AT_RISK, SLA_BREACHED,
    CREDIT_REVIEW_DUE — backend/domain/crm/enums.py's TIME_BASED_TRIGGERS)
    have no discrete event to react to; nothing "becomes idle," a query
    just crosses a threshold. This repo has NO scheduler/cron/background-job
    mechanism anywhere (confirmed by research before building this) — this
    use case is a callable, explicit sweep entry point, not a fabricated
    always-on scheduler. It is not wired to anything today; whoever adds
    scheduling infrastructure to this desktop app (or a future server
    component) is the intended caller. Documented as a real gap, same as
    CRM-13 left WhatsApp-conversation-boundary/Cotizaciones gaps documented
    rather than invented.

    Only implements the LEAD_IDLE check today, as a working reference
    implementation others can extend — the remaining six time-based
    triggers each need a query this phase didn't have scope to build for
    every one (SLA breach detection already has its own canonical logic in
    SLAQueryService; duplicating a simplified version here would violate
    the same "don't reimplement, call the real one" rule CRM-13's
    sla_breach_count proxy already flagged as a simplification, not a
    precedent to repeat blindly)."""

    def execute(self, connection, *, operation_id: str,
                idle_days_default: int = 3) -> list[CRMAutomationExecution]:
        executions: list[CRMAutomationExecution] = []
        with CRMUnitOfWork(connection) as uow:
            rules = uow.automation_rules.list_active_for_trigger(CRMAutomationTrigger.LEAD_IDLE)
            if not rules:
                return executions
            # Lead.list_open() (built CRM-4, no dedicated "idle" query
            # exists) — filtered here by last-touch age instead of adding a
            # new repository method under this phase's time pressure; fine
            # at this scale (open-leads volume), not a hot path.
            open_leads = uow.leads.list_open(limit=500)
        for rule in rules:
            idle_days = int(rule.trigger_config.get("idle_days", idle_days_default))
            for lead in open_leads:
                if _lead_idle_days(lead) < idle_days:
                    continue
                executions.append(_run_rule(connection, rule, "LEAD", lead.id, operation_id))
        return executions


def _lead_idle_days(lead) -> int:
    last_touch = lead.updated_at or lead.created_at
    try:
        last_dt = datetime.fromisoformat(last_touch)
    except (TypeError, ValueError):
        return 0
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - last_dt).days
