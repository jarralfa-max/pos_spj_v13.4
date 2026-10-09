"""Raíz de composición de Clientes y CRM (CRM-43).

Único lugar que cablea la conexión viva y la sesión a los servicios de
consulta, casos de uso y presentador del módulo. Vivía en
``frontend/desktop/modules/customers_crm/composition.py`` y por eso esa capa
de UI terminaba llamando ``.execute(connection, …)`` (lo que la guarda
«la UI no ejecuta SQL» marca, con razón); ahora sigue el patrón de Caja
(``cash_register_factory.py``).

Antes de CRM-43 se cableaban 4 comandos de 141 casos de uso: el resto del CRM
existía sin pantalla. Aquí se registran TODOS — cada página de la UI sólo pide
``presenter.run("<comando>", …)`` o ``presenter.read("<lectura>", …)``.

Cada caso de uso se instancia por llamada con la política de autorización
real de la sesión (``CustomerSessionPermissionChecker``, falla cerrado):
nunca un verificador permisivo de pruebas.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.data_scope import CRMDataScopeResolver
from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.data_scope import CustomerDataScopeResolver
from backend.application.customers.session_authorization import (
    CustomerSessionPermissionChecker,
)

#: comando → (módulo, clase, política: "customer" | "crm" | "both" | "owner")
_COMMANDS: dict[str, tuple[str, str, str]] = {
    # ── clientes ────────────────────────────────────────────────────────────
    "create_customer": ("customers.use_cases.lifecycle_use_cases", "CreateCustomerUseCase", "customer"),
    "update_customer": ("customers.use_cases.lifecycle_use_cases", "UpdateCustomerUseCase", "customer"),
    "activate_customer": ("customers.use_cases.lifecycle_use_cases", "ActivateCustomerUseCase", "customer"),
    "deactivate_customer": ("customers.use_cases.lifecycle_use_cases", "DeactivateCustomerUseCase", "customer"),
    "suspend_customer": ("customers.use_cases.lifecycle_use_cases", "SuspendCustomerUseCase", "customer"),
    "block_customer": ("customers.use_cases.lifecycle_use_cases", "BlockCustomerUseCase", "customer"),
    "close_customer": ("customers.use_cases.lifecycle_use_cases", "CloseCustomerUseCase", "customer"),
    "set_customer_birthday": ("customers.use_cases.birthday_use_cases", "SetCustomerBirthdayUseCase", "customer"),
    "add_contact": ("customers.use_cases.contact_use_cases", "AddCustomerContactUseCase", "customer"),
    "update_contact": ("customers.use_cases.contact_use_cases", "UpdateCustomerContactUseCase", "customer"),
    "set_primary_contact": ("customers.use_cases.contact_use_cases", "SetPrimaryCustomerContactUseCase", "customer"),
    "remove_contact": ("customers.use_cases.contact_use_cases", "RemoveCustomerContactUseCase", "customer"),
    "add_address": ("customers.use_cases.address_use_cases", "AddCustomerAddressUseCase", "customer"),
    "update_address": ("customers.use_cases.address_use_cases", "UpdateCustomerAddressUseCase", "customer"),
    "set_default_address": ("customers.use_cases.address_use_cases", "SetDefaultCustomerAddressUseCase", "customer"),
    "remove_address": ("customers.use_cases.address_use_cases", "RemoveCustomerAddressUseCase", "customer"),
    "update_tax_profile": ("customers.use_cases.tax_profile_use_cases", "UpdateCustomerTaxProfileUseCase", "customer"),
    "create_account": ("customers.use_cases.account_use_cases", "CreateCustomerAccountUseCase", "customer"),
    "update_account": ("customers.use_cases.account_use_cases", "UpdateCustomerAccountUseCase", "customer"),
    "scan_data_quality": ("customers.use_cases.data_quality_use_cases", "RunCustomerDataQualityScanUseCase", "customer"),
    "acknowledge_quality_issue": ("customers.use_cases.data_quality_use_cases", "AcknowledgeDataQualityIssueUseCase", "customer"),
    "correct_quality_issue": ("customers.use_cases.data_quality_use_cases", "CorrectDataQualityIssueUseCase", "customer"),
    "dismiss_quality_issue": ("customers.use_cases.data_quality_use_cases", "DismissDataQualityIssueUseCase", "customer"),
    "detect_duplicates": ("customers.use_cases.duplicate_use_cases", "DetectDuplicateCandidatesUseCase", "customer"),
    "review_duplicate": ("customers.use_cases.duplicate_use_cases", "ReviewDuplicateCandidateUseCase", "customer"),
    "confirm_duplicate": ("customers.use_cases.duplicate_use_cases", "ConfirmDuplicateCandidateUseCase", "customer"),
    "dismiss_duplicate": ("customers.use_cases.duplicate_use_cases", "DismissDuplicateCandidateUseCase", "customer"),
    "propose_merge": ("customers.use_cases.merge_use_cases", "ProposeCustomerMergeUseCase", "customer"),
    "execute_merge": ("customers.use_cases.merge_use_cases", "ExecuteCustomerMergeUseCase", "customer"),
    "reject_merge": ("customers.use_cases.merge_use_cases", "RejectCustomerMergeUseCase", "customer"),
    "import_customers": ("customers.use_cases.import_use_cases", "ImportCustomersUseCase", "customer"),
    "approve_import": ("customers.use_cases.import_use_cases", "ApproveCustomerImportUseCase", "customer"),
    "reject_import": ("customers.use_cases.import_use_cases", "RejectCustomerImportUseCase", "customer"),
    "resolve_customer_sync_conflict": ("customers.use_cases.sync_conflict_use_cases", "ResolveCustomerSyncConflictUseCase", "customer"),
    # ── prospectos ───────────────────────────────────────────────────────────
    "create_lead": ("crm.use_cases.lead_use_cases", "CreateLeadUseCase", "crm"),
    "update_lead": ("crm.use_cases.lead_use_cases", "UpdateLeadUseCase", "crm"),
    "assign_lead": ("crm.use_cases.lead_use_cases", "AssignLeadUseCase", "crm"),
    "mark_lead_contacted": ("crm.use_cases.lead_use_cases", "MarkLeadContactedUseCase", "crm"),
    "start_lead_nurturing": ("crm.use_cases.lead_use_cases", "StartLeadNurturingUseCase", "crm"),
    "qualify_lead": ("crm.use_cases.lead_use_cases", "QualifyLeadUseCase", "crm"),
    "disqualify_lead": ("crm.use_cases.lead_use_cases", "DisqualifyLeadUseCase", "crm"),
    "lose_lead": ("crm.use_cases.lead_use_cases", "LoseLeadUseCase", "crm"),
    "archive_lead": ("crm.use_cases.lead_use_cases", "ArchiveLeadUseCase", "crm"),
    "convert_lead": ("crm.use_cases.convert_lead_use_case", "ConvertLeadUseCase", "both"),
    "create_opportunity_from_lead": ("crm.use_cases.create_opportunity_from_lead_use_case", "CreateOpportunityFromLeadUseCase", "crm"),
    # ── oportunidades ────────────────────────────────────────────────────────
    "create_opportunity": ("crm.use_cases.opportunity_use_cases", "CreateOpportunityUseCase", "crm"),
    "update_opportunity": ("crm.use_cases.opportunity_use_cases", "UpdateOpportunityUseCase", "crm"),
    "assign_opportunity": ("crm.use_cases.opportunity_use_cases", "AssignOpportunityUseCase", "crm"),
    "move_opportunity_stage": ("crm.use_cases.opportunity_use_cases", "MoveOpportunityStageUseCase", "crm"),
    "win_opportunity": ("crm.use_cases.opportunity_use_cases", "WinOpportunityUseCase", "crm"),
    "lose_opportunity": ("crm.use_cases.opportunity_use_cases", "LoseOpportunityUseCase", "crm"),
    "hold_opportunity": ("crm.use_cases.opportunity_use_cases", "PutOpportunityOnHoldUseCase", "crm"),
    "resume_opportunity": ("crm.use_cases.opportunity_use_cases", "ResumeOpportunityUseCase", "crm"),
    "cancel_opportunity": ("crm.use_cases.opportunity_use_cases", "CancelOpportunityUseCase", "crm"),
    "reopen_opportunity": ("crm.use_cases.opportunity_use_cases", "ReopenOpportunityUseCase", "crm"),
    "add_product_interest": ("crm.use_cases.opportunity_use_cases", "AddOpportunityProductInterestUseCase", "crm"),
    "create_stage": ("crm.use_cases.stage_definition_use_cases", "CreateStageDefinitionUseCase", "crm"),
    "update_stage": ("crm.use_cases.stage_definition_use_cases", "UpdateStageDefinitionUseCase", "crm"),
    "move_stage": ("crm.use_cases.stage_definition_use_cases", "MoveStageDefinitionUseCase", "crm"),
    "deactivate_stage": ("crm.use_cases.stage_definition_use_cases", "DeactivateStageDefinitionUseCase", "crm"),
    # ── actividades, tareas, notas, recordatorios ───────────────────────────
    "create_activity": ("crm.use_cases.activity_use_cases", "CreateCRMActivityUseCase", "crm"),
    "start_activity": ("crm.use_cases.activity_use_cases", "StartCRMActivityUseCase", "crm"),
    "complete_activity": ("crm.use_cases.activity_use_cases", "CompleteCRMActivityUseCase", "crm"),
    "cancel_activity": ("crm.use_cases.activity_use_cases", "CancelCRMActivityUseCase", "crm"),
    "reschedule_activity": ("crm.use_cases.activity_use_cases", "RescheduleCRMActivityUseCase", "crm"),
    "reassign_activity": ("crm.use_cases.activity_use_cases", "ReassignCRMActivityUseCase", "crm"),
    "create_task": ("crm.use_cases.task_use_cases", "CreateCRMTaskUseCase", "crm"),
    "complete_task": ("crm.use_cases.task_use_cases", "CompleteCRMTaskUseCase", "crm"),
    "cancel_task": ("crm.use_cases.task_use_cases", "CancelCRMTaskUseCase", "crm"),
    "reschedule_task": ("crm.use_cases.task_use_cases", "RescheduleCRMTaskUseCase", "crm"),
    "assign_task": ("crm.use_cases.task_use_cases", "AssignCRMTaskUseCase", "crm"),
    "create_note": ("crm.use_cases.note_use_cases", "CreateCRMNoteUseCase", "crm"),
    "update_note": ("crm.use_cases.note_use_cases", "UpdateCRMNoteUseCase", "crm"),
    "delete_note": ("crm.use_cases.note_use_cases", "DeleteCRMNoteUseCase", "crm"),
    "create_reminder": ("crm.use_cases.reminder_use_cases", "CreateCRMReminderUseCase", "crm"),
    # ── segmentación, propietarios, territorios, carteras ─────────────────────
    "create_segment": ("crm.use_cases.segment_use_cases", "CreateCustomerSegmentUseCase", "crm"),
    "deactivate_segment": ("crm.use_cases.segment_use_cases", "DeactivateCustomerSegmentUseCase", "crm"),
    "add_to_segment": ("crm.use_cases.segment_use_cases", "AddCustomerToSegmentUseCase", "crm"),
    "remove_from_segment": ("crm.use_cases.segment_use_cases", "RemoveCustomerFromSegmentUseCase", "crm"),
    "create_tag": ("crm.use_cases.tag_use_cases", "CreateCustomerTagUseCase", "crm"),
    "deactivate_tag": ("crm.use_cases.tag_use_cases", "DeactivateCustomerTagUseCase", "crm"),
    "assign_tag": ("crm.use_cases.tag_use_cases", "AssignCustomerTagUseCase", "crm"),
    "remove_tag": ("crm.use_cases.tag_use_cases", "RemoveCustomerTagUseCase", "crm"),
    "create_territory": ("crm.use_cases.territory_use_cases", "CreateSalesTerritoryUseCase", "crm"),
    "deactivate_territory": ("crm.use_cases.territory_use_cases", "DeactivateSalesTerritoryUseCase", "crm"),
    "assign_territory": ("crm.use_cases.territory_use_cases", "AssignCustomerTerritoryUseCase", "crm"),
    "create_portfolio": ("crm.use_cases.portfolio_use_cases", "CreateCustomerPortfolioUseCase", "crm"),
    "deactivate_portfolio": ("crm.use_cases.portfolio_use_cases", "DeactivateCustomerPortfolioUseCase", "crm"),
    "assign_portfolio": ("crm.use_cases.portfolio_use_cases", "AssignCustomerPortfolioUseCase", "crm"),
    "assign_owner": ("crm.use_cases.ownership_use_cases", "AssignCustomerOwnerUseCase", "crm_kw"),
    # ── automatizaciones y conflictos ─────────────────────────────────────────
    "create_automation": ("crm.use_cases.automation_use_cases", "CreateAutomationRuleUseCase", "crm"),
    "update_automation": ("crm.use_cases.automation_use_cases", "UpdateAutomationRuleUseCase", "crm"),
    "activate_automation": ("crm.use_cases.automation_use_cases", "ActivateAutomationRuleUseCase", "crm"),
    "deactivate_automation": ("crm.use_cases.automation_use_cases", "DeactivateAutomationRuleUseCase", "crm"),
    "resolve_crm_sync_conflict": ("crm.use_cases.sync_conflict_use_cases", "ResolveCRMSyncConflictUseCase", "crm"),
    # ── atención al cliente ──────────────────────────────────────────────────
    "create_case": ("customer_service.use_cases.service_case_use_cases", "CreateServiceCaseUseCase", "crm"),
    "update_case": ("customer_service.use_cases.service_case_use_cases", "UpdateServiceCaseUseCase", "crm"),
    "assign_case": ("customer_service.use_cases.service_case_use_cases", "AssignServiceCaseUseCase", "crm"),
    "start_case": ("customer_service.use_cases.service_case_use_cases", "StartServiceCaseProgressUseCase", "crm"),
    "wait_customer_case": ("customer_service.use_cases.service_case_use_cases", "WaitForCustomerUseCase", "crm"),
    "wait_internal_case": ("customer_service.use_cases.service_case_use_cases", "WaitInternalUseCase", "crm"),
    "resume_case": ("customer_service.use_cases.service_case_use_cases", "ResumeServiceCaseUseCase", "crm"),
    "cancel_case": ("customer_service.use_cases.service_case_use_cases", "CancelServiceCaseUseCase", "crm"),
    "close_case": ("customer_service.use_cases.service_case_use_cases", "CloseServiceCaseUseCase", "crm"),
    "reopen_case": ("customer_service.use_cases.service_case_use_cases", "ReopenServiceCaseUseCase", "crm"),
    "first_response_case": ("customer_service.use_cases.service_case_use_cases", "RecordFirstResponseUseCase", "crm"),
    "resolve_case": ("customer_service.use_cases.service_case_use_cases", "ResolveServiceCaseUseCase", "crm"),
    "escalate_case": ("customer_service.use_cases.escalate_service_case_use_case", "EscalateServiceCaseUseCase", "crm"),
    "create_sla_policy": ("customer_service.use_cases.service_level_policy_use_cases", "CreateServiceLevelPolicyUseCase", "crm"),
    "override_sla": ("customer_service.use_cases.service_level_policy_use_cases", "OverrideSLAUseCase", "crm"),
    "deactivate_sla_policy": ("customer_service.use_cases.service_level_policy_use_cases", "DeactivateServiceLevelPolicyUseCase", "crm"),
    # ── crédito ──────────────────────────────────────────────────────────────
    "request_credit": ("customer_credit.use_cases.customer_credit_use_cases", "RequestCustomerCreditUseCase", "customer"),
    "review_credit": ("customer_credit.use_cases.customer_credit_use_cases", "ReviewCustomerCreditUseCase", "customer"),
    "approve_credit": ("customer_credit.use_cases.customer_credit_use_cases", "ApproveCustomerCreditUseCase", "customer"),
    "reject_credit": ("customer_credit.use_cases.customer_credit_use_cases", "RejectCustomerCreditUseCase", "customer"),
    "update_credit_limit": ("customer_credit.use_cases.customer_credit_use_cases", "UpdateCustomerCreditLimitUseCase", "customer"),
    "suspend_credit": ("customer_credit.use_cases.customer_credit_use_cases", "SuspendCustomerCreditUseCase", "customer"),
    "block_credit": ("customer_credit.use_cases.customer_credit_use_cases", "BlockCustomerCreditUseCase", "customer"),
    "reopen_credit": ("customer_credit.use_cases.customer_credit_use_cases", "ReopenCustomerCreditUseCase", "customer"),
    "close_credit": ("customer_credit.use_cases.customer_credit_use_cases", "CloseCustomerCreditUseCase", "customer"),
    # ── privacidad y comunicaciones ─────────────────────────────────────────
    "capture_consent": ("customer_privacy.use_cases.consent_use_cases", "CaptureConsentUseCase", "customer"),
    "request_consent": ("customer_privacy.use_cases.consent_use_cases", "RequestConsentUseCase", "customer"),
    "confirm_consent": ("customer_privacy.use_cases.consent_use_cases", "ConfirmConsentUseCase", "customer"),
    "withdraw_consent": ("customer_privacy.use_cases.consent_use_cases", "WithdrawConsentUseCase", "customer"),
    "consent_not_required": ("customer_privacy.use_cases.consent_use_cases", "MarkConsentNotRequiredUseCase", "customer"),
    "set_communication_preference": ("customer_privacy.use_cases.communication_preference_use_cases", "SetCommunicationPreferenceUseCase", "customer"),
    "create_privacy_request": ("customer_privacy.use_cases.privacy_request_use_cases", "CreatePrivacyRequestUseCase", "customer"),
    "validate_privacy_request": ("customer_privacy.use_cases.privacy_request_use_cases", "ValidatePrivacyRequestUseCase", "customer"),
    "process_privacy_request": ("customer_privacy.use_cases.privacy_request_use_cases", "StartProcessingPrivacyRequestUseCase", "customer"),
    "reject_privacy_request": ("customer_privacy.use_cases.privacy_request_use_cases", "RejectPrivacyRequestUseCase", "customer"),
    "cancel_privacy_request": ("customer_privacy.use_cases.privacy_request_use_cases", "CancelPrivacyRequestUseCase", "customer"),
    "complete_privacy_request": ("customer_privacy.use_cases.privacy_request_use_cases", "CompletePrivacyRequestUseCase", "customer"),
    "anonymize_customer": ("customer_privacy.use_cases.anonymize_customer_use_case", "AnonymizeCustomerUseCase", "authorizer"),
    "create_retention_policy": ("customer_privacy.use_cases.retention_policy_use_cases", "CreateDataRetentionPolicyUseCase", "customer"),
    "deactivate_retention_policy": ("customer_privacy.use_cases.retention_policy_use_cases", "DeactivateDataRetentionPolicyUseCase", "customer"),
}


def _use_case_class(module: str, name: str):
    return getattr(import_module(f"backend.application.{module}"), name)


def build_command_handlers(connection, customer_auth, crm_auth,
                           extra: dict[str, Callable] | None = None) -> dict[str, Callable]:
    handlers: dict[str, Callable] = {}
    for command, (module, class_name, policy) in _COMMANDS.items():
        def handler(*, _m=module, _c=class_name, _p=policy, **kwargs):
            cls = _use_case_class(_m, _c)
            if _p == "both":
                use_case = cls(crm_auth, customer_auth)
            elif _p == "crm_kw":
                use_case = cls(crm_authorization=crm_auth)
            elif _p == "crm":
                use_case = cls(crm_auth)
            else:
                use_case = cls(customer_auth)
            if _p == "authorizer":
                kwargs["authorizer_user_id"] = kwargs.pop("actor_user_id")
            run = use_case.execute
            return run(connection, **kwargs)
        handlers[command] = handler
    handlers.update(extra or {})
    return handlers


def _q(module: str, name: str):
    return getattr(import_module(f"backend.application.{module}"), name)


def build_readers(connection, *, customer_auth, crm_auth, customer_scope, crm_scope
                  ) -> dict[str, Callable]:
    """Lecturas para las pantallas. Cada lector recibe un ``CrmReadContext``."""
    ref = _q("crm.queries.crm_reference_query_service", "CRMReferenceQueryService")(
        connection, customer_auth)
    leads = _q("crm.queries.lead_directory_query_service", "LeadDirectoryQueryService")(
        connection, crm_scope, crm_auth)
    opps = _q("crm.queries.opportunity_directory_query_service",
              "OpportunityDirectoryQueryService")(connection, crm_scope)
    forecast = _q("crm.queries.sales_pipeline_forecast_query_service",
                  "SalesPipelineForecastQueryService")(connection, crm_scope)
    activities = _q("crm.queries.crm_activity_query_service", "CRMActivityQueryService")(
        connection, crm_auth)
    tasks = _q("crm.queries.crm_task_query_service", "CRMTaskQueryService")(connection, crm_auth)
    notes = _q("crm.queries.crm_note_query_service", "CRMNoteQueryService")(connection, crm_auth)
    calendar = _q("crm.queries.crm_calendar_query_service", "CRMCalendarQueryService")(
        connection, crm_auth)
    lookup = _q("customers.queries.customer_lookup_query_service",
                "CustomerLookupQueryService")(connection, customer_auth)
    cases = _q("customer_service.queries.service_case_query_service",
               "ServiceCaseQueryService")(connection, crm_scope, crm_auth)
    sla = _q("customer_service.queries.sla_query_service", "SLAQueryService")(connection, crm_auth)
    credit = _q("customer_credit.queries.customer_credit_query_service",
                "CustomerCreditQueryService")(connection, customer_auth)
    profiles = _q("customers.queries.customer_profile_query_service",
                  "CustomerProfileQueryService")(connection, customer_scope)
    display = import_module("backend.application.customers.queries.customer_display_profile")
    seg = _q("crm.queries.segmentation_admin_query_service",
             "SegmentationAdminQueryService")(connection, crm_auth)
    privacy = _q("customer_privacy.queries.privacy_admin_query_service",
                 "PrivacyAdminQueryService")(connection, customer_auth)
    consents = _q("customer_privacy.queries.customer_consent_query_service",
                  "CustomerConsentQueryService")(connection, customer_auth)
    preferences = _q("customer_privacy.queries.customer_communication_preference_query_service",
                     "CustomerCommunicationPreferenceQueryService")(connection, customer_auth)
    whatsapp = _q("customers.queries.customer_whatsapp_summary_query",
                  "CustomerWhatsAppSummaryQuery")(connection, customer_auth)
    audit = _q("customers.queries.audit_trail_query_service",
               "AuditTrailQueryService")(connection, customer_auth)
    control = _q("customers.queries.control_query_service",
                 "ControlQueryService")(connection, customer_auth)
    history = _q("customers.queries.customer_history_query_service",
                 "CustomerHistoryQueryService")(connection, customer_auth)
    insights = _q("crm.queries.crm_insights_query_service",
                  "CRMInsightsQueryService")(connection, crm_scope, crm_auth)
    directory = _q("customers.queries.customer_directory_query_service",
                   "CustomerDirectoryQueryService")(connection, customer_scope, customer_auth)
    automation = _q("crm.queries.automation_query_service",
                    "AutomationQueryService")(connection, crm_auth)
    preview = _q("customers.queries.customer_import_preview_query",
                 "CustomerImportPreviewQuery")(connection, customer_auth)

    def _categories():
        from backend.infrastructure.db.repositories.customer_service.unit_of_work import (
            CustomerServiceUnitOfWork,
        )
        return CustomerServiceUnitOfWork(connection).categories.list_active()

    return {
        "assignable_users": lambda ctx: ref.assignable_users(actor_user_id=ctx.user_id),
        "customer_names": lambda ctx, customer_ids: ref.customer_names(
            customer_ids, actor_user_id=ctx.user_id),
        "branch_names": lambda ctx: ref.branch_names(actor_user_id=ctx.user_id),
        "related_names": lambda ctx, pairs: ref.related_names(pairs, actor_user_id=ctx.user_id),
        "stages": lambda ctx, include_inactive=False: ref.stages(
            actor_user_id=ctx.user_id, include_inactive=include_inactive),
        "customer_lookup": lambda ctx, query, limit=20: lookup.lookup(
            query, actor_user_id=ctx.user_id, limit=limit),
        "leads": lambda ctx, limit=500: leads.list_directory(ctx.crm(), limit=limit),
        "lead_profile": lambda ctx, lead_id: leads.get_profile(lead_id, ctx.crm()),
        "opportunities": lambda ctx, limit=500: opps.list_directory(ctx.crm(), limit=limit),
        "opportunity_profile": lambda ctx, opportunity_id: opps.get_profile(
            opportunity_id, ctx.crm()),
        "pipeline": lambda ctx: opps.list_by_stage_for_kanban(ctx.crm()),
        "opportunity_rows": lambda ctx, limit=500: opps.list_rows(ctx.crm(), limit=limit),
        "notes_mine": lambda ctx: notes.list_mine(actor_user_id=ctx.user_id),
        "forecast": lambda ctx: forecast.get_forecast(ctx.crm()),
        "activities_for_user": lambda ctx, user_id=None: activities.list_assigned_to(
            user_id or ctx.user_id, actor_user_id=ctx.user_id),
        "activities_for": lambda ctx, entity_type, entity_id: activities.list_for_related_entity(
            entity_type, entity_id, actor_user_id=ctx.user_id),
        "tasks_for_user": lambda ctx, user_id=None: tasks.list_assigned_to(
            user_id or ctx.user_id, actor_user_id=ctx.user_id),
        "tasks_for": lambda ctx, entity_type, entity_id: tasks.list_for_related_entity(
            entity_type, entity_id, actor_user_id=ctx.user_id),
        "notes_for": lambda ctx, entity_type, entity_id: notes.list_for_related_entity(
            entity_type, entity_id, actor_user_id=ctx.user_id),
        "calendar": lambda ctx, start_date, end_date, user_id=None: calendar.get_calendar(
            user_id or ctx.user_id, actor_user_id=ctx.user_id, start_date=start_date,
            end_date=end_date),
        "cases": lambda ctx, limit=500: cases.list_directory(ctx.crm(), limit=limit),
        "case_profile": lambda ctx, case_id: cases.get_profile(case_id, ctx.crm()),
        "case_rows": lambda ctx, limit=500: cases.list_rows(ctx.crm(), limit=limit),
        "case_detail": lambda ctx, case_id: cases.get_detail(case_id, ctx.crm()),
        "sla_policies": lambda ctx: sla.list_policies(actor_user_id=ctx.user_id),
        "sla_breached": lambda ctx: sla.list_breached(actor_user_id=ctx.user_id),
        "sla_at_risk": lambda ctx: sla.list_at_risk(actor_user_id=ctx.user_id),
        "case_categories": lambda ctx: _categories(),
        "customer_profile": lambda ctx, customer_id: display.display_profile(
            profiles, customer_auth, customer_id, ctx.customers()),
        "segments": lambda ctx: seg.segments(actor_user_id=ctx.user_id),
        "segment_members": lambda ctx, segment_id: seg.segment_members(
            segment_id, actor_user_id=ctx.user_id),
        "tags": lambda ctx: seg.tags(actor_user_id=ctx.user_id),
        "tag_members": lambda ctx, tag_id: seg.tag_members(tag_id, actor_user_id=ctx.user_id),
        "territories": lambda ctx: seg.territories(actor_user_id=ctx.user_id),
        "territory_members": lambda ctx, territory_id: seg.territory_members(
            territory_id, actor_user_id=ctx.user_id),
        "portfolios": lambda ctx: seg.portfolios(actor_user_id=ctx.user_id),
        "portfolio_members": lambda ctx, portfolio_id: seg.portfolio_members(
            portfolio_id, actor_user_id=ctx.user_id),
        "owners": lambda ctx, customer_ids: seg.owners(customer_ids, actor_user_id=ctx.user_id),
        "owner_history": lambda ctx, customer_id: seg.owner_history(
            customer_id, actor_user_id=ctx.user_id),
        "automation_rules": lambda ctx: automation.rules(actor_user_id=ctx.user_id),
        "automation_executions": lambda ctx: automation.executions(actor_user_id=ctx.user_id),
        "insights": lambda ctx: insights.get(ctx.crm()),
        "customer_rows": lambda ctx, limit=1000: directory.list_rows(ctx.customers(),
                                                                     limit=limit),
        "purchase_history": lambda ctx, customer_id: history.get_purchase_history(
            customer_id, actor_user_id=ctx.user_id),
        "payment_history": lambda ctx, customer_id: history.get_payment_history(
            customer_id, actor_user_id=ctx.user_id),
        "return_history": lambda ctx, customer_id: history.get_return_history(
            customer_id, actor_user_id=ctx.user_id),
        "order_history": lambda ctx, customer_id: history.get_order_history(
            customer_id, actor_user_id=ctx.user_id),
        "quote_history": lambda ctx, customer_id: history.get_quote_history(
            customer_id, actor_user_id=ctx.user_id),
        "product_affinity": lambda ctx, customer_id: history.get_product_affinity(
            customer_id, actor_user_id=ctx.user_id),
        "duplicates": lambda ctx, include_closed=False: control.duplicates(
            actor_user_id=ctx.user_id, include_closed=include_closed),
        "merges": lambda ctx: control.merges(actor_user_id=ctx.user_id),
        "import_batches": lambda ctx: control.import_batches(actor_user_id=ctx.user_id),
        "quality_issues": lambda ctx, statuses=("OPEN", "ACKNOWLEDGED"): control.quality_issues(
            actor_user_id=ctx.user_id, statuses=tuple(statuses)),
        "import_preview": lambda ctx, rows: preview.preview(rows, actor_user_id=ctx.user_id),
        "audit_trail": lambda ctx, module=None, action=None: audit.recent(
            actor_user_id=ctx.user_id, module=module, action=action),
        "exports_history": lambda ctx: audit.exports(actor_user_id=ctx.user_id),
        "privacy_requests": lambda ctx: privacy.requests(actor_user_id=ctx.user_id),
        "privacy_trail": lambda ctx, request_id: privacy.request_trail(
            request_id, actor_user_id=ctx.user_id),
        "retention_policies": lambda ctx: privacy.retention_policies(actor_user_id=ctx.user_id),
        "notification_history": lambda ctx, customer_id: privacy.notification_history(
            customer_id, actor_user_id=ctx.user_id),
        "consents_for": lambda ctx, customer_id: consents.list_for_customer(
            customer_id, actor_user_id=ctx.user_id),
        "preference_for": lambda ctx, customer_id: preferences.get(
            customer_id, actor_user_id=ctx.user_id),
        "whatsapp_summary": lambda ctx, customer_id: whatsapp.get_summary(
            customer_id, actor_user_id=ctx.user_id),
        "customers": lambda ctx, limit=1000: profiles.list_directory(ctx.customers(),
                                                                     limit=limit),
        "credit_rows": lambda ctx, statuses=(): credit.list_rows(
            actor_user_id=ctx.user_id, statuses=tuple(statuses)),
        "credit_summary": lambda ctx, customer_id: credit.get_summary(
            customer_id, actor_user_id=ctx.user_id),
        "credit_history": lambda ctx, customer_id=None: credit.history(
            actor_user_id=ctx.user_id, customer_id=customer_id),
    }


def build_customers_crm_presenter(connection, session_context=None):
    from backend.application.crm.queries.customer_dashboard_query_service import (
        CustomerDashboardQueryService,
    )
    from backend.application.customers.queries.customer_360_query_service import (
        Customer360QueryService,
    )
    from backend.application.customers.queries.customer_profile_query_service import (
        CustomerProfileQueryService,
    )
    from backend.application.customers.use_cases.birthday_use_cases import customer_birthday
    from frontend.desktop.modules.customers_crm.customers_crm_presenter import (
        CustomerCrmPresenter,
    )

    checker = CustomerSessionPermissionChecker(session_context)
    customer_auth = CustomerAuthorizationPolicy(checker)
    crm_auth = CRMAuthorizationPolicy(checker)
    customer_scope = CustomerDataScopeResolver(checker)
    crm_scope = CRMDataScopeResolver(checker)

    query_services = {
        "dashboard": CustomerDashboardQueryService(connection, crm_scope, crm_auth),
        "customer_360": Customer360QueryService(
            connection, customer_scope, crm_scope, customer_auth, crm_auth),
        "customer_birthday": lambda customer_id: customer_birthday(connection, customer_id),
    }

    def _address_search_factory():
        from backend.infrastructure.maps.address_search_factory import (
            build_address_search_service,
        )
        return build_address_search_service(connection)

    readers = build_readers(connection, customer_auth=customer_auth, crm_auth=crm_auth,
                            customer_scope=customer_scope, crm_scope=crm_scope)

    def _session_ctx():
        from backend.application.customers.read_context import CrmReadContext
        branch = str(getattr(session_context, "active_branch_id", "") or "") or None
        return CrmReadContext(user_id=str(getattr(session_context, "user_id", "") or ""),
                              branch_id=branch)

    def _export(**kwargs):
        from backend.application.customers.use_cases.export_use_cases import (
            ExportCustomerDataUseCase,
        )
        profiles_service = CustomerProfileQueryService(connection, customer_scope)
        ctx = _session_ctx()
        export_readers = {
            "customers": lambda: readers["customers"](ctx, limit=100_000),
            "customer_profile_raw": lambda cid: profiles_service.get_profile(
                cid, ctx.customers()),
            "leads": lambda: readers["leads"](ctx, limit=100_000),
            "opportunities": lambda: readers["opportunities"](ctx, limit=100_000),
            "activities": lambda: readers["activities_for_user"](ctx),
            "customer_names": lambda ids: readers["customer_names"](ctx, customer_ids=list(ids)),
            "stage_names": lambda: {s.id: s.name for s in readers["stages"](
                ctx, include_inactive=True)},
        }
        run = ExportCustomerDataUseCase(customer_auth, readers=export_readers).execute
        return run(connection, **kwargs)

    return CustomerCrmPresenter(
        session_context=session_context,
        query_services=query_services,
        command_handlers=build_command_handlers(connection, customer_auth, crm_auth,
                                                extra={"export_data": _export}),
        readers=readers,
        address_search_factory=_address_search_factory,
    )
