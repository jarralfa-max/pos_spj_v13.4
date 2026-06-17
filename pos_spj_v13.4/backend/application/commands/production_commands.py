"""Production module commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.application.commands.base_command import BaseCommand


@dataclass(frozen=True)
class ExecuteMeatProductionCommand(BaseCommand):
    """Command to execute a full meat production batch lifecycle.

    outputs: sequence of dicts {product_id: str (UUID), weight_kg: float}
    """

    product_id: str = ""
    recipe_id: str = ""
    batch_weight_kg: float = 0.0
    outputs: tuple = ()
    waste_kg: float = 0.0


@dataclass(frozen=True)
class OpenMeatBatchCommand(BaseCommand):
    """Open a meat production batch (first step of batch lifecycle)."""

    product_id: str = ""
    recipe_id: str = ""
    batch_weight_kg: float = 0.0


@dataclass(frozen=True)
class CloseMeatBatchCommand(BaseCommand):
    """Close an open meat production batch."""

    batch_id: str = ""
    outputs: tuple = ()
    waste_kg: float = 0.0
