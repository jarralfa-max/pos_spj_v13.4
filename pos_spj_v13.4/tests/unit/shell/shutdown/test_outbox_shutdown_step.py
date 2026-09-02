from frontend.desktop.shell.shutdown.shutdown_step_result import ShutdownStepStatus
from frontend.desktop.shell.shutdown.steps.outbox_shutdown_step import OutboxShutdownStep
from tests.unit.shell.shutdown.conftest import context  # noqa: F401 (fixture)


class FakeOutbox:
    def __init__(self, pending: int, *, sent: int | None = None, raise_on_flush: Exception | None = None):
        self._pending = pending
        self._sent = pending if sent is None else sent
        self._raise_on_flush = raise_on_flush
        self.flush_calls = 0

    def pending_count(self) -> int:
        return self._pending

    def flush(self, *, timeout_seconds: float) -> int:
        self.flush_calls += 1
        if self._raise_on_flush is not None:
            raise self._raise_on_flush
        return self._sent


def test_nothing_pending_is_ok_and_does_not_call_flush(context):
    outbox = FakeOutbox(pending=0)
    result = OutboxShutdownStep(outbox).run(context)
    assert result.status is ShutdownStepStatus.OK
    assert outbox.flush_calls == 0


def test_everything_flushed_is_ok(context):
    outbox = FakeOutbox(pending=5, sent=5)
    result = OutboxShutdownStep(outbox).run(context)
    assert result.status is ShutdownStepStatus.OK
    assert "5" in result.message


def test_partial_flush_is_a_warning_not_a_failure(context):
    outbox = FakeOutbox(pending=5, sent=3)
    result = OutboxShutdownStep(outbox).run(context)
    assert result.status is ShutdownStepStatus.WARNING
    assert "2" in result.message


def test_flush_exception_is_a_failure(context):
    outbox = FakeOutbox(pending=5, raise_on_flush=RuntimeError("network down"))
    result = OutboxShutdownStep(outbox).run(context)
    assert result.status is ShutdownStepStatus.FAILED
    assert isinstance(result.exception, RuntimeError)


def test_timeout_seconds_is_passed_through_to_flush(context):
    captured = {}

    class CapturingOutbox(FakeOutbox):
        def flush(self, *, timeout_seconds):
            captured["timeout"] = timeout_seconds
            return super().flush(timeout_seconds=timeout_seconds)

    OutboxShutdownStep(CapturingOutbox(pending=1), timeout_seconds=3.5).run(context)
    assert captured["timeout"] == 3.5
