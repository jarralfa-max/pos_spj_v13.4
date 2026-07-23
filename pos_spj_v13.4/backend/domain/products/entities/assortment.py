"""Assortment / AssortmentProduct — a curated product set per channel (§29).

An assortment groups products for a channel (POS, e-commerce, WhatsApp, wholesale…)
and optionally a branch. Products are linked, never duplicated; no price lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.channel_enums import SalesChannel
from backend.domain.products.exceptions import InvalidAssortmentError
from backend.shared.ids import new_uuid


@dataclass
class Assortment:
    name: str
    channel: SalesChannel
    id: str = field(default_factory=new_uuid)
    branch_id: str | None = None      # None = todas las sucursales del canal
    active: bool = True

    def __post_init__(self) -> None:
        if not (self.name or "").strip():
            raise InvalidAssortmentError("El surtido requiere un nombre")
        if not isinstance(self.channel, SalesChannel):
            try:
                self.channel = SalesChannel(str(self.channel))
            except ValueError as exc:
                raise InvalidAssortmentError(
                    f"Canal inválido: {self.channel!r}") from exc


@dataclass
class AssortmentProduct:
    assortment_id: str
    product_id: str
    id: str = field(default_factory=new_uuid)
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.assortment_id:
            raise InvalidAssortmentError("El elemento requiere surtido")
        if not self.product_id:
            raise InvalidAssortmentError("El elemento requiere producto")
