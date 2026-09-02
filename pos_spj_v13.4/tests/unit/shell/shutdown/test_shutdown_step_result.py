from frontend.desktop.shell.shutdown.shutdown_step_result import ShutdownStepResult, ShutdownStepStatus


def test_ok_factory():
    result = ShutdownStepResult.ok("connections", "closed")
    assert result.status is ShutdownStepStatus.OK
    assert result.message == "closed"
    assert result.exception is None


def test_ok_factory_default_message_is_empty():
    result = ShutdownStepResult.ok("connections")
    assert result.message == ""


def test_warning_factory():
    result = ShutdownStepResult.warning("outbox", "1 pending")
    assert result.status is ShutdownStepStatus.WARNING


def test_failed_factory_carries_exception():
    exc = RuntimeError("boom")
    result = ShutdownStepResult.failed("connections", "broke", exception=exc)
    assert result.status is ShutdownStepStatus.FAILED
    assert result.exception is exc


def test_failed_factory_exception_is_optional():
    result = ShutdownStepResult.failed("connections", "broke")
    assert result.exception is None


def test_with_duration_preserves_other_fields():
    result = ShutdownStepResult.ok("workers", "stopped").with_duration(12.5)
    assert result.duration_ms == 12.5
    assert result.step_name == "workers"
    assert result.status is ShutdownStepStatus.OK
    assert result.message == "stopped"
