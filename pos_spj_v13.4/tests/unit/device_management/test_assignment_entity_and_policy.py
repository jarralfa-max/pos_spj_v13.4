"""SET-7 — WorkstationDeviceAssignment entity + DeviceAssignmentPolicy
(§20). Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.device_management.entities.workstation_device_assignment import (
    WorkstationDeviceAssignment,
)
from backend.domain.device_management.enums import ROLE_COMPATIBLE_DEVICE_TYPES, AssignmentRole, DeviceType
from backend.domain.device_management.exceptions import (
    DeviceAssignmentRoleNotCompatibleError,
    DeviceTransitionNotAllowedError,
)
from backend.domain.device_management.policies.device_assignment_policy import (
    assert_role_compatible_with_device_type,
    compatible_device_types,
)
from backend.shared.ids import is_uuidv7, new_uuid


class TestWorkstationDeviceAssignment:
    def test_assign_mints_uuidv7_and_starts_active(self):
        assignment = WorkstationDeviceAssignment.assign(
            workstation_id=new_uuid(), device_id=new_uuid(), role=AssignmentRole.SCALE,
        )
        assert is_uuidv7(assignment.id)
        assert assignment.active is True
        assert assignment.unassigned_at is None

    def test_assign_validates_workstation_and_device_ids(self):
        with pytest.raises(ValueError):
            WorkstationDeviceAssignment.assign(workstation_id="bad", device_id=new_uuid(), role=AssignmentRole.SCALE)
        with pytest.raises(ValueError):
            WorkstationDeviceAssignment.assign(workstation_id=new_uuid(), device_id="bad", role=AssignmentRole.SCALE)

    def test_unassign_marks_inactive_and_stamps_time(self):
        assignment = WorkstationDeviceAssignment.assign(
            workstation_id=new_uuid(), device_id=new_uuid(), role=AssignmentRole.CASH_DRAWER,
        )
        assignment.unassign()
        assert assignment.active is False
        assert assignment.unassigned_at is not None

    def test_unassign_twice_raises(self):
        assignment = WorkstationDeviceAssignment.assign(
            workstation_id=new_uuid(), device_id=new_uuid(), role=AssignmentRole.CASH_DRAWER,
        )
        assignment.unassign()
        with pytest.raises(DeviceTransitionNotAllowedError):
            assignment.unassign()

    def test_records_assigned_by_user(self):
        assignment = WorkstationDeviceAssignment.assign(
            workstation_id=new_uuid(), device_id=new_uuid(), role=AssignmentRole.SCALE,
            assigned_by_user_id="admin-1",
        )
        assert assignment.assigned_by_user_id == "admin-1"


class TestDeviceAssignmentPolicy:
    def test_every_role_has_at_least_one_compatible_device_type(self):
        for role in AssignmentRole:
            assert compatible_device_types(role), f"{role} has no compatible device types"

    def test_scale_role_only_accepts_scale(self):
        assert_role_compatible_with_device_type(AssignmentRole.SCALE, DeviceType.SCALE)
        with pytest.raises(DeviceAssignmentRoleNotCompatibleError):
            assert_role_compatible_with_device_type(AssignmentRole.SCALE, DeviceType.CASH_DRAWER)

    def test_receipt_printer_roles_accept_thermal_or_document_printer(self):
        for role in (
            AssignmentRole.PRIMARY_RECEIPT_PRINTER, AssignmentRole.SECONDARY_RECEIPT_PRINTER,
            AssignmentRole.KITCHEN_PRINTER, AssignmentRole.PRODUCTION_PRINTER, AssignmentRole.TRANSFER_PRINTER,
        ):
            assert_role_compatible_with_device_type(role, DeviceType.THERMAL_PRINTER)
            assert_role_compatible_with_device_type(role, DeviceType.DOCUMENT_PRINTER)
            with pytest.raises(DeviceAssignmentRoleNotCompatibleError):
                assert_role_compatible_with_device_type(role, DeviceType.LABEL_PRINTER)

    def test_label_printer_role_does_not_accept_thermal_printer(self):
        # LABEL_PRINTER (device type) and thermal receipt printers are
        # different hardware — a receipt printer must not masquerade as
        # the label-printer role.
        with pytest.raises(DeviceAssignmentRoleNotCompatibleError):
            assert_role_compatible_with_device_type(AssignmentRole.LABEL_PRINTER, DeviceType.THERMAL_PRINTER)
        assert_role_compatible_with_device_type(AssignmentRole.LABEL_PRINTER, DeviceType.LABEL_PRINTER)

    def test_scanner_role_accepts_barcode_or_qr(self):
        assert_role_compatible_with_device_type(AssignmentRole.SCANNER, DeviceType.BARCODE_SCANNER)
        assert_role_compatible_with_device_type(AssignmentRole.SCANNER, DeviceType.QR_SCANNER)

    def test_role_compatible_device_types_mapping_covers_every_role(self):
        assert set(ROLE_COMPATIBLE_DEVICE_TYPES) == set(AssignmentRole)
