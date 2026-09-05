"""ASSET-4 — AssetAssignment (custody history) and AssetLoan (temporary loans)."""

from datetime import date, timedelta

import pytest

from backend.domain.assets.entities.asset_assignment import AssetAssignment
from backend.domain.assets.entities.asset_loan import AssetLoan
from backend.domain.assets.enums import AssetAssignmentType
from backend.domain.assets.exceptions import AssetDomainError, AssetStateInvalidError


class TestAssetAssignment:
    def test_create_requires_employee_or_user(self):
        with pytest.raises(AssetDomainError):
            AssetAssignment.create("asset-1", AssetAssignmentType.CUSTODY, "br-1", "op-1")

    def test_create_with_employee(self):
        a = AssetAssignment.create("asset-1", AssetAssignmentType.CUSTODY, "br-1", "op-1",
                                   employee_id="emp-1", assigned_by="u1")
        assert a.is_active() is True
        assert a.employee_id == "emp-1"

    def test_return_custody_closes_record(self):
        a = AssetAssignment.create("asset-1", AssetAssignmentType.OPERATION, "br-1", "op-1",
                                   user_id="usr-1")
        a.return_custody("GOOD")
        assert a.is_active() is False
        assert a.condition_at_return == "GOOD"

    def test_return_custody_twice_fails(self):
        a = AssetAssignment.create("asset-1", AssetAssignmentType.OPERATION, "br-1", "op-1",
                                   user_id="usr-1")
        a.return_custody()
        with pytest.raises(AssetStateInvalidError):
            a.return_custody()


class TestAssetLoan:
    def _loan(self, **extra):
        return AssetLoan.create("asset-1", "empleado-visita", date.today() + timedelta(days=3),
                                "u1", "op-1", **extra)

    def test_create_requires_borrower_and_authorizer(self):
        with pytest.raises(AssetDomainError):
            AssetLoan.create("asset-1", "", date.today(), "u1", "op-1")
        with pytest.raises(AssetDomainError):
            AssetLoan.create("asset-1", "borrower", date.today(), "", "op-1")

    def test_not_overdue_before_due_date(self):
        loan = self._loan()
        assert loan.is_overdue() is False

    def test_overdue_after_due_date(self):
        loan = AssetLoan.create("asset-1", "borrower", date.today() - timedelta(days=1),
                                "u1", "op-1")
        assert loan.is_overdue() is True

    def test_returned_loan_is_never_overdue(self):
        loan = AssetLoan.create("asset-1", "borrower", date.today() - timedelta(days=1),
                                "u1", "op-1")
        loan.return_loan("GOOD")
        assert loan.is_overdue() is False
        assert loan.is_returned() is True

    def test_return_twice_fails(self):
        loan = self._loan()
        loan.return_loan()
        with pytest.raises(AssetStateInvalidError):
            loan.return_loan()
