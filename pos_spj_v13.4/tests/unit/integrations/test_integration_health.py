"""SET-19 — "Health": IntegrationHealthCheck + integration_health_policy.
current_status. Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.integrations.entities.integration_health_check import IntegrationHealthCheck
from backend.domain.integrations.enums import IntegrationHealthStatus
from backend.domain.integrations.exceptions import IntegrationsInvalidValueError
from backend.domain.integrations.policies.integration_health_policy import current_status
from backend.shared.ids import is_uuidv7, new_uuid


class TestIntegrationHealthCheckRecord:
    def test_mints_uuidv7(self):
        check = IntegrationHealthCheck.record(instance_id=new_uuid(), success=True)
        assert is_uuidv7(check.id)

    def test_validates_instance_id_as_uuid(self):
        with pytest.raises(ValueError):
            IntegrationHealthCheck.record(instance_id="not-a-uuid", success=True)

    def test_rejects_non_bool_success(self):
        with pytest.raises(IntegrationsInvalidValueError):
            IntegrationHealthCheck.record(instance_id=new_uuid(), success="yes")

    def test_trims_message(self):
        check = IntegrationHealthCheck.record(instance_id=new_uuid(), success=True, message="  ok  ")
        assert check.message == "ok"


def _check(success: bool, checked_at: str) -> IntegrationHealthCheck:
    check = IntegrationHealthCheck.record(instance_id=new_uuid(), success=success)
    check.checked_at = checked_at
    return check


class TestCurrentStatus:
    def test_empty_history_is_unknown(self):
        assert current_status([]) is IntegrationHealthStatus.UNKNOWN

    def test_most_recent_success_is_healthy(self):
        checks = [_check(True, "2026-08-21T10:00:00"), _check(True, "2026-08-21T11:00:00")]
        assert current_status(checks) is IntegrationHealthStatus.HEALTHY

    def test_most_recent_failure_with_earlier_success_is_degraded(self):
        checks = [_check(True, "2026-08-21T10:00:00"), _check(False, "2026-08-21T11:00:00")]
        assert current_status(checks) is IntegrationHealthStatus.DEGRADED

    def test_all_failures_is_down(self):
        checks = [_check(False, "2026-08-21T10:00:00"), _check(False, "2026-08-21T11:00:00")]
        assert current_status(checks) is IntegrationHealthStatus.DOWN

    def test_uses_most_recent_regardless_of_input_order(self):
        checks = [_check(True, "2026-08-21T12:00:00"), _check(False, "2026-08-21T10:00:00")]
        assert current_status(checks) is IntegrationHealthStatus.HEALTHY

    def test_single_success_is_healthy(self):
        assert current_status([_check(True, "2026-08-21T10:00:00")]) is IntegrationHealthStatus.HEALTHY

    def test_single_failure_is_down(self):
        assert current_status([_check(False, "2026-08-21T10:00:00")]) is IntegrationHealthStatus.DOWN
