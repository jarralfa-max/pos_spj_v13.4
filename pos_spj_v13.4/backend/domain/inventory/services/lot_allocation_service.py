"""LotAllocationService — choose which lots satisfy a demand (§20).

Pure domain logic. Perishables default to FEFO (first-expired, first-out); FIFO
and LIFO use the received date; MANUAL is caller-ordered. Expired lots and
blocked/quarantined/rejected lots are never allocated, and a lot without enough
remaining shelf life is skipped when a minimum is required.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.domain.inventory.enums import AllocationStrategy, LotQualityStatus
from backend.domain.inventory.exceptions import InsufficientInventoryError


def _as_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


@dataclass(frozen=True, slots=True)
class LotCandidate:
    lot_id: str
    available_quantity: Decimal
    expiration_date: str | None = None
    received_at: str | None = None
    quality_status: LotQualityStatus = LotQualityStatus.RELEASED


@dataclass(frozen=True, slots=True)
class LotAllocation:
    lot_id: str
    quantity: Decimal


_ALLOCATABLE = {LotQualityStatus.RELEASED, LotQualityStatus.PENDING_INSPECTION}


class LotAllocationService:
    def eligible(self, candidates, *, as_of: date | None = None,
                 min_shelf_life_days: int | None = None,
                 require_released: bool = False) -> list[LotCandidate]:
        ref = as_of or date.today()
        out = []
        for c in candidates:
            if c.available_quantity <= 0:
                continue
            allowed = ({LotQualityStatus.RELEASED} if require_released else _ALLOCATABLE)
            if c.quality_status not in allowed:
                continue
            exp = _as_date(c.expiration_date)
            if exp is not None:
                if exp < ref:
                    continue  # expired
                if min_shelf_life_days is not None \
                        and (exp - ref).days < min_shelf_life_days:
                    continue  # not enough remaining shelf life
            out.append(c)
        return out

    def _sort(self, candidates, strategy: AllocationStrategy) -> list[LotCandidate]:
        far = date.max
        if strategy is AllocationStrategy.FEFO:
            return sorted(candidates, key=lambda c: _as_date(c.expiration_date) or far)
        if strategy is AllocationStrategy.FIFO:
            return sorted(candidates, key=lambda c: _as_date(c.received_at) or date.max)
        if strategy is AllocationStrategy.LIFO:
            return sorted(candidates, key=lambda c: _as_date(c.received_at) or date.min,
                          reverse=True)
        return list(candidates)  # MANUAL_AUTHORIZED — caller order

    def allocate(self, candidates, requested_quantity: Decimal, *,
                 strategy: AllocationStrategy = AllocationStrategy.FEFO,
                 as_of: date | None = None, min_shelf_life_days: int | None = None,
                 require_released: bool = False) -> list[LotAllocation]:
        if requested_quantity <= 0:
            return []
        pool = self._sort(
            self.eligible(candidates, as_of=as_of,
                          min_shelf_life_days=min_shelf_life_days,
                          require_released=require_released),
            strategy)
        remaining = requested_quantity
        plan: list[LotAllocation] = []
        for c in pool:
            if remaining <= 0:
                break
            take = min(c.available_quantity, remaining)
            plan.append(LotAllocation(lot_id=c.lot_id, quantity=take))
            remaining -= take
        if remaining > 0:
            raise InsufficientInventoryError(
                f"Lotes elegibles insuficientes: faltan {remaining}")
        return plan
