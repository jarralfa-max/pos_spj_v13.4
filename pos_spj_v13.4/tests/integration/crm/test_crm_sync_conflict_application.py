"""CRM offline-first sync conflicts (§91-92, CRM-20) — LEAD is the fully
wired reference implementation (detect + resolve with real field
application); OPPORTUNITY is exercised for detect-only + RESOLVED_LOCAL
(documented: REMOTE/MERGED field application isn't wired for it yet)."""

from __future__ import annotations

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.use_cases.lead_use_cases import CreateLeadUseCase
from backend.application.crm.use_cases.opportunity_use_cases import CreateOpportunityUseCase
from backend.application.crm.use_cases.sync_conflict_use_cases import (
    DetectCRMSyncConflictUseCase,
    ResolveCRMSyncConflictUseCase,
)
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork

_ACTOR = "user-sync-admin"


class _AllowAllForActor:
    def __init__(self, user_id: str) -> None:
        self._user_id = user_id

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return user_id == self._user_id


def _admin_policy() -> CRMAuthorizationPolicy:
    return CRMAuthorizationPolicy(_AllowAllForActor(_ACTOR))


class TestDetectCRMSyncConflictLead:
    def test_matching_timestamp_reports_no_conflict(self, crm_conn):
        result = CreateLeadUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, display_name="Lead Sync", operation_id="op-lead-1")
        lead_id = result.entity_id
        with CRMUnitOfWork(crm_conn) as uow:
            lead = uow.leads.get(lead_id)

        detect_result = DetectCRMSyncConflictUseCase().execute(
            crm_conn, related_entity_type="LEAD", related_entity_id=lead_id,
            local_updated_at=lead.updated_at, base_updated_at=lead.updated_at,
            remote_snapshot={}, conflict_type="LEAD_ASSIGNMENT_CONFLICT",
            operation_id="op-detect-1")
        assert detect_result.success
        assert detect_result.data["conflict"] is False

    def test_stale_timestamp_creates_conflict_and_blocks(self, crm_conn):
        create_result = CreateLeadUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, display_name="Lead Sync 2", operation_id="op-lead-2")
        lead_id = create_result.entity_id
        with CRMUnitOfWork(crm_conn) as uow:
            original_updated_at = uow.leads.get(lead_id).updated_at

        from backend.application.crm.use_cases.lead_use_cases import UpdateLeadUseCase
        UpdateLeadUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, lead_id=lead_id, operation_id="op-edit-local",
            display_name="Editado localmente")
        with CRMUnitOfWork(crm_conn) as uow:
            current_lead = uow.leads.get(lead_id)
        # `updated_at` has second precision — two calls in the same test can
        # land in the same second, so force a distinguishable "local changed
        # since base" timestamp rather than depending on real elapsed time
        # (same fabricated-future-timestamp approach as the Opportunity test
        # below, which never depended on wall-clock timing at all).
        simulated_local_updated_at = "2099-01-01T00:00:00+00:00"

        detect_result = DetectCRMSyncConflictUseCase().execute(
            crm_conn, related_entity_type="LEAD", related_entity_id=lead_id,
            local_updated_at=simulated_local_updated_at, base_updated_at=original_updated_at,
            remote_snapshot={"display_name": "Editado remotamente"},
            conflict_type="LEAD_ASSIGNMENT_CONFLICT", operation_id="op-detect-2")

        assert not detect_result.success
        assert detect_result.error_code == "SYNC_CONFLICT"
        with CRMUnitOfWork(crm_conn) as uow:
            still_local = uow.leads.get(lead_id)
            conflicts = uow.sync_conflicts.list_open_for_entity("LEAD", lead_id)
        assert still_local.display_name == "Editado localmente"
        assert len(conflicts) == 1


class TestResolveCRMSyncConflictLead:
    def test_resolve_remote_applies_field_to_lead(self, crm_conn):
        create_result = CreateLeadUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, display_name="Lead Original", operation_id="op-lead-3")
        lead_id = create_result.entity_id
        with CRMUnitOfWork(crm_conn) as uow:
            base_updated_at = uow.leads.get(lead_id).updated_at
        from backend.application.crm.use_cases.lead_use_cases import UpdateLeadUseCase
        UpdateLeadUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, lead_id=lead_id, operation_id="op-edit-local-2",
            display_name="Editado localmente")

        detect_result = DetectCRMSyncConflictUseCase().execute(
            crm_conn, related_entity_type="LEAD", related_entity_id=lead_id,
            local_updated_at="2099-01-01T00:00:00+00:00", base_updated_at=base_updated_at,
            remote_snapshot={"display_name": "Ganó la carrera remota"},
            conflict_type="LEAD_ASSIGNMENT_CONFLICT", operation_id="op-detect-3")
        conflict_id = detect_result.data["conflict_id"]

        resolve_result = ResolveCRMSyncConflictUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, conflict_id=conflict_id, resolution="REMOTE",
            operation_id="op-resolve-1")
        assert resolve_result.success
        assert resolve_result.data["applied"] is True
        with CRMUnitOfWork(crm_conn) as uow:
            lead = uow.leads.get(lead_id)
        assert lead.display_name == "Ganó la carrera remota"


class TestDetectCRMSyncConflictOpportunity:
    def test_opportunity_conflict_detected_and_resolved_local(self, crm_conn):
        create_result = CreateOpportunityUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, customer_id="cust-1", name="Oportunidad Sync",
            operation_id="op-opp-1")
        opp_id = create_result.entity_id
        with CRMUnitOfWork(crm_conn) as uow:
            base_updated_at = uow.opportunities.get(opp_id).updated_at

        detect_result = DetectCRMSyncConflictUseCase().execute(
            crm_conn, related_entity_type="OPPORTUNITY", related_entity_id=opp_id,
            local_updated_at="2099-01-01T00:00:00+00:00",  # simulates a local change since base
            base_updated_at=base_updated_at, remote_snapshot={"stage": "remote"},
            conflict_type="OPPORTUNITY_STAGE_CONFLICT", operation_id="op-detect-4")
        assert not detect_result.success
        conflict_id = detect_result.data["conflict_id"]

        resolve_result = ResolveCRMSyncConflictUseCase(_admin_policy()).execute(
            crm_conn, actor_user_id=_ACTOR, conflict_id=conflict_id, resolution="LOCAL",
            operation_id="op-resolve-2")
        assert resolve_result.success
        assert resolve_result.data["applied"] is False
