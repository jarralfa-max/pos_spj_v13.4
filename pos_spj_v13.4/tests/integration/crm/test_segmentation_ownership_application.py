"""CRM-10 — Propietario/Territorios/Carteras/Segmentación/Etiquetas
application tests: permissions (incl. assign-vs-reassign splits), SoD
reason enforcement, and cross-context sync with the Customers bounded
context (CustomerOwnership PRIMARY ↔ Customer.account_owner_user_id,
territory assignment ↔ Customer.territory_id).
"""

from __future__ import annotations

import pytest

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.queries.customer_ownership_query_service import (
    CustomerOwnershipQueryService,
)
from backend.application.crm.queries.customer_portfolio_query_service import (
    CustomerPortfolioQueryService,
)
from backend.application.crm.queries.customer_segmentation_query_service import (
    CustomerSegmentationQueryService,
)
from backend.application.crm.use_cases.ownership_use_cases import AssignCustomerOwnerUseCase
from backend.application.crm.use_cases.portfolio_use_cases import (
    AssignCustomerPortfolioUseCase,
    CreateCustomerPortfolioUseCase,
    DeactivateCustomerPortfolioUseCase,
)
from backend.application.crm.use_cases.segment_use_cases import (
    AddCustomerToSegmentUseCase,
    CreateCustomerSegmentUseCase,
    RemoveCustomerFromSegmentUseCase,
)
from backend.application.crm.use_cases.tag_use_cases import (
    AssignCustomerTagUseCase,
    CreateCustomerTagUseCase,
    RemoveCustomerTagUseCase,
)
from backend.application.crm.use_cases.territory_use_cases import (
    AssignCustomerTerritoryUseCase,
    CreateSalesTerritoryUseCase,
    DeactivateSalesTerritoryUseCase,
)
from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.use_cases.lifecycle_use_cases import CreateCustomerUseCase
from backend.shared.ids import new_uuid


def _allow_crm():
    return CRMAuthorizationPolicy.permissive_for_tests()


def _allow_cust():
    return CustomerAuthorizationPolicy.permissive_for_tests()


def _deny_crm():
    return CRMAuthorizationPolicy(DenyChecker())


class DenyChecker:
    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return False


def _customer(conn, *, name="Restaurante El Sol") -> str:
    result = CreateCustomerUseCase(_allow_cust()).execute(
        conn, actor_user_id="u1", display_name=name, operation_id=new_uuid())
    assert result.success
    return result.entity_id


class TestCreateAndDeactivateSalesTerritory:
    def test_create_happy_path(self, crm_conn):
        result = CreateSalesTerritoryUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", code="norte", name="Zona Norte",
            operation_id=new_uuid())
        assert result.success
        code = crm_conn.execute(
            "SELECT code FROM sales_territories WHERE id=?", (result.entity_id,)).fetchone()[0]
        assert code == "NORTE"

    def test_create_rejects_duplicate_code(self, crm_conn):
        CreateSalesTerritoryUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", code="NORTE", name="Zona Norte",
            operation_id=new_uuid())
        result = CreateSalesTerritoryUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", code="NORTE", name="Zona Norte Bis",
            operation_id=new_uuid())
        assert not result.success and result.error_code == "DUPLICATE"

    def test_create_requires_permission(self, crm_conn):
        result = CreateSalesTerritoryUseCase(_deny_crm()).execute(
            crm_conn, actor_user_id="u1", code="NORTE", name="Zona Norte",
            operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_deactivate(self, crm_conn):
        created = CreateSalesTerritoryUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", code="NORTE", name="Zona Norte",
            operation_id=new_uuid())
        result = DeactivateSalesTerritoryUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", territory_id=created.entity_id,
            operation_id=new_uuid())
        assert result.success
        active = crm_conn.execute(
            "SELECT active FROM sales_territories WHERE id=?", (created.entity_id,)).fetchone()[0]
        assert active == 0


