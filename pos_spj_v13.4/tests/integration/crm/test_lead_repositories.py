"""CRM-4 — Lead repository round-trips + UnitOfWork behavior."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.crm.entities.lead import Lead
from backend.domain.crm.entities.lead_qualification import LeadQualification
from backend.domain.crm.enums import LeadSource, QualificationDecision, QualificationModel
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


def _new_lead(uow, **kwargs) -> Lead:
    return Lead.create(
        uow.leads.next_code(), kwargs.pop("display_name", "Restaurante El Sol"),
        created_by_user_id="u-capturista", **kwargs)


class TestLeadRepository:
    def test_save_and_get(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            lead = _new_lead(uow, operation_id="op-1")
            uow.leads.save(lead, operation_id="op-1")
        with CRMUnitOfWork(crm_conn) as uow2:
            fetched = uow2.leads.get(lead.id)
            assert fetched.display_name == "Restaurante El Sol"
            assert fetched.status.value == "NEW"

    def test_next_code_increments(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            l1 = _new_lead(uow, operation_id="op-1")
            uow.leads.save(l1, operation_id="op-1")
        with CRMUnitOfWork(crm_conn) as uow2:
            l2 = _new_lead(uow2, operation_id="op-2")
            uow2.leads.save(l2, operation_id="op-2")
        assert str(l1.code) == "LEAD-000001"
        assert str(l2.code) == "LEAD-000002"

    def test_get_by_operation_id_is_idempotency_lookup(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            lead = _new_lead(uow, operation_id="op-dup")
            uow.leads.save(lead, operation_id="op-dup")
        with CRMUnitOfWork(crm_conn) as uow2:
            found = uow2.leads.get_by_operation_id("op-dup")
            assert found is not None and found.id == lead.id

    def test_decimal_and_date_round_trip(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            lead = _new_lead(uow, operation_id="op-1", estimated_value="15000.50",
                             expected_purchase_date=date(2026, 9, 1))
            uow.leads.save(lead, operation_id="op-1")
        with CRMUnitOfWork(crm_conn) as uow2:
            fetched = uow2.leads.get(lead.id)
            assert fetched.estimated_value == Decimal("15000.50")
            assert fetched.expected_purchase_date == date(2026, 9, 1)

    def test_update_persists_status(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            lead = _new_lead(uow, operation_id="op-1")
            uow.leads.save(lead, operation_id="op-1")
        with CRMUnitOfWork(crm_conn) as uow2:
            lead = uow2.leads.get(lead.id)
            lead.assign("u-vendedor")
            uow2.leads.update(lead)
        with CRMUnitOfWork(crm_conn) as uow3:
            reloaded = uow3.leads.get(lead.id)
            assert reloaded.status.value == "ASSIGNED"
            assert reloaded.assigned_user_id == "u-vendedor"

    def test_list_owned_by_filters_by_assignee(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            mine = _new_lead(uow, display_name="Mio", operation_id="op-1")
            uow.leads.save(mine, operation_id="op-1")
            mine.assign("u1")
            uow.leads.update(mine)
            other = _new_lead(uow, display_name="Ajeno", operation_id="op-2")
            uow.leads.save(other, operation_id="op-2")
            other.assign("u2")
            uow.leads.update(other)
        with CRMUnitOfWork(crm_conn) as uow2:
            results = uow2.leads.list_owned_by(("u1",))
            assert [l.id for l in results] == [mine.id]

    def test_rollback_on_exception_discards_all_writes(self, crm_conn):
        try:
            with CRMUnitOfWork(crm_conn) as uow:
                lead = _new_lead(uow, operation_id="op-1")
                uow.leads.save(lead, operation_id="op-1")
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        count = crm_conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        assert count == 0


class TestLeadQualificationRepository:
    def test_save_and_list_for_lead(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            lead = _new_lead(uow, operation_id="op-1")
            uow.leads.save(lead, operation_id="op-1")
            q = LeadQualification.create(
                lead.id, QualificationModel.BANT_LIKE, QualificationDecision.QUALIFIED, "u1",
                criteria={"budget": True, "authority": True}, score=None)
            uow.qualifications.save(q)
        with CRMUnitOfWork(crm_conn) as uow2:
            quals = uow2.qualifications.list_for_lead(lead.id)
            assert len(quals) == 1
            assert quals[0].criteria == {"budget": True, "authority": True}
            assert quals[0].model is QualificationModel.BANT_LIKE
