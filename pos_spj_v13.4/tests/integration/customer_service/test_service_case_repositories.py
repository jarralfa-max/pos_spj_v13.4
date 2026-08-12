"""CRM-7 — ServiceCase/Category/Resolution/Escalation/Policy/SLAInstance
repository round-trips."""

from __future__ import annotations

from backend.domain.customer_service.entities.customer_service_case import CustomerServiceCase
from backend.domain.customer_service.entities.service_case_category import ServiceCaseCategory
from backend.domain.customer_service.entities.service_case_escalation import (
    ServiceCaseEscalation,
)
from backend.domain.customer_service.entities.service_case_resolution import (
    ServiceCaseResolution,
)
from backend.domain.customer_service.entities.service_level_policy import ServiceLevelPolicy
from backend.domain.customer_service.entities.sla_instance import SLAInstance
from backend.domain.customer_service.enums import EscalationReason, ServiceCasePriority, ServiceCaseType
from backend.infrastructure.db.repositories.customer_service.unit_of_work import (
    CustomerServiceUnitOfWork,
)


def _case(uow, **kwargs) -> CustomerServiceCase:
    return CustomerServiceCase.create(
        uow.cases.next_code(), kwargs.pop("customer_id", "cust-1"),
        kwargs.pop("case_type", ServiceCaseType.COMPLAINT),
        kwargs.pop("subject", "Producto en mal estado"), **kwargs)


class TestServiceCaseRepository:
    def test_save_and_get(self, cs_conn):
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            case = _case(uow, operation_id="op-1")
            uow.cases.save(case, operation_id="op-1")
        with CustomerServiceUnitOfWork(cs_conn) as uow2:
            fetched = uow2.cases.get(case.id)
            assert fetched.subject == "Producto en mal estado"
            assert fetched.status.value == "NEW"

    def test_next_code_increments(self, cs_conn):
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            c1 = _case(uow, operation_id="op-1")
            uow.cases.save(c1, operation_id="op-1")
        with CustomerServiceUnitOfWork(cs_conn) as uow2:
            c2 = _case(uow2, operation_id="op-2")
            uow2.cases.save(c2, operation_id="op-2")
        assert str(c1.code) == "CASE-000001"
        assert str(c2.code) == "CASE-000002"

    def test_get_by_operation_id_is_idempotency_lookup(self, cs_conn):
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            case = _case(uow, operation_id="op-dup")
            uow.cases.save(case, operation_id="op-dup")
        with CustomerServiceUnitOfWork(cs_conn) as uow2:
            found = uow2.cases.get_by_operation_id("op-dup")
            assert found is not None and found.id == case.id

    def test_update_persists_status_and_priority(self, cs_conn):
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            case = _case(uow, operation_id="op-1")
            uow.cases.save(case, operation_id="op-1")
        with CustomerServiceUnitOfWork(cs_conn) as uow2:
            case = uow2.cases.get(case.id)
            case.priority = ServiceCasePriority.CRITICAL
            case.assign_owner("u1")
            uow2.cases.update(case)
        with CustomerServiceUnitOfWork(cs_conn) as uow3:
            reloaded = uow3.cases.get(case.id)
            assert reloaded.status.value == "ASSIGNED"
            assert reloaded.priority.value == "CRITICAL"

    def test_list_owned_by_filters_by_assignee(self, cs_conn):
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            mine = _case(uow, subject="Mio", operation_id="op-1")
            uow.cases.save(mine, operation_id="op-1")
            mine.assign_owner("u1")
            uow.cases.update(mine)
            other = _case(uow, subject="Ajeno", operation_id="op-2")
            uow.cases.save(other, operation_id="op-2")
            other.assign_owner("u2")
            uow.cases.update(other)
        with CustomerServiceUnitOfWork(cs_conn) as uow2:
            results = uow2.cases.list_owned_by(("u1",))
            assert [c.id for c in results] == [mine.id]

    def test_list_open_owned_by_excludes_closed_and_cancelled(self, cs_conn):
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            open_case = _case(uow, subject="Abierto", operation_id="op-1")
            uow.cases.save(open_case, operation_id="op-1")
            open_case.assign_owner("u1")
            uow.cases.update(open_case)
            cancelled = _case(uow, subject="Cancelado", operation_id="op-2")
            uow.cases.save(cancelled, operation_id="op-2")
            cancelled.assign_owner("u1")
            cancelled.cancel("motivo")
            uow.cases.update(cancelled)
        with CustomerServiceUnitOfWork(cs_conn) as uow2:
            results = uow2.cases.list_open_owned_by(("u1",))
            assert [c.id for c in results] == [open_case.id]

    def test_rollback_on_exception_discards_all_writes(self, cs_conn):
        try:
            with CustomerServiceUnitOfWork(cs_conn) as uow:
                case = _case(uow, operation_id="op-1")
                uow.cases.save(case, operation_id="op-1")
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        count = cs_conn.execute("SELECT COUNT(*) FROM service_cases").fetchone()[0]
        assert count == 0


