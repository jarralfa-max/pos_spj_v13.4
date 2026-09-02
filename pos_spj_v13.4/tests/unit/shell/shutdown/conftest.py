import pytest

from frontend.desktop.shell.shutdown.shutdown_context import ShutdownContext
from frontend.desktop.shell.shutdown.shutdown_step_result import ShutdownStepResult


class RecordingStep:
    """A `ShutdownStep` test double: records that it ran and returns a
    preconfigured result (or raises, if `raise_error` is set)."""

    def __init__(self, name: str, result: ShutdownStepResult | None = None, *, raise_error: Exception | None = None):
        self.name = name
        self._result = result or ShutdownStepResult.ok(name)
        self._raise_error = raise_error
        self.ran = False
        self.received_context: ShutdownContext | None = None

    def run(self, context: ShutdownContext) -> ShutdownStepResult:
        self.ran = True
        self.received_context = context
        if self._raise_error is not None:
            raise self._raise_error
        return self._result


@pytest.fixture
def context() -> ShutdownContext:
    return ShutdownContext(reason="USER_REQUESTED")
