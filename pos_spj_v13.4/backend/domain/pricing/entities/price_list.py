"""PriceList — a named set of prices with a lifecycle (PRC-2).

A list (BASE, CHANNEL, CUSTOMER, PROMOTIONAL) with an optional global discount and
inheritance from a parent list. Lifecycle DRAFT→UNDER_REVIEW→APPROVED→ACTIVE→
INACTIVE; an APPROVED/ACTIVE list is immutable (create a new one to change it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from backend.domain.pricing.enums import (
    IMMUTABLE_LIST_STATES,
    PriceListKind,
    PriceListStatus,
)
from backend.domain.pricing.exceptions import InvalidPriceListError
from backend.shared.ids import new_uuid

_TRANSITIONS = {
    PriceListStatus.DRAFT: frozenset({PriceListStatus.UNDER_REVIEW, PriceListStatus.INACTIVE}),
    PriceListStatus.UNDER_REVIEW: frozenset(
        {PriceListStatus.DRAFT, PriceListStatus.APPROVED, PriceListStatus.INACTIVE}),
    PriceListStatus.APPROVED: frozenset({PriceListStatus.ACTIVE, PriceListStatus.INACTIVE}),
    PriceListStatus.ACTIVE: frozenset({PriceListStatus.INACTIVE}),
    PriceListStatus.INACTIVE: frozenset(),
}


def _pct(value) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidPriceListError("discount_pct no puede ser float")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidPriceListError(f"Descuento inválido: {value!r}") from exc
    if not (Decimal("0") <= d < Decimal("100")):
        raise InvalidPriceListError("discount_pct debe estar en [0, 100)")
    return d


@dataclass
class PriceList:
    code: str
    name: str
    kind: PriceListKind
    id: str = field(default_factory=new_uuid)
    status: PriceListStatus = PriceListStatus.DRAFT
    channel: str | None = None
    discount_pct: Decimal = Decimal("0")
    inherits_from_id: str | None = None
    approved_by_user_id: str | None = None

    def __post_init__(self) -> None:
        code = (self.code or "").strip().upper()
        if not code:
            raise InvalidPriceListError("La lista de precios requiere un código")
        if not (self.name or "").strip():
            raise InvalidPriceListError("La lista de precios requiere un nombre")
        if not isinstance(self.kind, PriceListKind):
            self.kind = PriceListKind(str(self.kind))
        if not isinstance(self.status, PriceListStatus):
            self.status = PriceListStatus(str(self.status))
        if self.inherits_from_id == self.id:
            raise InvalidPriceListError("Una lista no puede heredar de sí misma")
        self.discount_pct = _pct(self.discount_pct)
        object.__setattr__(self, "code", code)

    @property
    def is_editable(self) -> bool:
        return self.status not in IMMUTABLE_LIST_STATES

    @property
    def is_active(self) -> bool:
        return self.status is PriceListStatus.ACTIVE

    def _transition(self, target: PriceListStatus) -> None:
        if target not in _TRANSITIONS.get(self.status, frozenset()):
            raise InvalidPriceListError(
                f"Transición no permitida: {self.status.value} → {target.value}")
        self.status = target

    def submit(self) -> None:
        self._transition(PriceListStatus.UNDER_REVIEW)

    def approve(self, *, approved_by_user_id: str) -> None:
        self._transition(PriceListStatus.APPROVED)
        self.approved_by_user_id = approved_by_user_id

    def activate(self) -> None:
        self._transition(PriceListStatus.ACTIVE)

    def deactivate(self) -> None:
        self._transition(PriceListStatus.INACTIVE)
