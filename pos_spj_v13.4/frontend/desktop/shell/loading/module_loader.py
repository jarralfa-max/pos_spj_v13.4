"""ModuleLoader — SHELL-13.

Turns SHELL-8's `StartupMode` from a declared-but-unused field into actual
behavior:
- `EAGER` modules are activated by `load_eager_modules()`, meant to be
  called once at shell startup.
- `LAZY`/`ON_DEMAND` modules are activated the first time something
  actually needs them, via `ensure_loaded()` — idempotent: a module
  already in `LOADED` state is never re-activated. A module in `FAILED`
  state *is* retried on the next `ensure_loaded()` call — a transient
  failure (a flaky connection, a missing optional dependency) shouldn't
  permanently lock a module out for the rest of the session.
- `BACKGROUND_PRELOAD` modules are activated through an injected
  `scheduler` callable via `schedule_background_preload()`, so activation
  doesn't block whatever's calling it — this loader has no opinion on
  *how* deferred work happens (a `QTimer.singleShot` wrapper in
  production, `immediate_scheduler` — the default — in tests and any
  caller that doesn't need real deferral).

A failed activation is recorded, never raised out of `load_eager_modules()`
or `schedule_background_preload()`'s scheduled task — one broken module
must not prevent every other module, or the whole shell, from starting.
`ensure_loaded()` *does* return the failed `ModuleLoadResult` rather than
raising, too — the caller (SHELL-13's `ApplicationWindow` integration)
decides what a failure means for navigation (an error view), not this
class.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from frontend.desktop.shell.loading.errors import ModuleActivationError
from frontend.desktop.shell.loading.module_activator import ModuleActivator
from frontend.desktop.shell.loading.module_load_result import ModuleLoadResult
from frontend.desktop.shell.loading.module_load_state import ModuleLoadState
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.module_registry import ModuleRegistry
from frontend.desktop.shell.modules.startup_mode import StartupMode

Scheduler = Callable[[Callable[[], None]], None]


def immediate_scheduler(task: Callable[[], None]) -> None:
    task()


class ModuleLoader:
    def __init__(self, *, module_registry: ModuleRegistry, activator: ModuleActivator) -> None:
        self._modules = module_registry
        self._activator = activator
        self._results: dict[str, ModuleLoadResult] = {}

    def state_of(self, module_id: str) -> ModuleLoadState:
        result = self._results.get(module_id)
        return result.state if result is not None else ModuleLoadState.NOT_LOADED

    def is_loaded(self, module_id: str) -> bool:
        return self.state_of(module_id) is ModuleLoadState.LOADED

    def result_for(self, module_id: str) -> ModuleLoadResult | None:
        return self._results.get(module_id)

    def load_eager_modules(self) -> tuple[ModuleLoadResult, ...]:
        return tuple(self._activate(module) for module in self._modules.by_startup_mode(StartupMode.EAGER))

    def schedule_background_preload(self, scheduler: Scheduler = immediate_scheduler) -> None:
        for module in self._modules.by_startup_mode(StartupMode.BACKGROUND_PRELOAD):
            scheduler(lambda module=module: self._activate(module))

    def ensure_loaded(self, module_id: str) -> ModuleLoadResult:
        existing = self._results.get(module_id)
        if existing is not None and existing.state is ModuleLoadState.LOADED:
            return existing
        return self._activate(self._modules.require(module_id))

    def _activate(self, module: ModuleDescriptor) -> ModuleLoadResult:
        self._results[module.module_id] = ModuleLoadResult(
            module_id=module.module_id, state=ModuleLoadState.LOADING, error=None, loaded_at=None,
        )
        try:
            self._activator.activate(module)
        except Exception as exc:  # noqa: BLE001 - any activation failure is captured, never crashes the caller
            result = ModuleLoadResult(
                module_id=module.module_id, state=ModuleLoadState.FAILED,
                error=ModuleActivationError(module.module_id, exc), loaded_at=None,
            )
        else:
            result = ModuleLoadResult(
                module_id=module.module_id, state=ModuleLoadState.LOADED,
                error=None, loaded_at=datetime.now(timezone.utc),
            )
        self._results[module.module_id] = result
        return result
