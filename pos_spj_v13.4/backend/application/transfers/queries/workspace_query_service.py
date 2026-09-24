"""Read models for the canonical Transfers desktop/API workspace."""
from dataclasses import dataclass
from typing import Any, Protocol


# `BranchOptionViewModel` se eliminó el 2026-09-17 junto con
# `list_active_branches`: era el tipo de retorno de aquella consulta sin
# alcance y quedó sin un solo uso. (Ojo: Configuración tiene una clase
# HOMÓNIMA en `backend/application/queries/configuracion/`, viva y sin
# relación con ésta.) Las sucursales que un usuario puede ver salen de
# `BranchScopeQueryService` como `BranchOption`.


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
    # `list_active_branches` se retiró del contrato el 2026-09-17 junto con su
    # implementación: devolvía todas las sucursales activas sin filtrar por
    # usuario. Dejarlo DECLARADO habría obligado a cualquier implementador
    # futuro a reintroducir esa consulta sin alcance para satisfacer el
    # protocolo. Las sucursales que un usuario puede ver las resuelve
    # `BranchScopeQueryService` (backend/application/security/).
    def page(self, *, page_id: str, search: str = "") -> TransferPageViewModel: ...
    def product_base_unit_id(self, product_id: str) -> str | None: ...
