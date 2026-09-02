import pytest

from backend.bootstrap.bootstrap_severity import BootstrapFailureReason, BootstrapSeverity
from backend.bootstrap.bootstrap_step_result import BootstrapStepResult


def test_ok_is_successful_info():
    result = BootstrapStepResult.ok("step", "all good")
    assert result.success is True
    assert result.severity is BootstrapSeverity.INFO
    assert result.message == "all good"


def test_warning_is_successful():
    result = BootstrapStepResult.warning(
        "step", BootstrapFailureReason.BACKUP_OVERDUE, "backup is late",
    )
    assert result.success is True
    assert result.severity is BootstrapSeverity.WARNING


def test_warning_rejects_non_warning_reason():
    with pytest.raises(ValueError):
        BootstrapStepResult.warning(
            "step", BootstrapFailureReason.DATABASE_CORRUPTED_UNRECOVERABLE, "wrong bucket",
        )


def test_degraded_is_successful_and_carries_capability():
    result = BootstrapStepResult.degraded(
        "step", BootstrapFailureReason.WHATSAPP_UNAVAILABLE, "no whatsapp",
    )
    assert result.success is True
    assert result.severity is BootstrapSeverity.DEGRADED
    assert "WHATSAPP_UNAVAILABLE" in result.degraded_capabilities


def test_degraded_rejects_non_degraded_reason():
    with pytest.raises(ValueError):
        BootstrapStepResult.degraded(
            "step", BootstrapFailureReason.BACKUP_OVERDUE, "wrong bucket",
        )


def test_fatal_is_unsuccessful():
    result = BootstrapStepResult.fatal(
        "step", BootstrapFailureReason.SCHEMA_INCOMPLETE, "missing tables",
    )
    assert result.success is False
    assert result.severity is BootstrapSeverity.FATAL


def test_fatal_rejects_non_fatal_reason():
    with pytest.raises(ValueError):
        BootstrapStepResult.fatal(
            "step", BootstrapFailureReason.BACKUP_OVERDUE, "wrong bucket",
        )


def test_fatal_captures_exception_metadata():
    exc = ValueError("boom")
    result = BootstrapStepResult.fatal(
        "step", BootstrapFailureReason.BOOTSTRAP_INVALID, "failed", exception=exc,
    )
    assert result.exception_type == "ValueError"
    assert result.technical_details == "boom"


def test_with_duration_preserves_other_fields():
    result = BootstrapStepResult.ok("step", "msg").with_duration(12.5)
    assert result.duration_ms == 12.5
    assert result.step_name == "step"
    assert result.message == "msg"
