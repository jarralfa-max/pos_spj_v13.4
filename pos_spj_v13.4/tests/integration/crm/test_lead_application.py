"""CRM-4 — Leads application tests (use cases + query service).

Covers happy path, permission-denied (fail closed), invalid state,
duplicate detection, idempotency, rollback, events, audit, qualification
models, conversion (including its cross-bounded-context atomicity), and
scope enforcement in the query service.
"""

from __future__ import annotations

import pytest

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.data_scope import CRMDataScopeResolver, CRMScopeContext
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.queries.lead_directory_query_service import (
    LeadDirectoryQueryService,
)
from backend.application.crm.use_cases.convert_lead_use_case import ConvertLeadUseCase
from backend.application.crm.use_cases.lead_use_cases import (
    ArchiveLeadUseCase,
    AssignLeadUseCase,
    CreateLeadUseCase,
    DisqualifyLeadUseCase,
    LoseLeadUseCase,
    MarkLeadContactedUseCase,
    QualifyLeadUseCase,
    StartLeadNurturingUseCase,
    UpdateLeadUseCase,
)
from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.domain.crm.exceptions import CRMScopeError, LeadNotFoundError
from backend.shared.ids import new_uuid


def _allow_crm():
    return CRMAuthorizationPolicy.permissive_for_tests()


def _allow_cust():
    return CustomerAuthorizationPolicy.permissive_for_tests()


def _create(conn, *, actor="u-capturista", name="Restaurante El Sol", operation_id=None, **kwargs):
    return CreateLeadUseCase(_allow_crm()).execute(
        conn, actor_user_id=actor, display_name=name,
        operation_id=operation_id or new_uuid(), **kwargs)


def _qualified_lead_id(conn, *, owner="u-vendedor"):
    lead_id = _create(conn).entity_id
    AssignLeadUseCase(_allow_crm()).execute(
        conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid(),
        assignee_user_id=owner)
    QualifyLeadUseCase(_allow_crm()).execute(
        conn, actor_user_id=owner, lead_id=lead_id, operation_id=new_uuid(),
        model="MANUAL", manual_decision="QUALIFIED")
    return lead_id


class TestCreate:
    def test_happy_path_emits_event_and_audit(self, crm_conn):
        result = _create(crm_conn)
        assert result.success and result.entity_id
        assert result.data["code"] == "LEAD-000001"
        outbox = crm_conn.execute(
            "SELECT COUNT(*) FROM crm_outbox WHERE event_name='CRM_LEAD_CREATED'"
        ).fetchone()[0]
        audit = crm_conn.execute(
            "SELECT COUNT(*) FROM crm_audit_log WHERE action='CRM_LEAD_CREATED'"
        ).fetchone()[0]
        assert outbox == 1 and audit == 1

    def test_permission_denied_without_checker_wired(self, crm_conn):
        result = CreateLeadUseCase().execute(
            crm_conn, actor_user_id="u1", display_name="X", operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_duplicate_detected_not_merged(self, crm_conn):
        _create(crm_conn, phone_e164="+525512345678")
        dup = _create(crm_conn, name="Restaurante El Sol", phone_e164="+525512345678")
        assert not dup.success and dup.error_code == "DUPLICATE"
        assert dup.data["duplicates"]

    def test_allow_duplicate_overrides(self, crm_conn):
        _create(crm_conn, name="Restaurante El Sol")
        second = _create(crm_conn, name="Restaurante El Sol", allow_duplicate=True)
        assert second.success

    def test_idempotent_on_operation_id(self, crm_conn):
        op = new_uuid()
        first = _create(crm_conn, operation_id=op)
        second = _create(crm_conn, operation_id=op)
        assert first.entity_id == second.entity_id

    def test_invalid_display_name_fails_validation(self, crm_conn):
        result = CreateLeadUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", display_name="   ", operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"


class TestTransitions:
    def test_assign_mark_contacted_nurture_qualify(self, crm_conn):
        lead_id = _create(crm_conn).entity_id
        assert AssignLeadUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid(),
            assignee_user_id="u-vendedor").success
        assert MarkLeadContactedUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid()).success
        assert StartLeadNurturingUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid()).success
        result = QualifyLeadUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid(),
            model="MANUAL", manual_decision="QUALIFIED")
        assert result.success and result.data["decision"] == "QUALIFIED"

    def test_disqualify_requires_reason(self, crm_conn):
        lead_id = _create(crm_conn).entity_id
        result = DisqualifyLeadUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid(), reason="")
        assert not result.success and result.error_code == "VALIDATION"
        ok = DisqualifyLeadUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid(),
            reason="sin presupuesto")
        assert ok.success

    def test_lose_then_archive(self, crm_conn):
        lead_id = _create(crm_conn).entity_id
        LoseLeadUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid(),
            reason="no contesta")
        result = ArchiveLeadUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid())
        assert result.success
        row = crm_conn.execute("SELECT status FROM leads WHERE id=?", (lead_id,)).fetchone()
        assert row[0] == "ARCHIVED"

    def test_transition_on_missing_lead_is_not_found(self, crm_conn):
        result = AssignLeadUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", lead_id="does-not-exist", operation_id=new_uuid(),
            assignee_user_id="u2")
        assert not result.success and result.error_code == "NOT_FOUND"


