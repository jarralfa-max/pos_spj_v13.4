"""AssetImprovement — a completed improvement to an asset (ASSET-10, §36).

Purely evidentiary: cost_reference documents what was spent, but this entity
never changes the asset's accounting value directly (that's the legacy
`UPDATE activos SET valor_adquisicion = valor_adquisicion + ...` anti-pattern
§31 explicitly forbids). Capitalizing it is a separate, explicit workflow via
AssetCapitalizationProposal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from backend.domain.assets.exceptions import AssetDomainError
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AssetImprovement:
    id: str
    asset_id: str
    description: str
    completed_at: date
    cost_reference: Money
    operation_id: str
    operational_effect: str = ""
    useful_life_extension_months: int | None = None
    capacity_change: str = ""
    capitalization_proposal_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, asset_id: str, description: str, completed_at: date, cost_reference: Money,
               operation_id: str, **extra) -> "AssetImprovement":
        if not asset_id:
            raise AssetDomainError("AssetImprovement.asset_id is required")
        if not description or not description.strip():
            raise AssetDomainError("AssetImprovement.description is required")
        if not cost_reference.is_positive():
            raise AssetDomainError("AssetImprovement.cost_reference must be positive")
        return cls(id=new_uuid(), asset_id=asset_id, description=description.strip(),
                    completed_at=completed_at, cost_reference=cost_reference,
                    operation_id=operation_id, **extra)

    def link_to_proposal(self, proposal_id: str) -> None:
        if self.capitalization_proposal_id is not None:
            raise AssetDomainError(
                "Esta mejora ya está vinculada a una propuesta de capitalización")
        self.capitalization_proposal_id = proposal_id