class TestAssignCustomerTerritory:
    def test_syncs_customer_territory_id(self, crm_and_customers_conn):
        customer_id = _customer(crm_and_customers_conn)
        territory = CreateSalesTerritoryUseCase(_allow_crm()).execute(
            crm_and_customers_conn, actor_user_id="u1", code="NORTE", name="Zona Norte",
            operation_id=new_uuid())

        result = AssignCustomerTerritoryUseCase(_allow_crm()).execute(
            crm_and_customers_conn, actor_user_id="u1", customer_id=customer_id,
            territory_id=territory.entity_id, operation_id=new_uuid())
        assert result.success

        row = crm_and_customers_conn.execute(
            "SELECT territory_id FROM customers WHERE id=?", (customer_id,)).fetchone()
        assert row[0] == territory.entity_id

    def test_rejects_inactive_territory(self, crm_and_customers_conn):
        customer_id = _customer(crm_and_customers_conn)
        territory = CreateSalesTerritoryUseCase(_allow_crm()).execute(
            crm_and_customers_conn, actor_user_id="u1", code="NORTE", name="Zona Norte",
            operation_id=new_uuid())
        DeactivateSalesTerritoryUseCase(_allow_crm()).execute(
            crm_and_customers_conn, actor_user_id="u1", territory_id=territory.entity_id,
            operation_id=new_uuid())

        result = AssignCustomerTerritoryUseCase(_allow_crm()).execute(
            crm_and_customers_conn, actor_user_id="u1", customer_id=customer_id,
            territory_id=territory.entity_id, operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"
        row = crm_and_customers_conn.execute(
            "SELECT territory_id FROM customers WHERE id=?", (customer_id,)).fetchone()
        assert row[0] is None

    def test_unknown_customer_rolls_back(self, crm_and_customers_conn):
        territory = CreateSalesTerritoryUseCase(_allow_crm()).execute(
            crm_and_customers_conn, actor_user_id="u1", code="NORTE", name="Zona Norte",
            operation_id=new_uuid())
        result = AssignCustomerTerritoryUseCase(_allow_crm()).execute(
            crm_and_customers_conn, actor_user_id="u1", customer_id="does-not-exist",
            territory_id=territory.entity_id, operation_id=new_uuid())
        assert not result.success and result.error_code == "NOT_FOUND"


class TestAssignCustomerPortfolio:
    def _portfolio(self, conn, code="A") -> str:
        result = CreateCustomerPortfolioUseCase(_allow_crm()).execute(
            conn, actor_user_id="u1", code=code, name=f"Cartera {code}", operation_id=new_uuid())
        assert result.success
        return result.entity_id

    def test_first_assignment_needs_no_reason(self, crm_conn):
        portfolio_id = self._portfolio(crm_conn)
        result = AssignCustomerPortfolioUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", customer_id="cust-1", portfolio_id=portfolio_id,
            operation_id=new_uuid())
        assert result.success

    def test_reassignment_without_reason_is_rejected(self, crm_conn):
        portfolio_a = self._portfolio(crm_conn, "A")
        portfolio_b = self._portfolio(crm_conn, "B")
        AssignCustomerPortfolioUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", customer_id="cust-1", portfolio_id=portfolio_a,
            operation_id=new_uuid())
        result = AssignCustomerPortfolioUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", customer_id="cust-1", portfolio_id=portfolio_b,
            operation_id=new_uuid())
        assert not result.success and result.error_code == "SOD_VIOLATION"

    def test_reassignment_with_reason_succeeds_and_supersedes(self, crm_conn):
        portfolio_a = self._portfolio(crm_conn, "A")
        portfolio_b = self._portfolio(crm_conn, "B")
        AssignCustomerPortfolioUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", customer_id="cust-1", portfolio_id=portfolio_a,
            operation_id=new_uuid())
        result = AssignCustomerPortfolioUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", customer_id="cust-1", portfolio_id=portfolio_b,
            operation_id=new_uuid(), reason="reorganización de zona")
        assert result.success

        current = CustomerPortfolioQueryService(crm_conn, _allow_crm()).get_current_portfolio(
            "cust-1", actor_user_id="u1")
        assert current.id == portfolio_b

    def test_requires_permission(self, crm_conn):
        portfolio_id = self._portfolio(crm_conn)
        result = AssignCustomerPortfolioUseCase(_deny_crm()).execute(
            crm_conn, actor_user_id="u1", customer_id="cust-1", portfolio_id=portfolio_id,
            operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_deactivated_portfolio_cannot_receive_assignment(self, crm_conn):
        portfolio_id = self._portfolio(crm_conn)
        DeactivateCustomerPortfolioUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", portfolio_id=portfolio_id, operation_id=new_uuid())
        result = AssignCustomerPortfolioUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", customer_id="cust-1", portfolio_id=portfolio_id,
            operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"


class TestAssignCustomerOwner:
    def test_first_assignment_uses_assign_permission(self, crm_and_customers_conn):
        customer_id = _customer(crm_and_customers_conn)
        checker = _RecordingChecker()
        result = AssignCustomerOwnerUseCase(CRMAuthorizationPolicy(checker)).execute(
            crm_and_customers_conn, actor_user_id="u1", customer_id=customer_id,
            ownership_type="PRIMARY", owner_user_id="u-vendedor", operation_id=new_uuid())
        assert result.success
        assert checker.checked == [CRMPermissions.CUSTOMER_OWNER_ASSIGN]

        row = crm_and_customers_conn.execute(
            "SELECT account_owner_user_id FROM customers WHERE id=?", (customer_id,)).fetchone()
        assert row[0] == "u-vendedor"

    def test_reassignment_without_reason_is_rejected(self, crm_and_customers_conn):
        customer_id = _customer(crm_and_customers_conn)
        AssignCustomerOwnerUseCase(_allow_crm()).execute(
            crm_and_customers_conn, actor_user_id="u1", customer_id=customer_id,
            ownership_type="PRIMARY", owner_user_id="u-a", operation_id=new_uuid())
        result = AssignCustomerOwnerUseCase(_allow_crm()).execute(
            crm_and_customers_conn, actor_user_id="u1", customer_id=customer_id,
            ownership_type="PRIMARY", owner_user_id="u-b", operation_id=new_uuid())
        assert not result.success and result.error_code == "SOD_VIOLATION"
        # denormalized field must remain unchanged on rollback
        row = crm_and_customers_conn.execute(
            "SELECT account_owner_user_id FROM customers WHERE id=?", (customer_id,)).fetchone()
        assert row[0] == "u-a"

    def test_reassignment_with_reason_uses_reassign_permission_and_syncs(
        self, crm_and_customers_conn,
    ):
        customer_id = _customer(crm_and_customers_conn)
        AssignCustomerOwnerUseCase(_allow_crm()).execute(
            crm_and_customers_conn, actor_user_id="u1", customer_id=customer_id,
            ownership_type="PRIMARY", owner_user_id="u-a", operation_id=new_uuid())

        checker = _RecordingChecker()
        result = AssignCustomerOwnerUseCase(CRMAuthorizationPolicy(checker)).execute(
            crm_and_customers_conn, actor_user_id="u1", customer_id=customer_id,
            ownership_type="PRIMARY", owner_user_id="u-b", operation_id=new_uuid(),
            reason="salió de la empresa")
        assert result.success
        assert checker.checked == [CRMPermissions.CUSTOMER_OWNER_REASSIGN]
        row = crm_and_customers_conn.execute(
            "SELECT account_owner_user_id FROM customers WHERE id=?", (customer_id,)).fetchone()
        assert row[0] == "u-b"

    def test_secondary_ownership_does_not_touch_customer_row(self, crm_and_customers_conn):
        customer_id = _customer(crm_and_customers_conn)
        result = AssignCustomerOwnerUseCase(_allow_crm()).execute(
            crm_and_customers_conn, actor_user_id="u1", customer_id=customer_id,
            ownership_type="SECONDARY", owner_user_id="u-backup", operation_id=new_uuid())
        assert result.success
        row = crm_and_customers_conn.execute(
            "SELECT account_owner_user_id FROM customers WHERE id=?", (customer_id,)).fetchone()
        assert row[0] is None

        history = CustomerOwnershipQueryService(
            crm_and_customers_conn, _allow_crm()).list_history(customer_id, actor_user_id="u1")
        assert len(history) == 1 and history[0].owner_user_id == "u-backup"

    def test_invalid_ownership_type_is_rejected(self, crm_and_customers_conn):
        customer_id = _customer(crm_and_customers_conn)
        result = AssignCustomerOwnerUseCase(_allow_crm()).execute(
            crm_and_customers_conn, actor_user_id="u1", customer_id=customer_id,
            ownership_type="NOT_A_TYPE", owner_user_id="u-a", operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"

    def test_unknown_customer_rolls_back(self, crm_and_customers_conn):
        result = AssignCustomerOwnerUseCase(_allow_crm()).execute(
            crm_and_customers_conn, actor_user_id="u1", customer_id="does-not-exist",
            ownership_type="PRIMARY", owner_user_id="u-a", operation_id=new_uuid())
        assert not result.success and result.error_code == "NOT_FOUND"


class _RecordingChecker:
    def __init__(self) -> None:
        self.checked: list[str] = []

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        self.checked.append(permission_code)
        return True


class TestCustomerSegmentMembershipUseCases:
    def _segment(self, conn) -> str:
        result = CreateCustomerSegmentUseCase(_allow_crm()).execute(
            conn, actor_user_id="u1", code="VIP", name="Clientes VIP", operation_id=new_uuid())
        assert result.success
        return result.entity_id

    def test_add_then_remove(self, crm_conn):
        segment_id = self._segment(crm_conn)
        added = AddCustomerToSegmentUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", customer_id="cust-1", segment_id=segment_id,
            operation_id=new_uuid())
        assert added.success

        memberships = CustomerSegmentationQueryService(
            crm_conn, _allow_crm()).list_active_memberships("cust-1", actor_user_id="u1")
        assert len(memberships) == 1

        removed = RemoveCustomerFromSegmentUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", membership_id=added.entity_id, operation_id=new_uuid())
        assert removed.success
        memberships = CustomerSegmentationQueryService(
            crm_conn, _allow_crm()).list_active_memberships("cust-1", actor_user_id="u1")
        assert len(memberships) == 0

    def test_duplicate_active_membership_rejected(self, crm_conn):
        segment_id = self._segment(crm_conn)
        AddCustomerToSegmentUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", customer_id="cust-1", segment_id=segment_id,
            operation_id=new_uuid())
        result = AddCustomerToSegmentUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", customer_id="cust-1", segment_id=segment_id,
            operation_id=new_uuid())
        assert not result.success and result.error_code == "DUPLICATE"

    def test_rule_based_source_is_recorded_but_never_evaluated_by_crm(self, crm_conn):
        segment_id = self._segment(crm_conn)
        result = AddCustomerToSegmentUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", customer_id="cust-1", segment_id=segment_id,
            operation_id=new_uuid(), source="RULE_BASED")
        assert result.success
        source = crm_conn.execute(
            "SELECT source FROM customer_segment_memberships WHERE id=?",
            (result.entity_id,)).fetchone()[0]
        assert source == "RULE_BASED"


