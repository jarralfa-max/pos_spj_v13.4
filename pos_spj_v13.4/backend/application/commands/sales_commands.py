"""Sales module commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from backend.application.commands.base_command import BaseCommand


@dataclass(frozen=True)
class CreateSaleCommand(BaseCommand):
    """Command for the canonical sale creation route.

    Field names are backend/API-facing English. The desktop UI remains
    responsible only for translating Spanish labels into this command shape.
    """

    items: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    payment: Mapping[str, Any] = field(default_factory=dict)
    customer_id: int | str | None = None
    notes: str = ""
    reservation_id: int | str | None = None
