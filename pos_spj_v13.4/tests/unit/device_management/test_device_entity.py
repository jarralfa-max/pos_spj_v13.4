"""SET-7 — Device entity lifecycle (§18). Pure domain — no DB."""

from __future__ import annotations

import pytest

from backend.domain.device_management.entities.device import Device
from backend.domain.device_management.enums import DeviceStatus
from backend.domain.device_management.exceptions import DeviceInvalidValueError, DeviceTransitionNotAllowedError
from backend.domain.device_management.value_objects.device_identifier import DeviceIdentifier
from backend.shared.ids import is_uuidv7, new_uuid


def _device(**overrides) -> Device:
    kwargs = dict(branch_id=new_uuid(), profile_id=new_uuid(), code="PRN-01", name="Impresora caja 1")
    kwargs.update(overrides)
    return Device.create(**kwargs)


class TestCreate:
    def test_mints_uuidv7_and_starts_active(self):
        device = _device()
        assert is_uuidv7(device.id)
        assert device.status is DeviceStatus.ACTIVE

    def test_requires_valid_branch_id(self):
        with pytest.raises(ValueError):
            _device(branch_id="not-a-uuid")

    def test_requires_valid_profile_id(self):
        with pytest.raises(ValueError):
            _device(profile_id="not-a-uuid")

    def test_requires_code_and_name(self):
        with pytest.raises(DeviceInvalidValueError):
            _device(code="   ")
        with pytest.raises(DeviceInvalidValueError):
            _device(name="")

    def test_hardware_identifier_is_optional(self):
        assert _device().hardware_identifier is None

    def test_hardware_identifier_round_trips(self):
        device = _device(hardware_identifier=DeviceIdentifier.create("USB-SN-123"))
        assert device.hardware_identifier.value == "USB-SN-123"


class TestBehavior:
    def test_reassign_profile(self):
        device = _device()
        new_profile_id = new_uuid()
        device.reassign_profile(new_profile_id)
        assert device.profile_id == new_profile_id

    def test_reassign_profile_validates_uuid(self):
        device = _device()
        with pytest.raises(ValueError):
            device.reassign_profile("not-a-uuid")

    def test_rename(self):
        device = _device()
        device.rename("Impresora caja 2")
        assert device.name == "Impresora caja 2"

    def test_rename_rejects_blank(self):
        device = _device()
        with pytest.raises(DeviceInvalidValueError):
            device.rename("   ")

    def test_update_notes(self):
        device = _device()
        device.update_notes("Cambiar rollo cada semana")
        assert device.notes == "Cambiar rollo cada semana"

    def test_update_notes_accepts_blank_to_clear(self):
        device = _device(notes="algo")
        device.update_notes("   ")
        assert device.notes == ""


class TestEstado:
    def test_activate_from_inactive_maintenance_or_blocked(self):
        for prepare in (
            lambda d: d.deactivate(),
            lambda d: d.enter_maintenance(),
            lambda d: d.block("motivo"),
        ):
            device = _device()
            prepare(device)
            device.activate()
            assert device.status is DeviceStatus.ACTIVE

    def test_enter_and_exit_maintenance(self):
        device = _device()
        device.enter_maintenance()
        assert device.status is DeviceStatus.MAINTENANCE
        device.exit_maintenance()
        assert device.status is DeviceStatus.ACTIVE

    def test_exit_maintenance_requires_maintenance_status(self):
        device = _device()
        with pytest.raises(DeviceTransitionNotAllowedError):
            device.exit_maintenance()

    def test_block_requires_reason_and_records_it(self):
        device = _device()
        with pytest.raises(DeviceInvalidValueError):
            device.block("   ")
        device.block("falla reportada por el cajero")
        assert device.status is DeviceStatus.BLOCKED
        assert device.blocked_reason == "falla reportada por el cajero"

    def test_unblock_requires_blocked_status(self):
        device = _device()
        with pytest.raises(DeviceTransitionNotAllowedError):
            device.unblock()

    def test_unblock_clears_reason(self):
        device = _device()
        device.block("motivo")
        device.unblock()
        assert device.status is DeviceStatus.ACTIVE
        assert device.blocked_reason is None

    def test_retire_is_terminal(self):
        device = _device()
        device.retire()
        assert device.status is DeviceStatus.RETIRED
        with pytest.raises(DeviceTransitionNotAllowedError):
            device.retire()
        with pytest.raises(DeviceTransitionNotAllowedError):
            device.activate()
        with pytest.raises(DeviceTransitionNotAllowedError):
            device.block("motivo")
