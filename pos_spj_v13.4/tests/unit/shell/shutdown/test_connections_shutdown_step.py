from frontend.desktop.shell.shutdown.shutdown_step_result import ShutdownStepStatus
from frontend.desktop.shell.shutdown.steps.connections_shutdown_step import ConnectionsShutdownStep
from tests.unit.shell.shutdown.conftest import context  # noqa: F401 (fixture)


class FakeConnectionCloser:
    def __init__(self, closed: int = 0, *, raise_error: Exception | None = None):
        self._closed = closed
        self._raise_error = raise_error

    def close_all(self) -> int:
        if self._raise_error is not None:
            raise self._raise_error
        return self._closed


def test_successful_close_is_ok(context):
    result = ConnectionsShutdownStep(FakeConnectionCloser(closed=3)).run(context)
    assert result.status is ShutdownStepStatus.OK
    assert "3" in result.message


def test_zero_connections_is_still_ok(context):
    result = ConnectionsShutdownStep(FakeConnectionCloser(closed=0)).run(context)
    assert result.status is ShutdownStepStatus.OK


def test_exception_is_a_failure_not_propagated(context):
    closer = FakeConnectionCloser(raise_error=RuntimeError("locked file"))
    result = ConnectionsShutdownStep(closer).run(context)  # must not raise
    assert result.status is ShutdownStepStatus.FAILED
    assert isinstance(result.exception, RuntimeError)
    assert "locked file" in result.message
