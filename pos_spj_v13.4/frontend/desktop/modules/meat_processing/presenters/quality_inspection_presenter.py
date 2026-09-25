"""Calidad → Por inspeccionar: lo que espera decisión y la decisión misma.

La pantalla no decide ni calcula: pide a `DecideOutputInspectionUseCase` (de
Calidad) con el permiso de la SESIÓN, y entrega los hechos de Calidad por el
bus para que Procesamiento e Inventario queden igual que lo decidido.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from backend.application.quality.queries import PendingInspectionsQueryService

DECISIONS = {"RELEASED": "Liberar", "BLOCKED": "Bloquear",
             "REWORK_REQUIRED": "Mandar a reproceso", "CONDEMNED": "Decomisar"}

_ORIGEN = {"meat_processing": "Procesamiento"}


@dataclass
class InspectionTableModel:
    rows: list[list[str]] = field(default_factory=list)
    row_ids: list[str] = field(default_factory=list)


def _peso(valor: Decimal) -> str:
    return f"{valor.normalize():f} kg" if valor else "—"


def _fecha(valor: str) -> str:
    return valor[:16].replace("T", " ") if valor else "—"


class QualityInspectionPresenter:
    def __init__(self, connection, *, branch_id: str, actor_provider, decide_uc,
                 dispatch=None, query_factory=PendingInspectionsQueryService) -> None:
        self._conn = connection
        self._branch_id = branch_id
        self._actor = actor_provider
        self._decide = decide_uc
        self._dispatch = dispatch
        self._query = query_factory

    def pending(self) -> InspectionTableModel:
        pendientes = self._query(self._conn).list_pending(self._branch_id)
        return InspectionTableModel(
            rows=[[p.product_name or "—", p.lot_code or "Sin código", _peso(p.held_quantity),
                   _fecha(p.requested_at), _ORIGEN.get(p.source_module, p.source_module)]
                  for p in pendientes],
            row_ids=[p.inspection_id for p in pendientes])

    @staticmethod
    def needs_reason(decision: str) -> bool:
        return decision != "RELEASED"

    def decide(self, inspection_id: str, decision: str, reason: str = "") -> tuple[bool, str]:
        from backend.shared.ids import new_uuid

        if decision not in DECISIONS:
            return False, "Decisión no válida."
        r = self._decide.execute(
            self._conn, inspection_id=inspection_id, decision=decision, reason=reason,
            operation_id=new_uuid(), actor_user_id=str(self._actor() or ""),
            dispatch=self._dispatch)
        if r.success:
            return True, f"{DECISIONS[decision]}: decisión registrada."
        return False, r.message
