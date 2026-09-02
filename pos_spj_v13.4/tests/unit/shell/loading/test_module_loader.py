import pytest

from frontend.desktop.shell.loading.errors import ModuleActivationError
from frontend.desktop.shell.loading.module_load_state import ModuleLoadState
from frontend.desktop.shell.loading.module_loader import ModuleLoader
from frontend.desktop.shell.modules.errors import ModuleNotFoundError


def test_state_of_unloaded_module_is_not_loaded(modules, activator):
    loader = ModuleLoader(module_registry=modules, activator=activator)
    assert loader.state_of("eager_a") is ModuleLoadState.NOT_LOADED
    assert loader.is_loaded("eager_a") is False
    assert loader.result_for("eager_a") is None


def test_load_eager_modules_activates_only_eager_startup_mode(modules, activator):
    loader = ModuleLoader(module_registry=modules, activator=activator)
    loader.load_eager_modules()
    assert set(activator.calls) == {"eager_a", "eager_b"}


def test_load_eager_modules_returns_a_result_per_eager_module(modules, activator):
    loader = ModuleLoader(module_registry=modules, activator=activator)
    results = loader.load_eager_modules()
    assert {r.module_id for r in results} == {"eager_a", "eager_b"}
    assert all(r.state is ModuleLoadState.LOADED for r in results)


def test_successful_eager_load_marks_module_loaded(modules, activator):
    loader = ModuleLoader(module_registry=modules, activator=activator)
    loader.load_eager_modules()
    assert loader.is_loaded("eager_a") is True
    result = loader.result_for("eager_a")
    assert result.state is ModuleLoadState.LOADED
    assert result.error is None
    assert result.loaded_at is not None


def test_failed_eager_module_does_not_prevent_others_from_loading(modules, activator):
    activator.fail_for.add("eager_a")
    loader = ModuleLoader(module_registry=modules, activator=activator)
    results = loader.load_eager_modules()
    assert set(activator.calls) == {"eager_a", "eager_b"}
    by_id = {r.module_id: r for r in results}
    assert by_id["eager_a"].state is ModuleLoadState.FAILED
    assert by_id["eager_b"].state is ModuleLoadState.LOADED


def test_failed_module_result_wraps_the_original_exception(modules, activator):
    activator.fail_for.add("eager_a")
    loader = ModuleLoader(module_registry=modules, activator=activator)
    loader.load_eager_modules()
    error = loader.result_for("eager_a").error
    assert isinstance(error, ModuleActivationError)
    assert error.module_id == "eager_a"
    assert isinstance(error.cause, RuntimeError)


def test_ensure_loaded_activates_a_lazy_module_on_first_call(modules, activator):
    loader = ModuleLoader(module_registry=modules, activator=activator)
    result = loader.ensure_loaded("lazy_a")
    assert result.state is ModuleLoadState.LOADED
    assert activator.calls == ["lazy_a"]


def test_ensure_loaded_is_idempotent_for_an_already_loaded_module(modules, activator):
    loader = ModuleLoader(module_registry=modules, activator=activator)
    loader.ensure_loaded("lazy_a")
    loader.ensure_loaded("lazy_a")
    loader.ensure_loaded("lazy_a")
    assert activator.calls == ["lazy_a"]


def test_ensure_loaded_activates_on_demand_module(modules, activator):
    loader = ModuleLoader(module_registry=modules, activator=activator)
    result = loader.ensure_loaded("on_demand_a")
    assert result.state is ModuleLoadState.LOADED


def test_ensure_loaded_retries_a_previously_failed_module(modules, activator):
    activator.fail_for.add("lazy_a")
    loader = ModuleLoader(module_registry=modules, activator=activator)
    first = loader.ensure_loaded("lazy_a")
    assert first.state is ModuleLoadState.FAILED

    activator.fail_for.discard("lazy_a")
    second = loader.ensure_loaded("lazy_a")
    assert second.state is ModuleLoadState.LOADED
    assert activator.calls == ["lazy_a", "lazy_a"]


def test_ensure_loaded_unknown_module_id_raises(modules, activator):
    loader = ModuleLoader(module_registry=modules, activator=activator)
    with pytest.raises(ModuleNotFoundError):
        loader.ensure_loaded("does_not_exist")


def test_schedule_background_preload_uses_the_default_immediate_scheduler(modules, activator):
    loader = ModuleLoader(module_registry=modules, activator=activator)
    loader.schedule_background_preload()
    assert activator.calls == ["bg_a"]
    assert loader.is_loaded("bg_a") is True


def test_schedule_background_preload_uses_an_injected_scheduler(modules, activator):
    deferred_tasks = []
    loader = ModuleLoader(module_registry=modules, activator=activator)
    loader.schedule_background_preload(scheduler=deferred_tasks.append)
    assert activator.calls == []  # not run yet — only scheduled
    assert len(deferred_tasks) == 1
    deferred_tasks[0]()
    assert activator.calls == ["bg_a"]


def test_schedule_background_preload_only_targets_background_preload_modules(modules, activator):
    loader = ModuleLoader(module_registry=modules, activator=activator)
    loader.schedule_background_preload()
    assert "eager_a" not in activator.calls
    assert "lazy_a" not in activator.calls


def test_failed_background_preload_does_not_raise(modules, activator):
    activator.fail_for.add("bg_a")
    loader = ModuleLoader(module_registry=modules, activator=activator)
    loader.schedule_background_preload()  # must not raise
    assert loader.state_of("bg_a") is ModuleLoadState.FAILED
