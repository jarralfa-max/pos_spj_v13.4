"""SET-10 — "Asignación": CASH_DRAWER/PAYMENT_TERMINAL through the
existing WorkstationDeviceAssignment + DeviceAssignmentPolicy (built
generically in SET-7) — confirms these two roles work correctly rather
than re-implementing assignment logic. Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.device_management.entities.workstation_device_assignment import (
    WorkstationDeviceAssignment,
)
from backend.domain.device_management.enums import AssignmentRole, DeviceType
from backend.domain.device_management.exceptions import DeviceAssignmentRoleNotCompatibleError
from backend.domain.device_management.policies.device_assignment_policy import (
    assert_role_compatible_with_device_type,
)
from backend.shared.ids import new_uuid


class TestCashDrawerAssignment:
    def test_cash_drawer_role_accepts_cash_drawer_device_type(self):
        assert_role_compatible_with_device_type(AssignmentRole.CASH_DRAWER, DeviceType.CASH_DRAWER)

    def test_cash_drawer_role_rejects_other_device_types(self):
        with pytest.raises(DeviceAssignmentRoleNotCompatibleError):
            assert_role_compatible_with_device_type(AssignmentRole.CASH_DRAWER, DeviceType.SCALE)

    def test_assign_and_unassign_cash_drawer(self):
        assignment = WorkstationDeviceAssignment.assign(
            workstation_id=new_uuid(), device_id=new_uuid(), role=AssignmentRole.CASH_DRAWER,
            assigned_by_user_id="admin-1",
        )
        assert assignment.active is True
        assignment.unassign()
        assert assignment.active is False


class TestPaymentTerminalAssignment:
    def test_payment_terminal_role_accepts_payment_terminal_device_type(self):
        assert_role_compatible_with_device_type(AssignmentRole.PAYMENT_TERMINAL, DeviceType.PAYMENT_TERMINAL)

    def test_payment_terminal_role_rejects_other_device_types(self):
        with pytest.raises(DeviceAssignmentRoleNotCompatibleError):
            assert_role_compatible_with_device_type(AssignmentRole.PAYMENT_TERMINAL, DeviceType.CASH_DRAWER)

    def test_assign_payment_terminal(self):
        assignment = WorkstationDeviceAssignment.assign(
            workstation_id=new_uuid(), device_id=new_uuid(), role=AssignmentRole.PAYMENT_TERMINAL,
        )
        assert assignment.role is AssignmentRole.PAYMENT_TERMINAL
