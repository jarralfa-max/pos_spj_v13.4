"""SET-9 — SqliteDeviceTestResultRepository against a real (in-memory)
SQLite born-clean schema.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from backend.domain.device_management.entities.device import Device
from backend.domain.device_management.entities.device_profile import DeviceProfile
from backend.domain.device_management.entities.device_test_result import DeviceTestResult
from backend.domain.device_management.enums import ConnectionType, DeviceType
from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
    SqliteDeviceProfileRepository,
)
from backend.infrastructure.db.repositories.device_management.device_repository import (
    SqliteDeviceRepository,
)
from backend.infrastructure.db.repositories.device_management.device_test_result_repository import (
    SqliteDeviceTestResultRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


@pytest.fixture
def test_repo(conn):
    return SqliteDeviceTestResultRepository(conn)


def _existing_device(conn, *, device_type: DeviceType, code: str) -> Device:
    branch_id = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (branch_id, "Sucursal"))
    profile = DeviceProfile.create(
        name=f"Dispositivo {code}", device_type=device_type,
        connection_profile=ConnectionProfile.create(ConnectionType.USB),
    )
    SqliteDeviceProfileRepository(conn).save(profile)
    device = Device.create(branch_id=branch_id, profile_id=profile.id, code=code, name=f"Dispositivo {code}")
    SqliteDeviceRepository(conn).save(device)
    return device


class TestDeviceTestResultRepository:
    def test_round_trips_scale_test(self, conn, test_repo):
        device = _existing_device(conn, device_type=DeviceType.SCALE, code="SCALE-01")
        conn.commit()
        result = DeviceTestResult.record(
            device_id=device.id, test_type="read_weight", success=True, message="120.5 g",
            tested_by_user_id="admin-1",
        )
        test_repo.save(result)
        conn.commit()

        history = test_repo.list_for_device(device.id)
        assert len(history) == 1
        assert history[0].test_type == "READ_WEIGHT"
        assert history[0].success is True
        assert history[0].tested_by_user_id == "admin-1"

    def test_round_trips_reader_test(self, conn, test_repo):
        device = _existing_device(conn, device_type=DeviceType.BARCODE_SCANNER, code="SCN-01")
        conn.commit()
        result = DeviceTestResult.record(device_id=device.id, test_type="scan", success=False, message="Sin lectura")
        test_repo.save(result)
        conn.commit()
        assert test_repo.list_for_device(device.id)[0].success is False

    def test_orders_most_recent_first(self, conn, test_repo):
        device = _existing_device(conn, device_type=DeviceType.SCALE, code="SCALE-01")
        conn.commit()
        now = datetime.now(timezone.utc)
        first = DeviceTestResult.record(device_id=device.id, test_type="read_weight", success=False, at=now)
        test_repo.save(first)
        conn.commit()
        second = DeviceTestResult.record(
            device_id=device.id, test_type="read_weight", success=True, at=now + timedelta(seconds=1),
        )
        test_repo.save(second)
        conn.commit()

        history = test_repo.list_for_device(device.id)
        assert [r.id for r in history] == [second.id, first.id]

    def test_device_id_must_reference_existing_device(self, conn, test_repo):
        orphan = DeviceTestResult.record(device_id=new_uuid(), test_type="scan", success=True)
        with pytest.raises(sqlite3.IntegrityError):
            test_repo.save(orphan)
            conn.commit()
        conn.rollback()

    def test_empty_history_for_unknown_device(self, conn, test_repo):
        assert test_repo.list_for_device(new_uuid()) == []

    def test_same_device_can_have_both_scale_and_reader_style_tests(self, conn, test_repo):
        # Deliberately checking DeviceTestResult's generality: a single
        # device (or, per this test, its test log) isn't hardcoded to one
        # test_type taxonomy the way PrinterTestResult is to printers.
        device = _existing_device(conn, device_type=DeviceType.SCALE, code="SCALE-01")
        conn.commit()
        test_repo.save(DeviceTestResult.record(device_id=device.id, test_type="read_weight", success=True))
        test_repo.save(DeviceTestResult.record(device_id=device.id, test_type="connectivity", success=True))
        conn.commit()
        assert {r.test_type for r in test_repo.list_for_device(device.id)} == {"READ_WEIGHT", "CONNECTIVITY"}
