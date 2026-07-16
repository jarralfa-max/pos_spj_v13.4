"""DTOs for configurable HR catalogs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HRCatalogItemDTO:
    id: str
    code: str
    name: str
    active: bool
