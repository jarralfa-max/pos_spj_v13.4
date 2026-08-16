"""Granular CRM (relationship) permission codes (CRM-2, master prompt §64-67, §69).

Covers Leads, Opportunities/Pipeline/Forecast, Activities/Tasks/Notes,
Service Cases/SLA, and Segmentation/Tags/Territories/Portfolios/Ownership.
Same ``MODULO.accion`` vocabulary as ``CustomerPermissions`` — see that
module's docstring for the format rationale and precedent
(``backend/application/inventory/permissions.py``).
"""

from __future__ import annotations


class CRMPermissions:
    # ── leads (§64) — ejes OWN/TEAM sobre lectura ─────────────────────────
    LEADS_VIEW = "CRM.leads.ver"
    LEADS_VIEW_OWN = "CRM.leads.ver.propia"
    LEADS_VIEW_TEAM = "CRM.leads.ver.equipo"
    LEADS_CREATE = "CRM.leads.crear"
    LEADS_EDIT = "CRM.leads.editar"
    LEADS_ASSIGN = "CRM.leads.asignar"
    LEADS_REASSIGN = "CRM.leads.reasignar"
    LEADS_QUALIFY = "CRM.leads.calificar"
    LEADS_DISQUALIFY = "CRM.leads.descalificar"
    LEADS_CONVERT = "CRM.leads.convertir"
    LEADS_ARCHIVE = "CRM.leads.archivar"
    LEADS_EXPORT = "CRM.leads.exportar"

    # ── oportunidades / pipeline / forecast (§65) ─────────────────────────
    OPPORTUNITIES_VIEW = "CRM.oportunidades.ver"
    OPPORTUNITIES_VIEW_OWN = "CRM.oportunidades.ver.propia"
    OPPORTUNITIES_VIEW_TEAM = "CRM.oportunidades.ver.equipo"
    OPPORTUNITIES_CREATE = "CRM.oportunidades.crear"
    OPPORTUNITIES_EDIT = "CRM.oportunidades.editar"
    OPPORTUNITIES_ASSIGN = "CRM.oportunidades.asignar"
    OPPORTUNITIES_REASSIGN = "CRM.oportunidades.reasignar"
    OPPORTUNITIES_CHANGE_STAGE = "CRM.oportunidades.cambiar_etapa"
    OPPORTUNITIES_OVERRIDE_STAGE = "CRM.oportunidades.sobrescribir_etapa"
    OPPORTUNITIES_MARK_WON = "CRM.oportunidades.marcar_ganada"
    OPPORTUNITIES_MARK_LOST = "CRM.oportunidades.marcar_perdida"
    OPPORTUNITIES_REOPEN = "CRM.oportunidades.reabrir"
    PIPELINE_VIEW = "CRM.pipeline.ver"
    FORECAST_VIEW = "CRM.forecast.ver"
    FORECAST_VIEW_TEAM = "CRM.forecast.ver.equipo"
    FORECAST_VIEW_COMPANY = "CRM.forecast.ver.compania"

    # ── actividades, tareas, notas (§66) ──────────────────────────────────
    ACTIVITIES_VIEW = "CRM.actividades.ver"
    ACTIVITIES_CREATE = "CRM.actividades.crear"
    ACTIVITIES_EDIT = "CRM.actividades.editar"
    ACTIVITIES_COMPLETE = "CRM.actividades.completar"
    ACTIVITIES_CANCEL = "CRM.actividades.cancelar"
    ACTIVITIES_REASSIGN = "CRM.actividades.reasignar"

    TASKS_VIEW = "CRM.tareas.ver"
    TASKS_CREATE = "CRM.tareas.crear"
    TASKS_ASSIGN = "CRM.tareas.asignar"
    TASKS_REASSIGN = "CRM.tareas.reasignar"
    TASKS_COMPLETE = "CRM.tareas.completar"
    TASKS_CANCEL = "CRM.tareas.cancelar"
    # CRM-6 retroactive addition: §23-26 names RescheduleCRMTaskUseCase
    # explicitly, but CRM-2's original catalog didn't anticipate a
    # dedicated "reschedule" action distinct from assign/complete/cancel —
    # same kind of gap as CustomerPermissions.DEACTIVATE added retroactively
    # in CRM-3. Reusing TASKS_ASSIGN for reschedule would have been a
    # semantic mismatch (rescheduling isn't reassigning), so this adds the
    # missing code instead of overloading an existing one.
    TASKS_RESCHEDULE = "CRM.tareas.reprogramar"

    NOTES_VIEW = "CRM.notas.ver"
    NOTES_CREATE = "CRM.notas.crear"
    NOTES_EDIT_OWN = "CRM.notas.editar.propia"
    NOTES_DELETE_OWN = "CRM.notas.eliminar.propia"
    NOTES_VIEW_PRIVATE = "CRM.notas.ver.privada"
    NOTES_CREATE_PRIVATE = "CRM.notas.crear.privada"

    # CRM-6 retroactive addition: §26 describes CRMReminder ("CRM solo
    # define recordatorio/destinatario") but CRM-2's catalog never defined
    # a permission for it — no ACTIVITIES_*/TASKS_* code fits a reminder
    # semantically (it isn't completing or cancelling anything), so this
    # adds a dedicated code rather than reusing an unrelated one.
    REMINDERS_CREATE = "CRM.recordatorios.crear"

    # ── atención al cliente / SLA (§67) ───────────────────────────────────
    CASES_VIEW = "CRM.casos.ver"
    CASES_VIEW_OWN = "CRM.casos.ver.propia"
    CASES_VIEW_TEAM = "CRM.casos.ver.equipo"
    CASES_CREATE = "CRM.casos.crear"
    CASES_EDIT = "CRM.casos.editar"
    CASES_ASSIGN = "CRM.casos.asignar"
    CASES_REASSIGN = "CRM.casos.reasignar"
    CASES_ESCALATE = "CRM.casos.escalar"
    CASES_RESOLVE = "CRM.casos.resolver"
    CASES_CLOSE = "CRM.casos.cerrar"
    CASES_REOPEN = "CRM.casos.reabrir"
    CASES_VIEW_SENSITIVE = "CRM.casos.ver.sensible"
    SLA_VIEW = "CRM.sla.ver"
    SLA_MANAGE = "CRM.sla.gestionar"
    SLA_OVERRIDE = "CRM.sla.sobrescribir"

    # ── segmentación, territorios, carteras, propietario (§69) ────────────
    SEGMENTS_VIEW = "CRM.segmentos.ver"
    SEGMENTS_CREATE = "CRM.segmentos.crear"
    SEGMENTS_EDIT = "CRM.segmentos.editar"
    SEGMENTS_ASSIGN = "CRM.segmentos.asignar"
    SEGMENTS_REMOVE = "CRM.segmentos.remover"

    TAGS_VIEW = "CRM.etiquetas.ver"
    TAGS_CREATE = "CRM.etiquetas.crear"
    TAGS_EDIT = "CRM.etiquetas.editar"
    TAGS_ASSIGN = "CRM.etiquetas.asignar"
    TAGS_REMOVE = "CRM.etiquetas.remover"

    TERRITORIES_VIEW = "CRM.territorios.ver"
    TERRITORIES_MANAGE = "CRM.territorios.gestionar"
    PORTFOLIOS_VIEW = "CRM.carteras.ver"
    PORTFOLIOS_MANAGE = "CRM.carteras.gestionar"
    # CRM-10 retroactive addition: §33-36/§73 ("reasignar cartera... requiere
    # motivo") implies a dedicated, reason-gated action for putting a
    # specific customer into a portfolio — distinct from PORTFOLIOS_MANAGE,
    # which governs the portfolio *catalog* (create/edit/deactivate a
    # cartera), not membership in one. Same gap-filling rationale as
    # CRM-6's TASKS_RESCHEDULE/REMINDERS_CREATE and CRM-8's CREDIT_CLOSE.
    # No separate "reassign" code: unlike leads/opportunities/tasks/cases,
    # the catalog has no signal singling out portfolio *reassignment* as a
    # distinct permission from first assignment, so one code covers both —
    # the SoD reason requirement (enforce_ownership_reassignment_justified)
    # is what actually gates reassignment, not a second permission code.
    PORTFOLIOS_ASSIGN = "CRM.carteras.asignar"
    CUSTOMER_OWNER_VIEW = "CRM.propietario.ver"
    CUSTOMER_OWNER_ASSIGN = "CRM.propietario.asignar"
    CUSTOMER_OWNER_REASSIGN = "CRM.propietario.reasignar"

    # ── BI (§49-55, CRM-13 retroactive addition) ───────────────────────────
    # §55: "CRM expone leads/conversiones/pipeline/actividad/oportunidades/
    # casos/SLA/segmentos... BI calcula CLV/churn/... " — CRM-2's catalog had
    # no permission for exposing an aggregate company-wide snapshot to a
    # separate BI module; §73's "exportar datos sensibles deja evidencia"
    # implies this needs its own gate, distinct from any single VIEW
    # permission (an export sees across leads/opportunities/cases/segments
    # at once, at COMPANY scope, not one entity at a time).
    BI_EXPORT_VIEW = "CRM.bi.exportar"

    # ── automatizaciones (§56, CRM-26) ─────────────────────────────────────
    # A rule's ACTION still requires its own target permission when it fires
    # (e.g. CREATE_TASK checks TASKS_CREATE via CreateCRMTaskUseCase itself)
    # — these codes gate the rule ENGINE (who can define/toggle automation),
    # not a bypass around each action's own authorization.
    AUTOMATION_RULES_VIEW = "CRM.automatizaciones.ver"
    AUTOMATION_RULES_CREATE = "CRM.automatizaciones.crear"
    AUTOMATION_RULES_EDIT = "CRM.automatizaciones.editar"
    AUTOMATION_RULES_ACTIVATE = "CRM.automatizaciones.activar"
    AUTOMATION_RULES_DEACTIVATE = "CRM.automatizaciones.desactivar"
    AUTOMATION_EXECUTIONS_VIEW = "CRM.automatizaciones.ver_ejecuciones"

    # ── offline-first sync conflicts (§91-92, CRM-20) ──────────────────────
    SYNC_CONFLICTS_VIEW = "CRM.sync_conflictos.ver"
    SYNC_CONFLICTS_RESOLVE = "CRM.sync_conflictos.resolver"


ALL_CRM_PERMISSIONS = frozenset(
    v for k, v in vars(CRMPermissions).items()
    if not k.startswith("_") and isinstance(v, str)
)

# Scope-suffixed view permissions per entity family, narrowest → widest.
# Company-wide CRM read access ("todas las oportunidades/leads/casos de la
# empresa") shares CustomerPermissions.VIEW_COMPANY — one COMPANY axis for
# the whole Clientes/CRM module, not one per entity.
LEAD_VIEW_SCOPE_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("OWN", CRMPermissions.LEADS_VIEW_OWN),
    ("TEAM", CRMPermissions.LEADS_VIEW_TEAM),
)
OPPORTUNITY_VIEW_SCOPE_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("OWN", CRMPermissions.OPPORTUNITIES_VIEW_OWN),
    ("TEAM", CRMPermissions.OPPORTUNITIES_VIEW_TEAM),
)
CASE_VIEW_SCOPE_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("OWN", CRMPermissions.CASES_VIEW_OWN),
    ("TEAM", CRMPermissions.CASES_VIEW_TEAM),
)