class TestUpdate:
    def test_update_display_name(self, crm_conn):
        lead_id = _create(crm_conn).entity_id
        result = UpdateLeadUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid(),
            display_name="Restaurante El Sol S.A.")
        assert result.success
        row = crm_conn.execute("SELECT display_name FROM leads WHERE id=?", (lead_id,)).fetchone()
        assert row[0] == "Restaurante El Sol S.A."


def _assigned_lead_id(conn, *, name="Restaurante El Sol", assignee="u-vendedor"):
    lead_id = _create(conn, name=name).entity_id
    AssignLeadUseCase(_allow_crm()).execute(
        conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid(),
        assignee_user_id=assignee)
    return lead_id


class TestQualification:
    def test_score_based_qualifies_above_threshold(self, crm_conn):
        lead_id = _assigned_lead_id(crm_conn)
        result = QualifyLeadUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid(),
            model="SCORE_BASED", score=85, score_threshold=70)
        assert result.success and result.data["decision"] == "QUALIFIED"
        row = crm_conn.execute("SELECT status FROM leads WHERE id=?", (lead_id,)).fetchone()
        assert row[0] == "QUALIFIED"

    def test_score_based_disqualifies_below_threshold(self, crm_conn):
        lead_id = _assigned_lead_id(crm_conn)
        result = QualifyLeadUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid(),
            model="SCORE_BASED", score=40, score_threshold=70, notes="score bajo")
        assert result.success and result.data["decision"] == "UNQUALIFIED"
        row = crm_conn.execute("SELECT status FROM leads WHERE id=?", (lead_id,)).fetchone()
        assert row[0] == "UNQUALIFIED"

    def test_bant_like_records_criteria_as_evidence(self, crm_conn):
        lead_id = _assigned_lead_id(crm_conn)
        result = QualifyLeadUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid(),
            model="BANT_LIKE", criteria={"budget": True, "authority": True, "need": True},
            min_criteria_passed=2)
        assert result.success
        row = crm_conn.execute(
            "SELECT criteria_json FROM lead_qualifications WHERE lead_id=?", (lead_id,)
        ).fetchone()
        assert "budget" in row[0]

    def test_qualify_missing_lead_is_not_found(self, crm_conn):
        result = QualifyLeadUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", lead_id="does-not-exist", operation_id=new_uuid(),
            model="MANUAL", manual_decision="QUALIFIED")
        assert not result.success and result.error_code == "NOT_FOUND"


