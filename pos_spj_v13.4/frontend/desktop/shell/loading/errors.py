"""ModuleLoader errors — SHELL-13."""
from __future__ import annotations


class ModuleActivationError(RuntimeError):
    """Wraps whatever a `ModuleActivator.activate()` raised, with the
    `module_id` context `ModuleLoader` has and the raw activator error
    doesn't. Never swallows the original exception — `cause` holds it."""

    def __init__(self, module_id: str, cause: BaseException) -> None:
        self.module_id = module_id
        self.cause = cause
        super().__init__(f"El módulo '{module_id}' falló al cargar: {cause}")
