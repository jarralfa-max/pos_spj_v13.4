"""Base command contracts for application use cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class BaseCommand:
    """Command envelope shared by desktop and future API entrypoints."""

    operation_id: str
    branch_id: str
    user_id: str | None = None
    user_name: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    def validate_context(self) -> None:
        missing = []
        if not self.operation_id:
            missing.append("operation_id")
        if not self.branch_id:
            missing.append("branch_id")
        if self.user_id is None and self.user_name is None:
            missing.append("user_id or user_name")
        if missing:
            raise ValueError("Missing required command field(s): " + ", ".join(missing))
