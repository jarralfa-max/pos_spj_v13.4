"""SET-8 — PrinterTestResult entity (§21/§23). Pure domain — no DB."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.domain.device_management.entities.printer_test_result import PrinterTestResult
from backend.shared.ids import is_uuidv7, new_uuid

_NOW = datetime.now(timezone.utc)


class TestRecord:
    def test_mints_uuidv7(self):
        result = PrinterTestResult.record(device_id=new_uuid(), success=True)
        assert is_uuidv7(result.id)

    def test_validates_device_id(self):
        with pytest.raises(ValueError):
            PrinterTestResult.record(device_id="not-a-uuid", success=True)

    def test_records_success_and_failure(self):
        success = PrinterTestResult.record(device_id=new_uuid(), success=True, message="Impresión de prueba OK")
        failure = PrinterTestResult.record(device_id=new_uuid(), success=False, message="Sin papel")
        assert success.success is True
        assert failure.success is False
        assert failure.message == "Sin papel"

    def test_records_who_and_when(self):
        result = PrinterTestResult.record(
            device_id=new_uuid(), success=True, tested_by_user_id="admin-1", at=_NOW,
        )
        assert result.tested_by_user_id == "admin-1"
        assert result.tested_at == _NOW.isoformat(timespec="seconds")

    def test_two_records_for_the_same_device_are_independent(self):
        device_id = new_uuid()
        first = PrinterTestResult.record(device_id=device_id, success=False, message="Falla 1")
        second = PrinterTestResult.record(device_id=device_id, success=True, message="Reparada")
        assert first.id != second.id
        assert first.success is False
        assert second.success is True
