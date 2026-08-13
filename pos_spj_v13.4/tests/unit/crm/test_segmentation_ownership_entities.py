"""CRM-10 — Propietario/Territorios/Carteras/Segmentación/Etiquetas domain
unit tests: catalog entities (SalesTerritory, CustomerPortfolio,
CustomerSegment, CustomerTag) and append-only history entities
(CustomerOwnership, PortfolioAssignment, CustomerSegmentMembership,
CustomerTagAssignment). Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.crm.entities.customer_ownership import CustomerOwnership
from backend.domain.crm.entities.customer_portfolio import CustomerPortfolio
from backend.domain.crm.entities.customer_segment import CustomerSegment
from backend.domain.crm.entities.customer_segment_membership import CustomerSegmentMembership
from backend.domain.crm.entities.customer_tag import CustomerTag
from backend.domain.crm.entities.customer_tag_assignment import CustomerTagAssignment
from backend.domain.crm.entities.portfolio_assignment import PortfolioAssignment
from backend.domain.crm.entities.sales_territory import SalesTerritory
from backend.domain.crm.enums import OwnershipType, SegmentMembershipSource
from backend.domain.crm.exceptions import (
    InvalidCustomerOwnershipError,
    InvalidCustomerPortfolioError,
    InvalidCustomerSegmentError,
    InvalidCustomerSegmentMembershipError,
    InvalidCustomerTagAssignmentError,
    InvalidCustomerTagError,
    InvalidPortfolioAssignmentError,
    InvalidSalesTerritoryError,
)


class TestSalesTerritory:
    def test_create_normalizes_code(self):
        territory = SalesTerritory.create("norte", "Zona Norte")
        assert territory.code == "NORTE"
        assert territory.active is True

    def test_create_requires_code(self):
        with pytest.raises(InvalidSalesTerritoryError):
            SalesTerritory.create("", "Zona Norte")

    def test_create_requires_name(self):
        with pytest.raises(InvalidSalesTerritoryError):
            SalesTerritory.create("NORTE", "   ")

    def test_deactivate(self):
        territory = SalesTerritory.create("NORTE", "Zona Norte")
        territory.deactivate()
        assert territory.active is False


class TestCustomerPortfolio:
    def test_create_normalizes_code(self):
        portfolio = CustomerPortfolio.create("cartera-a", "Cartera A")
        assert portfolio.code == "CARTERA-A"
        assert portfolio.active is True

    def test_create_requires_code(self):
        with pytest.raises(InvalidCustomerPortfolioError):
            CustomerPortfolio.create("", "Cartera A")

    def test_deactivate(self):
        portfolio = CustomerPortfolio.create("CARTERA-A", "Cartera A")
        portfolio.deactivate()
        assert portfolio.active is False


class TestCustomerSegment:
    def test_create_with_rule_definition(self):
        segment = CustomerSegment.create(
            "vip", "Clientes VIP", rule_definition="ltv > 100000")
        assert segment.code == "VIP"
        assert segment.rule_definition == "ltv > 100000"

    def test_create_requires_name(self):
        with pytest.raises(InvalidCustomerSegmentError):
            CustomerSegment.create("VIP", "")

    def test_deactivate(self):
        segment = CustomerSegment.create("VIP", "Clientes VIP")
        segment.deactivate()
        assert segment.active is False


class TestCustomerTag:
    def test_create_normalizes_code(self):
        tag = CustomerTag.create("moroso", "Moroso")
        assert tag.code == "MOROSO"

    def test_create_requires_label(self):
        with pytest.raises(InvalidCustomerTagError):
            CustomerTag.create("MOROSO", "")

    def test_deactivate(self):
        tag = CustomerTag.create("MOROSO", "Moroso")
        tag.deactivate()
        assert tag.active is False


class TestCustomerOwnership:
    def test_capture_requires_customer_id(self):
        with pytest.raises(InvalidCustomerOwnershipError):
            CustomerOwnership.capture("", OwnershipType.PRIMARY, "u-owner")

    def test_capture_requires_owner_user_id(self):
        with pytest.raises(InvalidCustomerOwnershipError):
            CustomerOwnership.capture("cust-1", OwnershipType.PRIMARY, "")

    def test_capture_records_reason_and_assigner(self):
        ownership = CustomerOwnership.capture(
            "cust-1", OwnershipType.PRIMARY, "u-owner", assigned_by_user_id="u-mgr",
            reason="reorganización de cartera")
        assert ownership.owner_user_id == "u-owner"
        assert ownership.assigned_by_user_id == "u-mgr"
        assert ownership.reason == "reorganización de cartera"
        assert ownership.ownership_type is OwnershipType.PRIMARY


class TestPortfolioAssignment:
    def test_capture_requires_customer_id(self):
        with pytest.raises(InvalidPortfolioAssignmentError):
            PortfolioAssignment.capture("", "portfolio-1")

    def test_capture_requires_portfolio_id(self):
        with pytest.raises(InvalidPortfolioAssignmentError):
            PortfolioAssignment.capture("cust-1", "")

    def test_capture_ok(self):
        assignment = PortfolioAssignment.capture("cust-1", "portfolio-1", reason="reorganización")
        assert assignment.customer_id == "cust-1"
        assert assignment.portfolio_id == "portfolio-1"


class TestCustomerSegmentMembership:
    def test_add_defaults_to_manual(self):
        membership = CustomerSegmentMembership.add("cust-1", "seg-1")
        assert membership.source is SegmentMembershipSource.MANUAL
        assert membership.is_active() is True

    def test_add_requires_customer_id(self):
        with pytest.raises(InvalidCustomerSegmentMembershipError):
            CustomerSegmentMembership.add("", "seg-1")

    def test_remove_sets_removed_at(self):
        membership = CustomerSegmentMembership.add(
            "cust-1", "seg-1", SegmentMembershipSource.RULE_BASED)
        membership.remove(removed_by_user_id="u1")
        assert membership.is_active() is False
        assert membership.removed_at is not None
        assert membership.removed_by_user_id == "u1"

    def test_remove_twice_raises(self):
        membership = CustomerSegmentMembership.add("cust-1", "seg-1")
        membership.remove()
        with pytest.raises(InvalidCustomerSegmentMembershipError):
            membership.remove()


class TestCustomerTagAssignment:
    def test_add_requires_tag_id(self):
        with pytest.raises(InvalidCustomerTagAssignmentError):
            CustomerTagAssignment.add("cust-1", "")

    def test_remove_sets_removed_at(self):
        assignment = CustomerTagAssignment.add("cust-1", "tag-1")
        assignment.remove(removed_by_user_id="u1")
        assert assignment.is_active() is False

    def test_remove_twice_raises(self):
        assignment = CustomerTagAssignment.add("cust-1", "tag-1")
        assignment.remove()
        with pytest.raises(InvalidCustomerTagAssignmentError):
            assignment.remove()
