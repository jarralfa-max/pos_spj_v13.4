"""Read models for the canonical Transfers desktop/API workspace."""
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class TransferKPIViewModel:
    title: str
    value: str
    variant: str = "neutral"


@dataclass(frozen=True, slots=True)
class TransferRowViewModel:
    entity_id: str
    reference: str
    origin: str
    destination: str
    status: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class TransferPageViewModel:
    rows: tuple[TransferRowViewModel, ...] = ()
    kpis: tuple[TransferKPIViewModel, ...] = ()
    empty_message: str = "No hay información para los filtros seleccionados."
    chart: Any | None = None


class TransfersWorkspaceQueryService(Protocol):
    def page(self, *, page_id: str, search: str = "") -> TransferPageViewModel: ...
