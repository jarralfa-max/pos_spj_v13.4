from frontend.desktop.shell.shutdown.shutdown_context import ShutdownContext
from frontend.desktop.shell.shutdown.shutdown_coordinator import ShutdownCoordinator
from frontend.desktop.shell.shutdown.shutdown_step_result import ShutdownStepResult
from tests.unit.shell.shutdown.conftest import RecordingStep


def test_runs_every_step_in_order():
    order = []

    class OrderedStep(RecordingStep):
        def run(self, context):
            order.append(self.name)
            return super().run(context)

    steps = [OrderedStep("workers"), OrderedStep("outbox"), OrderedStep("connections")]
    ShutdownCoordinator(steps).shutdown()
    assert order == ["workers", "outbox", "connections"]


def test_all_ok_steps_produce_a_successful_result():
    steps = [RecordingStep("workers"), RecordingStep("outbox"), RecordingStep("connections")]
    result = ShutdownCoordinator(steps).shutdown()
    assert result.success is True
    assert len(result.step_results) == 3
    assert result.warnings == ()


def test_warning_step_does_not_flip_overall_success():
    steps = [
        RecordingStep("workers"),
        RecordingStep("outbox", ShutdownStepResult.warning("outbox", "1 pending")),
    ]
    result = ShutdownCoordinator(steps).shutdown()
    assert result.success is True
    assert result.warnings == ("1 pending",)


def test_failed_step_flips_overall_success_to_false():
    steps = [RecordingStep("workers", ShutdownStepResult.failed("workers", "broke"))]
    result = ShutdownCoordinator(steps).shutdown()
    assert result.success is False


def test_a_failed_step_does_not_prevent_later_steps_from_running():
    workers = RecordingStep("workers", ShutdownStepResult.failed("workers", "broke"))
    outbox = RecordingStep("outbox")
    connections = RecordingStep("connections")
    ShutdownCoordinator([workers, outbox, connections]).shutdown()
    assert workers.ran is True
    assert outbox.ran is True
    assert connections.ran is True


def test_an_exception_raised_by_a_step_is_captured_as_a_failed_result():
    steps = [RecordingStep("connections", raise_error=RuntimeError("disk full"))]
    result = ShutdownCoordinator(steps).shutdown()
    assert result.success is False
    assert result.step_results[0].step_name == "connections"
    assert "disk full" in result.step_results[0].message
    assert isinstance(result.step_results[0].exception, RuntimeError)


def test_an_exception_in_one_step_does_not_prevent_the_next_step_running():
    broken = RecordingStep("outbox", raise_error=RuntimeError("boom"))
    after = RecordingStep("connections")
    ShutdownCoordinator([broken, after]).shutdown()
    assert after.ran is True


def test_every_step_receives_the_same_context():
    ctx = ShutdownContext(reason="APPLICATION_UPDATE")
    step = RecordingStep("workers")
    ShutdownCoordinator([step]).shutdown(ctx)
    assert step.received_context is ctx


def test_shutdown_without_explicit_context_uses_a_default():
    step = RecordingStep("workers")
    ShutdownCoordinator([step]).shutdown()
    assert step.received_context is not None
    assert step.received_context.reason == ""


def test_empty_step_list_succeeds_trivially():
    result = ShutdownCoordinator([]).shutdown()
    assert result.success is True
    assert result.step_results == ()


def test_started_at_is_not_after_completed_at():
    result = ShutdownCoordinator([RecordingStep("workers")]).shutdown()
    assert result.started_at <= result.completed_at


def test_step_results_carry_a_duration():
    result = ShutdownCoordinator([RecordingStep("workers")]).shutdown()
    assert result.step_results[0].duration_ms >= 0.0
