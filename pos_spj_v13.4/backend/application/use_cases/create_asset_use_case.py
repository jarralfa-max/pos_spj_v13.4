"""Create asset use case."""

from __future__ import annotations

from backend.application.commands.asset_commands import CreateAssetCommand
from backend.application.use_cases.base_use_case import DelegatingUseCase


class CreateAssetUseCase(DelegatingUseCase[CreateAssetCommand]):
    name = "CreateAssetUseCase"
