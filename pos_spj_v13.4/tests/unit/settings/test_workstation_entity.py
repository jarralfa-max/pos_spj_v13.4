"""SET-6 — Workstation entity: registro, estado, versión, offline (§17).
Pure domain — no DB.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.domain.settings.entities.workstation import Workstation
from backend.domain.settings.enums import WorkstationStatus, WorkstationType
from backend.domain.settings.exceptions import (
    ConfigurationInvalidValueError,
    WorkstationTransitionNotAllowedError,
)
from backend.shared.ids import is_uuidv7, new_uuid

_NOW = datetime.now(timezone.utc)


def _workstation(**overrides) -> Workstation:
    kwargs = dict(
        branch_id=new_uuid(), code="POS-01", name="Caja 1", workstation_type=WorkstationType.POS,
    )
    kwargs.update(overrides)
    return Workstation.create(**kwargs)


class TestCreate:
    def test_mints_uuidv7_and_starts_active(self):
        workstation = _workstation()
        assert is_uuidv7(workstation.id)
        assert workstation.status is WorkstationStatus.ACTIVE

    def test_requires_valid_branch_id(self):
        with pytest.raises(ValueError):
            _workstation(branch_id="not-a-uuid")

    def test_requires_code_and_name(self):
        with pytest.raises(ConfigurationInvalidValueError):
            _workstation(code="   ")
        with pytest.raises(ConfigurationInvalidValueError):
            _workstation(name="")

    def test_defaults_offline_enabled_true(self):
        assert _workstation().offline_enabled is True

    def test_all_workstation_types_are_constructible(self):
        for workstation_type in WorkstationType:
            assert _workstation(workstation_type=workstation_type).workstation_type is workstation_type


class TestRegistroVersionOffline:
    def test_check_in_records_last_seen_and_version(self):
        workstation = _workstation()
        assert workstation.last_seen_at is None
        workstation.check_in(application_version="13.4.1", at=_NOW)
        assert workstation.last_seen_at == _NOW.isoformat(timespec="seconds")
        assert workstation.application_version == "13.4.1"

    def test_check_in_without_version_keeps_existing(self):
        workstation = _workstation(application_version="13.4.0")
        workstation.check_in(at=_NOW)
        assert workstation.application_version == "13.4.0"

    def test_check_in_refused_when_blocked_or_retired(self):
        blocked = _workstation()
        blocked.block("mantenimiento de seguridad")
        with pytest.raises(WorkstationTransitionNotAllowedError):
            blocked.check_in(at=_NOW)

        retired = _workstation()
        retired.retire()
        with pytest.raises(WorkstationTransitionNotAllowedError):
            retired.check_in(at=_NOW)

    def test_is_online_false_when_never_checked_in(self):
        workstation = _workstation()
        assert workstation.is_online(at=_NOW, staleness_threshold=timedelta(minutes=5)) is False

    def test_is_online_true_within_threshold(self):
        workstation = _workstation()
        workstation.check_in(at=_NOW)
        assert workstation.is_online(at=_NOW + timedelta(minutes=2), staleness_threshold=timedelta(minutes=5))

    def test_is_online_false_past_threshold(self):
        workstation = _workstation()
        workstation.check_in(at=_NOW)
        assert not workstation.is_online(at=_NOW + timedelta(minutes=10), staleness_threshold=timedelta(minutes=5))

    def test_set_offline_enabled(self):
        workstation = _workstation()
        workstation.set_offline_enabled(False)
        assert workstation.offline_enabled is False


class TestEstado:
    def test_activate_from_inactive_maintenance_or_blocked(self):
        for prepare in (
            lambda w: w.deactivate(),
            lambda w: w.enter_maintenance(),
            lambda w: w.block("motivo"),
        ):
            workstation = _workstation()
            prepare(workstation)
            workstation.activate()
            assert workstation.status is WorkstationStatus.ACTIVE

    def test_deactivate_requires_active_or_maintenance(self):
        workstation = _workstation()
        workstation.retire()
        with pytest.raises(WorkstationTransitionNotAllowedError):
            workstation.deactivate()

    def test_enter_and_exit_maintenance(self):
        workstation = _workstation()
        workstation.enter_maintenance()
        assert workstation.status is WorkstationStatus.MAINTENANCE
        workstation.exit_maintenance()
        assert workstation.status is WorkstationStatus.ACTIVE

    def test_exit_maintenance_requires_maintenance_status(self):
        workstation = _workstation()
        with pytest.raises(WorkstationTransitionNotAllowedError):
            workstation.exit_maintenance()

    def test_block_requires_reason(self):
        workstation = _workstation()
        with pytest.raises(ConfigurationInvalidValueError):
            workstation.block("   ")

    def test_block_records_reason_and_unblock_clears_it(self):
        workstation = _workstation()
        workstation.block("uso indebido reportado")
        assert workstation.status is WorkstationStatus.BLOCKED
        assert workstation.blocked_reason == "uso indebido reportado"
        workstation.unblock()
        assert workstation.status is WorkstationStatus.ACTIVE
        assert workstation.blocked_reason is None

    def test_unblock_requires_blocked_status(self):
        workstation = _workstation()
        with pytest.raises(WorkstationTransitionNotAllowedError):
            workstation.unblock()

    def test_cannot_block_a_retired_workstation(self):
        workstation = _workstation()
        workstation.retire()
        with pytest.raises(WorkstationTransitionNotAllowedError):
            workstation.block("motivo")

    def test_retire_is_terminal(self):
        workstation = _workstation()
        workstation.retire()
        assert workstation.status is WorkstationStatus.RETIRED
        with pytest.raises(WorkstationTransitionNotAllowedError):
            workstation.retire()
        with pytest.raises(WorkstationTransitionNotAllowedError):
            workstation.activate()
        with pytest.raises(WorkstationTransitionNotAllowedError):
            workstation.deactivate()
        with pytest.raises(WorkstationTransitionNotAllowedError):
            workstation.enter_maintenance()

    def test_retire_from_any_non_retired_state(self):
        for prepare in (
            lambda w: None,
            lambda w: w.deactivate(),
            lambda w: w.enter_maintenance(),
            lambda w: w.block("motivo"),
        ):
            workstation = _workstation()
            prepare(workstation)
            workstation.retire()
            assert workstation.status is WorkstationStatus.RETIRED


class TestUpdateDetails:
    """SET-6 follow-up (2026-08-22) — the UI needs to edit a registered
    workstation's descriptive fields, same gap `Device.rename()`/
    `update_notes()` closed for Dispositivos."""

    def test_updates_name_identifier_and_os(self):
        workstation = _workstation()
        workstation.update_details(
            name="  Caja 1 (mostrador)  ", device_identifier="  SN-123  ", operating_system="  Windows 11  ",
        )
        assert workstation.name == "Caja 1 (mostrador)"
        assert workstation.device_identifier == "SN-123"
        assert workstation.operating_system == "Windows 11"

    def test_clears_optional_fields_when_blank(self):
        workstation = _workstation(device_identifier="SN-123", operating_system="Windows 11")
        workstation.update_details(name="Caja 1")
        assert workstation.device_identifier == ""
        assert workstation.operating_system == ""

    def test_requires_name(self):
        workstation = _workstation()
        with pytest.raises(ConfigurationInvalidValueError):
            workstation.update_details(name="   ")

    def test_allowed_from_any_status(self):
        # Editing descriptive fields isn't a lifecycle transition — it
        # should work even on a blocked/retired workstation.
        workstation = _workstation()
        workstation.retire()
        workstation.update_details(name="Caja 1 retirada")
        assert workstation.name == "Caja 1 retirada"
        assert workstation.status is WorkstationStatus.RETIRED
