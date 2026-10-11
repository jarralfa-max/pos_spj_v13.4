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
import logging
from datetime import datetime, timedelta, timezone

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.result import CRMResult
from backend.domain.crm.entities.crm_automation_execution import CRMAutomationExecution
from backend.domain.crm.entities.crm_automation_rule import CRMAutomationRule
from backend.domain.crm.entities.crm_automation_rule import threshold_days
from backend.domain.crm.enums import (
    TIME_BASED_TRIGGERS,
    TRIGGER_TARGET_ENTITY,
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
    if target_entity_type not in ("LEAD", "OPPORTUNITY", "CASE", "CUSTOMER"):
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


_TARGET_LABEL = {"LEAD": "Prospecto", "OPPORTUNITY": "Oportunidad", "CASE": "Caso",
                 "CUSTOMER": "Cliente"}


def _exec_send_notification(connection, rule, target_entity_type, target_entity_id, operation_id):
    """CRM-43: aviso en la bandeja personal (`notification_inbox`), la misma que
    muestra la campana de la barra superior. Antes esta acción sólo creaba un
    CRMReminder colgado de una tarea que la regla debía conocer de antemano —
    imposible de configurar — y ningún recordatorio se entregaba jamás.

    Destinatarios: una persona fija (``recipient_user_id``), el responsable del
    registro (``notify_responsible``) o ambos."""
    from backend.infrastructure.notifications.in_app_inbox_repository import (
        InAppInboxRepository,
    )
    cfg = rule.action_config
    with CRMUnitOfWork(connection) as uow:
        responsible, branch_id = uow.sweep.responsible_of(target_entity_type, target_entity_id)
        subject = uow.sweep.describe(target_entity_type, target_entity_id)
        recipients: list[str] = []
        if cfg.get("recipient_user_id"):
            recipients.append(cfg["recipient_user_id"])
        if cfg.get("notify_responsible") and responsible and responsible not in recipients:
            recipients.append(responsible)
        if not recipients:
            return (CRMAutomationExecutionStatus.SKIPPED,
                    "El registro no tiene responsable a quien avisar", None)
        inbox = InAppInboxRepository(connection)
        label = _TARGET_LABEL.get(target_entity_type, target_entity_type)
        extra = cfg.get("message") or ""
        body = f"{label}: {subject}" + (f"\n{extra}" if extra else "")
        for recipient in recipients:
            inbox.deliver(
                recipient_user_id=recipient, kind="CRM", title=rule.name, body=body,
                data={"rule_id": rule.id, "target_entity_type": target_entity_type,
                      "target_entity_id": target_entity_id},
                branch_id=branch_id, severity=cfg.get("severity", "info"),
                dedupe_key=f"crm-automation:{operation_id}:{recipient}")
    return (CRMAutomationExecutionStatus.SUCCEEDED,
            f"Aviso enviado a {len(recipients)} persona(s)", None)


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
    """CRM-43: prospectos (``UpdateLeadUseCase``) y casos (``UpdateServiceCaseUseCase``),
    cada uno con su propio permiso de edición."""
    priority = rule.action_config.get("priority")
    if not priority:
        return (CRMAutomationExecutionStatus.SKIPPED,
                "CHANGE_PRIORITY requiere action_config.priority", None)
    if target_entity_type == "LEAD":
        from backend.application.crm.use_cases.lead_use_cases import UpdateLeadUseCase
        result = UpdateLeadUseCase(_system_policy(CRMPermissions.LEADS_EDIT)).execute(
            connection, actor_user_id=SYSTEM_AUTOMATION_ACTOR, lead_id=target_entity_id,
            operation_id=f"{operation_id}-priority", priority=priority)
    elif target_entity_type == "CASE":
        from backend.application.customer_service.use_cases.service_case_use_cases import (
            UpdateServiceCaseUseCase,
        )
        result = UpdateServiceCaseUseCase(_system_policy(CRMPermissions.CASES_EDIT)).execute(
            connection, actor_user_id=SYSTEM_AUTOMATION_ACTOR, case_id=target_entity_id,
            operation_id=f"{operation_id}-priority", priority=priority)
    else:
        return (CRMAutomationExecutionStatus.SKIPPED,
                f"CHANGE_PRIORITY no soporta target_entity_type={target_entity_type}", None)
    status = CRMAutomationExecutionStatus.SUCCEEDED if result.success else CRMAutomationExecutionStatus.FAILED
    return status, result.message, result.entity_id


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
                connection, rule, target_entity_type, target_entity_id,
                f"{operation_id}:{rule.id}")
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
        # Auditoría CRM F17: antes en nivel debug (invisible). Un fallo de la
        # evaluación no bloquea la operación real, pero sí debe verse.
        logging.getLogger("spj.crm.automation").warning(
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


#: Cuántos registros revisa cada regla por pasada (los más antiguos primero);
#: lo que quede se toma en la pasada siguiente.
SWEEP_BATCH_SIZE = 500

_LOG = logging.getLogger("spj.crm.automation")


class EvaluateTimeBasedAutomationTriggersUseCase:
    """Los disparadores derivados de §56 (``TIME_BASED_TRIGGERS``): nada «se
    vuelve» inactivo, una consulta cruza un umbral. CRM-43 completa los siete
    (antes sólo LEAD_IDLE) y los ejecuta en segundo plano desde la aplicación de
    escritorio (``run_crm_background_cycle``).

    Una regla se dispara una vez por registro y por ancla (último movimiento,
    última compra, fecha de cierre, revisión de crédito, SLA): pasadas repetidas
    no duplican tareas ni avisos. El registro vuelve a ser elegible cuando su
    ancla cambia. Una ejecución FALLIDA también cuenta: queda a la vista en el
    historial de la regla en lugar de reintentarse cada pasada."""

    def execute(self, connection, *, operation_id: str,
                now: datetime | None = None) -> list[CRMAutomationExecution]:
        now = now or datetime.now(timezone.utc)
        executions: list[CRMAutomationExecution] = []
        with CRMUnitOfWork(connection) as uow:
            rules = [rule for trigger in sorted(TIME_BASED_TRIGGERS, key=lambda t: t.value)
                     for rule in uow.automation_rules.list_active_for_trigger(trigger)]
        for rule in rules:
            target_type = TRIGGER_TARGET_ENTITY[rule.trigger_type]
            try:
                candidates = self._candidates(connection, rule, now)
            except Exception as exc:  # una tabla ausente no detiene las demás reglas
                _LOG.warning("Regla %s (%s) no evaluable: %s", rule.name,
                             rule.trigger_type.value, exc)
                continue
            for target_id, anchor in candidates:
                with CRMUnitOfWork(connection) as uow:
                    last = uow.sweep.last_execution_at(rule.id, target_type, target_id)
                if last and last >= anchor:
                    continue
                executions.append(_run_rule(connection, rule, target_type, target_id,
                                            f"{operation_id}:{target_id}"))
        return executions

    @staticmethod
    def _candidates(connection, rule: CRMAutomationRule, now: datetime) -> list[tuple[str, str]]:
        trigger = rule.trigger_type
        if trigger in (CRMAutomationTrigger.SLA_AT_RISK, CRMAutomationTrigger.SLA_BREACHED):
            from backend.domain.customer_service.enums import SLABreachStatus
            from backend.infrastructure.db.repositories.customer_service.unit_of_work import (
                CustomerServiceUnitOfWork,
            )
            wanted = (SLABreachStatus.AT_RISK if trigger is CRMAutomationTrigger.SLA_AT_RISK
                      else SLABreachStatus.BREACHED)
            as_of = now.isoformat(timespec="seconds")
            slas = CustomerServiceUnitOfWork(connection).sla_instances.list_open()
            return [(sla.case_id, sla.created_at) for sla in slas
                    if sla.effective_breach_status(as_of=as_of) is wanted][:SWEEP_BATCH_SIZE]
        with CRMUnitOfWork(connection) as uow:
            sweep = uow.sweep
            if trigger is CRMAutomationTrigger.OPPORTUNITY_OVERDUE:
                today = now.astimezone().date().isoformat()
                return sweep.overdue_opportunities(today, limit=SWEEP_BATCH_SIZE)
            days = threshold_days(rule.trigger_config)
            if days is None:
                raise InvalidCRMAutomationRuleError("la regla no dice cuántos días")
            cutoff = (now - timedelta(days=days)).isoformat(timespec="seconds")
            query = {
                CRMAutomationTrigger.LEAD_IDLE: sweep.idle_leads,
                CRMAutomationTrigger.OPPORTUNITY_IDLE: sweep.idle_opportunities,
                CRMAutomationTrigger.CUSTOMER_INACTIVE: sweep.inactive_customers,
                CRMAutomationTrigger.CREDIT_REVIEW_DUE: sweep.credit_reviews_due,
            }[trigger]
            return query(cutoff, limit=SWEEP_BATCH_SIZE)
