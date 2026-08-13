"""CRM-10 — repository round-trips for the Propietario/Territorios/
Carteras/Segmentación/Etiquetas tables.
"""

from __future__ import annotations

from backend.domain.crm.entities.customer_ownership import CustomerOwnership
from backend.domain.crm.entities.customer_portfolio import CustomerPortfolio
from backend.domain.crm.entities.customer_segment import CustomerSegment
from backend.domain.crm.entities.customer_segment_membership import CustomerSegmentMembership
from backend.domain.crm.entities.customer_tag import CustomerTag
from backend.domain.crm.entities.customer_tag_assignment import CustomerTagAssignment
from backend.domain.crm.entities.portfolio_assignment import PortfolioAssignment
from backend.domain.crm.entities.sales_territory import SalesTerritory
from backend.domain.crm.enums import OwnershipType, SegmentMembershipSource
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


class TestSalesTerritoryRepository:
    def test_save_get_and_list_active(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            uow.territories.save(SalesTerritory.create("NORTE", "Zona Norte"))
            inactive = SalesTerritory.create("SUR", "Zona Sur")
            inactive.deactivate()
            uow.territories.save(inactive)
        with CRMUnitOfWork(crm_conn) as uow2:
            found = uow2.territories.get_by_code("NORTE")
            assert found is not None and found.name == "Zona Norte"
            active = uow2.territories.list_active()
            assert [t.code for t in active] == ["NORTE"]

    def test_update_deactivates(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            territory = SalesTerritory.create("NORTE", "Zona Norte")
            uow.territories.save(territory)
        with CRMUnitOfWork(crm_conn) as uow2:
            territory = uow2.territories.get(territory.id)
            territory.deactivate()
            uow2.territories.update(territory)
        with CRMUnitOfWork(crm_conn) as uow3:
            assert uow3.territories.get(territory.id).active is False


class TestCustomerPortfolioRepository:
    def test_save_and_get_by_code(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            uow.portfolios.save(CustomerPortfolio.create("CARTERA-A", "Cartera A",
                                                          manager_user_id="u-mgr"))
        with CRMUnitOfWork(crm_conn) as uow2:
            found = uow2.portfolios.get_by_code("CARTERA-A")
            assert found.manager_user_id == "u-mgr"


class TestCustomerOwnershipRepository:
    def test_get_latest_orders_by_id_when_created_at_ties(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            first = CustomerOwnership.capture("cust-1", OwnershipType.PRIMARY, "u-a")
            second = CustomerOwnership.capture("cust-1", OwnershipType.PRIMARY, "u-b")
            second.created_at = first.created_at  # force a same-second tie
            uow.ownerships.save(first)
            uow.ownerships.save(second)
        with CRMUnitOfWork(crm_conn) as uow2:
            latest = uow2.ownerships.get_latest("cust-1", "PRIMARY")
            assert latest.owner_user_id == "u-b"

    def test_list_for_customer_returns_full_history(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            uow.ownerships.save(CustomerOwnership.capture("cust-1", OwnershipType.PRIMARY, "u-a"))
            uow.ownerships.save(
                CustomerOwnership.capture("cust-1", OwnershipType.SECONDARY, "u-c"))
        with CRMUnitOfWork(crm_conn) as uow2:
            history = uow2.ownerships.list_for_customer("cust-1")
            assert len(history) == 2

    def test_get_latest_is_independent_per_ownership_type(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            uow.ownerships.save(CustomerOwnership.capture("cust-1", OwnershipType.PRIMARY, "u-a"))
            uow.ownerships.save(
                CustomerOwnership.capture("cust-1", OwnershipType.SECONDARY, "u-b"))
        with CRMUnitOfWork(crm_conn) as uow2:
            assert uow2.ownerships.get_latest("cust-1", "PRIMARY").owner_user_id == "u-a"
            assert uow2.ownerships.get_latest("cust-1", "SECONDARY").owner_user_id == "u-b"


class TestPortfolioAssignmentRepository:
    def test_get_latest_reflects_most_recent_assignment(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            portfolio_a = CustomerPortfolio.create("A", "Cartera A")
            portfolio_b = CustomerPortfolio.create("B", "Cartera B")
            uow.portfolios.save(portfolio_a)
            uow.portfolios.save(portfolio_b)
            uow.portfolio_assignments.save(PortfolioAssignment.capture("cust-1", portfolio_a.id))
        with CRMUnitOfWork(crm_conn) as uow2:
            uow2.portfolio_assignments.save(
                PortfolioAssignment.capture("cust-1", portfolio_b.id, reason="reorganización"))
        with CRMUnitOfWork(crm_conn) as uow3:
            latest = uow3.portfolio_assignments.get_latest("cust-1")
            assert latest.portfolio_id == portfolio_b.id
            assert len(uow3.portfolio_assignments.list_for_customer("cust-1")) == 2


class TestCustomerSegmentMembershipRepository:
    def test_get_active_ignores_removed_membership(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            segment = CustomerSegment.create("VIP", "Clientes VIP")
            uow.segments.save(segment)
            membership = CustomerSegmentMembership.add(
                "cust-1", segment.id, SegmentMembershipSource.MANUAL)
            uow.segment_memberships.save(membership)
        with CRMUnitOfWork(crm_conn) as uow2:
            assert uow2.segment_memberships.get_active("cust-1", segment.id) is not None
            membership = uow2.segment_memberships.get(membership.id)
            membership.remove()
            uow2.segment_memberships.update(membership)
        with CRMUnitOfWork(crm_conn) as uow3:
            assert uow3.segment_memberships.get_active("cust-1", segment.id) is None
            assert len(uow3.segment_memberships.list_active_for_customer("cust-1")) == 0


class TestCustomerTagAssignmentRepository:
    def test_get_active_ignores_removed_assignment(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            tag = CustomerTag.create("MOROSO", "Moroso")
            uow.tags.save(tag)
            assignment = CustomerTagAssignment.add("cust-1", tag.id)
            uow.tag_assignments.save(assignment)
        with CRMUnitOfWork(crm_conn) as uow2:
            assert uow2.tag_assignments.get_active("cust-1", tag.id) is not None
            assignment = uow2.tag_assignments.get(assignment.id)
            assignment.remove()
            uow2.tag_assignments.update(assignment)
        with CRMUnitOfWork(crm_conn) as uow3:
            assert uow3.tag_assignments.get_active("cust-1", tag.id) is None
