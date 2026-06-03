"""Base use case scaffolding for Phase 6."""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

from backend.application.commands.base_command import BaseCommand
from backend.application.dto.use_case_result import UseCaseResult


CommandT = TypeVar("CommandT", bound=BaseCommand)
UseCaseHandler = Callable[[CommandT], UseCaseResult]


class BaseUseCase(Generic[CommandT]):
    """Base class for explicitly injected application use cases."""

    name: str

    def execute(self, command: CommandT) -> UseCaseResult:
        raise NotImplementedError


class DelegatingUseCase(BaseUseCase[CommandT]):
    """Use case shell that delegates to a future application service/handler.

    This keeps Phase 6 non-invasive: current modules are not migrated, while new
    canonical use case routes can be wired gradually by injecting handlers.
    """

    def __init__(self, handler: UseCaseHandler[CommandT] | None = None) -> None:
        self._handler = handler

    def execute(self, command: CommandT) -> UseCaseResult:
        command.validate_context()
        if self._handler is None:
            return UseCaseResult.not_implemented(command.operation_id, use_case_name=self.name)
        return self._handler(command)