class TestServiceCaseCategoryRepository:
    def test_save_and_list_active(self, cs_conn):
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            cat = ServiceCaseCategory.create("FACTURACION", "Facturación")
            uow.categories.save(cat)
        with CustomerServiceUnitOfWork(cs_conn) as uow2:
            active = uow2.categories.list_active()
            assert [c.id for c in active] == [cat.id]


class TestServiceCaseResolutionRepository:
    def test_save_and_get_for_case(self, cs_conn):
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            case = _case(uow, operation_id="op-1")
            uow.cases.save(case, operation_id="op-1")
            resolution = ServiceCaseResolution.create(case.id, "Se repuso el producto", "u1",
                                                       customer_satisfied=True)
            uow.resolutions.save(resolution)
        with CustomerServiceUnitOfWork(cs_conn) as uow2:
            fetched = uow2.resolutions.get_for_case(case.id)
            assert fetched.resolution_summary == "Se repuso el producto"
            assert fetched.customer_satisfied is True


class TestServiceCaseEscalationRepository:
    def test_save_and_list_for_case_ordered(self, cs_conn):
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            case = _case(uow, operation_id="op-1")
            uow.cases.save(case, operation_id="op-1")
            e1 = ServiceCaseEscalation.create(case.id, EscalationReason.SLA_BREACHED, 1, "u2",
                                              "u1")
            uow.escalations.save(e1)
        with CustomerServiceUnitOfWork(cs_conn) as uow2:
            escalations = uow2.escalations.list_for_case(case.id)
            assert len(escalations) == 1
            assert escalations[0].reason.value == "SLA_BREACHED"


class TestServiceLevelPolicyRepository:
    def test_save_and_list_active(self, cs_conn):
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            policy = ServiceLevelPolicy.create("DEFAULT", "Default", 60, 480)
            uow.policies.save(policy)
        with CustomerServiceUnitOfWork(cs_conn) as uow2:
            active = uow2.policies.list_active()
            assert [p.id for p in active] == [policy.id]

    def test_update_persists_deactivation(self, cs_conn):
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            policy = ServiceLevelPolicy.create("DEFAULT", "Default", 60, 480)
            uow.policies.save(policy)
            policy.deactivate()
            uow.policies.update(policy)
        with CustomerServiceUnitOfWork(cs_conn) as uow2:
            assert uow2.policies.list_active() == []


class TestSLAInstanceRepository:
    def test_save_and_get_for_case(self, cs_conn):
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            case = _case(uow, operation_id="op-1")
            uow.cases.save(case, operation_id="op-1")
            policy = ServiceLevelPolicy.create("DEFAULT", "Default", 60, 480)
            uow.policies.save(policy)
            sla = SLAInstance.create(case.id, policy.id, 60, 480)
            uow.sla_instances.save(sla)
        with CustomerServiceUnitOfWork(cs_conn) as uow2:
            fetched = uow2.sla_instances.get_for_case(case.id)
            assert fetched.policy_id == policy.id

    def test_update_persists_first_response_and_escalation(self, cs_conn):
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            case = _case(uow, operation_id="op-1")
            uow.cases.save(case, operation_id="op-1")
            policy = ServiceLevelPolicy.create("DEFAULT", "Default", 60, 480)
            uow.policies.save(policy)
            sla = SLAInstance.create(case.id, policy.id, 60, 480)
            uow.sla_instances.save(sla)
        with CustomerServiceUnitOfWork(cs_conn) as uow2:
            sla = uow2.sla_instances.get_for_case(case.id)
            sla.record_first_response()
            sla.bump_escalation()
            uow2.sla_instances.update(sla)
        with CustomerServiceUnitOfWork(cs_conn) as uow3:
            reloaded = uow3.sla_instances.get_for_case(case.id)
            assert reloaded.first_response_at is not None
            assert reloaded.escalation_level == 1

    def test_list_open_excludes_resolved(self, cs_conn):
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            case1 = _case(uow, subject="A", operation_id="op-1")
            uow.cases.save(case1, operation_id="op-1")
            case2 = _case(uow, subject="B", operation_id="op-2")
            uow.cases.save(case2, operation_id="op-2")
            policy = ServiceLevelPolicy.create("DEFAULT", "Default", 60, 480)
            uow.policies.save(policy)
            sla1 = SLAInstance.create(case1.id, policy.id, 60, 480)
            uow.sla_instances.save(sla1)
            sla2 = SLAInstance.create(case2.id, policy.id, 60, 480)
            sla2.record_resolution()
            uow.sla_instances.save(sla2)
        with CustomerServiceUnitOfWork(cs_conn) as uow2:
            open_slas = uow2.sla_instances.list_open()
            assert [s.id for s in open_slas] == [sla1.id]
