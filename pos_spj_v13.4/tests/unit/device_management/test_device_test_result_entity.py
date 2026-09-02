"""SET-9 — DeviceTestResult entity: the generalized diagnostic log for
scales/readers (§21). Pure domain — no DB.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.domain.device_management.entities.device_test_result import DeviceTestResult
from backend.domain.device_management.exceptions import DeviceInvalidValueError
from backend.shared.ids import is_uuidv7, new_uuid

_NOW = datetime.now(timezone.utc)


class TestRecord:
    def test_mints_uuidv7(self):
        result = DeviceTestResult.record(device_id=new_uuid(), test_type="read_weight", success=True)
        assert is_uuidv7(result.id)

    def test_validates_device_id(self):
        with pytest.raises(ValueError):
            DeviceTestResult.record(device_id="not-a-uuid", test_type="scan", success=True)

    def test_requires_test_type(self):
        with pytest.raises(DeviceInvalidValueError):
            DeviceTestResult.record(device_id=new_uuid(), test_type="   ", success=True)

    def test_normalizes_test_type(self):
        result = DeviceTestResult.record(device_id=new_uuid(), test_type="read_weight", success=True)
        assert result.test_type == "READ_WEIGHT"

    def test_records_success_and_failure(self):
        success = DeviceTestResult.record(device_id=new_uuid(), test_type="scan", success=True, message="1234567890128 leído")
        failure = DeviceTestResult.record(device_id=new_uuid(), test_type="scan", success=False, message="Lector sin respuesta")
        assert success.success is True
        assert failure.success is False

    def test_records_who_and_when(self):
        result = DeviceTestResult.record(
            device_id=new_uuid(), test_type="connectivity", success=True, tested_by_user_id="admin-1", at=_NOW,
        )
        assert result.tested_by_user_id == "admin-1"
        assert result.tested_at == _NOW.isoformat(timespec="seconds")

    def test_scale_and_reader_test_types_are_independent_records(self):
        device_id = new_uuid()
        weight_test = DeviceTestResult.record(device_id=device_id, test_type="read_weight", success=True)
        scan_test = DeviceTestResult.record(device_id=device_id, test_type="scan", success=True)
        assert weight_test.id != scan_test.id
        assert weight_test.test_type != scan_test.test_type
