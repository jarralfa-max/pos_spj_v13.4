"""CRM offline-first sync conflicts (§91-92, CRM-20). Mirrors
backend/application/customers/use_cases/sync_conflict_use_cases.py.

Detection is entity-agnostic by design: it takes ``local_updated_at``
(already fetched by the caller, who already holds the Lead/Opportunity/
CRMTask/ServiceCase in hand) rather than looking the entity up itself —
avoids this file needing to import all four target packages'
UnitOfWork/repositories (Cases live in ``customer_service``, a sibling
bounded context) just to read one timestamp. Resolution's REMOTE/MERGED
field-application is only wired for LEAD today — the one entity this phase
had time to fully verify end-to-end; OPPORTUNITY/TASK/CASE can still be
detected and marked RESOLVED_LOCAL/RESOLVED_REMOTE/RESOLVED_MERGED (closing
the conflict), but REMOTE/MERGED field application for those three is a
documented gap, not a silent no-op — see the docstring on
ResolveCRMSyncConflictUseCase.
"""

from __future__ import annotations

import json

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.result import CRMResult
from backend.domain.crm.entities.crm_sync_conflict import CRMSyncConflict
from backend.domain.crm.enums import CRMSyncConflictType, SyncConflictStatus
from backend.domain.crm.events import CRMEvents, build_event_payload
from backend.domain.crm.exceptions import CRMDomainError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork

_RESOLUTION_MAP = {
    "LOCAL": SyncConflictStatus.RESOLVED_LOCAL,
    "REMOTE": SyncConflictStatus.RESOLVED_REMOTE,
    "MERGED": SyncConflictStatus.RESOLVED_MERGED,
}
_LEAD_APPLICABLE_FIELDS = ("display_name", "company_name", "contact_name")


class _BaseUseCase:
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()

    def _emit(self, uow, event_name: str, conflict: CRMSyncConflict, operation_id: str,
              actor_user_id: str | None, **extra) -> None:
        payload = build_event_payload(
            event_name, operation_id=operation_id, user_id=actor_user_id,
            **{("lead_id" if conflict.related_entity_type == "LEAD" else "opportunity_id"):
               conflict.related_entity_id} if conflict.related_entity_type in ("LEAD", "OPPORTUNITY")
            else {}, **extra)
        uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload), operation_id)


class DetectCRMSyncConflictUseCase:
    """System-triggered (no actor_user_id/permission check), same reasoning
    as DetectCustomerSyncConflictUseCase and CRM-26's automation dispatch."""

    def execute(
        self, connection, *, related_entity_type: str, related_entity_id: str,
        local_updated_at: str, base_updated_at: str, remote_snapshot: dict,
        conflict_type: str, operation_id: str, detail: str = "",
    ) -> CRMResult:
        if local_updated_at == base_updated_at:
            return CRMResult.ok("Sin conflicto — sin cambios concurrentes",
                                entity_id=related_entity_id, operation_id=operation_id,
                                conflict=False)
        with CRMUnitOfWork(connection) as uow:
            try:
                conflict = CRMSyncConflict.detect(
                    related_entity_type, related_entity_id, CRMSyncConflictType(conflict_type),
                    local_updated_at, remote_snapshot, detail=detail, operation_id=operation_id)
            except (CRMDomainError, ValueError) as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.sync_conflicts.save(conflict)
            uow.audit.record(action="CRM_SYNC_CONFLICT_DETECTED", actor_user_id=None,
                             operation_id=operation_id,
                             after_json=json.dumps({"conflict_id": conflict.id,
                                                    "conflict_type": conflict.conflict_type.value}))
        return CRMResult.fail(
            "Conflicto de sincronización: la versión local cambió, el cambio remoto no se aplicó",
            "SYNC_CONFLICT", operation_id=operation_id, conflict=True, conflict_id=conflict.id)


class ResolveCRMSyncConflictUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, conflict_id: str, resolution: str,
        operation_id: str, resolution_note: str = "", merged_fields: dict | None = None,
    ) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.SYNC_CONFLICTS_RESOLVE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        outcome = _RESOLUTION_MAP.get(resolution)
        if outcome is None:
            return CRMResult.fail("resolution debe ser LOCAL, REMOTE o MERGED", "VALIDATION",
                                  operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            conflict = uow.sync_conflicts.get(conflict_id)
            if conflict is None:
                return CRMResult.fail("El conflicto no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            try:
                conflict.resolve(outcome, resolved_by_user_id=actor_user_id,
                                 resolution_note=resolution_note)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)

            applied = False
            if (outcome != SyncConflictStatus.RESOLVED_LOCAL
                    and conflict.related_entity_type == "LEAD"):
                lead = uow.leads.get(conflict.related_entity_id)
                if lead is not None:
                    source = merged_fields if outcome == SyncConflictStatus.RESOLVED_MERGED \
                        else conflict.remote_snapshot
                    for field_name in _LEAD_APPLICABLE_FIELDS:
                        if source and source.get(field_name) is not None:
                            setattr(lead, field_name, source[field_name])
                    lead.record_edit()
                    uow.leads.update(lead)
                    applied = True

            uow.sync_conflicts.update(conflict)
            uow.audit.record(action="CRM_SYNC_CONFLICT_RESOLVED", actor_user_id=actor_user_id,
                             operation_id=operation_id, reason=resolution_note,
                             after_json=json.dumps({"conflict_id": conflict.id,
                                                    "outcome": outcome.value, "applied": applied}))
            self._emit(uow, "CRM_SYNC_CONFLICT_RESOLVED", conflict, operation_id, actor_user_id,
                      conflict_id=conflict.id, outcome=outcome.value)
        return CRMResult.ok("Conflicto resuelto", entity_id=conflict_id,
                            operation_id=operation_id, outcome=outcome.value, applied=applied)
