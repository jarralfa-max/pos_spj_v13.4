"""Inventory domain services (cross-entity rules). INV-7: lots + expiry."""

from backend.domain.inventory.services.expiry_risk_service import ExpiryRiskService
from backend.domain.inventory.services.lot_allocation_service import (
    LotAllocation,
    LotAllocationService,
    LotCandidate,
)

__all__ = [
    "ExpiryRiskService",
    "LotAllocation",
    "LotAllocationService",
    "LotCandidate",
]
