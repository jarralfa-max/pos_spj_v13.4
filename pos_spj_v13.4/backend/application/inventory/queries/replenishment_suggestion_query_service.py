"""Sugerencias de reposición ABIERTAS de una sucursal — contrato de lectura de
Inventario para quien planea (Compras, Producción). Inventario las calcula
(`GenerateReplenishmentSuggestionsUseCase`); aquí sólo se leen."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.infrastructure.db.repositories.inventory.unit_of_work import InventoryUnitOfWork


@dataclass(frozen=True)
class OpenReplenishmentSuggestion:
    suggestion_id: str
    product_id: str
    warehouse_id: str
    suggested_quantity: Decimal
    current_available: Decimal
    urgency: str
    generated_at: str


class ReplenishmentSuggestionQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def open_for_branch(self, branch_id: str) -> list[OpenReplenishmentSuggestion]:
        filas = InventoryUnitOfWork(self._conn).replenishment_suggestions.list_open(
            branch_id=branch_id)
        return [OpenReplenishmentSuggestion(
            suggestion_id=str(f["id"]), product_id=str(f["product_id"]),
            warehouse_id=str(f["warehouse_id"]),
            suggested_quantity=Decimal(str(f["suggested_quantity"] or 0)),
            current_available=Decimal(str(f["current_available"] or 0)),
            urgency=str(f["urgency"]), generated_at=str(f["generated_at"]))
            for f in filas]