class TestCustomerTagAssignmentUseCases:
    def _tag(self, conn) -> str:
        result = CreateCustomerTagUseCase(_allow_crm()).execute(
            conn, actor_user_id="u1", code="MOROSO", label="Moroso", operation_id=new_uuid())
        assert result.success
        return result.entity_id

    def test_assign_then_remove(self, crm_conn):
        tag_id = self._tag(crm_conn)
        assigned = AssignCustomerTagUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", customer_id="cust-1", tag_id=tag_id,
            operation_id=new_uuid())
        assert assigned.success

        tags = CustomerSegmentationQueryService(
            crm_conn, _allow_crm()).list_active_tag_assignments("cust-1", actor_user_id="u1")
        assert len(tags) == 1

        removed = RemoveCustomerTagUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", assignment_id=assigned.entity_id,
            operation_id=new_uuid())
        assert removed.success
        tags = CustomerSegmentationQueryService(
            crm_conn, _allow_crm()).list_active_tag_assignments("cust-1", actor_user_id="u1")
        assert len(tags) == 0

    def test_duplicate_active_assignment_rejected(self, crm_conn):
        tag_id = self._tag(crm_conn)
        AssignCustomerTagUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", customer_id="cust-1", tag_id=tag_id,
            operation_id=new_uuid())
        result = AssignCustomerTagUseCase(_allow_crm()).execute(
            crm_conn, actor_user_id="u1", customer_id="cust-1", tag_id=tag_id,
            operation_id=new_uuid())
        assert not result.success and result.error_code == "DUPLICATE"
