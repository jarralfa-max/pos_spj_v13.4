"""Presentation view models for Procesamiento Cárnico (PROC-23). Mirrors
frontend/desktop/modules/inventory/view_models.py's TableViewModel shape."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TableViewModel:
    rows: list[list[str]] = field(default_factory=list)
    row_ids: list[str] = field(default_factory=list)
    total: int = 0