class TestConvertLead:
    def test_happy_path_creates_customer_account_and_contact(self, crm_and_customers_conn):
        lead_id = _qualified_lead_id(crm_and_customers_conn)
        # give the lead a company + contact details before converting
        UpdateLeadUseCase(_allow_crm()).execute(
            crm_and_customers_conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid(),
            contact_name="Maria")
        crm_and_customers_conn.execute(
            "UPDATE leads SET company_name=?, phone_e164=?, email=? WHERE id=?",
            ("El Sol SA", "+525512345678", "maria@elsol.com", lead_id))
        crm_and_customers_conn.commit()

        result = ConvertLeadUseCase(_allow_crm(), _allow_cust()).execute(
            crm_and_customers_conn, actor_user_id="u-vendedor", lead_id=lead_id,
            operation_id=new_uuid())
        assert result.success
        customer_id = result.data["customer_id"]

        lead_row = crm_and_customers_conn.execute(
            "SELECT status FROM leads WHERE id=?", (lead_id,)).fetchone()
        assert lead_row[0] == "CONVERTED"

        customer_row = crm_and_customers_conn.execute(
            "SELECT display_name, legal_name FROM customers WHERE id=?", (customer_id,)
        ).fetchone()
        assert customer_row == ("Restaurante El Sol", "El Sol SA")

        accounts = crm_and_customers_conn.execute(
            "SELECT COUNT(*) FROM customer_accounts WHERE customer_id=?", (customer_id,)
        ).fetchone()[0]
        assert accounts == 1

        contact = crm_and_customers_conn.execute(
            "SELECT phone_e164, email FROM customer_contacts WHERE customer_id=?", (customer_id,)
        ).fetchone()
        assert contact == ("+525512345678", "maria@elsol.com")

    def test_requires_qualified_status(self, crm_and_customers_conn):
        lead_id = _create(crm_and_customers_conn).entity_id  # still NEW, not qualified
        result = ConvertLeadUseCase(_allow_crm(), _allow_cust()).execute(
            crm_and_customers_conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"
        # nothing should have been written on either side
        assert crm_and_customers_conn.execute(
            "SELECT status FROM leads WHERE id=?", (lead_id,)).fetchone()[0] == "NEW"
        assert crm_and_customers_conn.execute(
            "SELECT COUNT(*) FROM customers").fetchone()[0] == 0

    def test_duplicate_customer_detected(self, crm_and_customers_conn):
        from backend.application.customers.use_cases.lifecycle_use_cases import (
            CreateCustomerUseCase,
        )
        CreateCustomerUseCase(_allow_cust()).execute(
            crm_and_customers_conn, actor_user_id="u1", display_name="Restaurante El Sol",
            operation_id=new_uuid())

        lead_id = _qualified_lead_id(crm_and_customers_conn)
        result = ConvertLeadUseCase(_allow_crm(), _allow_cust()).execute(
            crm_and_customers_conn, actor_user_id="u-vendedor", lead_id=lead_id,
            operation_id=new_uuid())
        assert not result.success and result.error_code == "DUPLICATE"
        # lead must remain QUALIFIED, not silently converted
        assert crm_and_customers_conn.execute(
            "SELECT status FROM leads WHERE id=?", (lead_id,)).fetchone()[0] == "QUALIFIED"

    def test_link_to_existing_customer_skips_creation(self, crm_and_customers_conn):
        from backend.application.customers.use_cases.lifecycle_use_cases import (
            CreateCustomerUseCase,
        )
        existing = CreateCustomerUseCase(_allow_cust()).execute(
            crm_and_customers_conn, actor_user_id="u1", display_name="Cliente Existente",
            operation_id=new_uuid())
        lead_id = _qualified_lead_id(crm_and_customers_conn)

        result = ConvertLeadUseCase(_allow_crm(), _allow_cust()).execute(
            crm_and_customers_conn, actor_user_id="u-vendedor", lead_id=lead_id,
            operation_id=new_uuid(), link_to_customer_id=existing.entity_id)
        assert result.success
        assert result.data["customer_id"] == existing.entity_id
        total_customers = crm_and_customers_conn.execute(
            "SELECT COUNT(*) FROM customers").fetchone()[0]
        assert total_customers == 1  # no new customer created

    def test_lead_not_deleted_on_conversion(self, crm_and_customers_conn):
        lead_id = _qualified_lead_id(crm_and_customers_conn)
        ConvertLeadUseCase(_allow_crm(), _allow_cust()).execute(
            crm_and_customers_conn, actor_user_id="u-vendedor", lead_id=lead_id,
            operation_id=new_uuid())
        row = crm_and_customers_conn.execute(
            "SELECT COUNT(*) FROM leads WHERE id=?", (lead_id,)).fetchone()
        assert row[0] == 1  # still there, just CONVERTED (§18: never eliminar)


class TestLeadDirectoryQueryService:
    def _service(self, conn, granted):
        class _Checker:
            def has_permission(self, user_id, code):
                return code in granted
        return LeadDirectoryQueryService(conn, CRMDataScopeResolver(_Checker()))

    def test_own_scope_sees_own_lead_only(self, crm_conn):
        owner = "u-vendedor"
        lead_id = _create(crm_conn).entity_id
        AssignLeadUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid(),
            assignee_user_id=owner)
        service = self._service(crm_conn, {CRMPermissions.LEADS_VIEW_OWN})

        profile = service.get_profile(lead_id, CRMScopeContext(user_id=owner))
        assert profile.lead.id == lead_id

    def test_own_scope_denies_other_owners_lead(self, crm_conn):
        lead_id = _create(crm_conn).entity_id
        AssignLeadUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid(),
            assignee_user_id="u-vendedor-a")
        service = self._service(crm_conn, {CRMPermissions.LEADS_VIEW_OWN})

        with pytest.raises(CRMScopeError):
            service.get_profile(lead_id, CRMScopeContext(user_id="u-vendedor-b"))

    def test_get_profile_missing_lead_raises_not_found(self, crm_conn):
        service = self._service(crm_conn, {CRMPermissions.LEADS_VIEW_TEAM})
        with pytest.raises(LeadNotFoundError):
            service.get_profile("does-not-exist", CRMScopeContext(user_id="u1"))

    def test_profile_includes_qualifications(self, crm_conn):
        lead_id = _qualified_lead_id(crm_conn, owner="u1")
        service = self._service(crm_conn, {CRMPermissions.LEADS_VIEW_OWN})
        profile = service.get_profile(lead_id, CRMScopeContext(user_id="u1"))
        assert len(profile.qualifications) == 1

    def test_team_scope_filters_by_team_membership(self, crm_conn):
        mine = _create(crm_conn, name="Del equipo").entity_id
        AssignLeadUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", lead_id=mine, operation_id=new_uuid(),
            assignee_user_id="u2")
        other = _create(crm_conn, name="Ajeno").entity_id
        AssignLeadUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", lead_id=other, operation_id=new_uuid(),
            assignee_user_id="u-fuera-del-equipo")
        service = self._service(crm_conn, {CRMPermissions.LEADS_VIEW_TEAM})

        results = service.list_directory(
            CRMScopeContext(user_id="u1", team_member_ids=("u1", "u2")))
        assert [l.id for l in results] == [mine]
